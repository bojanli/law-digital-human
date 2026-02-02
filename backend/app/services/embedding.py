import hashlib
from app.core.config import settings


def embed_text(text: str) -> list[float]:
    provider = settings.embedding_provider.lower().strip()
    if provider == "mock":
        return _mock_embed(text, settings.embedding_dim)
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _mock_embed(text: str, dim: int) -> list[float]:
    if dim <= 0:
        raise ValueError("embedding_dim must be positive")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec: list[float] = []
    for i in range(dim):
        b = digest[i % len(digest)]
        vec.append((b / 255.0) * 2.0 - 1.0)
    return vec
