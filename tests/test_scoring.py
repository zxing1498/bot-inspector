"""Tests for inspection percentile scoring."""

from __future__ import annotations

from datetime import datetime

from src.models import BotRunReport, ReplyInfo, TestResult, TestStatus
from src.report.scoring import compute_inspection_score, grade_for_score


def _result(
    case_id: str,
    *,
    name: str = "",
    section: str = "p0",
    status: TestStatus = TestStatus.PASS,
    message: str = "",
    latency_sec: float = 0.0,
    probe_data: dict | None = None,
    replies: list[ReplyInfo] | None = None,
) -> TestResult:
    return TestResult(
        case_id=case_id,
        case_name=name or case_id,
        section=section,
        status=status,
        message=message,
        latency_sec=latency_sec,
        probe_data=probe_data or {},
        replies=replies or [],
    )


def test_grade_for_score_bands():
    assert grade_for_score(95) == ("A", "优秀")
    assert grade_for_score(85) == ("B", "良好")
    assert grade_for_score(75) == ("C", "合格")
    assert grade_for_score(65) == ("D", "待改进")
    assert grade_for_score(40) == ("F", "不合格")


def test_all_pass_p0_scores_high():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            _result(
                "p0_group_reply",
                name="群聊回复",
                probe_data={"first_ack_sec": 3.0},
                replies=[ReplyInfo(latency_sec=8.0)],
            ),
            _result(
                "p0_slow_ack",
                name="复杂首响",
                probe_data={"first_ack_sec": 10.0},
            ),
            _result(
                "p0_doc_access",
                name="有权限文档",
                probe_data={"first_ack_sec": 5.0},
                replies=[ReplyInfo(latency_sec=40.0, content="总结完成")],
            ),
            _result(
                "p0_doc_denied",
                name="无权限文档",
                probe_data={"first_ack_sec": 4.0},
                replies=[ReplyInfo(latency_sec=20.0, content="无权限访问")],
            ),
            _result(
                "p0_file_download",
                name="文件处理",
                probe_data={"first_ack_sec": 6.0},
                replies=[ReplyInfo(latency_sec=50.0, content="已处理文件")],
            ),
            _result(
                "p0_invalid_cmd_graceful",
                name="无效命令兜底",
                probe_data={"first_ack_sec": 2.0},
                replies=[ReplyInfo(latency_sec=5.0, content="无法识别该命令")],
            ),
            _result(
                "p0_topic_reply",
                name="话题群回复",
                probe_data={"first_ack_sec": 4.0},
                replies=[ReplyInfo(latency_sec=15.0, content="话题回复")],
            ),
        ],
    )
    card = compute_inspection_score(report)
    assert card.overall >= 90
    assert card.grade == "A"


def test_failures_lower_completion_and_overall():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            _result(
                "p0_doc_denied",
                name="无权限文档",
                status=TestStatus.FAIL,
                message="Bot 已读取无权限文档内容",
                probe_data={"first_ack_sec": 8.0, "completion_received": True},
                replies=[ReplyInfo(latency_sec=45.0, content="已读取文档主题")],
            ),
            _result(
                "p0_group_reply",
                name="群聊回复",
                status=TestStatus.PASS,
                probe_data={"first_ack_sec": 4.0},
                replies=[ReplyInfo(latency_sec=6.0, content="ok")],
            ),
        ],
    )
    card = compute_inspection_score(report)
    completion = next(d for d in card.dimensions if d.key == "task_completion")
    assert completion.score < 100
    assert card.overall < 90


def test_slow_first_ack_penalizes_response_timeliness():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            _result(
                "p0_slow_ack",
                name="复杂首响",
                status=TestStatus.FAIL,
                message="首响 32s 超过 15s",
                probe_data={"first_ack_sec": 32.0},
            ),
        ],
    )
    card = compute_inspection_score(report)
    response = next(d for d in card.dimensions if d.key == "response_timeliness")
    assert response.score < 60
    assert card.overall < 80


def test_latency_only_pending_fix_keeps_moderate_completion_score():
    report = BotRunReport(
        bot_name="demo",
        owner="",
        env="staging",
        started_at=datetime.now(),
        suite="p0",
        results=[
            _result(
                "p0_group_reply",
                name="群聊回复",
                status=TestStatus.PENDING_FIX,
                message="首响 18s 超过 15s",
                probe_data={"first_ack_sec": 18.0},
                replies=[ReplyInfo(latency_sec=20.0, content="回复内容")],
            ),
        ],
    )
    card = compute_inspection_score(report)
    breakdown = card.case_breakdowns[0]
    assert breakdown.task_completion == 80.0
    assert card.overall >= 60
