from typing import Any

from pydantic import BaseModel, Field, model_validator
from app.schemas.common import Citation


class CaseStartRequest(BaseModel):
    case_id: str = Field(..., min_length=1, description="案件模板ID")
    session_id: str | None = Field(default=None, description="会话ID（可选，不传则后端生成）")


class CaseStepRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="会话ID")
    user_input: str | None = Field(default=None, description="用户输入")
    user_choice: str | None = Field(default=None, description="用户选择（分支）")

    @model_validator(mode="after")
    def validate_payload(self) -> "CaseStepRequest":
        if not (self.user_input and self.user_input.strip()) and not (self.user_choice and self.user_choice.strip()):
            raise ValueError("user_input 和 user_choice 不能同时为空")
        return self


class CaseResponse(BaseModel):
    session_id: str
    case_id: str
    text: str
    next_question: str | None = None
    state: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)
    path: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    emotion: str = "calm"
    audio_url: str | None = None
