"""Tests for checklist RAG."""

from src.conversation.rag import retrieve


def test_retrieve_permission_hint():
    chunks = retrieve("permission_hint 权限 授权 断言")
    assert chunks
    assert any("permission" in c.content.lower() or "权限" in c.content for c in chunks)
