"""Feishu chat trigger — @Inspector 后通过长连接触发巡检."""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from src.conversation.service import ConversationService
from src.feishu.client import FeishuClient
from src.inspection_cancel import is_active, request_cancel
from src.onboarding.mentions import MentionedBot, is_inspector_mentioned, parse_message_mentions
from src.onboarding.service import OnboardingService
from src.registry import load_bot, load_bots
from src.runner import ROOT, SUITE_ALIASES, deliver_inspection_results, run_inspection

logger = logging.getLogger(__name__)


def _inspector_names() -> tuple[str, str]:
    """Read from env at call time (after load_dotenv)."""
    return (
        os.getenv("INSPECTOR_AT_NAME", "bot检查员"),
        os.getenv("INSPECTOR_BOT_EXAMPLE", "demo-bot"),
    )


def build_help_text(*, unrecognized: bool = False) -> str:
    n, example = _inspector_names()
    body = f"""我是 {n}，可以帮你对其他 Bot 做可用性、有效性检查，并自动生成验收报告。

你可以对我说：

【首次测试某个 Bot】
@{n} @被测Bot 测试 <Bot名>
→ 弹出配置卡片，校验通过后自动巡检（同时 @被测Bot 可自动识别 open_id）

【已配置过的 Bot】
@{n} 巡检 [p0|full] [Bot名]
→ 不写级别默认 P0；不写 Bot 名则巡检全部。例：@{n} 巡检 {example}

【修改已保存的配置】（文档链接、能力模块等）
@{n} 配置 <Bot名>
→ 弹出配置卡片，预填当前值；校验通过后保存，不会自动巡检
也可：@{n} 注册 <Bot名>（效果相同）

【暂停正在进行的巡检】
@{n} 暂停 <Bot名>  或  @{n} 暂停对<Bot名>的巡检

【仅登记配置、暂不巡检】（首次）
@{n} 注册 <Bot名>

【对话与解读】（巡检完成后 1 小时内可追问）
@{n} 解释 p0_doc_denied  /  为什么 ISS-001 判失败
@{n} 无权限文档这项为什么失败？  /  建议应该怎么测文件附件
说明：解读基于最近一次报告 + 检测清单；配置 LLM 后回复更自然。

随时发「帮助」或问我「你能干什么」查看本说明。"""
    if unrecognized:
        return (
            f"暂未识别为巡检指令。你可以：\n"
            f"· 开始巡检：@{n} 巡检 p0 <Bot名>\n"
            f"· 解释结果：@{n} 解释 <用例ID> 或 为什么 ISS-001\n"
            f"· 查看说明：@{n} 帮助\n\n"
            f"{body}"
        )
    return body


def build_startup_instructions() -> str:
    """Shown in console and Feishu ready ping when service starts."""
    n, example = _inspector_names()
    return f"""【{n}】已就绪

首次测试：@{n} @被测Bot 测试 <Bot名>
已配置巡检：@{n} 巡检 [p0|full] [Bot名]
修改配置：@{n} 配置 <Bot名>
查看说明：@{n} 帮助

示例：@{n} 巡检 {example}"""


def _allowed_chat_ids() -> set[str]:
    ids: set[str] = set()
    for key in ("TRIGGER_CHAT_IDS", "NOTIFY_CHAT_ID"):
        raw = os.getenv(key, "")
        for part in raw.split(","):
            part = part.strip()
            if part:
                ids.add(part)
    return ids


def _trigger_max_age_sec() -> int:
    return int(os.getenv("TRIGGER_MAX_AGE_SEC", "300"))


def _send_ready_ping_enabled() -> bool:
    return os.getenv("SEND_READY_PING", "true").lower() in ("1", "true", "yes")


def _message_age_sec(msg) -> float | None:
    create_time = getattr(msg, "create_time", None)
    if not create_time:
        return None
    try:
        return max(0.0, time.time() - int(create_time) / 1000)
    except (TypeError, ValueError):
        return None


def _is_stale_command(msg) -> bool:
    age = _message_age_sec(msg)
    if age is None:
        return False
    return age > _trigger_max_age_sec()


def _instance_lock_path() -> Path:
    return ROOT / ".cache" / "chat_trigger.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _release_instance_lock() -> None:
    lock_path = _instance_lock_path()
    try:
        if lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _find_chat_trigger_pids() -> list[int]:
    """Return other python PIDs running `python -m src.chat_trigger`."""
    current = os.getpid()
    pids: list[int] = []
    if sys.platform != "win32":
        return pids
    try:
        import subprocess

        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
            "| Where-Object { $_.CommandLine -match 'chat_trigger' } "
            "| Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                if pid != current:
                    pids.append(pid)
    except Exception as exc:
        logger.debug("scan chat_trigger processes failed: %s", exc)
    return pids


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            import subprocess

            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
            return
        except Exception:
            pass
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def _acquire_instance_lock() -> None:
    """Refuse to start if another chat_trigger process is already running."""
    lock_path = _instance_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    force = os.getenv("CHAT_TRIGGER_FORCE", "").lower() in ("1", "true", "yes")
    current_pid = os.getpid()

    others = _find_chat_trigger_pids()
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and old_pid != current_pid and old_pid not in others:
            others.append(old_pid)

    alive_others = [pid for pid in others if _pid_alive(pid)]
    if alive_others:
        if not force:
            logger.error(
                "检测到 %s 个 chat_trigger 已在运行 (pids=%s)，拒绝重复启动。"
                "请先停止全部旧进程；确需接管可设 CHAT_TRIGGER_FORCE=1。",
                len(alive_others),
                alive_others,
            )
            raise SystemExit(1)
        for pid in alive_others:
            _terminate_pid(pid)
        time.sleep(1)

    lock_path.write_text(str(current_pid), encoding="utf-8")
    atexit.register(_release_instance_lock)


def _trigger_mode() -> str:
    return os.getenv("CHAT_TRIGGER_MODE", "ws").lower()


def _extract_text(content: str, msg_type: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content.strip()

    if msg_type == "text":
        return data.get("text", "").strip()

    if msg_type == "post":
        lines: list[str] = []
        for locale in ("zh_cn", "en_us", "ja_jp"):
            block = data.get(locale) or data.get("post", {}).get(locale)
            if not block:
                continue
            for row in block.get("content", []):
                for elem in row:
                    if elem.get("tag") == "text":
                        lines.append(elem.get("text", ""))
        return " ".join(lines).strip()

    return ""


def _normalize_command_text(text: str) -> str:
    text = re.sub(r"@_user_\d+", "", text)
    text = re.sub(r"@[^\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_usage_query(text: str) -> bool:
    """True when user asks how to use the inspector bot."""
    normalized = _normalize_command_text(text.strip()).lower()
    if not normalized:
        return False
    if normalized in ("帮助", "help", "/help", "?", "？"):
        return True
    markers = (
        "你可以怎么使用",
        "你可以干什么",
        "你能干什么",
        "你能做什么",
        "你可以做什么",
        "你会什么",
        "能做什么",
        "我要怎么用你",
        "我要怎么用",
        "怎么使用你",
        "怎么用你",
        "怎么使用",
        "如何使用",
        "怎么用",
    )
    return any(m in normalized for m in markers)


def _is_from_self(event: P2ImMessageReceiveV1, app_id: str) -> bool:
    sender = getattr(event.event, "sender", None)
    if not sender:
        return False
    if getattr(sender, "sender_type", "") == "app":
        return True
    sid = getattr(sender, "sender_id", None)
    if not sid:
        return False
    return getattr(sid, "open_id", "") == app_id or getattr(sid, "user_id", "") == app_id


def parse_command(text: str) -> tuple[str | None, str, str]:
    text = _normalize_command_text(text.strip())
    if is_usage_query(text):
        return ("__help__", "", "")

    m = re.match(r"^(?:/inspect|巡检)(?:\s+(.*))?$", text, re.IGNORECASE)
    if not m:
        return (None, "", "")

    rest = (m.group(1) or "").strip()
    if not rest:
        return (None, "p0", "all")

    tokens = rest.split()
    suite = "p0"
    bot = "all"

    if tokens[0].lower() in ("p0", "full", "api"):
        suite = tokens[0].lower()
        tokens = tokens[1:]

    if tokens:
        bot = " ".join(tokens)

    known = {b.name for b in load_bots()}
    if bot != "all" and bot not in known:
        return (f"未找到 Bot「{bot}」，请在 config/bots.yaml 中配置", "", "")

    return (None, suite, bot)


def parse_test_command(text: str) -> tuple[str | None, str, str, bool]:
    """Parse 测试/注册 command. Returns (error, suite, bot_name, register_only)."""
    text = _normalize_command_text(text.strip())
    m = re.match(r"^(?:测试|注册)(?:\s+(.*))?$", text, re.IGNORECASE)
    if not m:
        return (None, "", "", False)

    register_only = bool(re.match(r"^注册", text, re.IGNORECASE))
    rest = (m.group(1) or "").strip()
    if not rest:
        return ("请指定要测试的 Bot 名称，例如：测试 demo-kb-bot", "", "", register_only)

    tokens = rest.split()
    suite = "p0"
    if tokens[0].lower() in ("p0", "full", "api"):
        suite = "full" if tokens[0].lower() in ("full", "api") else "p0"
        tokens = tokens[1:]

    if not tokens:
        return ("请指定 Bot 名称", "", "", register_only)

    bot_name = " ".join(tokens)
    return (None, suite, bot_name, register_only)


def parse_config_command(text: str) -> tuple[str | None, str]:
    """Parse 配置/修改配置/更新配置 <Bot名>. Returns (error, bot_name); bot empty if not a config cmd."""
    text = _normalize_command_text(text.strip())
    m = re.match(r"^(?:配置|修改配置|更新配置)(?:\s+(.*))?$", text, re.IGNORECASE)
    if not m:
        return (None, "")

    rest = (m.group(1) or "").strip()
    if not rest:
        return ("请指定 Bot 名称，例如：配置 demo-bot", "")

    return (None, " ".join(rest.split()))


def parse_pause_command(text: str) -> str | None:
    """Parse 暂停/停止/中断 … 巡检. Returns bot name or None if not a pause command."""
    text = _normalize_command_text(text.strip())
    if not text:
        return None

    markers = ("暂停", "停止", "中断")
    if not any(text.startswith(m) for m in markers):
        return None

    rest = text
    for marker in markers:
        if text.startswith(marker):
            rest = text[len(marker) :].strip()
            break

    if rest in ("测试", "注册", "配置"):
        return None

    rest = re.sub(r"^对\s*", "", rest)
    rest = re.sub(r"^巡检\s*", "", rest)
    rest = re.sub(r"的巡检$", "", rest).strip()
    return rest or ""


def resolve_bot_name(name: str) -> str | None:
    """Resolve user input to a registered bot name."""
    bot = load_bot(name)
    if bot:
        return bot.name
    key = name.casefold()
    matches = [b.name for b in load_bots() if key in b.name.casefold()]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_pause_bot(name: str) -> str | None:
    return resolve_bot_name(name)


def should_start_onboarding(bot_name: str) -> bool:
    """Use interactive onboarding unless bot is fully configured in registry."""
    bot = load_bot(bot_name)
    if not bot:
        return True
    if not bot.target_app_id or not bot.open_id:
        return True
    if not bot.chats.get("normal_group"):
        return True
    return False


class ChatTriggerService:
    def __init__(self) -> None:
        load_dotenv(ROOT / ".env")
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not self.app_id or not self.app_secret:
            raise RuntimeError("请配置 .env 中的 FEISHU_APP_ID / FEISHU_APP_SECRET")
        self.client = FeishuClient(self.app_id, self.app_secret)
        self._running_jobs: set[str] = set()
        self._processed_ids: set[str] = set()
        self._lock = threading.Lock()
        self.onboarding = OnboardingService(
            self.client,
            reply=self.reply,
            send_card=self.send_card,
            run_inspection_fn=self._run_job,
        )
        self.conversation = ConversationService(reply_fn=self.reply, send_card_fn=self.send_card)

    def send_card(self, chat_id: str, card: dict) -> None:
        self.client.send_interactive(chat_id, card)

    def reply(self, chat_id: str, text: str) -> None:
        try:
            self.client.send_text(chat_id, text, receive_id_type="chat_id")
        except Exception as exc:
            logger.error("reply failed chat=%s: %s", chat_id, exc)
            raise

    def _run_job(
        self,
        chat_id: str,
        suite: str,
        bot: str,
        operator_open_id: str = "",
    ) -> None:
        job_key = f"{chat_id}:{bot}:{suite}"
        triggered_by = ""
        triggered_by_open_id = operator_open_id or ""
        if operator_open_id:
            triggered_by = self.client.get_user_name(operator_open_id, chat_id=chat_id) or ""
        try:
            reports, errors, report_paths = run_inspection(
                bot=bot,
                suite=suite,
                dry_run=False,
                notify=False,
                triggered_by=triggered_by,
                triggered_by_open_id=triggered_by_open_id,
                trigger_chat_id=chat_id,
            )
            if errors and not reports:
                self.reply(
                    chat_id,
                    "巡检未能启动：\n" + "\n".join(f"- {e}" for e in errors),
                )
                return
            cancelled = any(r.cancelled for r in reports)
            if cancelled:
                done = len(reports[0].results) if reports else 0
                self.reply(
                    chat_id,
                    f"「{bot}」巡检已暂停（已完成 {done} 项用例）。",
                )
                if report_paths:
                    deliver_inspection_results(
                        chat_id, reports, report_paths, errors, self.client
                    )
            else:
                deliver_inspection_results(
                    chat_id, reports, report_paths, errors, self.client
                )
            if operator_open_id:
                for report, paths in zip(reports, report_paths):
                    self.conversation.record_inspection(
                        chat_id, operator_open_id, report, paths
                    )
        except Exception as exc:
            logger.exception("inspection failed")
            self.reply(chat_id, f"巡检失败: {exc}")
        finally:
            with self._lock:
                self._running_jobs.discard(job_key)

    def _pause_inspection(self, chat_id: str, bot_query: str) -> None:
        if not bot_query:
            self.reply(
                chat_id,
                "请指定要暂停的 Bot，例如：暂停 demo-bot  或  暂停对 demo-bot 的巡检",
            )
            return

        bot_name = resolve_pause_bot(bot_query)
        if not bot_name:
            key = bot_query.casefold()
            fuzzy = [b.name for b in load_bots() if key in b.name.casefold()]
            if len(fuzzy) > 1:
                self.reply(
                    chat_id,
                    f"「{bot_query}」匹配多个 Bot：{', '.join(fuzzy)}，请写全称。",
                )
                return
            self.reply(chat_id, f"未找到 Bot「{bot_query}」。")
            return

        with self._lock:
            in_jobs = any(k.split(":")[1] == bot_name for k in self._running_jobs)

        if not (request_cancel(bot_name) or in_jobs or is_active(bot_name)):
            self.reply(chat_id, f"当前没有正在进行的「{bot_name}」巡检任务。")
            return

        self.reply(
            chat_id,
            f"已暂停「{bot_name}」巡检，当前用例结束后停止（等待回复时也会尽快中断）。",
        )

    def _dispatch_command(
        self,
        chat_id: str,
        text: str,
        message_id: str = "",
        operator_open_id: str = "",
        mentioned_bots: list[MentionedBot] | None = None,
    ) -> None:
        if message_id:
            with self._lock:
                if message_id in self._processed_ids:
                    return
                self._processed_ids.add(message_id)

        if is_usage_query(text):
            self.reply(chat_id, build_help_text())
            return

        pause_bot = parse_pause_command(text)
        if pause_bot is not None:
            self._pause_inspection(chat_id, pause_bot)
            return

        if self.onboarding.handle_text(chat_id, operator_open_id, text):
            return

        config_err, config_bot = parse_config_command(text)
        if config_err is not None or config_bot:
            if config_err:
                self.reply(chat_id, config_err)
                return
            resolved = resolve_bot_name(config_bot)
            if not resolved:
                self.reply(
                    chat_id,
                    f"未找到 Bot「{config_bot}」。"
                    f"首次使用请 @{_inspector_names()[0]} 测试 {config_bot} 完成配置。",
                )
                return
            self.onboarding.start_config_flow(
                chat_id,
                operator_open_id,
                resolved,
                mentioned_bots=mentioned_bots,
            )
            return

        if operator_open_id and self.conversation.try_handle(
            chat_id, operator_open_id, text
        ):
            return

        test_err, test_suite, test_bot, register_only = parse_test_command(text)
        if test_err is None and test_bot:
            if should_start_onboarding(test_bot) or register_only:
                existing = load_bot(test_bot)
                self.onboarding.start_test_flow(
                    chat_id,
                    operator_open_id,
                    test_bot,
                    suite=test_suite,
                    register_only=register_only,
                    reconfigure=bool(register_only and existing),
                    mentioned_bots=mentioned_bots,
                )
                return

            job_key = f"{chat_id}:{test_bot}:{test_suite}"
            with self._lock:
                if job_key in self._running_jobs:
                    self.reply(chat_id, "该巡检任务正在进行中，请稍候...")
                    return
                self._running_jobs.add(job_key)
            self.reply(
                chat_id,
                f"「{test_bot}」已在台账中，开始 {test_suite.upper()} 巡检…",
            )
            threading.Thread(
                target=self._run_job,
                args=(chat_id, test_suite, test_bot, operator_open_id),
                daemon=True,
            ).start()
            return

        if test_err:
            self.reply(chat_id, test_err)
            return

        err, suite, bot = parse_command(text)
        if err is None and not suite:
            self.reply(chat_id, build_help_text(unrecognized=True))
            return

        if err == "__help__":
            self.reply(chat_id, build_help_text())
            return

        if err:
            self.reply(chat_id, err)
            return

        job_key = f"{chat_id}:{bot}:{suite}"
        with self._lock:
            if job_key in self._running_jobs:
                self.reply(chat_id, "该巡检任务正在进行中，请稍候...")
                return
            self._running_jobs.add(job_key)

        label = f"{bot} / {suite}"
        suite_hint = "P0 必测" if suite == "p0" else "完整巡检"
        logger.info(
            "INSPECTION_TRIGGER chat=%s suite=%s bot=%s msg_id=%s sender=%s text=%r",
            chat_id,
            suite,
            bot,
            message_id,
            operator_open_id,
            text,
        )
        self.reply(
            chat_id,
            f"已收到巡检指令（{label}，{suite_hint}），开始执行，请稍候…\n"
            f"提示：同一 Bot 同时只能跑一轮，进度消息以编号 R… 区分。",
        )
        threading.Thread(
            target=self._run_job,
            args=(chat_id, suite, bot, operator_open_id),
            daemon=True,
        ).start()

    def handle_card_action(self, event: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        try:
            ev = event.event
            operator = getattr(ev, "operator", None)
            operator_open_id = getattr(operator, "open_id", "") if operator else ""
            action = getattr(ev, "action", None)
            value = getattr(action, "value", None) if action else None
            form_value = getattr(action, "form_value", None) if action else None

            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = {}
            if not isinstance(value, dict):
                value = {}

            context = getattr(ev, "context", None)
            chat_id = getattr(context, "open_chat_id", "") if context else ""
            if not chat_id:
                chat_id = getattr(context, "chat_id", "") if context else ""

            allowed = _allowed_chat_ids()
            if allowed and chat_id and chat_id not in allowed:
                return P2CardActionTriggerResponse(
                    {"toast": {"type": "warning", "content": "该群未授权触发巡检"}}
                )

            resp = self.onboarding.handle_card_action(
                chat_id,
                operator_open_id,
                value,
                form_value or {},
            )
            return P2CardActionTriggerResponse(resp)
        except Exception as exc:
            logger.exception("card action failed")
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": f"处理失败: {exc}"}}
            )

    def handle_message(self, event: P2ImMessageReceiveV1) -> None:
        if _is_from_self(event, self.app_id):
            return

        msg = event.event.message
        chat_id = msg.chat_id
        allowed = _allowed_chat_ids()

        logger.info(
            "ws event chat=%s type=%s chat_type=%s",
            chat_id,
            msg.message_type,
            getattr(msg, "chat_type", ""),
        )

        if allowed and chat_id not in allowed:
            logger.warning("ignore chat %s (not in TRIGGER_CHAT_IDS)", chat_id)
            return

        # 群聊：须 @Inspector 本人才处理；仅 @ 其他 Bot/用户时不回复
        chat_type = getattr(msg, "chat_type", "") or ""
        mentions = getattr(msg, "mentions", None) or []
        n, _ = _inspector_names()
        inspector_open_id = self.client.get_bot_info().get("open_id", "")
        if chat_type != "p2p":
            if not mentions:
                logger.debug("ignore group message without @mention")
                return
            if not is_inspector_mentioned(
                mentions,
                inspector_open_id=inspector_open_id,
                inspector_names=(n, "bot检查员"),
            ):
                logger.debug(
                    "ignore group message not @inspector mentions=%s",
                    [getattr(m, "name", "") for m in mentions],
                )
                return

        if _is_stale_command(msg):
            age = _message_age_sec(msg)
            logger.warning(
                "ignore stale command chat=%s msg_id=%s age=%.0fs (max=%ss)",
                chat_id,
                getattr(msg, "message_id", ""),
                age or -1,
                _trigger_max_age_sec(),
            )
            return

        text = _extract_text(msg.content, msg.message_type)
        message_id = getattr(msg, "message_id", "") or ""
        sender = getattr(event.event, "sender", None)
        sid = getattr(sender, "sender_id", None) if sender else None
        operator_open_id = getattr(sid, "open_id", "") if sid else ""
        mentioned_bots = parse_message_mentions(
            mentions,
            inspector_open_id=inspector_open_id,
            inspector_names=(n, "bot检查员"),
        )
        logger.info("command text: %r mentions=%s", text, [m.name for m in mentioned_bots])
        self._dispatch_command(
            chat_id, text, message_id, operator_open_id, mentioned_bots
        )

    def _send_ready_ping(self) -> None:
        ready_text = build_startup_instructions()
        for chat_id in _allowed_chat_ids():
            try:
                self.reply(chat_id, ready_text)
                logger.info("ready ping sent to %s", chat_id)
                return
            except Exception as exc:
                logger.error("ready ping failed chat=%s: %s", chat_id, exc)

    def start(self) -> None:
        _acquire_instance_lock()
        mode = _trigger_mode()
        chats = ", ".join(_allowed_chat_ids()) or "(未限制)"

        print("Bot 巡检助手已启动（长连接）")
        print(f"  App ID: {self.app_id}")
        print(f"  模式: {mode}")
        print(f"  监听群: {chats}")
        print()
        for line in build_startup_instructions().splitlines():
            print(f"  {line}")

        if _send_ready_ping_enabled():
            threading.Thread(target=self._send_ready_ping, daemon=True).start()
        else:
            logger.info("SEND_READY_PING=false，跳过启动就绪消息")

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.handle_message)
            .register_p2_card_action_trigger(self.handle_card_action)
            .build()
        )
        ws = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )
        ws.start()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    ChatTriggerService().start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
