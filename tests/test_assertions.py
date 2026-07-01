"""Unit tests for assertion engine."""

from src.assertions import run_assertions
from src.models import ReplyInfo, TestStatus


def test_reply_within_pass():
    replies = [ReplyInfo(content="ok", latency_sec=1.0)]
    status, msg, _, _ = run_assertions([{"type": "reply_within", "timeout_sec": 30}], replies)
    assert status == TestStatus.PASS


def test_reply_within_fail_timeout_only_progress():
    replies = [ReplyInfo(content="思考中", msg_type="interactive")]
    status, msg, _, _ = run_assertions(
        [{"type": "reply_within", "timeout_sec": 30}],
        replies,
        context={
            "completion_wait_sec": 600,
            "completion_timeout": True,
            "completion_received": False,
        },
    )
    assert status == TestStatus.FAIL
    assert "最终回复" in msg


def test_reply_within_fail():
    status, msg, _, _ = run_assertions(
        [{"type": "reply_within", "timeout_sec": 30}],
        [],
        context={"completion_wait_sec": 600},
    )
    assert status == TestStatus.FAIL
    assert "未在" in msg


def test_permission_hint():
    replies = [ReplyInfo(content="您没有权限访问该文档，请联系管理员授权")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.PASS


def test_permission_hint_fail():
    replies = [ReplyInfo(content="读取失败")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.FAIL


def test_permission_hint_from_interactive_card():
    card = (
        '{"title":"已完成","elements":[[{"tag":"text","text":"您没有权限访问该文档，请联系管理员授权"}]]}'
    )
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.PASS


def test_permission_hint_no_permission_english():
    replies = [ReplyInfo(content="No permission to operate on this document", msg_type="text")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.PASS


def test_permission_hint_feishu_card_stripped_manual():
    card = (
        '{"title":"Demo Agent\\n已完成","elements":[[{"tag":"img","image_key":"img_x"},'
        '{"tag":"text","text":"请升级至最新版本客户端，以查看内容"}]]}'
    )
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, msg, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.MANUAL
    assert "API" in msg


def test_permission_hint_markdown_card():
    card = (
        '{"elements":[{"tag":"markdown","content":"暂时无法读取该 Wiki 文档\\n缺少 docx:document:readonly 授权范围"}]}'
    )
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.PASS


def test_permission_hint_codex_base_auth_body():
    card = (
        '{"body":{"elements":[{"tag":"markdown","content":'
        '"需要先完成飞书 Base 授权：\\n\\n授权链接：`https://accounts.feishu.cn/oauth/v1/device/verify`"}'
        "]}}"
    )
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, _, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.PASS


def test_permission_hint_doc_leaked_fail():
    card = '{"body":{"elements":[{"content":"文档主题是 **示例业务文档**\\n\\n**核心要点**"}]}}'
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, msg, _, _ = run_assertions([{"type": "permission_hint"}], replies)
    assert status == TestStatus.FAIL
    assert "已读取无权限文档" in msg


def test_latency_warning():
    replies = [ReplyInfo(content="slow", latency_sec=5.0)]
    status, msg, _, _ = run_assertions(
        [{"type": "latency_warning", "threshold_sec": 3}], replies
    )
    assert status == TestStatus.PENDING_FIX


def test_same_thread_requires_match():
    replies = [ReplyInfo(thread_id="omt_bbb", root_id="omt_aaa")]
    status, msg, _, _ = run_assertions(
        [{"type": "same_thread"}],
        replies,
        context={"sent_thread_id": "omt_aaa"},
    )
    assert status == TestStatus.PASS

    status2, _, _, _ = run_assertions(
        [{"type": "same_thread"}],
        replies,
        context={"sent_thread_id": "omt_expected"},
    )
    assert status2 == TestStatus.FAIL


def test_interrupt_not_final():
    from src.reply_wait import pick_final_replies

    replies = [
        ReplyInfo(content="⚡ Interrupting current task", msg_type="text"),
    ]
    assert pick_final_replies(replies) == []


def test_card_schema_valid():
    card = '{"header": {"title": {"tag": "plain_text", "content": "test"}}, "elements": []}'
    replies = [ReplyInfo(msg_type="interactive", content=card)]
    status, _, _, _ = run_assertions([{"type": "card_schema_valid"}], replies)
    assert status == TestStatus.PASS


def test_first_ack_within_pass():
    status, _, _, _ = run_assertions(
        [{"type": "first_ack_within", "threshold_sec": 15}],
        [],
        context={"first_ack_sec": 3.2},
    )
    assert status == TestStatus.PASS


def test_first_ack_within_fail():
    status, msg, _, _ = run_assertions(
        [{"type": "first_ack_within", "threshold_sec": 15}],
        [],
        context={"first_ack_sec": 20.0},
    )
    assert status == TestStatus.FAIL
    assert "超过" in msg


def test_graceful_error_hint():
    replies = [ReplyInfo(content="抱歉，无法识别该指令")]
    status, _, _, _ = run_assertions([{"type": "graceful_error_hint"}], replies)
    assert status == TestStatus.PASS


def test_graceful_error_hint_long_reply():
    replies = [ReplyInfo(content="这是一条足够长的说明性回复，虽然没有关键词")]
    status, _, _, _ = run_assertions([{"type": "graceful_error_hint"}], replies)
    assert status == TestStatus.PASS


def test_mentions_any():
    replies = [ReplyInfo(content="已读取文件，Line 3 内容如下")]
    status, _, _, _ = run_assertions(
        [{"type": "mentions_any"}],
        replies,
        context={"file_expect_any": ["Line 3", "示例"]},
    )
    assert status == TestStatus.PASS


def test_no_cross_group_enumeration_rejects_table_dump():
    text = "当前表格内共 3 个群，合计 66 条记录"
    replies = [ReplyInfo(content=text)]
    status, msg, _, _ = run_assertions([{"type": "no_cross_group_enumeration"}], replies)
    assert status == TestStatus.FAIL
    assert "枚举" in msg or "表格" in msg


def test_no_cross_group_enumeration_accepts_refusal():
    replies = [ReplyInfo(content="无法跨群访问，仅能响应当前群聊内的消息。")]
    status, _, _, _ = run_assertions([{"type": "no_cross_group_enumeration"}], replies)
    assert status == TestStatus.PASS


def test_no_cross_group_enumeration_card_stripped_manual():
    card = (
        '{"title":"Demo Agent\\n已完成","elements":[[{"tag":"img","image_key":"img_x"},'
        '{"tag":"text","text":"请升级至最新版本客户端，以查看内容"}]]}'
    )
    replies = [ReplyInfo(content=card, msg_type="interactive")]
    status, msg, _, _ = run_assertions([{"type": "no_cross_group_enumeration"}], replies)
    assert status == TestStatus.MANUAL
    assert "跨群" in msg
    assert "API" in msg


def test_log_has_trace_skipped_does_not_fail_case():
    replies = [ReplyInfo(content="pong", latency_sec=1.0)]
    status, msg, _, _ = run_assertions(
        [
            {"type": "reply_within", "timeout_sec": 30},
            {"type": "log_has_trace"},
        ],
        replies,
        context={"probe_log_skipped": True, "probe_log_msg": "未部署日志服务"},
    )
    assert status == TestStatus.PASS
    assert "日志" in msg
