#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("/root/app/backend/data/vernika.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

phones = ['+918882912625', '+916307116156', '8882912625', '6307116156']

for phone in phones:
    c.execute('SELECT id, role, phone, name, status, _log_id, duration_sec FROM leads WHERE phone LIKE ? ORDER BY created_at DESC LIMIT 5', (f'%{phone[-10:]}%',))
    leads = c.fetchall()
    if leads:
        print(f"--- Leads for {phone} ---")
        for r in leads:
            print(dict(r))
    
    c.execute('SELECT id, role, to_phone, callee_name, status, log_id, duration_sec FROM manual_calls WHERE to_phone LIKE ? ORDER BY id DESC LIMIT 5', (f'%{phone[-10:]}%',))
    manual = c.fetchall()
    if manual:
        print(f"--- Manual calls for {phone} ---")
        for r in manual:
            print(dict(r))

conn.close()