import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.case import CaseStartRequest, CaseStepRequest
from app.schemas.chat import AnswerJson, ChatRequest
from app.schemas.common import Citation
from app.services import case as case_service
from app.services import knowledge as knowledge_service
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
def test_s1_chunk_not_found_returns_404(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.knowledge.knowledge_service.get_chunk", lambda _: None)
    resp = client.get("/api/knowledge/chunk/not_found")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "chunk not found"


@pytest.mark.sprint1
def test_s1_search_validation_for_topk(client):
    resp = client.post("/api/knowledge/search", json={"query": "测试", "top_k": 30})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "请求参数不合法"


@pytest.mark.sprint2
def test_s2_chat_returns_structured_payload(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.chat.knowledge_service.search",
        lambda query, top_k=5: [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"}],
    )
    monkeypatch.setattr(
        "app.api.v1.chat.chat_service.build_answer",
        lambda req, evidence: AnswerJson(
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
    req = ChatRequest(session_id="s2_2", text="随机问题", mode="chat", case_state=None)
    from app.services import chat as chat_service

    result = chat_service.build_answer(req, evidence=[])
    assert result.emotion == "serious"
    assert result.citations == []
    assert "无法给出确定结论" in result.conclusion


@pytest.mark.sprint2
def test_s2_guard_filters_invalid_citations(monkeypatch):
    from app.services import chat as chat_service

    req = ChatRequest(session_id="s2_3", text="测试", mode="chat", case_state=None)
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

    old_provider = settings.llm_provider
    old_key = settings.ark_api_key
    old_model = settings.ark_model
    settings.llm_provider = "ark"
    settings.ark_api_key = "k"
    settings.ark_model = "m"
    monkeypatch.setattr("app.services.chat._ask_ark", lambda *_: fake_answer)
    try:
        result = chat_service.build_answer(req, evidence=evidence)
        assert result.citations == []
        assert result.emotion == "serious"
    finally:
        settings.llm_provider = old_provider
        settings.ark_api_key = old_key
        settings.ark_model = old_model


@pytest.mark.sprint2
def test_s2_chat_endpoint_handles_service_failure(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.chat.knowledge_service.search", lambda *_: [])
    monkeypatch.setattr(
        "app.api.v1.chat.chat_service.build_answer",
        lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    resp = client.post("/api/chat", json={"session_id": "s2_4", "text": "测试", "mode": "chat", "case_state": None})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "聊天服务暂时不可用，请稍后重试"


@pytest.mark.sprint3
def test_s3_rent_case_end_to_end(isolated_case_db, monkeypatch):
    monkeypatch.setattr(
        knowledge_service,
        "search",
        lambda query, top_k=5: [{"chunk_id": "rent_1", "law_name": "民法典", "article_no": "第七百一十条"}],
    )
    sid = "s3_rent"
    case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid))
    fact = case_service.step_case(CaseStepRequest(session_id=sid, user_input="有合同，已搬走，房屋无损坏，押金2000元"))
    assert fact.state == "dispute_identify"
    dispute = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="withhold_deposit"))
    assert dispute.state == "option_select"
    result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="mediate"))
    assert result.state == "consequence_feedback"
    assert len(result.citations) >= 1


@pytest.mark.sprint3
def test_s3_labor_case_template_end_to_end(isolated_case_db, monkeypatch):
    monkeypatch.setattr(
        knowledge_service,
        "search",
        lambda query, top_k=5: [{"chunk_id": "labor_1", "law_name": "劳动合同法", "article_no": "第三十条"}],
    )
    sid = "s3_labor"
    case_service.start_case(CaseStartRequest(case_id="labor_wage_arrears", session_id=sid))
    fact = case_service.step_case(
        CaseStepRequest(
            session_id=sid,
            user_input="有劳动合同，工资已逾期未发，有加班费争议，附工资流水和考勤",
        )
    )
    assert fact.state == "dispute_identify"
    dispute = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arrears_wage"))
    assert dispute.state == "option_select"
    result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arbitration"))
    assert result.state == "consequence_feedback"
    assert "action:arbitration" in result.path


@pytest.mark.sprint3
def test_s3_case_state_persistence(isolated_case_db, monkeypatch):
    monkeypatch.setattr(knowledge_service, "search", lambda *args, **kwargs: [])
    sid = "s3_persist"
    case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid))
    case_service.step_case(CaseStepRequest(session_id=sid, user_input="有合同，已搬走，房屋无损坏"))
    case_service.step_case(CaseStepRequest(session_id=sid, user_choice="withhold_deposit"))
    saved = session_store.get_session(sid)
    assert saved is not None
    assert saved["state"] == "option_select"
    assert "dispute:withhold_deposit" in saved["path"]


@pytest.mark.sprint3
def test_s3_no_evidence_guard_actions(isolated_case_db, monkeypatch):
    monkeypatch.setattr(knowledge_service, "search", lambda *args, **kwargs: [])
    sid = "s3_no_evidence"
    case_service.start_case(CaseStartRequest(case_id="labor_wage_arrears", session_id=sid))
    case_service.step_case(
        CaseStepRequest(session_id=sid, user_input="有劳动合同，工资逾期未发，存在加班费争议")
    )
    case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arrears_wage"))
    result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arbitration"))
    assert result.citations == []
    assert "补充劳动合同" in result.next_actions
