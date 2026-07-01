"""Orchestrate interactive bot onboarding in Feishu chat."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from typing import Any, Callable

from src.feishu.client import FeishuClient
from src.models import BotConfig
from src.onboarding.cards import (
    build_config_form_card,
    build_validation_result_card,
    field_help_text,
    parse_text_form_submission,
    text_form_fallback,
)
from src.onboarding.detect import build_onboard_hints
from src.onboarding.mentions import MentionedBot, OnboardHints
from src.onboarding.models import (
    DEFAULT_DOC_DENIED,
    DEFAULT_DOC_PERMITTED,
    OnboardPhase,
    OnboardingSession,
    bot_from_form,
    parse_capabilities,
    parse_suite,
)
from src.onboarding.persist import defaults_from_bot, upsert_registered_bot
from src.onboarding.validator import validate_bot_config
from src.registry import load_bot
from src.runner import run_inspection, deliver_inspection_results

logger = logging.getLogger(__name__)

ReplyFn = Callable[[str, str], None]
CardFn = Callable[[str, dict[str, Any]], None]
RunInspectFn = Callable[[str, str, str, str], None]


class OnboardingService:
    def __init__(
        self,
        client: FeishuClient,
        *,
        reply: ReplyFn,
        send_card: CardFn | None = None,
        run_inspection_fn: RunInspectFn | None = None,
    ) -> None:
        self.client = client
        self._reply = reply
        self._send_card = send_card or (lambda chat_id, card: None)
        self._run_inspection = run_inspection_fn or self._default_run_inspection
        self._sessions: dict[str, OnboardingSession] = {}
        self._lock = threading.Lock()

    def _default_run_inspection(
        self,
        chat_id: str,
        suite: str,
        bot_name: str,
        operator_open_id: str = "",
    ) -> None:
        triggered_by = ""
        if operator_open_id:
            triggered_by = self.client.get_user_name(operator_open_id) or operator_open_id
        try:
            reports, errors, report_paths = run_inspection(
                bot=bot_name,
                suite=suite,
                dry_run=False,
                notify=False,
                triggered_by=triggered_by,
            )
            deliver_inspection_results(
                chat_id, reports, report_paths, errors, self.client
            )
        except Exception as exc:
            logger.exception("onboard inspection failed")
            self._reply(chat_id, f"巡检失败: {exc}")

    def get_session(self, chat_id: str, operator_open_id: str) -> OnboardingSession | None:
        key = f"{chat_id}:{operator_open_id}"
        return self._sessions.get(key)

    def start_test_flow(
        self,
        chat_id: str,
        operator_open_id: str,
        bot_name: str,
        *,
        suite: str = "p0",
        register_only: bool = False,
        reconfigure: bool = False,
        mentioned_bots: list[MentionedBot] | None = None,
        hints: OnboardHints | None = None,
    ) -> None:
        existing = load_bot(bot_name)
        if reconfigure and not existing:
            self._reply(
                chat_id,
                f"未找到 Bot「{bot_name}」，请先 @{os.getenv('INSPECTOR_AT_NAME', 'bot检查员')} "
                f"测试 {bot_name} 完成首次配置。",
            )
            return
        if hints is None:
            inspector = self.client.get_bot_info()
            hints = build_onboard_hints(
                self.client,
                chat_id=chat_id,
                bot_name=bot_name,
                operator_open_id=operator_open_id,
                mentioned_bots=mentioned_bots or [],
                inspector_open_id=inspector.get("open_id", ""),
                inspector_names=(
                    os.getenv("INSPECTOR_AT_NAME", "bot检查员"),
                    inspector.get("app_name", ""),
                ),
            )

        session_id = uuid.uuid4().hex[:12]
        session = OnboardingSession(
            session_id=session_id,
            bot_name=bot_name,
            chat_id=chat_id,
            operator_open_id=operator_open_id,
            suite=suite,
            register_only=register_only,
            reconfigure=reconfigure or bool(existing and register_only),
            phase=OnboardPhase.FORM,
            draft=existing,
            hints=hints,
        )
        with self._lock:
            self._sessions[session.session_key()] = session

        if session.reconfigure:
            intro_lines = [
                f"修改「{bot_name}」配置（已预填当前保存项）。",
                "更新文档链接、能力模块等后提交；校验通过即保存，不会自动巡检。",
                "当前群仍作为普通测试群。",
            ]
        else:
            intro_lines = [
                f"开始为「{bot_name}」准备{'注册' if register_only else suite.upper() + ' 巡检'}。",
                "当前群已作为普通测试群。",
            ]
        if hints.open_id:
            intro_lines.append(f"已从 @ 识别 open_id：{hints.open_id}")
        elif mentioned_bots:
            intro_lines.append("已看到你 @ 了其他 Bot，但未解析到 open_id，请确认被测 Bot 已入群。")
        else:
            intro_lines.append("推荐：@bot检查员 @被测Bot 测试 Bot名 — 可自动识别 open_id。")
        if hints.app_id:
            intro_lines.append(f"已按名称匹配 App ID：{hints.app_id}")
        intro_lines.append("请在下方的配置卡片中确认巡检级别与能力模块。")
        self._reply(chat_id, "\n".join(intro_lines))

        defaults = self._defaults_for_session(session)
        card = build_config_form_card(
            session_id, bot_name, chat_id, defaults, hints=hints, reconfigure=session.reconfigure
        )
        try:
            self._send_card(chat_id, card)
        except Exception as exc:
            logger.warning("send config card failed: %s", exc)
            self._reply(
                chat_id,
                text_form_fallback(bot_name, chat_id, defaults, hints=hints),
            )

    def start_config_flow(
        self,
        chat_id: str,
        operator_open_id: str,
        bot_name: str,
        *,
        mentioned_bots: list[MentionedBot] | None = None,
        hints: OnboardHints | None = None,
    ) -> None:
        """Re-open config card for an already registered bot (save only, no inspect)."""
        self.start_test_flow(
            chat_id,
            operator_open_id,
            bot_name,
            register_only=True,
            reconfigure=True,
            mentioned_bots=mentioned_bots,
            hints=hints,
        )

    def handle_text(
        self,
        chat_id: str,
        operator_open_id: str,
        text: str,
    ) -> bool:
        """Handle onboarding-related text. Returns True if consumed."""
        normalized = text.strip()
        session = self.get_session(chat_id, operator_open_id)

        if normalized in ("取消", "取消测试", "取消注册"):
            if session:
                with self._lock:
                    self._sessions.pop(session.session_key(), None)
                self._reply(chat_id, "已取消当前 Bot 配置流程。")
            return True

        if session and session.phase in (OnboardPhase.AWAITING_FIX, OnboardPhase.READY):
            if (
                normalized.startswith("确认测试")
                or normalized.startswith("确认配置")
                or normalized.startswith("保存配置")
                or normalized in ("确认", "开始巡检", "提交配置")
            ):
                self._try_start_inspection(session)
                return True

        form = parse_text_form_submission(normalized)
        if form and session and session.phase == OnboardPhase.FORM:
            self._apply_form(session, form)
            return True

        if normalized.startswith("提交配置") and session:
            body = normalized.replace("提交配置", "", 1).strip()
            parsed = parse_text_form_submission(body) if body else None
            if parsed:
                self._apply_form(session, parsed)
                return True

        return False

    def handle_card_action(
        self,
        chat_id: str,
        operator_open_id: str,
        action: dict[str, Any],
        form_value: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Process card.action.trigger. Returns toast payload for Feishu."""
        session_id = (action or {}).get("session_id", "")
        act = (action or {}).get("action", "")

        if act == "show_help":
            field = (action or {}).get("field", "")
            label = field_help_text(field)
            return {"toast": {"type": "info", "content": label[:2000]}}

        session = self._find_session(session_id, chat_id, operator_open_id)
        if not session:
            return {"toast": {"type": "warning", "content": "会话已过期，请重新发送「测试 Bot名」或「配置 Bot名」"}}

        if act == "submit_config":
            if not form_value:
                return {"toast": {"type": "warning", "content": "未收到表单数据，请重试"}}
            self._apply_form(session, form_value)
            return {"toast": {"type": "info", "content": "已提交，正在校验…"}}

        if act == "edit_config":
            session.phase = OnboardPhase.FORM
            defaults = self._defaults_for_session(session)
            try:
                self._send_card(
                    chat_id,
                    build_config_form_card(
                        session.session_id,
                        session.bot_name,
                        session.chat_id,
                        defaults,
                        hints=session.hints,
                        reconfigure=session.reconfigure,
                    ),
                )
            except Exception as exc:
                logger.warning("resend config card failed: %s", exc)
                self._reply(
                    chat_id,
                    text_form_fallback(
                        session.bot_name,
                        session.chat_id,
                        defaults,
                        hints=session.hints,
                    ),
                )
            return {"toast": {"type": "info", "content": "请更新配置"}}

        if act == "start_inspection":
            self._try_start_inspection(session)
            return {"toast": {"type": "success", "content": "开始巡检"}}

        return {"toast": {"type": "warning", "content": f"未知操作: {act}"}}

    def _find_session(
        self,
        session_id: str,
        chat_id: str,
        operator_open_id: str,
    ) -> OnboardingSession | None:
        if session_id:
            for session in self._sessions.values():
                if session.session_id == session_id:
                    return session
        return self.get_session(chat_id, operator_open_id)

    def _defaults_for_session(self, session: OnboardingSession) -> dict[str, str]:
        defaults = defaults_from_bot(session.draft)
        defaults.setdefault("test_suite", session.suite or "p0")
        if not defaults.get("capabilities"):
            from src.onboarding.models import ALL_CAPABILITIES

            defaults["capabilities"] = ",".join(ALL_CAPABILITIES)
        caps = parse_capabilities(defaults.get("capabilities"))
        if "doc_access" in caps:
            defaults.setdefault("doc_permitted", DEFAULT_DOC_PERMITTED)
            defaults.setdefault("doc_denied", DEFAULT_DOC_DENIED)
        hints = session.hints
        if hints:
            if hints.open_id:
                defaults["open_id"] = hints.open_id
            if hints.app_id:
                defaults["target_app_id"] = hints.app_id
            if hints.owner_name:
                defaults["owner"] = hints.owner_name
        return defaults

    def _merge_form(self, session: OnboardingSession, form: dict[str, Any]) -> dict[str, Any]:
        merged = dict(form or {})
        hints = session.hints
        if hints:
            if hints.open_id and not str(merged.get("open_id", "")).strip():
                merged["open_id"] = hints.open_id
            if hints.app_id and not str(merged.get("target_app_id", "")).strip():
                merged["target_app_id"] = hints.app_id
            if hints.owner_name and not str(merged.get("owner", "")).strip():
                merged["owner"] = hints.owner_name
        return merged

    def _apply_form(self, session: OnboardingSession, form: dict[str, Any]) -> None:
        merged = self._merge_form(session, form)
        session.suite = parse_suite(merged.get("test_suite"), default=session.suite)
        bot = bot_from_form(
            session.bot_name,
            session.chat_id,
            merged,
            owner_fallback=session.draft.owner if session.draft else "",
        )
        session.draft = bot
        session.phase = OnboardPhase.VALIDATING
        self._reply(session.chat_id, f"正在校验「{session.bot_name}」的配置…")

        report = validate_bot_config(
            bot,
            self.client,
            trigger_chat_id=session.chat_id,
            operator_open_id=session.operator_open_id,
        )
        session.last_validation = report
        session.phase = OnboardPhase.READY if report.ok else OnboardPhase.AWAITING_FIX

        try:
            self._send_card(
                session.chat_id,
                build_validation_result_card(
                    session.session_id,
                    session.bot_name,
                    report,
                    register_only=session.register_only,
                    reconfigure=session.reconfigure,
                    suite=session.suite,
                ),
            )
        except Exception as exc:
            logger.warning("send validation card failed: %s", exc)
            self._reply(session.chat_id, self._validation_text(report))

        if not report.ok:
            hint = (
                f"或发送「确认配置 {session.bot_name}」保存。"
                if session.register_only
                else f"或发送「确认测试 {session.bot_name}」重新校验。"
            )
            self._reply(
                session.chat_id,
                "请按卡片提示完成必要操作后，点击「修改配置」重新提交，" + hint,
            )

    def _validation_text(self, report) -> str:
        lines = ["【校验结果】"]
        for check in report.checks:
            if check.ok:
                mark = "通过"
            elif check.blocking:
                mark = "未通过"
            else:
                mark = "提示"
            lines.append(f"- [{mark}] {check.name}: {check.message}")
            if check.user_action and not check.ok:
                lines.append(f"  请你：{check.user_action}")
        if report.warnings:
            lines.append("\n提示项不影响继续巡检；私聊相关用例可能无法执行。")
        if report.ok:
            if session.register_only:
                lines.append("\n全部通过。发送「确认配置」或点击「保存配置」。")
            else:
                lines.append("\n全部通过。发送「确认」或点击卡片按钮开始巡检。")
        return "\n".join(lines)

    def _try_start_inspection(self, session: OnboardingSession) -> None:
        if not session.draft:
            self._reply(session.chat_id, "尚未提交有效配置，请先填写表单。")
            return

        report = validate_bot_config(
            session.draft, self.client, trigger_chat_id=session.chat_id,
            operator_open_id=session.operator_open_id,
        )
        session.last_validation = report
        if not report.ok:
            session.phase = OnboardPhase.AWAITING_FIX
            self._reply(session.chat_id, self._validation_text(report))
            try:
                self._send_card(
                    session.chat_id,
                    build_validation_result_card(
                        session.session_id,
                        session.bot_name,
                        report,
                        register_only=session.register_only,
                        reconfigure=session.reconfigure,
                        suite=session.suite,
                    ),
                )
            except Exception:
                pass
            return

        path = upsert_registered_bot(session.draft)
        session.phase = OnboardPhase.RUNNING

        if session.register_only:
            self._reply(
                session.chat_id,
                f"配置已更新并保存至 {path.name}。\n"
                f"之后可 @{os.getenv('INSPECTOR_AT_NAME', 'bot检查员')} 巡检 {session.bot_name}",
            )
            with self._lock:
                self._sessions.pop(session.session_key(), None)
            return

        self._reply(
            session.chat_id,
            f"配置已保存至 {path.name}，开始 {session.suite.upper()} 巡检「{session.bot_name}」…",
        )

        threading.Thread(
            target=self._run_inspection,
            args=(
                session.chat_id,
                session.suite,
                session.bot_name,
                session.operator_open_id,
            ),
            daemon=True,
        ).start()

        with self._lock:
            self._sessions.pop(session.session_key(), None)
