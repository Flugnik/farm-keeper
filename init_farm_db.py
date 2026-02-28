import sqlite3
from pathlib import Path

db_path = Path("farm_memory/db/farm.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS animals (
    id TEXT PRIMARY KEY,
    name TEXT,
    species TEXT,
    breed TEXT,
    born_date DATE,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    animal_id TEXT,
    type TEXT,
    value REAL,
    unit TEXT,
    text TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS milkings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    animal_id TEXT,
    liters REAL,
    fat REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY,
    title TEXT,
    unit TEXT,
    stock REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
""")

conn.commit()
conn.close()

print("OK: farm.db и таблицы созданы/обновлены:", db_path.resolve())
