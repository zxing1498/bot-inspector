"""Test case executor — sends messages and runs assertions."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.assertions import expected_labels_for_assertions, run_assertions
from src.feishu.client import FeishuClient
from src.models import BotConfig, BotRunReport, ReplyInfo, TestCaseDef, TestResult, TestStatus
from src.probes.callback import check_callback
from src.probes.health import check_health
from src.probes.logs import query_logs
from src.error_messages import humanize_error
from src.inspection_cancel import is_cancelled
from src.test_defaults import merge_test_assets, resolve_prompt_template
from src.registry import ROOT, case_applicable, load_env_config
from src.reply_wait import pick_final_replies, is_completion_reply
from src.timeout_tiers import apply_timeout_tier
from src.inspection_anchors import (
    case_search_key,
    format_case_progress_text,
    format_case_skipped_text,
    generate_run_id,
)
from src.wait_policy import (
    case_uses_first_ack_only,
    resolve_completion_wait,
    resolve_first_ack_poll_wait,
)

DEFAULT_TIMEOUT = 30

CHANNEL_LABELS = {
    "dm": "私聊（Inspector 向被测 Bot 发消息）",
    "normal_group": "普通群聊",
    "topic_group": "话题群",
}


class TestExecutor:
    def __init__(self, client: FeishuClient, *, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self.env_config = load_env_config()

    def _resolve_prompt(self, case: TestCaseDef, bot: BotConfig) -> tuple[str, list[str]]:
        variables = merge_test_assets(bot.capabilities, bot.test_assets)
        return resolve_prompt_template(case.prompt, variables)

    def _resolve_chat(self, case: TestCaseDef, bot: BotConfig) -> tuple[str, str]:
        channel = case.channel
        if channel == "dm":
            # 私聊自动化须用被测 Bot 的 open_id（Inspector 发消息），
            # 不能用「用户与 Bot 私聊」的 chat_id。
            if bot.open_id:
                return bot.open_id, "open_id"
            return bot.chats.get("dm", ""), "chat_id"
        chat_id = bot.chats.get(channel, bot.chats.get("normal_group", ""))
        return chat_id, "chat_id"

    def _resolve_file_asset(
        self, attach_file: str
    ) -> tuple[Path | None, list[str], str]:
        if not attach_file:
            return None, [], "file"
        assets = self.env_config.get("file_assets", {})
        entry = assets.get(attach_file)
        if entry is None:
            entry = attach_file
        kind = "file"
        if isinstance(entry, dict):
            rel = entry.get("path", "")
            expect_any = list(entry.get("expect_any") or [])
            if entry.get("kind") == "image":
                kind = "image"
        elif isinstance(entry, str):
            rel = entry
            expect_any = []
        else:
            return None, [], "file"
        if not rel or not isinstance(rel, str):
            return None, expect_any, kind
        path = ROOT / rel
        return (path if path.is_file() else None), expect_any, kind

    def _resolve_file_path(self, attach_file: str) -> Path | None:
        path, _, _ = self._resolve_file_asset(attach_file)
        return path

    def _file_followup_prompt(self, prompt: str, file_path: Path | None) -> str:
        """Make file-processing prompts explicit; many bots only handle @ on the reply."""
        base = (prompt or "请处理这个文件").strip()
        if file_path and file_path.name and file_path.name not in base:
            return f"{base}（附件：{file_path.name}）"
        return base

    def _run_probes(self, case: TestCaseDef, bot: BotConfig) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        backend = bot.backend

        if case.probe in ("health", "") or case.id.startswith("ops_health"):
            if case.probe == "health" or case.id == "ops_health":
                result = check_health(backend.get("health_url", ""))
                ctx["probe_health_ok"] = result.ok
                ctx["probe_health_msg"] = result.message

        if case.probe == "callback" or case.id == "ops_callback":
            result = check_callback(backend.get("callback_url", ""))
            ctx["probe_callback_ok"] = result.ok
            ctx["probe_callback_msg"] = result.message

        if case.probe == "bot_in_group" or case.id == "cfg_in_group":
            chat_id = bot.chats.get("normal_group", "")
            in_group = (
                self.client.is_bot_in_chat(
                    chat_id,
                    bot.target_app_id,
                    target_open_id=bot.open_id,
                    bot_name=bot.name,
                )
                if chat_id
                else False
            )
            ctx["probe_in_group"] = in_group

        if case.probe == "token_valid" or case.id == "cfg_token":
            ctx["probe_token_ok"] = self.client.validate_token()

        return ctx

    def execute_case(
        self,
        case: TestCaseDef,
        bot: BotConfig,
        *,
        run_id: str = "",
        case_index: int = 0,
        case_total: int = 0,
    ) -> TestResult:
        if is_cancelled(bot.name):
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.NA,
                message="巡检已暂停，跳过",
            )

        case = apply_timeout_tier(case, self.env_config)

        if not case_applicable(case, bot):
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.NA,
                message="Bot 不具备所需能力，跳过",
            )

        probe_ctx = self._run_probes(case, bot)

        # Probe-only cases (no messaging)
        if case.probe in ("health", "callback", "bot_in_group", "token_valid") and not case.prompt:
            status, msg, expected, actual = run_assertions(
                case.assertions, [], context=probe_ctx
            )
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=status,
                message=msg,
                expected=expected,
                actual=actual,
                probe_data=probe_ctx,
                repro_steps=f"探针: {case.probe}",
            )

        if self.dry_run:
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.PASS,
                message="dry-run 跳过实际发送",
                repro_steps=self._build_repro(case, bot),
            )

        receive_id, receive_type = self._resolve_chat(case, bot)
        if not receive_id:
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.PENDING_FIX,
                message=f"未配置 channel={case.channel} 的 chat_id",
                repro_steps=self._build_repro(case, bot),
                expected=" | ".join(
                    expected_labels_for_assertions(case.assertions)
                ),
                severity="P0" if case.section == "p0" else "P1",
            )

        if case.channel == "dm" and receive_type == "chat_id":
            try:
                self.client.list_messages(receive_id, page_size=1)
            except Exception as exc:
                return TestResult(
                    case_id=case.id,
                    case_name=case.name,
                    section=case.section,
                    report_section=case.report_section,
                    status=TestStatus.FAIL,
                    message=(
                        f"私聊 chat_id 不可用（多为用户与 Bot 的会话，Inspector 无法发消息）: {exc}。"
                        f"请在 bots.yaml 配置 open_id，由 Inspector 以 open_id 发私聊。"
                    ),
                    repro_steps=self._build_repro(case, bot),
                    severity="P0" if case.section == "p0" else "P1",
                )

        prompt, unresolved = self._resolve_prompt(case, bot)
        if unresolved:
            names = "、".join(unresolved)
            friendly = f"测试话术未配置完整，占位符未替换：{names}（请检查 config/test_defaults.yaml 或 Bot test_assets）"
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.FAIL,
                message=friendly,
                repro_steps=self._build_repro(case, bot, case.prompt),
                expected=" | ".join(expected_labels_for_assertions(case.assertions)),
                actual=friendly,
                severity="P0" if case.section == "p0" else "P1",
                probe_data=probe_ctx,
            )

        if case.extra_text and case.repeat_extra:
            prompt += case.extra_text * case.repeat_extra

        if case.attach_doc:
            doc_key = case.attach_doc
            asset_key = f"doc_{doc_key}" if not doc_key.startswith("doc_") else doc_key
            doc_url = bot.test_assets.get(asset_key, bot.test_assets.get(doc_key, doc_key))
            prompt = f"{prompt}\n{doc_url}"

        if run_id and (case.prompt or case.attach_file or case.at_bot):
            probe_ctx["run_id"] = run_id
            probe_ctx["search_key"] = case_search_key(run_id, case.id)

        repro = self._build_repro(case, bot, prompt)
        replies: list[ReplyInfo] = []
        if case.attach_file:
            file_path, expect_any, attach_kind = self._resolve_file_asset(case.attach_file)
            if expect_any:
                probe_ctx["file_expect_any"] = expect_any
            if not file_path:
                friendly = f"测试附件「{case.attach_file}」未找到或路径配置有误"
                return TestResult(
                    case_id=case.id,
                    case_name=case.name,
                    section=case.section,
                    report_section=case.report_section,
                    status=TestStatus.FAIL,
                    message=friendly,
                    repro_steps=self._build_repro(case, bot, prompt),
                    expected=" | ".join(
                        expected_labels_for_assertions(case.assertions, context=probe_ctx)
                    ),
                    actual=friendly,
                    severity="P0" if case.section == "p0" else "P1",
                    probe_data=probe_ctx,
                )
        sent_thread_id = ""
        sent_message_id = ""
        poll_chat_id = receive_id if receive_type == "chat_id" else ""
        resolve_chat = receive_id if receive_type == "chat_id" else bot.chats.get("normal_group", "")
        target_open_id = self.client.resolve_bot_open_id(
            bot.target_app_id,
            bot_name=bot.name,
            chat_id=resolve_chat,
            configured_open_id=bot.open_id,
        )

        try:
            send_ts = time.time()
            burst = max(case.burst_count, 1)

            for i in range(burst):
                if case.attach_file:
                    file_path = self._resolve_file_path(case.attach_file)
                    _, _, attach_kind = self._resolve_file_asset(case.attach_file)
                    if file_path and receive_type == "chat_id":
                        if attach_kind == "image":
                            image_key = self.client.upload_image(file_path)
                            resp = self.client.send_image_message(
                                receive_id,
                                image_key,
                                reply_in_thread=case.in_thread,
                            )
                        else:
                            file_key = self.client.upload_file(file_path)
                            resp = self.client.send_file_message(
                                receive_id,
                                file_key,
                                reply_in_thread=case.in_thread,
                            )
                        data = resp.get("data", {}) or {}
                        sent_message_id = data.get("message_id", "") or sent_message_id
                        sent_thread_id = (
                            data.get("thread_id") or data.get("message_id") or sent_thread_id
                        )
                        poll_chat_id = poll_chat_id or data.get("chat_id", "")
                        file_message_id = data.get("message_id", "")
                        if case.at_bot:
                            followup = self._file_followup_prompt(prompt, file_path)
                            if file_message_id:
                                resp = self.client.reply_text_with_at(
                                    file_message_id,
                                    followup,
                                    bot.target_app_id,
                                    target_name=bot.name,
                                    target_open_id=target_open_id,
                                )
                            else:
                                resp = self.client.send_text_with_at(
                                    receive_id,
                                    followup,
                                    bot.target_app_id,
                                    target_name=bot.name,
                                    target_open_id=target_open_id,
                                    reply_in_thread=case.in_thread,
                                )
                            data = resp.get("data", {}) or {}
                            sent_message_id = data.get("message_id", "") or sent_message_id
                            sent_thread_id = (
                                data.get("thread_id") or data.get("message_id") or sent_thread_id
                            )
                            poll_chat_id = poll_chat_id or data.get("chat_id", "")
                    else:
                        prompt += f"\n[file:{case.attach_file}]"
                elif case.at_bot and receive_type == "chat_id":
                    resp = self.client.send_text_with_at(
                        receive_id,
                        prompt,
                        bot.target_app_id,
                        target_name=bot.name,
                        target_open_id=target_open_id,
                        reply_in_thread=case.in_thread,
                    )
                    data = resp.get("data", {}) or {}
                    sent_message_id = data.get("message_id", "") or sent_message_id
                    sent_thread_id = data.get("thread_id") or data.get("message_id", "")
                    poll_chat_id = poll_chat_id or data.get("chat_id", "")
                elif receive_type == "open_id":
                    resp = self.client.send_text(
                        receive_id,
                        prompt,
                        receive_id_type="open_id",
                    )
                    data = resp.get("data", {}) or {}
                    sent_message_id = data.get("message_id", "") or sent_message_id
                    poll_chat_id = data.get("chat_id", "") or bot.chats.get("dm", "")
                elif receive_type == "chat_id":
                    resp = self.client.send_text(
                        receive_id,
                        prompt,
                        receive_id_type="chat_id",
                        reply_in_thread=case.in_thread,
                    )
                    data = resp.get("data", {}) or {}
                    sent_message_id = data.get("message_id", "") or sent_message_id
                    sent_thread_id = data.get("thread_id") or data.get("message_id", "")
                    poll_chat_id = poll_chat_id or data.get("chat_id", "")
                else:
                    self.client.send_text(receive_id, prompt, receive_id_type=receive_type)

                if burst > 1:
                    time.sleep(self.env_config.get("defaults", {}).get("burst_interval_ms", 200) / 1000)

            completion_wait = resolve_completion_wait(
                case, self.env_config.get("defaults", {}), self.env_config
            )
            first_ack_only = case_uses_first_ack_only(case)
            if first_ack_only:
                completion_wait = resolve_first_ack_poll_wait(case, self.env_config)
            probe_ctx["completion_wait_sec"] = completion_wait

            if case.prompt or case.attach_file:
                wait_chat = poll_chat_id or (
                    receive_id if receive_type == "chat_id" else bot.chats.get("normal_group", receive_id)
                )
                poll_thread_id = self.client.resolve_thread_id(sent_thread_id)
                probe_message_ids = [sent_message_id] if sent_message_id else []
                probe_ctx["probe_message_id"] = sent_message_id
                if first_ack_only:
                    ack_infos = self.client.wait_for_any_bot_ack(
                        wait_chat,
                        after_ts=send_ts,
                        timeout_sec=completion_wait,
                        min_count=1,
                        sender_app_id=bot.target_app_id or None,
                        sender_open_id=target_open_id or None,
                        thread_id=poll_thread_id or sent_thread_id,
                        probe_message_ids=probe_message_ids,
                    )
                    replies = list(ack_infos)
                    completed = bool(ack_infos)
                    if ack_infos:
                        probe_ctx["first_ack_sec"] = ack_infos[0].latency_sec
                        probe_ctx["first_ack_kind"] = ack_infos[0].msg_type
                        if ack_infos[0].msg_type == "reaction":
                            probe_ctx["first_ack_reaction"] = ack_infos[0].content
                else:
                    raw_replies, completed = self.client.wait_for_completion_replies(
                        wait_chat,
                        after_ts=send_ts,
                        timeout_sec=completion_wait,
                        sender_app_id=bot.target_app_id or None,
                        sender_open_id=target_open_id or None,
                        cancel_check=lambda: is_cancelled(bot.name),
                        thread_id=poll_thread_id or sent_thread_id,
                    )
                probe_ctx["completion_received"] = completed
                if not first_ack_only:
                    if not completed and raw_replies:
                        probe_ctx["completion_timeout"] = True
                    for raw in raw_replies:
                        info = self.client.parse_message_content(raw)
                        create_time = int(raw.get("create_time", "0")) / 1000
                        info.latency_sec = max(0, create_time - send_ts)
                        replies.append(info)
                    if probe_message_ids:
                        reaction_infos = self.client.collect_bot_reactions(
                            probe_message_ids,
                            after_ts=send_ts,
                            sender_app_id=bot.target_app_id or None,
                            sender_open_id=target_open_id or None,
                        )
                        if reaction_infos:
                            earliest_reaction = reaction_infos[0]
                            prev_ack = probe_ctx.get("first_ack_sec")
                            if prev_ack is None or earliest_reaction.latency_sec < prev_ack:
                                probe_ctx["first_ack_sec"] = earliest_reaction.latency_sec
                                probe_ctx["first_ack_kind"] = "reaction"
                                probe_ctx["first_ack_reaction"] = earliest_reaction.content
                    if replies:
                        msg_first = min(replies, key=lambda r: r.latency_sec)
                        prev_ack = probe_ctx.get("first_ack_sec")
                        if prev_ack is None or msg_first.latency_sec < prev_ack:
                            probe_ctx["first_ack_sec"] = msg_first.latency_sec
                            probe_ctx["first_ack_kind"] = msg_first.msg_type
                    replies = pick_final_replies(replies)
                if replies and not probe_ctx.get("completion_received"):
                    if any(is_completion_reply(r) for r in replies):
                        probe_ctx["completion_received"] = True
                        probe_ctx.pop("completion_timeout", None)

            if case.probe == "log_trace" or case.id == "ops_log_fields":
                log_cfg = bot.backend.get("log_query", {})
                log_result = query_logs(log_cfg, bot_name=bot.name)
                probe_ctx["probe_log_ok"] = log_result.ok
                probe_ctx["probe_log_msg"] = log_result.message
                if log_cfg.get("type") in ("skip", "none", "disabled") or log_result.trace_id == "skipped":
                    probe_ctx["probe_log_skipped"] = True

            probe_ctx["sent_thread_id"] = (
                self.client.resolve_thread_id(sent_thread_id) or sent_thread_id
            )

            status, msg, expected, actual = run_assertions(
                case.assertions, replies, context=probe_ctx
            )
            severity = "P0" if case.section == "p0" else "P1"
            if status == TestStatus.PENDING_FIX:
                severity = "P1"

            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=status,
                message=msg,
                latency_sec=probe_ctx.get("first_ack_sec")
                or (replies[0].latency_sec if replies else 0),
                repro_steps=repro,
                expected=expected,
                actual=actual,
                severity=severity,
                probe_data=probe_ctx,
                replies=replies,
            )
        except Exception as exc:
            expected = " | ".join(
                expected_labels_for_assertions(case.assertions, context=probe_ctx)
            )
            friendly = humanize_error(exc)
            probe_ctx["error_detail"] = str(exc)
            return TestResult(
                case_id=case.id,
                case_name=case.name,
                section=case.section,
                report_section=case.report_section,
                status=TestStatus.FAIL,
                message=friendly,
                repro_steps=repro,
                expected=expected,
                actual=friendly,
                severity="P0" if case.section == "p0" else "P1",
                probe_data=probe_ctx,
                replies=replies,
            )

    def _build_repro(self, case: TestCaseDef, bot: BotConfig, prompt: str = "") -> str:
        channel = CHANNEL_LABELS.get(case.channel, case.channel)
        lines = [
            f"1. 渠道：{channel}",
            f"2. 用例：{case.name}（{case.id}）",
            f"3. 目标 Bot：{bot.name}",
        ]
        if case.probe and not case.prompt:
            lines.append(f"4. 执行探针：{case.probe}")
            return "\n".join(lines)

        step = 4
        if case.at_bot:
            lines.append(f"{step}. Inspector @「{bot.name}」后发送消息")
        else:
            lines.append(f"{step}. Inspector 发送消息")
        step += 1
        if case.in_thread:
            lines.append(f"{step}. 在话题内回复")
            step += 1
        if prompt:
            lines.append(f"{step}. 消息内容：{prompt[:500]}")
            step += 1
        if case.attach_file:
            lines.append(f"{step}. 附带文件：{case.attach_file}")
        if case.attach_doc:
            lines.append(f"{step}. 附带文档链接")
        return "\n".join(lines)

    def _case_action_hint(self, case: TestCaseDef, bot: BotConfig) -> str:
        steps: list[str] = []
        path = None
        if case.attach_file:
            path, _, kind = self._resolve_file_asset(case.attach_file)
            label = "图片" if kind == "image" else "文件"
            steps.append(f"上传{label} {path.name if path else case.attach_file}")
        prompt, unresolved = self._resolve_prompt(case, bot)
        if unresolved:
            steps.append(f"（占位符未配置：{'、'.join(unresolved)}）")
        elif case.at_bot:
            text = self._file_followup_prompt(prompt or "处理文件", path).replace("\n", " ")[:48]
            if case.attach_file:
                steps.append(f"回复该附件并 @{bot.name}「{text}」")
            else:
                steps.append(f"@{bot.name}「{text}」")
        elif prompt:
            steps.append(f"发送「{prompt.replace(chr(10), ' ')[:40]}」")
        if case.attach_doc:
            steps.append("附带文档链接")
        return " → ".join(steps)

    def _notify_case_start(
        self,
        bot: BotConfig,
        case: TestCaseDef,
        index: int,
        total: int,
        *,
        run_id: str = "",
    ) -> None:
        chat_id = bot.chats.get(case.channel, "") or bot.chats.get("normal_group", "")
        if not chat_id or not (case.prompt or case.attach_file or case.at_bot):
            return
        channel = case.channel
        if channel == "dm":
            channel_hint = "私聊用例，群内无探测消息"
        elif channel == "topic_group":
            channel_hint = "话题群用例，请在话题测试群查看"
        else:
            channel_hint = ""
        try:
            if run_id:
                text = format_case_progress_text(
                    run_id,
                    case.id,
                    case.name,
                    index,
                    total,
                    channel_hint=channel_hint,
                )
                self.client.send_text(chat_id, text, receive_id_type="chat_id")
            else:
                body = f"【巡检进度 {index}/{total}】{case.name}"
                if channel_hint:
                    body += f"（{channel_hint}）"
                action = self._case_action_hint(case, bot)
                if action:
                    body += f"\n{action}"
                self.client.send_text(chat_id, body, receive_id_type="chat_id")
        except Exception:
            pass

    def _notify_case_skipped(
        self,
        bot: BotConfig,
        case: TestCaseDef,
        index: int,
        total: int,
        reason: str,
        *,
        run_id: str = "",
    ) -> None:
        chat_id = bot.chats.get("normal_group", "")
        if not chat_id:
            return
        try:
            if run_id:
                text = format_case_skipped_text(
                    run_id, case.id, case.name, index, total, reason
                )
                self.client.send_text(chat_id, text, receive_id_type="chat_id")
            else:
                self.client.send_text(
                    chat_id,
                    f"【巡检进度 {index}/{total}】{case.name} — 未采到回复或表情\n原因：{reason}",
                    receive_id_type="chat_id",
                )
        except Exception:
            pass

    def run_suite(
        self,
        bot: BotConfig,
        cases: list[TestCaseDef],
        *,
        suite: str = "p0",
        suite_names: list[str] | None = None,
        run_owner: str = "",
        owner_open_id: str = "",
        trigger_chat_id: str = "",
    ) -> BotRunReport:
        started_at = datetime.now()
        run_id = generate_run_id(started_at)
        report = BotRunReport(
            bot_name=bot.name,
            owner=run_owner or bot.owner,
            env=bot.env,
            started_at=started_at,
            suite=suite,
            suite_names=list(suite_names or [suite]),
            run_id=run_id,
            owner_open_id=owner_open_id,
            trigger_chat_id=trigger_chat_id,
        )
        total = len(cases)
        for index, case in enumerate(cases, start=1):
            if is_cancelled(bot.name):
                report.cancelled = True
                break
            self._notify_case_start(bot, case, index, total, run_id=run_id)
            result = self.execute_case(
                case, bot, run_id=run_id, case_index=index, case_total=total
            )
            if (
                result.status == TestStatus.FAIL
                and result.latency_sec == 0
                and not result.replies
                and result.message
            ):
                self._notify_case_skipped(
                    bot, case, index, total, result.message, run_id=run_id
                )
            report.results.append(result)
            if is_cancelled(bot.name):
                report.cancelled = True
                break
            if case.prompt or case.attach_file or case.at_bot:
                interval = self.env_config.get("defaults", {}).get("case_interval_sec", 0)
                if interval:
                    for _ in range(int(interval * 10)):
                        if is_cancelled(bot.name):
                            report.cancelled = True
                            break
                        time.sleep(0.1)
                    if report.cancelled:
                        break
        report.finished_at = datetime.now()
        return report
