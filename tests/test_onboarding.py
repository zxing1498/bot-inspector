"""Tests for interactive bot onboarding."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.chat_trigger import parse_config_command, parse_test_command, should_start_onboarding
from src.models import BotConfig
from src.onboarding.cards import build_config_form_card, build_validation_result_card, field_help_text, parse_text_form_submission
from src.onboarding.models import CheckResult, ValidationReport, bot_from_form, parse_capabilities
from src.onboarding.validator import validate_bot_config
from src.registry import _merge_bot_dict


def test_parse_test_command_basic():
    err, suite, bot, reg = parse_test_command("测试 demo-kb-bot")
    assert err is None
    assert suite == "p0"
    assert bot == "demo-kb-bot"
    assert reg is False


def test_parse_test_command_full():
    err, suite, bot, _ = parse_test_command("测试 full demo-kb-bot")
    assert err is None
    assert suite == "full"
    assert bot == "demo-kb-bot"


def test_parse_register_command():
    err, suite, bot, reg = parse_test_command("注册 新Bot")
    assert err is None
    assert reg is True
    assert bot == "新Bot"


def test_parse_config_command():
    err, bot = parse_config_command("配置 demo-assistant")
    assert err is None
    assert bot == "demo-assistant"

    err, bot = parse_config_command("修改配置 agent")
    assert err is None
    assert bot == "agent"

    err, bot = parse_config_command("更新配置 demo-kb-bot")
    assert err is None
    assert bot == "demo-kb-bot"

    err, bot = parse_config_command("配置")
    assert err is not None
    assert bot == ""

    err, bot = parse_config_command("巡检 p0 demo")
    assert err is None
    assert bot == ""


def test_merge_registered_overlays_yaml_bot():
    base = {
        "name": "demo",
        "app_id": "cli_base",
        "test_assets": {"doc_permitted": "https://old/ok"},
        "capabilities": ["messaging"],
    }
    overlay = {
        "name": "demo",
        "test_assets": {"doc_permitted": "https://new/ok", "doc_denied": "https://new/deny"},
    }
    merged = _merge_bot_dict(base, overlay)
    assert merged["app_id"] == "cli_base"
    assert merged["test_assets"]["doc_permitted"] == "https://new/ok"
    assert merged["test_assets"]["doc_denied"] == "https://new/deny"


def test_config_form_card_reconfigure_title():
    card = build_config_form_card("s1", "demo-assistant", "oc_x", {}, reconfigure=True)
    assert "修改配置" in card["header"]["title"]["content"]


def test_validation_card_save_only():
    report = ValidationReport(
        ok=True,
        checks=[CheckResult(name="x", ok=True, message="ok", blocking=False)],
    )
    card = build_validation_result_card("s1", "demo", report, register_only=True, reconfigure=True)
    assert card["header"]["title"]["content"] == "校验通过，配置已可保存"
    btn = next(e for e in card["body"]["elements"] if e.get("tag") == "button")
    assert btn["text"]["content"] == "保存配置"


def test_parse_capabilities_defaults():
    assert parse_capabilities("") == ["messaging", "topic_reply", "doc_access", "file_process", "card_reply", "export_file"]
    assert parse_capabilities("messaging, doc_access") == ["messaging", "doc_access"]


def test_bot_from_form_builds_config():
    bot = bot_from_form(
        "demo-bot",
        "oc_group123",
        {
            "target_app_id": "cli_abc",
            "open_id": "ou_xyz",
            "capabilities": "messaging,topic_reply",
            "health_url": "http://example.com",
        },
    )
    assert bot.name == "demo-bot"
    assert bot.chats["normal_group"] == "oc_group123"
    assert "topic_reply" in bot.capabilities


def test_bot_from_form_default_doc_urls():
    from src.onboarding.models import DEFAULT_DOC_DENIED, DEFAULT_DOC_PERMITTED

    bot = bot_from_form(
        "demo-bot",
        "oc_group123",
        {
            "target_app_id": "cli_abc",
            "open_id": "ou_xyz",
            "capabilities": "messaging,doc_access",
        },
    )
    assert bot.test_assets["doc_permitted"] == DEFAULT_DOC_PERMITTED
    assert bot.test_assets["doc_denied"] == DEFAULT_DOC_DENIED


def test_bot_from_form_custom_doc_urls():
    custom_ok = "https://example.com/permitted"
    custom_deny = "https://example.com/denied"
    bot = bot_from_form(
        "demo-bot",
        "oc_group123",
        {
            "target_app_id": "cli_abc",
            "open_id": "ou_xyz",
            "capabilities": "doc_access",
            "doc_permitted": custom_ok,
            "doc_denied": custom_deny,
        },
    )
    assert bot.test_assets["doc_permitted"] == custom_ok
    assert bot.test_assets["doc_denied"] == custom_deny


def test_parse_text_form_submission():
    text = """
app_id: cli_demo
open_id: ou_demo
capabilities: messaging
"""
    form = parse_text_form_submission(text)
    assert form is not None
    assert form["target_app_id"] == "cli_demo"
    assert form["open_id"] == "ou_demo"


def test_validate_bot_config_required_fields():
    client = MagicMock()
    bot = BotConfig(name="x", app_id="", owner="", env="staging", open_id="", chats={})
    report = validate_bot_config(bot, client, trigger_chat_id="oc_test")
    assert not report.ok
    names = {c.name for c in report.blockers}
    assert "App ID" in names
    assert "open_id" in names


def test_validate_private_chat_failure_is_warning_only():
    client = MagicMock()
    client.is_bot_in_chat.return_value = True
    client.send_text.side_effect = RuntimeError(
        "Feishu HTTP 400: Bot has NO availability to this user."
    )
    bot = BotConfig(
        name="demo-bot",
        app_id="cli_demoappid000001",
        target_app_id="cli_demoappid000001",
        owner="",
        env="staging",
        open_id="ou_demo00000000000000000000001",
        chats={"normal_group": "oc_demo00000000000000000000001"},
        capabilities=["messaging"],
        test_assets={
            "doc_permitted": "https://example.feishu.cn/docx/permitted",
            "doc_denied": "https://example.feishu.cn/docx/denied",
        },
    )
    report = validate_bot_config(
        bot, client, trigger_chat_id="oc_demo00000000000000000000001"
    )
    assert report.ok
    dm = next(c for c in report.checks if c.name == "私聊通道")
    assert not dm.ok
    assert dm.blocking is False
    assert dm in report.warnings
    assert not report.blockers


def test_config_form_card_schema_2():
    card = build_config_form_card("sess1", "demo-bot", "oc_test", {})
    assert card["schema"] == "2.0"
    form = next(e for e in card["body"]["elements"] if e["tag"] == "form")
    submit = next(e for e in form["elements"] if e["tag"] == "button")
    assert submit["action_type"] == "form_submit"
    assert submit["name"] == "submit_config"
    assert "complex_interaction" not in submit
    assert submit["value"]["session_id"] == "sess1"
    cap = next(
        el["columns"][0]["elements"][0]
        for el in form["elements"]
        if el["tag"] == "column_set"
        and el["columns"][0]["elements"][0].get("name") == "capabilities"
    )
    assert cap["tag"] == "multi_select_static"


def test_field_help_text():
    assert "App ID" in field_help_text("target_app_id")
    assert "能力" in field_help_text("capabilities")


def test_should_start_onboarding_missing_fields():
    assert should_start_onboarding("不存在的Bot") is True
