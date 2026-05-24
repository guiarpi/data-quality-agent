from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from knowledge.knowledge_base import KnowledgeBase

# ---------------------------------------------------------------------------
# Placeholder detection
# ---------------------------------------------------------------------------

# Strings that look like real values but function as nulls.
# All compared case-insensitively after stripping whitespace.
_PLACEHOLDER_STRINGS: frozenset[str] = frozenset(
    {
        "n/a", "na", "n.a.", "n.a",
        "null", "none", "nil",
        "unknown", "unk",
        "tbd", "tba", "todo",
        "missing", "not available", "not applicable",
        "undefined", "unspecified",
        "-", "--", "---", ".", "..",
        "0",         # "0" in a string column (not numeric) is usually a placeholder
        "empty", "blank",
        "test", "temp", "dummy", "placeholder", "example", "sample",
        "#n/a", "#na", "#null", "#value",  # spreadsheet export artefacts
    }
)

_SAMPLE_SIZE = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col_present(df: pd.DataFrame, col: str) -> bool:
    return col.casefold() in {c.casefold() for c in df.columns}


def _get_col(df: pd.DataFrame, col: str) -> pd.Series:
    for c in df.columns:
        if c.casefold() == col.casefold():
            return df[c]
    raise KeyError(col)


def _string_columns(df: pd.DataFrame) -> list[str]:
    """Return names of object-dtype columns (likely string)."""
    return [c for c in df.columns if df[c].dtype == object]


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------

def _eval_enum(df: pd.DataFrame, rule: dict[str, Any]) -> dict[str, Any] | None:
    """Check that non-null values in a column belong to an allowed set.

    Config keys:
      column       — column name (case-insensitive)
      allowed      — list of permitted values
      case_insensitive — compare ignoring case (default: true)
      label, description
    """
    col = rule["column"]
    if not _col_present(df, col):
        return None

    series = _get_col(df, col).dropna()
    if series.empty:
        return None

    case_insensitive = bool(rule.get("case_insensitive", True))
    allowed_raw: list[str] = [str(v) for v in rule["allowed"]]
    allowed_set = (
        {v.casefold() for v in allowed_raw}
        if case_insensitive
        else set(allowed_raw)
    )

    as_str = series.astype(str)
    check = as_str.str.casefold() if case_insensitive else as_str
    violated = series[~check.isin(allowed_set)]
    return _build_result(rule, col, violated, len(series), "enum")


def _eval_pattern(df: pd.DataFrame, rule: dict[str, Any]) -> dict[str, Any] | None:
    """Check that non-null string values match a regex pattern.

    Config keys:
      column   — column name (case-insensitive)
      pattern  — Python regex; anchored with ^ and $ if you want full-match
      label, description
    """
    col = rule["column"]
    if not _col_present(df, col):
        return None

    series = _get_col(df, col).dropna().astype(str)
    if series.empty:
        return None

    regex = re.compile(rule["pattern"])
    violated = series[~series.str.match(regex)]
    return _build_result(rule, col, violated, len(series), "pattern")


# ---------------------------------------------------------------------------
# Automatic checks (no per-column config required)
# ---------------------------------------------------------------------------

def _check_placeholders(
    df: pd.DataFrame,
    kb: KnowledgeBase,
    min_violation_rate: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan all object columns for placeholder strings.

    Returns (findings, suppressed) lists.
    """
    findings: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for col in _string_columns(df):
        series = df[col].dropna().astype(str)
        if series.empty:
            continue

        normalised = series.str.strip().str.casefold()
        mask = normalised.isin(_PLACEHOLDER_STRINGS)
        violated = series[mask]

        if len(violated) == 0:
            continue

        rate = len(violated) / len(series)
        if rate < min_violation_rate:
            continue

        if kb.is_false_positive(col, "placeholder_value"):
            suppressed.append({"column": col, "issue_type": "placeholder_value"})
            continue

        prior_note = kb.get_note(col, "placeholder_value")
        finding: dict[str, Any] = {
            "label": col,
            "rule_type": "placeholder",
            "column": col,
            "description": f"Column contains placeholder / functional-null strings",
            "violation_count": len(violated),
            "violation_rate": rate,
            "denominator": len(series),
            "sample_values": list(violated.unique()[:_SAMPLE_SIZE]),
        }
        if prior_note:
            finding["prior_note"] = prior_note
        findings.append(finding)

    return findings, suppressed


def _check_whitespace(
    df: pd.DataFrame,
    kb: KnowledgeBase,
    min_violation_rate: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan all object columns for leading/trailing whitespace or double spaces.

    Returns (findings, suppressed) lists.
    """
    findings: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    double_space_re = re.compile(r" {2,}")

    for col in _string_columns(df):
        series = df[col].dropna().astype(str)
        if series.empty:
            continue

        has_edge_space = series != series.str.strip()
        has_double_space = series.str.contains(double_space_re, regex=True)
        mask = has_edge_space | has_double_space
        violated = series[mask]

        if len(violated) == 0:
            continue

        rate = len(violated) / len(series)
        if rate < min_violation_rate:
            continue

        if kb.is_false_positive(col, "whitespace_anomaly"):
            suppressed.append({"column": col, "issue_type": "whitespace_anomaly"})
            continue

        prior_note = kb.get_note(col, "whitespace_anomaly")
        finding: dict[str, Any] = {
            "label": col,
            "rule_type": "whitespace",
            "column": col,
            "description": "Column contains leading/trailing spaces or double spaces",
            "violation_count": len(violated),
            "violation_rate": rate,
            "denominator": len(series),
            "sample_values": [repr(v) for v in violated.head(_SAMPLE_SIZE).tolist()],
        }
        if prior_note:
            finding["prior_note"] = prior_note
        findings.append(finding)

    return findings, suppressed


# ---------------------------------------------------------------------------
# Rule dispatcher
# ---------------------------------------------------------------------------

_RULE_EVALUATORS = {
    "enum": _eval_enum,
    "pattern": _eval_pattern,
}


def _detect_rule_type(rule: dict[str, Any]) -> str:
    if "type" in rule:
        return rule["type"]
    if "allowed" in rule:
        return "enum"
    if "pattern" in rule:
        return "pattern"
    return "unknown"


def _build_result(
    rule: dict[str, Any],
    column_display: str,
    violation_series: pd.Series,
    denominator: int,
    rule_type: str,
) -> dict[str, Any]:
    violation_count = int(len(violation_series))
    violation_rate = violation_count / denominator if denominator else 0.0
    sample = [str(v) for v in violation_series.head(_SAMPLE_SIZE).tolist()]
    return {
        "label": rule["label"],
        "rule_type": rule_type,
        "column": column_display,
        "description": rule.get("description", ""),
        "violation_count": violation_count,
        "violation_rate": violation_rate,
        "denominator": denominator,
        "sample_values": sample,
    }


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class InvalidEntriesTask(BaseTask):
    """Flag malformed values: enum violations, pattern mismatches, placeholders, whitespace."""

    @property
    def name(self) -> str:
        return "invalid_entries"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("invalid_entries", {})
        dd_cfg = ctx.config.get("data_dictionary", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        min_violation_rate = float(cfg.get("min_violation_rate", 0.0))
        check_placeholders = bool(cfg.get("check_placeholders", True))
        check_whitespace = bool(cfg.get("check_whitespace", True))
        reports_dir = (
            ctx.base_dir / cfg.get("reports_dir", dd_cfg.get("reports_dir", "outputs/reports"))
        ).resolve()
        kb_path = (
            ctx.base_dir / cfg.get("knowledge_base_path", "knowledge/learnings.json")
        ).resolve()

        rules_cfg: list[dict[str, Any]] = cfg.get("rules", [])

        if ctx.sample_df is not None:
            df = ctx.sample_df
        else:
            if not csv_path.is_file():
                return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
            df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

        kb = KnowledgeBase(kb_path)
        rule_findings: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        skipped_rules: list[str] = []

        # --- Configured rules (enum, pattern) ---
        for rule in rules_cfg:
            label = rule.get("label", "unnamed")
            rule_type = _detect_rule_type(rule)
            evaluator = _RULE_EVALUATORS.get(rule_type)

            if evaluator is None:
                skipped_rules.append(f"{label} (unknown type: {rule_type})")
                continue

            result = evaluator(df, rule)
            if result is None:
                skipped_rules.append(f"{label} (column not in CSV)")
                continue
            if result["violation_count"] == 0:
                continue
            if result["violation_rate"] < min_violation_rate:
                continue

            if kb.is_false_positive(label, "invalid_entry"):
                suppressed.append({"label": label, "issue_type": "invalid_entry"})
                continue

            prior_note = kb.get_note(label, "invalid_entry")
            if prior_note:
                result["prior_note"] = prior_note
            rule_findings.append(result)

        # --- Automatic checks ---
        placeholder_findings: list[dict[str, Any]] = []
        placeholder_suppressed: list[dict[str, Any]] = []
        if check_placeholders:
            placeholder_findings, placeholder_suppressed = _check_placeholders(
                df, kb, min_violation_rate
            )
            suppressed.extend(placeholder_suppressed)

        whitespace_findings: list[dict[str, Any]] = []
        whitespace_suppressed: list[dict[str, Any]] = []
        if check_whitespace:
            whitespace_findings, whitespace_suppressed = _check_whitespace(
                df, kb, min_violation_rate
            )
            suppressed.extend(whitespace_suppressed)

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"invalid_entries_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                min_violation_rate=min_violation_rate,
                rule_findings=rule_findings,
                placeholder_findings=placeholder_findings,
                whitespace_findings=whitespace_findings,
                suppressed=suppressed,
                skipped_rules=skipped_rules,
            ),
            encoding="utf-8",
        )

        all_findings = rule_findings + placeholder_findings + whitespace_findings
        # Pass structured findings to the review loop
        raw_findings_payload = {
            "invalid_entries": all_findings,
            "suppressed": suppressed,
            "kb_path": str(kb_path),
        }

        return TaskResult(
            ok=True,
            message="Invalid entries report written",
            findings={
                "rules_evaluated": len(rules_cfg),
                "rule_violations": len(rule_findings),
                "columns_with_placeholders": len(placeholder_findings),
                "columns_with_whitespace": len(whitespace_findings),
                "suppressed_by_learnings": len(suppressed),
            },
            report_path=report_path,
            raw_findings=raw_findings_payload,
        )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _findings_table(findings: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Rule / Column | Type | Violations | Rate | Sample invalid values |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for f in findings:
        sample_str = ", ".join(f"`{v}`" for v in f["sample_values"])
        note = f" _(prior note: {f['prior_note']})_" if f.get("prior_note") else ""
        lines.append(
            f"| **{f['label']}** | {f['rule_type']} "
            f"| {f['violation_count']:,} | {f['violation_rate']:.1%} "
            f"| {sample_str}{note} |"
        )
    return lines


def _render_report(
    *,
    csv_path: Path,
    sample_rows: int,
    min_violation_rate: float,
    rule_findings: list[dict[str, Any]],
    placeholder_findings: list[dict[str, Any]],
    whitespace_findings: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    skipped_rules: list[str],
) -> str:
    total_findings = len(rule_findings) + len(placeholder_findings) + len(whitespace_findings)
    lines = [
        "# Invalid entries quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {sample_rows:,}",
        f"- **Min violation rate to report:** {min_violation_rate:.1%}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Configured rules with violations | {len(rule_findings)} |",
        f"| Columns with placeholder values | {len(placeholder_findings)} |",
        f"| Columns with whitespace anomalies | {len(whitespace_findings)} |",
        f"| Total findings | {total_findings} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        f"| Rules skipped (column absent or unknown type) | {len(skipped_rules)} |",
        "",
    ]

    # Configured rule findings
    lines.append("## Configured rule violations")
    lines.append("")
    if rule_findings:
        lines.extend(_findings_table(rule_findings))
    else:
        lines.append("_No violations found across all configured rules._")
    lines.append("")

    # Placeholder findings
    lines.append("## Placeholder / functional-null values")
    lines.append("")
    lines.append(
        "_These columns contain strings like `N/A`, `null`, `unknown`, `tbd`, etc. "
        "that are non-null but functionally missing._"
    )
    lines.append("")
    if placeholder_findings:
        lines.extend(_findings_table(placeholder_findings))
    else:
        lines.append("_None detected._")
    lines.append("")

    # Whitespace findings
    lines.append("## Whitespace anomalies")
    lines.append("")
    lines.append(
        "_These columns contain values with leading/trailing spaces or double spaces "
        "that may cause silent mismatches in joins, filters, and lookups._"
    )
    lines.append("")
    if whitespace_findings:
        lines.extend(_findings_table(whitespace_findings))
    else:
        lines.append("_None detected._")
    lines.append("")

    # Suppressed
    lines.append("## Suppressed by prior learnings")
    lines.append("")
    if suppressed:
        lines.extend([
            "| Column / Rule | Issue type |",
            "| --- | --- |",
        ])
        for s in suppressed:
            key = s.get("label", s.get("column", "—"))
            lines.append(f"| `{key}` | {s['issue_type']} |")
    else:
        lines.append("_None — no findings have been marked as false positives yet._")
    lines.append("")

    return "\n".join(lines)
