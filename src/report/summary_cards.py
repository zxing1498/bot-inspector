"""Feishu interactive cards for inspection progress and summary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.inspection_anchors import case_search_key, run_search_key
from src.inspection_nav import case_navigation, inspector_at_name
from src.report.scoring import compute_inspection_score, format_score_line
from src.models import BotRunReport, TestResult, TestStatus


def _plain(text: str) -> dict[str, Any]:
    return {"tag": "plain_text", "content": text}


def _status_emoji(status: TestStatus) -> str:
    if status == TestStatus.PASS:
        return "✅"
    if status == TestStatus.FAIL:
        return "❌"
    if status == TestStatus.PENDING_FIX:
        return "⚠️"
    if status == TestStatus.MANUAL:
        return "🔍"
    if status == TestStatus.PENDING_PERM:
        return "🔒"
    return "➖"


def _header_template(report: BotRunReport) -> tuple[str, str]:
    fails = [r for r in report.results if r.status == TestStatus.FAIL]
    warns = [r for r in report.results if r.status == TestStatus.PENDING_FIX]
    if fails:
        return "巡检未通过", "red"
    if warns:
        return "巡检完成（有待整改）", "yellow"
    if report.cancelled:
        return "巡检已暂停", "grey"
    return "巡检通过", "green"


def _suite_stat_line(report: BotRunReport) -> str:
    suite_hint = "Full" if report.suite in ("full", "api") else report.suite.upper()
    if report.suite in ("full", "api"):
        stat = (
            f"全量 **{report.run_pass_count()}/{report.run_total()}**"
            f" · P0 **{report.p0_pass_count()}/{report.p0_total()}**"
        )
    else:
        stat = f"P0 **{report.p0_pass_count()}/{report.p0_total()}**"
    return f"**{report.bot_name}**（{suite_hint}） {stat}"


def _attention_results(report: BotRunReport) -> list[TestResult]:
    return [
        r
        for r in report.results
        if r.status
        in (
            TestStatus.FAIL,
            TestStatus.PENDING_FIX,
            TestStatus.MANUAL,
            TestStatus.PENDING_PERM,
        )
    ]


def _issue_id_by_case(report: BotRunReport) -> dict[str, str]:
    mapping: dict[str, str] = {}
    idx = 1
    for result in report.results:
        if result.status in (TestStatus.FAIL, TestStatus.PENDING_FIX):
            mapping[result.case_id] = f"ISS-{idx:03d}"
            idx += 1
    return mapping


def _format_attention_item(report: BotRunReport, result: TestResult) -> str:
    run_id = report.run_id or (result.probe_data or {}).get("run_id", "")
    issue_id = _issue_id_by_case(report).get(result.case_id, "")
    nav = case_navigation(result, run_id=run_id, issue_id=issue_id)
    label = _status_emoji(result.status)
    reason = (result.message or result.status.value).strip()
    lines = [
        f"{label} **{result.case_name}**",
        f"`{result.case_id}` · {reason}",
        f"**复制搜索**（群内 Ctrl+F）\n`{nav['search_key']}`",
        f"**追问检查员**\n`{nav['explain_command']}`",
    ]
    if issue_id:
        lines.append(f"按问题编号\n`{nav.get('explain_issue_command', '')}`")
    return "\n".join(lines)


def build_progress_card(
    *,
    run_id: str,
    case_name: str,
    case_id: str,
    case_index: int,
    case_total: int,
    action_hint: str = "",
    channel_hint: str = "",
) -> dict[str, Any]:
    _ = action_hint  # kept for call-site compatibility
    search = case_search_key(run_id, case_id)
    body_elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"`{search}`"},
    ]
    if channel_hint:
        body_elements.append({"tag": "markdown", "content": channel_hint})

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": _plain(f"巡检 {case_index}/{case_total}"),
            "subtitle": _plain(case_name[:80]),
            "template": "blue",
        },
        "body": {"elements": body_elements},
    }


def build_skipped_card(
    *,
    run_id: str,
    case_name: str,
    case_id: str,
    case_index: int,
    case_total: int,
    reason: str,
) -> dict[str, Any]:
    search = case_search_key(run_id, case_id)
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": _plain(f"未采到回复 {case_index}/{case_total}"),
            "subtitle": _plain(case_name[:80]),
            "template": "grey",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": f"{reason}\n\n`{search}`"},
            ]
        },
    }


def build_inspection_summary_card(
    report: BotRunReport,
    *,
    report_date: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    title, template = _header_template(report)
    run_id = report.run_id or ""
    finished = report.finished_at or datetime.now()
    date_label = report_date or finished.strftime("%Y-%m-%d")

    fails = len([r for r in report.results if r.status == TestStatus.FAIL])
    warns = len([r for r in report.results if r.status == TestStatus.PENDING_FIX])

    overview = [
        _suite_stat_line(report),
        f"失败 **{fails}** · 待整改 **{warns}**",
        f"**综合评分** {format_score_line(compute_inspection_score(report))}",
    ]
    if run_id:
        overview.append(f"本轮编号：`{run_id}`")
        overview.append(f"**复制搜索整轮**\n`{run_search_key(run_id)}`")

    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": "\n\n".join(overview)},
    ]

    attention = _attention_results(report)
    if attention:
        blocks = [_format_attention_item(report, r) for r in attention]
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "markdown",
                "content": "**需关注**\n\n" + "\n\n---\n\n".join(blocks),
            }
        )

    inspector = inspector_at_name()
    footer_lines = [
        f"报告：`reports/{date_label}/{report.bot_name}.html`",
        f"复制追问模板：`@{inspector} 解释 <用例ID>` · `@{inspector} 为什么 ISS-001`",
    ]
    if errors:
        footer_lines.append("**错误**\n" + "\n".join(f"- {e}" for e in errors))

    elements.append({"tag": "hr"})
    elements.append({"tag": "markdown", "content": "\n\n".join(footer_lines)})

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": _plain(title),
            "subtitle": _plain(
                f"{report.bot_name} · {finished.strftime('%Y-%m-%d %H:%M')}"
            ),
            "template": template,
        },
        "body": {"elements": elements},
    }


def format_summary_text(reports: list[BotRunReport], *, errors: list[str] | None = None) -> str:
    """Plain-text fallback matching summary card content."""
    lines = [f"【Bot 巡检摘要】{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for report in reports:
        fails_n = len([x for x in report.results if x.status == TestStatus.FAIL])
        warns_n = len([x for x in report.results if x.status == TestStatus.PENDING_FIX])
        suite_hint = "Full" if report.suite in ("full", "api") else report.suite.upper()
        if report.suite in ("full", "api"):
            stat = f"全量 {report.run_pass_count()}/{report.run_total()}，P0 {report.p0_pass_count()}/{report.p0_total()}"
        else:
            stat = f"P0 {report.p0_pass_count()}/{report.p0_total()}"
        run_bit = f" · 本轮 {report.run_id}" if report.run_id else ""
        score_line = format_score_line(compute_inspection_score(report))
        lines.append(
            f"- {report.bot_name}（{suite_hint}）: {stat}，失败 {fails_n}，待整改 {warns_n}{run_bit}"
        )
        lines.append(f"  评分: {score_line}")
        for result in _attention_results(report):
            run_id = report.run_id or (result.probe_data or {}).get("run_id", "")
            nav = case_navigation(result, run_id=run_id)
            lines.append(
                f"  · {result.case_id} — {result.message or result.status.value}"
            )
            lines.append(f"    复制搜索：{nav['search_key']}")
            lines.append(f"    追问：{nav['explain_command']}")
    lines.append("")
    inspector = inspector_at_name()
    lines.append(f"报告目录: reports/{datetime.now().strftime('%Y-%m-%d')}/（HTML + Markdown）")
    lines.append(
        f"追问检查员：@{inspector} 解释 <用例ID> 或 @{inspector} 为什么 ISS-001"
    )
    if errors:
        lines.append("")
        lines.append("错误:")
        lines.extend(f"- {e}" for e in errors)
    return "\n".join(lines)
