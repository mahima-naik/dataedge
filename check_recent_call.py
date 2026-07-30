#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("/root/app/backend/data/vernika.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT * FROM manual_calls WHERE to_phone LIKE ? ORDER BY id DESC LIMIT 5", ("%9833246992%",))
for r in c.fetchall():
    print(dict(r))
conn.close()