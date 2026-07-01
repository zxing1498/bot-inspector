"""Probe backend health/callback/log endpoints and print config suggestions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

from src.probes.callback import check_callback
from src.probes.health import check_health
from src.probes.logs import query_logs
from src.registry import load_bot


def probe_url(base: str, paths: list[str]) -> tuple[str, str]:
    """Return best health path and callback path."""
    base = base.rstrip("/")
    health_best = base + "/"
    callback_best = base + "/"
    health_ok = False

    for path in paths:
        url = base + path if path.startswith("/") else base + "/" + path
        hr = check_health(url)
        if hr.ok:
            health_best = url
            health_ok = True
            break

    cr = check_callback(callback_best)
    return health_best, callback_best if cr.ok else health_best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探测 Bot 后端并输出推荐配置")
    parser.add_argument("--bot", default="demo-bot", help="Bot 名称")
    parser.add_argument("--base", default="", help="后端根地址，如 https://your-service.example.com")
    args = parser.parse_args(argv)

    bot = load_bot(args.bot)
    if not bot:
        print(f"未找到 Bot: {args.bot}", file=sys.stderr)
        return 1

    base = args.base or bot.backend.get("health_url", "").rstrip("/") or "https://your-service.example.com"
    paths = ["/", "/health", "/healthz", "/api/health", "/ping", "/actuator/health"]

    print(f"探测后端: {base}\n")
    for p in paths:
        url = base + p
        hr = check_health(url)
        mark = "OK" if hr.ok else "FAIL"
        print(f"  [{mark}] health {url} -> {hr.status_code} {hr.message[:50]}")

    cb_paths = ["/", "/feishu/event", "/feishu/webhook", "/webhook", "/callback"]
    for p in cb_paths:
        url = base + p
        cr = check_callback(url)
        mark = "OK" if cr.ok else "FAIL"
        print(f"  [{mark}] callback {url} -> {cr.status_code} {cr.message[:50]}")

    log_cfg = bot.backend.get("log_query", {})
    lr = query_logs(log_cfg, bot_name=bot.name)
    print(f"\n  [{'OK' if lr.ok else 'SKIP/FAIL'}] logs ({log_cfg.get('type')}): {lr.message}")

    health_url, callback_url = probe_url(base, paths)
    print("\n--- 推荐写入 bots.yaml ---")
    print("backend:")
    print(f"  health_url: {health_url}")
    print(f"  callback_url: {callback_url}")
    print("  log_query:")
    print("    type: skip   # 无 ES 时用 skip；有 ES 后改为 elasticsearch")
    print("    # type: elasticsearch")
    print("    # url: ${ES_URL}")
    print("    # index: bot-logs")
    print("    # trace_field: request_id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
