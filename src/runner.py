"""CLI runner — parallel bot inspection with report generation."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.feishu.client import FeishuClient
from src.inspection_anchors import format_run_summary_text
from src.inspection_cancel import mark_active, mark_inactive
from src.inspection_lock import (
    inspection_lock_holder,
    release_inspection_lock,
    try_acquire_inspection_lock,
)
from src.models import BotRunReport, TestStatus
from src.registry import load_all_suites, load_bot, load_bots, load_test_cases
from src.report.generator import ReportPaths, generate_report
from src.report.summary_cards import (
    build_inspection_summary_card,
    format_summary_text,
)
from src.tests.executor import TestExecutor

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

SUITE_ALIASES = {
    "p0": ["p0"],
    "full": ["p0", "messaging", "docs", "files", "ops", "security", "config"],
    "api": ["p0", "messaging", "docs", "files", "ops", "security", "config"],
}


def resolve_suites(suite_arg: str) -> list[str]:
    if suite_arg in SUITE_ALIASES:
        return SUITE_ALIASES[suite_arg]
    return [s.strip() for s in suite_arg.split(",") if s.strip()]


def resolve_report_owner(
    *,
    triggered_by: str = "",
    triggered_by_open_id: str = "",
    bot_owner: str = "",
    client: FeishuClient | None = None,
    trigger_chat_id: str = "",
) -> str:
    from src.report.owner_display import resolve_report_owner as _resolve

    return _resolve(
        triggered_by=triggered_by,
        triggered_by_open_id=triggered_by_open_id,
        bot_owner=bot_owner,
        client=client,
        chat_id=trigger_chat_id,
    )


def collect_cases(suite_names: list[str]) -> list:
    cases = []
    seen = set()
    for name in suite_names:
        for case in load_test_cases(name):
            if case.id not in seen:
                seen.add(case.id)
                cases.append(case)
    return cases


def run_bot(
    bot_name: str,
    cases: list,
    *,
    dry_run: bool,
    output_dir: Path | None,
    suite: str = "p0",
    suite_names: list[str] | None = None,
    triggered_by: str = "",
    triggered_by_open_id: str = "",
    trigger_chat_id: str = "",
) -> tuple[BotRunReport, ReportPaths]:
    bot = load_bot(bot_name)
    if not bot:
        raise ValueError(f"未找到 Bot: {bot_name}")

    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not dry_run and (not app_id or not app_secret):
        raise RuntimeError("请配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET（见 .env.example）")

    if not dry_run:
        if not try_acquire_inspection_lock(bot_name):
            holder = inspection_lock_holder(bot_name) or "其他进程"
            raise RuntimeError(
                f"「{bot_name}」已有巡检在进行中（{holder}），"
                f"请稍候完成或发送「暂停 {bot_name}」后再试"
            )

    mark_active(bot_name)
    try:
        client = FeishuClient(app_id, app_secret)
        executor = TestExecutor(client, dry_run=dry_run)
        report = executor.run_suite(
            bot,
            cases,
            suite=suite,
            suite_names=suite_names or resolve_suites(suite),
            run_owner=resolve_report_owner(
                triggered_by=triggered_by,
                triggered_by_open_id=triggered_by_open_id,
                bot_owner=bot.owner,
                client=client,
                trigger_chat_id=trigger_chat_id,
            ),
            owner_open_id=triggered_by_open_id,
            trigger_chat_id=trigger_chat_id,
        )
        report_paths = generate_report(report, output_dir)
        return report, report_paths
    finally:
        mark_inactive(bot_name)
        if not dry_run:
            release_inspection_lock(bot_name)


def build_summary(reports: list[BotRunReport], *, errors: list[str] | None = None) -> str:
    return format_summary_text(reports, errors=errors)


def notify_summary(
    reports: list[BotRunReport],
    report_paths: list[ReportPaths],
    client: FeishuClient,
    *,
    chat_id: str | None = None,
    errors: list[str] | None = None,
) -> None:
    """Send summary + HTML report once to the target chat."""
    target = chat_id or os.getenv("NOTIFY_CHAT_ID", "")
    if not target:
        return
    deliver_inspection_results(target, reports, report_paths, errors or [], client)


def deliver_inspection_results(
    chat_id: str,
    reports: list[BotRunReport],
    report_paths: list[ReportPaths],
    errors: list[str],
    client: FeishuClient,
) -> None:
    if not reports and errors:
        try:
            client.send_text(
                chat_id,
                "巡检失败：\n" + "\n".join(f"- {e}" for e in errors),
                receive_id_type="chat_id",
            )
        except Exception as exc:
            logger.error("send inspection error notice failed: %s", exc)
        return

    report_date = datetime.now().strftime("%Y-%m-%d")
    for index, report in enumerate(reports):
        card_errors = errors if index == 0 and errors else None
        if report.run_id:
            attention_ids = [
                r.case_id
                for r in report.results
                if r.status
                in (
                    TestStatus.FAIL,
                    TestStatus.PENDING_FIX,
                    TestStatus.MANUAL,
                    TestStatus.PENDING_PERM,
                )
            ]
            try:
                client.send_text(
                    chat_id,
                    format_run_summary_text(
                        report.run_id, report.bot_name, case_ids=attention_ids
                    ),
                    receive_id_type="chat_id",
                )
            except Exception as exc:
                logger.warning("send summary search text failed: %s", exc)
        try:
            client.send_interactive(
                chat_id,
                build_inspection_summary_card(
                    report, report_date=report_date, errors=card_errors
                ),
            )
        except Exception as exc:
            logger.error("send summary card failed: %s", exc)
            client.send_notification(
                chat_id, format_summary_text([report], errors=errors or None)
            )

    for paths in report_paths:
        sent_html = False
        if paths.html.exists():
            try:
                client.send_report_file(chat_id, paths.html)
                sent_html = True
            except Exception as exc:
                logger.error("send html report failed: %s", exc)
                client.send_notification(
                    chat_id,
                    f"⚠️ HTML 报告上传失败（{paths.html.name}）：{exc}",
                )
        if not sent_html and paths.md.exists():
            try:
                client.send_report_file(chat_id, paths.md)
                client.send_notification(
                    chat_id,
                    f"已改发 Markdown 报告（{paths.md.name}），请在电脑上下载后用浏览器打开同目录 HTML。",
                )
            except Exception as exc:
                logger.error("send md report fallback failed: %s", exc)


def run_inspection(
    *,
    bot: str = "all",
    suite: str = "p0",
    dry_run: bool = False,
    parallel: int = 3,
    output_dir: Path | None = None,
    notify: bool = False,
    triggered_by: str = "",
    triggered_by_open_id: str = "",
    trigger_chat_id: str = "",
) -> tuple[list[BotRunReport], list[str], list[ReportPaths]]:
    """Run inspection programmatically. Returns (reports, errors, report_paths)."""
    load_dotenv(ROOT / ".env")

    suite_names = resolve_suites(suite)
    cases = collect_cases(suite_names)
    if not cases:
        raise ValueError(f"未找到套件 {suite} 的用例")

    if bot == "all":
        bot_names = [b.name for b in load_bots()]
    else:
        bot_names = [s.strip() for s in bot.split(",") if s.strip()]

    if not bot_names:
        raise ValueError("bots.yaml 中无 Bot 配置")

    out_dir = output_dir or ROOT / "reports" / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    reports: list[BotRunReport] = []
    report_paths: list[ReportPaths] = []
    errors: list[str] = []

    workers = min(parallel, len(bot_names))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_bot,
                name,
                cases,
                dry_run=dry_run,
                output_dir=out_dir,
                suite=suite,
                suite_names=suite_names,
                triggered_by=triggered_by,
                triggered_by_open_id=triggered_by_open_id,
                trigger_chat_id=trigger_chat_id,
            ): name
            for name in bot_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                report, paths = future.result()
                reports.append(report)
                report_paths.append(paths)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

    if notify and not dry_run:
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if app_id and app_secret:
            notify_summary(reports, report_paths, FeishuClient(app_id, app_secret))

    return reports, errors, report_paths


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="飞书 Bot 自动化巡检")
    parser.add_argument(
        "--bot",
        default="all",
        help="被测 Bot 名称，或 all",
    )
    parser.add_argument(
        "--suite",
        default="p0",
        help="测试套件: p0 | full | api | 逗号分隔套件名",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅加载用例并生成 dry-run 报告，不调用飞书 API",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=3,
        help="并行 Bot 数量",
    )
    parser.add_argument(
        "--output",
        default="",
        help="报告输出目录",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="巡检完成后发送摘要到 NOTIFY_CHAT_ID",
    )
    parser.add_argument(
        "--owner",
        default="",
        help="报告负责人（默认使用 bots.yaml 中的 owner）",
    )
    args = parser.parse_args(argv)

    suite_names = resolve_suites(args.suite)
    cases = collect_cases(suite_names)
    if not cases:
        print(f"未找到套件 {args.suite} 的用例", file=sys.stderr)
        return 1

    bot_names = [b.name for b in load_bots()] if args.bot == "all" else [
        s.strip() for s in args.bot.split(",") if s.strip()
    ]
    print(f"套件: {', '.join(suite_names)} | Bot: {', '.join(bot_names)} | 用例数: {len(cases)}")
    if args.dry_run:
        print("模式: dry-run（不调用飞书 API）")

    output_dir = Path(args.output) if args.output else None
    try:
        reports, errors, report_paths = run_inspection(
            bot=args.bot,
            suite=args.suite,
            dry_run=args.dry_run,
            parallel=args.parallel,
            output_dir=output_dir,
            notify=args.notify,
            triggered_by=args.owner.strip(),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_dir = output_dir or ROOT / "reports" / datetime.now().strftime("%Y-%m-%d")
    for report in reports:
        safe = report.bot_name.replace("/", "_")
        path = out_dir / f"{safe}.html"
        mark = "OK" if report.bot_name not in [e.split(":")[0] for e in errors] else "FAIL"
        print(f"[{mark}] {report.bot_name} -> {path}")

    for err in errors:
        print(f"[FAIL] {err}", file=sys.stderr)

    print("\n" + build_summary(reports))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
