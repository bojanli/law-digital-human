import sqlite3
from typing import Any
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.core.config import settings
from app.services.embedding import embed_text


def _get_db() -> sqlite3.Connection:
    root = Path(__file__).resolve().parents[3]
    db_path = Path(settings.knowledge_db_path)
    if not db_path.is_absolute():
        db_path = root / db_path
    return sqlite3.connect(db_path)


def _get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, check_compatibility=False)


def ensure_collection() -> None:
    client = _get_qdrant()
    collections = client.get_collections().collections
    if not any(c.name == settings.qdrant_collection for c in collections):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
        )


def search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    ensure_collection()
    vector = embed_text(query)
    client = _get_qdrant()
    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=top_k,
        with_payload=True,
    )

    ids = [r.id for r in results]
    score_map = {r.id: r.score for r in results}

    if not ids:
        return []

    with _get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({','.join('?' for _ in ids)})",
            ids,
        )
        rows = cursor.fetchall()

    # preserve ranking
    row_map = {row["chunk_id"]: dict(row) for row in rows}
    ordered: list[dict[str, Any]] = []
    for chunk_id in ids:
        row = row_map.get(chunk_id)
        if not row:
            continue
        row["score"] = score_map.get(chunk_id)
        ordered.append(row)
    return ordered


def get_chunk(chunk_id: str) -> dict[str, Any] | None:
    with _get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        row = cursor.fetchone()
    return dict(row) if row else None
