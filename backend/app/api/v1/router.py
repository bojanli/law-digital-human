from fastapi import APIRouter
from app.api.v1.chat import router as chat_router
from app.api.v1.case import router as case_router
from app.api.v1.knowledge import router as knowledge_router

api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(case_router)
api_router.include_router(knowledge_router)
