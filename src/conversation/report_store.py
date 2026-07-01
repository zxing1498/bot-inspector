"""Load and index inspection reports from disk."""

from __future__ import annotations

import re
from pathlib import Path

from src.conversation.session import CaseSnapshot, InspectionSnapshot
from src.models import BotRunReport, TestStatus
from src.registry import ROOT, load_all_suites
from src.report.generator import ReportPaths
from src.report.issue_format import build_actual_lines


def _issue_id(index: int) -> str:
    return f"ISS-{index:03d}"


def snapshot_from_report(
    report: BotRunReport,
    paths: ReportPaths,
) -> InspectionSnapshot:
    cases_by_id = {}
    for cases in load_all_suites().values():
        for case in cases:
            cases_by_id[case.id] = case

    failed: list[CaseSnapshot] = []
    all_cases: list[CaseSnapshot] = []
    issue_idx = 1

    for result in report.results:
        if result.status == TestStatus.NA:
            continue
        issue = ""
        if result.status in (TestStatus.FAIL, TestStatus.PENDING_FIX):
            issue = _issue_id(issue_idx)
            issue_idx += 1

        actual_text = "；".join(build_actual_lines(result)[:4])
        snap = CaseSnapshot(
            case_id=result.case_id,
            case_name=result.case_name,
            status=result.status.value,
            message=result.message or "",
            expected=(result.expected or "")[:500],
            actual=actual_text[:800],
            issue_id=issue if result.status in (TestStatus.FAIL, TestStatus.PENDING_FIX) else "",
        )
        all_cases.append(snap)
        if result.status in (TestStatus.FAIL, TestStatus.PENDING_FIX):
            failed.append(snap)

    return InspectionSnapshot(
        bot_name=report.bot_name,
        suite=report.suite,
        started_at=report.started_at.isoformat(timespec="seconds"),
        md_path=str(paths.md),
        html_path=str(paths.html),
        pass_count=report.run_pass_count(),
        fail_count=len(failed),
        failed_cases=failed,
        all_cases=all_cases,
    )


def find_case_in_snapshot(
    snapshot: InspectionSnapshot,
    *,
    case_id: str = "",
    issue_id: str = "",
    case_name_hint: str = "",
) -> CaseSnapshot | None:
    pool = snapshot.all_cases or snapshot.failed_cases

    if issue_id:
        target = issue_id.upper()
        for case in pool:
            if case.issue_id.upper() == target:
                return case

    if case_id:
        cid = case_id.lower()
        for case in pool:
            if case.case_id.lower() == cid:
                return case

    if case_name_hint:
        for case in pool:
            if case_name_hint in case.case_name:
                return case

    return None


def load_latest_snapshot_for_bot(bot_name: str) -> InspectionSnapshot | None:
    reports_root = ROOT / "reports"
    if not reports_root.exists():
        return None

    md_files = sorted(reports_root.glob(f"*/{bot_name}.md"), reverse=True)
    for md_path in md_files:
        snapshot = _parse_md_snapshot(md_path, bot_name)
        if snapshot:
            return snapshot
    return None


def _parse_md_snapshot(md_path: Path, bot_name: str) -> InspectionSnapshot | None:
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    failed: list[CaseSnapshot] = []
    all_cases: list[CaseSnapshot] = []
    issue_idx = 1

    # Parse issue table rows: | ISS-001 | bot | desc | ...
    for match in re.finditer(
        r"\|\s*(ISS-\d+)\s*\|\s*[^|]+\|\s*([^|]+)\s*\|",
        text,
    ):
        issue_id = match.group(1).strip()
        desc = match.group(2).strip()
        case_id = ""
        case_name = desc.split("—")[0].strip() if "—" in desc else desc
        m = re.search(r"（([a-z0-9_]+)）", desc)
        if m:
            case_id = m.group(1)
        snap = CaseSnapshot(
            case_id=case_id,
            case_name=case_name,
            status="不通过",
            message=desc,
            expected="",
            actual="",
            issue_id=issue_id,
        )
        failed.append(snap)
        all_cases.append(snap)
        issue_idx += 1

    if not all_cases:
        return None

    html_path = md_path.with_suffix(".html")
    return InspectionSnapshot(
        bot_name=bot_name,
        suite="unknown",
        started_at="",
        md_path=str(md_path),
        html_path=str(html_path),
        pass_count=0,
        fail_count=len(failed),
        failed_cases=failed,
        all_cases=all_cases,
    )
