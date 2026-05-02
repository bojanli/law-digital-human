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
    llm_fast_model: str = Field(default="doubao-1-5-lite-32k-250115", alias="LLM_FAST_MODEL")
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
    tts_app_id: str = Field(default="", alias="TTS_APP_ID")
    tts_access_token: str = Field(default="", alias="TTS_ACCESS_TOKEN")
    tts_resource_id: str = Field(default="seed-tts-1.0", alias="TTS_RESOURCE_ID")
    tts_ws_url: str = Field(
        default="wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream",
        alias="TTS_WS_URL",
    )
    tts_http_url: str = Field(
        default="https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        alias="TTS_HTTP_URL",
    )
    tts_audio_format: str = Field(default="wav", alias="TTS_AUDIO_FORMAT")
    tts_sample_rate: int = Field(default=24000, alias="TTS_SAMPLE_RATE")
    chat_tts_soft_timeout_ms: int = Field(default=300, alias="CHAT_TTS_SOFT_TIMEOUT_MS")
    tts_audio_public_base_url: str = Field(default="http://127.0.0.1:8000", alias="TTS_AUDIO_PUBLIC_BASE_URL")
    tts_audio_store_dir: str = Field(default="data/tts_cache", alias="TTS_AUDIO_STORE_DIR")
    asr_enabled: bool = Field(default=False, alias="ASR_ENABLED")
    asr_provider: str = Field(default="mock", alias="ASR_PROVIDER")
    asr_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="ASR_BASE_URL")
    asr_api_key: str = Field(default="", alias="ASR_API_KEY")
    asr_model: str = Field(default="", alias="ASR_MODEL")
    asr_language: str = Field(default="zh-CN", alias="ASR_LANGUAGE")
    asr_app_id: str = Field(default="", alias="ASR_APP_ID")
    asr_access_token: str = Field(default="", alias="ASR_ACCESS_TOKEN")
    asr_secret_key: str = Field(default="", alias="ASR_SECRET_KEY")
    asr_cluster: str = Field(default="", alias="ASR_CLUSTER")
    asr_resource_id: str = Field(default="volc.bigasr.auc", alias="ASR_RESOURCE_ID")
    asr_submit_path: str = Field(default="/api/v3/auc/bigmodel/submit", alias="ASR_SUBMIT_PATH")
    asr_query_path: str = Field(default="/api/v3/auc/bigmodel/query", alias="ASR_QUERY_PATH")
    asr_ws_url: str = Field(default="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream", alias="ASR_WS_URL")
    asr_chunk_bytes: int = Field(default=32000, alias="ASR_CHUNK_BYTES")
    asr_audio_public_base_url: str = Field(default="", alias="ASR_AUDIO_PUBLIC_BASE_URL")
    asr_audio_store_dir: str = Field(default="data/asr_uploads", alias="ASR_AUDIO_STORE_DIR")
    asr_auc_poll_interval_ms: int = Field(default=800, alias="ASR_AUC_POLL_INTERVAL_MS")
    asr_auc_timeout_sec: int = Field(default=40, alias="ASR_AUC_TIMEOUT_SEC")

    def cors_origin_list(self) -> list[str]:
        # 支持用逗号分隔多个 origin
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    def resolved_llm_base_url(self) -> str:
        return (self.llm_base_url or self.ark_base_url).rstrip("/")

    def resolved_llm_api_key(self) -> str:
        return (self.llm_api_key or self.ark_api_key).strip()

    def resolved_llm_model(self) -> str:
        return (self.llm_model or self.ark_model).strip()

    def resolved_fast_llm_model(self) -> str:
        return (self.llm_fast_model or self.llm_model or self.ark_model).strip()

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

    def resolved_asr_base_url(self) -> str:
        return (self.asr_base_url or self.ark_base_url).rstrip("/")

    def resolved_asr_api_key(self) -> str:
        return (self.asr_api_key or self.ark_api_key).strip()

    def resolved_asr_model(self) -> str:
        return (self.asr_model or self.ark_model).strip()


settings = Settings()
