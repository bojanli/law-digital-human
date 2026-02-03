import hashlib
import json
import time
from urllib import error, request

from app.core.config import settings

_NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))


def embed_text(text: str, provider_override: str | None = None) -> list[float]:
    provider = (provider_override or settings.embedding_provider).lower().strip()
    if provider == "mock":
        return _mock_embed(text, settings.embedding_dim)
    if provider in {"doubao", "ark"}:
        return _ark_embed(text)
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
    if not settings.ark_api_key:
        raise ValueError("ARK_API_KEY is empty")
    model = settings.ark_embedding_model or settings.ark_model
    if not model:
        raise ValueError("ARK_EMBEDDING_MODEL is empty")

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
        url = f"{settings.ark_base_url.rstrip('/')}/embeddings/multimodal"
    else:
        payload = {
            "model": model,
            "input": text,
            "encoding_format": "float",
        }
        url = f"{settings.ark_base_url.rstrip('/')}/embeddings"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.ark_api_key}",
        "Content-Type": "application/json",
    }
    last_exc = None
    body = None
    for attempt in range(3):
        req_obj = request.Request(url=url, data=data, headers=headers, method="POST")
        try:
            with _NO_PROXY_OPENER.open(req_obj, timeout=60) as resp:
                body = resp.read().decode("utf-8")
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Ark embedding HTTPError: {exc.code} {detail}") from exc
        except (error.URLError, OSError) as exc:
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
