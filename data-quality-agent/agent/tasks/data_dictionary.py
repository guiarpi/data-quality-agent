from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from knowledge.knowledge_base import KnowledgeBase

# Maps normalized dictionary "Data Type" labels to internal categories
_TYPE_KEYWORDS: dict[str, str] = {
    "boolean": "boolean",
    "integer": "integer",
    "number": "integer",
    "timestamp": "timestamp",
    "string": "string",
    "text": "string",
}

_BOOL_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_BOOL_FALSE = frozenset({"false", "f", "no", "n", "0"})


def _normalize_dict_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def _normalize_for_match(name: str, case_insensitive: bool) -> str:
    n = _normalize_dict_key(name)
    return n.casefold() if case_insensitive else n


def parse_markdown_dictionary(path: Path) -> dict[str, dict[str, str]]:
    """Parse a markdown pipe table with Variable, Definition, Data Type columns."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        var, definition, data_type = cells[0], cells[1], cells[2]
        if not var or var.replace("-", "").replace(":", "") == "":
            continue
        if var.casefold() == "variable" or "variable" == var.casefold():
            continue
        if "---" in var and set(var) <= {"-", ":", " "}:
            continue
        key = _normalize_dict_key(var)
        entries[key] = {"definition": definition, "data_type": data_type}
    return entries


def _classify_expected(data_type_cell: str) -> str | None:
    s = data_type_cell.lower().replace("/", " ")
    for kw, cat in _TYPE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", s):
            return cat
    return None


def _check_boolean(series: pd.Series, threshold: float) -> tuple[bool, str]:
    s = series.dropna()
    if s.empty:
        return True, "all null (handled by missing values task)"
    as_str = s.astype(str).str.strip().str.casefold()
    ok_mask = as_str.isin(_BOOL_TRUE | _BOOL_FALSE) | as_str.eq("")
    bad_rate = 1.0 - (ok_mask.sum() / len(as_str))
    if bad_rate >= threshold:
        sample = as_str[~ok_mask].head(5).tolist()
        return False, f"{bad_rate:.1%} non-boolean-like values; examples: {sample}"
    return True, f"pandas dtype `{series.dtype}`; {bad_rate:.1%} non-boolean-like"


def _check_integer(series: pd.Series, threshold: float) -> tuple[bool, str]:
    s = series.dropna()
    if s.empty:
        return True, "all null (handled by missing values task)"
    if pd.api.types.is_integer_dtype(series):
        return True, f"pandas dtype `{series.dtype}`"
    if pd.api.types.is_float_dtype(series):
        frac_int = (s == s.round()).mean()
        if frac_int >= (1.0 - threshold):
            return True, f"pandas dtype `{series.dtype}` (values are whole numbers)"
        return False, f"pandas dtype `{series.dtype}` with many non-integer floats"
    num = pd.to_numeric(s, errors="coerce")
    fail_rate = num.isna().sum() / len(s)
    if fail_rate >= threshold:
        sample = s[num.isna()].astype(str).head(5).tolist()
        return False, f"{fail_rate:.1%} non-numeric; examples: {sample}"
    return True, f"object column; {100 * (1 - fail_rate):.1f}% parseable as numeric"


def _check_timestamp(series: pd.Series, threshold: float) -> tuple[bool, str]:
    s = series.dropna()
    if s.empty:
        return True, "all null (handled by missing values task)"
    # utc=True avoids object-dtype results (and a FutureWarning) when the
    # column mixes UTC offsets; we only measure parse success rate here.
    try:
        parsed = pd.to_datetime(s, errors="coerce", format="mixed", utc=True)
    except (TypeError, ValueError):
        parsed = pd.to_datetime(s, errors="coerce", utc=True)
    fail_rate = parsed.isna().sum() / len(s)
    if fail_rate >= threshold:
        sample = s[parsed.isna()].astype(str).head(5).tolist()
        return False, f"{fail_rate:.1%} unparseable as datetime; examples: {sample}"
    return True, f"{fail_rate:.1%} failed parse; pandas inferred from sample"


def _check_string(series: pd.Series) -> tuple[bool, str]:
    if series.notna().sum() == 0:
        return True, "all null (handled by missing values task)"
    return True, f"pandas dtype `{series.dtype}`; non-null count {series.notna().sum()}"


class DataDictionaryTask(BaseTask):
    """Compare CSV columns to a markdown data dictionary and profile types."""

    @property
    def name(self) -> str:
        return "data_dictionary"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("data_dictionary", {})
        csv_path = (ctx.base_dir / cfg["csv_path"]).resolve()
        dict_path = (ctx.base_dir / cfg["dictionary_path"]).resolve()
        sample_rows = int(cfg.get("sample_rows", 50_000))
        case_insensitive = bool(cfg.get("case_insensitive_column_match", True))
        inconsistency_threshold = float(cfg.get("inconsistency_threshold", 0.05))
        reports_dir = (ctx.base_dir / cfg.get("reports_dir", "outputs/reports")).resolve()

        if not csv_path.is_file():
            return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
        if not dict_path.is_file():
            return TaskResult(ok=False, message=f"Dictionary not found: {dict_path}")

        kb_path = (ctx.base_dir / cfg.get("knowledge_base_path", "knowledge/learnings.json")).resolve()
        kb = KnowledgeBase(kb_path)

        dict_entries = parse_markdown_dictionary(dict_path)
        dict_by_match = {
            _normalize_for_match(k, case_insensitive): (k, v) for k, v in dict_entries.items()
        }

        df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)
        csv_columns = list(df.columns)

        suppressed: list[dict[str, str]] = []

        missing_defs: list[str] = []
        for col in csv_columns:
            mk = _normalize_for_match(col, case_insensitive)
            if mk not in dict_by_match:
                if kb.is_false_positive(col, "missing_definition"):
                    suppressed.append({"column": col, "issue_type": "missing_definition"})
                else:
                    missing_defs.append(col)

        extra_dict_vars: list[str] = []
        csv_match_keys = {_normalize_for_match(c, case_insensitive) for c in csv_columns}
        for dk in dict_entries:
            if _normalize_for_match(dk, case_insensitive) not in csv_match_keys:
                if kb.is_false_positive(dk, "dictionary_only"):
                    suppressed.append({"column": dk, "issue_type": "dictionary_only"})
                else:
                    extra_dict_vars.append(dk)

        inconsistencies: list[dict[str, Any]] = []
        for col in csv_columns:
            mk = _normalize_for_match(col, case_insensitive)
            if mk not in dict_by_match:
                continue
            _canonical, meta = dict_by_match[mk]
            expected = _classify_expected(meta["data_type"])
            if expected is None:
                issue_type = "unmappable_type"
                if kb.is_false_positive(col, issue_type):
                    suppressed.append({"column": col, "issue_type": issue_type})
                    continue
                notes = "Could not map dictionary Data Type to boolean/integer/timestamp/string"
                prior_note = kb.get_note(col, issue_type)
                if prior_note:
                    notes += f" [Prior note: {prior_note}]"
                inconsistencies.append(
                    {
                        "column": col,
                        "expected_type": meta["data_type"],
                        "category": None,
                        "ok": None,
                        "notes": notes,
                    }
                )
                continue
            series = df[col]
            ok, obs = True, ""
            if expected == "boolean":
                ok, obs = _check_boolean(series, inconsistency_threshold)
            elif expected == "integer":
                ok, obs = _check_integer(series, inconsistency_threshold)
            elif expected == "timestamp":
                ok, obs = _check_timestamp(series, inconsistency_threshold)
            else:
                ok, obs = _check_string(series)
            if not ok:
                issue_type = "type_mismatch"
                if kb.is_false_positive(col, issue_type):
                    suppressed.append({"column": col, "issue_type": issue_type})
                    continue
                prior_note = kb.get_note(col, issue_type)
                if prior_note:
                    obs += f" [Prior note: {prior_note}]"
                inconsistencies.append(
                    {
                        "column": col,
                        "expected_type": meta["data_type"],
                        "category": expected,
                        "ok": False,
                        "notes": obs,
                    }
                )

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"data_dictionary_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                dict_path=dict_path,
                sample_rows=sample_rows,
                missing_defs=sorted(missing_defs),
                extra_dict_vars=sorted(extra_dict_vars),
                inconsistencies=inconsistencies,
                suppressed=suppressed,
            ),
            encoding="utf-8",
        )

        return TaskResult(
            ok=True,
            message="Report written",
            findings={
                "missing_definition_count": len(missing_defs),
                "dictionary_only_count": len(extra_dict_vars),
                "inconsistency_count": len(inconsistencies),
                "suppressed_by_learnings_count": len(suppressed),
            },
            report_path=report_path,
            raw_findings={
                "missing_defs": sorted(missing_defs),
                "extra_dict_vars": sorted(extra_dict_vars),
                "inconsistencies": inconsistencies,
                "kb_path": str(kb_path),
                "dict_variables": list(dict_entries.keys()),
                "csv_columns": csv_columns,
                "dict_path": str(dict_path),
            },
        )


def _render_report(
    *,
    csv_path: Path,
    dict_path: Path,
    sample_rows: int,
    missing_defs: list[str],
    extra_dict_vars: list[str],
    inconsistencies: list[dict[str, Any]],
    suppressed: list[dict[str, str]],
) -> str:
    lines = [
        "# Data dictionary quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Dictionary:** `{dict_path}`",
        f"- **Sample rows:** {sample_rows}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"| --- | ---: |",
        f"| CSV columns missing a dictionary definition | {len(missing_defs)} |",
        f"| Dictionary variables not present in CSV | {len(extra_dict_vars)} |",
        f"| Columns with type/data inconsistencies | {len(inconsistencies)} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        "",
        "## Missing definitions",
        "",
    ]
    if missing_defs:
        lines.append("| Column |")
        lines.append("| --- |")
        for c in missing_defs:
            lines.append(f"| `{c}` |")
    else:
        lines.append("_None._")
    lines.extend(["", "## Dictionary variables not in CSV", ""])
    if extra_dict_vars:
        lines.append("| Variable |")
        lines.append("| --- |")
        for v in extra_dict_vars:
            lines.append(f"| `{v}` |")
    else:
        lines.append("_None._")
    lines.extend(["", "## Inconsistencies", ""])
    if inconsistencies:
        lines.append("| Column | Expected (dictionary) | Category | Notes |")
        lines.append("| --- | --- | --- | --- |")
        for row in inconsistencies:
            cat = row.get("category")
            cat_s = "" if cat is None else str(cat)
            lines.append(
                f"| `{row['column']}` | {row['expected_type']} | {cat_s} | {row['notes']} |"
            )
    else:
        lines.append("_None._")
    lines.extend(["", "## Suppressed by prior learnings", ""])
    if suppressed:
        lines.append("| Column | Issue type |")
        lines.append("| --- | --- |")
        for s in suppressed:
            lines.append(f"| `{s['column']}` | {s['issue_type']} |")
    else:
        lines.append("_None — no findings have been marked as false positives yet._")
    lines.append("")
    return "\n".join(lines)
