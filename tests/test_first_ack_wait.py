"""Tests for first_ack poll wait."""

from src.models import TestCaseDef
from src.wait_policy import case_uses_first_ack_only, resolve_first_ack_poll_wait


def test_first_ack_only_case():
    case = TestCaseDef(
        id="p0_slow_ack",
        name="slow",
        section="p0",
        capabilities=["messaging"],
        difficulty="medium",
        assertions=[
            {"type": "first_ack_within", "threshold_sec": 15},
            {"type": "not_system_error"},
        ],
    )
    assert case_uses_first_ack_only(case)
    assert resolve_first_ack_poll_wait(case, {"timeout_tiers": {"medium": {"reply_within_sec": 120}}}) == 120


def test_mixed_reply_within_not_first_ack_only():
    case = TestCaseDef(
        id="p0_group",
        name="g",
        section="p0",
        capabilities=["messaging"],
        assertions=[
            {"type": "reply_within"},
            {"type": "first_ack_within"},
        ],
    )
    assert not case_uses_first_ack_only(case)
