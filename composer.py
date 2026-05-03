import json
import re
from datetime import datetime, timezone
from typing import Optional

from llm_client import LLMClient
from models import AnalystOutput, StrategyOutput, ComposerOutput, TickAction
from context_store import ContextStore
from conversation import ConversationStore, ConvState, Conversation
from suppression import SuppressionStore
from message_validator import MessageValidator
from prompts import (
    ANALYST_PROMPT,
    STRATEGIST_PROMPT,
    COMPOSER_PROMPT,
    REPLY_COMPOSER_PROMPT,
)


class ThreePassComposer:
    def __init__(
        self,
        llm: LLMClient,
        ctx: ContextStore,
        convs: ConversationStore,
        suppression: SuppressionStore,
        enable_validation: bool = True,
        max_retries: int = 2,
    ):
        self.llm = llm
        self.ctx = ctx
        self.convs = convs
        self.suppression = suppression
        self.enable_validation = enable_validation
        self.max_retries = max_retries
        self.validator = MessageValidator() if enable_validation else None

    async def compose_proactive(
        self,
        trigger_id: str,
        now_iso: str,
        analyst_override: Optional[AnalystOutput] = None,
    ) -> Optional[TickAction]:
        """
        Full three-pass pipeline for a single trigger.
        Returns None if Strategist decides to skip.
        """
        trigger = self.ctx.get("trigger", trigger_id)
        if not trigger:
            return None

        expires_at = trigger.get("expires_at")
        if expires_at and _is_expired(expires_at, now_iso):
            return None

        merchant_id = trigger.get("merchant_id")
        customer_id = trigger.get("customer_id")

        merchant = self.ctx.get("merchant", merchant_id) if merchant_id else None
        if not merchant:
            return None

        category_slug = merchant.get("category_slug")
        category = self.ctx.get("category", category_slug) if category_slug else None

        customer = self.ctx.get("customer", customer_id) if customer_id else None

        analyst_out = analyst_override or await self._run_analyst(
            category, merchant, trigger, customer
        )
        if analyst_out.urgency_assessment == "SKIP":
            return None

        strategy = await self._run_strategist(analyst_out, trigger, merchant, customer)
        if not strategy.send:
            return None

        sup_key = trigger.get("suppression_key", trigger_id)
        if self.suppression.is_suppressed(sup_key):
            return None

        composed = await self._run_composer(
            strategy, analyst_out, category, merchant, trigger, customer
        )

        if _contains_url(composed.body):
            composed = ComposerOutput(
                body=_strip_urls(composed.body),
                template_params=composed.template_params,
                cta=composed.cta,
            )

        conv_id = _build_conv_id(merchant_id, trigger_id)
        conv = self.convs.get_or_create(conv_id, merchant_id, customer_id, trigger_id)
        conv.add_sent_body(composed.body)
        conv.add_turn("vera", composed.body)

        self.suppression.suppress(sup_key)

        trigger_kind = trigger.get("kind", "generic")

        return TickAction(
            conversation_id=conv_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            send_as=strategy.send_as,
            trigger_id=trigger_id,
            template_name=f"vera_{trigger_kind}_v1",
            template_params=composed.template_params,
            body=composed.body,
            cta=composed.cta,
            suppression_key=sup_key,
            rationale=strategy.rationale_for_judge,
        )

    async def compose_reply(
        self,
        conversation_id: str,
        merchant_id: Optional[str],
        customer_id: Optional[str],
        incoming_message: str,
        turn_number: int,
        intent: str,
    ) -> dict:
        """
        Compose the bot's reply to an incoming message.
        Returns a dict matching ReplyResponse shape.
        """
        conv = self.convs.get(conversation_id)
        if not conv:
            return {
                "action": "end",
                "rationale": "Unknown conversation_id; cannot continue.",
            }

        if intent == "AUTO_REPLY":
            return self._handle_auto_reply(conv, incoming_message)

        if intent in ("EXPLICIT_NO", "HOSTILE"):
            self.convs.transition(conversation_id, ConvState.HOSTILE)
            return {
                "action": "end",
                "rationale": (
                    "Merchant expressed clear disinterest or frustration. "
                    "Closing gracefully; suppressing this merchant for 30 days."
                ),
            }

        if intent == "EXPLICIT_YES":
            self.convs.transition(conversation_id, ConvState.ACTION_MODE)

        if intent in ("SOFT_ENGAGE", "QUESTION", "UNRELATED"):
            if conv.state not in (ConvState.ACTION_MODE, ConvState.HOSTILE):
                self.convs.transition(conversation_id, ConvState.ENGAGED)

        mid = merchant_id or conv.merchant_id
        merchant = self.ctx.get("merchant", mid) if mid else None
        category_slug = merchant.get("category_slug") if merchant else None
        category = self.ctx.get("category", category_slug) if category_slug else None
        trigger = self.ctx.get("trigger", conv.trigger_id)
        customer = (
            self.ctx.get("customer", customer_id or conv.customer_id)
            if (customer_id or conv.customer_id)
            else None
        )

        conv.add_turn("merchant", incoming_message)

        history = conv.history_text()
        state_name = conv.state.value
        sent_bodies = conv.sent_bodies

        prompt = REPLY_COMPOSER_PROMPT.format(
            conv_state=state_name,
            intent=intent,
            history=history,
            incoming=incoming_message,
            turn_number=turn_number,
            merchant_name=merchant.get("identity", {}).get("name", "") if merchant else "",
            owner_name=merchant.get("identity", {}).get("owner_first_name", "") if merchant else "",
            languages=str(merchant.get("identity", {}).get("languages", ["en"]))
            if merchant
            else "['en']",
            category_voice=json.dumps(category.get("voice", {})) if category else "{}",
            category_taboos=str(category.get("voice", {}).get("vocab_taboo", []))
            if category
            else "[]",
            trigger_kind=trigger.get("kind", "unknown") if trigger else "unknown",
            trigger_payload=json.dumps(trigger.get("payload", {})) if trigger else "{}",
            offers=json.dumps(merchant.get("offers", [])) if merchant else "[]",
            customer_state=customer.get("state", "") if customer else "",
            customer_name=customer.get("identity", {}).get("name", "") if customer else "",
            sent_bodies_summary=str(sent_bodies[-3:]) if sent_bodies else "[]",
        )

        raw = await self.llm.complete(prompt, max_tokens=400)
        parsed = _parse_json(raw)

        action = parsed.get("action", "send")
        body = parsed.get("body", "")

        if body and conv.is_body_repeat(body):
            body = body + " (follow-up)"

        if body:
            conv.add_sent_body(body)
            conv.add_turn("vera", body)

        result = {
            "action": action,
            "rationale": parsed.get("rationale", "Continuing conversation."),
        }
        if action == "send":
            result["body"] = body
            result["cta"] = parsed.get("cta", "open_ended")
        elif action == "wait":
            result["wait_seconds"] = parsed.get("wait_seconds", 3600)

        return result

    async def _run_analyst(
        self,
        category: Optional[dict],
        merchant: dict,
        trigger: dict,
        customer: Optional[dict],
    ) -> AnalystOutput:
        prompt = ANALYST_PROMPT.format(
            category_json=json.dumps(category or {}, ensure_ascii=False),
            merchant_json=json.dumps(merchant, ensure_ascii=False),
            trigger_json=json.dumps(trigger, ensure_ascii=False),
            customer_json=json.dumps(customer or {}, ensure_ascii=False),
        )
        raw = await self.llm.complete(prompt, max_tokens=600)
        parsed = _parse_json(raw)
        return AnalystOutput(
            merchant_vs_peers=parsed.get("merchant_vs_peers", "No peer data"),
            cohort_math=parsed.get("cohort_math", ""),
            urgency_assessment=parsed.get("urgency_assessment", "SEND_NOW"),
            best_compulsion_lever=parsed.get("best_compulsion_lever", "specificity"),
            contrarian_flag=parsed.get("contrarian_flag"),
            tone_override=parsed.get("tone_override"),
            opportunity_score=float(parsed.get("opportunity_score", 0.5)),
        )

    async def _run_strategist(
        self,
        analyst: AnalystOutput,
        trigger: dict,
        merchant: dict,
        customer: Optional[dict],
    ) -> StrategyOutput:
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if scope == "customer" else "vera"

        prompt = STRATEGIST_PROMPT.format(
            analyst_json=analyst.model_dump_json(),
            trigger_json=json.dumps(trigger, ensure_ascii=False),
            merchant_json=json.dumps(merchant, ensure_ascii=False),
            customer_json=json.dumps(customer or {}, ensure_ascii=False),
            send_as=send_as,
        )
        raw = await self.llm.complete(prompt, max_tokens=500)
        parsed = _parse_json(raw)

        return StrategyOutput(
            send=parsed.get("send", True),
            skip_reason=parsed.get("skip_reason"),
            angle=parsed.get("angle", "general_value"),
            lever=parsed.get("lever", analyst.best_compulsion_lever),
            secondary_levers=parsed.get("secondary_levers", []),
            cta_type=parsed.get("cta_type", "open_ended"),
            tone=parsed.get("tone", "warm_practical"),
            key_numbers_to_include=parsed.get("key_numbers_to_include", []),
            what_to_avoid=parsed.get("what_to_avoid", []),
            send_as=send_as,
            rationale_for_judge=parsed.get(
                "rationale_for_judge",
                "Composed from 4-context analysis.",
            ),
        )

    async def _run_composer(
        self,
        strategy: StrategyOutput,
        analyst: AnalystOutput,
        category: Optional[dict],
        merchant: dict,
        trigger: dict,
        customer: Optional[dict],
    ) -> ComposerOutput:
        identity = merchant.get("identity", {})
        lang = identity.get("languages", ["en"])
        voice = category.get("voice", {}) if category else {}
        offers = merchant.get("offers", [])

        prompt = COMPOSER_PROMPT.format(
            angle=strategy.angle,
            lever=strategy.lever,
            cta_type=strategy.cta_type,
            tone=strategy.tone,
            key_numbers=str(strategy.key_numbers_to_include),
            what_to_avoid=str(strategy.what_to_avoid),
            derived_insight=analyst.contrarian_flag or analyst.cohort_math or "",
            merchant_vs_peers=analyst.merchant_vs_peers,
            owner_name=identity.get("owner_first_name", ""),
            merchant_name=identity.get("name", ""),
            city=identity.get("city", ""),
            locality=identity.get("locality", ""),
            languages=str(lang),
            category_voice=json.dumps(voice, ensure_ascii=False),
            vocab_taboo=str(voice.get("vocab_taboo", [])),
            trigger_kind=trigger.get("kind", ""),
            trigger_payload=json.dumps(trigger.get("payload", {}), ensure_ascii=False),
            trigger_scope=trigger.get("scope", "merchant"),
            offers=json.dumps(offers, ensure_ascii=False),
            customer_json=json.dumps(customer or {}, ensure_ascii=False),
            send_as=strategy.send_as,
            peer_stats=json.dumps(category.get("peer_stats", {}) if category else {}, ensure_ascii=False),
            digest_items=json.dumps(category.get("digest", []) if category else [], ensure_ascii=False),
        )
        
        # Try up to max_retries times to get a valid message
        best_output = None
        best_score = 0.0
        
        for attempt in range(self.max_retries + 1):
            raw = await self.llm.complete(prompt, max_tokens=400)
            parsed = _parse_json(raw)
            
            output = ComposerOutput(
                body=parsed.get("body", ""),
                template_params=[str(p) if p is not None else "" for p in parsed.get("template_params", [])],
                cta=parsed.get("cta", "open_ended"),
            )
            
            # If validation is disabled, return immediately
            if not self.enable_validation:
                return output
            
            # Validate the message
            is_valid, issues, checks = self.validator.validate_message(
                output.body, trigger, merchant, category
            )
            score = self.validator.get_validation_score(checks)
            
            # Track best attempt
            if score > best_score:
                best_score = score
                best_output = output
            
            # If valid and score is good enough, return
            if is_valid and score >= 0.75:
                if attempt > 0:
                    print(f"✅ Validation passed on attempt {attempt + 1} (score: {score:.2f})")
                return output
            
            # Log validation issues
            if attempt < self.max_retries:
                print(f"⚠️  Attempt {attempt + 1} validation issues (score: {score:.2f}):")
                for issue in issues[:3]:  # Show top 3 issues
                    print(f"   - {issue}")
        
        # If we exhausted retries, return best attempt
        print(f"⚠️  Used best attempt after {self.max_retries + 1} tries (score: {best_score:.2f})")
        return best_output or output

    def _handle_auto_reply(self, conv: Conversation, message: str) -> dict:
        is_same = (
            conv.last_auto_reply_text is not None
            and message.strip() == conv.last_auto_reply_text.strip()
        )

        if conv.state == ConvState.AUTO_REPLY_CONFIRMED or conv.auto_reply_count >= 2:
            self.convs.transition(conv.conversation_id, ConvState.CLOSED)
            return {
                "action": "end",
                "rationale": (
                    "Auto-reply received 3+ times. Owner is not at the phone. "
                    "Closing conversation; will retry via a fresh trigger."
                ),
            }

        if conv.state == ConvState.AUTO_REPLY_SUSPECTED:
            conv.auto_reply_count += 1
            conv.last_auto_reply_text = message
            self.convs.transition(conv.conversation_id, ConvState.AUTO_REPLY_CONFIRMED)
            return {
                "action": "wait",
                "wait_seconds": 86400,
                "rationale": (
                    "Second auto-reply in a row. Owner is away. "
                    "Waiting 24h before any follow-up."
                ),
            }

        conv.auto_reply_count += 1
        conv.last_auto_reply_text = message
        self.convs.transition(conv.conversation_id, ConvState.AUTO_REPLY_SUSPECTED)
        return {
            "action": "send",
            "body": (
                "Looks like an auto-reply 😊 "
                "When you see this, just reply 'Yes' and I'll continue from here."
            ),
            "cta": "binary_yes_no",
            "rationale": (
                "Detected WhatsApp Business canned auto-reply. "
                "Sending one clarifying prompt for the owner, then standing by."
            ),
        }


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    try:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


def _is_expired(expires_at: str, now_iso: str) -> bool:
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return now > exp
    except Exception:
        return False


def _contains_url(text: str) -> bool:
    return bool(re.search(r"https?://\S+", text))


def _strip_urls(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _build_conv_id(merchant_id: str, trigger_id: str) -> str:
    safe_mid = merchant_id[:20].replace("_", "-")
    safe_tid = trigger_id[:20].replace("_", "-")
    return f"conv_{safe_mid}_{safe_tid}"
