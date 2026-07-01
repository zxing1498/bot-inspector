"""Resolve timeout tiers by task difficulty."""

from __future__ import annotations

from typing import Any

from src.models import TestCaseDef

TIER_LABELS = {
    "simple": "简单（短问答）",
    "medium": "中等（权限/拒答）",
    "heavy": "复杂（文档/文件/长任务）",
}


def get_tier_config(env_config: dict[str, Any], difficulty: str) -> dict[str, Any]:
    tiers = env_config.get("timeout_tiers", {})
    if difficulty in tiers:
        return dict(tiers[difficulty])
    return dict(tiers.get("simple", {}))


def apply_timeout_tier(case: TestCaseDef, env_config: dict[str, Any]) -> TestCaseDef:
    """Fill reply_within / latency_warning thresholds from difficulty tier."""
    if not case.difficulty:
        return case

    tier = get_tier_config(env_config, case.difficulty)
    if not tier:
        return case

    reply_sec = int(tier.get("reply_within_sec", 90))
    first_ack = int(tier.get("first_ack_sec", 15))

    new_assertions: list[dict[str, Any]] = []
    has_latency = False
    has_first_ack = False
    for rule in case.assertions:
        item = dict(rule)
        atype = item.get("type")
        if atype == "reply_within":
            item.setdefault("timeout_sec", reply_sec)
        elif atype in ("latency_warning", "first_ack_within"):
            item.setdefault("threshold_sec", first_ack)
            if atype == "latency_warning":
                has_latency = True
            else:
                has_first_ack = True
        new_assertions.append(item)

    if case.difficulty in ("simple", "heavy") and not has_latency and not has_first_ack:
        new_assertions.append(
            {"type": "latency_warning", "threshold_sec": first_ack},
        )

    return TestCaseDef(
        id=case.id,
        name=case.name,
        section=case.section,
        capabilities=list(case.capabilities),
        prompt=case.prompt,
        channel=case.channel,
        at_bot=case.at_bot,
        in_thread=case.in_thread,
        attach_doc=case.attach_doc,
        attach_file=case.attach_file,
        account=case.account,
        burst_count=case.burst_count,
        extra_text=case.extra_text,
        repeat_extra=case.repeat_extra,
        probe=case.probe,
        report_section=case.report_section,
        difficulty=case.difficulty,
        assertions=new_assertions,
    )


def tier_completion_buffer(case: TestCaseDef, env_config: dict[str, Any]) -> int | None:
    if not case.difficulty:
        return None
    tier = get_tier_config(env_config, case.difficulty)
    value = tier.get("completion_buffer_sec")
    return int(value) if value is not None else None
