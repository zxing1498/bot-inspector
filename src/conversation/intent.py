"""Classify user messages for conversational vs execute intents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.conversation.session import ChatSession
from src.registry import load_all_suites, load_bots


class Intent(str, Enum):
    EXECUTE = "execute"
    EXPLAIN = "explain"
    ADVISE = "advise"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dataclass
class ExplainQuery:
    case_id: str = ""
    issue_id: str = ""
    bot_name: str = ""
    case_name_hint: str = ""
    raw_text: str = ""


EXPLAIN_MARKERS = (
    "解释",
    "为什么",
    "怎么回事",
    "怎么失败",
    "判错",
    "判断错",
    "判断为不通过",
    "误判",
    "怎么测",
    "检测标准",
    "判据",
    "这项",
    "那条",
    "上次巡检",
    "上次结果",
    "报告里",
    "有正常回复",
    "正常回复",
)

ADVISE_MARKERS = (
    "建议",
    "应该测",
    "应该检测",
    "应该检查",
    "改进检测",
    "改进判据",
    "换个文档",
    "换用例",
    "不应该判",
    "算通过",
)

CHAT_MARKERS = (
    "你好",
    "谢谢",
    "辛苦了",
    "在吗",
    "你是谁",
    "介绍一下",
)

CASE_ID_RE = re.compile(r"\b(p0_[a-z0-9_]+|[a-z]+_[a-z0-9_]+)\b", re.IGNORECASE)
ISSUE_ID_RE = re.compile(r"ISS-(\d+)", re.IGNORECASE)
EXPLAIN_CMD_RE = re.compile(r"^(?:解释|说明)\s*(.*)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    text = re.sub(r"@_user_\d+", "", text)
    text = re.sub(r"@[^\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _known_bot_names() -> list[str]:
    return [b.name for b in load_bots()]


def _match_bot_name(text: str) -> str:
    lowered = text.casefold()
    for name in sorted(_known_bot_names(), key=len, reverse=True):
        if name.casefold() in lowered:
            return name
    return ""


def _match_case_from_registry(normalized: str) -> tuple[str, str]:
    for cases in load_all_suites().values():
        for case in cases:
            if case.name and case.name in normalized:
                return case.id, case.name
    return "", ""


def parse_explain_query(text: str, session: ChatSession | None = None) -> ExplainQuery | None:
    normalized = _normalize(text)
    if not normalized:
        return None

    lowered = normalized.casefold()
    has_marker = any(m in normalized for m in EXPLAIN_MARKERS)
    cmd_match = EXPLAIN_CMD_RE.match(normalized)
    if cmd_match:
        has_marker = True
        normalized = cmd_match.group(1).strip() or normalized
        lowered = normalized.casefold()

    issue_match = ISSUE_ID_RE.search(normalized)
    case_match = CASE_ID_RE.search(normalized)
    if not has_marker and not issue_match and not case_match:
        return None

    query = ExplainQuery(raw_text=text)
    if issue_match:
        query.issue_id = f"ISS-{issue_match.group(1).zfill(3)}"

    if case_match:
        query.case_id = case_match.group(1).lower()

    query.bot_name = _match_bot_name(normalized)
    if not query.bot_name and session and session.last_inspection:
        query.bot_name = session.last_inspection.bot_name

    # try match case name from failed cases in session
    if session and session.last_inspection and not query.case_id:
        for case in session.last_inspection.failed_cases:
            if case.case_name and case.case_name in normalized:
                query.case_id = case.case_id
                query.case_name_hint = case.case_name
                break
            if case.issue_id and query.issue_id and case.issue_id.upper() == query.issue_id.upper():
                query.case_id = case.case_id
                break

    if "无权限" in normalized or "doc_denied" in lowered or "p0_doc_denied" in lowered:
        query.case_id = query.case_id or "p0_doc_denied"
    if "有权限" in normalized and "文档" in normalized:
        query.case_id = query.case_id or "p0_doc_access"
    if "话题" in normalized and "回复" in normalized:
        query.case_id = query.case_id or "p0_topic_reply"
    if "目标群" in normalized and "回复" in normalized:
        query.case_id = query.case_id or "p0_group_reply"

    if not query.case_id:
        cid, cname = _match_case_from_registry(normalized)
        if cid:
            query.case_id = cid
            query.case_name_hint = cname

    return query if (has_marker or query.case_id or query.issue_id) else None


def classify_intent(text: str, session: ChatSession | None = None) -> Intent:
    normalized = _normalize(text)
    if not normalized:
        return Intent.UNKNOWN

    if parse_explain_query(text, session):
        return Intent.EXPLAIN

    if any(m in normalized for m in ADVISE_MARKERS):
        return Intent.ADVISE

    if any(m in normalized for m in CHAT_MARKERS):
        return Intent.CHAT

    # follow-up without explicit marker within session window
    if session and session.last_inspection:
        follow_markers = ("那项", "这个", "刚才", "它", "为啥", "对吗", "是不是")
        if any(m in normalized for m in follow_markers) and len(normalized) < 80:
            return Intent.EXPLAIN

    if len(normalized) < 40 and not re.match(
        r"^(?:巡检|测试|注册|暂停|停止|中断|/inspect)", normalized, re.IGNORECASE
    ):
        return Intent.CHAT

    return Intent.UNKNOWN
