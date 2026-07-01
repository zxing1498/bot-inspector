"""Tests for verdict derivation aligned with composite score."""

from datetime import datetime

from src.models import BotRunReport, TestResult, TestStatus
from src.report.scoring import compute_inspection_score
from src.report.verdict import derive_verdict


def _pending_p0(case_id: str, name: str) -> TestResult:
    return TestResult(
        case_id=case_id,
        case_name=name,
        section="p0",
        report_section=case_id.split("_")[1] if "_" in case_id else "messaging",
        status=TestStatus.PENDING_FIX,
        message="首响超过 15s",
    )


def test_high_score_with_pending_fix_is_positive_verdict():
    report = BotRunReport(
        bot_name="demo-bot",
        owner="张星",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            _pending_p0("p0_group_reply", "群聊回复"),
            TestResult(
                case_id="p0_topic_reply",
                case_name="话题回复",
                section="p0",
                report_section="messaging",
                status=TestStatus.PASS,
            ),
            TestResult(
                case_id="p0_doc_denied",
                case_name="无权限文档",
                section="p0",
                report_section="docs",
                status=TestStatus.PASS,
            ),
            _pending_p0("p0_doc_access", "有权限文档"),
            _pending_p0("p0_file_download", "文件处理"),
            TestResult(
                case_id="p0_invalid_cmd_graceful",
                case_name="无效命令",
                section="p0",
                report_section="ops",
                status=TestStatus.PASS,
            ),
            TestResult(
                case_id="p0_slow_ack",
                case_name="首响",
                section="p0",
                report_section="ops",
                status=TestStatus.PASS,
            ),
        ],
    )
    scorecard = compute_inspection_score(report)
    assert scorecard.overall >= 80
    verdict_class, title, desc = derive_verdict(report, scorecard)
    assert verdict_class == "pass"
    assert "优秀" in title or "继续使用" in title
    assert "存在问题，但不影响核心使用" not in title


def test_p0_fail_is_blocking_verdict():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            TestResult(
                case_id="p0_doc_denied",
                case_name="无权限",
                section="p0",
                status=TestStatus.FAIL,
            ),
        ],
    )
    scorecard = compute_inspection_score(report)
    verdict_class, title, _ = derive_verdict(report, scorecard)
    assert verdict_class == "fail"
    assert "阻塞" in title or "整改" in title
