import sqlite3, json

DB_PATH = "/root/app/backend/data/vernika.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check manual_calls for recent entries
print("=== RECENT MANUAL CALLS (last 10) ===")
try:
    cur.execute('SELECT * FROM "manual_calls" ORDER BY rowid DESC LIMIT 10')
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    for r in rows:
        row_dict = {cols[i]: r[i] for i in range(len(cols))}
        for k, v in row_dict.items():
            if isinstance(v, str) and len(v) > 500:
                row_dict[k] = v[:500] + "..."
        print(json.dumps(row_dict, indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")

# Check leads for recent call activity
print("\n=== RECENT LEADS WITH CALL DATA ===")
try:
    cur.execute("PRAGMA table_info(leads)")
    lead_cols = [r[1] for r in cur.fetchall()]
    print(f"Lead columns: {lead_cols}")
    
    # Check for recently updated leads
    cur.execute('SELECT * FROM leads ORDER BY rowid DESC LIMIT 3')
    rows = cur.fetchall()
    for r in rows:
        row_dict = {lead_cols[i]: r[i] for i in range(len(lead_cols))}
        for k, v in row_dict.items():
            if isinstance(v, str) and len(v) > 200:
                row_dict[k] = v[:200] + "..."
        print(json.dumps(row_dict, indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")

# Check cases
print("\n=== CASES (all) ===")
try:
    cur.execute('SELECT * FROM cases')
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    for r in rows:
        row_dict = {cols[i]: r[i] for i in range(len(cols))}
        for k, v in row_dict.items():
            if isinstance(v, str) and len(v) > 500:
                row_dict[k] = v[:500] + "..."
        print(json.dumps(row_dict, indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")

conn.close()
