from fastapi import APIRouter, HTTPException

from app.schemas.case import CaseStartRequest, CaseStepRequest, CaseResponse
from app.services import case as case_service

router = APIRouter(prefix="/api/case", tags=["case"])


@router.post("/start", response_model=CaseResponse)
def start_case(req: CaseStartRequest) -> CaseResponse:
    try:
        return case_service.start_case(req)
    except case_service.CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/step", response_model=CaseResponse)
def case_step(req: CaseStepRequest) -> CaseResponse:
    try:
        return case_service.step_case(req)
    except case_service.CaseSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
