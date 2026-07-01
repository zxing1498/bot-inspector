"""Tests for emoji reaction polling as bot first ack."""

import time

from src.assertions import run_assertions
from src.feishu.client import FeishuClient
from src.models import ReplyInfo, TestStatus


class _FakeReactionClient(FeishuClient):
    def __init__(self) -> None:
        super().__init__("inspector", "secret")
        self.reactions_by_message: dict[str, list[dict]] = {}
        self.chat_messages: list[dict] = []
        self.thread_messages: dict[str, list[dict]] = {}

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

    def list_message_reactions(self, message_id: str, *, page_size: int = 50) -> list[dict]:
        return list(self.reactions_by_message.get(message_id, []))


def test_reaction_from_target_bot_matches_app_operator():
    client = FeishuClient("app", "secret")
    reaction = {
        "reaction_id": "rx_1",
        "operator": {"operator_type": "app", "operator_id": "cli_bot"},
        "action_time": "2000000005000",
        "reaction_type": {"emoji_type": "THUMBSUP"},
    }
    assert client._reaction_from_target_bot(
        reaction,
        after_ts=2000000000.0,
        sender_app_id="cli_bot",
    )


def test_reaction_from_target_bot_rejects_other_app():
    client = FeishuClient("app", "secret")
    reaction = {
        "operator": {"operator_type": "app", "operator_id": "cli_other"},
        "action_time": "2000000005000",
    }
    assert not client._reaction_from_target_bot(
        reaction,
        after_ts=2000000000.0,
        sender_app_id="cli_bot",
    )


def test_wait_for_any_bot_ack_prefers_earlier_reaction():
    client = _FakeReactionClient()
    after_ts = time.time()
    client.reactions_by_message["om_probe"] = [
        {
            "reaction_id": "rx_fast",
            "operator": {"operator_type": "app", "operator_id": "cli_bot"},
            "action_time": str(int((after_ts + 2) * 1000)),
            "reaction_type": {"emoji_type": "OK"},
        }
    ]
    client.chat_messages = [
        {
            "message_id": "om_slow",
            "create_time": str(int((after_ts + 20) * 1000)),
            "sender": {"sender_type": "app", "id": "cli_bot"},
            "msg_type": "text",
            "body": {"content": '{"text":"完成"}'},
        }
    ]

    acks = client.wait_for_any_bot_ack(
        "oc_chat",
        after_ts=after_ts,
        timeout_sec=1.0,
        sender_app_id="cli_bot",
        probe_message_ids=["om_probe"],
        poll_interval=0.01,
    )
    assert len(acks) == 2
    assert acks[0].msg_type == "reaction"
    assert acks[0].content == "表情回复:OK"
    assert acks[0].latency_sec < acks[1].latency_sec


def test_first_ack_within_passes_on_reaction_only():
    status, msg, _, actual = run_assertions(
        [
            {"type": "first_ack_within", "threshold_sec": 15},
            {"type": "not_system_error"},
        ],
        [ReplyInfo(msg_type="reaction", content="表情回复:OK", latency_sec=3.0)],
        context={
            "first_ack_sec": 3.0,
            "first_ack_kind": "reaction",
            "first_ack_reaction": "表情回复:OK",
        },
    )
    assert status == TestStatus.PASS
    assert "表情回复:OK" in actual
