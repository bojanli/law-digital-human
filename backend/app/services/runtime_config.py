import json
from pathlib import Path

from app.core.config import settings
from app.schemas.runtime_config import RuntimeConfig


_CACHE: RuntimeConfig | None = None


def _config_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    path = root / "data" / "runtime_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_config() -> RuntimeConfig:
    return RuntimeConfig(
        chat_top_k=settings.chat_top_k,
        hybrid_retrieval=False,
        enable_rerank=True,
        reject_without_evidence=False,
        strict_citation_check=True,
        enable_tts=settings.tts_enabled,
        enable_unity_avatar=True,
        default_emotion="calm",
        knowledge_collection=settings.qdrant_collection,
        case_collection="cases",
        chat_case_top_k=3,
        embedding_provider=settings.embedding_provider if settings.embedding_provider in {"mock", "ark", "doubao"} else "mock",
        timeout_sec=30,
        llm_provider=settings.llm_provider,
        model_name=settings.resolved_llm_model(),
        temperature=0.2,
        max_tokens=260,
    )


def get_runtime_config() -> RuntimeConfig:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    path = _config_path()
    if not path.exists():
        _CACHE = _default_config()
        path.write_text(_CACHE.model_dump_json(indent=2), encoding="utf-8")
        return _CACHE

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _CACHE = RuntimeConfig(**raw)
    except (json.JSONDecodeError, OSError, ValueError):
        _CACHE = _default_config()
    return _CACHE


def update_runtime_config(payload: RuntimeConfig) -> RuntimeConfig:
    global _CACHE
    _CACHE = payload
    _config_path().write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return _CACHE
