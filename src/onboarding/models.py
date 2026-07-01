"""Onboarding session and validation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.models import BotConfig


from src.onboarding.mentions import OnboardHints
from src.test_defaults import load_project_defaults

_project = load_project_defaults()


class OnboardPhase(str, Enum):
    FORM = "form"
    VALIDATING = "validating"
    AWAITING_FIX = "awaiting_fix"
    READY = "ready"
    RUNNING = "running"


CAPABILITY_OPTIONS = {
    "messaging": "基础消息收发",
    "topic_reply": "话题群内回复",
    "doc_access": "飞书文档访问",
    "file_process": "群文件处理",
    "card_reply": "卡片消息回复",
    "export_file": "导出/发送文件",
}

# 多选下拉展示：名称 + 一句话说明 + 对应测试内容
CAPABILITY_DESCRIPTIONS = {
    "messaging": "基础消息收发 — 群聊能否正常收消息、回消息（P0 必测）",
    "topic_reply": "话题群回复 — 在话题群内 @Bot 后，回复是否落在同一条话题下",
    "doc_access": "文档访问 — 发送有/无权限的飞书文档链接，检查读取与越权",
    "file_process": "文件处理 — 群里上传 txt/pdf 等文件，检查 Bot 能否接收并处理",
    "card_reply": "卡片消息 — Bot 能否返回合法的飞书 interactive 卡片",
    "export_file": "导出文件 — 触发导出指令后，Bot 能否回传文件或下载链接",
}

ALL_CAPABILITIES = list(CAPABILITY_OPTIONS.keys())

DEFAULT_DOC_PERMITTED = _project["doc_permitted"]
DEFAULT_DOC_DENIED = _project["doc_denied"]
DEFAULT_EXPORT_TRIGGER = _project["export_trigger"]
DEFAULT_SLOW_TRIGGER = _project["slow_trigger"]


def resolve_doc_test_assets(
    capabilities: list[str],
    form: dict[str, Any],
) -> dict[str, str]:
    """Apply default doc URLs when doc_access is enabled and fields are empty."""
    if "doc_access" not in capabilities:
        return {}
    permitted = (form.get("doc_permitted") or "").strip()
    denied = (form.get("doc_denied") or "").strip()
    return {
        "doc_permitted": permitted or DEFAULT_DOC_PERMITTED,
        "doc_denied": denied or DEFAULT_DOC_DENIED,
    }

SUITE_OPTIONS = {
    "p0": "P0 必测 — 7 项核心验收（约 20~90 分钟），适合首次接入 / 发版前快验",
    "full": "Full 完整 — P0 + 文档/文件/运维/安全/配置等全部套件，用例更多、耗时更长",
}

SUITE_HELP = {
    "p0": (
        "P0 必测包含 7 项核心用例：群聊 @ 回复、话题回复、文档访问、文件处理、无效指令兜底、复杂请求首响等。\n"
        "适合 Bot 刚接入或日常快速验收，通常 20~90 分钟完成。"
    ),
    "full": (
        "Full = P0 + messaging/docs/files/ops/security/config 全部扩展套件。\n"
        "适合发版前全面回归，用例显著多于 P0，请预留更长时间。"
    ),
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    user_action: str = ""
    blocking: bool = True


@dataclass
class ValidationReport:
    ok: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def blockers(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and c.blocking]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and not c.blocking]


@dataclass
class OnboardingSession:
    session_id: str
    bot_name: str
    chat_id: str
    operator_open_id: str
    suite: str = "p0"
    register_only: bool = False
    reconfigure: bool = False
    phase: OnboardPhase = OnboardPhase.FORM
    draft: BotConfig | None = None
    last_validation: ValidationReport | None = None
    hints: OnboardHints | None = None

    def session_key(self) -> str:
        return f"{self.chat_id}:{self.operator_open_id}"


def parse_capabilities(raw: str | list[Any] | None) -> list[str]:
    if raw is None:
        return list(ALL_CAPABILITIES)
    if isinstance(raw, list):
        caps = [str(x).strip() for x in raw if str(x).strip() in CAPABILITY_OPTIONS]
        return caps or list(ALL_CAPABILITIES)
    if not str(raw).strip():
        return list(ALL_CAPABILITIES)
    caps = []
    for part in str(raw).replace("，", ",").split(","):
        key = part.strip()
        if key and key in CAPABILITY_OPTIONS:
            caps.append(key)
    return caps or list(ALL_CAPABILITIES)


def parse_suite(raw: Any, *, default: str = "p0") -> str:
    value = str(raw or default).strip().lower()
    if value in ("full", "api"):
        return "full"
    return "p0"


def bot_from_form(
    bot_name: str,
    chat_id: str,
    form: dict[str, Any],
    *,
    owner_fallback: str = "",
) -> BotConfig:
    app_id = (form.get("target_app_id") or form.get("app_id") or "").strip()
    open_id = (form.get("open_id") or "").strip()
    owner = (form.get("owner") or owner_fallback or "").strip()
    health_url = (form.get("health_url") or "").strip()
    callback_url = (form.get("callback_url") or health_url).strip()
    topic_group = (form.get("topic_group") or "").strip()
    capabilities = parse_capabilities(form.get("capabilities"))

    chats: dict[str, str] = {"normal_group": chat_id}
    if topic_group:
        chats["topic_group"] = topic_group

    test_assets = resolve_doc_test_assets(capabilities, form)

    backend: dict[str, Any] = {}
    if health_url:
        backend["health_url"] = health_url
    if callback_url:
        backend["callback_url"] = callback_url
    if not backend.get("log_query"):
        backend["log_query"] = {"type": "skip", "trace_field": "request_id"}
    if "topic_reply" in capabilities:
        backend["_auto_create_topic"] = True

    return BotConfig(
        name=bot_name,
        app_id=app_id,
        target_app_id=app_id,
        open_id=open_id,
        owner=owner,
        env=(form.get("env") or "staging").strip() or "staging",
        chats=chats,
        capabilities=capabilities,
        backend=backend,
        test_assets=test_assets,
    )
