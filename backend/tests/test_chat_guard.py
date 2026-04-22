import unittest
from unittest.mock import patch

from app.schemas.runtime_config import RuntimeConfig
from app.schemas.chat import ChatRequest, AnswerJson
from app.schemas.common import Citation
from app.services import chat as chat_service


class ChatGuardTests(unittest.TestCase):
    def test_reject_when_no_evidence(self) -> None:
        req = ChatRequest(session_id="s1", text="房东不退押金", mode="chat", case_state=None)
        with patch(
            "app.services.chat.get_runtime_config",
            return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
        ):
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
        with (
            patch("app.services.chat.settings.llm_provider", "ark"),
            patch("app.services.chat.settings.ark_api_key", "k"),
            patch("app.services.chat.settings.ark_model", "m"),
            patch(
                "app.services.chat.get_runtime_config",
                return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
            ),
            patch("app.services.chat._ask_ark", return_value=fake_answer),
        ):
            answer = chat_service.build_answer(req, evidence=evidence)
            self.assertEqual(answer.citations, [])
            self.assertEqual(answer.emotion, "serious")
            self.assertIn("未能生成可核验引用", answer.conclusion)

    def test_non_json_response_is_still_structured(self) -> None:
        req = ChatRequest(session_id="s3", text="兼职被拖欠工资怎么办", mode="chat", case_state=None)
        evidence = [{"chunk_id": "c_ok", "law_name": "劳动法", "article_no": "第五十条"}]

        with (
            patch("app.services.chat.settings.llm_provider", "ark"),
            patch("app.services.chat.settings.ark_api_key", "k"),
            patch("app.services.chat.settings.ark_model", "m"),
            patch(
                "app.services.chat.get_runtime_config",
                return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=False),
            ),
            patch(
                "app.services.chat._ask_ark",
                return_value=AnswerJson(
                    conclusion="用人单位应当及时足额支付劳动报酬。",
                    analysis=["拖欠工资属于常见劳动争议。"],
                    actions=["先保留劳动合同和考勤记录。"],
                    citations=[],
                    assumptions=[],
                    follow_up_questions=["你是否有工资流水？"],
                    emotion="calm",
                ),
            ),
        ):
            answer = chat_service.build_answer(req, evidence=evidence)
        self.assertEqual(answer.emotion, "calm")
        self.assertGreaterEqual(len(answer.citations), 1)
        self.assertTrue(isinstance(answer.analysis, list))


if __name__ == "__main__":
    unittest.main()
