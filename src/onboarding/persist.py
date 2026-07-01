"""Persist dynamically registered bots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.models import BotConfig
from src.onboarding.models import ALL_CAPABILITIES
from src.registry import CONFIG_DIR

REGISTERED_PATH = CONFIG_DIR / "bots_registered.yaml"


def bot_to_dict(bot: BotConfig) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": bot.name,
        "app_id": bot.app_id,
        "target_app_id": bot.target_app_id or bot.app_id,
        "open_id": bot.open_id,
        "owner": bot.owner,
        "env": bot.env,
        "chats": dict(bot.chats),
        "capabilities": list(bot.capabilities),
    }
    if bot.backend:
        item["backend"] = {
            k: v for k, v in bot.backend.items() if not str(k).startswith("_")
        }
    if bot.test_assets:
        item["test_assets"] = bot.test_assets
    if bot.accounts:
        item["accounts"] = bot.accounts
    if bot.feishu:
        item["feishu"] = bot.feishu
    return item


def _load_registered_raw() -> dict[str, Any]:
    if not REGISTERED_PATH.exists():
        return {"bots": []}
    with open(REGISTERED_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"bots": []}


def upsert_registered_bot(bot: BotConfig) -> Path:
    data = _load_registered_raw()
    bots: list[dict[str, Any]] = list(data.get("bots", []))
    item = bot_to_dict(bot)
    for idx, existing in enumerate(bots):
        if existing.get("name") == bot.name:
            bots[idx] = item
            break
    else:
        bots.append(item)
    data["bots"] = bots
    REGISTERED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTERED_PATH, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    return REGISTERED_PATH


def defaults_from_bot(bot: BotConfig | None) -> dict[str, str]:
    if not bot:
        return {}
    return {
        "target_app_id": bot.target_app_id or bot.app_id,
        "open_id": bot.open_id,
        "owner": bot.owner,
        "capabilities": ",".join(bot.capabilities) if bot.capabilities else ",".join(ALL_CAPABILITIES),
        "test_suite": "p0",
        "health_url": bot.backend.get("health_url", ""),
        "topic_group": bot.chats.get("topic_group", ""),
        "doc_permitted": bot.test_assets.get("doc_permitted", ""),
        "doc_denied": bot.test_assets.get("doc_denied", ""),
    }
