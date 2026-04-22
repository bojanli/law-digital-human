import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.chat import AnswerJson
from app.schemas.common import Citation
from app.schemas.runtime_config import RuntimeConfig
from app.services import runtime_config as runtime_config_service
from app.services import session_store


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def isolated_case_db():
    old = settings.case_db_path
    rel = f"backend/tests/.tmp/accept_case_{uuid.uuid4().hex}.db"
    Path("backend/tests/.tmp").mkdir(parents=True, exist_ok=True)
    settings.case_db_path = rel
    try:
        yield rel
    finally:
        settings.case_db_path = old
        db_file = Path("..").resolve() / rel
        if db_file.exists():
            try:
                db_file.unlink()
            except PermissionError:
                pass


@pytest.fixture(autouse=True)
def isolated_runtime_config():
    path = Path(__file__).resolve().parents[2] / "data" / "runtime_config.json"
    original = path.read_text(encoding="utf-8") if path.exists() else None
    runtime_config_service._CACHE = None
    try:
        yield
    finally:
        if original is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(original, encoding="utf-8")
        runtime_config_service._CACHE = None


@pytest.mark.sprint1
def test_s1_search_api_returns_ranked_chunks(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.knowledge.knowledge_service.search",
        lambda query, top_k=5: [
            {
                "chunk_id": "k1",
                "text": "承租人应当按照约定支付租金。",
                "law_name": "民法典",
                "article_no": "第七百二十一条",
                "source": "docs/civil.md",
                "score": 0.92,
            }
        ],
    )
    resp = client.post("/api/knowledge/search", json={"query": "租房合同纠纷", "top_k": 5})
    assert resp.status_code == 200
    payload = resp.json()["results"]
    assert len(payload) == 1
    assert payload[0]["chunk_id"] == "k1"
    assert payload[0]["law_name"] == "民法典"


@pytest.mark.sprint1
def test_s1_chunk_lookup_returns_text(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.knowledge.knowledge_service.get_chunk",
        lambda chunk_id: {
            "chunk_id": chunk_id,
            "text": "劳动者依法享有取得劳动报酬的权利。",
            "law_name": "劳动法",
            "article_no": "第五十条",
            "source": "docs/labor.md",
        },
    )
    resp = client.get("/api/knowledge/chunk/chunk_x")
    assert resp.status_code == 200
    assert "劳动报酬" in resp.json()["text"]


@pytest.mark.sprint1
def test_s1_runtime_config_can_round_trip(client):
    payload = {
        "chat_top_k": 7,
        "hybrid_retrieval": True,
        "enable_rerank": False,
        "reject_without_evidence": True,
        "strict_citation_check": True,
        "default_emotion": "supportive",
        "knowledge_collection": "laws",
        "embedding_provider": "mock",
        "timeout_sec": 25,
    }
    put_resp = client.put("/api/admin/runtime-config", json=payload)
    assert put_resp.status_code == 200
    get_resp = client.get("/api/admin/runtime-config")
    assert get_resp.status_code == 200
    assert get_resp.json()["chat_top_k"] == 7
    assert get_resp.json()["default_emotion"] == "supportive"


@pytest.mark.sprint2
def test_s2_chat_returns_structured_payload(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.chat.knowledge_service.search",
        lambda query, top_k=5: [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"}],
    )
    monkeypatch.setattr(
        "app.api.v1.chat.runtime_config_service.get_runtime_config",
        lambda: RuntimeConfig(reject_without_evidence=True, strict_citation_check=False, chat_top_k=5),
    )
    monkeypatch.setattr(
        "app.api.v1.chat.chat_service.build_answer",
        lambda req, evidence, history=None: AnswerJson(
            conclusion="测试结论",
            analysis=["分析A"],
            actions=["建议A"],
            citations=[Citation(chunk_id="c1", law_name="民法典", article_no="第一条")],
            assumptions=["假设A"],
            follow_up_questions=["追问A"],
            emotion="calm",
        ),
    )
    resp = client.post("/api/chat", json={"session_id": "s2_1", "text": "租房纠纷", "mode": "chat", "case_state": None})
    assert resp.status_code == 200
    answer = resp.json()["answer_json"]
    assert "conclusion" in answer
    assert isinstance(answer["analysis"], list)
    assert answer["citations"][0]["chunk_id"] == "c1"


@pytest.mark.sprint2
def test_s2_guard_rejects_when_no_evidence():
    from app.services import chat as chat_service

    req = {"session_id": "s2_2", "text": "随机问题", "mode": "chat", "case_state": None}
    with patch(
        "app.services.chat.get_runtime_config",
        return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
    ):
        result = chat_service.build_answer(chat_service.ChatRequest(**req), evidence=[])
    assert result.emotion == "serious"
    assert result.citations == []
    assert "无法给出确定结论" in result.conclusion


@pytest.mark.sprint2
def test_s2_guard_filters_invalid_citations(monkeypatch):
    from app.services import chat as chat_service

    req = chat_service.ChatRequest(session_id="s2_3", text="测试", mode="chat", case_state=None)
    evidence = [{"chunk_id": "ok_1", "law_name": "民法典"}]
    fake_answer = AnswerJson(
        conclusion="结论",
        analysis=["a"],
        actions=["b"],
        citations=[Citation(chunk_id="bad_1", law_name="民法典")],
        assumptions=[],
        follow_up_questions=[],
        emotion="calm",
    )

    monkeypatch.setattr("app.services.chat.settings.llm_provider", "ark")
    monkeypatch.setattr("app.services.chat.settings.ark_api_key", "k")
    monkeypatch.setattr("app.services.chat.settings.ark_model", "m")
    monkeypatch.setattr(
        "app.services.chat.get_runtime_config",
        lambda: RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
    )
    monkeypatch.setattr("app.services.chat._ask_ark", lambda *_: fake_answer)
    result = chat_service.build_answer(req, evidence=evidence)
    assert result.citations == []
    assert result.emotion == "serious"


@pytest.mark.sprint3
def test_s3_case_catalog_and_session_persistence(client, isolated_case_db):
    catalog_resp = client.get("/api/case/catalog")
    assert catalog_resp.status_code == 200
    catalog = catalog_resp.json()
    assert len(catalog) >= 3

    start_resp = client.post("/api/case/start", json={"case_id": "peng_yu_case", "session_id": "court_s3"})
    assert start_resp.status_code == 200
    start_payload = start_resp.json()
    assert start_payload["state"] == "opening"
    assert isinstance(start_payload["next_actions"], list)

    step_resp = client.post("/api/case/step", json={"session_id": "court_s3", "user_choice": "查看关键证据"})
    assert step_resp.status_code == 200
    step_payload = step_resp.json()
    assert step_payload["state"] in {"opening", "trial", "verdict"}
    saved = session_store.get_session("court_s3")
    assert saved is not None
    assert saved["turn"] >= 1
    assert saved["phase"] in {"opening", "trial", "verdict"}


@pytest.mark.sprint3
def test_s3_case_can_progress_to_verdict(client, isolated_case_db):
    start_resp = client.post("/api/case/start", json={"case_id": "xu_ting_case", "session_id": "court_verdict"})
    assert start_resp.status_code == 200

    final_payload = start_resp.json()
    for choice in ["查看关键证据", "听取双方陈述", "直接进入辩论阶段", "继续审理", "进入最终陈述", "部分责任"]:
        resp = client.post("/api/case/step", json={"session_id": "court_verdict", "user_choice": choice})
        assert resp.status_code == 200
        final_payload = resp.json()

    assert final_payload["state"] == "verdict"
    assert len(final_payload["path"]) >= 6


@pytest.mark.sprint3
def test_s3_case_real_verdict_branch(client, isolated_case_db):
    client.post("/api/case/start", json={"case_id": "kunshan_defense_case", "session_id": "court_real"})
    resp = client.post("/api/case/step", json={"session_id": "court_real", "user_choice": "查看真实判决结果"})
    assert resp.status_code == 200
    assert "真实判决结果" in resp.json()["text"]
