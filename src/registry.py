"""Load bot registry and test case definitions."""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path

import yaml

from src.models import BotConfig, TestCaseDef
from src.test_defaults import merge_test_assets

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def _expand_env(value: str) -> str:
    if not isinstance(value, str):
        return value

    def repl(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), match.group(0))

    return re.sub(r"\$\{([^}]+)\}", repl, value)


def _expand_dict(obj: dict | list | str) -> dict | list | str:
    if isinstance(obj, dict):
        return {k: _expand_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_dict(v) for v in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _expand_dict(data)


def load_bots() -> list[BotConfig]:
    bots_path = CONFIG_DIR / "bots.yaml"
    if bots_path.exists():
        data = load_yaml(bots_path)
    else:
        data = {"bots": []}
    bots_list: list[dict] = list(data.get("bots", []))
    by_name = {item["name"]: idx for idx, item in enumerate(bots_list) if item.get("name")}

    registered_path = CONFIG_DIR / "bots_registered.yaml"
    if registered_path.exists():
        reg = load_yaml(registered_path)
        for item in reg.get("bots", []):
            name = item.get("name")
            if not name:
                continue
            if name in by_name:
                idx = by_name[name]
                bots_list[idx] = _merge_bot_dict(bots_list[idx], item)
            else:
                by_name[name] = len(bots_list)
                bots_list.append(item)
    return [_bot_from_item(item) for item in bots_list]


def _merge_bot_dict(base: dict, overlay: dict) -> dict:
    """Overlay bots_registered.yaml fields onto bots.yaml for the same name."""
    merged = dict(base)
    for key, value in overlay.items():
        if key == "name":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _apply_test_asset_defaults(bot: BotConfig) -> BotConfig:
    assets = merge_test_assets(bot.capabilities, bot.test_assets)
    if assets == bot.test_assets:
        return bot
    return replace(bot, test_assets=assets)


def _bot_from_item(item: dict) -> BotConfig:
    bot = BotConfig(
        name=item["name"],
        app_id=item.get("app_id", ""),
        owner=item.get("owner", ""),
        env=item.get("env", "staging"),
        target_app_id=item.get("target_app_id", item.get("app_id", "")),
        open_id=item.get("open_id", ""),
        chats=item.get("chats", {}),
        capabilities=item.get("capabilities", []),
        backend=item.get("backend", {}),
        test_assets=item.get("test_assets", {}),
        accounts=item.get("accounts", {}),
        feishu=item.get("feishu", {}),
    )
    return _apply_test_asset_defaults(bot)


def load_bot(name: str) -> BotConfig | None:
    for bot in load_bots():
        if bot.name == name:
            return bot
    return None


def load_test_cases(suite: str) -> list[TestCaseDef]:
    data = load_yaml(CONFIG_DIR / "test_cases.yaml")
    suite_data = data.get("suites", {}).get(suite)
    if not suite_data:
        return []

    cases = []
    for item in suite_data.get("cases", []):
        cases.append(
            TestCaseDef(
                id=item["id"],
                name=item["name"],
                section=item.get("section", suite),
                capabilities=item.get("capabilities", []),
                prompt=item.get("prompt", ""),
                channel=item.get("channel", "normal_group"),
                at_bot=item.get("at_bot", False),
                in_thread=item.get("in_thread", False),
                attach_doc=item.get("attach_doc", ""),
                attach_file=item.get("attach_file", ""),
                account=item.get("account", ""),
                burst_count=item.get("burst_count", 0),
                extra_text=item.get("extra_text", ""),
                repeat_extra=item.get("repeat_extra", 0),
                probe=item.get("probe", ""),
                report_section=item.get("report_section", ""),
                difficulty=item.get("difficulty", ""),
                assertions=item.get("assertions", []),
            )
        )
    return cases


def load_all_suites() -> dict[str, list[TestCaseDef]]:
    data = load_yaml(CONFIG_DIR / "test_cases.yaml")
    return {name: load_test_cases(name) for name in data.get("suites", {})}


def load_env_config() -> dict:
    return load_yaml(CONFIG_DIR / "environments.yaml")


def case_applicable(case: TestCaseDef, bot: BotConfig) -> bool:
    if not case.capabilities:
        return True
    return any(cap in bot.capabilities for cap in case.capabilities)
