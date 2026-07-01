"""Callback URL reachability probe."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class CallbackResult:
    ok: bool
    status_code: int = 0
    message: str = ""


def check_callback(url: str, timeout: float = 10.0) -> CallbackResult:
    if not url:
        return CallbackResult(ok=False, message="未配置 callback_url")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            # Feishu challenge verification expects POST; HEAD/GET for reachability
            resp = client.head(url)
            if resp.status_code >= 400:
                resp = client.get(url)
            ok = resp.status_code < 500
            return CallbackResult(
                ok=ok,
                status_code=resp.status_code,
                message="reachable" if ok else resp.text[:200],
            )
    except Exception as exc:
        return CallbackResult(ok=False, message=str(exc))
