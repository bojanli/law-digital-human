import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib import request


def parse_queries(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"Invalid line (need 3 tab-separated fields): {line}")
        category, query, expected = parts
        expected_keywords = [x.strip() for x in expected.split(";") if x.strip()]
        rows.append(
            {
                "category": category.strip(),
                "query": query.strip(),
                "expected_keywords": expected_keywords,
            }
        )
    return rows


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    import urllib.error
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 500 and e.fp:
            body = e.fp.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("detail", body)
            except Exception:
                detail = body
            print(f"API 500 error: {detail}")
        raise


def hit_rank(results: list[dict[str, Any]], expected_keywords: list[str]) -> int | None:
    lowered = [k.lower() for k in expected_keywords]
    for idx, item in enumerate(results, start=1):
        corpus = " ".join(
            [
                str(item.get("law_name") or ""),
                str(item.get("article_no") or ""),
                str(item.get("section") or ""),
                str(item.get("tags") or ""),
                str(item.get("source") or ""),
                str(item.get("text") or ""),
            ]
        ).lower()
        if any(k in corpus for k in lowered):
            return idx
    return None


def summarize(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    hit1 = sum(1 for r in rows if r["hit_rank"] == 1)
    hit3 = sum(1 for r in rows if r["hit_rank"] is not None and r["hit_rank"] <= 3)
    hit5 = sum(1 for r in rows if r["hit_rank"] is not None and r["hit_rank"] <= 5)
    avg_ms = sum(r["latency_ms"] for r in rows) / total if total else 0.0

    print("\n=== Retrieval Eval Summary ===")
    print(f"Total: {total}")
    print(f"Top1 hit rate: {hit1}/{total} = {hit1 / total:.2%}" if total else "Top1 hit rate: N/A")
    print(f"Top3 hit rate: {hit3}/{total} = {hit3 / total:.2%}" if total else "Top3 hit rate: N/A")
    print(f"Top5 hit rate: {hit5}/{total} = {hit5 / total:.2%}" if total else "Top5 hit rate: N/A")
    print(f"Avg latency: {avg_ms:.1f} ms")

    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    print("\nBy category:")
    for cat, items in by_cat.items():
        c_total = len(items)
        c_hit3 = sum(1 for x in items if x["hit_rank"] is not None and x["hit_rank"] <= 3)
        print(f"- {cat}: Top3 {c_hit3}/{c_total} = {c_hit3 / c_total:.2%}")

    misses = [r for r in rows if r["hit_rank"] is None]
    if misses:
        print("\nMissed queries:")
        for m in misses:
            print(f"- [{m['category']}] {m['query']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="backend/tests/retrieval_queries.txt",
        help="tab-separated query file",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/api/knowledge/search",
        help="knowledge search endpoint",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--output",
        default="backend/tests/retrieval_eval_results.csv",
        help="csv output path",
    )
    args = parser.parse_args()

    query_rows = parse_queries(Path(args.input))
    result_rows: list[dict[str, Any]] = []

    print(f"Running {len(query_rows)} queries against {args.url} ...")
    for idx, row in enumerate(query_rows, start=1):
        t0 = time.perf_counter()
        resp = post_json(args.url, {"query": row["query"], "top_k": args.top_k})
        latency_ms = (time.perf_counter() - t0) * 1000.0
        results = resp.get("results", [])
        rank = hit_rank(results, row["expected_keywords"])

        top1 = results[0] if results else {}
        result_rows.append(
            {
                "idx": idx,
                "category": row["category"],
                "query": row["query"],
                "expected_keywords": ";".join(row["expected_keywords"]),
                "hit_rank": rank,
                "latency_ms": round(latency_ms, 2),
                "top1_law": top1.get("law_name"),
                "top1_article": top1.get("article_no"),
                "top1_source": top1.get("source"),
            }
        )
        rank_text = rank if rank is not None else "miss"
        print(f"[{idx:02d}] {row['category']} rank={rank_text} latency={latency_ms:.1f}ms")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "idx",
                "category",
                "query",
                "expected_keywords",
                "hit_rank",
                "latency_ms",
                "top1_law",
                "top1_article",
                "top1_source",
            ],
        )
        writer.writeheader()
        writer.writerows(result_rows)

    summarize(result_rows)
    print(f"\nSaved CSV: {output_path}")


if __name__ == "__main__":
    main()
