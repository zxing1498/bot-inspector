"""Backend health probe."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class HealthResult:
    ok: bool
    status_code: int = 0
    message: str = ""
    latency_ms: float = 0.0


def check_health(url: str, timeout: float = 10.0) -> HealthResult:
    if not url:
        return HealthResult(ok=False, message="未配置 health_url")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            ok = resp.status_code == 200
            return HealthResult(
                ok=ok,
                status_code=resp.status_code,
                message="OK" if ok else resp.text[:200],
                latency_ms=resp.elapsed.total_seconds() * 1000,
            )
    except Exception as exc:
        return HealthResult(ok=False, message=str(exc))
