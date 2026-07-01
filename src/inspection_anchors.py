"""Searchable anchors for multi-run inspection threads in Feishu chats."""

from __future__ import annotations

import secrets
from datetime import datetime


def generate_run_id(started_at: datetime | None = None) -> str:
    """Unique id per inspection run, e.g. R250625-173245-a3."""
    dt = started_at or datetime.now()
    suffix = secrets.token_hex(1)
    return f"R{dt.strftime('%y%m%d-%H%M%S')}-{suffix}"


def case_anchor_prefix(
    run_id: str,
    case_id: str,
    case_index: int = 0,
    case_total: int = 0,
) -> str:
    """Human-readable anchor shown on inspector progress cards (not sent to @Bot)."""
    if case_index and case_total:
        return f"【巡检·{run_id}·{case_id}·{case_index}/{case_total}】"
    return f"【巡检·{run_id}·{case_id}】"


def case_search_key(run_id: str, case_id: str) -> str:
    """Copy-paste hint for Ctrl+F in Feishu (unique per run + case)."""
    return f"{run_id}·{case_id}"


def run_search_key(run_id: str) -> str:
    """Search all messages from one inspection run."""
    return run_id


def format_case_progress_text(
    run_id: str,
    case_id: str,
    case_name: str,
    case_index: int,
    case_total: int,
    *,
    channel_hint: str = "",
) -> str:
    """Plain-text progress ping — Feishu chat search indexes text, not interactive cards."""
    line = (
        f"【巡检 {run_id} {case_index}/{case_total}】"
        f"{case_id} · {case_name}"
    )
    if channel_hint:
        return f"{line}\n{channel_hint}"
    return line


def format_case_skipped_text(
    run_id: str,
    case_id: str,
    case_name: str,
    case_index: int,
    case_total: int,
    reason: str,
) -> str:
    return (
        f"【巡检 {run_id} {case_index}/{case_total}】"
        f"{case_id} · {case_name} — 未采到回复：{reason}"
    )


def format_run_summary_text(run_id: str, bot_name: str, *, case_ids: list[str] | None = None) -> str:
    """Searchable summary anchor after inspection completes."""
    lines = [f"【巡检结束】{run_id} · {bot_name}"]
    for case_id in case_ids or []:
        lines.append(case_search_key(run_id, case_id))
    return "\n".join(lines)


def attach_case_anchor(
    prompt: str,
    run_id: str,
    case_id: str,
    case_index: int = 0,
    case_total: int = 0,
) -> str:
    """Append searchable anchor after probe text so @Bot payload stays clean at the start."""
    anchor = case_anchor_prefix(run_id, case_id, case_index, case_total)
    text = (prompt or "").strip()
    if not text:
        return anchor
    return f"{text}\n{anchor}"


def prepend_case_anchor(
    prompt: str,
    run_id: str,
    case_id: str,
    case_index: int = 0,
    case_total: int = 0,
) -> str:
    """Backward-compatible alias; anchors are appended, not prepended."""
    return attach_case_anchor(prompt, run_id, case_id, case_index, case_total)
