from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="law-digital-human-backend", alias="APP_NAME")
    env: str = Field(default="dev", alias="ENV")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")
    qdrant_url: str = Field(default="http://127.0.0.1:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="laws", alias="QDRANT_COLLECTION")
    knowledge_db_path: str = Field(default="data/knowledge.db", alias="KNOWLEDGE_DB_PATH")
    embedding_provider: str = Field(default="mock", alias="EMBEDDING_PROVIDER")
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")

    def cors_origin_list(self) -> list[str]:
        # 支持用逗号分隔多个 origin
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
