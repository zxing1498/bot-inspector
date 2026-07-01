"""Tests for factual explainer."""

from src.conversation.explainer import build_explain_facts, render_template_reply
from src.conversation.intent import ExplainQuery
from src.conversation.session import CaseSnapshot, ChatSession, InspectionSnapshot


def test_build_explain_facts_with_case():
    session = ChatSession(chat_id="c1", operator_open_id="u1")
    session.last_inspection = InspectionSnapshot(
        bot_name="demo-assistant",
        suite="p0",
        started_at="2026-06-25T10:00:00",
        md_path="reports/2026-06-25/demo-assistant.md",
        html_path="reports/2026-06-25/demo-assistant.html",
        pass_count=3,
        fail_count=1,
        failed_cases=[
            CaseSnapshot(
                case_id="p0_doc_denied",
                case_name="无权限文档",
                status="不通过",
                message="未检测到权限相关提示",
                expected="含权限/授权提示",
                actual="Bot 总结了示例业务文档",
                issue_id="ISS-001",
            )
        ],
        all_cases=[
            CaseSnapshot(
                case_id="p0_doc_denied",
                case_name="无权限文档",
                status="不通过",
                message="未检测到权限相关提示",
                expected="含权限/授权提示",
                actual="Bot 总结了示例业务文档",
                issue_id="ISS-001",
            )
        ],
    )
    facts, chunks, case = build_explain_facts(
        ExplainQuery(case_id="p0_doc_denied", bot_name="demo-assistant"),
        session,
    )
    assert case is not None
    assert "p0_doc_denied" in facts
    assert "未检测到权限相关提示" in facts
    assert isinstance(chunks, list)


def test_render_template_reply():
    text = render_template_reply("为什么失败", "事实", [], mode="explain")
    assert "巡检解读" in text
    assert "事实" in text
