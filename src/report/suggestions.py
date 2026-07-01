"""Failure pattern → optimization suggestions."""

from __future__ import annotations

from src.models import BotRunReport, TestResult, TestStatus
from src.registry import load_bot

SUGGESTION_RULES: list[tuple[str, str, str]] = [
    ("首响", "P1", "增加「正在处理」即时反馈；长任务改为异步处理并在完成后主动通知用户。"),
    ("超过", "P1", "优化冷启动与首包响应，简单问答建议 3 秒内返回首条消息。"),
    ("权限", "P0", "统一无权限错误模板，明确告知原因并提供文档授权/共享步骤链接。"),
    ("系统错误", "P0", "避免向用户暴露 500/stack trace，改为可读错误码 + 联系管理员指引。"),
    ("回复过多", "P1", "检查 event_id 去重与消息幂等键，避免重复推送导致多次回复。"),
    ("话题", "P1", "确认 reply_in_thread 与 root_id 在群话题场景正确传递。"),
    ("health", "P0", "补充 /health readiness 探针并接入告警，确保异常时能通知负责人。"),
    ("trace", "P1", "全链路透传飞书 event_id / message_id 作为 request_id，便于排障。"),
    ("卡片", "P1", "校验 interactive 卡片 JSON schema，确保 PC/移动端 header 与 elements 完整。"),
    ("Token", "P0", "检查 app_secret 配置与 token 刷新逻辑，避免鉴权失败。"),
    ("不在目标群", "P0", "将被测 Bot 加入普通群、话题群及外部群（如适用）后再复测。"),
    ("敏感", "P0", "对身份证、手机号等敏感输入做脱敏或拦截，禁止原样回显。"),
    ("文件", "P1", "检查文件下载 Content-Disposition 编码，确保中文文件名不乱码。"),
    ("私聊", "P0", "私聊自动化需配置被测 Bot 的 open_id；勿使用用户与 Bot 私聊的 chat_id。"),
    ("Interrupting", "P1", "避免在 Agent 未完成上一轮时连续发送用例；已启用 completion_wait 与 case_interval。"),
    ("最终回复", "P0", "确保 Hermes 卡片最终进入「已完成」状态，而非停留在思考中/中断提示。"),
]

WEBHOOK_RULES: list[tuple[str, str, str]] = [
    ("未在", "P0", "检查事件订阅、回调地址与被测 Bot 服务状态，确认 webhook 能稳定收到消息。"),
    ("回调", "P0", "确认回调 URL 公网可达、TLS 有效，并能正确响应飞书 challenge 验证。"),
]

LONG_CONNECTION_RULES: list[tuple[str, str, str]] = [
    (
        "未在",
        "P0",
        "检查长连接是否在线、是否订阅 im.message.receive_v1，以及网关 FEISHU_ALLOW_BOTS 等策略。",
    ),
    (
        "回调",
        "P0",
        "长连接模式无 webhook 地址；请检查 Hermes Gateway 进程与飞书事件日志是否 SUCCESS。",
    ),
]


def _event_mode(report: BotRunReport) -> str:
    bot = load_bot(report.bot_name)
    if not bot:
        return "webhook"
    return str(bot.feishu.get("event_mode", "webhook")).strip().lower()


def _rules_for_report(report: BotRunReport) -> list[tuple[str, str, str]]:
    mode = _event_mode(report)
    if mode == "long_connection":
        return SUGGESTION_RULES + LONG_CONNECTION_RULES
    return SUGGESTION_RULES + WEBHOOK_RULES


def generate_suggestions(report: BotRunReport) -> list[str]:
    suggestions: list[str] = []
    seen: set[str] = set()
    rules = _rules_for_report(report)

    for result in report.results:
        if result.status not in (TestStatus.FAIL, TestStatus.PENDING_FIX, TestStatus.MANUAL):
            continue
        for keyword, priority, text in rules:
            haystack = f"{result.case_name} {result.message} {result.actual}"
            if keyword in haystack:
                entry = f"[{priority}] {result.case_name}: {text}"
                if entry not in seen:
                    seen.add(entry)
                    suggestions.append(entry)

    if not suggestions and any(r.status == TestStatus.FAIL for r in report.results):
        suggestions.append("[P1] 存在失败项，请查看明细表中的复现步骤逐项整改。")

    if not any(r.status != TestStatus.PASS and r.status != TestStatus.NA for r in report.results):
        suggestions.append("全部自动化项通过，建议补充移动端卡片交互人工抽检。")

    report.suggestions = suggestions
    return suggestions
