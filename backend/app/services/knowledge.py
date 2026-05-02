import logging
import re
import sqlite3
import threading
from collections import OrderedDict
from contextlib import closing
from typing import Any
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.core.config import settings
from app.services.embedding import embed_text
from app.services.runtime_config import get_runtime_config


_ENSURED_COLLECTIONS: set[str] = set()
_ENSURE_LOCK = threading.Lock()
_SEARCH_CACHE_MAX = 256
_SEARCH_CACHE: "OrderedDict[tuple[str, int, str, str, bool, int], list[dict[str, Any]]]" = OrderedDict()
_SEARCH_CACHE_LOCK = threading.Lock()


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


def _ensure_case_chunks_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_chunks (
            chunk_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            case_id TEXT,
            case_name TEXT,
            charges TEXT,
            articles TEXT,
            section TEXT,
            source TEXT
        )
        """
    )


def _get_qdrant() -> QdrantClient:
    try:
        return QdrantClient(url=settings.qdrant_url, check_compatibility=False, timeout=5)
    except TypeError:
        # Newer qdrant-client versions may remove this argument.
        return QdrantClient(url=settings.qdrant_url, timeout=5)


def ensure_collection() -> None:
    runtime = get_runtime_config()
    targets = {runtime.knowledge_collection}
    if runtime.chat_case_top_k > 0:
        targets.add(runtime.case_collection)

    with _ENSURE_LOCK:
        missing = [name for name in targets if name not in _ENSURED_COLLECTIONS]
        if not missing:
            return

        client = _get_qdrant()
        collections = {c.name for c in client.get_collections().collections}

        if runtime.knowledge_collection not in collections:
            client.create_collection(
                collection_name=runtime.knowledge_collection,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )
        _ENSURED_COLLECTIONS.add(runtime.knowledge_collection)

        if runtime.chat_case_top_k > 0:
            if runtime.case_collection not in collections:
                client.create_collection(
                    collection_name=runtime.case_collection,
                    vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
                )
            _ENSURED_COLLECTIONS.add(runtime.case_collection)


def search(query: str, top_k: int = 5, use_rerank: bool | None = None) -> list[dict[str, Any]]:
    runtime = get_runtime_config()
    enable_rerank = runtime.enable_rerank if use_rerank is None else use_rerank
    cache_key = (
        query.strip(),
        int(top_k),
        str(runtime.knowledge_collection),
        str(runtime.case_collection),
        bool(enable_rerank),
        int(runtime.chat_case_top_k or 0),
    )
    cached = _search_cache_get(cache_key)
    if cached is not None:
        return cached

    case_top_k = max(0, int(runtime.chat_case_top_k or 0))
    case_fetch_k = max(case_top_k, case_top_k * 3) if case_top_k > 0 else 0

    try:
        ensure_collection()
        vector = embed_text(query)
        client = _get_qdrant()
        law_results = _search_points(client, vector, top_k, runtime.knowledge_collection)

        case_results = []
        if case_top_k > 0:
            try:
                case_results = _search_points(client, vector, case_fetch_k, runtime.case_collection)
            except Exception as e:
                logging.getLogger(__name__).warning("case search skipped: %s", e)
    except Exception as e:
        # Qdrant 不可用或网络错误时返回空，避免 500
        logging.getLogger(__name__).warning("knowledge search: Qdrant unreachable, returning []: %s", e)
        return []

    law_ids = [str(r.id) for r in law_results]
    case_ids = [str(r.id) for r in case_results]
    law_score_map = {str(r.id): r.score for r in law_results}
    case_score_map = {str(r.id): r.score for r in case_results}

    if not law_ids and not case_ids:
        return []

    law_rows: list[sqlite3.Row] = []
    case_rows: list[sqlite3.Row] = []
    with closing(_get_db()) as conn:
        _ensure_chunks_table(conn)
        _ensure_case_chunks_table(conn)
        conn.row_factory = sqlite3.Row

        if law_ids:
            law_cursor = conn.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({','.join('?' for _ in law_ids)})",
                law_ids,
            )
            law_rows = law_cursor.fetchall()

        if case_ids:
            case_cursor = conn.execute(
                f"SELECT * FROM case_chunks WHERE chunk_id IN ({','.join('?' for _ in case_ids)})",
                case_ids,
            )
            case_rows = case_cursor.fetchall()

    law_items = _build_law_items(law_ids, law_rows, law_score_map)
    case_items = _build_case_items(case_ids, case_rows, case_score_map)

    if enable_rerank:
        law_items = _rerank_by_keyword(query, law_items)
        case_items = _rerank_by_keyword(query, case_items)
    case_items = _dedupe_case_items(case_items, case_top_k)

    # 先法条、后案例，符合“先给依据再举例”的回答顺序。
    result = law_items + case_items
    _search_cache_set(cache_key, result)
    return result


def _build_law_items(ids: list[str], rows: list[sqlite3.Row], score_map: dict[str, float]) -> list[dict[str, Any]]:
    row_map = {str(row["chunk_id"]): row for row in rows}
    ordered: list[dict[str, Any]] = []
    for chunk_id in ids:
        row = row_map.get(chunk_id)
        if not row:
            continue
        ordered.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "text": str(row["text"]) if row["text"] is not None else "",
                "law_name": str(row["law_name"]) if row["law_name"] is not None else None,
                "article_no": str(row["article_no"]) if row["article_no"] is not None else None,
                "section": str(row["section"]) if row["section"] is not None else None,
                "tags": str(row["tags"]) if row["tags"] is not None else None,
                "source": str(row["source"]) if row["source"] is not None else None,
                "source_type": "law",
                "score": score_map.get(chunk_id),
            }
        )
    return ordered


def _build_case_items(ids: list[str], rows: list[sqlite3.Row], score_map: dict[str, float]) -> list[dict[str, Any]]:
    row_map = {str(row["chunk_id"]): row for row in rows}
    ordered: list[dict[str, Any]] = []
    for chunk_id in ids:
        row = row_map.get(chunk_id)
        if not row:
            continue
        case_name = str(row["case_name"]) if row["case_name"] is not None else None
        charges = str(row["charges"]) if row["charges"] is not None else None
        ordered.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "text": str(row["text"]) if row["text"] is not None else "",
                "law_name": case_name,
                "article_no": "相关案例",
                "section": charges,
                "tags": "case",
                "source": str(row["source"]) if row["source"] is not None else None,
                "source_type": "case",
                "case_id": str(row["case_id"]) if row["case_id"] is not None else None,
                "case_name": case_name,
                "charges": charges,
                "articles": str(row["articles"]) if row["articles"] is not None else None,
                "score": score_map.get(chunk_id),
            }
        )
    return ordered


def _dedupe_case_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not items:
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("case_id") or item.get("chunk_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if limit > 0 and len(out) >= limit:
            break
    return out


def _search_points(client: QdrantClient, vector: list[float], top_k: int, collection_name: str):
    # qdrant-client API differs by version: older uses search(), newer uses query_points().
    if hasattr(client, "search"):
        return client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )

    if not hasattr(client, "query_points"):
        raise AttributeError("QdrantClient has neither search nor query_points")

    try:
        resp = client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
    except TypeError:
        # Compatibility with alternate argument name in some versions.
        resp = client.query_points(
            collection_name=collection_name,
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
    with closing(_get_db()) as conn:
        _ensure_chunks_table(conn)
        _ensure_case_chunks_table(conn)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            data["source_type"] = "law"
            data["case_id"] = None
            data["case_name"] = None
            return data

        case_cursor = conn.execute("SELECT * FROM case_chunks WHERE chunk_id = ?", (chunk_id,))
        case_row = case_cursor.fetchone()
        if case_row:
            data = dict(case_row)
            data["source_type"] = "case"
            data["law_name"] = data.get("case_name")
            data["article_no"] = "相关案例"
            return data

    return None


def _search_cache_get(key: tuple[str, int, str, str, bool, int]) -> list[dict[str, Any]] | None:
    with _SEARCH_CACHE_LOCK:
        cached = _SEARCH_CACHE.get(key)
        if cached is None:
            return None
        _SEARCH_CACHE.move_to_end(key)
        return [dict(item) for item in cached]


def _search_cache_set(key: tuple[str, int, str, str, bool, int], value: list[dict[str, Any]]) -> None:
    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[key] = [dict(item) for item in value]
        _SEARCH_CACHE.move_to_end(key)
        while len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
            _SEARCH_CACHE.popitem(last=False)
