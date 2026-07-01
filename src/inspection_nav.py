"""Navigation hints: search keys and @inspector explain commands."""

from __future__ import annotations

import os

from src.inspection_anchors import case_search_key, run_search_key
from src.models import TestResult


def inspector_at_name() -> str:
    return (os.getenv("INSPECTOR_AT_NAME", "bot检查员") or "bot检查员").strip()


def explain_case_command(case_id: str) -> str:
    return f"@{inspector_at_name()} 解释 {case_id}"


def explain_issue_command(issue_id: str) -> str:
    return f"@{inspector_at_name()} 为什么 {issue_id}"


def case_navigation(
    result: TestResult,
    *,
    run_id: str = "",
    issue_id: str = "",
) -> dict[str, str]:
    """Search + explain hints for one test result."""
    search = case_search_key(run_id, result.case_id) if run_id else result.case_id
    nav: dict[str, str] = {
        "case_id": result.case_id,
        "search_key": search,
        "explain_command": explain_case_command(result.case_id),
    }
    if issue_id:
        nav["explain_issue_command"] = explain_issue_command(issue_id)
    if run_id:
        nav["run_id"] = run_id
        nav["run_search_key"] = run_search_key(run_id)
    return nav
