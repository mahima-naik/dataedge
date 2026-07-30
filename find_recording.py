#!/usr/bin/env python3
"""Find recording for a call by phone number."""
import sqlite3
import os

DB_PATH = "/root/app/backend/data/vernika.db"
RECORDING_BASE = "/root/app/data/recordings"

phone = "919833246992"
phone_last10 = phone[-10:]

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Check table schemas
c.execute("PRAGMA table_info(manual_calls)")
mc_cols = [r[1] for r in c.fetchall()]
print(f"manual_calls columns: {mc_cols}")

c.execute("PRAGMA table_info(leads)")
lead_cols = [r[1] for r in c.fetchall()]
print(f"leads columns: {lead_cols}")

# Search manual_calls
phone_col = 'to_number' if 'to_number' in mc_cols else 'phone' if 'phone' in mc_cols else None
if not phone_col:
    for col in mc_cols:
        if 'phone' in col.lower() or 'to' in col.lower() or 'number' in col.lower():
            phone_col = col
            break

if phone_col:
    c.execute(f"SELECT * FROM manual_calls WHERE {phone_col} LIKE ?", (f"%{phone_last10}",))
    rows = c.fetchall()
    print(f"\nFound {len(rows)} manual call(s) via {phone_col}")
    for row in rows:
        d = dict(row)
        print(f"  ID: {d.get('id')}, Camp: {d.get('camp_id')}, Status: {d.get('status')}, Log: {d.get('log_id')}, Created: {d.get('created_at')}")
else:
    print("\nmanual_calls: no phone-like column found")

# Search leads
phone_col2 = None
for col in lead_cols:
    if 'phone' in col.lower() or 'number' in col.lower():
        phone_col2 = col
        break

if phone_col2:
    c.execute(f"SELECT * FROM leads WHERE {phone_col2} LIKE ?", (f"%{phone_last10}",))
    leads = c.fetchall()
    print(f"\nFound {len(leads)} lead(s) via {phone_col2}")
    for lead in leads:
        d = dict(lead)
        print(f"  ID: {d.get('id')}, Name: {d.get('name')}, Log: {d.get('log_id')}, Status: {d.get('status')}")
else:
    print("\nleads: no phone-like column found")

# Search all recording files
print("\nSearching recording directories...")
found = []
for root, dirs, files in os.walk(RECORDING_BASE):
    for f in files:
        if f.endswith(('.wav', '.mp3')):
            found.append(os.path.join(root, f))

print(f"Total recording files: {len(found)}")
if found:
    # Show recent ones
    found.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    for fp in found[:20]:
        size = os.path.getsize(fp)
        print(f"  {fp} ({size} bytes)")

conn.close()
