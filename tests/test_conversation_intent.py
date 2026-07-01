"""Tests for conversation intent parsing."""

from src.conversation.intent import (
    Intent,
    classify_intent,
    parse_explain_query,
)
from src.conversation.session import CaseSnapshot, ChatSession, InspectionSnapshot


def test_parse_explain_by_case_id():
    q = parse_explain_query("解释 p0_doc_denied")
    assert q is not None
    assert q.case_id == "p0_doc_denied"


def test_parse_explain_by_issue():
    q = parse_explain_query("为什么 ISS-001 判失败")
    assert q is not None
    assert q.issue_id == "ISS-001"


def test_parse_explain_from_session_case_name():
    session = ChatSession(chat_id="c1", operator_open_id="u1")
    session.last_inspection = InspectionSnapshot(
        bot_name="demo-assistant",
        suite="p0",
        started_at="",
        md_path="reports/x.md",
        html_path="reports/x.html",
        pass_count=3,
        fail_count=1,
        failed_cases=[
            CaseSnapshot(
                case_id="p0_doc_denied",
                case_name="Bot 对无权限文档拒绝访问并给出明确提示",
                status="不通过",
                message="未检测到权限相关提示",
                expected="含权限提示",
                actual="已读取文档",
                issue_id="ISS-001",
            )
        ],
    )
    q = parse_explain_query("无权限文档这项为什么失败", session)
    assert q is not None
    assert q.case_id == "p0_doc_denied"
    assert q.bot_name == "demo-assistant"


def test_classify_advise():
    assert classify_intent("建议文件检测应该回复附件") == Intent.ADVISE


def test_classify_execute_unknown():
    assert classify_intent("巡检 p0 demo-assistant") == Intent.UNKNOWN
