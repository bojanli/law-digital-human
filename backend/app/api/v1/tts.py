from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import tts as tts_service

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    emotion: str = Field(default="calm")


class TtsSynthesizeResponse(BaseModel):
    audio_url: str | None = None


class TtsJobResponse(BaseModel):
    tts_job_id: str | None = None


class TtsJobStatusResponse(BaseModel):
    status: str
    audio_url: str | None = None


@router.get("/files/{file_name}")
def get_tts_audio(file_name: str):
    base_dir = Path(settings.tts_audio_store_dir).resolve()
    target = (base_dir / file_name).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)


@router.post("/synthesize", response_model=TtsSynthesizeResponse)
def synthesize_tts(req: TtsSynthesizeRequest) -> TtsSynthesizeResponse:
    audio_url = tts_service.synthesize(req.text, emotion=req.emotion)
    audio_url = tts_service.public_audio_url(audio_url)
    return TtsSynthesizeResponse(audio_url=audio_url)


@router.post("/jobs", response_model=TtsJobResponse)
def create_tts_job(req: TtsSynthesizeRequest) -> TtsJobResponse:
    job_id = tts_service.start_synthesize_job(req.text, emotion=req.emotion)
    return TtsJobResponse(tts_job_id=job_id)


@router.get("/jobs/{job_id}", response_model=TtsJobStatusResponse)
def get_tts_job(job_id: str) -> TtsJobStatusResponse:
    status, audio_url = tts_service.read_synthesize_job(job_id)
    return TtsJobStatusResponse(status=status, audio_url=audio_url)
