from unittest.mock import MagicMock

from src.runner import resolve_report_owner


def test_resolve_report_owner_prefers_triggered_by():
    assert resolve_report_owner(triggered_by="张三", bot_owner="李四") == "张三"


def test_resolve_report_owner_falls_back_to_bot_owner():
    assert resolve_report_owner(triggered_by="", bot_owner="张三") == "张三"


def test_resolve_report_owner_empty_when_both_missing():
    assert resolve_report_owner(triggered_by="", bot_owner="") == ""


def test_resolve_report_owner_accepts_trigger_chat_id():
    client = MagicMock()
    client.get_user_name.return_value = "张三"
    assert (
        resolve_report_owner(
            triggered_by_open_id="ou_x",
            client=client,
            trigger_chat_id="oc_test",
        )
        == "张三"
    )
    client.get_user_name.assert_called_once_with("ou_x", chat_id="oc_test")

