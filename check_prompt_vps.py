#!/usr/bin/env python3
"""Check current prompt in DB and verify it's being used."""
import sqlite3

DB_PATH = "/root/app/backend/data/vernika.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check what's in DB
c.execute("SELECT length(prompt), substr(prompt, 1, 300) FROM role_state WHERE role='data_edge'")
row = c.fetchone()
if row:
    print(f"DB prompt length: {row[0]}")
    print(f"DB prompt start: {row[1]}")
    print()
    # Check if our opening is in there
    c.execute("SELECT prompt FROM role_state WHERE role='data_edge'")
    full = c.fetchone()[0]
    if "OPENING CONVERSATION FLOW" in full:
        print("✓ 'OPENING CONVERSATION FLOW' found in prompt")
    else:
        print("✗ 'OPENING CONVERSATION FLOW' NOT found in prompt")
    
    if "career counselor from Data Edge" in full:
        print("✓ New opening greeting found")
    else:
        print("✗ New opening greeting NOT found")
    
    # Check what init_db does
    print(f"\nFull prompt ({len(full)} chars):")
    print(full[:2000])
    print("...")
else:
    print("No prompt found for role='data_edge'!")

conn.close()
