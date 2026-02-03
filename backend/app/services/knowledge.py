import logging
import re
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


def _ensure_chunks_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            law_name TEXT,
            article_no TEXT,
            section TEXT,
            tags TEXT,
            source TEXT
        )
        """
    )


def _get_qdrant() -> QdrantClient:
    try:
        return QdrantClient(url=settings.qdrant_url, check_compatibility=False)
    except TypeError:
        # Newer qdrant-client versions may remove this argument.
        return QdrantClient(url=settings.qdrant_url)


def ensure_collection() -> None:
    client = _get_qdrant()
    collections = client.get_collections().collections
    if not any(c.name == settings.qdrant_collection for c in collections):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
        )


def search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    try:
        ensure_collection()
        vector = embed_text(query)
        client = _get_qdrant()
        results = _search_points(client, vector, top_k)
    except Exception as e:
        # Qdrant 不可用或网络错误时返回空，避免 500
        logging.getLogger(__name__).warning("knowledge search: Qdrant unreachable, returning []: %s", e)
        return []

    ids = [str(r.id) for r in results]
    score_map = {str(r.id): r.score for r in results}

    if not ids:
        return []

    with _get_db() as conn:
        _ensure_chunks_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({','.join('?' for _ in ids)})",
            ids,
        )
        rows = cursor.fetchall()

    # preserve ranking, build response with exact KnowledgeChunk fields
    row_map = {str(row["chunk_id"]): row for row in rows}
    ordered: list[dict[str, Any]] = []
    for chunk_id in ids:
        row = row_map.get(chunk_id)
        if not row:
            continue
        ordered.append({
            "chunk_id": str(row["chunk_id"]),
            "text": str(row["text"]) if row["text"] is not None else "",
            "law_name": str(row["law_name"]) if row["law_name"] is not None else None,
            "article_no": str(row["article_no"]) if row["article_no"] is not None else None,
            "section": str(row["section"]) if row["section"] is not None else None,
            "tags": str(row["tags"]) if row["tags"] is not None else None,
            "source": str(row["source"]) if row["source"] is not None else None,
            "score": score_map.get(chunk_id),
        })
    return _rerank_by_keyword(query, ordered)


def _search_points(client: QdrantClient, vector: list[float], top_k: int):
    # qdrant-client API differs by version: older uses search(), newer uses query_points().
    if hasattr(client, "search"):
        return client.search(
            collection_name=settings.qdrant_collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )

    if not hasattr(client, "query_points"):
        raise AttributeError("QdrantClient has neither search nor query_points")

    try:
        resp = client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
    except TypeError:
        # Compatibility with alternate argument name in some versions.
        resp = client.query_points(
            collection_name=settings.qdrant_collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )

    points = getattr(resp, "points", None)
    if points is None and isinstance(resp, list):
        points = resp
    return points or []


def _extract_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for t in re.findall(r"[A-Za-z0-9_]{2,}", query.lower()):
        terms.append(t)
    for t in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        terms.append(t)
    # keep order, remove duplicates
    return list(dict.fromkeys(terms))


def _rerank_by_keyword(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = _extract_query_terms(query)
    if not terms or not items:
        return items

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        base = float(item.get("score") or 0.0)
        law = (item.get("law_name") or "").lower()
        article = (item.get("article_no") or "").lower()
        section = (item.get("section") or "").lower()
        tags = (item.get("tags") or "").lower()
        text = (item.get("text") or "")[:500].lower()

        bonus = 0.0
        for term in terms:
            tl = term.lower()
            if tl in law:
                bonus += 0.25
            if tl in article:
                bonus += 0.20
            if tl in section:
                bonus += 0.15
            if tl in tags:
                bonus += 0.12
            if tl in text:
                bonus += 0.08
        ranked.append((base + bonus, idx, item))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [x[2] for x in ranked]


def get_chunk(chunk_id: str) -> dict[str, Any] | None:
    with _get_db() as conn:
        _ensure_chunks_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        row = cursor.fetchone()
    return dict(row) if row else None
