import argparse
import csv
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import metrics as metrics_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Export API metrics summary and rows to CSV")
    parser.add_argument("--output", default="backend/tests/metrics_export.csv", help="CSV output path")
    parser.add_argument("--endpoint", default=None, help="Optional endpoint filter")
    parser.add_argument("--days", type=int, default=None, help="Optional recent days filter")
    args = parser.parse_args()

    rows = metrics_service.fetch_metrics_rows(endpoint=args.endpoint, days=args.days)
    summary = metrics_service.get_metrics_summary(endpoint=args.endpoint, days=args.days)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "endpoint",
                "ok",
                "status_code",
                "latency_ms",
                "request_id",
                "created_at",
                "meta_json",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "endpoint": row["endpoint"],
                    "ok": row["ok"],
                    "status_code": row["status_code"],
                    "latency_ms": row["latency_ms"],
                    "request_id": row["request_id"],
                    "created_at": row["created_at"],
                    "meta_json": json.dumps(row["meta"], ensure_ascii=False),
                }
            )

    print("=== Metrics Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV saved to: {output_path}")


if __name__ == "__main__":
    main()
