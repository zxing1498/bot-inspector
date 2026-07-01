"""Format issue records for HTML/Markdown reports — tests."""

from __future__ import annotations

from src.models import ReplyInfo, TestCaseDef, TestResult, TestStatus
from src.report.issue_format import build_actual_lines, format_issue


def test_format_issue_with_repro_expected_and_reply_preview():
    case = TestCaseDef(
        id="p0_dm_reply",
        name="Bot 能在私聊中接收并回复消息",
        section="p0",
        capabilities=["messaging"],
        prompt="你好，请回复「收到」",
        channel="dm",
        assertions=[
            {"type": "reply_within", "timeout_sec": 30},
            {"type": "content_not_empty"},
        ],
    )
    result = TestResult(
        case_id="p0_dm_reply",
        case_name=case.name,
        section="p0",
        status=TestStatus.FAIL,
        message="未在 30s 内收到回复; 回复内容为空",
        repro_steps="1. 渠道：私聊\n2. 用例：Bot 能在私聊中接收并回复消息（p0_dm_reply）\n3. 目标 Bot：demo-agent\n4. Inspector 发送消息\n5. 消息内容：你好，请回复「收到」",
        expected="30s 内收到最终回复 | 回复内容非空",
        actual="无回复 | 空",
        severity="P0",
        replies=[ReplyInfo(content="思考中…", msg_type="text", latency_sec=2.1)],
    )

    issue = format_issue(result, bot_name="demo-agent", index=1, case=case)

    assert issue["id"] == "ISS-001"
    assert len(issue["repro_lines"]) >= 4
    assert "私聊" in issue["repro_lines"][0]
    assert len(issue["expected_lines"]) == 2
    assert "30" in issue["expected_lines"][0]
    assert any("未在 30s" in line for line in issue["actual_lines"])
    assert any("思考中" in line for line in issue["actual_lines"])


def test_format_issue_falls_back_to_case_assertions_when_expected_missing():
    case = TestCaseDef(
        id="p0_topic_reply",
        name="Bot 能在话题群中回复",
        section="p0",
        capabilities=["messaging"],
        channel="topic_group",
        at_bot=True,
        in_thread=True,
        assertions=[
            {"type": "reply_within", "timeout_sec": 30},
            {"type": "same_thread"},
        ],
    )
    result = TestResult(
        case_id="p0_topic_reply",
        case_name=case.name,
        section="p0",
        status=TestStatus.FAIL,
        message="回复未落在同一话题",
        severity="P0",
    )

    issue = format_issue(result, bot_name="demo-agent", index=2, case=case)

    assert issue["repro_lines"][0].startswith("目标 Bot")
    assert any("话题" in line for line in issue["expected_lines"])
    assert issue["actual_lines"][0] == "回复未落在同一话题"


def test_build_actual_lines_splits_semicolon_messages_without_duplicates():
    result = TestResult(
        case_id="p0_x",
        case_name="x",
        section="p0",
        status=TestStatus.FAIL,
        message="未在 30s 内收到回复; 未返回 interactive 卡片",
        actual="无回复 | msg_types=['text']",
    )
    lines = build_actual_lines(result)
    assert lines[0] == "未在 30s 内收到回复"
    assert lines[1] == "未返回 interactive 卡片"
    assert "无回复" in lines
    assert lines.count("未在 30s 内收到回复") == 1


def test_build_actual_lines_sanitizes_technical_errors():
    result = TestResult(
        case_id="file_small",
        case_name="下载小文件",
        section="files",
        status=TestStatus.FAIL,
        message="unsupported operand type(s) for /: 'WindowsPath' and 'dict'",
        actual="unsupported operand type(s) for /: 'WindowsPath' and 'dict'",
    )
    issue = format_issue(result, bot_name="demo-bot", index=5)
    assert "WindowsPath" not in issue["desc"]
    assert all("WindowsPath" not in line for line in issue["actual_lines"])
