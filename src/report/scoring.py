"""Percentile scoring for bot inspection reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models import BotRunReport, TestCaseDef, TestResult, TestStatus
from src.registry import load_all_suites, load_env_config
from src.timeout_tiers import apply_timeout_tier

DIMENSION_DEFS: tuple[tuple[str, str, float], ...] = (
    ("response_timeliness", "响应及时性", 0.25),
    ("completion_timeliness", "任务完成及时性", 0.25),
    ("task_completion", "任务完成度", 0.35),
    ("interaction_ux", "交互体验", 0.15),
)

GRADE_BANDS: tuple[tuple[float, str, str], ...] = (
    (90, "A", "优秀"),
    (80, "B", "良好"),
    (70, "C", "合格"),
    (60, "D", "待改进"),
    (0, "F", "不合格"),
)


@dataclass
class CaseScoreBreakdown:
    case_id: str
    case_name: str
    section: str
    weight: float
    response_timeliness: float | None = None
    completion_timeliness: float | None = None
    task_completion: float = 0.0
    interaction_ux: float | None = None


@dataclass
class DimensionScore:
    key: str
    label: str
    weight: float
    effective_weight: float
    score: float
    case_count: int
    summary: str = ""


@dataclass
class InspectionScorecard:
    overall: float
    grade: str
    grade_label: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    case_breakdowns: list[CaseScoreBreakdown] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 1),
            "grade": self.grade,
            "grade_label": self.grade_label,
            "dimensions": [
                {
                    "key": d.key,
                    "label": d.label,
                    "weight_pct": int(d.weight * 100),
                    "effective_weight_pct": int(d.effective_weight * 100),
                    "score": round(d.score, 1),
                    "case_count": d.case_count,
                    "summary": d.summary,
                }
                for d in self.dimensions
            ],
            "case_breakdowns": [
                {
                    "case_id": c.case_id,
                    "case_name": c.case_name,
                    "section": c.section,
                    "weight": c.weight,
                    "response_timeliness": _fmt_optional(c.response_timeliness),
                    "completion_timeliness": _fmt_optional(c.completion_timeliness),
                    "task_completion": round(c.task_completion, 1),
                    "interaction_ux": _fmt_optional(c.interaction_ux),
                }
                for c in self.case_breakdowns
            ],
        }


def _fmt_optional(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def grade_for_score(score: float) -> tuple[str, str]:
    for threshold, letter, label in GRADE_BANDS:
        if score >= threshold:
            return letter, label
    return "F", "不合格"


def _cases_by_id() -> dict[str, TestCaseDef]:
    out: dict[str, TestCaseDef] = {}
    for cases in load_all_suites().values():
        for case in cases:
            out[case.id] = case
    return out


def _assertion_types(case: TestCaseDef) -> set[str]:
    return {rule.get("type", "") for rule in case.assertions}


def _tiered_case(case: TestCaseDef) -> TestCaseDef:
    return apply_timeout_tier(case, load_env_config())


def _threshold_from_assertions(case: TestCaseDef, atype: str, default: float) -> float:
    for rule in case.assertions:
        if rule.get("type") == atype:
            return float(rule.get("threshold_sec", default))
    return default


def _timeout_from_assertions(case: TestCaseDef, probe: dict[str, Any], default: float) -> float:
    for rule in case.assertions:
        if rule.get("type") == "reply_within":
            return float(rule.get("timeout_sec", default))
    wait = probe.get("completion_wait_sec")
    if wait is not None:
        return float(wait)
    return default


def _case_weight(result: TestResult) -> float:
    return 2.0 if result.section == "p0" else 1.0


def _is_interaction_case(case: TestCaseDef) -> bool:
    if case.prompt or case.at_bot or case.attach_doc or case.attach_file:
        return True
    return case.section in ("messaging", "docs", "files", "security", "p0")


def _latency_only_pending(result: TestResult) -> bool:
    msg = (result.message or "").lower()
    markers = ("首响", "耗时", "latency", "超过", "秒")
    return result.status == TestStatus.PENDING_FIX and any(m in msg for m in markers)


def _curve_fast_ok(elapsed: float, threshold: float) -> float:
    if elapsed <= threshold:
        return 100.0
    if elapsed <= threshold * 2:
        ratio = (elapsed - threshold) / threshold
        return 100.0 - ratio * 40.0
    if elapsed <= threshold * 4:
        ratio = (elapsed - threshold * 2) / (threshold * 2)
        return 60.0 - ratio * 40.0
    return max(0.0, 20.0 - (elapsed - threshold * 4) / threshold * 10.0)


def _curve_completion_ok(elapsed: float, timeout: float) -> float:
    if timeout <= 0:
        return 0.0
    if elapsed <= timeout * 0.5:
        return 100.0
    if elapsed <= timeout:
        ratio = (elapsed - timeout * 0.5) / (timeout * 0.5)
        return 100.0 - ratio * 25.0
    if elapsed <= timeout * 1.2:
        ratio = (elapsed - timeout) / (timeout * 0.2)
        return 75.0 - ratio * 45.0
    return max(0.0, 30.0 - (elapsed - timeout * 1.2) / timeout * 30.0)


def _final_reply_latency(result: TestResult) -> float | None:
    if not result.replies:
        return None
    return max(r.latency_sec for r in result.replies)


def _score_response_timeliness(result: TestResult, case: TestCaseDef) -> float | None:
    types = _assertion_types(case)
    probe = result.probe_data or {}
    threshold = _threshold_from_assertions(case, "first_ack_within", 15.0)
    if "latency_warning" in types:
        threshold = min(
            threshold,
            _threshold_from_assertions(case, "latency_warning", threshold),
        )

    first_ack = probe.get("first_ack_sec")
    if first_ack is not None:
        return _curve_fast_ok(float(first_ack), threshold)

    if result.replies:
        return _curve_fast_ok(result.replies[0].latency_sec, threshold)

    if not _is_interaction_case(case):
        if result.status == TestStatus.PASS:
            return 100.0
        if result.status == TestStatus.FAIL:
            return 0.0
        return 70.0

    if result.status == TestStatus.FAIL and not result.replies:
        return 0.0
    return None


def _score_completion_timeliness(result: TestResult, case: TestCaseDef) -> float | None:
    types = _assertion_types(case)
    if "reply_within" not in types:
        return None

    probe = result.probe_data or {}
    if probe.get("completion_timeout"):
        return 15.0

    timeout = _timeout_from_assertions(case, probe, 90.0)
    latency = _final_reply_latency(result)
    if latency is None:
        return 0.0 if result.status == TestStatus.FAIL else None
    return _curve_completion_ok(latency, timeout)


def _score_task_completion(result: TestResult) -> float:
    status = result.status
    if status == TestStatus.PASS:
        return 100.0
    if status == TestStatus.FAIL:
        return 0.0
    if status == TestStatus.PENDING_FIX:
        return 80.0 if _latency_only_pending(result) else 55.0
    if status == TestStatus.MANUAL:
        return 50.0
    if status == TestStatus.PENDING_PERM:
        return 40.0
    return 0.0


def _score_interaction_ux(result: TestResult, case: TestCaseDef) -> float | None:
    if not _is_interaction_case(case):
        return None

    base = _score_task_completion(result)
    probe = result.probe_data or {}
    actual = (result.actual or "") + (result.message or "")

    penalty = 0.0
    if any(x in actual for x in ("系统错误", "500", "traceback", "Internal Server Error")):
        penalty += 35.0
    if probe.get("completion_timeout"):
        penalty += 25.0
    if _latency_only_pending(result):
        penalty += 10.0
    if result.status == TestStatus.FAIL and any(
        x in actual for x in ("已读取", "泄露", "无权限文档内容")
    ):
        penalty = max(penalty, 0.0)

    return max(0.0, min(100.0, base - penalty))


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return sum(score * w for score, w in pairs) / total_w


def _dimension_summary(key: str, score: float, case_count: int) -> str:
    if case_count == 0:
        return "本轮无适用用例"
    if key == "response_timeliness":
        if score >= 90:
            return f"首响表现优秀（{case_count} 项）"
        if score >= 70:
            return f"首响整体可接受，个别用例偏慢（{case_count} 项）"
        return f"首响偏慢或未响应（{case_count} 项）"
    if key == "completion_timeliness":
        if score >= 90:
            return f"任务在时限内完成（{case_count} 项）"
        if score >= 70:
            return f"多数任务按时完成，少数接近超时（{case_count} 项）"
        return f"存在超时或仅中间状态（{case_count} 项）"
    if key == "task_completion":
        if score >= 90:
            return f"功能完成度高（{case_count} 项）"
        if score >= 70:
            return f"核心能力基本达成，有少量待整改（{case_count} 项）"
        return f"多项功能未达标（{case_count} 项）"
    if score >= 90:
        return f"交互友好、错误提示得体（{case_count} 项）"
    if score >= 70:
        return f"交互尚可，体验有优化空间（{case_count} 项）"
    return f"交互体验欠佳（系统错误/长时间无反馈等，{case_count} 项）"


def compute_inspection_score(report: BotRunReport) -> InspectionScorecard:
    cases_by_id = _cases_by_id()
    breakdowns: list[CaseScoreBreakdown] = []

    dim_values: dict[str, list[tuple[float, float]]] = {k: [] for k, _, _ in DIMENSION_DEFS}

    for result in report.results:
        if result.status == TestStatus.NA:
            continue
        raw_case = cases_by_id.get(result.case_id)
        if not raw_case:
            continue
        case = _tiered_case(raw_case)
        weight = _case_weight(result)

        response = _score_response_timeliness(result, case)
        completion = _score_completion_timeliness(result, case)
        task = _score_task_completion(result)
        ux = _score_interaction_ux(result, case)

        breakdowns.append(
            CaseScoreBreakdown(
                case_id=result.case_id,
                case_name=result.case_name,
                section=result.section,
                weight=weight,
                response_timeliness=response,
                completion_timeliness=completion,
                task_completion=task,
                interaction_ux=ux,
            )
        )

        if response is not None:
            dim_values["response_timeliness"].append((response, weight))
        if completion is not None:
            dim_values["completion_timeliness"].append((completion, weight))
        dim_values["task_completion"].append((task, weight))
        if ux is not None:
            dim_values["interaction_ux"].append((ux, weight))

    dimensions: list[DimensionScore] = []
    active_weight = 0.0
    dim_scores: dict[str, float] = {}

    for key, label, weight in DIMENSION_DEFS:
        mean = _weighted_mean(dim_values[key])
        case_count = len(dim_values[key])
        if mean is None:
            dimensions.append(
                DimensionScore(
                    key=key,
                    label=label,
                    weight=weight,
                    effective_weight=0.0,
                    score=0.0,
                    case_count=0,
                    summary="本轮无适用用例",
                )
            )
            continue
        dim_scores[key] = mean
        active_weight += weight
        dimensions.append(
            DimensionScore(
                key=key,
                label=label,
                weight=weight,
                effective_weight=weight,
                score=mean,
                case_count=case_count,
                summary=_dimension_summary(key, mean, case_count),
            )
        )

    overall = 0.0
    if active_weight > 0:
        for dim in dimensions:
            if dim.case_count == 0:
                continue
            dim.effective_weight = dim.weight / active_weight
            overall += dim.score * dim.effective_weight
    else:
        overall = 0.0

    overall = round(overall, 1)
    grade, grade_label = grade_for_score(overall)
    return InspectionScorecard(
        overall=overall,
        grade=grade,
        grade_label=grade_label,
        dimensions=dimensions,
        case_breakdowns=breakdowns,
    )


def format_score_line(scorecard: InspectionScorecard) -> str:
    parts = [f"综合 {scorecard.overall:.1f} 分（{scorecard.grade_label}）"]
    for dim in scorecard.dimensions:
        if dim.case_count == 0:
            continue
        parts.append(f"{dim.label} {dim.score:.1f}")
    return " · ".join(parts)
