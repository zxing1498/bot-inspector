import os

import pytest

from src.chat_trigger import (
    build_help_text,
    build_startup_instructions,
    is_usage_query,
    parse_command,
    parse_pause_command,
    resolve_pause_bot,
)


def test_startup_instructions():
    text = build_startup_instructions()
    assert "首次测试" in text
    assert "已配置巡检" in text
    assert "帮助" in text
    assert "测试" in text


def test_build_help_text_uses_inspector_name(monkeypatch):
    monkeypatch.setenv("INSPECTOR_AT_NAME", "bot检查员")
    text = build_help_text()
    assert "bot检查员" in text
    assert "尾程时效质量助手" not in text
    assert "可用性、有效性" in text


def test_is_usage_query():
    assert is_usage_query("帮助")
    assert is_usage_query("help")
    assert is_usage_query("你可以怎么使用")
    assert is_usage_query("你可以干什么")
    assert is_usage_query("我要怎么用你")
    assert not is_usage_query("巡检 p0")
    assert not is_usage_query("测试 foo")


def test_parse_default():
    err, suite, bot = parse_command("巡检")
    assert err is None
    assert suite == "p0"
    assert bot == "all"


def test_parse_full_bot():
    err, suite, bot = parse_command("巡检 full 尾程hermes-ada")
    assert err is None
    assert suite == "full"
    assert bot == "尾程hermes-ada"


def test_parse_inspect_prefix():
    err, suite, bot = parse_command("/inspect p0")
    assert err is None
    assert suite == "p0"


def test_parse_help():
    err, _, _ = parse_command("帮助")
    assert err == "__help__"


def test_parse_usage_query_as_help():
    err, _, _ = parse_command("你可以干什么")
    assert err == "__help__"


def test_build_help_text_unrecognized():
    text = build_help_text(unrecognized=True)
    assert "暂未识别为巡检指令" in text
    assert "解释" in text
    assert "可用性、有效性" in text


def test_unrecognized_at_mention_gets_help():
    err, suite, bot = parse_command("你好")
    assert err is None and not suite


def test_empty_at_mention_gets_help():
    err, suite, bot = parse_command("")
    assert err is None and not suite


def test_parse_pause_command():
    assert parse_pause_command("暂停对demo-bot的巡检") == "demo-bot"
    assert parse_pause_command("暂停 demo-bot") == "demo-bot"
    assert parse_pause_command("停止巡检 demo-bot") == "demo-bot"
    assert parse_pause_command("中断 尾程hermes-ada") == "尾程hermes-ada"
    assert parse_pause_command("暂停") == ""
    assert parse_pause_command("取消测试") is None
    assert parse_pause_command("巡检 p0") is None


def test_resolve_pause_bot(monkeypatch):
    from src.models import BotConfig

    def fake_load_bots():
        return [
            BotConfig(name="demo-bot", app_id="", owner="", env="staging"),
            BotConfig(name="尾程hermes-ada", app_id="", owner="", env="staging"),
        ]

    def fake_load_bot(name):
        for b in fake_load_bots():
            if b.name == name:
                return b
        return None

    monkeypatch.setattr("src.chat_trigger.load_bots", fake_load_bots)
    monkeypatch.setattr("src.chat_trigger.load_bot", fake_load_bot)
    assert resolve_pause_bot("demo-bot") == "demo-bot"
    assert resolve_pause_bot("hermes") == "尾程hermes-ada"


def test_build_help_text_includes_pause():
    assert "暂停" in build_help_text()


def test_is_stale_command_by_age():
    from types import SimpleNamespace

    from src.chat_trigger import _is_stale_command, _message_age_sec

    fresh = SimpleNamespace(create_time=str(int(__import__("time").time() * 1000)))
    old = SimpleNamespace(
        create_time=str(int((__import__("time").time() - 600) * 1000))
    )
    assert _message_age_sec(fresh) is not None
    assert _message_age_sec(fresh) < 60
    assert _is_stale_command(old) is True


def test_pid_alive_current_process():
    from src.chat_trigger import _pid_alive

    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(999999999) is False


def test_acquire_instance_lock_exits_when_other_alive(monkeypatch, tmp_path):
    import src.chat_trigger as ct

    lock_path = tmp_path / "chat_trigger.lock"
    lock_path.write_text("424242", encoding="utf-8")
    monkeypatch.setattr(ct, "_instance_lock_path", lambda: lock_path)
    monkeypatch.setattr(ct, "_pid_alive", lambda pid: pid == 424242)

    with pytest.raises(SystemExit) as exc:
        ct._acquire_instance_lock()
    assert exc.value.code == 1


def test_acquire_instance_lock_replaces_stale(monkeypatch, tmp_path):
    import src.chat_trigger as ct

    lock_path = tmp_path / "chat_trigger.lock"
    lock_path.write_text("424242", encoding="utf-8")
    monkeypatch.setattr(ct, "_instance_lock_path", lambda: lock_path)
    monkeypatch.setattr(ct, "_pid_alive", lambda pid: False)
    ct.atexit.register = lambda fn: None  # type: ignore[assignment]

    ct._acquire_instance_lock()
    assert lock_path.read_text(encoding="utf-8") == str(os.getpid())
