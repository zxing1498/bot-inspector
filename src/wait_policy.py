"""Compute per-case wait timeouts for bot replies."""

from __future__ import annotations

from typing import Any

from src.models import TestCaseDef


def max_reply_timeout_sec(case: TestCaseDef, default: int = 30) -> int:
    timeout = default
    for rule in case.assertions:
        if rule.get("type") == "reply_within":
            timeout = max(timeout, int(rule.get("timeout_sec", default)))
    return timeout


def resolve_completion_wait(
    case: TestCaseDef, defaults: dict[str, Any], env_config: dict[str, Any] | None = None
) -> float:
    """Wait long enough for slow bots, scaled by task difficulty."""
    from src.timeout_tiers import tier_completion_buffer

    reply_timeout = max_reply_timeout_sec(case, int(defaults.get("reply_timeout_sec", 30)))
    buffer_sec = int(defaults.get("completion_buffer_sec", 45))
    if env_config and case.difficulty:
        tier_buffer = tier_completion_buffer(case, env_config)
        if tier_buffer is not None:
            buffer_sec = tier_buffer
    cap_sec = float(defaults.get("completion_wait_sec", 360))
    return min(reply_timeout + buffer_sec, cap_sec)


def case_uses_first_ack_only(case: TestCaseDef) -> bool:
    types = {rule.get("type") for rule in case.assertions}
    return "first_ack_within" in types and "reply_within" not in types


def resolve_first_ack_poll_wait(
    case: TestCaseDef, env_config: dict[str, Any] | None = None
) -> float:
    """Max wait to capture the first bot reply for first_ack_within cases."""
    from src.timeout_tiers import get_tier_config

    tier = get_tier_config(env_config or {}, case.difficulty or "medium")
    return float(tier.get("reply_within_sec", 120))
