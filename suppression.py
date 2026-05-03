from datetime import datetime, timezone, timedelta


class SuppressionStore:
    """
    Tracks suppression keys to prevent duplicate sends.
    Also tracks per-merchant hostile flag for 30-day cooldown.
    """

    def __init__(self):
        # suppression_key -> suppressed_at ISO string
        self._keys: dict[str, str] = {}
        # merchant_id -> hostile_until ISO string
        self._hostile: dict[str, str] = {}

    def suppress(self, key: str, ttl_hours: int = 168):
        """Mark a suppression key as used. Default TTL: 1 week."""
        self._keys[key] = datetime.now(timezone.utc).isoformat()

    def is_suppressed(self, key: str) -> bool:
        return key in self._keys

    def mark_hostile(self, merchant_id: str, days: int = 30):
        until = datetime.now(timezone.utc) + timedelta(days=days)
        self._hostile[merchant_id] = until.isoformat()

    def is_hostile(self, merchant_id: str) -> bool:
        until_str = self._hostile.get(merchant_id)
        if not until_str:
            return False
        try:
            until = datetime.fromisoformat(until_str)
            return datetime.now(timezone.utc) < until
        except Exception:
            return False

    def clear(self):
        self._keys.clear()
        self._hostile.clear()
