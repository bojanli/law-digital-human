from pydantic import BaseModel, Field
from typing import Literal
from app.schemas.common import Citation


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    text: str = Field(..., min_length=1, description="用户输入文本")
    mode: Literal["chat", "case"] = Field(default="chat", description="模式：普通问答/案件模拟")
    case_state: dict | None = Field(default=None, description="案件状态（可选）")


class AnswerJson(BaseModel):
    conclusion: str
    analysis: list[str]
    actions: list[str]
    citations: list[Citation]
    assumptions: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    emotion: str = "calm"


class ChatResponse(BaseModel):
    answer_json: AnswerJson
    audio_url: str | None = None
