import re, hashlib
from pathlib import Path
from datetime import datetime

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

BASE = Path('farm_memory')
CHROMA_DIR = BASE / 'vector' / 'chroma'
COLLECTION_NAME = 'farm_memory'
MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

SCAN_DIRS = [(BASE / 'knowledge','knowledge'), (BASE / 'journal','journal')]
EXTS = {'.md', '.txt'}

def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return p.read_text(encoding='cp1251', errors='replace')

def normalize(t: str) -> str:
    t = t.replace('\r\n','\n')
    t = re.sub(r'[ \t]+',' ', t)
    t = re.sub(r'\n{3,}','\n\n', t)
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

def main():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))
    col = client.get_or_create_collection(name=COLLECTION_NAME)
    model = SentenceTransformer(MODEL_NAME)

    added_files=0; added_chunks=0

    for root, kind in SCAN_DIRS:
        if not root.exists(): 
            continue
        for p in root.rglob('*'):
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

            # remove old chunks for that file
            try:
                existing = col.get(where={'source_path': rel})
                if existing and existing.get('ids'):
                    col.delete(ids=existing['ids'])
            except Exception:
                pass

            ids=[]; docs=[]; metas=[]
            for idx, ch in enumerate(chunks):
                ids.append(f'{rel}::#{idx}::{sha[:8]}')
                docs.append(ch)
                metas.append({
                    'source_path': rel,
                    'kind': kind,
                    'file_sha1': sha,
                    'chunk_index': idx,
                    'ingested_at': datetime.utcnow().isoformat(timespec='seconds')+'Z'
                })

            embs = model.encode(docs, normalize_embeddings=True).tolist()
            col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)

            added_files += 1
            added_chunks += len(chunks)

    if added_files == 0:
        print('Нечего индексировать: добавь .md/.txt в farm_memory/knowledge или journal')
    else:
        print(f'OK: проиндексировано файлов: {added_files}, чанков: {added_chunks}')
        print('Chroma:', CHROMA_DIR.resolve(), 'collection:', COLLECTION_NAME)

if __name__=='__main__':
    main()
