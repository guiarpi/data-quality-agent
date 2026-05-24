from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult

# Thresholds used in semantic type inference
_DEFAULT_CATEGORICAL_MAX = 20       # distinct values ≤ this → likely categorical
_DEFAULT_UNIQUENESS_ID = 0.99       # unique rate ≥ this → likely identifier
_DEFAULT_SAMPLE_COUNT = 5           # number of representative values shown per column
_TIMESTAMP_PARSE_THRESHOLD = 0.80   # fraction that must parse as datetime to call it a timestamp


def _infer_semantic_type(
    series: pd.Series,
    *,
    categorical_max: int,
    id_threshold: float,
) -> str:
    """Infer the semantic type of a column from its values.

    Numeric and datetime dtypes are handled directly to avoid false positives
    (e.g. pandas can parse plain integers as Unix timestamps, so we only attempt
    datetime parsing on object/string columns).

    Decision tree (first match wins):

    Datetime dtype → timestamp immediately.

    Numeric dtype (int / float):
      1. All null                          → unknown
      2. Unique rate ≥ id_threshold        → identifier
      3. Distinct values ≤ 2              → boolean_like
      4. Distinct values ≤ categorical_max → categorical
      5. Integer dtype or whole-number float → integer
      6. Float dtype                       → decimal

    Object / string dtype:
      1. All null                          → unknown
      2. Parseable as datetime (≥ threshold) → timestamp   ← before identifier check
         so date columns with one date per row aren't mislabelled as identifier
      3. Unique rate ≥ id_threshold        → identifier
      4. Distinct values ≤ 2              → boolean_like
      5. Distinct values ≤ categorical_max → categorical
      6. Numeric-parseable (≥ 95%)        → integer or decimal
      7. Fallback                         → free_text
    """
    non_null = series.dropna()
    if non_null.empty:
        return "unknown"

    n_total = len(series)
    n_distinct = int(non_null.nunique())
    unique_rate = n_distinct / n_total if n_total else 0.0

    # Datetime dtype — no further inference needed.
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"

    # --- Numeric dtype branch (int / float) ---
    if pd.api.types.is_numeric_dtype(series):
        if unique_rate >= id_threshold and n_distinct > categorical_max:
            return "identifier"
        if n_distinct <= 2:
            return "boolean_like"
        if n_distinct <= categorical_max:
            return "categorical"
        if pd.api.types.is_integer_dtype(series):
            return "integer"
        if (non_null == non_null.round()).all():
            return "integer"
        return "decimal"

    # --- Object / string branch ---
    # Try datetime parse before uniqueness check so date columns with one
    # unique value per row are not mislabelled as "identifier".
    try:
        parsed = pd.to_datetime(
            non_null, errors="coerce", infer_datetime_format=True, utc=True
        )
        parse_rate = parsed.notna().sum() / len(non_null)
        if parse_rate >= _TIMESTAMP_PARSE_THRESHOLD:
            return "timestamp"
    except Exception:
        pass

    if unique_rate >= id_threshold and n_distinct > categorical_max:
        return "identifier"
    if n_distinct <= 2:
        return "boolean_like"
    if n_distinct <= categorical_max:
        return "categorical"

    # Attempt numeric parse on string column
    numeric = pd.to_numeric(non_null, errors="coerce")
    numeric_rate = numeric.notna().sum() / len(non_null)
    if numeric_rate >= 0.95:
        valid = numeric.dropna()
        if (valid == valid.round()).all():
            return "integer"
        return "decimal"

    return "free_text"


def _column_stats(series: pd.Series, semantic_type: str, sample_count: int) -> dict[str, Any]:
    """Compute descriptive statistics appropriate for the column's semantic type."""
    non_null = series.dropna()
    stats: dict[str, Any] = {}

    if semantic_type in ("integer", "decimal"):
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if not numeric.empty:
            stats["min"] = _fmt(numeric.min())
            stats["max"] = _fmt(numeric.max())
            stats["mean"] = _fmt(round(float(numeric.mean()), 4))

    elif semantic_type == "timestamp":
        try:
            parsed = pd.to_datetime(non_null, errors="coerce", utc=True).dropna()
            if not parsed.empty:
                stats["min"] = str(parsed.min())
                stats["max"] = str(parsed.max())
        except Exception:
            pass

    # Sample values — shown for all types
    sample = non_null.drop_duplicates().head(sample_count)
    stats["sample_values"] = [str(v) for v in sample.tolist()]

    return stats


def _fmt(v: Any) -> str:
    """Format a numeric value for display, stripping unnecessary decimals."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def _profile_column(
    col: str,
    series: pd.Series,
    *,
    categorical_max: int,
    id_threshold: float,
    sample_count: int,
    total_rows: int,
) -> dict[str, Any]:
    """Build a full profile dict for one column."""
    null_count = int(series.isna().sum())
    null_rate = null_count / total_rows if total_rows else 0.0
    non_null = series.dropna()
    n_distinct = int(non_null.nunique()) if not non_null.empty else 0
    unique_rate = n_distinct / total_rows if total_rows else 0.0

    semantic_type = _infer_semantic_type(
        series,
        categorical_max=categorical_max,
        id_threshold=id_threshold,
    )

    stats = _column_stats(series, semantic_type, sample_count)

    return {
        "column": col,
        "pandas_dtype": str(series.dtype),
        "semantic_type": semantic_type,
        "null_rate": null_rate,
        "null_count": null_count,
        "distinct_values": n_distinct,
        "unique_rate": unique_rate,
        **stats,
    }


class DataTypesTask(BaseTask):
    """Full column-level type profiling: dtype, semantic type, cardinality, stats, samples."""

    @property
    def name(self) -> str:
        return "data_types"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("data_types", {})
        dd_cfg = ctx.config.get("data_dictionary", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        categorical_max = int(cfg.get("categorical_cardinality_max", _DEFAULT_CATEGORICAL_MAX))
        id_threshold = float(cfg.get("uniqueness_id_threshold", _DEFAULT_UNIQUENESS_ID))
        sample_count = int(cfg.get("sample_values_count", _DEFAULT_SAMPLE_COUNT))
        reports_dir = (
            ctx.base_dir / cfg.get("reports_dir", dd_cfg.get("reports_dir", "outputs/reports"))
        ).resolve()

        if ctx.sample_df is not None:
            df = ctx.sample_df
        else:
            if not csv_path.is_file():
                return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
            df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

        total_rows = len(df)
        profiles: list[dict[str, Any]] = []

        for col in df.columns:
            profile = _profile_column(
                col,
                df[col],
                categorical_max=categorical_max,
                id_threshold=id_threshold,
                sample_count=sample_count,
                total_rows=total_rows,
            )
            profiles.append(profile)

        # Count semantic types for the summary
        type_counts: dict[str, int] = {}
        for p in profiles:
            st = p["semantic_type"]
            type_counts[st] = type_counts.get(st, 0) + 1

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"data_types_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                categorical_max=categorical_max,
                id_threshold=id_threshold,
                total_rows=total_rows,
                profiles=profiles,
                type_counts=type_counts,
            ),
            encoding="utf-8",
        )

        return TaskResult(
            ok=True,
            message="Data types report written",
            findings={
                "columns_profiled": len(profiles),
                **{f"semantic_{k}": v for k, v in type_counts.items()},
            },
            report_path=report_path,
            raw_findings={
                "profiles": profiles,
                "type_counts": type_counts,
            },
        )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

_SEMANTIC_LABEL: dict[str, str] = {
    "identifier": "Identifier",
    "boolean_like": "Boolean-like",
    "categorical": "Categorical",
    "timestamp": "Timestamp",
    "integer": "Integer",
    "decimal": "Decimal",
    "free_text": "Free text",
    "unknown": "Unknown (all null)",
}

_SEMANTIC_NOTE: dict[str, str] = {
    "identifier": "nearly all values unique — likely a key or ID column",
    "boolean_like": "≤ 2 distinct values",
    "categorical": "low-cardinality — consider using as a dimension/filter",
    "timestamp": "parseable as datetime",
    "integer": "whole-number numeric",
    "decimal": "fractional numeric",
    "free_text": "high-cardinality text — not easily groupable",
    "unknown": "all values are null",
}


def _render_report(
    *,
    csv_path: Path,
    sample_rows: int,
    categorical_max: int,
    id_threshold: float,
    total_rows: int,
    profiles: list[dict[str, Any]],
    type_counts: dict[str, int],
) -> str:
    lines = [
        "# Data types quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {total_rows:,} (limit: {sample_rows:,})",
        f"- **Categorical cardinality max:** {categorical_max}",
        f"- **Identifier uniqueness threshold:** {id_threshold:.0%}",
        "",
        "## Semantic type summary",
        "",
        "| Semantic type | Columns | Notes |",
        "| --- | ---: | --- |",
    ]
    for st, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        label = _SEMANTIC_LABEL.get(st, st)
        note = _SEMANTIC_NOTE.get(st, "")
        lines.append(f"| {label} | {count} | {note} |")

    lines.extend(["", "## Column profiles", ""])
    lines.append("| Column | Pandas dtype | Semantic type | Distinct | Unique rate | Null rate | Min | Max | Mean | Sample values |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |")

    for p in profiles:
        mn = p.get("min", "")
        mx = p.get("max", "")
        mean = p.get("mean", "")
        samples = ", ".join(f"`{v}`" for v in p.get("sample_values", []))
        label = _SEMANTIC_LABEL.get(p["semantic_type"], p["semantic_type"])
        lines.append(
            f"| `{p['column']}` "
            f"| `{p['pandas_dtype']}` "
            f"| {label} "
            f"| {p['distinct_values']:,} "
            f"| {p['unique_rate']:.1%} "
            f"| {p['null_rate']:.1%} "
            f"| {mn} "
            f"| {mx} "
            f"| {mean} "
            f"| {samples} |"
        )

    lines.append("")
    return "\n".join(lines)
