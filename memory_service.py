from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import List, Optional

from datetime import datetime, timezone
import uuid

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer


# ----------------------------
# Config
# ----------------------------
BASE = Path("farm_memory")
DB_PATH = BASE / "db" / "rag.db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

PRIORITIES = {"normal", "high"}


# ----------------------------
# API models
# ----------------------------
class Query(BaseModel):
    query: str = Field(..., min_length=1)
    topk: int = Field(5, ge=1, le=50)
    kind: Optional[str] = None
    # если нужно: можно добавлять фильтр по priority, но пока не включаем в API
    # priority: Optional[str] = None


class RetrievedChunk(BaseModel):
    score: float
    source_path: str
    kind: str
    chunk_index: int
    priority: str
    text: str


class StoreRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    chunk_index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    priority: str = Field("normal")  # normal | high


class StoreResponse(BaseModel):
    ok: bool
    id: str
    dim: int


# ----------------------------
# In-memory index
# ----------------------------
@dataclass
class RagIndex:
    source_path: List[str]
    kind: List[str]
    chunk_index: List[int]
    priority: List[str]
    text: List[str]
    emb_matrix: np.ndarray  # (N, D) float32 normalized


class AppState:
    def __init__(self) -> None:
        self.model: Optional[SentenceTransformer] = None
        self.index: Optional[RagIndex] = None
        self.loaded_at: Optional[float] = None

    def ready(self) -> bool:
        return self.model is not None and self.index is not None


state = AppState()
app = FastAPI()


# ----------------------------
# DB / loading
# ----------------------------
def _db_connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=1.0)


def _has_column(con: sqlite3.Connection, table: str, col: str) -> bool:
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]  # r[1] = name
    return col in cols


def _ensure_schema(con: sqlite3.Connection) -> None:
    """
    1) UNIQUE индекс для UPSERT по натуральному ключу
    2) priority column (migration) если её нет
    """
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_rag_chunks_sp_kind_idx "
        "ON rag_chunks(source_path, kind, chunk_index)"
    )

    if not _has_column(con, "rag_chunks", "priority"):
        con.execute("ALTER TABLE rag_chunks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")


def _load_index_from_db() -> RagIndex:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"rag.db not found: {DB_PATH.resolve()}")

    con = _db_connect()
    try:
        # на всякий случай: если сервис подняли на старой БД
        _ensure_schema(con)
        con.commit()

        cur = con.cursor()
        cur.execute(
            "SELECT source_path, kind, chunk_index, priority, text, emb, dim FROM rag_chunks"
        )
        rows = cur.fetchall()
    finally:
        con.close()

    if not rows:
        raise RuntimeError("rag_chunks is empty")

    source_path: List[str] = []
    kind: List[str] = []
    chunk_index: List[int] = []
    priority: List[str] = []
    text: List[str] = []
    embs: List[np.ndarray] = []

    dim0 = int(rows[0][6])
    for sp, k, idx, pr, t, emb_blob, dim in rows:
        dim = int(dim)
        if dim != dim0:
            raise RuntimeError(f"Inconsistent dim in DB: got {dim}, expected {dim0}")

        v = np.frombuffer(emb_blob, dtype=np.float32, count=dim)
        norm = float(np.linalg.norm(v))
        if norm > 0:
            v = v / norm

        source_path.append(str(sp))
        kind.append(str(k))
        chunk_index.append(int(idx))
        pr_s = str(pr) if pr is not None else "normal"
        priority.append(pr_s if pr_s in PRIORITIES else "normal")
        text.append(str(t))
        embs.append(v)

    emb_matrix = np.vstack(embs).astype(np.float32, copy=False)

    return RagIndex(
        source_path=source_path,
        kind=kind,
        chunk_index=chunk_index,
        priority=priority,
        text=text,
        emb_matrix=emb_matrix,
    )


# ----------------------------
# Lifecycle
# ----------------------------
@app.on_event("startup")
def _startup() -> None:
    if DB_PATH.exists():
        con = _db_connect()
        try:
            _ensure_schema(con)
            con.commit()
        finally:
            con.close()

    state.model = SentenceTransformer(MODEL_NAME)
    _ = state.model.encode(["warmup"], normalize_embeddings=True)

    state.index = _load_index_from_db()
    state.loaded_at = time.time()


# ----------------------------
# Endpoints
# ----------------------------
@app.get("/health")
def health():
    return {
        "status": "ok" if state.ready() else "starting",
        "db_path": str(DB_PATH),
        "model": MODEL_NAME,
        "model_loaded": state.model is not None,
        "index_loaded": state.index is not None,
        "loaded_at": state.loaded_at,
        "chunks": int(state.index.emb_matrix.shape[0]) if state.index else 0,
        "dim": int(state.index.emb_matrix.shape[1]) if state.index else 0,
    }


@app.post("/reload_index")
def reload_index():
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    try:
        state.index = _load_index_from_db()
        state.loaded_at = time.time()
        return {"ok": True, "chunks": int(state.index.emb_matrix.shape[0])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reload failed: {e}")


@app.post("/store", response_model=StoreResponse)
def store(req: StoreRequest):
    if not state.ready():
        raise HTTPException(status_code=503, detail="Service not ready")
    assert state.model is not None

    pr = (req.priority or "normal").strip().lower()
    if pr not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority: {req.priority}. Use 'normal' or 'high'.")

    try:
        v = state.model.encode([req.text], normalize_embeddings=True)[0].astype(np.float32, copy=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    emb_blob = v.tobytes()
    dim = int(v.shape[0])

    new_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()

    con = _db_connect()
    try:
        _ensure_schema(con)
        cur = con.cursor()

        cur.execute(
            """
            INSERT INTO rag_chunks (id, source_path, kind, chunk_index, priority, text, emb, dim, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path, kind, chunk_index) DO UPDATE SET
                priority = excluded.priority,
                text = excluded.text,
                emb = excluded.emb,
                dim = excluded.dim,
                created_at = excluded.created_at
            """,
            (
                new_id,
                req.source_path,
                req.kind,
                int(req.chunk_index),
                pr,
                req.text,
                emb_blob,
                dim,
                created_at,
            ),
        )
        con.commit()

        cur.execute(
            "SELECT id, dim FROM rag_chunks WHERE source_path=? AND kind=? AND chunk_index=?",
            (req.source_path, req.kind, int(req.chunk_index)),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Store succeeded but row not found")
        stored_id, stored_dim = row[0], int(row[1])

    except sqlite3.IntegrityError as e:
        con.rollback()
        raise HTTPException(status_code=409, detail=f"Integrity error: {e}")
    except sqlite3.Error as e:
        con.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    finally:
        con.close()

    try:
        state.index = _load_index_from_db()
        state.loaded_at = time.time()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stored but reload_index failed: {e}")

    return StoreResponse(ok=True, id=str(stored_id), dim=int(stored_dim))


@app.post("/retrieve", response_model=List[RetrievedChunk])
def retrieve(q: Query):
    if not state.ready():
        raise HTTPException(status_code=503, detail="Service not ready")
    assert state.model is not None
    assert state.index is not None

    try:
        qv = state.model.encode([q.query], normalize_embeddings=True)[0].astype(np.float32, copy=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    topk_req = int(q.topk)

    if q.kind:
        mask = np.fromiter((k == q.kind for k in state.index.kind), dtype=bool)
        if not mask.any():
            return []

        embs = state.index.emb_matrix[mask]
        scores_local = embs @ qv

        topk = min(topk_req, int(scores_local.shape[0]))
        idx_local = np.argpartition(-scores_local, kth=topk - 1)[:topk]
        idx_local = idx_local[np.argsort(-scores_local[idx_local])]

        idx_global_all = np.flatnonzero(mask)
        idx_global = idx_global_all[idx_local]
        scores_sorted = scores_local[idx_local]
    else:
        scores = state.index.emb_matrix @ qv
        topk = min(topk_req, int(scores.shape[0]))
        idx_global = np.argpartition(-scores, kth=topk - 1)[:topk]
        idx_global = idx_global[np.argsort(-scores[idx_global])]
        scores_sorted = scores[idx_global]

    out: List[RetrievedChunk] = []
    for rank, gi in enumerate(idx_global):
        i = int(gi)
        out.append(
            RetrievedChunk(
                score=float(scores_sorted[rank]),
                source_path=state.index.source_path[i],
                kind=state.index.kind[i],
                chunk_index=state.index.chunk_index[i],
                priority=state.index.priority[i],
                text=state.index.text[i],
            )
        )
    return out