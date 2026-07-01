"""Tests for topic/thread reply polling."""

from src.feishu.client import FeishuClient


class _FakeClient(FeishuClient):
    def __init__(self) -> None:
        super().__init__("app", "secret")
        self.chat_messages: list[dict] = []
        self.thread_messages: dict[str, list[dict]] = {}
        self.message_lookup: dict[str, dict] = {}

    def list_messages(
        self,
        container_id: str,
        *,
        container_id_type: str = "chat",
        start_time: str | None = None,
        page_size: int = 50,
    ) -> list[dict]:
        if container_id_type == "thread":
            return list(self.thread_messages.get(container_id, []))
        return list(self.chat_messages)

    def get_message(self, message_id: str, *, user_card_content: bool = True):
        return self.message_lookup.get(message_id)


def test_gather_includes_thread_replies_not_visible_in_chat():
    client = _FakeClient()
    client.chat_messages = [
        {
            "message_id": "om_root",
            "thread_id": "omt_aaa",
            "create_time": "2000000000000",
            "sender": {"sender_type": "user", "id": "ou_user"},
        }
    ]
    client.thread_messages["omt_aaa"] = [
        {
            "message_id": "om_bot",
            "thread_id": "omt_aaa",
            "create_time": "2000000001000",
            "sender": {"sender_type": "app", "id": "cli_bot"},
            "body": {"content": '{"text":"话题正常"}'},
            "msg_type": "text",
        }
    ]

    by_id = client._gather_bot_message_candidates(
        "oc_chat",
        after_ts=2000000000.0,
        start_time="1999999999",
        thread_hint="om_root",
    )
    assert "om_bot" in by_id


def test_resolve_thread_id_from_message():
    client = _FakeClient()
    client.message_lookup["om_root"] = {"thread_id": "omt_xyz"}
    assert client.resolve_thread_id("omt_xyz") == "omt_xyz"
    assert client.resolve_thread_id("om_root") == "omt_xyz"
