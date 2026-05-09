import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


@dataclass
class QueryCase:
    category: str
    query: str
    expected_keywords: list[str]


def parse_queries(path: Path) -> list[QueryCase]:
    rows: list[QueryCase] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"{path}:{line_no} need 3 tab-separated fields")
        category, query, expected = parts
        keywords = [item.strip() for item in expected.split(";") if item.strip()]
        if not keywords:
            raise ValueError(f"{path}:{line_no} expected_keywords cannot be empty")
        rows.append(QueryCase(category=category.strip(), query=query.strip(), expected_keywords=keywords))
    return rows


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_with_testclient(client: Any, query: str, top_k: int) -> dict[str, Any]:
    resp = client.post("/api/knowledge/search", json={"query": query, "top_k": top_k})
    resp.raise_for_status()
    return resp.json()


def hit_rank(results: list[dict[str, Any]], expected_keywords: list[str]) -> int | None:
    lowered = [keyword.lower() for keyword in expected_keywords]
    for idx, item in enumerate(results, start=1):
        corpus = " ".join(
            str(item.get(field) or "")
            for field in (
                "law_name",
                "article_no",
                "section",
                "tags",
                "source",
                "text",
                "case_name",
                "charges",
                "articles",
            )
        ).lower()
        if any(keyword in corpus for keyword in lowered):
            return idx
    return None


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "N/A"
    return f"{numerator / denominator * 100:.2f}%"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    hit1 = sum(1 for row in rows if row["hit_rank"] == 1)
    hit3 = sum(1 for row in rows if row["hit_rank"] is not None and row["hit_rank"] <= 3)
    hit5 = sum(1 for row in rows if row["hit_rank"] is not None and row["hit_rank"] <= 5)
    avg_ms = sum(float(row["latency_ms"]) for row in rows) / total if total else 0.0
    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_category.setdefault(row["category"], {"total": 0, "hit1": 0, "hit3": 0, "hit5": 0})
        bucket["total"] += 1
        if row["hit_rank"] == 1:
            bucket["hit1"] += 1
        if row["hit_rank"] is not None and row["hit_rank"] <= 3:
            bucket["hit3"] += 1
        if row["hit_rank"] is not None and row["hit_rank"] <= 5:
            bucket["hit5"] += 1

    return {
        "total": total,
        "top1_hits": hit1,
        "top3_hits": hit3,
        "top5_hits": hit5,
        "top1_rate": round(hit1 / total, 4) if total else 0.0,
        "top3_rate": round(hit3 / total, 4) if total else 0.0,
        "top5_rate": round(hit5 / total, 4) if total else 0.0,
        "avg_latency_ms": round(avg_ms, 2),
        "by_category": by_category,
        "misses": [row for row in rows if row["hit_rank"] is None],
    }


def to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 检索质量测试报告（80题正式版）",
        "",
        f"- 测试时间：{report['meta']['run_at']}",
        f"- 测试集：`{report['meta']['input']}`",
        f"- 检索方式：{report['meta']['mode']}",
        f"- top_k：{report['meta']['top_k']}",
        "",
        "## 总体结果",
        "",
        "| 指标 | 命中数 | 样本数 | 比例 |",
        "|---|---:|---:|---:|",
        f"| Top1 | {summary['top1_hits']} | {summary['total']} | {summary['top1_rate'] * 100:.2f}% |",
        f"| Top3 | {summary['top3_hits']} | {summary['total']} | {summary['top3_rate'] * 100:.2f}% |",
        f"| Top5 | {summary['top5_hits']} | {summary['total']} | {summary['top5_rate'] * 100:.2f}% |",
        f"| 平均耗时 | - | - | {summary['avg_latency_ms']:.2f} ms |",
        "",
        "## 分类结果",
        "",
        "| 类别 | 样本数 | Top1 | Top3 | Top5 |",
        "|---|---:|---:|---:|---:|",
    ]
    for category, item in summary["by_category"].items():
        total = item["total"]
        lines.append(
            f"| {category} | {total} | {item['hit1']}/{total} ({pct(item['hit1'], total)}) | "
            f"{item['hit3']}/{total} ({pct(item['hit3'], total)}) | {item['hit5']}/{total} ({pct(item['hit5'], total)}) |"
        )

    lines.extend(["", "## 未命中问题", ""])
    if summary["misses"]:
        for row in summary["misses"]:
            lines.append(f"- [{row['idx']:02d}] {row['category']}：{row['query']}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本报告用于正式检索质量评估，测试集共 80 个问题。",
            "- 命中判定依据为返回结果的法条名、条号、章节、标签、来源、正文或案例字段是否包含期望关键词之一。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval quality evaluation on the official query set.")
    parser.add_argument("--input", default="backend/tests/retrieval_queries.txt", help="TSV query file")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--url", default="", help="Optional running backend endpoint, e.g. http://127.0.0.1:8000/api/knowledge/search")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--csv-out", default="backend/tests/reports/retrieval_quality_80_results.csv")
    parser.add_argument("--json-out", default="backend/tests/reports/retrieval_quality_80_report.json")
    parser.add_argument("--md-out", default="backend/tests/reports/retrieval_quality_80_report.md")
    args = parser.parse_args()

    input_path = ROOT / args.input
    cases = parse_queries(input_path)
    rows: list[dict[str, Any]] = []
    mode = args.url or "FastAPI TestClient"

    print(f"Running retrieval quality eval: {len(cases)} queries, mode={mode}, top_k={args.top_k}")

    client_context = None
    client = None
    if not args.url:
        from fastapi.testclient import TestClient

        from app.main import app

        client_context = TestClient(app)
        client = client_context.__enter__()

    try:
        for idx, case in enumerate(cases, start=1):
            started = time.perf_counter()
            if args.url:
                resp = post_json(args.url, {"query": case.query, "top_k": args.top_k}, timeout=args.timeout)
            else:
                resp = search_with_testclient(client, case.query, args.top_k)
            latency_ms = (time.perf_counter() - started) * 1000
            results = resp.get("results", [])
            rank = hit_rank(results, case.expected_keywords)
            top1 = results[0] if results else {}
            row = {
                "idx": idx,
                "category": case.category,
                "query": case.query,
                "expected_keywords": ";".join(case.expected_keywords),
                "hit_rank": rank,
                "latency_ms": round(latency_ms, 2),
                "top1_law": top1.get("law_name"),
                "top1_article": top1.get("article_no"),
                "top1_section": top1.get("section"),
                "top1_source_type": top1.get("source_type"),
                "top1_score": top1.get("score"),
            }
            rows.append(row)
            print(f"[{idx:02d}/{len(cases)}] {case.category} rank={rank if rank is not None else 'miss'} {latency_ms:.1f}ms")
    finally:
        if client_context is not None:
            client_context.__exit__(None, None, None)

    report = {
        "meta": {
            "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "input": str(input_path),
            "mode": mode,
            "top_k": args.top_k,
        },
        "summary": summarize(rows),
        "rows": rows,
    }

    csv_out = ROOT / args.csv_out
    json_out = ROOT / args.json_out
    md_out = ROOT / args.md_out
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)

    with csv_out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(to_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print("\n=== Retrieval Quality Summary ===")
    print(f"Total: {summary['total']}")
    print(f"Top1: {summary['top1_hits']}/{summary['total']} = {summary['top1_rate'] * 100:.2f}%")
    print(f"Top3: {summary['top3_hits']}/{summary['total']} = {summary['top3_rate'] * 100:.2f}%")
    print(f"Top5: {summary['top5_hits']}/{summary['total']} = {summary['top5_rate'] * 100:.2f}%")
    print(f"CSV saved to: {csv_out}")
    print(f"JSON saved to: {json_out}")
    print(f"Markdown saved to: {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
