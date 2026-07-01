"""Tests for per-case completion wait policy."""

from src.models import TestCaseDef
from src.wait_policy import max_reply_timeout_sec, resolve_completion_wait


def test_resolve_completion_wait_uses_assertion_timeout():
    case = TestCaseDef(
        id="p0_x",
        name="x",
        section="p0",
        capabilities=["messaging"],
        assertions=[{"type": "reply_within", "timeout_sec": 30}],
    )
    wait = resolve_completion_wait(
        case,
        {
            "reply_timeout_sec": 30,
            "completion_buffer_sec": 45,
            "completion_wait_sec": 360,
        },
        {},
    )
    assert wait == 75


def test_resolve_completion_wait_caps_at_global_max():
    case = TestCaseDef(
        id="p0_doc",
        name="doc",
        section="p0",
        capabilities=["doc_access"],
        assertions=[{"type": "reply_within", "timeout_sec": 60}],
    )
    assert max_reply_timeout_sec(case) == 60
    wait = resolve_completion_wait(
        case,
        {
            "completion_buffer_sec": 45,
            "completion_wait_sec": 90,
        },
        {},
    )
    assert wait == 90
