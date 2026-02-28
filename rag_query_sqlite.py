import sqlite3
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path("farm_memory")
DB_PATH = BASE / "db" / "rag.db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

def from_blob(b: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32, count=dim)

def main():
    q = "Что мы завели сегодня?"
    topk = 5

    model = SentenceTransformer(MODEL_NAME)
    qv = model.encode([q], normalize_embeddings=True)[0].astype(np.float32)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, source_path, kind, chunk_index, text, emb, dim FROM rag_chunks")
    rows = cur.fetchall()
    con.close()

    if not rows:
        print("Пусто: сначала запусти ingest_rag_sqlite.py")
        return

    scored = []
    for _id, sp, kind, idx, text, emb_blob, dim in rows:
        v = from_blob(emb_blob, dim)
        score = float(np.dot(qv, v))  # cosine, т.к. нормализовано
        scored.append((score, sp, kind, idx, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    print("Q:", q)
    for score, sp, kind, idx, text in scored[:topk]:
        print("-"*60)
        print(f"{score:.4f}  {sp}  ({kind} #{idx})")
        print(text[:300].replace("\n"," "))

if __name__ == "__main__":
    main()
