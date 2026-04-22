from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import runtime_config as runtime_config_service


class ApiRuntimeConfigTests:
    client = TestClient(app)

    def setup_method(self) -> None:
        self.path = Path(__file__).resolve().parents[2] / "data" / "runtime_config.json"
        self.original = self.path.read_text(encoding="utf-8") if self.path.exists() else None
        runtime_config_service._CACHE = None

    def teardown_method(self) -> None:
        if self.original is None:
            if self.path.exists():
                self.path.unlink()
        else:
            self.path.write_text(self.original, encoding="utf-8")
        runtime_config_service._CACHE = None

    def test_round_trip(self) -> None:
        payload = {
            "chat_top_k": 6,
            "hybrid_retrieval": True,
            "enable_rerank": False,
            "reject_without_evidence": True,
            "strict_citation_check": True,
            "default_emotion": "warning",
            "knowledge_collection": "laws",
            "embedding_provider": "mock",
            "timeout_sec": 35,
        }
        put_resp = self.client.put("/api/admin/runtime-config", json=payload)
        assert put_resp.status_code == 200
        get_resp = self.client.get("/api/admin/runtime-config")
        assert get_resp.status_code == 200
        assert get_resp.json()["default_emotion"] == "warning"
        assert get_resp.json()["chat_top_k"] == 6

    def test_invalid_payload(self) -> None:
        resp = self.client.put(
            "/api/admin/runtime-config",
            json={
                "chat_top_k": 99,
                "hybrid_retrieval": True,
                "enable_rerank": True,
                "reject_without_evidence": True,
                "strict_citation_check": True,
                "default_emotion": "calm",
                "knowledge_collection": "laws",
                "embedding_provider": "mock",
                "timeout_sec": 30,
            },
        )
        assert resp.status_code == 422
