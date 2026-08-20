from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from knowledge.knowledge_base import KnowledgeBase

_SAMPLE_SIZE = 5


# ---------------------------------------------------------------------------
# Numeric outlier detection
# ---------------------------------------------------------------------------

def _iqr_outliers(
    series: pd.Series,
    multiplier: float,
) -> dict[str, Any]:
    """Return IQR outlier stats for a numeric series (non-null values only)."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    q1 = float(s.quantile(0.25))
    q3 = float(s.quantile(0.75))
    iqr = q3 - q1

    if iqr == 0:
        # Constant column — no meaningful IQR.
        return {"fence_low": q1, "fence_high": q3, "low_count": 0, "high_count": 0,
                "total": 0, "rate": 0.0, "sample_low": [], "sample_high": []}

    fence_low = q1 - multiplier * iqr
    fence_high = q3 + multiplier * iqr

    low_mask = s < fence_low
    high_mask = s > fence_high

    sample_low = [_fmt(v) for v in s[low_mask].head(_SAMPLE_SIZE).tolist()]
    sample_high = [_fmt(v) for v in s[high_mask].head(_SAMPLE_SIZE).tolist()]
    total = int(low_mask.sum()) + int(high_mask.sum())

    return {
        "fence_low": _fmt(fence_low),
        "fence_high": _fmt(fence_high),
        "low_count": int(low_mask.sum()),
        "high_count": int(high_mask.sum()),
        "total": total,
        "rate": total / len(s),
        "sample_low": sample_low,
        "sample_high": sample_high,
    }


def _zscore_outliers(
    series: pd.Series,
    threshold: float,
) -> dict[str, Any]:
    """Return Z-score outlier stats for a numeric series (non-null values only)."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    mean = float(s.mean())
    std = float(s.std())

    # A zero, NaN or infinite std makes Z-scores meaningless (constant column,
    # a single non-null value, or overflow from extreme magnitudes).
    if std == 0 or not math.isfinite(std) or not math.isfinite(mean):
        return {"threshold": threshold, "mean": _fmt(mean), "std": _fmt(std),
                "low_count": 0, "high_count": 0, "total": 0, "rate": 0.0,
                "sample_low": [], "sample_high": []}

    z = (s - mean) / std
    low_mask = z < -threshold
    high_mask = z > threshold

    sample_low = [_fmt(v) for v in s[low_mask].head(_SAMPLE_SIZE).tolist()]
    sample_high = [_fmt(v) for v in s[high_mask].head(_SAMPLE_SIZE).tolist()]
    total = int(low_mask.sum()) + int(high_mask.sum())

    return {
        "threshold": threshold,
        "mean": _fmt(mean),
        "std": _fmt(round(std, 4)),
        "low_count": int(low_mask.sum()),
        "high_count": int(high_mask.sum()),
        "total": total,
        "rate": total / len(s),
        "sample_low": sample_low,
        "sample_high": sample_high,
    }


# ---------------------------------------------------------------------------
# Temporal outlier detection
# ---------------------------------------------------------------------------

def _temporal_outliers(
    series: pd.Series,
    min_year: int,
    max_year: int,
) -> dict[str, Any]:
    """Flag timestamps outside a plausible year range.

    Uses format='mixed' (pandas ≥ 2.0) so that bare dates ('1970-01-01')
    and full timestamps ('2024-01-01 00:00:00') coexist in the same column
    without causing silent NaT coercion.

    utc=True is required: without it, a column containing mixed UTC offsets
    parses to object dtype rather than datetime64, which breaks the .dt
    accessor below. Normalising to UTC is safe here because we only compare
    the calendar year against a plausible range.
    """
    try:
        parsed = pd.to_datetime(
            series, errors="coerce", format="mixed", utc=True
        ).dropna()
    except (TypeError, ValueError):
        # Fallback for older pandas versions without format='mixed'.
        parsed = pd.to_datetime(series, errors="coerce", utc=True).dropna()

    if parsed.empty:
        return {"total": 0, "rate": 0.0, "sample": []}

    years = parsed.dt.year
    mask = (years < min_year) | (years > max_year)
    outliers = parsed[mask]
    total = int(len(outliers))

    return {
        "min_year": min_year,
        "max_year": max_year,
        "total": total,
        "rate": total / len(parsed),
        "sample": [str(v) for v in outliers.head(_SAMPLE_SIZE).tolist()],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(v: Any) -> str:
    """Format a value for display.

    Guards against non-finite floats: int(inf) raises OverflowError and
    int(nan) raises ValueError, so both are short-circuited before any
    integer conversion is attempted. Extreme magnitudes (e.g. 1e308) can
    overflow to inf during mean/std aggregation on real-world data.
    """
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        if v == int(v):
            return str(int(v))
        return str(round(v, 4))
    return str(v)


def _col_casefold(df: pd.DataFrame) -> dict[str, str]:
    return {c.casefold(): c for c in df.columns}


def _excluded(col: str, exclude_set: set[str]) -> bool:
    return col.casefold() in exclude_set


def _is_timestamp_col(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if series.dtype != object:
        return False
    sample = series.dropna().head(50)
    if sample.empty:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed", utc=True)
    except (TypeError, ValueError):
        parsed = pd.to_datetime(sample, errors="coerce", utc=True)
    return parsed.notna().mean() >= 0.8


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class OutliersTask(BaseTask):
    """Detect statistical outliers in numeric columns and temporal anomalies in timestamps."""

    @property
    def name(self) -> str:
        return "outliers"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("outliers", {})
        dd_cfg = ctx.config.get("data_dictionary", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        iqr_multiplier = float(cfg.get("iqr_multiplier", 1.5))
        zscore_threshold = float(cfg.get("zscore_threshold", 3.0))
        min_non_null = int(cfg.get("min_non_null_rows", 30))
        temporal_min_year = int(cfg.get("temporal_min_year", 2000))
        temporal_max_year = int(cfg.get("temporal_max_year", 2035))
        exclude_raw: list[str] = cfg.get("columns_exclude", [])
        exclude_set = {c.casefold() for c in exclude_raw}
        reports_dir = (
            ctx.base_dir / cfg.get("reports_dir", dd_cfg.get("reports_dir", "outputs/reports"))
        ).resolve()
        kb_path = (
            ctx.base_dir / cfg.get("knowledge_base_path", "knowledge/learnings.json")
        ).resolve()

        if ctx.sample_df is not None:
            df = ctx.sample_df
        else:
            if not csv_path.is_file():
                return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
            df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

        kb = KnowledgeBase(kb_path)
        findings: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        skipped: list[str] = []

        for col in df.columns:
            if _excluded(col, exclude_set):
                skipped.append(f"{col} (excluded)")
                continue

            series = df[col]
            non_null_count = int(series.notna().sum())

            # --- Timestamp columns ---
            if _is_timestamp_col(series):
                if non_null_count < min_non_null:
                    skipped.append(f"{col} (too few non-null values: {non_null_count})")
                    continue

                temp = _temporal_outliers(series, temporal_min_year, temporal_max_year)
                if temp["total"] == 0:
                    continue

                if kb.is_false_positive(col, "outlier_temporal"):
                    suppressed.append({"column": col, "issue_type": "outlier_temporal"})
                    continue

                prior_note = kb.get_note(col, "outlier_temporal")
                finding: dict[str, Any] = {
                    "column": col,
                    "check_type": "temporal",
                    "violation_count": temp["total"],
                    "violation_rate": temp["rate"],
                    "detail": (
                        f"{temp['total']} timestamp(s) outside {temporal_min_year}–{temporal_max_year}; "
                        f"examples: {', '.join(temp['sample'])}"
                    ),
                    "temporal": temp,
                    "sample_values": temp["sample"],
                }
                if prior_note:
                    finding["prior_note"] = prior_note
                findings.append(finding)
                continue

            # --- Numeric columns ---
            # Skip booleans — is_numeric_dtype returns True for bool but IQR
            # arithmetic (subtraction) is not defined on boolean arrays.
            if pd.api.types.is_bool_dtype(series) or not pd.api.types.is_numeric_dtype(series):
                continue

            if non_null_count < min_non_null:
                skipped.append(f"{col} (too few non-null values: {non_null_count})")
                continue

            iqr = _iqr_outliers(series, iqr_multiplier)
            zsc = _zscore_outliers(series, zscore_threshold)

            total_flagged = max(iqr["total"], zsc["total"])
            if total_flagged == 0:
                continue

            if kb.is_false_positive(col, "outlier"):
                suppressed.append({"column": col, "issue_type": "outlier"})
                continue

            prior_note = kb.get_note(col, "outlier")

            # Build a concise detail string for the review loop.
            parts = []
            if iqr["total"] > 0:
                parts.append(
                    f"IQR: {iqr['total']} outlier(s) "
                    f"(fences [{iqr['fence_low']}, {iqr['fence_high']}])"
                )
            if zsc["total"] > 0:
                parts.append(
                    f"Z-score: {zsc['total']} outlier(s) "
                    f"(|z| > {zscore_threshold}, mean={zsc['mean']}, σ={zsc['std']})"
                )
            detail = "; ".join(parts)

            # Collect sample values from whichever side has more outliers.
            sample_values = list(
                dict.fromkeys(iqr["sample_low"] + iqr["sample_high"] + zsc["sample_low"] + zsc["sample_high"])
            )[:_SAMPLE_SIZE]

            finding = {
                "column": col,
                "check_type": "numeric",
                "violation_count": total_flagged,
                "violation_rate": total_flagged / non_null_count,
                "detail": detail,
                "iqr": iqr,
                "zscore": zsc,
                "sample_values": sample_values,
            }
            if prior_note:
                finding["prior_note"] = prior_note
            findings.append(finding)

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"outliers_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                iqr_multiplier=iqr_multiplier,
                zscore_threshold=zscore_threshold,
                min_non_null=min_non_null,
                findings=findings,
                suppressed=suppressed,
                skipped=skipped,
            ),
            encoding="utf-8",
        )

        numeric_findings = [f for f in findings if f["check_type"] == "numeric"]
        temporal_findings = [f for f in findings if f["check_type"] == "temporal"]

        return TaskResult(
            ok=True,
            message="Outliers report written",
            findings={
                "numeric_columns_with_outliers": len(numeric_findings),
                "timestamp_columns_with_temporal_outliers": len(temporal_findings),
                "suppressed_by_learnings": len(suppressed),
            },
            report_path=report_path,
            raw_findings={
                "outliers": findings,
                "suppressed": suppressed,
                "kb_path": str(kb_path),
            },
        )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _render_report(
    *,
    csv_path: Path,
    sample_rows: int,
    iqr_multiplier: float,
    zscore_threshold: float,
    min_non_null: int,
    findings: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    skipped: list[str],
) -> str:
    numeric = [f for f in findings if f["check_type"] == "numeric"]
    temporal = [f for f in findings if f["check_type"] == "temporal"]

    lines = [
        "# Outliers quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {sample_rows:,}",
        f"- **IQR multiplier:** {iqr_multiplier} (fences: Q1 − {iqr_multiplier}×IQR, Q3 + {iqr_multiplier}×IQR)",
        f"- **Z-score threshold:** ±{zscore_threshold}",
        f"- **Min non-null rows to evaluate:** {min_non_null}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Numeric columns with outliers | {len(numeric)} |",
        f"| Timestamp columns with temporal outliers | {len(temporal)} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        f"| Columns skipped | {len(skipped)} |",
        "",
    ]

    # Numeric outliers
    lines.extend(["## Numeric outliers", ""])
    if numeric:
        lines.extend([
            "| Column | IQR outliers | IQR fences | Z-score outliers | Sample values |",
            "| --- | ---: | --- | ---: | --- |",
        ])
        for f in numeric:
            iqr = f["iqr"]
            zsc = f["zscore"]
            iqr_str = (
                f"{iqr['total']} ({iqr['low_count']} low, {iqr['high_count']} high)"
                if iqr["total"] else "—"
            )
            fence_str = f"[{iqr['fence_low']}, {iqr['fence_high']}]" if iqr["total"] else "—"
            zsc_str = (
                f"{zsc['total']} ({zsc['low_count']} low, {zsc['high_count']} high)"
                if zsc["total"] else "—"
            )
            sample_str = ", ".join(f"`{v}`" for v in f["sample_values"])
            note = f" _(prior note: {f['prior_note']})_" if f.get("prior_note") else ""
            lines.append(
                f"| `{f['column']}` | {iqr_str} | {fence_str} | {zsc_str} | {sample_str}{note} |"
            )
        lines.append("")

        # Detailed section per column
        lines.extend(["### Detail", ""])
        for f in numeric:
            iqr = f["iqr"]
            zsc = f["zscore"]
            lines.extend([
                f"#### `{f['column']}`",
                "",
                f"| Method | Low outliers | High outliers | Total | Rate |",
                f"| --- | ---: | ---: | ---: | ---: |",
                f"| IQR (×{iqr_multiplier}) | {iqr['low_count']} | {iqr['high_count']} "
                f"| {iqr['total']} | {iqr['rate']:.1%} |",
                f"| Z-score (|z|>{zscore_threshold}) | {zsc['low_count']} | {zsc['high_count']} "
                f"| {zsc['total']} | {zsc['rate']:.1%} |",
                "",
            ])
            if iqr["sample_low"]:
                lines.append(f"- **IQR low-end samples** (below {iqr['fence_low']}): "
                              + ", ".join(f"`{v}`" for v in iqr["sample_low"]))
            if iqr["sample_high"]:
                lines.append(f"- **IQR high-end samples** (above {iqr['fence_high']}): "
                              + ", ".join(f"`{v}`" for v in iqr["sample_high"]))
            if zsc["sample_low"]:
                lines.append(f"- **Z-score low-end samples**: "
                              + ", ".join(f"`{v}`" for v in zsc["sample_low"]))
            if zsc["sample_high"]:
                lines.append(f"- **Z-score high-end samples**: "
                              + ", ".join(f"`{v}`" for v in zsc["sample_high"]))
            lines.append("")
    else:
        lines.extend(["_No numeric outliers detected._", ""])

    # Temporal outliers
    lines.extend(["## Temporal outliers", ""])
    if temporal:
        lines.extend([
            "| Column | Outlier timestamps | Rate | Sample values |",
            "| --- | ---: | ---: | --- |",
        ])
        for f in temporal:
            t = f["temporal"]
            sample_str = ", ".join(f"`{v}`" for v in f["sample_values"])
            note = f" _(prior note: {f['prior_note']})_" if f.get("prior_note") else ""
            lines.append(
                f"| `{f['column']}` | {t['total']} | {t['rate']:.1%} | {sample_str}{note} |"
            )
        lines.append("")
    else:
        lines.extend(["_No temporal outliers detected._", ""])

    # Suppressed
    lines.extend(["## Suppressed by prior learnings", ""])
    if suppressed:
        lines.extend([
            "| Column | Issue type |",
            "| --- | --- |",
        ])
        for s in suppressed:
            lines.append(f"| `{s['column']}` | {s['issue_type']} |")
    else:
        lines.append("_None — no findings have been marked as false positives yet._")
    lines.append("")

    return "\n".join(lines)
