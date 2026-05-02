import unittest
import base64
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
            json={"session_id": "s1", "text": "房东不退押金", "mode": "chat", "case_state": None, "top_k": 1},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["answer_json"]["conclusion"], "测试结论")
        self.assertEqual(payload["answer_json"]["citations"][0]["chunk_id"], "c1")
        search_query = mock_search.call_args.args[0]
        self.assertIn("房东不退押金", search_query)
        self.assertIn("租赁合同", search_query)
        self.assertIn("押金返还", search_query)
        self.assertEqual(mock_search.call_args.args[1], 1)

    @patch("app.api.v1.chat.tts_service.synthesize")
    @patch("app.api.v1.chat.chat_service.build_answer")
    @patch("app.api.v1.chat.knowledge_service.search")
    def test_chat_enable_tts_false_skips_tts(self, mock_search, mock_build_answer, mock_tts) -> None:
        mock_search.return_value = [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"}]
        mock_build_answer.return_value = AnswerJson(
            conclusion="测试结论",
            analysis=[],
            actions=[],
            citations=[],
            assumptions=[],
            follow_up_questions=[],
            emotion="calm",
        )

        resp = self.client.post(
            "/api/chat",
            json={"session_id": "s_tts_off", "text": "房东不退押金", "mode": "chat", "case_state": None, "enable_tts": False},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["audio_url"])
        mock_tts.assert_not_called()

    @patch("app.api.v1.chat.chat_service.build_answer_from_stream_text")
    @patch("app.api.v1.chat.chat_service.stream_answer_text")
    @patch("app.api.v1.chat.knowledge_service.search")
    def test_chat_stream_success(self, mock_search, mock_stream_answer, mock_build_stream_answer) -> None:
        mock_search.return_value = [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"}]
        mock_stream_answer.return_value = iter(["测试", "结论"])
        mock_build_stream_answer.return_value = AnswerJson(
            conclusion="测试结论",
            analysis=["分析1"],
            actions=["建议1"],
            citations=[Citation(chunk_id="c1", law_name="民法典", article_no="第一条")],
            assumptions=[],
            follow_up_questions=[],
            emotion="calm",
        )

        resp = self.client.post(
            "/api/chat/stream",
            json={"session_id": "s_stream", "text": "房东不退押金", "mode": "chat", "case_state": None},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        self.assertIn('"type": "delta"', body)
        self.assertIn('"type": "final"', body)

    @patch("app.api.v1.chat.tts_service.synthesize")
    @patch("app.api.v1.chat.chat_service.build_answer")
    @patch("app.api.v1.chat.knowledge_service.search")
    def test_chat_tts_failure_does_not_break_response(self, mock_search, mock_build_answer, mock_tts) -> None:
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
        mock_tts.side_effect = RuntimeError("tts boom")

        resp = self.client.post(
            "/api/chat",
            json={"session_id": "s1", "text": "房东不退押金", "mode": "chat", "case_state": None},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["audio_url"])

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
        self.assertIn("未找到 chunk_id=not_exist", resp.json()["detail"])

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

    @patch("app.api.v1.case.tts_service.synthesize")
    @patch("app.api.v1.case.case_service.start_case")
    def test_case_start_tts_failure_does_not_break_response(self, mock_start, mock_tts) -> None:
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
        mock_tts.side_effect = RuntimeError("tts boom")
        resp = self.client.post("/api/case/start", json={"case_id": "rent_deposit_dispute"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["audio_url"])

    @patch("app.api.v1.case.tts_service.synthesize")
    @patch("app.api.v1.case.case_service.start_case")
    def test_case_start_enable_tts_false_skips_tts(self, mock_start, mock_tts) -> None:
        mock_start.return_value = CaseResponse(
            session_id="case_1",
            case_id="rent_deposit_dispute",
            text="已进入案件模拟",
            next_question="请补充事实",
            state="fact_confirm",
            slots={},
            path=[],
            missing_slots=[],
            next_actions=[],
            citations=[],
            emotion="serious",
            audio_url=None,
        )
        resp = self.client.post("/api/case/start", json={"case_id": "rent_deposit_dispute", "enable_tts": False})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["audio_url"])
        mock_tts.assert_not_called()

    def test_settings_effective_endpoint(self) -> None:
        resp = self.client.get("/api/settings/effective")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("chat_top_k", payload)
        self.assertIn("enable_tts", payload)
        self.assertIn("strict_citation_check", payload)
        self.assertIn("temperature", payload)
        self.assertIn("max_tokens", payload)

    @patch("app.api.v1.asr.asr_service.transcribe")
    def test_asr_transcribe_success(self, mock_transcribe) -> None:
        mock_transcribe.return_value = "房东不退押金怎么办"
        resp = self.client.post(
            "/api/asr/transcribe",
            json={
                "audio_base64": base64.b64encode(b"fake-bytes").decode("ascii"),
                "mime_type": "audio/webm",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["text"], "房东不退押金怎么办")

    def test_asr_transcribe_empty_audio(self) -> None:
        resp = self.client.post(
            "/api/asr/transcribe",
            json={"audio_base64": "", "mime_type": "audio/webm"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
