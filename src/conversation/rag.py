"""Lightweight RAG over INSPECTION_CHECKLIST and report snippets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.registry import ROOT


@dataclass
class RagChunk:
    source: str
    title: str
    content: str
    score: float = 0.0


def _tokenize(text: str) -> set[str]:
    text = text.casefold()
    tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{3,}", text))
    return tokens


def _score_chunk(query_tokens: set[str], chunk: RagChunk) -> float:
    body_tokens = _tokenize(chunk.title + " " + chunk.content)
    if not query_tokens or not body_tokens:
        return 0.0
    overlap = len(query_tokens & body_tokens)
    return overlap / max(len(query_tokens), 1)


def _load_checklist_chunks() -> list[RagChunk]:
    path = ROOT / "docs" / "INSPECTION_CHECKLIST.md"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    chunks: list[RagChunk] = []
    current_title = "概述"
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                chunks.append(
                    RagChunk(
                        source="checklist",
                        title=current_title,
                        content="\n".join(current_lines).strip(),
                    )
                )
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append(
            RagChunk(
                source="checklist",
                title=current_title,
                content="\n".join(current_lines).strip(),
            )
        )
    return chunks


_CHECKLIST_CACHE: list[RagChunk] | None = None


def retrieve(query: str, *, top_k: int = 3) -> list[RagChunk]:
    global _CHECKLIST_CACHE
    if _CHECKLIST_CACHE is None:
        _CHECKLIST_CACHE = _load_checklist_chunks()

    query_tokens = _tokenize(query)
    scored: list[RagChunk] = []
    for chunk in _CHECKLIST_CACHE:
        score = _score_chunk(query_tokens, chunk)
        if score > 0:
            scored.append(
                RagChunk(
                    source=chunk.source,
                    title=chunk.title,
                    content=chunk.content[:1200],
                    score=score,
                )
            )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]
