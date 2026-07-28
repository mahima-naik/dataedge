import sqlite3, os, glob, json

conn = sqlite3.connect('/root/app/backend/data/vernika.db')
cur = conn.cursor()

cur.execute("SELECT id, to_phone, status, started_at, ended_at, error, duration_sec, disposition, summary FROM manual_calls ORDER BY id DESC LIMIT 3")
for r in cur.fetchall():
    print(r)

conn.close()

print("\n=== TRANSCRIPT ===")
tfiles = sorted(glob.glob('/root/app/data/data_edge/logs/2026-07-28/*.jsonl'), key=os.path.getmtime, reverse=True)
for f in tfiles[:3]:
    print(f"\n--- {os.path.basename(f)} ({os.path.getsize(f)} bytes) ---")
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                ts = rec.get('ts','')[:19]
                rtype = rec.get('type','')
                role = rec.get('role','')
                content = rec.get('content','')
                meta = rec.get('meta',{})
                extra = rec.get('extra',{})
                if rtype == 'turn':
                    print(f"  [{ts}] {role}: {content[:120]}")
                elif rtype == 'session':
                    print(f"  [{ts}] session: {json.dumps(meta)[:120]}")
                elif rtype == 'artifact':
                    print(f"  [{ts}] artifact: {json.dumps(meta)[:120]}")
                else:
                    print(f"  [{ts}] {rtype}: {json.dumps(rec)[:120]}")
