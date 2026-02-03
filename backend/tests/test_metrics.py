import json
import sqlite3
import unittest
import uuid
from pathlib import Path

from app.core.config import settings
from app.services import metrics as metrics_service


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_metrics_db_path = settings.metrics_db_path
        self._db_relpath = f"backend/tests/.tmp/metrics_test_{uuid.uuid4().hex}.db"
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

    def test_record_api_call(self) -> None:
        metrics_service.record_api_call(
            endpoint="chat",
            ok=True,
            status_code=200,
            latency_ms=12.5,
            request_id="rid_1",
            meta={"k": "v"},
        )

        db_file = Path("..").resolve() / self._db_relpath
        with sqlite3.connect(db_file) as conn:
            row = conn.execute(
                "SELECT endpoint, ok, status_code, latency_ms, request_id, meta_json FROM api_metrics ORDER BY id DESC LIMIT 1"
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "chat")
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 200)
        self.assertAlmostEqual(float(row[3]), 12.5, places=3)
        self.assertEqual(row[4], "rid_1")
        self.assertEqual(json.loads(row[5]), {"k": "v"})


if __name__ == "__main__":
    unittest.main()
