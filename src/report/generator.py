"""Markdown + HTML report generator aligned with checklist format."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import BotRunReport, TestStatus
from src.registry import ROOT, load_all_suites, load_env_config
from src.inspection_anchors import run_search_key
from src.inspection_nav import case_navigation
from src.report.issue_format import format_issue
from src.report.scoring import compute_inspection_score
from src.report.suggestions import generate_suggestions
from src.report.verdict import derive_verdict
from src.report.owner_display import resolve_report_owner_display
from src.error_messages import sanitize_report_text

SECTION_LABELS = {
    "config": "基础配置与权限",
    "messaging": "消息收发能力",
    "p0": "P0 必测",
    "docs": "飞书文档访问能力",
    "files": "群文件下载与发送能力",
    "ops": "稳定性与运维",
    "security": "安全与合规",
}

DETAIL_SECTIONS = [
    ("config", "3. 基础配置与权限检查"),
    ("messaging", "4. 消息收发能力检查"),
    ("docs", "6. 飞书文档访问能力检查"),
    ("files", "7. 群文件下载与发送能力检查"),
    ("ops", "9. 稳定性与运维检查"),
    ("security", "10. 安全与合规检查"),
]

STATUS_CLASS = {
    "通过": "pass",
    "不通过": "fail",
    "待整改": "warn",
    "待人工确认": "manual",
    "待确认权限": "manual",
    "不适用": "na",
}


def _owner_display(report: BotRunReport) -> str:
    return resolve_report_owner_display(report)


def _env_display(env: str) -> str:
    envs = load_env_config().get("environments", {})
    label = (envs.get(env) or {}).get("label", "")
    if label and label != env:
        return f"{label}（{env}）"
    return env or "未配置"


def _suite_label(report: BotRunReport) -> str:
    if report.suite in ("full", "api"):
        names = "、".join(
            {
                "p0": "P0",
                "messaging": "消息",
                "docs": "文档",
                "files": "文件",
                "ops": "运维",
                "security": "安全",
                "config": "配置",
            }.get(n, n)
            for n in report.suite_names
        )
        return f"Full 完整巡检（{names}）"
    if len(report.suite_names) == 1:
        return {"p0": "P0 必测"}.get(report.suite_names[0], report.suite_names[0])
    return report.suite or "P0 必测"


def _is_full_suite(report: BotRunReport) -> bool:
    return report.suite in ("full", "api") or len(report.suite_names or []) > 1


@dataclass
class ReportPaths:
    md: Path
    html: Path


def _issues_from_report(report: BotRunReport) -> list[dict]:
    cases_by_id: dict[str, Any] = {}
    for cases in load_all_suites().values():
        for case in cases:
            cases_by_id[case.id] = case
    issues = []
    idx = 1
    for r in report.results:
        if r.status in (TestStatus.FAIL, TestStatus.PENDING_FIX):
            case = cases_by_id.get(r.case_id)
            issues.append(
                format_issue(
                    r,
                    bot_name=report.bot_name,
                    index=idx,
                    case=case,
                    run_id=report.run_id,
                )
            )
            idx += 1
    return issues


def _build_context(report: BotRunReport) -> dict:
    generate_suggestions(report)
    scorecard = compute_inspection_score(report)

    p0_fails = [r for r in report.results if r.section == "p0" and r.status == TestStatus.FAIL]
    final_pass = not p0_fails and report.p0_pass_count() == report.p0_total()
    verdict_class, verdict_title, verdict_desc = derive_verdict(report, scorecard)
    final_partial = verdict_class == "partial"

    p0_total = report.p0_total()
    p0_pass = report.p0_pass_count()
    p0_pct = int((p0_pass / p0_total * 100) if p0_total else 0)
    run_total = report.run_total()
    run_pass = report.run_pass_count()
    run_pct = int((run_pass / run_total * 100) if run_total else 0)
    is_full = _is_full_suite(report)
    suite_label = _suite_label(report)
    owner_display = _owner_display(report)
    env_display = _env_display(report.env)

    score_ctx = scorecard.to_context()

    def section_summary(section: str) -> str:
        return report.section_summary(section)

    def results_by_section(section: str):
        return [
            r
            for r in report.results
            if r.section == section or r.report_section == section
        ]

    def status_class(status: str) -> str:
        return STATUS_CLASS.get(status, "na")

    sections = [(k, v) for k, v in SECTION_LABELS.items() if k != "p0"]

    run_id = report.run_id or ""
    issues = _issues_from_report(report)
    navigation_items = []
    for r in report.results:
        if r.status in (
            TestStatus.FAIL,
            TestStatus.PENDING_FIX,
            TestStatus.MANUAL,
            TestStatus.PENDING_PERM,
        ):
            issue_match = next((i for i in issues if i["case_id"] == r.case_id), None)
            navigation_items.append(
                {
                    **case_navigation(
                        r,
                        run_id=run_id,
                        issue_id=issue_match["id"] if issue_match else "",
                    ),
                    "case_name": r.case_name,
                    "status": r.status.value,
                    "message": sanitize_report_text(r.message or ""),
                }
            )

    p0_results_enriched = []
    for r in [x for x in report.results if x.section == "p0"]:
        nav = case_navigation(r, run_id=run_id)
        p0_results_enriched.append({"result": r, "nav": nav})

    return {
        "bot_name": report.bot_name,
        "owner": report.owner,
        "owner_display": owner_display,
        "owner_open_id": report.owner_open_id,
        "trigger_chat_id": report.trigger_chat_id,
        "env": report.env,
        "env_display": env_display,
        "suite": report.suite,
        "suite_label": suite_label,
        "is_full": is_full,
        "started_at": report.started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": (report.finished_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "p0_pass": p0_pass,
        "p0_total": p0_total,
        "p0_pct": p0_pct,
        "run_pass": run_pass,
        "run_total": run_total,
        "run_pct": run_pct,
        "sections": sections,
        "section_summary": section_summary,
        "status_class": status_class,
        "p0_results": [r for r in report.results if r.section == "p0"],
        "p0_results_enriched": p0_results_enriched,
        "run_id": run_id,
        "run_search_key": run_search_key(run_id) if run_id else "",
        "navigation_items": navigation_items,
        "detail_sections": DETAIL_SECTIONS,
        "results_by_section": results_by_section,
        "issues": issues,
        "suggestions": report.suggestions,
        "final_pass": final_pass,
        "final_partial": final_partial and not final_pass,
        "verdict_class": verdict_class,
        "verdict_title": verdict_title,
        "verdict_desc": verdict_desc,
        "score": score_ctx,
    }


def generate_report(report: BotRunReport, output_dir: Path | None = None) -> ReportPaths:
    out_dir = output_dir or (ROOT / "reports" / datetime.now().strftime("%Y-%m-%d"))
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = report.bot_name.replace("/", "_").replace("\\", "_")
    md_path = out_dir / f"{safe_name}.md"
    html_path = out_dir / f"{safe_name}.html"

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "src" / "report" / "templates")),
        autoescape=select_autoescape(default_for_string=False, default=True),
    )
    env.filters["sanitize"] = sanitize_report_text
    ctx = _build_context(report)

    md_path.write_text(env.get_template("report.md.j2").render(**ctx), encoding="utf-8")
    html_path.write_text(env.get_template("report.html.j2").render(**ctx), encoding="utf-8")

    return ReportPaths(md=md_path, html=html_path)
