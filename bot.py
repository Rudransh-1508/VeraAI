import asyncio
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from models import ContextPush, TickRequest, TickAction, ReplyRequest
from context_store import ContextStore
from conversation import ConversationStore
from suppression import SuppressionStore
from llm_client import LLMClient
from composer import ThreePassComposer
from classifier import ReplyClassifier


app = FastAPI(title="Vera Bot", version="1.0.0")
START_TIME = time.time()

ctx_store = ContextStore()
conv_store = ConversationStore()
sup_store = SuppressionStore()
llm = LLMClient()
composer = ThreePassComposer(llm, ctx_store, conv_store, sup_store)
classifier = ReplyClassifier(llm)


@app.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": ctx_store.count_by_scope(),
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "YOUR_TEAM_NAME",
        "team_members": ["YOUR_NAME"],
        "model": "claude-sonnet-4-6",
        "approach": (
            "Three-pass Think→Strategize→Compose pipeline. "
            "Pass 1 (Analyst) derives implicit facts from contexts. "
            "Pass 2 (Strategist) decides send/skip + picks compulsion lever. "
            "Pass 3 (Composer) writes constrained by the brief above."
        ),
        "contact_email": "YOUR_EMAIL",
        "version": "1.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/context")
async def push_context(body: ContextPush):
    valid_scopes = {"category", "merchant", "customer", "trigger"}
    if body.scope not in valid_scopes:
        return JSONResponse(
            status_code=400,
            content={
                "accepted": False,
                "reason": "invalid_scope",
                "details": f"scope must be one of {valid_scopes}",
            },
        )

    ack = ctx_store.push(body)

    if not ack.accepted:
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": ack.reason,
                "current_version": ack.current_version,
            },
        )

    return {
        "accepted": True,
        "ack_id": ack.ack_id,
        "stored_at": ack.stored_at,
    }


@app.post("/v1/tick")
async def tick(body: TickRequest):
    """
    Core proactive messaging logic.
    Runs Analyst in parallel across all viable triggers,
    then Strategist + Composer sequentially for top candidates.
    One action per merchant per tick.
    """
    now_iso = body.now

    viable = []
    for trg_id in body.available_triggers:
        trg = ctx_store.get("trigger", trg_id)
        if not trg:
            continue
        sup_key = trg.get("suppression_key", trg_id)
        merchant_id = trg.get("merchant_id", "")
        if sup_store.is_suppressed(sup_key):
            continue
        if sup_store.is_hostile(merchant_id):
            continue
        from composer import _is_expired
        if _is_expired(trg.get("expires_at", "9999-12-31"), now_iso):
            continue
        viable.append(trg_id)

    if not viable:
        return {"actions": []}

    analyst_tasks = [
        _analyst_for_trigger(trg_id, composer, ctx_store)
        for trg_id in viable
    ]
    analyses = await asyncio.gather(*analyst_tasks, return_exceptions=True)

    ranked = []
    for trg_id, analysis in zip(viable, analyses):
        if isinstance(analysis, Exception):
            continue
        trg = ctx_store.get("trigger", trg_id)
        urgency = trg.get("urgency", 1) if trg else 1
        score = analysis.opportunity_score * urgency
        ranked.append((score, trg_id, analysis))
    ranked.sort(reverse=True, key=lambda x: x[0])

    actions: list[TickAction] = []
    sent_merchants: set[str] = set()

    for _score, trg_id, analysis in ranked:
        trg = ctx_store.get("trigger", trg_id)
        if not trg:
            continue
        merchant_id = trg.get("merchant_id", "")
        if merchant_id in sent_merchants:
            continue
        if analysis.urgency_assessment == "SKIP":
            continue

        action = await composer.compose_proactive(
            trg_id, now_iso, analyst_override=analysis
        )
        if action:
            actions.append(action)
            sent_merchants.add(merchant_id)

        if len(actions) >= 2:
            break

    return {"actions": [a.model_dump() for a in actions]}


async def _analyst_for_trigger(trg_id: str, comp: ThreePassComposer, ctx: ContextStore):
    """Helper to run analyst pass standalone for ranking."""
    trigger = ctx.get("trigger", trg_id)
    if not trigger:
        from models import AnalystOutput
        return AnalystOutput(
            merchant_vs_peers="",
            cohort_math="",
            urgency_assessment="SKIP",
            best_compulsion_lever="specificity",
            contrarian_flag=None,
            tone_override=None,
            opportunity_score=0.0,
        )
    merchant_id = trigger.get("merchant_id")
    merchant = ctx.get("merchant", merchant_id) if merchant_id else None
    category_slug = merchant.get("category_slug") if merchant else None
    category = ctx.get("category", category_slug) if category_slug else None
    customer_id = trigger.get("customer_id")
    customer = ctx.get("customer", customer_id) if customer_id else None

    if not merchant:
        from models import AnalystOutput
        return AnalystOutput(
            merchant_vs_peers="",
            cohort_math="",
            urgency_assessment="SKIP",
            best_compulsion_lever="specificity",
            contrarian_flag=None,
            tone_override=None,
            opportunity_score=0.0,
        )

    return await comp._run_analyst(category, merchant, trigger, customer)


@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    """
    Receive a merchant/customer reply and respond.
    Runs classifier first, then routes through state machine.
    """
    intent_result = await classifier.classify(body.message, body.turn_number)
    intent = intent_result.intent

    if intent == "HOSTILE":
        if body.merchant_id:
            sup_store.mark_hostile(body.merchant_id, days=30)

    conv = conv_store.get(body.conversation_id)
    merchant_id = body.merchant_id or (conv.merchant_id if conv else None)
    customer_id = body.customer_id or (conv.customer_id if conv else None)

    trigger_id = conv.trigger_id if conv else ""

    if not conv and merchant_id:
        trigger_id = _find_latest_trigger_for_merchant(merchant_id)
        conv = conv_store.get_or_create(
            body.conversation_id,
            merchant_id,
            customer_id,
            trigger_id,
        )

    result = await composer.compose_reply(
        conversation_id=body.conversation_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        incoming_message=body.message,
        turn_number=body.turn_number,
        intent=intent,
    )

    return result


def _find_latest_trigger_for_merchant(merchant_id: str) -> str:
    """Find the most recently stored trigger for a merchant."""
    all_triggers = ctx_store.get_all_triggers()
    for t in reversed(all_triggers):
        if t.get("merchant_id") == merchant_id:
            return t.get("id", "unknown")
    return "unknown"


@app.post("/v1/teardown")
async def teardown():
    """Called by judge at end of test. Wipe all state."""
    ctx_store.clear()
    conv_store.clear()
    sup_store.clear()
    return {"wiped": True}
