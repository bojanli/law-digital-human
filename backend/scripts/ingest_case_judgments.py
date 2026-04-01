import argparse
import json
import os
import sqlite3
import uuid
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.services.embedding import embed_text

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")


def chunk_text(text: str, max_len: int = 900) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= max_len:
        return [raw]
    parts: list[str] = []
    buf = ""
    for para in re.split(r"[。\n]+", raw):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 > max_len and buf:
            parts.append(buf)
            buf = para
        else:
            buf = f"{buf}。{para}".strip("。")
    if buf:
        parts.append(buf)
    return parts


def infer_case_name(qw: str, case_id: str) -> str:
    text = (qw or "").strip()
    if not text:
        return f"案例 {case_id}"
    m = re.search(r"([^。]{6,80}?判决书)", text)
    if m:
        return m.group(1)
    return text[:60]


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_case_chunks_case_id ON case_chunks(case_id)")


def upsert_case_chunk(conn: sqlite3.Connection, chunk: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO case_chunks
        (chunk_id, text, case_id, case_name, charges, articles, section, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk["chunk_id"],
            chunk["text"],
            chunk.get("case_id"),
            chunk.get("case_name"),
            chunk.get("charges"),
            chunk.get("articles"),
            chunk.get("section"),
            chunk.get("source"),
        ),
    )


def clear_case_chunks(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM case_chunks")


def load_done_sources(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT source FROM case_chunks WHERE source IS NOT NULL").fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def embed_chunk(chunk: dict, provider_override: str | None) -> dict:
    vector = embed_text(chunk["text"], provider_override=provider_override)
    payload = {
        "chunk_id": chunk["chunk_id"],
        "source_type": "case",
        "case_id": chunk.get("case_id"),
        "case_name": chunk.get("case_name"),
        "charges": chunk.get("charges"),
        "articles": chunk.get("articles"),
        "section": chunk.get("section"),
        "source": chunk.get("source"),
    }
    return {"id": chunk["chunk_id"], "vector": vector, "payload": payload, "chunk": chunk}


def get_existing_point_ids(client: QdrantClient, collection: str, point_ids: list[str]) -> set[str]:
    if not point_ids:
        return set()
    points = client.retrieve(collection_name=collection, ids=point_ids, with_payload=False, with_vectors=False)
    return {str(p.id) for p in points}


def ensure_collection(client: QdrantClient, collection: str, dim: int, recreate: bool) -> None:
    if recreate:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        return

    existing = client.get_collections().collections
    if not any(c.name == collection for c in existing):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def _new_qdrant_client() -> QdrantClient:
    try:
        return QdrantClient(url=settings.qdrant_url, check_compatibility=False)
    except TypeError:
        return QdrantClient(url=settings.qdrant_url)


def build_case_chunks(data: dict, source_file: Path) -> list[dict]:
    case_id = str(data.get("pid") if data.get("pid") is not None else source_file.stem)
    qw = str(data.get("qw") or "")
    fact = str(data.get("fact") or "")
    reason = str(data.get("reason") or "")
    result = str(data.get("result") or "")
    charge_list = data.get("charge") if isinstance(data.get("charge"), list) else []
    article_list = data.get("article") if isinstance(data.get("article"), list) else []

    charges = ",".join(str(x) for x in charge_list if str(x).strip())
    articles = ",".join(str(x) for x in article_list if str(x).strip())
    case_name = infer_case_name(qw, case_id)

    pieces: list[tuple[str, str]] = []
    if qw:
        pieces.extend([("全文摘要", p) for p in chunk_text(qw, max_len=1200)[:2]])
    if fact:
        pieces.extend([("事实认定", p) for p in chunk_text(fact)])
    if reason:
        pieces.extend([("裁判理由", p) for p in chunk_text(reason)])
    if result:
        pieces.extend([("裁判结果", p) for p in chunk_text(result)])

    chunks: list[dict] = []
    for idx, (section, text) in enumerate(pieces):
        raw_id = f"{case_id}|{section}|{idx}|{text}"
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))
        chunks.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "case_id": case_id,
                "case_name": case_name,
                "charges": charges,
                "articles": articles,
                "section": section,
                "source": source_file.name,
            }
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="judgment json folder path")
    parser.add_argument("--db", default=settings.knowledge_db_path)
    parser.add_argument("--collection", default="cases")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="only ingest first N files, 0 means all")
    parser.add_argument("--file-list", default="", help="optional newline-delimited json file list")
    parser.add_argument("--workers", type=int, default=6, help="parallel embedding workers")
    parser.add_argument("--batch-size", type=int, default=256, help="qdrant upsert batch size")
    parser.add_argument("--commit-every-files", type=int, default=100, help="sqlite commit interval")
    parser.add_argument("--skip-existing", action="store_true", help="skip files whose chunk IDs already exist in qdrant")
    parser.add_argument(
        "--embedding",
        default=None,
        help="Override embedding provider for this run (e.g. mock). Use mock when Ark/SSL fails.",
    )
    args = parser.parse_args()

    source_root = Path(args.source)
    if not source_root.exists():
        raise SystemExit(f"Source not found: {source_root}")

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    init_db(db_path)

    client = _new_qdrant_client()
    ensure_collection(client, args.collection, settings.embedding_dim, args.recreate)

    if args.file_list:
        file_list_path = Path(args.file_list)
        if not file_list_path.is_absolute():
            file_list_path = ROOT / file_list_path
        if not file_list_path.exists():
            raise SystemExit(f"File list not found: {file_list_path}")
        files: list[Path] = []
        for line in file_list_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = (ROOT / raw).resolve()
            if p.exists() and p.suffix.lower() == ".json":
                files.append(p)
    else:
        files = sorted(source_root.glob("*.json"))

    if args.limit and args.limit > 0:
        files = files[: args.limit]

    total_files_before_resume = len(files)
    total_chunks = 0
    skipped_files = 0
    batch: list[dict] = []
    batch_size = max(1, int(args.batch_size))

    with sqlite3.connect(db_path) as conn:
        if args.recreate:
            clear_case_chunks(conn)
            conn.commit()
        else:
            done_sources = load_done_sources(conn)
            if done_sources:
                old = len(files)
                files = [p for p in files if p.name not in done_sources]
                skipped_files = old - len(files)
                print(f"Resume mode: skipped {skipped_files} already-ingested files")

        total_files = len(files)
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
            for idx, file_path in enumerate(files, start=1):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue

                chunks = build_case_chunks(data, file_path)
                if not chunks:
                    continue

                if args.skip_existing and not args.recreate:
                    chunk_ids = [c["chunk_id"] for c in chunks]
                    existing_ids = get_existing_point_ids(client, args.collection, chunk_ids)
                    if len(existing_ids) == len(chunk_ids):
                        for c in chunks:
                            upsert_case_chunk(conn, c)
                        if idx % max(1, int(args.commit_every_files)) == 0:
                            conn.commit()
                        if idx % 20 == 0:
                            print(f"Progress: files {idx}/{total_files}, chunks {total_chunks} (reused)")
                        continue

                embedded = list(executor.map(lambda c: embed_chunk(c, args.embedding), chunks))
                for item in embedded:
                    upsert_case_chunk(conn, item["chunk"])
                    batch.append({"id": item["id"], "vector": item["vector"], "payload": item["payload"]})
                    total_chunks += 1

                    if len(batch) >= batch_size:
                        client.upsert(collection_name=args.collection, points=batch)
                        batch.clear()

                if idx % max(1, int(args.commit_every_files)) == 0:
                    conn.commit()

                if idx % 20 == 0:
                    print(f"Progress: files {idx}/{total_files}, chunks {total_chunks}")

        conn.commit()

    if batch:
        client.upsert(collection_name=args.collection, points=batch)

    print(
        f"Inserted {total_chunks} chunks from {total_files} files "
        f"(planned {total_files_before_resume}, skipped {skipped_files}) "
        f"into {args.collection} and {db_path}"
    )


if __name__ == "__main__":
    main()
