#!/usr/bin/env python3
"""Find the specific lead and check its transcript."""
import sqlite3, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.worker import _read_transcript_jsonl

db = Path(__file__).resolve().parents[1] / "data" / "vernika.db"
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, phone, status, analysis, _log_id, role FROM leads WHERE phone LIKE '%9881608711%'").fetchall()
for r in rows:
    aj = json.loads(r["analysis"]) if r["analysis"] else {}
    log_id = str(r["_log_id"] or "").strip()
    transcript = _read_transcript_jsonl(r["role"], log_id) if log_id else ""
    print(f"id={r['id']} phone={r['phone']} status={r['status']} disposition={aj.get('disposition','?')}")
    print(f"  summary={aj.get('summary','?')[:200]}")
    if transcript:
        print(f"  transcript ({len(transcript)} chars):")
        for line in transcript.strip().splitlines()[:10]:
            try:
                obj = json.loads(line)
                role = obj.get("role","?")
                content = obj.get("content") or obj.get("text") or ""
                print(f"    [{role}] {content[:150]}")
            except:
                pass
    else:
        print("  NO TRANSCRIPT FOUND")
    print()
conn.close()
