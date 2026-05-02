from pydantic import BaseModel, Field


class AsrTranscribeRequest(BaseModel):
    audio_base64: str = Field(default="", description="base64 编码音频")
    mime_type: str = Field(default="audio/webm", description="音频 mime type")


class AsrTranscribeResponse(BaseModel):
    text: str = Field(default="", description="识别结果文本")
    provider: str = Field(default="mock", description="ASR 提供方")
    detail: str | None = Field(default=None, description="调试信息或失败原因")
    log_id: str | None = Field(default=None, description="服务端日志ID")
