"""Tests for group reply explain intent."""

from src.conversation.intent import parse_explain_query


def test_parse_explain_group_reply_case_name():
    text = (
        "“Bot 能在目标群中接收并回复消息”这一项检测我看demo-assistant 有正常回复，"
        "为什么你会判断为不通过"
    )
    q = parse_explain_query(text)
    assert q is not None
    assert q.case_id == "p0_group_reply"
    assert q.bot_name == "demo-assistant"
