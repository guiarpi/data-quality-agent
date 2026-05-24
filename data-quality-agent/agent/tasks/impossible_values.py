from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from knowledge.knowledge_base import KnowledgeBase

# Number of example violating values to show in the report / review loop.
_SAMPLE_SIZE = 5


# ---------------------------------------------------------------------------
# Rule evaluation helpers
# ---------------------------------------------------------------------------

def _col_present(df: pd.DataFrame, col: str) -> bool:
    """Case-insensitive column lookup."""
    return col.casefold() in {c.casefold() for c in df.columns}


def _get_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Return the series for col (case-insensitive match)."""
    for c in df.columns:
        if c.casefold() == col.casefold():
            return df[c]
    raise KeyError(col)


def _eval_range(
    df: pd.DataFrame, rule: dict[str, Any]
) -> dict[str, Any] | None:
    """Check that a numeric column falls within [min, max].

    Config keys:
      column   — column name (case-insensitive)
      min      — lower bound (inclusive), optional
      max      — upper bound (inclusive), optional
      label    — unique rule identifier
      description — human-readable description
    """
    col = rule["column"]
    if not _col_present(df, col):
        return None  # column absent — skip silently

    series = _get_col(df, col)
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    if non_null.empty:
        return None

    lo = rule.get("min")
    hi = rule.get("max")

    mask = pd.Series(False, index=non_null.index)
    if lo is not None:
        mask |= non_null < lo
    if hi is not None:
        mask |= non_null > hi

    violations = non_null[mask]
    return _build_result(rule, col, violations, len(df), "range")


def _eval_date_order(
    df: pd.DataFrame, rule: dict[str, Any]
) -> dict[str, Any] | None:
    """Check that an earlier timestamp column is ≤ a later timestamp column.

    Config keys:
      earlier  — column that must come first (case-insensitive)
      later    — column that must come after (case-insensitive)
      label    — unique rule identifier
      description — human-readable description
    """
    earlier_col = rule["earlier"]
    later_col = rule["later"]

    if not _col_present(df, earlier_col) or not _col_present(df, later_col):
        return None

    earlier = pd.to_datetime(_get_col(df, earlier_col), errors="coerce", utc=True)
    later = pd.to_datetime(_get_col(df, later_col), errors="coerce", utc=True)

    # Only evaluate rows where both values are non-null.
    both_present = earlier.notna() & later.notna()
    if not both_present.any():
        return None

    violated = both_present & (earlier > later)
    violation_values = (
        earlier[violated].astype(str) + " > " + later[violated].astype(str)
    )
    return _build_result(
        rule,
        f"{earlier_col} → {later_col}",
        violation_values,
        both_present.sum(),
        "date_order",
    )


def _eval_not_null_if(
    df: pd.DataFrame, rule: dict[str, Any]
) -> dict[str, Any] | None:
    """Check that a dependent column is not null when a condition column equals a value.

    Config keys:
      when_column  — condition column (case-insensitive)
      when_value   — value to match (use Python literals: true/false/null or a string/number)
      then_column  — column that must be non-null when condition holds
      label        — unique rule identifier
      description  — human-readable description
    """
    when_col = rule["when_column"]
    then_col = rule["then_column"]
    when_value = rule["when_value"]

    if not _col_present(df, when_col) or not _col_present(df, then_col):
        return None

    when_series = _get_col(df, when_col)
    then_series = _get_col(df, then_col)

    # Normalise the condition value for comparison.
    if isinstance(when_value, bool):
        condition = when_series.astype(str).str.casefold().isin(
            {"true", "1", "yes"} if when_value else {"false", "0", "no"}
        )
    elif when_value is None:
        condition = when_series.isna()
    else:
        condition = when_series == when_value

    # Rows where condition holds AND dependent column is null.
    violated = condition & then_series.isna()
    violation_values = when_series[violated].astype(str)

    return _build_result(
        rule,
        f"{when_col} → {then_col}",
        violation_values,
        int(condition.sum()),
        "not_null_if",
    )


def _build_result(
    rule: dict[str, Any],
    column_display: str,
    violation_series: pd.Series,
    denominator: int,
    rule_type: str,
) -> dict[str, Any]:
    """Build a standardised result dict for any rule type."""
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
# Rule dispatcher
# ---------------------------------------------------------------------------

_RULE_EVALUATORS = {
    "range": _eval_range,
    "date_order": _eval_date_order,
    "not_null_if": _eval_not_null_if,
}


def _detect_rule_type(rule: dict[str, Any]) -> str:
    """Infer rule type from config keys if not explicitly set."""
    if "type" in rule:
        return rule["type"]
    if "earlier" in rule and "later" in rule:
        return "date_order"
    if "when_column" in rule and "then_column" in rule:
        return "not_null_if"
    return "range"  # default — requires 'column' + at least one of min/max


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class ImpossibleValuesTask(BaseTask):
    """Evaluate domain rules and flag rows with logically impossible values."""

    @property
    def name(self) -> str:
        return "impossible_values"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("impossible_values", {})
        dd_cfg = ctx.config.get("data_dictionary", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        min_violation_rate = float(cfg.get("min_violation_rate", 0.0))
        reports_dir = (
            ctx.base_dir / cfg.get("reports_dir", dd_cfg.get("reports_dir", "outputs/reports"))
        ).resolve()
        kb_path = (
            ctx.base_dir / cfg.get("knowledge_base_path", "knowledge/learnings.json")
        ).resolve()

        rules_cfg: list[dict[str, Any]] = cfg.get("rules", [])
        if not rules_cfg:
            return TaskResult(
                ok=True,
                message="No rules configured — skipping impossible values check. "
                        "Add rules under impossible_values.rules in agent_config.yaml.",
                findings={"rules_evaluated": 0},
            )

        if ctx.sample_df is not None:
            df = ctx.sample_df
        else:
            if not csv_path.is_file():
                return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
            df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

        kb = KnowledgeBase(kb_path)
        findings: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        skipped_rules: list[str] = []

        for rule in rules_cfg:
            label = rule.get("label", "unnamed")
            rule_type = _detect_rule_type(rule)
            evaluator = _RULE_EVALUATORS.get(rule_type)

            if evaluator is None:
                skipped_rules.append(f"{label} (unknown type: {rule_type})")
                continue

            result = evaluator(df, rule)
            if result is None:
                # Column(s) absent from CSV — skip silently.
                skipped_rules.append(f"{label} (column not in CSV)")
                continue

            if result["violation_count"] == 0:
                continue  # Rule passes — nothing to flag.

            if result["violation_rate"] < min_violation_rate:
                continue  # Below the configured reporting threshold.

            if kb.is_false_positive(label, "impossible_value"):
                suppressed.append({"label": label, "issue_type": "impossible_value"})
                continue

            prior_note = kb.get_note(label, "impossible_value")
            if prior_note:
                result["prior_note"] = prior_note

            findings.append(result)

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"impossible_values_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                min_violation_rate=min_violation_rate,
                findings=findings,
                suppressed=suppressed,
                skipped_rules=skipped_rules,
            ),
            encoding="utf-8",
        )

        return TaskResult(
            ok=True,
            message="Impossible values report written",
            findings={
                "rules_evaluated": len(rules_cfg),
                "rules_with_violations": len(findings),
                "suppressed_by_learnings": len(suppressed),
            },
            report_path=report_path,
            raw_findings={
                "impossible_values": findings,
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
    min_violation_rate: float,
    findings: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    skipped_rules: list[str],
) -> str:
    lines = [
        "# Impossible values quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {sample_rows:,}",
        f"- **Min violation rate to report:** {min_violation_rate:.1%}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Rules with violations | {len(findings)} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        f"| Rules skipped (column absent or unknown type) | {len(skipped_rules)} |",
        "",
    ]

    if findings:
        lines.extend([
            "## Rule violations",
            "",
            "| Rule | Type | Column(s) | Violations | Rate | Sample violating values |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ])
        for f in findings:
            sample_str = ", ".join(f"`{v}`" for v in f["sample_values"])
            note = f" _(prior note: {f['prior_note']})_" if f.get("prior_note") else ""
            lines.append(
                f"| **{f['label']}** | {f['rule_type']} | `{f['column']}` "
                f"| {f['violation_count']:,} | {f['violation_rate']:.1%} "
                f"| {sample_str}{note} |"
            )
        lines.append("")
        lines.extend([
            "## Violation details",
            "",
        ])
        for f in findings:
            sample_str = ", ".join(f"`{v}`" for v in f["sample_values"])
            lines.extend([
                f"### {f['label']}",
                "",
                f"- **Rule type:** {f['rule_type']}",
                f"- **Column(s):** `{f['column']}`",
                f"- **Description:** {f['description']}",
                f"- **Violations:** {f['violation_count']:,} of {f['denominator']:,} "
                f"evaluable rows ({f['violation_rate']:.1%})",
                f"- **Sample values:** {sample_str}",
                "",
            ])
    else:
        lines.extend(["## Rule violations", "", "_No violations found across all configured rules._", ""])

    if suppressed:
        lines.extend([
            "## Suppressed by prior learnings",
            "",
            "| Rule label | Issue type |",
            "| --- | --- |",
        ])
        for s in suppressed:
            lines.append(f"| `{s['label']}` | {s['issue_type']} |")
        lines.append("")
    else:
        lines.extend([
            "## Suppressed by prior learnings",
            "",
            "_None — no findings have been marked as false positives yet._",
            "",
        ])

    return "\n".join(lines)
