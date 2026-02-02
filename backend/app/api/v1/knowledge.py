from fastapi import APIRouter, HTTPException

from app.schemas.knowledge import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.services import knowledge as knowledge_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/search", response_model=KnowledgeSearchResponse)
def search(req: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    try:
        results = knowledge_service.search(req.query, req.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return KnowledgeSearchResponse(results=results)


@router.get("/chunk/{chunk_id}")
def get_chunk(chunk_id: str) -> dict:
    chunk = knowledge_service.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")
    return chunk
