"""Map internal exceptions to user-facing report messages."""

from __future__ import annotations

import re

# Patterns that should never appear verbatim in acceptance reports.
_TECHNICAL_MARKERS = (
    "unsupported operand",
    "Traceback (most recent call last)",
    'File "',
    "TypeError:",
    "AttributeError:",
    "KeyError:",
    "IndexError:",
    "NameError:",
    "WindowsPath",
)


def is_technical_message(text: str) -> bool:
    if not text or not text.strip():
        return False
    return any(marker in text for marker in _TECHNICAL_MARKERS)


def humanize_error(exc: BaseException) -> str:
    """Return a concise, non-technical message suitable for acceptance reports."""
    raw = str(exc).strip()
    name = type(exc).__name__

    if "WindowsPath" in raw and "dict" in raw:
        return "测试附件路径配置有误，Inspector 无法读取文件（请检查 file_assets 配置）"

    if name == "FileNotFoundError" or "No such file or directory" in raw:
        return "测试附件文件不存在，无法继续该项检查"

    if raw.startswith("Feishu HTTP"):
        return raw

    if name in ("TimeoutError", "ReadTimeout", "ConnectTimeout") or "timeout" in raw.lower():
        return "请求超时，未能完成该项检查"

    if name in ("TypeError", "AttributeError", "KeyError", "IndexError", "NameError", "ValueError"):
        return "巡检程序执行异常，该项未能完成（非被测 Bot 问题）"

    if is_technical_message(raw):
        return "巡检程序执行异常，该项未能完成（非被测 Bot 问题）"

    if len(raw) > 200:
        return raw[:200] + "…"

    return raw or "巡检执行失败（未知原因）"


def sanitize_report_text(text: str) -> str:
    """Sanitize text already stored on a result (e.g. legacy reports)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    if is_technical_message(cleaned):
        return humanize_error(Exception(cleaned))
    return cleaned
