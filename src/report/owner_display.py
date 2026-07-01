"""Resolve report owner for human-readable display."""

from __future__ import annotations

import os
import re

from src.feishu.client import FeishuClient

_OPEN_ID_RE = re.compile(r"^ou_[a-z0-9]+$", re.IGNORECASE)
_FALLBACK_OWNER_RE = re.compile(r"^飞书用户[（(](ou_[a-z0-9]+)")


def _feishu_client_optional() -> FeishuClient | None:
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return None
    try:
        return FeishuClient(app_id, app_secret)
    except Exception:
        return None


def is_open_id(value: str) -> bool:
    return bool(_OPEN_ID_RE.match((value or "").strip()))


def _extract_open_id_prefix(value: str) -> str:
    text = (value or "").strip()
    if is_open_id(text):
        return text
    match = _FALLBACK_OWNER_RE.match(text)
    if match:
        return match.group(1)
    return ""


def _resolve_name_from_chat_members(
    client: FeishuClient, open_id: str, *, chat_id: str
) -> str:
    if not open_id or not chat_id:
        return ""
    try:
        for member in client.list_chat_members(chat_id):
            member_id = member.get("member_id", "")
            if member_id == open_id or (
                len(open_id) >= 10 and member_id.startswith(open_id)
            ):
                name = member.get("name", "")
                if name:
                    return name
    except Exception:
        pass
    return ""


def format_owner_display(
    owner: str, client: FeishuClient | None = None, *, chat_id: str = ""
) -> str:
    """Show Feishu display name when owner is an open_id."""
    text = (owner or "").strip()
    if not text:
        return "未配置"
    if not is_open_id(text):
        return text

    client = client or _feishu_client_optional()
    if client:
        name = client.get_user_name(text, chat_id=chat_id)
        if name:
            return name
        prefix = _extract_open_id_prefix(text)
        if prefix and chat_id:
            name = _resolve_name_from_chat_members(client, prefix, chat_id=chat_id)
            if name:
                return name

    if _FALLBACK_OWNER_RE.match(text):
        return text
    return f"飞书用户（{text[:10]}…）" if is_open_id(text) else text


def resolve_report_owner(
    *,
    triggered_by: str = "",
    triggered_by_open_id: str = "",
    bot_owner: str = "",
    client: FeishuClient | None = None,
    chat_id: str = "",
) -> str:
    """Pick report owner: trigger display name > resolved open_id > bots.yaml owner."""
    client = client or _feishu_client_optional()

    name = (triggered_by or "").strip()
    if name and not is_open_id(name):
        return name

    for candidate in (triggered_by_open_id, triggered_by, bot_owner):
        oid = (candidate or "").strip()
        if not oid:
            continue
        if is_open_id(oid) and client:
            resolved = client.get_user_name(oid, chat_id=chat_id)
            if resolved:
                return resolved
        if oid and not is_open_id(oid):
            return oid

    oid = (triggered_by_open_id or triggered_by or bot_owner or "").strip()
    return format_owner_display(oid, client, chat_id=chat_id) if oid else ""


def resolve_report_owner_display(
    report,
    client: FeishuClient | None = None,
) -> str:
    """Resolve owner label for report rendering (supports stored open_id + chat)."""
    from src.models import BotRunReport

    if not isinstance(report, BotRunReport):
        return format_owner_display(str(report or ""), client)

    owner = (report.owner or "").strip()
    open_id = (report.owner_open_id or "").strip()
    chat_id = (report.trigger_chat_id or "").strip()

    if owner and not is_open_id(owner) and not _FALLBACK_OWNER_RE.match(owner):
        return owner

    if not open_id:
        open_id = _extract_open_id_prefix(owner) or (
            owner if is_open_id(owner) else ""
        )

    return resolve_report_owner(
        triggered_by_open_id=open_id,
        bot_owner=owner if is_open_id(owner) else "",
        client=client,
        chat_id=chat_id,
    ) or owner or "未配置"
