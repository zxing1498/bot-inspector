"""Tests for issue navigation fields in reports."""

from src.inspection_nav import explain_case_command, explain_issue_command
from src.models import TestResult, TestStatus
from src.report.issue_format import format_issue


def test_format_issue_includes_navigation():
    result = TestResult(
        case_id="p0_slow_ack",
        case_name="首响",
        section="p0",
        status=TestStatus.FAIL,
        message="无回复",
    )
    issue = format_issue(
        result, bot_name="尾程小助", index=1, run_id="R260625-120000-ab"
    )
    assert issue["search_key"] == "R260625-120000-ab·p0_slow_ack"
    assert issue["explain_command"] == explain_case_command("p0_slow_ack")
    assert issue["explain_issue_command"] == explain_issue_command("ISS-001")
