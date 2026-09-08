"""Lightweight local knowledge-base search for Rooze Ziba.

Indexes safe project documentation at runtime using a bounded lexical scorer.
No jokes_data.json or user/private files are indexed.
"""
from __future__ import annotations

import re
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = {"README.md", "RELEASE.md", ".env.example", "render.yaml"}
_MAX_FILE_CHARS = 80_000
_MAX_RESULTS = 6
_MAX_SNIPPET = 900


def _normalize(text: str) -> str:
    text = text.lower().replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[\u200c\u200d]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w\u0600-\u06ff]{2,}", _normalize(text)) if len(t) >= 2]


@lru_cache(maxsize=1)
def _documents() -> tuple[tuple[str, str], ...]:
    docs = []
    for name in sorted(_ALLOWED):
        p = ROOT / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_CHARS]
            docs.append((name, text))
        except OSError:
            continue
    return tuple(docs)


def refresh_index() -> None:
    _documents.cache_clear()


def search_knowledge(query: str, limit: int = 5) -> list[dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []
    qterms = set(_terms(query))
    if not qterms:
        return []
    scored = []
    for name, text in _documents():
        norm = _normalize(text)
        hits = sum(norm.count(term) for term in qterms)
        if hits == 0:
            continue
        # Reward documents matching more distinct query terms.
        coverage = len([t for t in qterms if t in norm])
        score = hits + coverage * 2
        positions = [norm.find(t) for t in qterms if norm.find(t) >= 0]
        pos = min(positions) if positions else 0
        start = max(0, pos - 180)
        snippet = text[start:start + _MAX_SNIPPET].strip()
        snippet = re.sub(r"\n{3,}", "\n\n", snippet)
        scored.append((score, coverage, name, snippet))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [{"source": n, "score": str(s), "snippet": sn} for s, _, n, sn in scored[: max(1, min(limit, _MAX_RESULTS))]]


def format_knowledge_results(query: str, limit: int = 5) -> str:
    results = search_knowledge(query, limit)
    if not results:
        return "اطلاعات مرتبطی در پایگاه دانش داخلی پیدا نشد."
    lines = [f"📚 نتایج پایگاه دانش برای: {query}", ""]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {item['source']} (score={item['score']})")
        lines.append(item["snippet"])
        lines.append("")
    return "\n".join(lines)[:5000]
