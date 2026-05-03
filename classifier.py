import json
import re

from llm_client import LLMClient
from models import ClassifierOutput
from prompts import CLASSIFIER_PROMPT


class ReplyClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def classify(self, message: str, turn_number: int) -> ClassifierOutput:
        """
        Fast single-call classification of an incoming message.
        Uses a small max_tokens budget (150) for speed.
        """
        fast = self._fast_path(message)
        if fast:
            return fast

        prompt = CLASSIFIER_PROMPT.format(
            message=message,
            turn_number=turn_number,
        )
        raw = await self.llm.complete(prompt, max_tokens=150)
        parsed = _parse_json(raw)

        return ClassifierOutput(
            intent=parsed.get("intent", "SOFT_ENGAGE"),
            confidence=float(parsed.get("confidence", 0.7)),
            notes=parsed.get("notes", ""),
        )

    def _fast_path(self, message: str) -> ClassifierOutput | None:
        """
        Rule-based shortcuts to avoid LLM call for obvious cases.
        Saves ~0.5s per reply turn.
        """
        msg = message.strip().lower()

        auto_reply_signals = [
            "thank you for contacting",
            "we will get back to you",
            "our team will respond",
            "please leave a message",
            "for inquiries, please",
        ]
        if any(sig in msg for sig in auto_reply_signals):
            return ClassifierOutput(
                intent="AUTO_REPLY",
                confidence=0.95,
                notes="Matched auto-reply pattern keyword",
            )

        yes_signals = [
            "yes",
            "haan",
            "han",
            "sure",
            "go ahead",
            "let's do it",
            "karo",
            "kar do",
            "bilkul",
            "definitely",
            "ok do it",
            "proceed",
            "confirm",
            "send it",
            "1",
            "done",
            "chalega",
        ]
        if msg in yes_signals or any(msg.startswith(s + " ") for s in yes_signals):
            return ClassifierOutput(
                intent="EXPLICIT_YES",
                confidence=0.92,
                notes="Matched explicit YES keyword",
            )

        no_signals = [
            "stop",
            "nahi",
            "no",
            "not interested",
            "band karo",
            "mat bhejo",
            "unsubscribe",
            "leave me alone",
        ]
        hostile_signals = [
            "why are you bothering",
            "useless",
            "waste of time",
            "stop messaging",
            "annoying",
            "bakwaas",
        ]
        if any(sig in msg for sig in no_signals):
            return ClassifierOutput(
                intent="EXPLICIT_NO",
                confidence=0.90,
                notes="Matched explicit NO keyword",
            )
        if any(sig in msg for sig in hostile_signals):
            return ClassifierOutput(
                intent="HOSTILE",
                confidence=0.88,
                notes="Matched hostile keyword",
            )

        return None


def _parse_json(raw: str) -> dict:
    try:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}
