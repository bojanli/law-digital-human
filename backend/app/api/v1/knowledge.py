import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import log_event
from app.schemas.knowledge import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.services import knowledge as knowledge_service
from app.services import metrics as metrics_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search(req: KnowledgeSearchRequest, request: Request) -> KnowledgeSearchResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    try:
        results = knowledge_service.search(req.query, req.top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "info",
            "knowledge_search_handled",
            rid=request_id,
            top_k=req.top_k,
            hit=len(results),
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="knowledge_search",
            ok=True,
            status_code=200,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"top_k": req.top_k, "hit": len(results)},
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "exception",
            "knowledge_search_failed",
            rid=request_id,
            query=req.query,
            top_k=req.top_k,
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="knowledge_search",
            ok=False,
            status_code=500,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"top_k": req.top_k},
        )
        raise HTTPException(status_code=500, detail="知识检索暂时不可用，请稍后重试") from exc
    return KnowledgeSearchResponse(results=results)


@router.get("/chunk/{chunk_id}")
def get_chunk(chunk_id: str, request: Request) -> dict:
    request_id = getattr(request.state, "request_id", "")
    chunk = knowledge_service.get_chunk(chunk_id)
    if not chunk:
        log_event(logger, "info", "knowledge_chunk_not_found", rid=request_id, chunk_id=chunk_id)
        metrics_service.record_api_call(
            endpoint="knowledge_chunk",
            ok=False,
            status_code=404,
            latency_ms=0.0,
            request_id=request_id,
            meta={"chunk_id": chunk_id},
        )
        raise HTTPException(status_code=404, detail="chunk not found")
    log_event(logger, "info", "knowledge_chunk_hit", rid=request_id, chunk_id=chunk_id)
    metrics_service.record_api_call(
        endpoint="knowledge_chunk",
        ok=True,
        status_code=200,
        latency_ms=0.0,
        request_id=request_id,
        meta={"chunk_id": chunk_id},
    )
    return chunk
