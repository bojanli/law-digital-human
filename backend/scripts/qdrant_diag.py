import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

ROOT = Path(__file__).resolve().parents[2]
# Ensure local backend package wins over any installed "app" package.
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402


def _print_proxy_env() -> None:
    keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ]
    print("proxy env:")
    for key in keys:
        print(f"  {key}={os.environ.get(key, '')}")


def _try_get_collections(label: str, client: QdrantClient) -> None:
    print(f"\n[{label}] get_collections()")
    try:
        res = client.get_collections()
        names = [c.name for c in res.collections]
        print(f"  ok: {names}")
    except UnexpectedResponse as exc:
        print(f"  UnexpectedResponse: {exc}")
        raw = getattr(exc, "raw_content", None)
        if raw is not None:
            print(f"  raw_content: {raw!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"  error: {type(exc).__name__}: {exc}")


def main() -> None:
    print(f"settings.qdrant_url={settings.qdrant_url}")
    _print_proxy_env()

    _try_get_collections(
        "url",
        QdrantClient(url=settings.qdrant_url, check_compatibility=False),
    )

    _try_get_collections(
        "host/port",
        QdrantClient(host="127.0.0.1", port=6333, check_compatibility=False),
    )

    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    _try_get_collections(
        "host/port + NO_PROXY",
        QdrantClient(host="127.0.0.1", port=6333, check_compatibility=False),
    )


if __name__ == "__main__":
    main()
