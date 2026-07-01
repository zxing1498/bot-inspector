"""Tests for difficulty-based timeout tiers."""

from src.models import TestCaseDef
from src.timeout_tiers import apply_timeout_tier
from src.wait_policy import resolve_completion_wait


def test_apply_simple_tier():
    case = TestCaseDef(
        id="p0_dm",
        name="dm",
        section="p0",
        capabilities=["messaging"],
        difficulty="simple",
        assertions=[
            {"type": "reply_within"},
            {"type": "content_not_empty"},
        ],
    )
    env = {
        "timeout_tiers": {
            "simple": {
                "reply_within_sec": 90,
                "first_ack_sec": 15,
                "completion_buffer_sec": 30,
            }
        }
    }
    applied = apply_timeout_tier(case, env)
    reply_rule = next(a for a in applied.assertions if a["type"] == "reply_within")
    assert reply_rule["timeout_sec"] == 90
    latency = next(a for a in applied.assertions if a["type"] == "latency_warning")
    assert latency["threshold_sec"] == 15


def test_apply_heavy_tier_no_extra_latency_with_first_ack():
    case = TestCaseDef(
        id="p0_slow_ack",
        name="slow",
        section="p0",
        capabilities=["messaging"],
        difficulty="heavy",
        assertions=[{"type": "first_ack_within"}],
    )
    env = {
        "timeout_tiers": {
            "heavy": {
                "reply_within_sec": 300,
                "first_ack_sec": 15,
                "completion_buffer_sec": 60,
            }
        }
    }
    applied = apply_timeout_tier(case, env)
    types = [a["type"] for a in applied.assertions]
    assert "latency_warning" not in types
    first_ack = next(a for a in applied.assertions if a["type"] == "first_ack_within")
    assert first_ack["threshold_sec"] == 15


def test_apply_heavy_tier_wait():
    case = TestCaseDef(
        id="p0_doc",
        name="doc",
        section="p0",
        capabilities=["doc_access"],
        difficulty="heavy",
        assertions=[{"type": "reply_within"}],
    )
    env = {
        "timeout_tiers": {
            "heavy": {
                "reply_within_sec": 300,
                "first_ack_sec": 15,
                "completion_buffer_sec": 60,
            }
        },
        "defaults": {"completion_wait_sec": 360},
    }
    applied = apply_timeout_tier(case, env)
    reply_rule = next(a for a in applied.assertions if a["type"] == "reply_within")
    assert reply_rule["timeout_sec"] == 300
    wait = resolve_completion_wait(applied, env["defaults"], env)
    assert wait == 360
