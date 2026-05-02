import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock
from urllib import error, request
from http.client import IncompleteRead

from app.core.config import settings
from app.services.runtime_config import get_runtime_config

_NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))
_EMBED_CACHE_MAX = 512
_EMBED_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()
_EMBED_CACHE_LOCK = Lock()


def embed_text(text: str, provider_override: str | None = None) -> list[float]:
    runtime = get_runtime_config()
    provider = (provider_override or runtime.embedding_provider or settings.embedding_provider).lower().strip()
    cache_key = _cache_key(provider, text)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    if provider == "mock":
        vector = _mock_embed(text, settings.embedding_dim)
        _cache_set(cache_key, vector)
        return vector
    if provider in {"doubao", "ark"}:
        vector = _ark_embed(text)
        _cache_set(cache_key, vector)
        return vector
    raise ValueError(f"Unsupported embedding provider: {provider}")


def _mock_embed(text: str, dim: int) -> list[float]:
    if dim <= 0:
        raise ValueError("embedding_dim must be positive")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec: list[float] = []
    for i in range(dim):
        b = digest[i % len(digest)]
        vec.append((b / 255.0) * 2.0 - 1.0)
    return vec


def _ark_embed(text: str) -> list[float]:
    api_key = settings.resolved_embedding_api_key()
    if not api_key:
        raise ValueError("EMBEDDING_API_KEY/ARK_API_KEY is empty")
    model = settings.resolved_embedding_model()
    if not model:
        raise ValueError("EMBEDDING_MODEL/ARK_EMBEDDING_MODEL is empty")

    use_multimodal = "vision" in model.lower()
    if use_multimodal:
        payload = {
            "model": model,
            "input": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "encoding_format": "float",
        }
        url = f"{settings.resolved_embedding_base_url()}/embeddings/multimodal"
    else:
        payload = {
            "model": model,
            "input": text,
            "encoding_format": "float",
        }
        url = f"{settings.resolved_embedding_base_url()}/embeddings"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_exc = None
    body = None
    for attempt in range(3):
        req_obj = request.Request(url=url, data=data, headers=headers, method="POST")
        try:
            with _NO_PROXY_OPENER.open(req_obj, timeout=get_runtime_config().timeout_sec) as resp:
                body = resp.read().decode("utf-8")
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Ark embedding HTTPError: {exc.code} {detail}") from exc
        except (error.URLError, OSError, IncompleteRead) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise ValueError(f"Ark embedding URLError (after retries): {exc}") from exc
        except TimeoutError as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise ValueError("Ark embedding timeout") from exc
    if body is None and last_exc:
        raise ValueError(f"Ark embedding failed: {last_exc}") from last_exc

    try:
        parsed = json.loads(body)
        data = parsed.get("data")
        if isinstance(data, list):
            vector = data[0]["embedding"]
        elif isinstance(data, dict):
            vector = data["embedding"]
        else:
            raise KeyError("data")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Ark embedding response: {body[:300]}") from exc

    if not isinstance(vector, list) or not vector:
        raise ValueError("Ark embedding is empty")
    if settings.embedding_dim > 0 and len(vector) != settings.embedding_dim:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vector)}, expected {settings.embedding_dim}. "
            "Please update EMBEDDING_DIM or switch embedding model."
        )
    return [float(x) for x in vector]


def _cache_key(provider: str, text: str) -> str:
    model = settings.resolved_embedding_model() if provider in {"doubao", "ark"} else "mock"
    return f"{provider}|{model}|{text.strip()}"


def _cache_get(key: str) -> list[float] | None:
    with _EMBED_CACHE_LOCK:
        cached = _EMBED_CACHE.get(key)
        if cached is None:
            return None
        _EMBED_CACHE.move_to_end(key)
        return list(cached)


def _cache_set(key: str, vector: list[float]) -> None:
    with _EMBED_CACHE_LOCK:
        _EMBED_CACHE[key] = list(vector)
        _EMBED_CACHE.move_to_end(key)
        while len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
            _EMBED_CACHE.popitem(last=False)
