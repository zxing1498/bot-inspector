"""Tests for onboarding mention parsing and auto-fill."""

from __future__ import annotations

from types import SimpleNamespace

from src.onboarding.cards import build_config_form_card
from src.onboarding.mentions import (
    MentionedBot,
    OnboardHints,
    is_inspector_mentioned,
    parse_message_mentions,
    pick_target_mention,
)
from src.onboarding.models import parse_capabilities


def _mention(name: str, open_id: str):
    return SimpleNamespace(
        name=name,
        id=SimpleNamespace(open_id=open_id),
    )


def test_parse_message_mentions_skips_inspector():
    mentions = [
        _mention("bot检查员", "ou_inspector"),
        _mention("demo-bot", "ou_target"),
    ]
    bots = parse_message_mentions(
        mentions,
        inspector_open_id="ou_inspector",
        inspector_names=("bot检查员",),
    )
    assert len(bots) == 1
    assert bots[0].name == "demo-bot"
    assert bots[0].open_id == "ou_target"


def test_is_inspector_mentioned_by_open_id():
    mentions = [_mention("bot检查员", "ou_inspector")]
    assert is_inspector_mentioned(
        mentions,
        inspector_open_id="ou_inspector",
        inspector_names=("bot检查员",),
    )


def test_is_inspector_mentioned_false_for_other_bot():
    mentions = [_mention("demo-bot", "ou_target")]
    assert not is_inspector_mentioned(
        mentions,
        inspector_open_id="ou_inspector",
        inspector_names=("bot检查员",),
    )


def test_pick_target_mention_by_bot_name():
    mentions = [MentionedBot(name="demo-bot", open_id="ou_abc")]
    picked = pick_target_mention(mentions, "demo-bot")
    assert picked is not None
    assert picked.open_id == "ou_abc"


def test_parse_capabilities_accepts_list():
    assert parse_capabilities(["messaging", "doc_access"]) == ["messaging", "doc_access"]


def test_parse_capabilities_defaults_all():
    assert len(parse_capabilities(None)) == 6


def test_config_card_defaults_all_capabilities():
    card = build_config_form_card("s1", "demo-bot", "oc_x", {})
    form = next(e for e in card["body"]["elements"] if e["tag"] == "form")
    cap = next(
        el["columns"][0]["elements"][0]
        for el in form["elements"]
        if el["tag"] == "column_set"
        and el["columns"][0]["elements"][0].get("name") == "capabilities"
    )
    assert set(cap["selected_values"]) == set(
        ["messaging", "topic_reply", "doc_access", "file_process", "card_reply", "export_file"]
    )


def test_config_card_has_suite_select():
    card = build_config_form_card("s1", "demo-bot", "oc_x", {"test_suite": "full"})
    form = next(e for e in card["body"]["elements"] if e["tag"] == "form")
    suite = next(
        el["columns"][0]["elements"][0]
        for el in form["elements"]
        if el["tag"] == "column_set"
        and el["columns"][0]["elements"][0].get("name") == "test_suite"
    )
    assert suite["tag"] == "select_static"
    assert suite["initial_option"] == "full"


def test_config_card_hides_app_id_when_hinted():
    hints = OnboardHints(app_id="cli_demo", open_id="ou_demo", normal_group="oc_x")
    card = build_config_form_card("s1", "demo-bot", "oc_x", {}, hints=hints)
    form = next(e for e in card["body"]["elements"] if e["tag"] == "form")
    names = []
    for el in form["elements"]:
        if el["tag"] == "column_set":
            inner = el["columns"][0]["elements"][0]
            if inner.get("name"):
                names.append(inner["name"])
    assert "target_app_id" not in names
    assert "capabilities" in names


def test_config_card_has_multiselect_capabilities():
    card = build_config_form_card("s1", "demo-bot", "oc_x", {})
    form = next(e for e in card["body"]["elements"] if e["tag"] == "form")
    cap = next(
        el["columns"][0]["elements"][0]
        for el in form["elements"]
        if el["tag"] == "column_set"
        and el["columns"][0]["elements"][0].get("name") == "capabilities"
    )
    assert cap["tag"] == "multi_select_static"
    assert len(cap["options"]) == 6
