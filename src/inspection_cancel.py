"""Cooperative cancellation for in-flight bot inspections."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled: set[str] = set()
_active: set[str] = set()


def mark_active(bot_name: str) -> None:
    with _lock:
        _active.add(bot_name)
        _cancelled.discard(bot_name)


def mark_inactive(bot_name: str) -> None:
    with _lock:
        _active.discard(bot_name)
        _cancelled.discard(bot_name)


def request_cancel(bot_name: str) -> bool:
    """Mark bot inspection for cancellation. Returns True if it was active."""
    with _lock:
        _cancelled.add(bot_name)
        return bot_name in _active


def is_cancelled(bot_name: str) -> bool:
    with _lock:
        return bot_name in _cancelled


def is_active(bot_name: str) -> bool:
    with _lock:
        return bot_name in _active


def active_bots() -> set[str]:
    with _lock:
        return set(_active)
