"""Tests for explain interactive cards."""

from src.conversation.cards import build_explain_card
from src.conversation.session import CaseSnapshot


def test_build_explain_card_uses_case_header():
    case = CaseSnapshot(
        case_id="p0_group_reply",
        case_name="Bot 能在目标群中接收并回复消息",
        status="待整改",
        message="首响 16.44s 超过 15s",
        expected="首响 ≤ 15s",
        actual="16.44s",
        issue_id="ISS-001",
    )
    card = build_explain_card("**结论**：待整改", mode="explain", case=case)
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "巡检解读 · p0_group_reply"
    assert card["header"]["template"] == "yellow"
    assert "待整改" in card["body"]["elements"][0]["content"]
