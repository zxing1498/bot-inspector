"""Cross-process lock so only one inspection per bot runs at a time."""

from __future__ import annotations

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_DIR = ROOT / ".cache" / "inspection_locks"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _lock_path(bot_name: str) -> Path:
    safe = bot_name.replace("/", "_").replace("\\", "_")
    return LOCK_DIR / f"{safe}.lock"


def _read_lock(path: Path) -> tuple[int, str, float]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, "", 0.0
    pid = int(lines[0]) if lines and lines[0].strip().isdigit() else 0
    owner = lines[1].strip() if len(lines) > 1 else ""
    try:
        started = float(lines[2]) if len(lines) > 2 else 0.0
    except ValueError:
        started = 0.0
    return pid, owner, started


def inspection_lock_holder(bot_name: str) -> str | None:
    """Return owner label if bot inspection lock is held by a live process."""
    path = _lock_path(bot_name)
    if not path.exists():
        return None
    pid, owner, _ = _read_lock(path)
    if pid and _pid_alive(pid):
        return owner or f"pid={pid}"
    path.unlink(missing_ok=True)
    return None


def try_acquire_inspection_lock(bot_name: str, *, owner: str = "") -> bool:
    """Acquire per-bot inspection lock. Returns False if another run is active."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = _lock_path(bot_name)
    holder = inspection_lock_holder(bot_name)
    if holder:
        return False
    label = owner or f"pid={os.getpid()}"
    path.write_text(f"{os.getpid()}\n{label}\n{time.time():.0f}\n", encoding="utf-8")
    return True


def release_inspection_lock(bot_name: str) -> None:
    path = _lock_path(bot_name)
    try:
        if path.exists():
            pid, _, _ = _read_lock(path)
            if pid in (0, os.getpid()):
                path.unlink(missing_ok=True)
    except OSError:
        pass
