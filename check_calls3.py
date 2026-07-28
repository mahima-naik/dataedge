import sqlite3, json

DB_PATH = "/root/app/backend/data/vernika.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get ALL manual calls from today (July 28)
print("=== ALL MANUAL CALLS FROM TODAY ===")
try:
    cur.execute("SELECT id, to_phone, status, started_at, ended_at, duration_sec, disposition, error, summary FROM manual_calls WHERE started_at >= '2026-07-28' ORDER BY id DESC")
    for r in cur.fetchall():
        print(dict(r))
except Exception as e:
    print(f"Error: {e}")

# Check transcript files
print("\n=== TRANSCRIPT FILES (recent) ===")
import os, glob
t_dir = "/root/app/backend/data/transcripts"
if os.path.isdir(t_dir):
    files = sorted(glob.glob(os.path.join(t_dir, "*")), key=os.path.getmtime, reverse=True)
    print(f"Total files: {len(files)}")
    for f in files[:10]:
        size = os.path.getsize(f)
        mtime = os.path.getmtime(f)
        from datetime import datetime
        mtime_str = datetime.utcfromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f"  {os.path.basename(f)} ({size} bytes, {mtime_str})")
        if size > 0 and size < 10000:
            with open(f) as fh:
                print(f"    Content: {fh.read()[:500]}")

# Check data_edge dir for call logs
print("\n=== DATA EDGE DIR ===")
de_dir = "/root/app/backend/data/data_edge"
if os.path.isdir(de_dir):
    for item in os.listdir(de_dir):
        full = os.path.join(de_dir, item)
        if os.path.isfile(full):
            size = os.path.getsize(full)
            mtime = os.path.getmtime(full)
            from datetime import datetime
            mtime_str = datetime.utcfromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"  {item} ({size} bytes, {mtime_str})")
        elif os.path.isdir(full):
            contents = os.listdir(full)
            print(f"  {item}/ ({len(contents)} items)")

conn.close()
