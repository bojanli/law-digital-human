import logging
import time
import csv
import io

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.core.logging import log_event
from app.schemas.metrics import MetricsSummaryResponse, PaperKpiResponse
from app.services import metrics as metrics_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
def metrics_summary(
    request: Request,
    endpoint: str | None = Query(default=None, description="按接口名过滤，如 chat/case_step"),
    days: int | None = Query(default=None, ge=1, le=365, description="仅统计最近 N 天"),
) -> MetricsSummaryResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    summary = metrics_service.get_metrics_summary(endpoint=endpoint, days=days)
    elapsed_ms = (time.perf_counter() - started) * 1000
    log_event(
        logger,
        "info",
        "metrics_summary_handled",
        rid=request_id,
        endpoint=endpoint,
        days=days,
        total=summary["total"],
        cost_ms=f"{elapsed_ms:.2f}",
    )
    return MetricsSummaryResponse(**summary)


@router.get("/metrics/export")
def metrics_export(
    request: Request,
    endpoint: str | None = Query(default=None, description="按接口名过滤，如 chat/case_step"),
    days: int | None = Query(default=None, ge=1, le=365, description="仅导出最近 N 天"),
) -> StreamingResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    rows = metrics_service.fetch_metrics_rows(endpoint=endpoint, days=days)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "endpoint",
            "ok",
            "status_code",
            "latency_ms",
            "request_id",
            "created_at",
            "meta",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "id": row["id"],
                "endpoint": row["endpoint"],
                "ok": row["ok"],
                "status_code": row["status_code"],
                "latency_ms": row["latency_ms"],
                "request_id": row["request_id"],
                "created_at": row["created_at"],
                "meta": row["meta"],
            }
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    log_event(
        logger,
        "info",
        "metrics_export_handled",
        rid=request_id,
        endpoint=endpoint,
        days=days,
        rows=len(rows),
        cost_ms=f"{elapsed_ms:.2f}",
    )

    filename = "metrics_export.csv"
    if endpoint:
        filename = f"metrics_export_{endpoint}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/metrics/paper-kpi", response_model=PaperKpiResponse)
def metrics_paper_kpi(
    request: Request,
    days: int | None = Query(default=None, ge=1, le=365, description="仅统计最近 N 天"),
) -> PaperKpiResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    payload = metrics_service.get_paper_kpis(days=days)
    elapsed_ms = (time.perf_counter() - started) * 1000
    log_event(
        logger,
        "info",
        "metrics_paper_kpi_handled",
        rid=request_id,
        days=days,
        chat_total=payload["chat_total"],
        cost_ms=f"{elapsed_ms:.2f}",
    )
    return PaperKpiResponse(**payload)
