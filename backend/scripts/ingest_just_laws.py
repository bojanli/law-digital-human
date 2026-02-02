import argparse
import hashlib
import re
import sqlite3
import uuid
from pathlib import Path
import os

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

import sys

ROOT = Path(__file__).resolve().parents[2]
# Ensure local backend package wins over any installed "app" package.
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.services.embedding import embed_text

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")


ARTICLE_RE = re.compile(r"^\*\*(\u7b2c.+?\u6761)\*\*")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip()
    return text


def parse_articles(text: str) -> list[dict]:
    text = strip_front_matter(text)
    lines = text.splitlines()
    current_section = None
    current = None
    articles: list[dict] = []

    def flush():
        nonlocal current
        if not current:
            return
        body = "\n".join(current["body"]).strip()
        if body:
            current["text"] = body
            articles.append(current)
        current = None

    for line in lines:
        heading = HEADING_RE.match(line.strip())
        if heading:
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if level >= 2:
                current_section = heading_text
            continue

        m = ARTICLE_RE.match(line.strip())
        if m:
            flush()
            article_no = m.group(1)
            rest = line.strip()[len(m.group(0)) :].strip()
            current = {
                "article_no": article_no,
                "section": current_section,
                "body": [rest] if rest else [],
            }
            continue

        if current is not None:
            if line.strip() == "":
                current["body"].append("")
            else:
                current["body"].append(line.strip())

    flush()
    return articles


def chunk_text(text: str, max_len: int = 800) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    buf = ""
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 > max_len and buf:
            parts.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}".strip()
    if buf:
        parts.append(buf)
    return parts


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_law ON chunks(law_name)")


def upsert_chunk(conn: sqlite3.Connection, chunk: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO chunks
        (chunk_id, text, law_name, article_no, section, tags, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk["chunk_id"],
            chunk["text"],
            chunk.get("law_name"),
            chunk.get("article_no"),
            chunk.get("section"),
            chunk.get("tags"),
            chunk.get("source"),
        ),
    )


def ensure_collection(client: QdrantClient, collection: str, dim: int, recreate: bool) -> None:
    import time
    
    if recreate:
        # 使用新的 API：先检查是否存在，如果存在则删除，然后创建
        try:
            if client.collection_exists(collection):
                print(f"删除现有集合: {collection}")
                client.delete_collection(collection)
                # 等待删除完成
                time.sleep(1)
        except Exception as e:
            print(f"删除集合时出错（可能不存在）: {e}")
        
        # 重试创建集合
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"创建集合: {collection} (尝试 {attempt + 1}/{max_retries})")
                client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                print(f"集合 {collection} 创建成功")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"创建集合失败，等待后重试: {e}")
                    time.sleep(2)
                else:
                    raise
        return
    
    existing = client.get_collections().collections
    if not any(c.name == collection for c in existing):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="just-laws docs path")
    parser.add_argument("--db", default=settings.knowledge_db_path)
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.source)
    if not source_root.exists():
        raise SystemExit(f"Source not found: {source_root}")

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    init_db(db_path)

    client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
    ensure_collection(client, args.collection, settings.embedding_dim, args.recreate)

    md_files = list(source_root.rglob("*.md"))
    total = 0
    batch: list[dict] = []
    batch_size = 64

    with sqlite3.connect(db_path) as conn:
        for file_idx, path in enumerate(md_files, start=1):
            text = path.read_text(encoding="utf-8")
            articles = parse_articles(text)
            if not articles:
                continue

            law_name = None
            for line in text.splitlines():
                if line.startswith("# "):
                    law_name = line[2:].strip()
                    break
            if not law_name:
                law_name = path.parent.name

            tags = ",".join(path.parts[len(source_root.parts) : -1])
            source = str(path.relative_to(source_root))

            for article in articles:
                for idx, chunk_text_part in enumerate(chunk_text(article["text"])):
                    raw_id = f"{law_name}|{article['article_no']}|{idx}|{chunk_text_part}"
                    # Use UUID for Qdrant point ID; keep deterministic across runs.
                    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))
                    vector = embed_text(chunk_text_part)
                    payload = {
                        "chunk_id": chunk_id,
                        "law_name": law_name,
                        "article_no": article["article_no"],
                        "section": article.get("section"),
                        "tags": tags,
                        "source": source,
                    }

                    upsert_chunk(
                        conn,
                        {
                            "chunk_id": chunk_id,
                            "text": chunk_text_part,
                            "law_name": law_name,
                            "article_no": article["article_no"],
                            "section": article.get("section"),
                            "tags": tags,
                            "source": source,
                        },
                    )

                    batch.append({"id": chunk_id, "vector": vector, "payload": payload})
                    total += 1

                    if total % 100 == 0:
                        print(
                            f"Progress: {total} chunks | file {file_idx}/{len(md_files)} | {path.name}"
                        )

                    if len(batch) >= batch_size:
                        client.upsert(collection_name=args.collection, points=batch)
                        batch.clear()

        conn.commit()

    if batch:
        client.upsert(collection_name=args.collection, points=batch)
        batch.clear()

    print(f"Inserted {total} chunks into {args.collection} and {db_path}")


if __name__ == "__main__":
    main()
