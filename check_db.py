import sqlite3
conn = sqlite3.connect('/root/DataEdge/backend/data/vernika.db')
conn.execute("UPDATE app_meta SET value = '0' WHERE key = 'campaign_want_running_v2:data_edge'")
conn.commit()
print("Set campaign_want_running_v2:data_edge to 0")
row = conn.execute("SELECT * FROM app_meta WHERE key LIKE '%campaign%'").fetchall()
for r in row:
    print(f'  {r}')
conn.close()
