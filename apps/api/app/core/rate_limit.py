from __future__ import annotations

import threading
import time

from cachetools import TTLCache


class _TokenBucket:
    __slots__ = ("tokens", "last_refill", "max_tokens", "refill_rate")

    def __init__(self, max_tokens: float, refill_rate: float):
        self.tokens = max_tokens
        self.last_refill = time.monotonic()
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


_buckets: TTLCache[str, _TokenBucket] = TTLCache(maxsize=8192, ttl=120)
_lock = threading.Lock()

GET_LIMIT = 200
WRITE_LIMIT = 60


def check_rate_limit(user_id: str, clinic_id: str, is_write: bool) -> int | None:
    """Return None if allowed, or seconds until retry if rate-limited."""
    limit = WRITE_LIMIT if is_write else GET_LIMIT
    key = f"{user_id}:{clinic_id}:{'w' if is_write else 'r'}"
    with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _TokenBucket(max_tokens=float(limit), refill_rate=limit / 60.0)
            _buckets[key] = bucket
        if bucket.consume():
            return None
        wait = (1.0 - bucket.tokens) / bucket.refill_rate
        return max(1, int(wait) + 1)
