"""Build factual explanations from inspection snapshots (no LLM)."""

from __future__ import annotations

from src.conversation.intent import ExplainQuery
from src.conversation.rag import RagChunk, retrieve
from src.conversation.report_store import find_case_in_snapshot, load_latest_snapshot_for_bot
from src.conversation.session import CaseSnapshot, ChatSession, InspectionSnapshot


def _resolve_snapshot(session: ChatSession, bot_name: str) -> InspectionSnapshot | None:
    if session.last_inspection:
        if not bot_name or session.last_inspection.bot_name == bot_name:
            return session.last_inspection
    if bot_name:
        latest = load_latest_snapshot_for_bot(bot_name)
        if latest:
            return latest
    if session.last_inspection:
        return session.last_inspection
    return None


def build_explain_facts(
    query: ExplainQuery,
    session: ChatSession,
) -> tuple[str, list[RagChunk], CaseSnapshot | None]:
    """Return structured facts text, RAG chunks, and matched case (if any)."""
    snapshot = _resolve_snapshot(session, query.bot_name)
    if not snapshot:
        return (
            "暂无可用巡检报告。请先执行一次巡检，例如：@bot检查员 巡检 p0 demo-bot",
            retrieve(query.raw_text or "巡检判据"),
            None,
        )

    case = find_case_in_snapshot(
        snapshot,
        case_id=query.case_id,
        issue_id=query.issue_id,
        case_name_hint=query.case_name_hint,
    )

    rag_query = " ".join(
        filter(
            None,
            [
                query.raw_text,
                query.case_id,
                case.case_name if case else "",
                case.case_id if case else "",
            ],
        )
    )
    chunks = retrieve(rag_query or "断言 permission_hint reply_within")

    lines = [
        f"Bot：{snapshot.bot_name}",
        f"套件：{snapshot.suite}",
        f"报告：{snapshot.md_path}",
        f"通过/失败：{snapshot.pass_count} 通过，{snapshot.fail_count} 失败",
    ]

    if case:
        lines.extend(_format_case_facts(case))
    elif query.issue_id or query.case_id:
        lines.append(f"未在报告中找到匹配项（issue={query.issue_id or '-'} case={query.case_id or '-'}）")
        if snapshot.failed_cases:
            lines.append("最近失败项：")
            for item in snapshot.failed_cases[:5]:
                lines.append(f"- {item.issue_id} {item.case_name}（{item.case_id}）")
    else:
        lines.append("最近失败项摘要：")
        for item in snapshot.failed_cases[:8]:
            lines.append(f"- {item.issue_id} {item.case_name}：{item.message or item.status}")

    return "\n".join(lines), chunks, case


def _format_case_facts(case: CaseSnapshot) -> list[str]:
    lines = [
        "",
        f"用例：{case.case_name}（{case.case_id}）",
        f"问题编号：{case.issue_id or '（非失败项）'}",
        f"结果：{case.status}",
    ]
    if case.message:
        lines.append(f"判定说明：{case.message}")
    if case.expected:
        lines.append(f"期望：{case.expected[:400]}")
    if case.actual:
        lines.append(f"实际：{case.actual[:600]}")
    lines.append(
        "责任归因提示：若实际回复与飞书客户端所见不一致，可能是 API 卡片格式或完成态识别问题；"
        "若 Bot 已正确回复但判据过严，可讨论调整断言或测试资产。"
    )
    return lines


def render_template_reply(
    user_text: str,
    facts: str,
    chunks: list[RagChunk],
    *,
    mode: str = "explain",
) -> str:
    """Deterministic reply when LLM is unavailable."""
    header = "【巡检解读】" if mode == "explain" else "【检测建议】"
    parts = [header, "", facts]

    if chunks:
        parts.extend(["", "相关检测标准（摘自清单）："])
        for chunk in chunks[:2]:
            excerpt = chunk.content.replace("\n", " ").strip()[:280]
            parts.append(f"- {chunk.title}：{excerpt}…")

    parts.extend(
        [
            "",
            "如需复测：@bot检查员 巡检 p0 <Bot名>",
            "如需逐项解释：@bot检查员 解释 <用例ID> 或 为什么 ISS-001",
        ]
    )
    return "\n".join(parts)
