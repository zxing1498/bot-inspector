"""Optional LLM polish for conversational replies (OpenAI-compatible API)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.conversation.rag import RagChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「bot检查员」的对话助手，专职解释 Bot 自动化巡检结果与判据。

规则：
1. 只能基于「事实材料」和「检测标准摘录」回答，不得编造未出现的 Bot 回复或报告内容。
2. 明确区分三类原因：被测 Bot 行为问题、测试资产/配置问题（如 doc_denied 链接）、Inspector 判据问题。
3. 语气专业、简洁，用中文，适当使用短列表。
4. 不能代替用户执行巡检；如需复测，提示使用「巡检 p0 <Bot名>」。
5. 若材料不足，直接说明缺少哪份报告或哪条用例信息。
6. 回答控制在 400 字以内，除非用户追问细节。"""


def is_llm_enabled() -> bool:
    return bool(os.getenv("INSPECTOR_LLM_API_KEY", "").strip())


def _api_config() -> tuple[str, str, str]:
    api_key = os.getenv("INSPECTOR_LLM_API_KEY", "").strip()
    base_url = os.getenv("INSPECTOR_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if base_url and not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    model = os.getenv("INSPECTOR_LLM_MODEL", "gpt-4o-mini")
    return api_key, base_url, model


def _format_rag(chunks: list[RagChunk]) -> str:
    if not chunks:
        return "（无）"
    parts = []
    for chunk in chunks[:3]:
        parts.append(f"### {chunk.title}\n{chunk.content[:900]}")
    return "\n\n".join(parts)


def generate_reply(
    user_text: str,
    facts: str,
    chunks: list[RagChunk],
    *,
    mode: str = "explain",
    history: list[tuple[str, str]] | None = None,
) -> str | None:
    """Call LLM; return None on failure (caller should use template fallback)."""
    api_key, base_url, model = _api_config()
    if not api_key:
        return None

    mode_hint = {
        "explain": "请解释用户疑问，说明为何判通过/失败，引用事实材料。",
        "advise": "用户在对检测方法提建议；评估是否合理，并说明应改判据、改配置还是被测 Bot。",
        "chat": "简短回应，并引导用户如何提问或触发巡检。",
    }.get(mode, "回答用户问题。")

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for role, content in history[-4:]:
            messages.append({"role": role, "content": content[:800]})

    user_payload = f"""{mode_hint}

【用户消息】
{user_text}

【事实材料】
{facts}

【检测标准摘录】
{_format_rag(chunks)}
"""
    messages.append({"role": "user", "content": user_payload})

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 800,
    }
    temp_raw = os.getenv("INSPECTOR_LLM_TEMPERATURE", "").strip()
    if temp_raw:
        try:
            body["temperature"] = float(temp_raw)
        except ValueError:
            pass

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return (content or "").strip() or None
    except Exception as exc:
        logger.warning("LLM reply failed: %s", exc)
        return None
