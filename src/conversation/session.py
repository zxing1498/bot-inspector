"""Per-user session context for follow-up dialogue."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

SESSION_TTL_SEC = 3600


@dataclass
class CaseSnapshot:
    case_id: str
    case_name: str
    status: str
    message: str
    expected: str
    actual: str
    issue_id: str = ""


@dataclass
class InspectionSnapshot:
    bot_name: str
    suite: str
    started_at: str
    md_path: str
    html_path: str
    pass_count: int
    fail_count: int
    failed_cases: list[CaseSnapshot] = field(default_factory=list)
    all_cases: list[CaseSnapshot] = field(default_factory=list)


@dataclass
class ChatSession:
    chat_id: str
    operator_open_id: str
    updated_at: float = field(default_factory=time.time)
    last_inspection: InspectionSnapshot | None = None
    recent_messages: list[tuple[str, str]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.chat_id}:{self.operator_open_id}"


class SessionStore:
    def __init__(self, *, ttl_sec: float = SESSION_TTL_SEC) -> None:
        self._ttl_sec = ttl_sec
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def get(self, chat_id: str, operator_open_id: str) -> ChatSession:
        key = f"{chat_id}:{operator_open_id}"
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            session = self._sessions.get(key)
            if session is None:
                session = ChatSession(chat_id=chat_id, operator_open_id=operator_open_id)
                self._sessions[key] = session
            session.updated_at = now
            return session

    def record_inspection(
        self,
        chat_id: str,
        operator_open_id: str,
        snapshot: InspectionSnapshot,
    ) -> None:
        session = self.get(chat_id, operator_open_id)
        session.last_inspection = snapshot

    def append_turn(
        self,
        chat_id: str,
        operator_open_id: str,
        role: str,
        content: str,
        *,
        max_turns: int = 6,
    ) -> None:
        session = self.get(chat_id, operator_open_id)
        session.recent_messages.append((role, content))
        if len(session.recent_messages) > max_turns:
            session.recent_messages = session.recent_messages[-max_turns:]

    def _purge_locked(self, now: float) -> None:
        stale = [
            key
            for key, session in self._sessions.items()
            if now - session.updated_at > self._ttl_sec
        ]
        for key in stale:
            del self._sessions[key]
