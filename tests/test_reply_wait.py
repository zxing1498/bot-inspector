"""Tests for completion reply detection."""

from src.models import ReplyInfo
from src.reply_wait import card_elements, is_completion_reply, is_in_progress_reply, pick_final_replies


def test_in_progress_thinking_card():
    reply = ReplyInfo(
        msg_type="interactive",
        content='{"header":{"title":{"content":"思考中"}},"elements":[]}',
    )
    assert is_in_progress_reply(reply)
    assert not is_completion_reply(reply)


def test_completion_card():
    reply = ReplyInfo(
        msg_type="interactive",
        content='{"header":{"title":{"content":"已完成"}},"elements":[{"text":"群聊正常"}]}',
    )
    assert is_completion_reply(reply)


def test_simple_text_reply():
    reply = ReplyInfo(msg_type="text", content="群聊正常")
    assert is_completion_reply(reply)


def test_agent_style_completion_card():
    reply = ReplyInfo(
        msg_type="interactive",
        content=(
            '{"header":{"title":{"content":"Demo Agent"}},'
            '"elements":[{"tag":"markdown","content":"已完成\\n群聊正常"}]}'
        ),
    )
    assert is_completion_reply(reply)


def test_runtime_footer_body_elements_card():
    reply = ReplyInfo(
        msg_type="interactive",
        content=(
            '{"body":{"elements":['
            '{"tag":"markdown","content":"群聊正常"},'
            '{"tag":"hr"},'
            '{"tag":"markdown","content":"gpt-demo · out 7 · in 16.6k cw 0 cr 10.1k · ctx 6%\\n~/workspace/agent-runtime"}'
            "]}}"
        ),
    )
    assert is_completion_reply(reply)
    assert not is_in_progress_reply(reply)


def test_runtime_footer_thinking_body_card():
    reply = ReplyInfo(
        msg_type="interactive",
        content='{"body":{"elements":[{"tag":"markdown","content":"思考中"}]}}',
    )
    assert is_in_progress_reply(reply)
    assert not is_completion_reply(reply)


def test_pick_final_prefers_completion():
    thinking = ReplyInfo(msg_type="interactive", content="思考中")
    done = ReplyInfo(msg_type="text", content="群聊正常")
    picked = pick_final_replies([thinking, done])
    assert picked == [done]
