import sqlite3, json, os, glob as globmod

DB_PATH = "/root/app/backend/data/vernika.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# List tables and row counts
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES ===")
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) as cnt FROM "{t}"')
        cnt = cur.fetchone()[0]
        if cnt > 0:
            print(f"  {t}: {cnt} rows")
    except:
        pass

# Check test_calls / calls / transcripts for recent entries
print("\n=== RECENT CALLS (last 30 min) ===")
for tname in ["calls", "test_calls", "transcripts", "call_log", "campaign_calls"]:
    if tname in tables:
        try:
            cur.execute(f'SELECT * FROM "{tname}" ORDER BY rowid DESC LIMIT 5')
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            print(f"\n--- {tname} (last 5) ---")
            for r in rows:
                row_dict = {cols[i]: r[i] for i in range(len(cols))}
                # Truncate large values
                for k, v in row_dict.items():
                    if isinstance(v, str) and len(v) > 200:
                        row_dict[k] = v[:200] + "..."
                print(json.dumps(row_dict, indent=2, default=str))
        except Exception as e:
            print(f"  Error reading {tname}: {e}")

# Check active call state
print("\n=== ACTIVE CALL STATE (in-memory check) ===")
# Check recordings dir for recent files
rec_dir = "/root/app/backend/data/recordings"
if os.path.isdir(rec_dir):
    files = sorted(globmod.glob(os.path.join(rec_dir, "*")), key=os.path.getmtime, reverse=True)
    print(f"  Recording files: {len(files)} total")
    for f in files[:10]:
        print(f"  {os.path.basename(f)} ({os.path.getsize(f)} bytes, mtime={os.path.getmtime(f):.0f})")

conn.close()
