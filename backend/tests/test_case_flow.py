import unittest
import uuid
from pathlib import Path

from app.core.config import settings
from app.schemas.case import CaseStartRequest, CaseStepRequest
from app.services import case as case_service
from app.services import knowledge as knowledge_service
from app.services import session_store


class CaseFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_case_db_path = settings.case_db_path
        self._db_relpath = f"backend/tests/.tmp/case_test_{uuid.uuid4().hex}.db"
        tmp_dir = Path("backend/tests/.tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        settings.case_db_path = self._db_relpath

    def tearDown(self) -> None:
        settings.case_db_path = self._old_case_db_path
        db_file = Path("..").resolve() / self._db_relpath
        if db_file.exists():
            try:
                db_file.unlink()
            except PermissionError:
                pass

    def test_full_flow_and_persistence(self) -> None:
        original_search = knowledge_service.search
        knowledge_service.search = lambda query, top_k=5: [
            {
                "chunk_id": "chunk_a",
                "law_name": "民法典",
                "article_no": "第七百一十一条",
                "section": "租赁合同",
                "source": "docs/a.md",
            }
        ]
        try:
            sid = "case_ut_001"
            start = case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid))
            self.assertEqual(start.state, "fact_confirm")

            fact = case_service.step_case(
                CaseStepRequest(
                    session_id=sid,
                    user_input="有合同，已搬走，房屋没有损坏，有聊天记录和转账记录，押金2000元",
                )
            )
            self.assertEqual(fact.state, "dispute_identify")
            self.assertGreaterEqual(len(fact.citations), 1)

            dispute = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="withhold_deposit"))
            self.assertEqual(dispute.state, "option_select")

            action = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="mediate"))
            self.assertEqual(action.state, "consequence_feedback")
            self.assertIn("action:mediate", action.path)

            saved = session_store.get_session(sid)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["state"], "consequence_feedback")
            self.assertEqual(saved["slots"]["deposit_amount"], "2000元")
        finally:
            knowledge_service.search = original_search

    def test_branch_outputs_are_different(self) -> None:
        original_search = knowledge_service.search
        knowledge_service.search = lambda query, top_k=5: [
            {"chunk_id": "chunk_branch", "law_name": "民法典", "article_no": "第七百一十条", "source": "docs/b.md"}
        ]
        try:
            base_text = "有合同，已搬走，房屋没有损坏"

            sid_a = "case_ut_002a"
            case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid_a))
            case_service.step_case(CaseStepRequest(session_id=sid_a, user_input=base_text))
            case_service.step_case(CaseStepRequest(session_id=sid_a, user_choice="withhold_deposit"))
            r_a = case_service.step_case(CaseStepRequest(session_id=sid_a, user_choice="negotiate"))

            sid_b = "case_ut_002b"
            case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid_b))
            case_service.step_case(CaseStepRequest(session_id=sid_b, user_input=base_text))
            case_service.step_case(CaseStepRequest(session_id=sid_b, user_choice="withhold_deposit"))
            r_b = case_service.step_case(CaseStepRequest(session_id=sid_b, user_choice="litigate"))

            self.assertNotEqual(r_a.text, r_b.text)
            self.assertIn("action:negotiate", r_a.path)
            self.assertIn("action:litigate", r_b.path)
        finally:
            knowledge_service.search = original_search

    def test_no_evidence_guard(self) -> None:
        original_search = knowledge_service.search
        knowledge_service.search = lambda query, top_k=5: []
        try:
            sid = "case_ut_003"
            case_service.start_case(CaseStartRequest(case_id="rent_deposit_dispute", session_id=sid))
            case_service.step_case(
                CaseStepRequest(session_id=sid, user_input="有合同，已搬走，房屋没有损坏，押金1500元")
            )
            case_service.step_case(CaseStepRequest(session_id=sid, user_choice="withhold_deposit"))
            result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="litigate"))

            self.assertEqual(result.state, "consequence_feedback")
            self.assertEqual(result.citations, [])
            self.assertIn("先不输出确定结论", result.text)
            self.assertIn("补充合同", result.next_actions)
        finally:
            knowledge_service.search = original_search

    def test_labor_template_flow(self) -> None:
        original_search = knowledge_service.search
        knowledge_service.search = lambda query, top_k=5: [
            {
                "chunk_id": "chunk_labor",
                "law_name": "劳动合同法",
                "article_no": "第三十条",
                "section": "工资支付",
                "source": "docs/labor.md",
            }
        ]
        try:
            sid = "case_ut_labor_001"
            start = case_service.start_case(CaseStartRequest(case_id="labor_wage_arrears", session_id=sid))
            self.assertEqual(start.state, "fact_confirm")
            self.assertIn("employment_exists", start.missing_slots)

            fact = case_service.step_case(
                CaseStepRequest(
                    session_id=sid,
                    user_input="有劳动合同，存在加班费争议，工资已逾期未发，有考勤和工资流水，欠薪8000元",
                )
            )
            self.assertEqual(fact.state, "dispute_identify")
            self.assertIn("arrears_wage", fact.next_actions)

            dispute = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arrears_wage"))
            self.assertEqual(dispute.state, "option_select")
            self.assertIn("arbitration", dispute.next_actions)

            action = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="arbitration"))
            self.assertEqual(action.state, "consequence_feedback")
            self.assertIn("action:arbitration", action.path)
            self.assertGreaterEqual(len(action.citations), 1)
        finally:
            knowledge_service.search = original_search

    def test_unknown_case_template(self) -> None:
        with self.assertRaises(case_service.CaseNotFoundError):
            case_service.start_case(CaseStartRequest(case_id="unknown_case_template", session_id="sid_x"))


if __name__ == "__main__":
    unittest.main()
