"""Format issue records for HTML/Markdown reports."""

from __future__ import annotations

from typing import Any

from src.assertions import expected_labels_for_assertions
from src.error_messages import sanitize_report_text
from src.inspection_nav import case_navigation, explain_issue_command
from src.models import ReplyInfo, TestCaseDef, TestResult

CHANNEL_LABELS = {
    "dm": "私聊（Inspector 向被测 Bot 发消息）",
    "normal_group": "普通群聊",
    "topic_group": "话题群",
}


def split_detail_field(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]
    for sep in (" → ", " | ", "; "):
        if sep in text:
            return [part.strip() for part in text.split(sep) if part.strip()]
    return [text.strip()]


def build_repro_lines(
    result: TestResult,
    *,
    bot_name: str,
    case: TestCaseDef | None = None,
) -> list[str]:
    if result.repro_steps:
        lines = split_detail_field(result.repro_steps)
        if lines:
            return lines

    if not case:
        return [f"执行用例「{result.case_name}」（{result.case_id}）"]

    channel = CHANNEL_LABELS.get(case.channel, case.channel)
    lines = [
        f"目标 Bot：{bot_name}",
        f"渠道：{channel}",
        f"用例：{case.name}（{case.id}）",
    ]
    if case.probe and not case.prompt:
        lines.append(f"执行探针检查：{case.probe}")
        return lines

    action = f"Inspector @「{bot_name}」并发送消息" if case.at_bot else "Inspector 发送消息"
    if case.in_thread:
        action += "（在话题内）"
    lines.append(action)

    prompt = case.prompt
    if prompt:
        lines.append(f"消息内容：{prompt}")
    if case.attach_file:
        lines.append(f"附带文件：{case.attach_file}")
    if case.attach_doc:
        lines.append(f"附带文档：{case.attach_doc}")
    return lines


def build_expected_lines(
    result: TestResult,
    *,
    case: TestCaseDef | None = None,
) -> list[str]:
    lines = split_detail_field(result.expected)
    if lines:
        return lines
    if case and case.assertions:
        return expected_labels_for_assertions(
            case.assertions, context=result.probe_data
        )
    return ["按用例断言规则，Bot 应正常响应且满足各项检查"]


def _reply_preview(reply: ReplyInfo, index: int) -> str:
    preview = (reply.content or "").strip().replace("\n", " ")
    if len(preview) > 220:
        preview = preview[:220] + "…"
    label = f"Bot 回复 #{index + 1}"
    if reply.msg_type and reply.msg_type != "text":
        label += f"（{reply.msg_type}）"
    if reply.latency_sec:
        label += f"，耗时 {reply.latency_sec:.1f}s"
    return f"{label}：{preview or '（空内容）'}"


def build_actual_lines(result: TestResult) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    def add(line: str) -> None:
        cleaned = line.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            lines.append(cleaned)

    message = sanitize_report_text((result.message or "").strip())
    if message:
        if ";" in message:
            for part in message.split(";"):
                add(sanitize_report_text(part))
        else:
            add(message)

    for part in split_detail_field(result.actual):
        add(sanitize_report_text(part))

    for index, reply in enumerate(result.replies[:3]):
        add(_reply_preview(reply, index))

    return lines or ["（未记录实际结果）"]


def format_issue(
    result: TestResult,
    *,
    bot_name: str,
    index: int,
    case: TestCaseDef | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    repro_lines = build_repro_lines(result, bot_name=bot_name, case=case)
    expected_lines = build_expected_lines(result, case=case)
    actual_lines = build_actual_lines(result)
    desc = result.case_name
    display_message = sanitize_report_text(result.message or "")
    if display_message and display_message != result.case_name:
        desc = f"{result.case_name} — {display_message}"

    issue_id = f"ISS-{index:03d}"
    nav = case_navigation(result, run_id=run_id, issue_id=issue_id)

    return {
        "id": issue_id,
        "case_id": result.case_id,
        "desc": desc,
        "severity": result.severity,
        "repro_lines": repro_lines,
        "expected_lines": expected_lines,
        "actual_lines": actual_lines,
        "repro": "<br>".join(repro_lines),
        "expected": "<br>".join(f"• {line}" for line in expected_lines),
        "actual": "<br>".join(f"• {line}" for line in actual_lines),
        "search_key": nav["search_key"],
        "explain_command": nav["explain_command"],
        "explain_issue_command": nav.get("explain_issue_command", explain_issue_command(issue_id)),
        "run_id": run_id,
    }
