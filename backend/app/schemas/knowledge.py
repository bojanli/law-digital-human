from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")


class KnowledgeChunk(BaseModel):
    chunk_id: str
    text: str
    law_name: str | None = None
    article_no: str | None = None
    section: str | None = None
    tags: str | None = None
    source: str | None = None
    score: float | None = None


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeChunk]
