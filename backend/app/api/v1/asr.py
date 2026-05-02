import base64
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.asr import AsrTranscribeRequest, AsrTranscribeResponse
from app.services import asr as asr_service

router = APIRouter(prefix="/api/asr", tags=["asr"])


@router.post("/transcribe", response_model=AsrTranscribeResponse)
def transcribe(req: AsrTranscribeRequest) -> AsrTranscribeResponse:
    raw = (req.audio_base64 or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="音频内容为空")
    try:
        content = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="音频内容非法") from exc
    if not content:
        raise HTTPException(status_code=400, detail="音频内容为空")
    text = asr_service.transcribe(content, content_type=req.mime_type)
    detail, log_id = asr_service.get_last_asr_debug()
    return AsrTranscribeResponse(
        text=text,
        provider=settings.asr_provider.lower().strip() or "mock",
        detail=detail,
        log_id=log_id,
    )


@router.get("/files/{file_name}")
def get_uploaded_audio(file_name: str):
    base_dir = Path(settings.asr_audio_store_dir).resolve()
    target = (base_dir / file_name).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)
