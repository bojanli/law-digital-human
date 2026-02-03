import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import metrics as metrics_service


class ApiAdminMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self._old_metrics_db_path = settings.metrics_db_path
        self._db_relpath = f"backend/tests/.tmp/metrics_admin_{uuid.uuid4().hex}.db"
        Path("backend/tests/.tmp").mkdir(parents=True, exist_ok=True)
        settings.metrics_db_path = self._db_relpath

    def tearDown(self) -> None:
        settings.metrics_db_path = self._old_metrics_db_path
        db_file = Path("..").resolve() / self._db_relpath
        if db_file.exists():
            try:
                db_file.unlink()
            except PermissionError:
                pass

    def test_metrics_summary_all(self) -> None:
        metrics_service.record_api_call("chat", True, 200, 12.0, request_id="r1", meta={"x": 1})
        metrics_service.record_api_call("chat", False, 500, 33.0, request_id="r2", meta={"x": 2})
        metrics_service.record_api_call("case_step", True, 200, 20.0, request_id="r3", meta={})

        resp = self.client.get("/api/admin/metrics/summary")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["ok"], 2)
        self.assertEqual(payload["fail"], 1)
        self.assertGreater(payload["avg_latency_ms"], 0)
        self.assertEqual(len(payload["by_endpoint"]), 2)

    def test_metrics_summary_filter_endpoint(self) -> None:
        metrics_service.record_api_call("chat", True, 200, 10.0, request_id="r1", meta={})
        metrics_service.record_api_call("case_step", False, 500, 15.0, request_id="r2", meta={})
        resp = self.client.get("/api/admin/metrics/summary", params={"endpoint": "chat"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["by_endpoint"][0]["endpoint"], "chat")

    def test_metrics_export_csv(self) -> None:
        metrics_service.record_api_call("chat", True, 200, 10.5, request_id="r1", meta={"mode": "chat"})
        metrics_service.record_api_call("case_step", False, 500, 17.5, request_id="r2", meta={"state": "x"})
        resp = self.client.get("/api/admin/metrics/export")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers.get("content-type", ""))
        text = resp.text
        self.assertIn("endpoint", text)
        self.assertIn("chat", text)
        self.assertIn("case_step", text)

    def test_metrics_paper_kpi(self) -> None:
        metrics_service.record_api_call(
            "chat",
            True,
            200,
            10.0,
            request_id="r1",
            meta={"evidence": 2, "citations": 1, "answer_emotion": "calm", "no_evidence_reject": False},
        )
        metrics_service.record_api_call(
            "chat",
            True,
            200,
            20.0,
            request_id="r2",
            meta={"evidence": 0, "citations": 0, "answer_emotion": "serious", "no_evidence_reject": True},
        )
        metrics_service.record_api_call("case_step", True, 200, 30.0, request_id="r3", meta={"state": "option_select"})

        resp = self.client.get("/api/admin/metrics/paper-kpi")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["chat_total"], 2)
        self.assertEqual(payload["chat_with_evidence"], 1)
        self.assertEqual(payload["chat_no_evidence"], 1)
        self.assertAlmostEqual(payload["citation_hit_rate"], 1.0)
        self.assertAlmostEqual(payload["no_evidence_reject_rate"], 1.0)
        self.assertEqual(payload["chat_latency"]["sample_size"], 2)
        self.assertEqual(payload["case_step_latency"]["sample_size"], 1)


if __name__ == "__main__":
    unittest.main()
