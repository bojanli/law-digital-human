from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    _env_file = Path(__file__).resolve().parents[2] / ".env"
    model_config = SettingsConfigDict(
        env_file=str(_env_file),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未声明的变量（如 NO_PROXY、no_proxy）
    )

    app_name: str = Field(default="law-digital-human-backend", alias="APP_NAME")
    env: str = Field(default="dev", alias="ENV")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")
    qdrant_url: str = Field(default="http://127.0.0.1:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="laws", alias="QDRANT_COLLECTION")
    knowledge_db_path: str = Field(default="data/knowledge.db", alias="KNOWLEDGE_DB_PATH")
    case_db_path: str = Field(default="data/case.db", alias="CASE_DB_PATH")
    metrics_db_path: str = Field(default="data/metrics.db", alias="METRICS_DB_PATH")
    embedding_provider: str = Field(default="mock", alias="EMBEDDING_PROVIDER")
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")
    chat_top_k: int = Field(default=5, alias="CHAT_TOP_K")
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    ark_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="ARK_BASE_URL")
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    ark_model: str = Field(default="", alias="ARK_MODEL")
    ark_embedding_model: str = Field(default="", alias="ARK_EMBEDDING_MODEL")

    def cors_origin_list(self) -> list[str]:
        # 支持用逗号分隔多个 origin
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
