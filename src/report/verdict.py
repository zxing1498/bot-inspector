"""Align report verdict banner with P0 outcomes and composite score."""

from __future__ import annotations

from src.models import BotRunReport, TestStatus
from src.report.scoring import InspectionScorecard


def derive_verdict(
    report: BotRunReport,
    scorecard: InspectionScorecard,
) -> tuple[str, str, str]:
    """Return (verdict_class, title, description)."""
    p0_results = [r for r in report.results if r.section == "p0" and r.status != TestStatus.NA]
    p0_fails = [r for r in p0_results if r.status == TestStatus.FAIL]
    p0_pending = [r for r in p0_results if r.status == TestStatus.PENDING_FIX]
    p0_manual = [r for r in p0_results if r.status == TestStatus.MANUAL]

    overall = scorecard.overall
    grade = scorecard.grade_label
    soft_count = len(p0_pending) + len(p0_manual)

    if p0_fails:
        return (
            "fail",
            "存在阻塞问题，需整改后复测",
            (
                f"P0 有 {len(p0_fails)} 项未通过；综合评分 {overall:.1f} 分。"
                "请优先处理下方问题记录后复测。"
            ),
        )

    if overall >= 80:
        if soft_count:
            return (
                "pass",
                f"优秀，可继续使用（{grade}）",
                (
                    f"综合评分 {overall:.1f} 分；P0 无阻塞失败。"
                    f"有 {soft_count} 项首响/体验类待优化，不影响核心能力判定。"
                ),
            )
        return (
            "pass",
            f"可以上线 / 继续使用（{grade}）",
            f"综合评分 {overall:.1f} 分；P0 必测全部通过，未发现阻塞问题。",
        )

    if soft_count and overall >= 60:
        return (
            "partial",
            "存在问题，但不影响核心使用",
            (
                f"综合评分 {overall:.1f} 分；P0 无阻塞失败，"
                f"但有 {soft_count} 项待整改或需人工确认。"
            ),
        )

    return (
        "fail",
        "需整改后复测",
        f"综合评分 {overall:.1f} 分偏低，请处理失败项与待整改项后复测。",
    )
