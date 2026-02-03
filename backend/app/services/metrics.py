import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.core.config import settings


def _get_db_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    db_path = Path(settings.metrics_db_path)
    if not db_path.is_absolute():
        db_path = root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(_get_db_path())


def ensure_metrics_table() -> None:
    with closing(_get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                ok INTEGER NOT NULL,
                status_code INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                request_id TEXT,
                meta_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def record_api_call(
    endpoint: str,
    ok: bool,
    status_code: int,
    latency_ms: float,
    request_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    ensure_metrics_table()
    with closing(_get_conn()) as conn:
        conn.execute(
            """
            INSERT INTO api_metrics (endpoint, ok, status_code, latency_ms, request_id, meta_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                endpoint,
                1 if ok else 0,
                int(status_code),
                float(latency_ms),
                request_id or None,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        conn.commit()


def get_metrics_summary(endpoint: str | None = None, days: int | None = None) -> dict[str, Any]:
    ensure_metrics_table()
    where_sql, params = _build_filter(endpoint=endpoint, days=days)
    with closing(_get_conn()) as conn:
        total, ok_count, avg_latency = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(ok), 0) AS ok_count,
                COALESCE(AVG(latency_ms), 0.0) AS avg_latency
            FROM api_metrics
            {where_sql}
            """,
            params,
        ).fetchone()

        grouped = conn.execute(
            f"""
            SELECT
                endpoint,
                COUNT(*) AS total,
                COALESCE(SUM(ok), 0) AS ok_count,
                COALESCE(AVG(latency_ms), 0.0) AS avg_latency
            FROM api_metrics
            {where_sql}
            GROUP BY endpoint
            ORDER BY endpoint ASC
            """,
            params,
        ).fetchall()

    total_i = int(total or 0)
    ok_i = int(ok_count or 0)
    fail_i = total_i - ok_i
    by_endpoint: list[dict[str, Any]] = []
    for row in grouped:
        ep = str(row[0])
        ep_total = int(row[1] or 0)
        ep_ok = int(row[2] or 0)
        ep_fail = ep_total - ep_ok
        by_endpoint.append(
            {
                "endpoint": ep,
                "total": ep_total,
                "ok": ep_ok,
                "fail": ep_fail,
                "ok_rate": (ep_ok / ep_total) if ep_total else 0.0,
                "avg_latency_ms": float(row[3] or 0.0),
            }
        )

    return {
        "total": total_i,
        "ok": ok_i,
        "fail": fail_i,
        "ok_rate": (ok_i / total_i) if total_i else 0.0,
        "avg_latency_ms": float(avg_latency or 0.0),
        "by_endpoint": by_endpoint,
    }


def fetch_metrics_rows(endpoint: str | None = None, days: int | None = None) -> list[dict[str, Any]]:
    ensure_metrics_table()
    where_sql, params = _build_filter(endpoint=endpoint, days=days)
    with closing(_get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, endpoint, ok, status_code, latency_ms, request_id, meta_json, created_at
            FROM api_metrics
            {where_sql}
            ORDER BY id ASC
            """,
            params,
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        meta_raw = row["meta_json"]
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        out.append(
            {
                "id": int(row["id"]),
                "endpoint": str(row["endpoint"]),
                "ok": int(row["ok"]),
                "status_code": int(row["status_code"]),
                "latency_ms": float(row["latency_ms"]),
                "request_id": row["request_id"],
                "meta": meta,
                "created_at": str(row["created_at"]),
            }
        )
    return out


def _build_filter(endpoint: str | None = None, days: int | None = None) -> tuple[str, tuple[Any, ...]]:
    clauses: list[str] = []
    params: list[Any] = []
    if endpoint:
        clauses.append("endpoint = ?")
        params.append(endpoint)
    if days and days > 0:
        clauses.append("created_at >= datetime('now', ?)")
        params.append(f"-{int(days)} day")
    if not clauses:
        return "", tuple()
    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def get_paper_kpis(days: int | None = None) -> dict[str, Any]:
    rows = fetch_metrics_rows(days=days)
    chat_rows = [row for row in rows if row["endpoint"] == "chat" and int(row["ok"]) == 1]
    case_step_rows = [row for row in rows if row["endpoint"] == "case_step" and int(row["ok"]) == 1]

    with_evidence = [r for r in chat_rows if _meta_int(r, "evidence") > 0]
    citation_hits = [r for r in with_evidence if _meta_int(r, "citations") > 0]
    no_evidence_rows = [r for r in chat_rows if _meta_int(r, "evidence") == 0]
    no_evidence_rejects = [r for r in no_evidence_rows if _is_no_evidence_reject(r)]

    return {
        "days": int(days) if days else None,
        "chat_total": len(chat_rows),
        "chat_with_evidence": len(with_evidence),
        "citation_hit_rate": _ratio(len(citation_hits), len(with_evidence)),
        "chat_no_evidence": len(no_evidence_rows),
        "no_evidence_reject_rate": _ratio(len(no_evidence_rejects), len(no_evidence_rows)),
        "chat_latency": _latency_stats(chat_rows),
        "case_step_latency": _latency_stats(case_step_rows),
    }


def _latency_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(r["latency_ms"]) for r in rows]
    if not values:
        return {"sample_size": 0, "p50_ms": 0.0, "p90_ms": 0.0, "avg_ms": 0.0}
    return {
        "sample_size": len(values),
        "p50_ms": _percentile(values, 50),
        "p90_ms": _percentile(values, 90),
        "avg_ms": sum(values) / len(values),
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    weight = rank - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def _ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


def _meta_int(row: dict[str, Any], key: str) -> int:
    meta = row.get("meta") or {}
    value = meta.get(key) if isinstance(meta, dict) else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_no_evidence_reject(row: dict[str, Any]) -> bool:
    meta = row.get("meta") or {}
    if not isinstance(meta, dict):
        return False
    explicit = meta.get("no_evidence_reject")
    if isinstance(explicit, bool):
        return explicit
    return _meta_int(row, "citations") == 0 and str(meta.get("answer_emotion") or "").strip().lower() == "serious"
