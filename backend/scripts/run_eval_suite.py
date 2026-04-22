import argparse
import json
import time
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.main import app
from app.services import knowledge as knowledge_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed 20-case evaluation suite for thesis reporting.")
    parser.add_argument("--dataset", default="backend/tests/eval_dataset.json", help="Evaluation dataset JSON path.")
    parser.add_argument(
        "--report-json",
        default="backend/tests/reports/eval_suite_report.json",
        help="Detailed JSON report output.",
    )
    parser.add_argument(
        "--report-md",
        default="backend/tests/reports/eval_suite_report.md",
        help="Readable Markdown report output.",
    )
    parser.add_argument(
        "--use-live-provider",
        action="store_true",
        help="Use current provider config. Default runs in mock LLM mode for stable reproducibility.",
    )
    args = parser.parse_args()

    dataset = _load_json(_resolve_path(args.dataset))
    report = run_eval(dataset=dataset, use_live_provider=args.use_live_provider)

    report_json_path = _resolve_path(args.report_json)
    report_md_path = _resolve_path(args.report_md)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md_path.write_text(_to_markdown(report), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"JSON report saved: {report_json_path}")
    print(f"Markdown report saved: {report_md_path}")
    return 0


def run_eval(dataset: dict[str, Any], use_live_provider: bool) -> dict[str, Any]:
    old_llm_provider = settings.llm_provider
    old_tts_enabled = settings.tts_enabled
    old_search = knowledge_service.search
    if not use_live_provider:
        settings.llm_provider = "mock"
        settings.tts_enabled = False
        knowledge_service.search = lambda *_args, **_kwargs: []

    try:
        with TestClient(app) as client:
            chat_regular_results = [_run_chat_item(client, item, expect_followup=False) for item in dataset["chat_regular"]]
            chat_incomplete_results = [_run_chat_item(client, item, expect_followup=True) for item in dataset["chat_incomplete"]]
            case_results = [_run_case_item(client, item) for item in dataset["case_branches"]]
    finally:
        settings.llm_provider = old_llm_provider
        settings.tts_enabled = old_tts_enabled
        knowledge_service.search = old_search

    all_rows = chat_regular_results + chat_incomplete_results + case_results
    passed = sum(1 for r in all_rows if r["pass"])
    failed = len(all_rows) - passed

    summary = {
        "total": len(all_rows),
        "passed": passed,
        "failed": failed,
        "pass_rate": _ratio(passed, len(all_rows)),
        "chat_regular_pass_rate": _ratio(sum(1 for r in chat_regular_results if r["pass"]), len(chat_regular_results)),
        "chat_incomplete_pass_rate": _ratio(sum(1 for r in chat_incomplete_results if r["pass"]), len(chat_incomplete_results)),
        "case_branch_pass_rate": _ratio(sum(1 for r in case_results if r["pass"]), len(case_results)),
        "chat_latency_ms": _latency_stats(chat_regular_results + chat_incomplete_results),
        "case_latency_ms": _latency_stats(case_results),
    }
    return {
        "meta": {
            "dataset_size": {
                "chat_regular": len(chat_regular_results),
                "chat_incomplete": len(chat_incomplete_results),
                "case_branches": len(case_results),
            },
            "use_live_provider": use_live_provider,
            "mock_search_disabled": not use_live_provider,
            "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": summary,
        "details": {
            "chat_regular": chat_regular_results,
            "chat_incomplete": chat_incomplete_results,
            "case_branches": case_results,
        },
    }


def _run_chat_item(client: TestClient, item: dict[str, Any], expect_followup: bool) -> dict[str, Any]:
    started = time.perf_counter()
    resp = client.post(
        "/api/chat",
        json={
            "session_id": f"eval_{item['id']}",
            "text": item["text"],
            "mode": "chat",
            "case_state": None,
        },
    )
    latency_ms = (time.perf_counter() - started) * 1000

    checks: list[tuple[str, bool]] = []
    checks.append(("status_200", resp.status_code == 200))
    body = resp.json() if resp.status_code == 200 else {}
    answer = body.get("answer_json") if isinstance(body, dict) else None
    checks.append(("answer_json_exists", isinstance(answer, dict)))

    if isinstance(answer, dict):
        checks.append(("has_conclusion", isinstance(answer.get("conclusion"), str) and bool(answer.get("conclusion", "").strip())))
        checks.append(("analysis_is_list", isinstance(answer.get("analysis"), list)))
        checks.append(("actions_is_list", isinstance(answer.get("actions"), list)))
        checks.append(("citations_is_list", isinstance(answer.get("citations"), list)))
        checks.append(("follow_up_is_list", isinstance(answer.get("follow_up_questions"), list)))
        checks.append(("emotion_is_str", isinstance(answer.get("emotion"), str)))
        if expect_followup:
            followups = answer.get("follow_up_questions") if isinstance(answer.get("follow_up_questions"), list) else []
            emotion = str(answer.get("emotion") or "").strip().lower()
            checks.append(("incomplete_triggers_followup_or_serious", bool(followups) or emotion == "serious"))

    passed = all(flag for _, flag in checks)
    return {
        "id": item["id"],
        "type": "chat_incomplete" if expect_followup else "chat_regular",
        "pass": passed,
        "latency_ms": round(latency_ms, 2),
        "checks": [{"name": name, "pass": ok} for name, ok in checks],
    }


def _run_case_item(client: TestClient, item: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    start_resp = client.post("/api/case/start", json={"case_id": item["case_id"]})
    checks: list[tuple[str, bool]] = [("start_status_200", start_resp.status_code == 200)]
    current_json = start_resp.json() if start_resp.status_code == 200 else {}
    session_id = current_json.get("session_id")
    checks.append(("session_created", isinstance(session_id, str) and bool(session_id)))

    if not session_id:
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "id": item["id"],
            "type": "case_branch",
            "pass": False,
            "latency_ms": round(latency_ms, 2),
            "checks": [{"name": name, "pass": ok} for name, ok in checks],
            "final_state": None,
            "path_len": 0,
        }

    final_json = current_json
    for step in item["steps"]:
        payload = {"session_id": session_id}
        payload.update(step)
        step_resp = client.post("/api/case/step", json=payload)
        checks.append(("step_status_200", step_resp.status_code == 200))
        if step_resp.status_code != 200:
            final_json = {}
            break
        final_json = step_resp.json()

    latency_ms = (time.perf_counter() - started) * 1000
    final_state = final_json.get("state")
    path_len = len(final_json.get("path") or []) if isinstance(final_json, dict) else 0
    checks.append(("final_state_verdict", final_state == "verdict"))
    checks.append(("path_len_ge_2", path_len >= 2))

    passed = all(flag for _, flag in checks)
    return {
        "id": item["id"],
        "type": "case_branch",
        "pass": passed,
        "latency_ms": round(latency_ms, 2),
        "checks": [{"name": name, "pass": ok} for name, ok in checks],
        "final_state": final_state,
        "path_len": path_len,
    }


def _latency_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(r["latency_ms"]) for r in rows]
    if not values:
        return {"sample_size": 0, "p50_ms": 0.0, "p90_ms": 0.0, "avg_ms": 0.0}
    return {
        "sample_size": len(values),
        "p50_ms": round(_percentile(values, 50), 2),
        "p90_ms": round(_percentile(values, 90), 2),
        "avg_ms": round(sum(values) / len(values), 2),
    }


def _percentile(values: list[float], p: float) -> float:
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    weight = rank - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def _ratio(num: int, den: int) -> float:
    return round((num / den), 4) if den else 0.0


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return (
        "# 固定测试集自动评测报告\n\n"
        f"- total: {summary['total']}\n"
        f"- passed: {summary['passed']}\n"
        f"- failed: {summary['failed']}\n"
        f"- pass_rate: {summary['pass_rate']:.4f}\n"
        f"- chat_regular_pass_rate: {summary['chat_regular_pass_rate']:.4f}\n"
        f"- chat_incomplete_pass_rate: {summary['chat_incomplete_pass_rate']:.4f}\n"
        f"- case_branch_pass_rate: {summary['case_branch_pass_rate']:.4f}\n"
        f"- chat_latency_p50_ms: {summary['chat_latency_ms']['p50_ms']:.2f}\n"
        f"- chat_latency_p90_ms: {summary['chat_latency_ms']['p90_ms']:.2f}\n"
        f"- case_latency_p50_ms: {summary['case_latency_ms']['p50_ms']:.2f}\n"
        f"- case_latency_p90_ms: {summary['case_latency_ms']['p90_ms']:.2f}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
