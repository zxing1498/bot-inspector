"""Tests for owner display resolution."""

from datetime import datetime
from unittest.mock import MagicMock

from src.models import BotRunReport
from src.report.owner_display import (
    format_owner_display,
    is_open_id,
    resolve_report_owner,
    resolve_report_owner_display,
)


def test_is_open_id():
    assert is_open_id("ou_demo00000000000000000000001")
    assert not is_open_id("张三")


def test_format_owner_display_resolves_name():
    client = MagicMock()
    client.get_user_name.return_value = "张三"
    assert format_owner_display("ou_abc123", client) == "张三"


def test_format_owner_display_fallback_when_api_fails():
    client = MagicMock()
    client.get_user_name.return_value = ""
    text = format_owner_display("ou_demo00000000000000000000001", client)
    assert "飞书用户" in text
    assert "ou_demo" in text


def test_resolve_report_owner_prefers_trigger_name():
    client = MagicMock()
    assert (
        resolve_report_owner(
            triggered_by="张三",
            triggered_by_open_id="ou_x",
            client=client,
        )
        == "张三"
    )


def test_resolve_report_owner_from_open_id():
    client = MagicMock()
    client.get_user_name.return_value = "张三"
    assert (
        resolve_report_owner(triggered_by_open_id="ou_x", client=client) == "张三"
    )


def test_resolve_report_owner_display_from_stored_ids():
    client = MagicMock()
    client.get_user_name.return_value = ""
    client.list_chat_members.return_value = [
        {
            "member_id": "ou_demo00000000000000000000001",
            "name": "张三",
        }
    ]
    report = BotRunReport(
        bot_name="demo-bot",
        owner="飞书用户（ou_demo_op…）",
        env="staging",
        started_at=datetime.now(),
        owner_open_id="ou_demo00000000000000000000001",
        trigger_chat_id="oc_test",
    )
    assert resolve_report_owner_display(report, client) == "张三"
