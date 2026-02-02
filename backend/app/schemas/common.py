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


class Citation(BaseModel):
    chunk_id: str
    law_name: str | None = None
    article_no: str | None = None
    section: str | None = None
    tags: list[str] | None = None
    source: str | None = None
