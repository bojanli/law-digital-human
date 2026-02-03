import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable Sprint acceptance tests with pytest markers.")
    parser.add_argument(
        "--sprint",
        choices=["all", "sprint1", "sprint2", "sprint3"],
        default="all",
        help="Select a single sprint marker or run all acceptance tests.",
    )
    parser.add_argument(
        "--report-dir",
        default="backend/tests/reports",
        help="Directory to write junit/xml and log reports.",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    marker = "sprint1 or sprint2 or sprint3" if args.sprint == "all" else args.sprint
    junit_path = report_dir / f"{args.sprint}_acceptance.junit.xml"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "backend/tests/test_sprint_acceptance.py",
        "-m",
        marker,
        "-q",
        f"--junitxml={junit_path}",
    ]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        print(f"Acceptance suite passed. Report: {junit_path}")
    else:
        print(f"Acceptance suite failed (exit={result.returncode}). Report: {junit_path}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
