"""Tests for section summary labels."""

from src.models import BotRunReport, TestResult, TestStatus


def test_section_summary_pending_fix_not_fail():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=__import__("datetime").datetime.now(),
        results=[
            TestResult(
                case_id="p0_doc_access",
                case_name="有权限文档",
                section="p0",
                report_section="docs",
                status=TestStatus.PENDING_FIX,
            ),
        ],
    )
    assert report.section_summary("docs") == "待整改"
