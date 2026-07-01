"""Feishu interactive cards for bot onboarding."""

from __future__ import annotations

from typing import Any

from src.onboarding.mentions import OnboardHints
from src.onboarding.models import (
    ALL_CAPABILITIES,
    CAPABILITY_DESCRIPTIONS,
    CAPABILITY_OPTIONS,
    DEFAULT_DOC_DENIED,
    DEFAULT_DOC_PERMITTED,
    SUITE_HELP,
    SUITE_OPTIONS,
    ValidationReport,
)

ONBOARD_FIELD_SPECS: dict[str, dict[str, str]] = {
    "test_suite": {
        "label": "巡检级别",
        "hover": "P0=快验7项；Full=全部套件",
        "help": SUITE_HELP["p0"] + "\n\n" + SUITE_HELP["full"],
    },
    "target_app_id": {
        "label": "被测 Bot App ID",
        "placeholder": "cli_xxxxxxxx",
        "hover": "飞书开放平台 → 被测 Bot → 凭证与基础信息",
        "help": (
            "用途：标识被测 Bot 应用。\n"
            "自动：若 Inspector 有「获取应用信息」权限，会按 Bot 名称匹配；"
            "也可同时 @被测 Bot，自动填 open_id。\n"
            "手动：开放平台复制 App ID（cli_ 开头）。"
        ),
    },
    "capabilities": {
        "label": "Bot 具备的能力",
        "hover": "默认全选；若 Bot 不具备某项能力请取消勾选，避免误报",
        "help": (
            "默认勾选全部 6 项。若 Bot 实际不具备某能力，请取消对应项。\n"
            + "\n".join(f"· {v}" for v in CAPABILITY_DESCRIPTIONS.values())
            + "\n\n勾选「话题群回复」时，Inspector 将自动创建话题测试群并拉入 Bot。"
        ),
    },
    "health_url": {
        "label": "健康检查 URL（可选）",
        "placeholder": "http://gateway/ 留空跳过",
        "hover": "运维探针：检查 Bot 后端网关是否在线",
        "help": "长连接 Bot 可填 Gateway 根路径。无独立后端可留空。",
    },
    "doc_permitted": {
        "label": "有权限文档 URL（可选）",
        "placeholder": "留空则使用默认有权限测试文档",
        "hover": "测试账号有读权限的 Wiki/Doc 链接",
        "help": (
            "勾选 doc_access 时建议填写，用于验证 Bot 能读取有权限文档。\n"
            f"留空默认：{DEFAULT_DOC_PERMITTED}"
        ),
    },
    "doc_denied": {
        "label": "无权限文档 URL（可选）",
        "placeholder": "留空则使用默认无权限测试文档",
        "hover": "测试账号无读权限的文档链接",
        "help": (
            "勾选 doc_access 时建议填写，用于验证 Bot 不会泄露无权限内容。\n"
            f"留空默认：{DEFAULT_DOC_DENIED}"
        ),
    },
}


def field_help_text(field: str) -> str:
    spec = ONBOARD_FIELD_SPECS.get(field, {})
    return spec.get("help") or spec.get("hover") or field


def _plain(text: str) -> dict:
    return {"tag": "plain_text", "content": text}


def _callback_button(
    label: str,
    *,
    name: str,
    action: str,
    session_id: str,
    btn_type: str = "primary",
) -> dict:
    return {
        "tag": "button",
        "text": _plain(label),
        "type": btn_type,
        "name": name,
        "behaviors": [
            {
                "type": "callback",
                "value": {"action": action, "session_id": session_id},
            }
        ],
    }


def _help_button(field: str) -> dict:
    spec = ONBOARD_FIELD_SPECS[field]
    return {
        "tag": "button",
        "name": f"help_{field}",
        "type": "text",
        "size": "tiny",
        "icon": {"tag": "standard_icon", "token": "info_outlined", "color": "grey"},
        "text": _plain("?"),
        "hover_tips": _plain(spec["hover"]),
        "behaviors": [
            {"type": "callback", "value": {"action": "show_help", "field": field}},
        ],
    }


def _field_row(field: str, element: dict) -> dict:
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "small",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [element],
            },
            {
                "tag": "column",
                "width": "auto",
                "vertical_align": "top",
                "elements": [_help_button(field)],
            },
        ],
    }


def _input_field(
    name: str,
    *,
    default: str = "",
    required: bool = False,
) -> dict:
    spec = ONBOARD_FIELD_SPECS[name]
    label = spec["label"] + (" *" if required else "")
    return {
        "tag": "input",
        "name": name,
        "required": required,
        "placeholder": _plain(spec.get("placeholder", "")),
        "default_value": default,
        "label": _plain(label),
    }


def _capabilities_multiselect(selected: list[str] | None = None) -> dict:
    selected = selected or list(ALL_CAPABILITIES)
    return {
        "tag": "multi_select_static",
        "name": "capabilities",
        "required": True,
        "placeholder": _plain("Bot 能力（默认全选；不具备的项请取消勾选）"),
        "selected_values": [c for c in selected if c in CAPABILITY_OPTIONS] or list(ALL_CAPABILITIES),
        "options": [
            {"text": _plain(CAPABILITY_DESCRIPTIONS[key]), "value": key}
            for key in CAPABILITY_OPTIONS
        ],
    }


def _suite_select(default_suite: str = "p0") -> dict:
    default_suite = "full" if default_suite in ("full", "api") else "p0"
    return {
        "tag": "select_static",
        "name": "test_suite",
        "required": True,
        "placeholder": _plain("选择巡检级别（P0 快验 / Full 全面）"),
        "initial_option": default_suite,
        "options": [
            {"text": _plain(SUITE_OPTIONS["p0"]), "value": "p0"},
            {"text": _plain(SUITE_OPTIONS["full"]), "value": "full"},
        ],
    }


def _auto_detected_div(hints: OnboardHints | None) -> dict:
    lines = [
        "【已自动识别】",
        "· 普通测试群 = 当前群",
        "· 勾选「话题群回复」→ 自动创建话题测试群并拉入 Bot",
    ]
    if hints and hints.summary_lines():
        for item in hints.summary_lines():
            if "普通测试群" not in item:
                lines.append(f"· {item}")
    else:
        lines.append("· 推荐同时 @被测 Bot → 自动识别 open_id")
    lines.extend(
        [
            "",
            "【你需要确认/补充】",
            "1. 巡检级别：P0（快验）或 Full（全面）",
            "2. 能力模块：默认全选，不具备的请取消",
            "3. App ID：未自动匹配时需手动填写",
            "4. 高级可选项：健康检查 URL、文档链接（可留空）",
            "",
            "字段旁 ? 可查看详细说明。",
        ]
    )
    return {"tag": "div", "text": _plain("\n".join(lines))}


def build_config_form_card(
    session_id: str,
    bot_name: str,
    chat_id: str,
    defaults: dict[str, str] | None = None,
    *,
    hints: OnboardHints | None = None,
    reconfigure: bool = False,
) -> dict[str, Any]:
    defaults = defaults or {}
    selected_caps = [
        c.strip()
        for c in defaults.get("capabilities", ",".join(ALL_CAPABILITIES)).replace("，", ",").split(",")
        if c.strip()
    ] or list(ALL_CAPABILITIES)
    default_suite = defaults.get("test_suite", "p0")

    form_elements: list[dict[str, Any]] = [
        _field_row("test_suite", _suite_select(default_suite)),
    ]

    if hints and hints.app_id:
        pass  # 提交时由 session hints 合并，无需用户填写
    elif defaults.get("target_app_id"):
        form_elements.append(
            _field_row(
                "target_app_id",
                _input_field("target_app_id", default=defaults["target_app_id"], required=True),
            )
        )
    else:
        form_elements.append(
            _field_row(
                "target_app_id",
                _input_field("target_app_id", required=True),
            )
        )

    form_elements.append(_field_row("capabilities", _capabilities_multiselect(selected_caps)))
    form_elements.append(
        _field_row(
            "health_url",
            _input_field("health_url", default=defaults.get("health_url", "")),
        )
    )
    form_elements.append(
        _field_row(
            "doc_permitted",
            _input_field("doc_permitted", default=defaults.get("doc_permitted", "")),
        )
    )
    form_elements.append(
        _field_row(
            "doc_denied",
            _input_field("doc_denied", default=defaults.get("doc_denied", "")),
        )
    )
    form_elements.append(
        {
            "tag": "button",
            "text": _plain("提交并校验"),
            "type": "primary",
            "action_type": "form_submit",
            "name": "submit_config",
            "value": {"action": "submit_config", "session_id": session_id},
        }
    )

    title = f"修改配置：{bot_name}" if reconfigure else f"配置被测 Bot：{bot_name}"
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": _plain(title),
            "template": "blue",
        },
        "body": {
            "elements": [
                _auto_detected_div(hints),
                {"tag": "form", "name": "bot_onboard_form", "elements": form_elements},
            ],
        },
    }


def build_validation_result_card(
    session_id: str,
    bot_name: str,
    report: ValidationReport,
    *,
    register_only: bool = False,
    reconfigure: bool = False,
    suite: str = "p0",
) -> dict[str, Any]:
    lines = []
    for check in report.checks:
        if check.ok:
            mark = "✅"
        elif check.blocking:
            mark = "❌"
        else:
            mark = "⚠️"
        line = f"{mark} {check.name}：{check.message}"
        if check.user_action and not check.ok:
            line += f"\n   → {check.user_action}"
        lines.append(line)

    elements: list[dict[str, Any]] = [{"tag": "div", "text": _plain("\n".join(lines))}]

    if report.ok and report.warnings:
        elements.append(
            {
                "tag": "div",
                "text": _plain(
                    "以上 ⚠️ 项不影响继续巡检；私聊相关用例可能无法执行或标记为不通过。"
                ),
            }
        )

    save_only = register_only or reconfigure
    if report.ok:
        suite_label = "FULL" if suite == "full" else "P0"
        btn_label = "保存配置" if save_only else f"确认有效，开始 {suite_label} 巡检"
        elements.append(
            _callback_button(
                btn_label,
                name="start_inspection",
                action="start_inspection",
                session_id=session_id,
                btn_type="primary",
            )
        )
    else:
        elements.append(
            _callback_button(
                "修改配置",
                name="edit_config",
                action="edit_config",
                session_id=session_id,
                btn_type="default",
            )
        )
        confirm_hint = f"确认配置 {bot_name}" if save_only else f"确认测试 {bot_name}"
        elements.append(
            {
                "tag": "div",
                "text": _plain(
                    "请按上方提示完成操作后，点击「修改配置」更新表单，"
                    f"或在群里发送：{confirm_hint}"
                ),
            }
        )

    template = "green" if report.ok else "red"
    if report.ok and report.warnings:
        title = "校验通过（有提示项），可以开始巡检" if not save_only else "校验通过（有提示项），可以保存"
    elif report.ok:
        title = "校验通过，配置已可保存" if save_only else "校验通过，可以开始巡检"
    else:
        title = "校验未通过，请补充或修正"

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {"title": _plain(title), "template": template},
        "body": {"elements": elements},
    }


def text_form_fallback(
    bot_name: str,
    chat_id: str,
    defaults: dict[str, str] | None = None,
    *,
    hints: OnboardHints | None = None,
) -> str:
    defaults = defaults or {}
    cap_lines = "\n".join(f"  - {k}: {v}" for k, v in CAPABILITY_DESCRIPTIONS.items())
    auto = ""
    if hints and hints.summary_lines():
        auto = "\n已自动识别：\n" + "\n".join(f"- {x}" for x in hints.summary_lines()) + "\n"
    return f"""【配置被测 Bot：{bot_name}】

当前测试群 chat_id：{chat_id}
{auto}
推荐：@bot检查员 @被测Bot 测试 {bot_name}

若未弹出配置卡片，请复制以下模板填写后发送（每行一项）：

app_id: {defaults.get('target_app_id') or (hints.app_id if hints else '') or 'cli_'}
open_id: {defaults.get('open_id') or (hints.open_id if hints else '') or 'ou_'}
capabilities: {defaults.get('capabilities', ','.join(ALL_CAPABILITIES))}
test_suite: {defaults.get('test_suite', 'p0')}
health_url: {defaults.get('health_url', '')}
doc_permitted: {defaults.get('doc_permitted') or DEFAULT_DOC_PERMITTED}
doc_denied: {defaults.get('doc_denied') or DEFAULT_DOC_DENIED}

能力说明：
{cap_lines}

填写后发送「提交配置」或再次 @我 测试 {bot_name}"""


def parse_text_form_submission(text: str) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("【") or line.startswith("-"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
        elif "：" in line:
            key, _, value = line.partition("：")
            fields[key.strip().lower()] = value.strip()
    if not fields:
        return None
    mapping = {
        "app_id": "target_app_id",
        "target_app_id": "target_app_id",
        "open_id": "open_id",
        "owner": "owner",
        "capabilities": "capabilities",
        "test_suite": "test_suite",
        "suite": "test_suite",
        "health_url": "health_url",
        "topic_group": "topic_group",
        "doc_permitted": "doc_permitted",
        "doc_denied": "doc_denied",
    }
    normalized: dict[str, str] = {}
    for key, value in fields.items():
        norm = mapping.get(key, key)
        normalized[norm] = value
    if normalized.get("target_app_id") or normalized.get("open_id"):
        return normalized
    return None
