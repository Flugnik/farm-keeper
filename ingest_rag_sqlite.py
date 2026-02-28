import re, hashlib, sqlite3
from pathlib import Path
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path("farm_memory")
DB_PATH = BASE / "db" / "rag.db"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SCAN_DIRS = [(BASE / "knowledge","knowledge"), (BASE / "journal","journal")]
EXTS = {".md", ".txt"}

def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="cp1251", errors="replace")

def normalize(t: str) -> str:
    t = t.replace("\r\n","\n")
    t = re.sub(r"[ \t]+"," ", t)
    t = re.sub(r"\n{3,}","\n\n", t)
    return t.strip()

def chunk_text(t: str, size=900, overlap=150):
    if not t: return []
    out=[]; i=0; n=len(t)
    while i<n:
        j=min(i+size,n)
        out.append(t[i:j])
        if j==n: break
        i=max(0, j-overlap)
    return out

def to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    model = SentenceTransformer(MODEL_NAME)

    added_files = 0
    added_chunks = 0

    for root, kind in SCAN_DIRS:
        if not root.exists():
            continue

        for p in root.rglob("*"):
            if not p.is_file(): 
                continue
            if p.suffix.lower() not in EXTS:
                continue

            text = normalize(read_text(p))
            if len(text) < 20:
                continue

            sha = file_sha1(p)
            rel = p.relative_to(BASE).as_posix()
            chunks = chunk_text(text)
            if not chunks:
                continue

            cur.execute("DELETE FROM rag_chunks WHERE source_path=?", (rel,))

            embs = model.encode(chunks, normalize_embeddings=True)
            embs = np.asarray(embs, dtype=np.float32)
            dim = int(embs.shape[1])

            now = datetime.utcnow().isoformat(timespec="seconds")+"Z"

            rows = []
            for idx, ch in enumerate(chunks):
                doc_id = f"{rel}::#{idx}::{sha[:8]}"
                rows.append((doc_id, rel, kind, idx, ch, to_blob(embs[idx]), dim, now))

            cur.executemany("""
                INSERT INTO rag_chunks(id, source_path, kind, chunk_index, text, emb, dim, created_at)
                VALUES(?,?,?,?,?,?,?,?)
            """, rows)

            added_files += 1
            added_chunks += len(chunks)

    con.commit()
    con.close()

    if added_files == 0:
        print("Нечего индексировать: добавь .md/.txt в farm_memory/knowledge или journal")
    else:
        print(f"OK: проиндексировано файлов: {added_files}, чанков: {added_chunks}")
        print("DB:", DB_PATH.resolve())

if __name__=="__main__":
    main()
