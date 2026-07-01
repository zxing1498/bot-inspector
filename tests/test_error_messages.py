"""Tests for user-facing error messages."""

from src.error_messages import humanize_error, is_technical_message, sanitize_report_text


def test_humanize_windows_path_dict():
    exc = TypeError("unsupported operand type(s) for /: 'WindowsPath' and 'dict'")
    msg = humanize_error(exc)
    assert "file_assets" in msg or "附件" in msg
    assert "WindowsPath" not in msg


def test_humanize_feishu_http_passthrough():
    exc = Exception("Feishu HTTP 400: Bot has NO availability to this user.")
    assert humanize_error(exc).startswith("Feishu HTTP")


def test_sanitize_report_text():
    raw = "unsupported operand type(s) for /: 'WindowsPath' and 'dict'"
    cleaned = sanitize_report_text(raw)
    assert not is_technical_message(cleaned)
