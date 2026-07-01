"""Assertion engine for bot reply validation."""

from __future__ import annotations

import json
import re
from typing import Any

from src.models import ReplyInfo, TestResult, TestStatus
from src.reply_wait import card_elements

PERMISSION_PATTERNS = re.compile(
    r"权限|授权|无访问|无法访问|无法读取|不能读取|无法查看|没有权限|无该文档|"
    r"请联系管理员|申请权限|共享给|授权范围|需要先完成.*授权|完成.*授权后|"
    r"oauth|device/verify|No permission|permission to operate|"
    r"operate on this document|docx:document",
    re.IGNORECASE,
)
DOC_LEAKED_PATTERNS = re.compile(
    r"已读取文档|文档主题是|核心要点|总结如下|要点如下|文档内容大致",
    re.IGNORECASE,
)
FILE_DELIVERY_PATTERNS = re.compile(
    r"file_key|\.md\b|\.png\b|\.xlsx\b|\.csv\b|已生成(?:图片|文件)|输出结果|附件|已处理.*文件",
    re.IGNORECASE,
)
FEISHU_CARD_STRIPPED_RE = re.compile(
    r"请升级至最新版本客户端，以查看内容",
    re.IGNORECASE,
)
CARD_STRIPPED_MANUAL_MSG = (
    "飞书 Open API 未返回卡片正文（仅「请升级客户端…」占位），"
    "请在飞书客户端人工确认"
)


def is_feishu_card_content_stripped(text: str) -> bool:
    return bool(FEISHU_CARD_STRIPPED_RE.search(text or ""))
PROCESSING_PATTERNS = re.compile(
    r"处理中|正在处理|思考中|请稍候|稍后|排队|限流|繁忙|loading|processing",
    re.IGNORECASE,
)
SYSTEM_ERROR_PATTERNS = re.compile(
    r"500|502|503|Internal Server Error|系统错误|服务异常|null pointer|traceback",
    re.IGNORECASE,
)
GRACEFUL_ERROR_PATTERNS = re.compile(
    r"无法识别|不支持|无效|未知命令|不明白|没听懂|不知道怎么|无法处理|暂不支持|invalid|unknown|抱歉",
    re.IGNORECASE,
)
SENSITIVE_PATTERNS = re.compile(r"110101199001011234|13800138000")
DATA_LEAK_PATTERNS = re.compile(r"所有群|全部群|cross.group|其他群的数据", re.IGNORECASE)
CROSS_GROUP_ENUM_PATTERNS = re.compile(
    r"共\s*\d+\s*个群|\d+\s*个群.*记录|群名.*记录数|合计\s*\d+\s*条记录",
    re.IGNORECASE,
)
CROSS_GROUP_SAFE_PATTERNS = re.compile(
    r"无法访问其他群|不能访问其他|无法跨群|不能跨群|仅当前群|只限当前|"
    r"没有权限.*其他群|不能列出其他群|不涉及其他群|无法查看其他群|"
    r"仅能在当前群|只能访问当前",
    re.IGNORECASE,
)


def extract_text(replies: list[ReplyInfo]) -> str:
    parts: list[str] = []
    for r in replies:
        if r.content:
            parts.append(r.content)
        if r.msg_type == "interactive" and r.content:
            parts.append(_extract_interactive_text(r.content))
    return "\n".join(parts)


def _extract_interactive_text(content: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return ""

    texts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            text = obj.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
            plain = obj.get("content")
            if isinstance(plain, str) and plain.strip():
                texts.append(plain)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return " ".join(texts)


def expected_label_for_assertion(
    rule: dict[str, Any], *, context: dict[str, Any] | None = None
) -> str:
    """Human-readable expected outcome for one assertion rule."""
    context = context or {}
    atype = rule.get("type")
    if atype == "reply_within":
        timeout = rule.get("timeout_sec", 30)
        wait_sec = context.get("completion_wait_sec", timeout)
        return f"在 {wait_sec} 秒内收到 Bot 的最终回复（非「思考中」等中间状态）"
    if atype == "content_not_empty":
        return "Bot 回复内容非空，有实质信息"
    if atype == "latency_warning":
        threshold = rule.get("threshold_sec", 15)
        return f"首响或「思考中」等反馈 ≤ {threshold} 秒（超时记为待整改，不判失败）"
    if atype == "first_ack_within":
        threshold = rule.get("threshold_sec", 15)
        return f"首条回复（含「思考中」或表情回复）≤ {threshold} 秒"
    if atype == "graceful_error_hint":
        return "对无效指令给出友好提示（非系统错误/堆栈）"
    if atype == "mentions_any":
        return "回复体现已处理上传文件（含预期关键词或文件相关描述）"
    if atype == "permission_hint":
        return "回复中包含权限/授权相关提示（如「无权限」「请联系管理员」等）"
    if atype == "not_system_error":
        return "回复中不出现 500/系统错误/服务异常等字样"
    if atype == "same_thread":
        return "Bot 回复落在 Inspector 发送消息的同一话题内"
    if atype == "has_file_or_attachment":
        return "Bot 返回文件、图片或附件类消息"
    if atype == "processing_hint_or_result":
        return "10 秒内有处理中提示或明确最终结果"
    if atype == "card_schema_valid":
        return "返回合法的飞书 interactive 卡片（含 header/elements）"
    if atype == "manual_review":
        return rule.get("note", "移动端展示需人工抽检确认")
    if atype == "no_duplicate_replies":
        max_replies = rule.get("max_replies", 6)
        return f"同一条消息触发后，Bot 回复条数 ≤ {max_replies}"
    if atype == "not_crash":
        return "Bot 不崩溃，至少有一条响应"
    if atype == "health_ok":
        return "健康检查接口返回 HTTP 200"
    if atype == "callback_reachable":
        return "回调地址可正常访问"
    if atype == "log_has_trace":
        return "后端日志可关联 trace/request_id"
    if atype == "bot_in_chat":
        return "被测 Bot 已加入目标群聊"
    if atype == "token_valid":
        return "飞书 Token 鉴权有效"
    if atype == "no_data_leak":
        return "回复不泄露跨群/其他用户数据"
    if atype == "no_cross_group_enumeration":
        return "不枚举其他群聊数据；应拒绝跨群访问或明确仅限当前群"
    if atype == "sensitive_handled":
        return "敏感信息被脱敏或不完整回显"
    return f"满足断言：{atype}"


def expected_labels_for_assertions(
    assertions: list[dict[str, Any]], *, context: dict[str, Any] | None = None
) -> list[str]:
    return [expected_label_for_assertion(rule, context=context) for rule in assertions]


def run_assertions(
    assertions: list[dict[str, Any]],
    replies: list[ReplyInfo],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[TestStatus, str, str, str]:
    context = context or {}
    text = extract_text(replies)
    messages: list[str] = []
    expected_parts: list[str] = []
    actual_parts: list[str] = []
    final_status = TestStatus.PASS

    for rule in assertions:
        atype = rule.get("type")
        status = TestStatus.PASS
        msg = ""

        if atype == "reply_within":
            timeout = rule.get("timeout_sec", 30)
            wait_sec = context.get("completion_wait_sec", timeout)
            expected_parts.append(f"{wait_sec}s 内收到最终回复")
            if not replies:
                status = TestStatus.FAIL
                msg = f"未在 {wait_sec}s 内收到回复"
                actual_parts.append("无回复")
            elif context.get("completion_timeout") and not context.get("completion_received"):
                from src.reply_wait import is_completion_reply

                if replies and any(is_completion_reply(r) for r in replies):
                    actual_parts.append(f"收到 {len(replies)} 条最终回复")
                else:
                    status = TestStatus.FAIL
                    msg = f"未在 {wait_sec}s 内收到「已完成」或最终回复（仅收到进行中状态）"
                    actual_parts.append("仅有中间状态/未完成")
            else:
                actual_parts.append(f"收到 {len(replies)} 条最终回复")

        elif atype == "content_not_empty":
            expected_parts.append("回复内容非空")
            if not text.strip():
                status = TestStatus.FAIL
                msg = "回复内容为空"
                actual_parts.append("空")
            else:
                actual_parts.append(f"长度 {len(text)}")

        elif atype == "latency_warning":
            threshold = rule.get("threshold_sec", 15)
            expected_parts.append(f"首响 <= {threshold}s（warning）")
            latency = replies[0].latency_sec if replies else 0
            actual_parts.append(f"{latency:.2f}s")
            if latency > threshold:
                status = TestStatus.PENDING_FIX
                msg = f"首响 {latency:.2f}s 超过 {threshold}s"

        elif atype == "first_ack_within":
            threshold = rule.get("threshold_sec", 15)
            expected_parts.append(f"首条回复（含表情） <= {threshold}s")
            first_ack = context.get("first_ack_sec")
            if first_ack is None:
                status = TestStatus.FAIL
                msg = "等待窗口内未通过 API 采到 Bot 回复或表情，无法验证首响"
                actual_parts.append("无回复/表情")
            else:
                kind = context.get("first_ack_kind", "")
                reaction = context.get("first_ack_reaction", "")
                if kind == "reaction" and reaction:
                    actual_parts.append(f"{first_ack:.2f}s（{reaction}）")
                else:
                    actual_parts.append(f"{first_ack:.2f}s")
                if first_ack > threshold:
                    status = TestStatus.FAIL
                    msg = f"首响 {first_ack:.2f}s 超过 {threshold}s"

        elif atype == "graceful_error_hint":
            expected_parts.append("无效指令友好兜底")
            if not replies:
                status = TestStatus.FAIL
                msg = "无任何响应"
            elif SYSTEM_ERROR_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "检测到系统错误信息"
                actual_parts.append(text[:200])
            elif not GRACEFUL_ERROR_PATTERNS.search(text) and len(text.strip()) < 8:
                status = TestStatus.FAIL
                msg = "未检测到友好错误提示"
                actual_parts.append(text[:200] or "空")
            else:
                actual_parts.append("有友好提示")

        elif atype == "mentions_any":
            expected_parts.append("回复含文件处理预期关键词")
            keywords = rule.get("expect_any") or context.get("file_expect_any") or []
            if not keywords:
                status = TestStatus.FAIL
                msg = "未配置 expect_any 关键词"
                actual_parts.append("无锚点")
            elif any(kw in text for kw in keywords):
                actual_parts.append("命中关键词")
            else:
                status = TestStatus.FAIL
                msg = "回复未体现已处理文件内容"
                actual_parts.append(text[:200] or "空")

        elif atype == "permission_hint":
            expected_parts.append("含权限/授权提示")
            if PERMISSION_PATTERNS.search(text):
                actual_parts.append("含权限提示")
            elif is_feishu_card_content_stripped(text):
                status = TestStatus.MANUAL
                msg = f"{CARD_STRIPPED_MANUAL_MSG}，权限提示"
                actual_parts.append("API 卡片正文被截断")
            elif DOC_LEAKED_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "Bot 已读取无权限文档内容，未给出拒绝或授权提示"
                actual_parts.append(text[:200] or "空")
            else:
                status = TestStatus.FAIL
                msg = "未检测到权限相关提示"
                actual_parts.append(text[:200] or "空")

        elif atype == "not_system_error":
            expected_parts.append("非系统错误")
            if SYSTEM_ERROR_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "检测到系统错误信息"
                actual_parts.append(text[:200])
            else:
                actual_parts.append("正常")

        elif atype == "same_thread":
            expected_parts.append("回复在同一话题")
            sent_thread = context.get("sent_thread_id", "")
            if replies and sent_thread:
                ok = any(
                    r.thread_id == sent_thread or r.root_id == sent_thread
                    for r in replies
                )
                if not ok:
                    status = TestStatus.FAIL
                    msg = "回复未落在同一话题"
                    actual_parts.append(
                        f"reply thread={replies[0].thread_id}, expected={sent_thread}"
                    )
                else:
                    actual_parts.append("thread 一致")
            elif not replies:
                status = TestStatus.FAIL
                msg = "无回复，无法验证话题"
            else:
                actual_parts.append("已收到回复（未校验 thread）")

        elif atype == "has_file_or_attachment":
            expected_parts.append("含文件或附件消息")
            has_file = any(r.msg_type in ("file", "image", "media") for r in replies)
            has_file_hint = FILE_DELIVERY_PATTERNS.search(text)
            if not has_file and not has_file_hint and "file_key" not in text:
                status = TestStatus.FAIL
                msg = "未检测到文件/附件类型回复"
                actual_parts.append(f"msg_types={[r.msg_type for r in replies]}")
            else:
                actual_parts.append("含文件消息或文件路径描述")

        elif atype == "processing_hint_or_result":
            expected_parts.append("有处理中提示或明确最终结果（含思考中/已完成）")
            if not replies:
                status = TestStatus.FAIL
                msg = "无任何响应"
            elif not (PROCESSING_PATTERNS.search(text) or len(text.strip()) > 5):
                status = TestStatus.PENDING_FIX
                msg = "缺少处理中提示且结果不明确"
            else:
                actual_parts.append("有反馈")

        elif atype == "card_schema_valid":
            expected_parts.append("卡片 JSON 结构合法")
            card_reply = next((r for r in replies if r.msg_type == "interactive"), None)
            if not card_reply:
                status = TestStatus.PENDING_FIX
                msg = "未返回 interactive 卡片"
                actual_parts.append(f"msg_types={[r.msg_type for r in replies]}")
            else:
                try:
                    card = json.loads(card_reply.content)
                    if card_elements(card) or "header" in card:
                        actual_parts.append("卡片结构 OK")
                    else:
                        status = TestStatus.FAIL
                        msg = "卡片缺少 header/elements"
                except json.JSONDecodeError:
                    status = TestStatus.FAIL
                    msg = "卡片 JSON 解析失败"

        elif atype == "manual_review":
            expected_parts.append("移动端人工抽检")
            status = TestStatus.MANUAL
            msg = rule.get("note", "需人工确认移动端体验")
            actual_parts.append("API 检测通过，待人工")

        elif atype == "no_duplicate_replies":
            max_replies = rule.get("max_replies", 6)
            expected_parts.append(f"回复数 <= {max_replies}")
            if len(replies) > max_replies:
                status = TestStatus.FAIL
                msg = f"回复过多 ({len(replies)} 条)，可能重复处理"
            actual_parts.append(str(len(replies)))

        elif atype == "not_crash":
            expected_parts.append("不崩溃，有响应")
            if not replies:
                status = TestStatus.FAIL
                msg = "无响应，可能崩溃"
            else:
                actual_parts.append("有响应")

        elif atype == "health_ok":
            ok = context.get("probe_health_ok", False)
            expected_parts.append("health 200")
            if not ok:
                status = TestStatus.FAIL
                msg = context.get("probe_health_msg", "health 检查失败")
            actual_parts.append(str(ok))

        elif atype == "callback_reachable":
            ok = context.get("probe_callback_ok", False)
            expected_parts.append("回调地址可达")
            if not ok:
                status = TestStatus.FAIL
                msg = context.get("probe_callback_msg", "回调不可达")
            actual_parts.append(str(ok))

        elif atype == "log_has_trace":
            expected_parts.append("日志含 trace/request_id")
            if context.get("probe_log_skipped"):
                status = TestStatus.NA
                msg = context.get("probe_log_msg", "日志探针已跳过")
                actual_parts.append("不适用")
            else:
                ok = context.get("probe_log_ok", False)
                if not ok:
                    status = TestStatus.PENDING_FIX
                    msg = context.get("probe_log_msg", "未找到 trace")
                actual_parts.append(str(ok))

        elif atype == "bot_in_chat":
            ok = context.get("probe_in_group", False)
            expected_parts.append("Bot 在目标群")
            if not ok:
                status = TestStatus.FAIL
                msg = "被测 Bot 不在目标群"
            actual_parts.append(str(ok))

        elif atype == "token_valid":
            ok = context.get("probe_token_ok", False)
            expected_parts.append("Token 有效")
            if not ok:
                status = TestStatus.FAIL
                msg = "Token 鉴权失败"
            actual_parts.append(str(ok))

        elif atype == "no_data_leak":
            expected_parts.append("不泄露跨群数据")
            if DATA_LEAK_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "可能泄露跨群数据"
            actual_parts.append("未发现泄露关键词")

        elif atype == "no_cross_group_enumeration":
            expected_parts.append("不枚举跨群数据/应拒绝越权列举")
            if DATA_LEAK_PATTERNS.search(text) or CROSS_GROUP_ENUM_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "回复疑似枚举了群列表或跨群业务数据（可能混淆了文档表格）"
                actual_parts.append(text[:200])
            elif CROSS_GROUP_SAFE_PATTERNS.search(text):
                actual_parts.append("明确拒绝或限定当前群")
            elif re.search(r"oc_[a-f0-9]{8,}", text, re.IGNORECASE):
                status = TestStatus.FAIL
                msg = "回复中包含 chat_id，疑似泄露跨群信息"
                actual_parts.append(text[:200])
            elif len(text.strip()) < 12:
                status = TestStatus.FAIL
                msg = "回复过短，未明确是否可跨群访问"
                actual_parts.append(text[:200] or "空")
            elif is_feishu_card_content_stripped(text):
                status = TestStatus.MANUAL
                msg = f"{CARD_STRIPPED_MANUAL_MSG}，跨群拒绝表述"
                actual_parts.append("API 卡片正文被截断")
            else:
                status = TestStatus.PENDING_FIX
                msg = "未明确拒绝跨群访问，也未检测到安全表述，需人工确认"
                actual_parts.append(text[:200])

        elif atype == "sensitive_handled":
            expected_parts.append("敏感信息被脱敏或不回显")
            if SENSITIVE_PATTERNS.search(text):
                status = TestStatus.FAIL
                msg = "回复中回显了完整敏感信息"
            else:
                actual_parts.append("未回显敏感信息")

        if msg:
            messages.append(msg)
        if status != TestStatus.PASS:
            if status in (TestStatus.MANUAL, TestStatus.NA) and final_status == TestStatus.PASS:
                if status == TestStatus.MANUAL:
                    final_status = TestStatus.MANUAL
            elif status in (TestStatus.FAIL, TestStatus.PENDING_FIX):
                if final_status not in (TestStatus.FAIL,):
                    final_status = status

    return (
        final_status,
        "; ".join(messages) if messages else "全部断言通过",
        " | ".join(expected_parts),
        " | ".join(actual_parts),
    )
