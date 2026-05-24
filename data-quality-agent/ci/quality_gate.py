"""Quality gate — evaluates generated reports and exits non-zero on critical failures.

Usage:
    python ci/quality_gate.py --reports-dir ci/outputs/reports

The gate reads the most recent Markdown report for each task and applies
configurable pass/fail thresholds.  Edit the THRESHOLDS dict below to
tighten or loosen the gate without touching the agent code.

Exit codes:
    0 — all checks passed
    1 — one or more checks exceeded their threshold
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds — edit these to tune the quality gate
# ---------------------------------------------------------------------------

# Each entry: task_report_prefix → {metric_pattern: max_allowed_value}
# metric_pattern is a regex matched against lines like "| Missing definitions | 5 |"
THRESHOLDS: dict[str, dict[str, int]] = {
    "data_dictionary_report": {
        # Allow up to 5 missing or extra definitions before failing CI.
        # (Synthetic CI CSV intentionally doesn't cover all dictionary columns.)
        r"CSV columns missing a dictionary definition\s*\|\s*(\d+)": 20,
        r"Columns with type/data inconsistencies\s*\|\s*(\d+)": 5,
    },
    "missing_values_report": {
        # Fail if any column is always-null (likely a dropped or broken column).
        r"Always-null columns\s*\|\s*(\d+)": 0,
    },
    "impossible_values_report": {
        # Zero tolerance for impossible-value rule violations.
        r"Rules with violations\s*\|\s*(\d+)": 0,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_report(reports_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(reports_dir.glob(f"{prefix}_*.md"), reverse=True)
    return candidates[0] if candidates else None


def _extract_metric(text: str, pattern: str) -> int | None:
    """Return the first integer captured by `pattern` in `text`, or None."""
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Data quality gate")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("ci/outputs/reports"),
        help="Directory containing the generated Markdown reports",
    )
    args = parser.parse_args(argv)

    reports_dir: Path = args.reports_dir
    if not reports_dir.is_dir():
        print(f"ERROR: reports dir not found: {reports_dir}", file=sys.stderr)
        return 1

    failures: list[str] = []
    checked = 0

    for prefix, metrics in THRESHOLDS.items():
        report = _latest_report(reports_dir, prefix)
        if report is None:
            print(f"  [skip] No {prefix} report found — task may not have run")
            continue

        text = report.read_text(encoding="utf-8")
        for pattern, max_val in metrics.items():
            value = _extract_metric(text, pattern)
            if value is None:
                print(f"  [skip] Pattern not found in {report.name}: {pattern!r}")
                continue
            checked += 1
            status = "✅ PASS" if value <= max_val else "❌ FAIL"
            print(f"  {status}  {prefix}: {pattern!r} = {value} (threshold: {max_val})")
            if value > max_val:
                failures.append(
                    f"{prefix}: metric matched by {pattern!r} = {value} exceeds threshold {max_val}"
                )

    print()
    print(f"Quality gate: {checked} checks, {len(failures)} failure(s)")

    if failures:
        print("\nFailed checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nReview the uploaded report artifacts for details, or run the agent "
            "locally with: python -m agent.runner --config ci/ci_agent_config.yaml",
            file=sys.stderr,
        )
        return 1

    print("All quality gate checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
