import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import metrics as metrics_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Export thesis-ready KPI summary from API metrics.")
    parser.add_argument("--days", type=int, default=None, help="Optional recent days filter.")
    parser.add_argument("--json-out", default="backend/tests/reports/paper_kpi.json", help="JSON output path.")
    parser.add_argument("--md-out", default="backend/tests/reports/paper_kpi.md", help="Markdown output path.")
    args = parser.parse_args()

    payload = metrics_service.get_paper_kpis(days=args.days)

    json_path = _resolve_output_path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = _resolve_output_path(args.md_out)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_to_markdown(payload), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"JSON saved to: {json_path}")
    print(f"Markdown saved to: {md_path}")


def _to_markdown(payload: dict) -> str:
    chat_latency = payload["chat_latency"]
    case_latency = payload["case_step_latency"]
    return (
        "# 论文评测关键指标\n\n"
        f"- days: {payload['days']}\n"
        f"- chat_total: {payload['chat_total']}\n"
        f"- chat_with_evidence: {payload['chat_with_evidence']}\n"
        f"- citation_hit_rate: {payload['citation_hit_rate']:.4f}\n"
        f"- chat_no_evidence: {payload['chat_no_evidence']}\n"
        f"- no_evidence_reject_rate: {payload['no_evidence_reject_rate']:.4f}\n"
        f"- chat_latency_p50_ms: {chat_latency['p50_ms']:.2f}\n"
        f"- chat_latency_p90_ms: {chat_latency['p90_ms']:.2f}\n"
        f"- chat_latency_avg_ms: {chat_latency['avg_ms']:.2f}\n"
        f"- case_step_latency_p50_ms: {case_latency['p50_ms']:.2f}\n"
        f"- case_step_latency_p90_ms: {case_latency['p90_ms']:.2f}\n"
        f"- case_step_latency_avg_ms: {case_latency['avg_ms']:.2f}\n"
    )


def _resolve_output_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return ROOT / path


if __name__ == "__main__":
    main()
