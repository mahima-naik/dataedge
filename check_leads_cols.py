#!/usr/bin/env python3
import sqlite3
c = sqlite3.connect("/root/app/backend/data/vernika.db")
print([r[1] for r in c.execute("PRAGMA table_info(leads)").fetchall()])
c.close()