import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import log_event
from app.schemas.case import CaseStartRequest, CaseStepRequest, CaseResponse
from app.services import case as case_service
from app.services import metrics as metrics_service

router = APIRouter(prefix="/api/case", tags=["case"])
logger = logging.getLogger(__name__)


@router.post("/start", response_model=CaseResponse)
def start_case(req: CaseStartRequest, request: Request) -> CaseResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    try:
        resp = case_service.start_case(req)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "info",
            "case_start_handled",
            rid=request_id,
            case_id=req.case_id,
            session_id=resp.session_id,
            state=resp.state,
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="case_start",
            ok=True,
            status_code=200,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"case_id": req.case_id, "state": resp.state},
        )
        return resp
    except case_service.CaseNotFoundError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics_service.record_api_call(
            endpoint="case_start",
            ok=False,
            status_code=404,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"case_id": req.case_id},
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "exception",
            "case_start_failed",
            rid=request_id,
            case_id=req.case_id,
            session_id=req.session_id,
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="case_start",
            ok=False,
            status_code=500,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"case_id": req.case_id},
        )
        raise HTTPException(status_code=500, detail="案件服务暂时不可用，请稍后重试") from exc


@router.post("/step", response_model=CaseResponse)
def case_step(req: CaseStepRequest, request: Request) -> CaseResponse:
    started = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")
    try:
        resp = case_service.step_case(req)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "info",
            "case_step_handled",
            rid=request_id,
            session_id=req.session_id,
            state=resp.state,
            path_len=len(resp.path),
            missing_slots=len(resp.missing_slots),
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="case_step",
            ok=True,
            status_code=200,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"state": resp.state, "missing_slots": len(resp.missing_slots), "path_len": len(resp.path)},
        )
        return resp
    except case_service.CaseSessionNotFoundError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics_service.record_api_call(
            endpoint="case_step",
            ok=False,
            status_code=404,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"session_id": req.session_id},
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics_service.record_api_call(
            endpoint="case_step",
            ok=False,
            status_code=400,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"session_id": req.session_id},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            "exception",
            "case_step_failed",
            rid=request_id,
            session_id=req.session_id,
            cost_ms=f"{elapsed_ms:.2f}",
        )
        metrics_service.record_api_call(
            endpoint="case_step",
            ok=False,
            status_code=500,
            latency_ms=elapsed_ms,
            request_id=request_id,
            meta={"session_id": req.session_id},
        )
        raise HTTPException(status_code=500, detail="案件服务暂时不可用，请稍后重试") from exc
