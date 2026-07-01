"""Tests for cross-process inspection lock."""

import os

from src.inspection_lock import (
    inspection_lock_holder,
    release_inspection_lock,
    try_acquire_inspection_lock,
)


def test_acquire_and_release_lock():
    bot = "test-lock-bot"
    release_inspection_lock(bot)
    assert try_acquire_inspection_lock(bot, owner="unit-test")
    assert inspection_lock_holder(bot) == "unit-test"
    release_inspection_lock(bot)
    assert inspection_lock_holder(bot) is None


def test_second_acquire_blocked_while_held():
    bot = "test-lock-bot-2"
    release_inspection_lock(bot)
    assert try_acquire_inspection_lock(bot)
    assert not try_acquire_inspection_lock(bot)
    release_inspection_lock(bot)


def test_stale_lock_reclaimed_when_pid_dead():
    bot = "test-lock-bot-3"
    release_inspection_lock(bot)
    from src.inspection_lock import LOCK_DIR, _lock_path

    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    _lock_path(bot).write_text("99999999\ndead\n0\n", encoding="utf-8")
    assert try_acquire_inspection_lock(bot)
    release_inspection_lock(bot)
