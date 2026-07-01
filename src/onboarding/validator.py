"""Pre-flight validation before running inspection on a new bot."""

from __future__ import annotations

import re

import httpx

from src.feishu.client import FeishuClient
from src.models import BotConfig
from src.onboarding.models import CAPABILITY_OPTIONS, CheckResult, ValidationReport

APP_ID_RE = re.compile(r"^cli_[a-z0-9]+$", re.I)
OPEN_ID_RE = re.compile(r"^ou_[a-z0-9]+$", re.I)
CHAT_ID_RE = re.compile(r"^oc_[a-z0-9]+$", re.I)


def validate_bot_config(
    bot: BotConfig,
    client: FeishuClient,
    *,
    trigger_chat_id: str,
    operator_open_id: str = "",
) -> ValidationReport:
    checks: list[CheckResult] = []

    if not bot.name.strip():
        checks.append(CheckResult("名称", False, "Bot 名称不能为空"))
    else:
        checks.append(CheckResult("名称", True, bot.name))

    app_id = bot.target_app_id or bot.app_id
    if not app_id:
        checks.append(
            CheckResult(
                "App ID",
                False,
                "未填写被测 Bot 的 App ID",
                "在飞书开放平台 → 应用详情 复制 App ID（cli_ 开头）",
            )
        )
    elif not APP_ID_RE.match(app_id):
        checks.append(CheckResult("App ID", False, f"格式异常：{app_id}", "应为 cli_ 开头的应用 ID"))
    else:
        checks.append(CheckResult("App ID", True, app_id))

    if not bot.open_id:
        checks.append(
            CheckResult(
                "open_id",
                False,
                "未填写被测 Bot 的 open_id",
                "在被测 Bot 所在群里 @ 它一次，或从开放平台/日志中获取 ou_ 开头的 open_id",
            )
        )
    elif not OPEN_ID_RE.match(bot.open_id):
        checks.append(CheckResult("open_id", False, f"格式异常：{bot.open_id}"))
    else:
        checks.append(CheckResult("open_id", True, bot.open_id))

    group_id = bot.chats.get("normal_group") or trigger_chat_id
    if not group_id:
        checks.append(
            CheckResult(
                "测试群",
                False,
                "未配置 normal_group chat_id",
                "请在要测试的群里 @ Inspector 发起「测试」指令",
            )
        )
    elif not CHAT_ID_RE.match(group_id):
        checks.append(CheckResult("测试群", False, f"chat_id 格式异常：{group_id}"))
    else:
        checks.append(CheckResult("测试群", True, f"使用群 {group_id}"))

    if group_id and app_id and bot.open_id:
        in_group = client.is_bot_in_chat(
            group_id,
            app_id,
            target_open_id=bot.open_id,
            bot_name=bot.name,
        )
        if in_group:
            checks.append(CheckResult("Bot 在测试群", True, f"「{bot.name}」已在当前测试群"))
        else:
            checks.append(
                CheckResult(
                    "Bot 在测试群",
                    False,
                    f"未检测到「{bot.name}」在当前测试群",
                    f"请将「{bot.name}」和 Inspector 都拉入同一测试群，并在群里 @ 被测 Bot 一次",
                )
            )

    if bot.open_id:
        try:
            client.send_text(
                bot.open_id,
                f"[Inspector 连通性探测] 准备巡检「{bot.name}」，请忽略本条消息。",
                receive_id_type="open_id",
            )
            checks.append(CheckResult("私聊通道", True, "可向被测 Bot 发送私聊探测消息"))
        except Exception as exc:
            checks.append(
                CheckResult(
                    "私聊通道",
                    False,
                    str(exc),
                    "未开通私聊权限时，私聊相关用例可能跳过或失败；确认后仍可继续巡检",
                    blocking=False,
                )
            )

    if "topic_reply" in bot.capabilities:
        topic_id = bot.chats.get("topic_group", "")
        if not topic_id and bot.backend.get("_auto_create_topic"):
            try:
                topic_id = client.create_topic_test_group(
                    f"{bot.name} 话题测试",
                    operator_open_id=operator_open_id,
                    target_app_id=app_id,
                )
                bot.chats["topic_group"] = topic_id
            except Exception as exc:
                checks.append(
                    CheckResult(
                        "话题群",
                        False,
                        f"自动创建话题群失败：{exc}",
                        "请为 Inspector 开通 im:chat:create 权限，或关闭自动建群并手动配置",
                    )
                )

        topic_id = bot.chats.get("topic_group", "")
        if not topic_id:
            if not any(c.name == "话题群" for c in checks):
                checks.append(
                    CheckResult(
                        "话题群",
                        False,
                        "已勾选话题回复能力，但未配置话题群",
                        "表单中选择「自动创建话题群」，或手动将 Bot 拉入已有话题群",
                    )
                )
        elif not CHAT_ID_RE.match(topic_id):
            checks.append(CheckResult("话题群", False, f"chat_id 格式异常：{topic_id}"))
        elif bot.open_id:
            in_topic = client.is_bot_in_chat(
                topic_id,
                app_id,
                target_open_id=bot.open_id,
                bot_name=bot.name,
            )
            if in_topic:
                checks.append(CheckResult("Bot 在话题群", True, topic_id))
            else:
                checks.append(
                    CheckResult(
                        "Bot 在话题群",
                        False,
                        f"未检测到「{bot.name}」在话题群",
                        "请将被测 Bot 与 Inspector 都加入该话题群",
                    )
                )
        else:
            checks.append(CheckResult("话题群", True, topic_id))

    if "doc_access" in bot.capabilities:
        if bot.test_assets.get("doc_permitted") and bot.test_assets.get("doc_denied"):
            checks.append(CheckResult("文档测试素材", True, "已配置有/无权限文档链接"))
        else:
            checks.append(
                CheckResult(
                    "文档测试素材",
                    False,
                    "缺少 doc_permitted 或 doc_denied 文档链接",
                    "在表单中填写两个飞书文档 URL，或暂时去掉 doc_access 能力",
                )
            )

    health_url = bot.backend.get("health_url", "")
    if health_url:
        try:
            with httpx.Client(timeout=5.0, follow_redirects=True) as http:
                resp = http.get(health_url)
            ok = resp.status_code < 500
            checks.append(
                CheckResult(
                    "健康检查",
                    ok,
                    f"HTTP {resp.status_code}",
                    "" if ok else "确认 health_url 可从 Inspector 所在网络访问",
                )
            )
        except Exception as exc:
            checks.append(
                CheckResult(
                    "健康检查",
                    False,
                    str(exc),
                    "填写可访问的网关/服务根地址，或留空跳过",
                )
            )

    unknown_caps = [c for c in bot.capabilities if c not in CAPABILITY_OPTIONS]
    if unknown_caps:
        checks.append(
            CheckResult(
                "能力标签",
                False,
                f"未知标签：{', '.join(unknown_caps)}",
                f"可选：{', '.join(CAPABILITY_OPTIONS)}",
            )
        )
    elif bot.capabilities:
        checks.append(
            CheckResult(
                "能力标签",
                True,
                ", ".join(bot.capabilities),
            )
        )

    ok = not any(not c.ok and c.blocking for c in checks)
    return ValidationReport(ok=ok, checks=checks)
