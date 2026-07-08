#!/usr/bin/env python3
"""Find leads with analyzer errors and reclassify them using transcript interest rules."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.worker import _read_transcript_jsonl
from services.call_analyzer import canonical_disposition
from services.transcript_interest import apply_interest_disposition_override

import sqlite3

def main():
    db_path = Path(__file__).resolve().parents[1] / "data" / "vernika.db"
    if not db_path.is_file():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, role, analysis, _log_id FROM leads WHERE analysis LIKE '%Analyzer error%'"
    ).fetchall()
    print(f"Found {len(rows)} leads with Analyzer errors")

    upgraded = 0
    for row in rows:
        aj = json.loads(row["analysis"]) if row["analysis"] else {}
        log_id = str(row["_log_id"] or "").strip()
        transcript = _read_transcript_jsonl(row["role"], log_id) if log_id else ""

        new_aj = apply_interest_disposition_override(aj, transcript or None)
        new_canon = canonical_disposition(new_aj.get("disposition"))
        old_canon = canonical_disposition(aj.get("disposition"))

        if new_canon != old_canon:
            upgraded += 1
            print(f"  lead_id={row['id']} {old_canon} -> {new_canon} (log_id={log_id})")
            conn.execute(
                "UPDATE leads SET analysis = ? WHERE id = ?",
                (json.dumps(new_aj, ensure_ascii=False), row["id"]),
            )
        else:
            print(f"  lead_id={row['id']} unchanged ({old_canon})")

    conn.commit()
    conn.close()
    print(f"\nUpgraded {upgraded} leads to Interested")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
