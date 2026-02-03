import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.case import CaseResponse
from app.schemas.chat import AnswerJson
from app.schemas.common import Citation


class ApiRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @patch("app.api.v1.chat.chat_service.build_answer")
    @patch("app.api.v1.chat.knowledge_service.search")
    def test_chat_success(self, mock_search, mock_build_answer) -> None:
        mock_search.return_value = [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"}]
        mock_build_answer.return_value = AnswerJson(
            conclusion="测试结论",
            analysis=["分析1"],
            actions=["建议1"],
            citations=[Citation(chunk_id="c1", law_name="民法典", article_no="第一条")],
            assumptions=[],
            follow_up_questions=[],
            emotion="calm",
        )

        resp = self.client.post(
            "/api/chat",
            json={"session_id": "s1", "text": "房东不退押金", "mode": "chat", "case_state": None},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["answer_json"]["conclusion"], "测试结论")
        self.assertEqual(payload["answer_json"]["citations"][0]["chunk_id"], "c1")

    @patch("app.api.v1.chat.chat_service.build_answer")
    @patch("app.api.v1.chat.knowledge_service.search")
    def test_chat_failure(self, mock_search, mock_build_answer) -> None:
        mock_search.return_value = []
        mock_build_answer.side_effect = RuntimeError("boom")
        resp = self.client.post(
            "/api/chat",
            json={"session_id": "s1", "text": "测试", "mode": "chat", "case_state": None},
        )
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["detail"], "聊天服务暂时不可用，请稍后重试")

    @patch("app.api.v1.knowledge.knowledge_service.search")
    def test_knowledge_search_failure(self, mock_search) -> None:
        mock_search.side_effect = RuntimeError("search err")
        resp = self.client.post("/api/knowledge/search", json={"query": "押金", "top_k": 5})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["detail"], "知识检索暂时不可用，请稍后重试")

    @patch("app.api.v1.knowledge.knowledge_service.get_chunk")
    def test_knowledge_chunk_hit(self, mock_get_chunk) -> None:
        mock_get_chunk.return_value = {
            "chunk_id": "c100",
            "text": "条文内容",
            "law_name": "民法典",
            "article_no": "第一条",
            "source": "docs/x.md",
        }
        resp = self.client.get("/api/knowledge/chunk/c100")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["chunk_id"], "c100")

    @patch("app.api.v1.knowledge.knowledge_service.get_chunk")
    def test_knowledge_chunk_miss(self, mock_get_chunk) -> None:
        mock_get_chunk.return_value = None
        resp = self.client.get("/api/knowledge/chunk/not_exist")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "chunk not found")

    @patch("app.api.v1.case.case_service.step_case")
    def test_case_step_not_found(self, mock_step) -> None:
        from app.services.case import CaseSessionNotFoundError

        mock_step.side_effect = CaseSessionNotFoundError("会话不存在: test")
        resp = self.client.post("/api/case/step", json={"session_id": "test", "user_choice": "negotiate"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("会话不存在", resp.json()["detail"])

    @patch("app.api.v1.case.case_service.start_case")
    def test_case_start_success(self, mock_start) -> None:
        mock_start.return_value = CaseResponse(
            session_id="case_1",
            case_id="rent_deposit_dispute",
            text="已进入案件模拟",
            next_question="请补充事实",
            state="fact_confirm",
            slots={"lease_exists": None},
            path=[],
            missing_slots=["lease_exists"],
            next_actions=[],
            citations=[],
            emotion="serious",
            audio_url=None,
        )
        resp = self.client.post("/api/case/start", json={"case_id": "rent_deposit_dispute"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["state"], "fact_confirm")


if __name__ == "__main__":
    unittest.main()
