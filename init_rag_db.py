import sqlite3
from pathlib import Path

db_path = Path("farm_memory/db/rag.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.executescript("""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS rag_chunks (
  id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  emb BLOB NOT NULL,
  dim INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_source ON rag_chunks(source_path);
CREATE INDEX IF NOT EXISTS idx_rag_kind ON rag_chunks(kind);
""")

con.commit()
con.close()

print("OK: rag.db initialized:", db_path.resolve())
