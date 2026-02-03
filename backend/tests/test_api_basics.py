import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiBasicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_has_request_id_header(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers.get("X-Request-ID"))

    def test_validation_error_shape(self) -> None:
        resp = self.client.post("/api/case/start", json={})
        self.assertEqual(resp.status_code, 422)
        payload = resp.json()
        self.assertEqual(payload.get("detail"), "请求参数不合法")
        self.assertIsInstance(payload.get("errors"), list)
        self.assertTrue(payload.get("request_id"))


if __name__ == "__main__":
    unittest.main()
