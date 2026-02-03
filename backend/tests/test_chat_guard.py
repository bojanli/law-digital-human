import unittest
from unittest.mock import patch

from app.core.config import settings
from app.schemas.chat import ChatRequest, AnswerJson
from app.schemas.common import Citation
from app.services import chat as chat_service


class ChatGuardTests(unittest.TestCase):
    def test_reject_when_no_evidence(self) -> None:
        req = ChatRequest(session_id="s1", text="房东不退押金", mode="chat", case_state=None)
        answer = chat_service.build_answer(req, evidence=[])
        self.assertEqual(answer.emotion, "serious")
        self.assertEqual(answer.citations, [])
        self.assertIn("无法给出确定结论", answer.conclusion)

    def test_reject_when_citation_not_in_evidence(self) -> None:
        req = ChatRequest(session_id="s2", text="测试", mode="chat", case_state=None)
        evidence = [{"chunk_id": "c_ok", "law_name": "民法典"}]
        fake_answer = AnswerJson(
            conclusion="假结论",
            analysis=["x"],
            actions=["y"],
            citations=[Citation(chunk_id="c_bad", law_name="民法典")],
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
        try:
            with patch("app.services.chat._ask_ark", return_value=fake_answer):
                answer = chat_service.build_answer(req, evidence=evidence)
            self.assertEqual(answer.citations, [])
            self.assertEqual(answer.emotion, "serious")
        finally:
            settings.llm_provider = old_provider
            settings.ark_api_key = old_key
            settings.ark_model = old_model


if __name__ == "__main__":
    unittest.main()
