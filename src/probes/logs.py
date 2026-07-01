"""Log trace probe — supports Elasticsearch and HTTP log API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class LogTraceResult:
    ok: bool
    trace_id: str = ""
    message: str = ""
    hits: int = 0


def query_elasticsearch(
    url: str,
    index: str,
    trace_field: str,
    *,
    since_minutes: int = 5,
    bot_name: str = "",
) -> LogTraceResult:
    if not url:
        return LogTraceResult(ok=False, message="未配置 ES URL")

    query: dict[str, Any] = {
        "size": 5,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": f"now-{since_minutes}m"}}},
                ]
            }
        },
    }
    if bot_name:
        query["query"]["bool"]["must"].append({"match": {"bot_name": bot_name}})

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{url.rstrip('/')}/{index}/_search", json=query)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return LogTraceResult(ok=False, message="未找到近期日志", hits=0)
            source = hits[0].get("_source", {})
            trace = source.get(trace_field, "") or source.get("request_id", "")
            if trace:
                return LogTraceResult(ok=True, trace_id=str(trace), hits=len(hits))
            return LogTraceResult(
                ok=False,
                message=f"日志缺少 {trace_field} 字段",
                hits=len(hits),
            )
    except Exception as exc:
        return LogTraceResult(ok=False, message=str(exc))


def query_http_logs(
    url: str,
    trace_field: str,
    *,
    headers: dict[str, str] | None = None,
) -> LogTraceResult:
    """Query a simple HTTP log API that returns JSON array or {items: [...]}."""
    if not url:
        return LogTraceResult(ok=False, message="未配置日志 API URL")
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers or {})
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", data.get("logs", []))
            if not items:
                return LogTraceResult(ok=False, message="日志 API 返回空列表")
            latest = items[0] if isinstance(items[0], dict) else {}
            trace = latest.get(trace_field, "") or latest.get("request_id", "")
            if trace:
                return LogTraceResult(ok=True, trace_id=str(trace), hits=len(items))
            return LogTraceResult(
                ok=False,
                message=f"日志 API 响应缺少 {trace_field} 字段",
                hits=len(items),
            )
    except Exception as exc:
        return LogTraceResult(ok=False, message=str(exc))


def query_logs(config: dict[str, Any], *, bot_name: str = "") -> LogTraceResult:
    log_type = config.get("type", "")
    if log_type in ("skip", "none", "disabled"):
        return LogTraceResult(
            ok=True,
            trace_id="skipped",
            message="未部署日志服务，已跳过（不影响其他测试）",
        )
    if log_type == "elasticsearch":
        return query_elasticsearch(
            config.get("url", ""),
            config.get("index", "bot-logs"),
            config.get("trace_field", "request_id"),
            bot_name=bot_name,
        )
    if log_type == "http":
        return query_http_logs(
            config.get("url", ""),
            config.get("trace_field", "request_id"),
            headers=config.get("headers"),
        )
    return LogTraceResult(ok=False, message=f"不支持的日志类型: {log_type}")
