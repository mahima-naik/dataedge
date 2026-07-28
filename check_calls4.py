import sqlite3

conn = sqlite3.connect('/root/app/backend/data/vernika.db')
cur = conn.cursor()

cur.execute('SELECT MAX(id) FROM manual_calls')
print('Max manual_call ID:', cur.fetchone()[0])

cur.execute("SELECT id, to_phone, status, started_at, ended_at, error, duration_sec FROM manual_calls WHERE id >= 480")
for r in cur.fetchall():
    print(r)

cur.execute("SELECT COUNT(*) FROM manual_calls WHERE started_at >= '2026-07-28 14:53:00'")
print('Calls after restart (14:53 UTC):', cur.fetchone()[0])

conn.close()
