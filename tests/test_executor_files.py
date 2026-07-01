"""Tests for file asset resolution in executor."""

from pathlib import Path

from src.models import BotConfig, TestCaseDef
from src.tests.executor import TestExecutor


class _FakeClient:
    pass


def test_resolve_file_asset_from_dict_config(tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    executor = TestExecutor(_FakeClient())
    executor.env_config = {
        "file_assets": {
            "small_txt": {
                "path": str(sample.relative_to(tmp_path)),
                "expect_any": ["hello"],
            }
        }
    }
    monkeypatch.setattr("src.tests.executor.ROOT", tmp_path)

    path, expect, kind = executor._resolve_file_asset("small_txt")
    assert path == sample
    assert expect == ["hello"]
    assert kind == "file"


def test_resolve_file_asset_rejects_dict_path(monkeypatch, tmp_path):
    executor = TestExecutor(_FakeClient())
    executor.env_config = {"file_assets": {"bad": {"no_path": True}}}
    monkeypatch.setattr("src.tests.executor.ROOT", tmp_path)

    path, _, kind = executor._resolve_file_asset("bad")
    assert path is None
    assert kind == "file"


def test_resolve_file_asset_image_kind(tmp_path, monkeypatch):
    sample = tmp_path / "sample.png"
    sample.write_bytes(b"\x89PNG")

    executor = TestExecutor(_FakeClient())
    executor.env_config = {
        "file_assets": {
            "topic_probe_image": {
                "path": str(sample.relative_to(tmp_path)),
                "kind": "image",
            }
        }
    }
    monkeypatch.setattr("src.tests.executor.ROOT", tmp_path)

    path, _, kind = executor._resolve_file_asset("topic_probe_image")
    assert path == sample
    assert kind == "image"
