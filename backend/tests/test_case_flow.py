import unittest
import uuid
from pathlib import Path

from app.core.config import settings
from app.schemas.case import CaseStartRequest, CaseStepRequest
from app.services import case as case_service
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
        sid = "case_ut_001"
        start = case_service.start_case(CaseStartRequest(case_id="peng_yu_case", session_id=sid))
        self.assertEqual(start.state, "opening")
        self.assertTrue(start.next_question)

        for choice in ["查看关键证据", "听取双方陈述", "继续审理"]:
            step = case_service.step_case(CaseStepRequest(session_id=sid, user_choice=choice))

        self.assertIn(step.state, {"opening", "trial", "verdict"})
        self.assertGreaterEqual(len(step.path), 3)

        saved = session_store.get_session(sid)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["turn"], 3)
        self.assertEqual(len(saved["user_choices"]), 3)

    def test_real_verdict_branch_outputs_reference_text(self) -> None:
        sid = "case_ut_002"
        case_service.start_case(CaseStartRequest(case_id="xu_ting_case", session_id=sid))
        result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice="查看真实判决结果"))
        self.assertIn("真实判决结果", result.text)
        self.assertIn("继续", result.next_question)

    def test_verdict_stage_reached_after_enough_turns(self) -> None:
        sid = "case_ut_003"
        case_service.start_case(CaseStartRequest(case_id="kunshan_defense_case", session_id=sid))
        result = None
        for choice in ["查看关键证据", "听取双方陈述", "继续审理", "进入最终陈述", "继续审理", "部分责任"]:
            result = case_service.step_case(CaseStepRequest(session_id=sid, user_choice=choice))
        self.assertIsNotNone(result)
        self.assertEqual(result.state, "verdict")
        self.assertGreaterEqual(len(result.path), 6)

    def test_unknown_case_template(self) -> None:
        with self.assertRaises(case_service.CaseNotFoundError):
            case_service.start_case(CaseStartRequest(case_id="unknown_case_template", session_id="sid_x"))


if __name__ == "__main__":
    unittest.main()
