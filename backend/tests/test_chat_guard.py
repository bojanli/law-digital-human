import unittest
from unittest.mock import patch

from app.schemas.runtime_config import RuntimeConfig
from app.schemas.chat import ChatRequest, AnswerJson
from app.schemas.common import Citation
from app.services import chat as chat_service
from app.services.web_search import WebSearchHit


class ChatGuardTests(unittest.TestCase):
    def test_select_answer_evidence_limits_to_three(self) -> None:
        evidence = [
            {"chunk_id": "l1", "source_type": "law", "text": "a" * 200},
            {"chunk_id": "l2", "source_type": "law", "text": "b" * 200},
            {"chunk_id": "c1", "source_type": "case", "text": "c" * 200},
            {"chunk_id": "l3", "source_type": "law", "text": "d" * 200},
        ]
        picked = chat_service.select_answer_evidence(evidence)
        self.assertEqual(len(picked), 3)
        self.assertEqual([item["chunk_id"] for item in picked], ["l1", "l2", "c1"])
        self.assertTrue(all(len(str(item["text"])) <= 120 for item in picked))

    def test_rule_rewrite_expands_follow_up_without_llm(self) -> None:
        history = [
            {"role": "user", "content": "租房押金不退怎么办"},
            {"role": "assistant", "content": "请补充是否签合同"},
        ]
        rewritten = chat_service.rewrite_query(history, "没签合同他也不退呢？")
        self.assertIn("租房押金不退怎么办", rewritten)
        self.assertIn("没签合同他也不退呢？", rewritten)

    def test_short_rent_deposit_query_is_expanded_for_search(self) -> None:
        expanded = chat_service.expand_legal_query("房东不退押金")
        self.assertIn("房东不退押金", expanded)
        self.assertIn("租赁合同", expanded)
        self.assertIn("押金返还", expanded)
        self.assertIn("出租人", expanded)
        self.assertIn("承租人", expanded)
        self.assertIn("民法典", expanded)

    def test_stream_text_can_recover_citations(self) -> None:
        answer = chat_service.build_answer_from_stream_text(
            "房东无正当理由不退押金属于违约。\n建议：保留转账和聊天记录。\n[[CITATIONS:c1,c2]]",
            [
                {"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条"},
                {"chunk_id": "c2", "law_name": "民法典", "article_no": "第二条"},
            ],
        )
        self.assertEqual(len(answer.citations), 2)
        self.assertIn("不退押金", answer.conclusion)

    def test_external_disclaimer_when_no_local_evidence(self) -> None:
        req = ChatRequest(session_id="s1", text="房东不退押金", mode="chat", case_state=None)
        with patch(
            "app.services.chat.get_runtime_config",
            return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
        ), patch(
            "app.services.chat.web_search_service.search_public_web",
            return_value=[],
        ):
            answer = chat_service.build_answer(req, evidence=[])
        self.assertEqual(answer.emotion, "supportive")
        self.assertEqual(answer.citations, [])
        self.assertIn("租赁押金纠纷", answer.conclusion)
        self.assertIn("未检索到足够可核验依据", answer.conclusion)

    def test_web_reference_answer_when_no_local_evidence(self) -> None:
        req = ChatRequest(session_id="s1_web", text="房东不退押金", mode="chat", case_state=None)
        with patch(
            "app.services.chat.get_runtime_config",
            return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=True),
        ), patch(
            "app.services.chat.web_search_service.search_public_web",
            return_value=[
                WebSearchHit(
                    title="押金纠纷处理提示",
                    snippet="可先保存合同、转账记录和交接证明，再与出租人协商或依法维权。",
                    url="https://example.test/rent",
                )
            ],
        ), patch("app.services.chat._ask_ark_with_web_results", return_value=None):
            answer = chat_service.build_answer(req, evidence=[])
        self.assertEqual(answer.emotion, "supportive")
        self.assertEqual(answer.citations, [])
        self.assertIn("公开网络信息", answer.conclusion)
        self.assertIn("不能替代正式法律意见", answer.conclusion)

    def test_short_rent_deposit_question_keeps_strong_relevant_citation(self) -> None:
        req = ChatRequest(session_id="s_rent", text="房东不退押金", mode="chat", case_state=None)
        evidence = [
            {
                "chunk_id": "rent_deposit_1",
                "law_name": "中华人民共和国民法典",
                "article_no": "房屋租赁合同",
                "section": "合同编 租赁合同",
                "source_type": "law",
                "text": "出租人与承租人发生租赁合同争议，租赁押金、保证金返还可依合同约定和履行情况处理。",
            }
        ]
        fake_answer = AnswerJson(
            conclusion="房东无正当理由扣押押金的，通常属于租赁合同履行中的押金返还争议。",
            analysis=["应结合合同约定、房屋交接情况和扣押理由判断。"],
            actions=["先固定合同、转账记录、聊天记录和交接证明。"],
            citations=[],
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

        self.assertNotIn("系统已中止直接结论输出", answer.conclusion)
        self.assertEqual([citation.chunk_id for citation in answer.citations], ["rent_deposit_1"])

    def test_rent_deposit_due_question_keeps_deposit_citation(self) -> None:
        req = ChatRequest(session_id="s_rent_due", text="租房押金到期不退怎么办", mode="chat", case_state=None)
        evidence = [
            {
                "chunk_id": "rent_due_1",
                "law_name": "中华人民共和国民法典",
                "article_no": "租赁合同",
                "section": "房屋租赁",
                "source_type": "law",
                "text": "租赁合同解除或期限届满后，出租人拒绝返还租赁押金的，承租人可依法主张返还。",
            }
        ]
        fake_answer = AnswerJson(
            conclusion="租房押金到期不退，应先核对合同约定和退租交接情况，再要求出租人说明扣押依据。",
            analysis=["押金返还争议属于租赁合同纠纷。"],
            actions=["保留合同、付款凭证和交接记录，协商不成可依法维权。"],
            citations=[],
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

        self.assertEqual(len(answer.citations), 1)
        self.assertIn("租赁", answer.citations[0].article_no or "")

    def test_legal_domain_without_citation_uses_natural_followup(self) -> None:
        req = ChatRequest(session_id="s_rent_no_cite", text="房东不退押金", mode="chat", case_state=None)
        evidence = [{"chunk_id": "labor_1", "law_name": "劳动法", "text": "劳动者工资应及时支付。"}]
        fake_answer = AnswerJson(
            conclusion="需要进一步判断。",
            analysis=[],
            actions=[],
            citations=[],
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
        self.assertNotIn("系统已中止直接结论输出", answer.conclusion)
        self.assertIn("租赁押金纠纷", answer.conclusion)
        self.assertIn("是否签订书面租赁合同？", answer.follow_up_questions)
        self.assertIn("押金金额是多少？", answer.follow_up_questions)
        self.assertIn("房东不退押金的理由是什么？", answer.follow_up_questions)
        self.assertIn("是否已经退租并完成房屋交接？", answer.follow_up_questions)

    def test_out_of_scope_investment_prediction_has_no_citations(self) -> None:
        req = ChatRequest(session_id="s_stock", text="帮我预测明天股票涨跌", mode="chat", case_state=None)
        evidence = [
            {
                "chunk_id": "finance_crime_1",
                "law_name": "中华人民共和国刑法",
                "article_no": "第一百八十条",
                "source_type": "law",
                "text": "证券、期货交易内幕信息的知情人员利用未公开信息交易的刑事责任。",
            },
            {
                "chunk_id": "finance_crime_2",
                "law_name": "中华人民共和国刑法",
                "article_no": "第一百九十二条",
                "source_type": "law",
                "text": "金融诈骗、破坏金融管理秩序相关犯罪。",
            },
        ]

        answer = chat_service.build_answer(req, evidence=evidence)

        self.assertIn("只能提供法律", answer.conclusion)
        self.assertIn("无法预测股票涨跌", answer.conclusion)
        self.assertEqual(answer.analysis, [])
        self.assertEqual(answer.actions, [])
        self.assertEqual(answer.assumptions, [])
        self.assertEqual(answer.citations, [])
        self.assertEqual(answer.emotion, "calm")

    def test_no_basis_answer_drops_citations(self) -> None:
        req = ChatRequest(session_id="s_no_basis", text="这个纠纷怎么处理", mode="chat", case_state=None)
        evidence = [{"chunk_id": "c1", "law_name": "民法典", "article_no": "第一条", "text": "民事主体合法权益受法律保护。"}]
        fake_answer = AnswerJson(
            conclusion="无法根据依据给出结论，依据中未涉及相关内容。",
            analysis=[],
            actions=[],
            citations=[Citation(chunk_id="c1", law_name="民法典", article_no="第一条")],
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
                return_value=RuntimeConfig(reject_without_evidence=True, strict_citation_check=False),
            ),
            patch("app.services.chat._ask_ark", return_value=fake_answer),
            patch("app.services.chat.web_search_service.search_public_web", return_value=[]),
        ):
            answer = chat_service.build_answer(req, evidence=evidence)

        self.assertEqual(answer.citations, [])
        self.assertNotIn("本轮已引用", answer.conclusion)

    def test_labor_question_keeps_relevant_citations(self) -> None:
        req = ChatRequest(session_id="s_labor", text="大学生兼职没有签合同，被拖欠工资怎么办？", mode="chat", case_state=None)
        evidence = [
            {
                "chunk_id": "labor_77",
                "law_name": "中华人民共和国劳动法",
                "article_no": "第七十七条",
                "source_type": "law",
                "text": "用人单位与劳动者发生劳动争议，当事人可以依法申请调解、仲裁、提起诉讼。",
            },
            {
                "chunk_id": "labor_91",
                "law_name": "中华人民共和国劳动法",
                "article_no": "第九十一条",
                "source_type": "law",
                "text": "用人单位克扣或者无故拖欠劳动者工资的，由劳动行政部门责令支付劳动者工资报酬。",
            },
        ]
        fake_answer = AnswerJson(
            conclusion="兼职被拖欠工资的，可以先固定证据，再依法申请劳动仲裁或向劳动行政部门投诉。",
            analysis=["拖欠劳动报酬属于劳动争议，未签合同不当然免除用人单位支付工资义务。"],
            actions=["保留考勤、聊天记录、工资约定和转账流水。"],
            citations=[
                Citation(chunk_id="labor_77", law_name="中华人民共和国劳动法", article_no="第七十七条"),
                Citation(chunk_id="labor_91", law_name="中华人民共和国劳动法", article_no="第九十一条"),
            ],
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

        self.assertEqual([citation.article_no for citation in answer.citations], ["第七十七条", "第九十一条"])

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
