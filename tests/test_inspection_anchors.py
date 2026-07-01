"""Tests for inspection run anchors and summary cards."""

from datetime import datetime

from src.inspection_anchors import (
    attach_case_anchor,
    case_anchor_prefix,
    case_search_key,
    format_case_progress_text,
    format_run_summary_text,
    generate_run_id,
    prepend_case_anchor,
)
from src.models import BotRunReport, TestResult, TestStatus
from src.report.summary_cards import (
    build_inspection_summary_card,
    build_progress_card,
    format_summary_text,
)


def test_generate_run_id_unique_suffix():
    dt = datetime(2026, 6, 25, 17, 32, 45)
    a = generate_run_id(dt)
    b = generate_run_id(dt)
    assert a.startswith("R260625-173245-")
    assert a != b


def test_case_anchor_and_search_key():
    run_id = "R250625-173245-ab"
    assert case_anchor_prefix(run_id, "p0_slow_ack", 7, 7) == (
        "【巡检·R250625-173245-ab·p0_slow_ack·7/7】"
    )
    assert case_search_key(run_id, "p0_slow_ack") == "R250625-173245-ab·p0_slow_ack"


def test_attach_case_anchor_single_line():
    out = attach_case_anchor("请回复", "R1", "p0_group_reply", 1, 7)
    assert out == "请回复\n【巡检·R1·p0_group_reply·1/7】"


def test_attach_case_anchor_multiline():
    out = attach_case_anchor("line1\nline2", "R1", "p0_doc_access", 2, 7)
    assert out.endswith("【巡检·R1·p0_doc_access·2/7】")
    assert out.startswith("line1\nline2")


def test_prepend_alias_appends():
    assert prepend_case_anchor("INVALID_CMD_XYZ_999", "R1", "p0_invalid_cmd_graceful", 6, 7).startswith(
        "INVALID_CMD_XYZ_999"
    )


def test_summary_card_lists_failed_search_keys():
    report = BotRunReport(
        bot_name="demo-assistant",
        owner="tester",
        env="prod",
        started_at=datetime(2026, 6, 25, 17, 0),
        suite="p0",
        run_id="R250625-170000-aa",
        results=[
            TestResult(
                case_id="p0_doc_access",
                case_name="文档访问",
                section="p0",
                status=TestStatus.PENDING_FIX,
                message="首响 47s 超过 15s",
            ),
            TestResult(
                case_id="p0_group_reply",
                case_name="群聊回复",
                section="p0",
                status=TestStatus.PASS,
            ),
        ],
    )
    card = build_inspection_summary_card(report)
    md = card["body"]["elements"][2]["content"]
    assert "p0_doc_access" in md
    assert "R250625-170000-aa·p0_doc_access" in md
    assert "复制搜索" in md
    assert "解释 p0_doc_access" in md
    assert "ISS-001" in md
    assert card["header"]["template"] == "yellow"


def test_format_case_progress_text_searchable():
    text = format_case_progress_text(
        "R260629-200909-7f",
        "p0_slow_ack",
        "Bot 对复杂请求有即时反馈（首响/处理中）",
        7,
        7,
    )
    assert "【巡检 R260629-200909-7f 7/7】" in text
    assert "p0_slow_ack" in text


def test_format_run_summary_text_lists_attention_cases():
    text = format_run_summary_text(
        "R260629-200909-7f",
        "demo-bot",
        case_ids=["p0_doc_denied", "p0_slow_ack"],
    )
    assert "【巡检结束】R260629-200909-7f · demo-bot" in text
    assert "R260629-200909-7f·p0_doc_denied" in text


def test_progress_card_has_search_key():
    card = build_progress_card(
        run_id="R250625-170000-aa",
        case_name="复杂首响",
        case_id="p0_slow_ack",
        case_index=7,
        case_total=7,
    )
    assert card["header"]["title"]["content"] == "巡检 7/7"
    assert card["body"]["elements"][0]["content"] == "`R250625-170000-aa·p0_slow_ack`"


def test_format_summary_text_includes_attention():
    report = BotRunReport(
        bot_name="demo-assistant",
        owner="",
        env="prod",
        started_at=datetime.now(),
        suite="p0",
        run_id="R250625-170000-aa",
        results=[
            TestResult(
                case_id="p0_slow_ack",
                case_name="首响",
                section="p0",
                status=TestStatus.FAIL,
                message="无回复",
            )
        ],
    )
    text = format_summary_text([report])
    assert "R250625-170000-aa·p0_slow_ack" in text
    assert "搜索" in text
