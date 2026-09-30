"""Tiny in-memory sliding-window rate limiter (per client IP).

Protects your OpenAI bill if the demo is ever exposed publicly. Behind a reverse proxy
all users may share one IP; use a proper gateway or Redis-based limiter in production.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from .exceptions import AppError


class RateLimiter:
    def __init__(self, limit_per_minute: int, window_seconds: int = 60) -> None:
        self.limit = limit_per_minute
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise AppError(
                "RATE_LIMITED",
                "You're sending messages too quickly. Please wait a moment and try again.",
                429,
            )
        hits.append(now)
        if len(self._hits) > 2000:  # prevent unbounded growth
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                del self._hits[k]


def rate_limit(request: Request) -> None:
    """FastAPI dependency."""
    client = request.client.host if request.client else "unknown"
    request.app.state.rate_limiter.check(client)
