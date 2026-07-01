"""Tests for prompt placeholder defaults."""

from src.models import BotConfig
from src.registry import _apply_test_asset_defaults
from src.test_defaults import (
    merge_test_assets,
    resolve_prompt_template,
    unresolved_placeholders,
)


def test_merge_ignores_empty_bot_override():
    assets = merge_test_assets(
        ["messaging"],
        {"slow_trigger": "", "export_trigger": "  "},
    )
    assert assets["slow_trigger"]
    assert "{" not in assets["slow_trigger"]


def test_resolve_slow_trigger():
    variables = merge_test_assets(["messaging"], {})
    prompt, unresolved = resolve_prompt_template("{slow_trigger}", variables)
    assert not unresolved
    assert "{" not in prompt
    assert len(prompt) > 10


def test_resolve_doc_permitted_in_prompt():
    variables = merge_test_assets(["doc_access"], {})
    prompt, unresolved = resolve_prompt_template("读取文档 {doc_permitted}", variables)
    assert not unresolved
    assert prompt.startswith("读取文档 https://")


def test_unresolved_detected():
    _, unresolved = resolve_prompt_template("{unknown_var}", {"slow_trigger": "ok"})
    assert unresolved == ["unknown_var"]


def test_resolve_topic_prompts():
    variables = merge_test_assets(["topic_reply", "export_file"], {})
    prompt, unresolved = resolve_prompt_template("{topic_kb_md_prompt}", variables)
    assert not unresolved
    assert "kb" in prompt.lower() or "KB" in prompt or "知识" in prompt

    prompt2, unresolved2 = resolve_prompt_template(
        "{topic_weather_image_prompt}", variables
    )
    assert not unresolved2
    assert "天气" in prompt2
    assert "图片" in prompt2


def test_resolve_cross_group_probe():
    variables = merge_test_assets(["messaging"], {})
    prompt, unresolved = resolve_prompt_template("{cross_group_probe}", variables)
    assert not unresolved
    assert "文档" in prompt or "多维表格" in prompt


def test_demo_bot_config_resolves_test_assets():
    bot = BotConfig(
        name="demo-bot",
        app_id="cli_x",
        owner="",
        env="staging",
        capabilities=["messaging", "doc_access"],
        test_assets={"slow_trigger": "自定义慢任务话术"},
    )
    bot = _apply_test_asset_defaults(bot)
    assert bot.test_assets["slow_trigger"] == "自定义慢任务话术"
    assert "{" not in bot.test_assets["slow_trigger"]
    assert bot.test_assets.get("doc_permitted", "").startswith("https://")
