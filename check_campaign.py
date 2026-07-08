import sqlite3
conn = sqlite3.connect('/root/DataEdge/backend/data/dataedge.db')
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {t} LIMIT 0").description]
    if any('running' in c.lower() or 'active' in c.lower() or 'campaign' in c.lower() for c in cols):
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        print(f"\n{t}: {cols}")
        for r in rows:
            print(r)
conn.close()
