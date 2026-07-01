"""Render HTML sample from an existing report directory (for preview)."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.models import BotRunReport, TestResult, TestStatus
from src.registry import ROOT, load_test_cases
from src.report.generator import generate_report
from src.report.owner_display import _extract_open_id_prefix, is_open_id

load_dotenv(ROOT / ".env")

STATUS_MAP = {
    "通过": TestStatus.PASS,
    "不通过": TestStatus.FAIL,
    "待人工确认": TestStatus.MANUAL,
    "待整改": TestStatus.PENDING_FIX,
    "不适用": TestStatus.NA,
}


def _parse_md_report(md_path: Path) -> BotRunReport:
    text = md_path.read_text(encoding="utf-8")
    owner = re.search(r"\*\*负责人\*\*:\s*(.+)", text)
    env = re.search(r"\*\*环境\*\*:\s*(\S+)", text)
    times = re.search(
        r"\*\*巡检时间\*\*:\s*([\d\- :]+)\s*—\s*([\d\- :]+)", text
    )
    run_id = re.search(r"\*\*本轮编号\*\*:\s*`([^`]+)`", text)
    meta = re.search(
        r"<!--\s*owner_open_id:\s*(\S+)\s+trigger_chat_id:\s*(\S+)\s*-->",
        text,
    )
    owner_raw = owner.group(1).strip() if owner else ""
    owner_open_id = meta.group(1).strip() if meta else ""
    trigger_chat_id = meta.group(2).strip() if meta else ""
    if not owner_open_id:
        owner_open_id = _extract_open_id_prefix(owner_raw) or (
            owner_raw if is_open_id(owner_raw) else ""
        )
    if not trigger_chat_id:
        trigger_chat_id = os.getenv("TRIGGER_CHAT_IDS", "").split(",")[0].strip()

    bot_name = md_path.stem

    report = BotRunReport(
        bot_name=bot_name,
        owner=owner_raw,
        env=env.group(1).strip() if env else "staging",
        started_at=datetime.strptime(times.group(1).strip(), "%Y-%m-%d %H:%M:%S")
        if times
        else datetime.now(),
        finished_at=datetime.strptime(times.group(2).strip(), "%Y-%m-%d %H:%M:%S")
        if times
        else datetime.now(),
        suite="p0",
        run_id=run_id.group(1).strip() if run_id else "",
        owner_open_id=owner_open_id,
        trigger_chat_id=trigger_chat_id,
    )

    p0_cases = load_test_cases("p0")
    p0_block = re.search(
        r"## 2\. P0 必测清单\s*\n\n\|.*?\n\|[-| ]+\|\n(.*?)\n\n---",
        text,
        re.S,
    )
    latency_by_name: dict[str, float] = {}
    for block in re.finditer(
        r"### \d+\. [^\n]+\n\n\| 检查项 \| 结果 \| 耗时\(s\) \| 备注 \|\n\|[-| ]+\|\n(.*?)(?=\n\n### |\n---)",
        text,
        re.S,
    ):
        for line in block.group(1).strip().splitlines():
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) < 3:
                continue
            try:
                latency_by_name[cols[0]] = float(cols[2])
            except ValueError:
                pass

    if p0_block:
        for line in p0_block.group(1).strip().splitlines():
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) < 4:
                continue
            row_no = cols[0]
            try:
                case_id = p0_cases[int(row_no) - 1].id
                report_section = p0_cases[int(row_no) - 1].report_section
            except (ValueError, IndexError):
                case_id = f"p0_{row_no}"
                report_section = ""
            case_name, status_raw, message = cols[1], cols[2], cols[3]
            report.results.append(
                TestResult(
                    case_id=case_id,
                    case_name=case_name,
                    section="p0",
                    report_section=report_section,
                    status=STATUS_MAP.get(status_raw, TestStatus.FAIL),
                    message=message,
                    latency_sec=latency_by_name.get(case_name, 0.0),
                    severity="P0",
                )
            )

    sugg_block = re.search(r"## 5\. 优化建议\s*\n\n(.*?)\n\n---", text, re.S)
    if sugg_block:
        report.suggestions = [
            ln.strip()[2:].strip()
            for ln in sugg_block.group(1).splitlines()
            if ln.strip().startswith("- ")
        ]

    return report


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) <= 1:
        print("用法: python -m src.report.sample <path/to/report.md>", file=sys.stderr)
        return 2
    md = Path(argv[1])
    if not md.exists():
        print(f"报告不存在: {md}", file=sys.stderr)
        return 1
    report = _parse_md_report(md)
    paths = generate_report(report, md.parent)
    print(f"HTML 样例: {paths.html}")
    print(f"Markdown: {paths.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
