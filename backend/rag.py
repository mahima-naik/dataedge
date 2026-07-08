"""Simple local RAG store using SQLite FTS5.

This keeps deployment lightweight (no external vector DB service) while still
providing retrieval grounding from project docs/knowledge files.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}")


def _fts_terms(text: str, max_terms: int = 24) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for tok in _TOKEN_RE.findall(text or ""):
        t = tok.lower()
        if t in seen:
            continue
        seen.add(t)
        terms.append(t)
        if len(terms) >= max_terms:
            break
    return terms


def _chunk_text(text: str, chunk_chars: int = 900, overlap_chars: int = 180) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= chunk_chars:
        return [raw]

    chunks: list[str] = []
    start = 0
    n = len(raw)
    while start < n:
        end = min(start + chunk_chars, n)
        part = raw[start:end].strip()
        if part:
            chunks.append(part)
        if end >= n:
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


class RagStore:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(text, content='chunks', content_rowid='id', tokenize='unicode61');
                """
            )
            # Rebuild fts table if needed.
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            conn.commit()

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            conn.commit()

    def add_document(self, source: str, text: str, *, chunk_chars: int = 900) -> int:
        chunks = _chunk_text(text, chunk_chars=chunk_chars)
        if not chunks:
            return 0
        with self._connect() as conn:
            rows = [(source, i, c) for i, c in enumerate(chunks)]
            conn.executemany(
                "INSERT INTO chunks(source, chunk_index, text) VALUES (?, ?, ?)",
                rows,
            )
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            conn.commit()
        return len(chunks)

    def build_from_files(self, files: Iterable[Path], *, chunk_chars: int = 900) -> int:
        total = 0
        self.clear()
        for path in files:
            try:
                txt = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            src = str(path)
            total += self.add_document(src, txt, chunk_chars=chunk_chars)
        return total

    def query(self, text: str, *, top_k: int = 4, max_chars: int = 2200) -> list[dict[str, str]]:
        terms = _fts_terms(text)
        if not terms:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in terms)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.source, c.text, bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, int(top_k)),
            ).fetchall()

        out: list[dict[str, str]] = []
        used = 0
        for r in rows:
            snippet = str(r["text"]).strip()
            if not snippet:
                continue
            remain = max_chars - used
            if remain <= 0:
                break
            if len(snippet) > remain:
                snippet = snippet[: max(0, remain - 1)].rstrip() + "…"
            out.append({"source": str(r["source"]), "text": snippet})
            used += len(snippet)
        return out


def format_references(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    lines: list[str] = []
    for i, item in enumerate(items, start=1):
        src = Path(item.get("source", "")).name or item.get("source", "unknown")
        txt = item.get("text", "").strip()
        if not txt:
            continue
        lines.append(f"[{i}] source={src}\n{txt}")
    return "\n\n".join(lines).strip()
