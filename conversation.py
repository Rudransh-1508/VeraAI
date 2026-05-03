from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ConvState(Enum):
    OPENING = "opening"
    ENGAGED = "engaged"
    AUTO_REPLY_SUSPECTED = "auto_reply_suspected"
    AUTO_REPLY_CONFIRMED = "auto_reply_confirmed"
    INTENT_EXPRESSED = "intent_expressed"
    ACTION_MODE = "action_mode"
    COOLING_OFF = "cooling_off"
    HOSTILE = "hostile"
    CLOSED = "closed"


@dataclass
class Conversation:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str]
    trigger_id: str
    state: ConvState = ConvState.OPENING
    turns: list[dict] = field(default_factory=list)
    sent_bodies: list[str] = field(default_factory=list)
    last_auto_reply_text: Optional[str] = None
    auto_reply_count: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_turn(self, role: str, message: str):
        self.turns.append(
            {
                "role": role,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def add_sent_body(self, body: str):
        self.sent_bodies.append(body)

    def is_body_repeat(self, body: str) -> bool:
        """Check if we've sent this exact body before in this conversation."""
        return body in self.sent_bodies

    def history_text(self, max_turns: int = 6) -> str:
        """Last N turns formatted as text for LLM context."""
        recent = self.turns[-max_turns:]
        lines = []
        for t in recent:
            prefix = "MERCHANT" if t["role"] == "merchant" else "VERA"
            lines.append(f"[{prefix}]: {t['message']}")
        return "\n".join(lines)


class ConversationStore:
    def __init__(self):
        self._convs: dict[str, Conversation] = {}

    def get_or_create(
        self,
        conversation_id: str,
        merchant_id: str,
        customer_id: Optional[str],
        trigger_id: str,
    ) -> Conversation:
        if conversation_id not in self._convs:
            self._convs[conversation_id] = Conversation(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                trigger_id=trigger_id,
            )
        return self._convs[conversation_id]

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._convs.get(conversation_id)

    def transition(self, conversation_id: str, new_state: ConvState):
        conv = self._convs.get(conversation_id)
        if conv:
            conv.state = new_state

    def clear(self):
        self._convs.clear()
