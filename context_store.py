from datetime import datetime, timezone
from typing import Any, Optional

from models import ContextPush, ContextAck


class ContextStore:
    """
    In-memory store for all 4 context types.
    Key: (scope, context_id) -> {version, payload, stored_at}
    """

    def __init__(self):
        self._store: dict[tuple[str, str], dict] = {}

    def push(self, push: ContextPush) -> ContextAck:
        key = (push.scope, push.context_id)
        existing = self._store.get(key)

    # Idempotency: same or older version -> reject
        if existing and existing["version"] >= push.version:
            return ContextAck(
                accepted=False,
                reason="stale_version",
                current_version=existing["version"],
            )

        stored_at = datetime.now(timezone.utc).isoformat()
        self._store[key] = {
            "version": push.version,
            "payload": push.payload,
            "stored_at": stored_at,
        }
        return ContextAck(
            accepted=True,
            ack_id=f"ack_{push.context_id}_v{push.version}",
            stored_at=stored_at,
        )

    def get(self, scope: str, context_id: str) -> Optional[dict]:
        entry = self._store.get((scope, context_id))
        return entry["payload"] if entry else None

    def get_version(self, scope: str, context_id: str) -> Optional[int]:
        entry = self._store.get((scope, context_id))
        return entry["version"] if entry else None

    def count_by_scope(self) -> dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._store:
            if scope in counts:
                counts[scope] += 1
        return counts

    def get_all_triggers(self) -> list[dict]:
        """Return all stored trigger payloads."""
        return [
            v["payload"]
            for (scope, _), v in self._store.items()
            if scope == "trigger"
        ]

    def clear(self):
        self._store.clear()
