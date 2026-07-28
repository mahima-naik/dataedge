import sqlite3, time

conn = sqlite3.connect('/root/app/backend/data/vernika.db')
cur = conn.cursor()

cur.execute("SELECT id, to_phone, status, started_at, ended_at, error, duration_sec FROM manual_calls ORDER BY id DESC LIMIT 5")
for r in cur.fetchall():
    print(r)

print("\nCurrent UTC:", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
conn.close()
