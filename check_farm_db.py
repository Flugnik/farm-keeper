import sqlite3
conn = sqlite3.connect("farm_memory/db/farm.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;").fetchall()
print("Tables:", [t[0] for t in tables])
conn.close()
