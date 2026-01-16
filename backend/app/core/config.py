from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="law-digital-human-backend", alias="APP_NAME")
    env: str = Field(default="dev", alias="ENV")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    def cors_origin_list(self) -> list[str]:
        # 支持用逗号分隔多个 origin
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
