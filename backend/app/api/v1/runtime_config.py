from fastapi import APIRouter

from app.schemas.runtime_config import RuntimeConfig
from app.services import runtime_config as runtime_config_service

router = APIRouter(prefix="/api/admin/runtime-config", tags=["runtime-config"])


@router.get("", response_model=RuntimeConfig)
def get_runtime_config() -> RuntimeConfig:
    return runtime_config_service.get_runtime_config()


@router.put("", response_model=RuntimeConfig)
def update_runtime_config(payload: RuntimeConfig) -> RuntimeConfig:
    return runtime_config_service.update_runtime_config(payload)
