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
    embedding_base_url: str = Field(default="", alias="EMBEDDING_BASE_URL")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_model: str = Field(default="", alias="EMBEDDING_MODEL")
    chat_top_k: int = Field(default=5, alias="CHAT_TOP_K")
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    ark_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="ARK_BASE_URL")
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    ark_model: str = Field(default="", alias="ARK_MODEL")
    ark_embedding_model: str = Field(default="", alias="ARK_EMBEDDING_MODEL")
    tts_enabled: bool = Field(default=False, alias="TTS_ENABLED")
    tts_provider: str = Field(default="mock", alias="TTS_PROVIDER")
    tts_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="TTS_BASE_URL")
    tts_api_key: str = Field(default="", alias="TTS_API_KEY")
    tts_model: str = Field(default="", alias="TTS_MODEL")
    tts_voice: str = Field(default="female-tianmei", alias="TTS_VOICE")

    def cors_origin_list(self) -> list[str]:
        # 支持用逗号分隔多个 origin
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    def resolved_llm_base_url(self) -> str:
        return (self.llm_base_url or self.ark_base_url).rstrip("/")

    def resolved_llm_api_key(self) -> str:
        return (self.llm_api_key or self.ark_api_key).strip()

    def resolved_llm_model(self) -> str:
        return (self.llm_model or self.ark_model).strip()

    def resolved_embedding_base_url(self) -> str:
        return (self.embedding_base_url or self.ark_base_url).rstrip("/")

    def resolved_embedding_api_key(self) -> str:
        return (self.embedding_api_key or self.ark_api_key).strip()

    def resolved_embedding_model(self) -> str:
        return (self.embedding_model or self.ark_embedding_model or self.ark_model).strip()

    def resolved_tts_base_url(self) -> str:
        return (self.tts_base_url or self.ark_base_url).rstrip("/")

    def resolved_tts_api_key(self) -> str:
        return (self.tts_api_key or self.ark_api_key).strip()

    def resolved_tts_model(self) -> str:
        return (self.tts_model or self.ark_model).strip()


settings = Settings()
