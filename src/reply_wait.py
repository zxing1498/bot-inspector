"""Detect final bot replies (e.g. Hermes「已完成」cards) vs in-progress status."""

from __future__ import annotations

import json
import re
from typing import Any

from src.models import ReplyInfo

IN_PROGRESS_RE = re.compile(
    r"思考中|正在思考|生成中|Generating|Interrupting|iteration\s+\d+/\d+",
    re.IGNORECASE,
)
COMPLETION_RE = re.compile(r"已完成|Completed", re.IGNORECASE)
CARD_FOOTER_RE = re.compile(
    r"gpt-\d|~/workspace|codex-pilot|·\s*out\s+\d+\s*·\s*in",
    re.IGNORECASE,
)


def card_elements(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Support standard Feishu cards and codex-pilot style `body.elements`."""
    elements = card.get("elements")
    if isinstance(elements, list) and elements:
        return [e for e in elements if isinstance(e, dict)]
    body = card.get("body")
    if isinstance(body, dict):
        nested = body.get("elements")
        if isinstance(nested, list):
            return [e for e in nested if isinstance(e, dict)]
    return []


def interactive_primary_text(card: dict[str, Any]) -> str:
    texts: list[str] = []
    for element in card_elements(card):
        for key in ("content", "text"):
            value = element.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    primary = [
        text
        for text in texts
        if text not in {"---", "—"} and not CARD_FOOTER_RE.search(text)
    ]
    return "\n".join(primary).strip()


def is_in_progress_reply(reply: ReplyInfo) -> bool:
    text = reply.content or ""
    if not text.strip():
        return False
    if COMPLETION_RE.search(text):
        return False
    if reply.msg_type == "interactive":
        try:
            card = json.loads(text)
            primary = interactive_primary_text(card)
            if primary:
                return bool(IN_PROGRESS_RE.search(primary))
        except json.JSONDecodeError:
            pass
    return bool(IN_PROGRESS_RE.search(text))


def is_completion_reply(reply: ReplyInfo) -> bool:
    """True when the bot appears to have finished the current turn."""
    text = reply.content or ""
    if not text.strip():
        return False

    if COMPLETION_RE.search(text):
        return True

    if is_in_progress_reply(reply):
        return False

    if reply.msg_type == "text" and len(text.strip()) >= 2:
        return True

    if reply.msg_type == "interactive":
        try:
            card = json.loads(text)
        except json.JSONDecodeError:
            return len(text.strip()) > 20

        header = card.get("header") or {}
        title = header.get("title") or {}
        title_text = ""
        if isinstance(title, dict):
            title_text = str(title.get("content", ""))
        elif isinstance(title, str):
            title_text = title
        if COMPLETION_RE.search(title_text):
            return True

        primary = interactive_primary_text(card)
        if primary and not IN_PROGRESS_RE.search(primary):
            return True

        elements = card_elements(card)
        body = json.dumps(elements, ensure_ascii=False)
        if len(body) > 80 and not IN_PROGRESS_RE.search(body):
            return True

    if reply.msg_type in ("file", "image", "media"):
        return True

    return False


def pick_final_replies(replies: list[ReplyInfo]) -> list[ReplyInfo]:
    """Prefer completion replies; fall back to the latest non-progress reply."""
    if not replies:
        return []
    completed = [r for r in replies if is_completion_reply(r)]
    if completed:
        return completed
    non_progress = [r for r in replies if not is_in_progress_reply(r)]
    if non_progress:
        return [non_progress[-1]]
    return []
