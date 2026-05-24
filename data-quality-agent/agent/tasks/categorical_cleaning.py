from __future__ import annotations

import difflib
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from agent.tasks.llm_dedup import assess_pairs as _llm_assess_pairs
from knowledge.knowledge_base import KnowledgeBase

_SAMPLE_SIZE = 5
_DOUBLE_SPACE = re.compile(r" {2,}")


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise(value: str) -> str:
    """Casefold, strip edges, collapse internal spaces."""
    return _DOUBLE_SPACE.sub(" ", value.strip().casefold())


# ---------------------------------------------------------------------------
# Per-column checks
# ---------------------------------------------------------------------------

def _case_variant_groups(
    value_counts: Counter,
) -> list[dict[str, Any]]:
    """Group values that are identical after normalisation.

    Returns groups that have more than one distinct raw form — these are
    case / whitespace variants of the same concept.
    Each group includes a suggested canonical name (the most frequent member).
    """
    norm_to_originals: dict[str, list[str]] = {}
    for v in value_counts:
        norm = _normalise(v)
        norm_to_originals.setdefault(norm, []).append(v)

    groups = []
    for norm, originals in norm_to_originals.items():
        if len(originals) <= 1:
            continue
        # Sort by frequency descending — most common becomes canonical.
        originals_sorted = sorted(originals, key=lambda v: value_counts[v], reverse=True)
        total_count = sum(value_counts[v] for v in originals)
        groups.append(
            {
                "canonical": originals_sorted[0],
                "variants": originals_sorted,
                "total_count": total_count,
            }
        )
    return sorted(groups, key=lambda g: g["total_count"], reverse=True)


def _fuzzy_pairs(
    value_counts: Counter,
    threshold: float,
    exclude_norms: set[str],
) -> list[dict[str, Any]]:
    """Find pairs of values that are similar but not identical after normalisation.

    Pairs that are already case/whitespace variants of each other (same
    normalised form) are excluded — they are handled by _case_variant_groups.

    Only values whose normalised form is NOT already in exclude_norms are
    considered (those are the ones already grouped as case variants).
    """
    # Keep one representative per normalised form (most frequent).
    norm_to_best: dict[str, str] = {}
    for v in value_counts:
        norm = _normalise(v)
        if norm in exclude_norms:
            continue
        if norm not in norm_to_best or value_counts[v] > value_counts[norm_to_best[norm]]:
            norm_to_best[norm] = v

    candidates = list(norm_to_best.values())
    pairs = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            ratio = difflib.SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()
            if ratio >= threshold:
                # Put the more frequent value first.
                if value_counts[b] > value_counts[a]:
                    a, b = b, a
                pairs.append(
                    {
                        "a": a,
                        "b": b,
                        "similarity": round(ratio, 3),
                        "count_a": value_counts[a],
                        "count_b": value_counts[b],
                    }
                )
    return sorted(pairs, key=lambda p: p["similarity"], reverse=True)


def _low_frequency(
    value_counts: Counter,
    total_rows: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Return values whose frequency is below the threshold."""
    results = []
    for v, count in value_counts.items():
        rate = count / total_rows if total_rows else 0.0
        if rate < threshold:
            results.append({"value": v, "count": count, "rate": rate})
    return sorted(results, key=lambda r: r["count"])


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class CategoricalCleaningTask(BaseTask):
    """Surface categorical columns with variant labels, near-duplicates, or rare values."""

    @property
    def name(self) -> str:
        return "categorical_cleaning"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("categorical_cleaning", {})
        dd_cfg = ctx.config.get("data_dictionary", {})
        llm_cfg = ctx.config.get("llm_dedup", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        max_cardinality = int(cfg.get("max_cardinality", 50))
        similarity_threshold = float(cfg.get("similarity_threshold", 0.85))
        low_freq_threshold = float(cfg.get("low_frequency_threshold", 0.01))
        include_cols: list[str] = [c.casefold() for c in cfg.get("columns_include", [])]
        exclude_cols: set[str] = {c.casefold() for c in cfg.get("columns_exclude", [])}
        reports_dir = (
            ctx.base_dir / cfg.get("reports_dir", dd_cfg.get("reports_dir", "outputs/reports"))
        ).resolve()
        kb_path = (
            ctx.base_dir / cfg.get("knowledge_base_path", "knowledge/learnings.json")
        ).resolve()

        # Load data dictionary definitions for LLM context (best-effort).
        dict_definitions: dict[str, str] = {}
        dict_path_raw = dd_cfg.get("dictionary_path", "")
        if dict_path_raw:
            dict_file = (ctx.base_dir / dict_path_raw).resolve()
            if dict_file.is_file():
                dict_definitions = _parse_dict_definitions(dict_file.read_text(encoding="utf-8"))

        if ctx.sample_df is not None:
            df = ctx.sample_df
        else:
            if not csv_path.is_file():
                return TaskResult(ok=False, message=f"CSV not found: {csv_path}")
            df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

        kb = KnowledgeBase(kb_path)
        total_rows = len(df)
        findings: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        skipped: list[str] = []

        for col in df.columns:
            col_cf = col.casefold()

            # Apply include/exclude filters.
            if exclude_cols and col_cf in exclude_cols:
                skipped.append(f"{col} (excluded)")
                continue
            if include_cols and col_cf not in include_cols:
                continue

            series = df[col].dropna().astype(str)
            if series.empty:
                continue

            # Only string-like columns.
            if df[col].dtype != object:
                continue

            n_distinct = series.nunique()
            if n_distinct > max_cardinality:
                skipped.append(f"{col} (cardinality {n_distinct} > max {max_cardinality})")
                continue
            if n_distinct <= 1:
                continue  # Nothing to compare.

            counts = Counter(series.tolist())

            # --- Case / whitespace variant groups ---
            variant_groups = _case_variant_groups(counts)
            # Normalised forms that are already grouped — exclude from fuzzy check.
            variant_norms: set[str] = set()
            for g in variant_groups:
                variant_norms.add(_normalise(g["canonical"]))

            # --- Fuzzy near-duplicate pairs ---
            fuzzy = _fuzzy_pairs(counts, similarity_threshold, variant_norms)

            # --- LLM semantic assessment (optional) ---
            if fuzzy and llm_cfg.get("enabled", False):
                col_def = dict_definitions.get(col.casefold(), "")
                fuzzy = _llm_assess_pairs(
                    pairs=fuzzy,
                    column=col,
                    dict_definition=col_def,
                    cfg=llm_cfg,
                )

            # --- Low-frequency categories ---
            low_freq = _low_frequency(counts, total_rows, low_freq_threshold)

            has_variants = len(variant_groups) > 0
            has_fuzzy = len(fuzzy) > 0
            has_low_freq = len(low_freq) > 0

            if not (has_variants or has_fuzzy or has_low_freq):
                continue

            # KB suppression — one entry per column covers all finding types.
            if kb.is_false_positive(col, "categorical_cleaning"):
                suppressed.append({"column": col, "issue_type": "categorical_cleaning"})
                continue

            prior_note = kb.get_note(col, "categorical_cleaning")
            finding: dict[str, Any] = {
                "column": col,
                "distinct_values": n_distinct,
                "has_case_variants": has_variants,
                "has_fuzzy_pairs": has_fuzzy,
                "has_low_frequency": has_low_freq,
                "case_variant_groups": variant_groups,
                "fuzzy_pairs": fuzzy,
                "low_frequency": low_freq,
                "value_counts": dict(counts.most_common()),
            }
            if prior_note:
                finding["prior_note"] = prior_note
            findings.append(finding)

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"categorical_cleaning_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                max_cardinality=max_cardinality,
                similarity_threshold=similarity_threshold,
                low_freq_threshold=low_freq_threshold,
                findings=findings,
                suppressed=suppressed,
                skipped=skipped,
            ),
            encoding="utf-8",
        )

        return TaskResult(
            ok=True,
            message="Categorical cleaning report written",
            findings={
                "columns_analysed": len(findings) + len(suppressed),
                "columns_with_case_variants": sum(1 for f in findings if f["has_case_variants"]),
                "columns_with_fuzzy_pairs": sum(1 for f in findings if f["has_fuzzy_pairs"]),
                "columns_with_low_frequency": sum(1 for f in findings if f["has_low_frequency"]),
                "suppressed_by_learnings": len(suppressed),
            },
            report_path=report_path,
            raw_findings={
                "categorical_findings": findings,
                "suppressed": suppressed,
                "kb_path": str(kb_path),
            },
        )


# ---------------------------------------------------------------------------
# Dictionary helper
# ---------------------------------------------------------------------------

def _parse_dict_definitions(md_text: str) -> dict[str, str]:
    """Extract {variable_casefold: definition} from a Markdown pipe table.

    Looks for a header row containing 'Variable' and 'Definition' columns
    and reads subsequent data rows.  Returns an empty dict on any parse error.
    """
    definitions: dict[str, str] = {}
    var_idx: int | None = None
    def_idx: int | None = None

    for line in md_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]

        # Locate header row
        if var_idx is None:
            lower_cells = [c.casefold() for c in cells]
            if "variable" in lower_cells:
                var_idx = lower_cells.index("variable")
                if "definition" in lower_cells:
                    def_idx = lower_cells.index("definition")
            continue

        # Skip separator row (---|---)
        if all(set(c) <= {"-", " ", ":"} for c in cells if c):
            continue

        if len(cells) <= var_idx:
            continue
        var_name = cells[var_idx].casefold()
        definition = cells[def_idx].strip() if def_idx is not None and len(cells) > def_idx else ""
        if var_name:
            definitions[var_name] = definition

    return definitions


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _render_report(
    *,
    csv_path: Path,
    sample_rows: int,
    max_cardinality: int,
    similarity_threshold: float,
    low_freq_threshold: float,
    findings: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    skipped: list[str],
) -> str:
    lines = [
        "# Categorical cleaning quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {sample_rows:,}",
        f"- **Max cardinality analysed:** {max_cardinality}",
        f"- **Fuzzy similarity threshold:** {similarity_threshold}",
        f"- **Low-frequency threshold:** {low_freq_threshold:.1%}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Columns with case / whitespace variants | "
        f"{sum(1 for f in findings if f['has_case_variants'])} |",
        f"| Columns with fuzzy near-duplicate pairs | "
        f"{sum(1 for f in findings if f['has_fuzzy_pairs'])} |",
        f"| Columns with low-frequency categories | "
        f"{sum(1 for f in findings if f['has_low_frequency'])} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        f"| Columns skipped (cardinality or exclusion) | {len(skipped)} |",
        "",
    ]

    if not findings:
        lines.extend(["_No categorical cleaning issues found._", ""])
        return "\n".join(lines)

    for f in findings:
        col = f["column"]
        note = f" _(prior note: {f['prior_note']})_" if f.get("prior_note") else ""
        lines.extend([
            f"## `{col}`{note}",
            "",
            f"- **Distinct values:** {f['distinct_values']}",
            f"- **Value distribution (top {_SAMPLE_SIZE}):** "
            + ", ".join(
                f"`{v}` ({c:,})"
                for v, c in list(f["value_counts"].items())[:_SAMPLE_SIZE]
            ),
            "",
        ])

        # Case variants
        if f["has_case_variants"]:
            lines.extend(["### Case / whitespace variant groups", ""])
            lines.append(
                "_Values that are identical after case-folding and whitespace normalisation. "
                "Consider standardising to the canonical form._"
            )
            lines.append("")
            lines.extend([
                "| Canonical (most frequent) | All variants | Total occurrences |",
                "| --- | --- | ---: |",
            ])
            for g in f["case_variant_groups"]:
                variants_str = ", ".join(f"`{v}`" for v in g["variants"])
                lines.append(
                    f"| `{g['canonical']}` | {variants_str} | {g['total_count']:,} |"
                )
            lines.append("")

        # Fuzzy pairs
        if f["has_fuzzy_pairs"]:
            lines.extend(["### Fuzzy near-duplicate pairs", ""])
            lines.append(
                f"_Pairs with string similarity ≥ {similarity_threshold}. "
                "These may be the same concept entered differently — verify before merging._"
            )
            lines.append("")
            has_llm = any("llm_verdict" in p for p in f["fuzzy_pairs"])
            if has_llm:
                lines.extend([
                    "| Value A | Value B | Similarity | Count A | Count B | LLM verdict | Reasoning |",
                    "| --- | --- | ---: | ---: | ---: | --- | --- |",
                ])
                _VERDICT_EMOJI = {"same": "✅ same", "different": "❌ different", "uncertain": "❓ uncertain"}
                for p in f["fuzzy_pairs"]:
                    verdict = _VERDICT_EMOJI.get(p.get("llm_verdict", ""), "")
                    reasoning = p.get("llm_reasoning", "")
                    lines.append(
                        f"| `{p['a']}` | `{p['b']}` | {p['similarity']:.0%} "
                        f"| {p['count_a']:,} | {p['count_b']:,} | {verdict} | {reasoning} |"
                    )
            else:
                lines.extend([
                    "| Value A | Value B | Similarity | Count A | Count B |",
                    "| --- | --- | ---: | ---: | ---: |",
                ])
                for p in f["fuzzy_pairs"]:
                    lines.append(
                        f"| `{p['a']}` | `{p['b']}` | {p['similarity']:.0%} "
                        f"| {p['count_a']:,} | {p['count_b']:,} |"
                    )
            lines.append("")

        # Low-frequency
        if f["has_low_frequency"]:
            lines.extend(["### Low-frequency categories", ""])
            lines.append(
                f"_Values appearing in fewer than {low_freq_threshold:.1%} of rows. "
                "Consider merging into an 'Other' bucket or investigating if these are data entry errors._"
            )
            lines.append("")
            lines.extend([
                "| Value | Count | Rate |",
                "| --- | ---: | ---: |",
            ])
            for lf in f["low_frequency"]:
                lines.append(f"| `{lf['value']}` | {lf['count']:,} | {lf['rate']:.2%} |")
            lines.append("")

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
