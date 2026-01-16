from pydantic import BaseModel
from typing import Any


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str


class ApiResponse(BaseModel):
    ok: bool = True
    data: Any = None
    message: str | None = None
