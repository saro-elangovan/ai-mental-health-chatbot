"""In-memory conversation sessions.

Design choices (good interview talking points):
- Memory lives in RAM only. Nothing personal is written to disk or a database, and
  everything disappears on restart. That is deliberate for a mental-health context.
- Sessions expire after a period of inactivity and the total number is capped.
- Only the most recent messages (bounded by count AND characters) are sent to the model,
  which keeps cost and latency low.
- Methods are synchronous and never `await`, so they run atomically inside FastAPI's
  event loop and need no locks.
"""

import time
import uuid
from dataclasses import dataclass, field

from .exceptions import AppError
from .logger import get_logger

log = get_logger("memory")


@dataclass
class Session:
    id: str
    created_at: float
    last_active: float
    messages: list[dict[str, str]] = field(default_factory=list)


class MemoryService:
    def __init__(self, max_messages: int, max_chars: int, ttl_seconds: int, max_sessions: int) -> None:
        self.max_messages = max(2, max_messages - (max_messages % 2))  # keep whole exchanges
        self.max_chars = max_chars
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}

    # ---- lifecycle -------------------------------------------------
    def create_session(self) -> str:
        self._purge_expired()
        if len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.last_active)
            del self._sessions[oldest.id]
            log.info("Session limit reached; evicted least recently used session")
        now = time.time()
        session = Session(id=str(uuid.uuid4()), created_at=now, last_active=now)
        self._sessions[session.id] = session
        return session.id

    def get_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None or self._is_expired(session):
            self._sessions.pop(session_id, None)
            raise AppError(
                "SESSION_NOT_FOUND",
                "This conversation has expired or does not exist. Please start a new chat.",
                404,
            )
        session.last_active = time.time()
        return session

    def clear_session(self, session_id: str) -> None:
        self.get_session(session_id)  # raises if invalid
        del self._sessions[session_id]

    @property
    def active_count(self) -> int:
        self._purge_expired()
        return len(self._sessions)

    # ---- history ---------------------------------------------------
    def add_exchange(self, session_id: str, user_text: str, assistant_text: str) -> None:
        session = self.get_session(session_id)
        session.messages.append({"role": "user", "content": user_text})
        session.messages.append({"role": "assistant", "content": assistant_text})
        if len(session.messages) > self.max_messages:
            del session.messages[: -self.max_messages]

    def get_context(self, session_id: str) -> list[dict[str, str]]:
        """Return the newest messages that fit inside the character budget."""
        session = self.get_session(session_id)
        picked: list[dict[str, str]] = []
        total = 0
        for msg in reversed(session.messages):
            total += len(msg["content"])
            if total > self.max_chars:
                break
            picked.append(msg)
        picked.reverse()
        while picked and picked[0]["role"] != "user":  # never start on an assistant turn
            picked.pop(0)
        return picked

    # ---- helpers ---------------------------------------------------
    def _is_expired(self, session: Session) -> bool:
        return time.time() - session.last_active > self.ttl_seconds

    def _purge_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if self._is_expired(s)]
        for sid in expired:
            del self._sessions[sid]
