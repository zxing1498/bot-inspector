"""Data models for test execution and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TestStatus(str, Enum):
    PASS = "通过"
    FAIL = "不通过"
    NA = "不适用"
    PENDING_PERM = "待确认权限"
    PENDING_FIX = "待整改"
    MANUAL = "待人工确认"


@dataclass
class BotConfig:
    name: str
    app_id: str
    owner: str
    env: str
    target_app_id: str = ""
    open_id: str = ""  # 被测 Bot 的 open_id，用于群内 @（/bot/v3/info 仅能查本应用）
    chats: dict[str, str] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    backend: dict[str, Any] = field(default_factory=dict)
    test_assets: dict[str, str] = field(default_factory=dict)
    accounts: dict[str, str] = field(default_factory=dict)
    feishu: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCaseDef:
    id: str
    name: str
    section: str
    capabilities: list[str]
    prompt: str = ""
    channel: str = "normal_group"
    at_bot: bool = False
    in_thread: bool = False
    attach_doc: str = ""
    attach_file: str = ""
    account: str = ""
    burst_count: int = 0
    extra_text: str = ""
    repeat_extra: int = 0
    probe: str = ""
    report_section: str = ""
    difficulty: str = ""  # simple | medium | heavy → config/environments.yaml timeout_tiers
    assertions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReplyInfo:
    message_id: str = ""
    msg_type: str = "text"
    content: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    latency_sec: float = 0.0
    thread_id: str = ""
    root_id: str = ""


@dataclass
class TestResult:
    case_id: str
    case_name: str
    section: str
    status: TestStatus
    message: str = ""
    latency_sec: float = 0.0
    repro_steps: str = ""
    expected: str = ""
    actual: str = ""
    severity: str = "P1"
    report_section: str = ""
    probe_data: dict[str, Any] = field(default_factory=dict)
    replies: list[ReplyInfo] = field(default_factory=list)


@dataclass
class BotRunReport:
    bot_name: str
    owner: str
    env: str
    started_at: datetime
    suite: str = "p0"
    suite_names: list[str] = field(default_factory=list)
    finished_at: datetime | None = None
    results: list[TestResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    cancelled: bool = False
    run_id: str = ""
    owner_open_id: str = ""
    trigger_chat_id: str = ""

    def p0_pass_count(self) -> int:
        p0 = [r for r in self.results if r.section == "p0" and r.status == TestStatus.PASS]
        return len(p0)

    def p0_total(self) -> int:
        return len([r for r in self.results if r.section == "p0" and r.status != TestStatus.NA])

    def run_pass_count(self) -> int:
        return len([r for r in self.results if r.status == TestStatus.PASS])

    def run_total(self) -> int:
        return len([r for r in self.results if r.status != TestStatus.NA])

    def section_summary(self, section: str) -> str:
        items = [
            r
            for r in self.results
            if r.status != TestStatus.NA
            and (r.section == section or r.report_section == section)
        ]
        if not items:
            return "不适用"
        fails = [r for r in items if r.status == TestStatus.FAIL]
        if fails:
            return "不通过"
        pending = [r for r in items if r.status == TestStatus.PENDING_FIX]
        if pending:
            return "待整改"
        manual = [r for r in items if r.status == TestStatus.MANUAL]
        if manual:
            return "待整改"
        return "通过"
