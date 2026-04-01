from typing import Literal

from pydantic import BaseModel, Field


EmotionTag = Literal["calm", "serious", "supportive", "warning"]
EmbeddingProvider = Literal["mock", "ark", "doubao"]


class RuntimeConfig(BaseModel):
    chat_top_k: int = Field(default=5, ge=1, le=12)
    hybrid_retrieval: bool = False
    enable_rerank: bool = True
    reject_without_evidence: bool = True
    strict_citation_check: bool = True
    default_emotion: EmotionTag = "calm"
    knowledge_collection: str = Field(default="laws", min_length=1, max_length=64)
    case_collection: str = Field(default="cases", min_length=1, max_length=64)
    chat_case_top_k: int = Field(default=3, ge=0, le=12)
    embedding_provider: EmbeddingProvider = "mock"
    timeout_sec: int = Field(default=30, ge=5, le=90)
