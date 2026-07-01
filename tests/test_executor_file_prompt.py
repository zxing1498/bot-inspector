from pathlib import Path

from src.tests.executor import TestExecutor


class _FakeClient:
    pass


def test_file_followup_prompt_includes_filename():
    executor = TestExecutor(_FakeClient())
    text = executor._file_followup_prompt("请处理这个文件", Path("corrupt.bin"))
    assert "corrupt.bin" in text
    assert "请处理这个文件" in text


def test_file_followup_prompt_skips_duplicate_name():
    executor = TestExecutor(_FakeClient())
    text = executor._file_followup_prompt("请处理 corrupt.bin", Path("corrupt.bin"))
    assert text == "请处理 corrupt.bin"
