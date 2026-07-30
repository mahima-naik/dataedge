#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("/root/app/backend/data/vernika.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute('SELECT id, role, phone, name, status, _log_id, duration_sec, start_time, created_at FROM leads WHERE duration_sec > 30 AND date(created_at) = "2026-07-29" ORDER BY created_at DESC LIMIT 20')
for r in c.fetchall():
    print(dict(r))
conn.close()