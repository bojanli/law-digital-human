import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.core.logging import log_event
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat as chat_service
from app.services import knowledge as knowledge_service
from app.services import metrics as metrics_service

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    try:
        evidence = knowledge_service.search(req.text, settings.chat_top_k)
        answer = chat_service.build_answer(req, evidence)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "info",
            "chat_handled",
            rid=request_id,
            session_id=req.session_id,
            mode=req.mode,
            evidence=len(evidence),
            citations=len(answer.citations),
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="chat",
            ok=True,
            status_code=200,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"mode": req.mode, "evidence": len(evidence), "citations": len(answer.citations)},
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "exception",
            "chat_failed",
            rid=request_id,
            session_id=req.session_id,
            mode=req.mode,
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="chat",
            ok=False,
            status_code=500,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"mode": req.mode},
        )
        raise HTTPException(status_code=500, detail="聊天服务暂时不可用，请稍后重试") from exc
    return ChatResponse(answer_json=answer, audio_url=None)
