from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat as chat_service
from app.services import knowledge as knowledge_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        evidence = knowledge_service.search(req.text, settings.chat_top_k)
        answer = chat_service.build_answer(req, evidence)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer_json=answer, audio_url=None)
