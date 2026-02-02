from pydantic import BaseModel, Field
from app.schemas.common import Citation


class CaseStartRequest(BaseModel):
    case_id: str = Field(..., description="案件模板ID")


class CaseStepRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    user_input: str | None = Field(default=None, description="用户输入")
    user_choice: str | None = Field(default=None, description="用户选择（分支）")


class CaseResponse(BaseModel):
    text: str
    next_question: str | None = None
    state: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    emotion: str = "calm"
    audio_url: str | None = None
