"""Orchestrate conversational interactions."""

from __future__ import annotations

import logging
import threading

from src.conversation.cards import build_explain_card
from src.conversation.explainer import build_explain_facts, render_template_reply
from src.conversation.intent import ExplainQuery, Intent, classify_intent, parse_explain_query
from src.conversation.llm import generate_reply, is_llm_enabled
from src.conversation.report_store import snapshot_from_report
from src.conversation.session import SessionStore
from src.models import BotRunReport
from src.report.generator import ReportPaths

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, *, reply_fn, send_card_fn=None) -> None:
        self._reply = reply_fn
        self._send_card = send_card_fn
        self._sessions = SessionStore()
        self._lock = threading.Lock()

    def record_inspection(
        self,
        chat_id: str,
        operator_open_id: str,
        report: BotRunReport,
        paths: ReportPaths,
    ) -> None:
        snapshot = snapshot_from_report(report, paths)
        self._sessions.record_inspection(chat_id, operator_open_id, snapshot)

    def try_handle(
        self,
        chat_id: str,
        operator_open_id: str,
        text: str,
    ) -> bool:
        """Handle conversational intents. Returns True if handled."""
        session = self._sessions.get(chat_id, operator_open_id)
        intent = classify_intent(text, session)

        if intent == Intent.UNKNOWN:
            return False

        if intent == Intent.EXPLAIN:
            query = parse_explain_query(text, session) or ExplainQuery(raw_text=text)
            self._handle_explain(chat_id, operator_open_id, text, query, mode="explain")
            return True

        if intent == Intent.ADVISE:
            query = parse_explain_query(text, session) or ExplainQuery(raw_text=text)
            self._handle_explain(chat_id, operator_open_id, text, query, mode="advise")
            return True

        if intent == Intent.CHAT:
            self._handle_explain(
                chat_id,
                operator_open_id,
                text,
                ExplainQuery(raw_text=text),
                mode="chat",
            )
            return True

        return False

    def _handle_explain(
        self,
        chat_id: str,
        operator_open_id: str,
        user_text: str,
        query: ExplainQuery,
        *,
        mode: str,
    ) -> None:
        session = self._sessions.get(chat_id, operator_open_id)
        facts, chunks, case = build_explain_facts(query, session)

        history = [(role, content) for role, content in session.recent_messages]
        reply = generate_reply(user_text, facts, chunks, mode=mode, history=history)
        if not reply:
            reply = render_template_reply(user_text, facts, chunks, mode=mode)

        if is_llm_enabled():
            footer = "（本回复由事实材料 + LLM 组织，检测结果以报告为准）"
        else:
            footer = "（未配置 LLM，以上为规则解读；配置 INSPECTOR_LLM_API_KEY 可启用更自然对话）"

        self._sessions.append_turn(chat_id, operator_open_id, "user", user_text)
        self._sessions.append_turn(chat_id, operator_open_id, "assistant", reply[:500])
        self._deliver_explain(chat_id, reply, footer, mode=mode, case=case)

    def _deliver_explain(
        self,
        chat_id: str,
        body: str,
        footer: str,
        *,
        mode: str,
        case,
    ) -> None:
        card_body = f"{body}\n\n---\n{footer}"
        if self._send_card:
            try:
                self._send_card(
                    chat_id,
                    build_explain_card(card_body, mode=mode, case=case),
                )
                return
            except Exception as exc:
                logger.warning("send explain card failed, fallback to text: %s", exc)
        self._reply(chat_id, f"{body}\n\n—\n{footer}")
