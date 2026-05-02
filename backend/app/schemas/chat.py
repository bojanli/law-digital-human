from pydantic import BaseModel, Field
from typing import Literal
from app.schemas.common import Citation

ModelVariant = Literal["default", "fast"]


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    text: str = Field(..., min_length=1, description="用户输入文本")
    mode: Literal["chat", "case"] = Field(default="chat", description="模式：普通问答/案件模拟")
    case_state: dict | None = Field(default=None, description="案件状态（可选）")
    model_variant: ModelVariant = Field(default="default", description="模型变体：默认/快速")
    top_k: int | None = Field(default=None, ge=1, le=12, description="本次检索 TopK 覆盖值")
    use_hybrid_search: bool | None = Field(default=None, description="预留：混合检索开关，当前后端未启用")
    use_rerank: bool | None = Field(default=None, description="预留：重排开关，当前后端未启用")
    temperature: float | None = Field(default=None, ge=0.0, le=1.0, description="本次 LLM temperature 覆盖值")
    max_tokens: int | None = Field(default=None, ge=128, le=4096, description="本次 LLM max_tokens 覆盖值")
    citation_strict: bool | None = Field(default=None, description="本次 citation 严格校验覆盖值")
    enable_tts: bool | None = Field(default=None, description="本次是否生成后端 TTS")


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
    tts_job_id: str | None = None
