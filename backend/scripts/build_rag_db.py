#!/usr/bin/env python3
"""Build local RAG SQLite DB from project knowledge/docs files.

Run on pod:
  cd /workspace/priya-agent
  python scripts/build_rag_db.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag import RagStore  # noqa: E402


DEFAULT_SOURCE_DIRS = [
    ROOT / "prompts",
]
DEFAULT_FILE_GLOBS = ("*.md", "*.txt", "*.rst", "*.html")


def gather_files(source_dirs: list[Path], globs: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for base in source_dirs:
        if not base.exists():
            continue
        for g in globs:
            for p in base.rglob(g):
                if p.is_file() and p not in seen:
                    seen.add(p)
                    files.append(p)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local RAG DB")
    parser.add_argument("--db", default=str(ROOT / "data" / "rag.db"))
    parser.add_argument("--source-dir", action="append", default=[])
    parser.add_argument("--chunk-chars", type=int, default=900)
    args = parser.parse_args()

    src_dirs = [Path(p).resolve() for p in args.source_dir] if args.source_dir else DEFAULT_SOURCE_DIRS
    files = gather_files(src_dirs, DEFAULT_FILE_GLOBS)
    if not files:
        raise SystemExit("No source files found to index. Provide --source-dir paths.")

    store = RagStore(args.db)
    total = store.build_from_files(files, chunk_chars=max(400, int(args.chunk_chars)))

    print(f"RAG DB: {args.db}")
    print(f"Indexed files: {len(files)}")
    print(f"Indexed chunks: {total}")


if __name__ == "__main__":
    main()
