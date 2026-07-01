"""Feishu interactive cards for conversational explain/advise replies."""

from __future__ import annotations

from typing import Any

from src.conversation.session import CaseSnapshot

_STATUS_TEMPLATE = {
    "通过": "green",
    "不通过": "red",
    "待整改": "yellow",
    "待人工确认": "blue",
    "待确认权限": "grey",
    "不适用": "grey",
}

_MODE_TITLE = {
    "explain": "巡检解读",
    "advise": "检测建议",
    "chat": "巡检问答",
}


def _plain(text: str) -> dict[str, Any]:
    return {"tag": "plain_text", "content": text}


def _header_template(status: str) -> str:
    return _STATUS_TEMPLATE.get(status, "blue")


def build_explain_card(
    body_markdown: str,
    *,
    mode: str = "explain",
    case: CaseSnapshot | None = None,
) -> dict[str, Any]:
    """Wrap explain/advise reply in Schema 2.0 card for readable layout in Feishu."""
    if case and case.case_id:
        title = f"{_MODE_TITLE.get(mode, '巡检解读')} · {case.case_id}"
        subtitle = case.case_name[:80]
        template = _header_template(case.status)
    else:
        title = _MODE_TITLE.get(mode, "巡检解读")
        subtitle = ""
        template = "blue"

    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": body_markdown[:7800]},
    ]
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": _plain(title),
            "subtitle": _plain(subtitle),
            "template": template,
        },
        "body": {"elements": elements},
    }
