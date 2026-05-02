import logging
import time
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.logging import log_event
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat as chat_service
from app.services import knowledge as knowledge_service
from app.services import metrics as metrics_service
from app.services import runtime_config as runtime_config_service
from app.services import session_store
from app.services import tts as tts_service

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


def _effective_top_k(req: ChatRequest, default_top_k: int) -> int:
    return min(12, max(1, req.top_k if req.top_k is not None else default_top_k))


def _effective_rerank(req: ChatRequest, default_enabled: bool) -> bool:
    return req.use_rerank if req.use_rerank is not None else default_enabled


def _should_generate_tts(req: ChatRequest, default_enabled: bool) -> bool:
    return req.enable_tts if req.enable_tts is not None else default_enabled


def _search_knowledge_for_chat(query: str, top_k: int, req: ChatRequest, runtime_rerank: bool):
    if req.use_rerank is None:
        return knowledge_service.search(query, top_k)
    return knowledge_service.search(query, top_k, use_rerank=runtime_rerank)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    stage_ms: dict[str, float] = {}
    try:
        # 1. 获取历史记录
        stage_started = time.perf_counter()
        history = session_store.get_chat_history(req.session_id)
        stage_ms["history"] = (time.perf_counter() - stage_started) * 1000
        
        # 2. Query Rewrite
        stage_started = time.perf_counter()
        rewritten_text = chat_service.rewrite_query(history, req.text) if history else req.text
        search_text = chat_service.expand_legal_query(rewritten_text)
        stage_ms["rewrite"] = (time.perf_counter() - stage_started) * 1000
        
        # 3. 检索时使用重写/扩展后的 search_text
        runtime = runtime_config_service.get_runtime_config()
        top_k = _effective_top_k(req, runtime.chat_top_k)
        use_rerank = _effective_rerank(req, runtime.enable_rerank)
        stage_started = time.perf_counter()
        evidence = _search_knowledge_for_chat(search_text, top_k, req, use_rerank)
        answer_evidence = chat_service.select_answer_evidence(evidence)
        stage_ms["search"] = (time.perf_counter() - stage_started) * 1000
        
        # 4. 回答时带上 context
        stage_started = time.perf_counter()
        answer = chat_service.build_answer(req, answer_evidence, history)
        stage_ms["answer"] = (time.perf_counter() - stage_started) * 1000
        
        # 5. 更新并保存新的历史记录
        history.append({"role": "user", "content": req.text})
        history.append({"role": "assistant", "content": answer.conclusion})
        stage_started = time.perf_counter()
        session_store.save_chat_history(req.session_id, history)
        stage_ms["history_save"] = (time.perf_counter() - stage_started) * 1000

        stage_started = time.perf_counter()
        audio_url = None
        if _should_generate_tts(req, runtime.enable_tts):
            try:
                audio_url = tts_service.synthesize(answer.conclusion, emotion=answer.emotion)
                audio_url = tts_service.public_audio_url(audio_url)
            except Exception:
                log_event(
                    logger,
                    "warning",
                    "chat_tts_failed",
                    rid=request_id,
                    session_id=req.session_id,
                )
        stage_ms["tts"] = (time.perf_counter() - stage_started) * 1000
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "info",
            "chat_handled",
            rid=request_id,
            session_id=req.session_id,
            mode=req.mode,
            evidence=len(evidence),
            answer_evidence=len(answer_evidence),
            citations=len(answer.citations),
            audio_ready=bool(audio_url),
            model_variant=req.model_variant,
            rewrite_changed=search_text != req.text,
            rewrite_len=len(search_text),
            top_k=top_k,
            use_rerank=use_rerank,
            stage_history_ms=f"{stage_ms.get('history', 0.0):.2f}",
            stage_rewrite_ms=f"{stage_ms.get('rewrite', 0.0):.2f}",
            stage_search_ms=f"{stage_ms.get('search', 0.0):.2f}",
            stage_answer_ms=f"{stage_ms.get('answer', 0.0):.2f}",
            stage_history_save_ms=f"{stage_ms.get('history_save', 0.0):.2f}",
            stage_tts_ms=f"{stage_ms.get('tts', 0.0):.2f}",
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="chat",
            ok=True,
            status_code=200,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={
                "mode": req.mode,
                "top_k": top_k,
                "use_rerank": use_rerank,
                "evidence": len(evidence),
                "answer_evidence": len(answer_evidence),
                "citations": len(answer.citations),
                "answer_emotion": answer.emotion,
                "model_variant": req.model_variant,
                "llm_model": settings.resolved_fast_llm_model() if req.model_variant == "fast" else settings.resolved_llm_model(),
                "no_local_evidence_external_reference": bool(
                    len(evidence) == 0 and len(answer.citations) == 0 and answer.emotion == "supportive"
                ),
                "audio_ready": bool(audio_url),
                "rewrite_changed": search_text != req.text,
                "stage_history_ms": round(stage_ms.get("history", 0.0), 2),
                "stage_rewrite_ms": round(stage_ms.get("rewrite", 0.0), 2),
                "stage_search_ms": round(stage_ms.get("search", 0.0), 2),
                "stage_answer_ms": round(stage_ms.get("answer", 0.0), 2),
                "stage_history_save_ms": round(stage_ms.get("history_save", 0.0), 2),
                "stage_tts_ms": round(stage_ms.get("tts", 0.0), 2),
            },
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
    return ChatResponse(answer_json=answer, audio_url=audio_url, tts_job_id=None)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    request_id = getattr(request.state, "request_id", "")

    def emit(event: dict[str, object]) -> bytes:
        return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")

    def stream():
        started = time.perf_counter()
        stage_ms: dict[str, float] = {}
        try:
            stage_started = time.perf_counter()
            history = session_store.get_chat_history(req.session_id)
            stage_ms["history"] = (time.perf_counter() - stage_started) * 1000
            yield emit({"type": "status", "phase": "history"})

            stage_started = time.perf_counter()
            rewritten_text = chat_service.rewrite_query(history, req.text) if history else req.text
            search_text = chat_service.expand_legal_query(rewritten_text)
            stage_ms["rewrite"] = (time.perf_counter() - stage_started) * 1000
            yield emit({"type": "status", "phase": "search"})

            runtime = runtime_config_service.get_runtime_config()
            top_k = _effective_top_k(req, runtime.chat_top_k)
            use_rerank = _effective_rerank(req, runtime.enable_rerank)
            stage_started = time.perf_counter()
            evidence = _search_knowledge_for_chat(search_text, top_k, req, use_rerank)
            answer_evidence = chat_service.select_answer_evidence(evidence)
            stage_ms["search"] = (time.perf_counter() - stage_started) * 1000

            if not answer_evidence:
                answer = chat_service.build_answer(req, answer_evidence, history)
                history.append({"role": "user", "content": req.text})
                history.append({"role": "assistant", "content": answer.conclusion})
                session_store.save_chat_history(req.session_id, history)
                stage_started = time.perf_counter()
                audio_url = None
                if _should_generate_tts(req, runtime.enable_tts):
                    audio_url = tts_service.synthesize(answer.conclusion, emotion=answer.emotion)
                    audio_url = tts_service.public_audio_url(audio_url)
                stage_ms["tts"] = (time.perf_counter() - stage_started) * 1000
                yield emit({"type": "final", "answer_json": answer.model_dump(), "audio_url": audio_url, "tts_job_id": None})
                return

            yield emit({"type": "status", "phase": "answer"})
            stage_started = time.perf_counter()
            accumulated = ""
            for delta in chat_service.stream_answer_text(req, answer_evidence, history):
                accumulated += delta
                yield emit({"type": "delta", "text": delta})
            stage_ms["answer"] = (time.perf_counter() - stage_started) * 1000

            answer = chat_service.build_answer_from_stream_text(accumulated, answer_evidence)
            answer = chat_service._finalize_answer(
                answer,
                answer_evidence,
                runtime.default_emotion,
                req.citation_strict if req.citation_strict is not None else runtime.strict_citation_check,
                req,
            )

            stage_started = time.perf_counter()
            audio_url = None
            if _should_generate_tts(req, runtime.enable_tts):
                audio_url = tts_service.synthesize(answer.conclusion, emotion=answer.emotion)
                audio_url = tts_service.public_audio_url(audio_url)
            stage_ms["tts"] = (time.perf_counter() - stage_started) * 1000
            history.append({"role": "user", "content": req.text})
            history.append({"role": "assistant", "content": answer.conclusion})
            stage_started = time.perf_counter()
            session_store.save_chat_history(req.session_id, history)
            stage_ms["history_save"] = (time.perf_counter() - stage_started) * 1000

            elapsed_ms = (time.perf_counter() - started) * 1000
            metrics_service.record_api_call(
                endpoint="chat_stream",
                ok=True,
                status_code=200,
                latency_ms=elapsed_ms,
                request_id=request_id,
                meta={
                    "mode": req.mode,
                    "top_k": top_k,
                    "use_rerank": use_rerank,
                    "evidence": len(evidence),
                    "answer_evidence": len(answer_evidence),
                    "citations": len(answer.citations),
                    "answer_emotion": answer.emotion,
                    "model_variant": req.model_variant,
                    "llm_model": settings.resolved_fast_llm_model() if req.model_variant == "fast" else settings.resolved_llm_model(),
                    "audio_ready": bool(audio_url),
                    "rewrite_changed": search_text != req.text,
                    "stage_history_ms": round(stage_ms.get("history", 0.0), 2),
                    "stage_rewrite_ms": round(stage_ms.get("rewrite", 0.0), 2),
                    "stage_search_ms": round(stage_ms.get("search", 0.0), 2),
                    "stage_answer_ms": round(stage_ms.get("answer", 0.0), 2),
                    "stage_history_save_ms": round(stage_ms.get("history_save", 0.0), 2),
                    "stage_tts_ms": round(stage_ms.get("tts", 0.0), 2),
                },
            )
            yield emit({"type": "final", "answer_json": answer.model_dump(), "audio_url": audio_url, "tts_job_id": None})
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            metrics_service.record_api_call(
                endpoint="chat_stream",
                ok=False,
                status_code=500,
                latency_ms=elapsed_ms,
                request_id=request_id,
                meta={"mode": req.mode, "model_variant": req.model_variant},
            )
            yield emit({"type": "error", "detail": "聊天服务暂时不可用，请稍后重试"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")
