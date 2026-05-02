from fastapi import APIRouter
from app.api.v1.chat import router as chat_router
from app.api.v1.case import router as case_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.admin import router as admin_router
from app.api.v1.runtime_config import public_router as settings_router
from app.api.v1.runtime_config import router as runtime_config_router
from app.api.v1.asr import router as asr_router
from app.api.v1.tts import router as tts_router

api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(case_router)
api_router.include_router(knowledge_router)
api_router.include_router(admin_router)
api_router.include_router(runtime_config_router)
api_router.include_router(settings_router)
api_router.include_router(asr_router)
api_router.include_router(tts_router)
