from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Any

from knowledge.knowledge_base import KnowledgeBase

# Maps short single-character inputs to resolution labels.
_RESOLUTION_KEYS = {
    "f": "false_positive",
    "c": "confirmed_issue",
    "k": "known_exception",
}

_DIVIDER = "─" * 60


def _find_close_matches(
    name: str, candidates: list[str], n: int = 3, cutoff: float = 0.7
) -> list[tuple[str, float]]:
    """Return up to n candidates that are similar to name, with scores.

    Matching is case-insensitive. Results are returned with the original
    (un-normalised) candidate string so the display matches the source.
    """
    name_cf = name.casefold()
    cf_map = {c.casefold(): c for c in candidates}
    close = difflib.get_close_matches(name_cf, list(cf_map.keys()), n=n, cutoff=cutoff)
    return [
        (cf_map[m], difflib.SequenceMatcher(None, name_cf, m).ratio())
        for m in close
    ]


def _apply_dictionary_fix(dict_path: Path, old_name: str, new_name: str) -> bool:
    """Rename a variable entry in the markdown dictionary file.

    Finds the pipe-table row whose first cell matches old_name (case-insensitive),
    replaces just that cell with new_name, and writes the file back.
    Everything else — definition, data type, whitespace padding — is preserved.

    Returns True if a change was made, False if the entry was not found.
    """
    text = dict_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    new_lines = []
    changed = False

    for line in lines:
        if line.strip().startswith("|"):
            cells = line.split("|")
            if len(cells) > 1:
                cell = cells[1]
                # Strip bold markers and whitespace to get the bare name.
                cell_name = cell.strip().strip("*").strip()
                if cell_name.casefold() == old_name.casefold():
                    # Replace only the name, preserving surrounding whitespace.
                    cells[1] = cell.replace(cell_name, new_name)
                    line = "|".join(cells)
                    changed = True

        new_lines.append(line)

    if changed:
        dict_path.write_text("".join(new_lines), encoding="utf-8")

    return changed


def _prompt_resolution(*, show_fix_option: bool, fix_label: str = "") -> str | None:
    """Ask the user to pick a resolution.

    Returns a resolution string, 'skip', 'fix_dictionary', or None to quit.
    The [m] fix-dictionary option is only shown when show_fix_option is True.
    """
    print()
    print("  Resolution:")
    print("    [f] false positive   — suppress in future runs")
    print("    [c] confirmed issue  — real problem, keep flagging")
    print("    [k] known exception  — quirk to document, not suppressed")
    if show_fix_option:
        print(f"    [m] fix dictionary   — {fix_label}")
    print("    [s] skip             — decide later")
    print("    [q] quit review      — stop here, save progress so far")
    print()

    valid = set(_RESOLUTION_KEYS) | {"s", "q"}
    if show_fix_option:
        valid.add("m")

    while True:
        try:
            raw = input("  Your choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw == "q":
            return None
        if raw == "s":
            return "skip"
        if raw == "m" and show_fix_option:
            return "fix_dictionary"
        if raw in _RESOLUTION_KEYS:
            return _RESOLUTION_KEYS[raw]
        print(f"  Please enter one of: {', '.join(sorted(valid))}.")


def _prompt_note() -> str:
    """Optionally ask for a free-text note. Returns empty string if skipped."""
    try:
        note = input("  Add a note (optional — press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        note = ""
    return note


def _already_reviewed(kb: KnowledgeBase, column: str, issue_type: str) -> bool:
    """Return True if this (column, issue_type) already has any learning recorded."""
    for learning in kb.all_learnings():
        if (
            learning.get("column_name") == column
            and learning.get("issue_type") == issue_type
        ):
            return True
    return False


def _pick_suggestion(suggestions: list[tuple[str, float]]) -> str | None:
    """If there are multiple suggestions, ask the user to pick one.
    Returns the chosen original name, or None if the user declines."""
    if len(suggestions) == 1:
        return suggestions[0][0]

    print()
    print("  Multiple matches found — which one is correct?")
    for i, (orig, score) in enumerate(suggestions, start=1):
        print(f"    [{i}] {orig}  ({score:.0%} similar)")
    print("    [n] none of these")
    print()

    while True:
        try:
            raw = input("  Your choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw == "n":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(suggestions):
            return suggestions[int(raw) - 1][0]
        print(f"  Please enter a number between 1 and {len(suggestions)}, or n.")


def _review_finding(
    *,
    kb: KnowledgeBase,
    index: int,
    total: int,
    task_name: str,
    column: str | None,
    issue_type: str,
    expected_type: str,
    detail: str,
    context: dict[str, Any],
) -> bool:
    """Show one finding and collect the human's response.
    Returns False if the reviewer chose to quit, True otherwise."""
    print()
    print(_DIVIDER)
    print(f"  Finding {index} of {total}  —  {issue_type}")
    print(f"  Task     : {task_name}")
    print(f"  Column   : {column or '(n/a)'}")
    print(f"  Expected : {expected_type}")
    print(f"  Detail   : {detail}")

    # Compute fuzzy suggestions and determine whether to offer the [m] option.
    suggestions: list[tuple[str, float]] = []
    fix_label = ""

    if column and issue_type == "missing_definition":
        suggestions = _find_close_matches(column, context.get("dict_variables", []))
        if suggestions:
            print()
            print("  Possible matches in the dictionary:")
            for orig, score in suggestions:
                print(f"    → {orig}  ({score:.0%} similar)")
            print("  This may be a naming mismatch — verify before marking as confirmed issue.")
            # Build the label for [m] using the best match.
            best = suggestions[0][0]
            fix_label = f"rename '{best}' → '{column}' in the dictionary"

    elif column and issue_type == "dictionary_only":
        suggestions = _find_close_matches(column, context.get("csv_columns", []))
        if suggestions:
            print()
            print("  Possible matches in the CSV:")
            for orig, score in suggestions:
                print(f"    → {orig}  ({score:.0%} similar)")
            print("  This may be a naming mismatch — verify before marking as confirmed issue.")
            best = suggestions[0][0]
            fix_label = f"rename '{column}' → '{best}' in the dictionary"

    already = _already_reviewed(kb, column, issue_type)
    if already:
        existing_note = kb.get_note(column, issue_type)
        print()
        print("  [already reviewed in a prior session]", end="")
        if existing_note:
            print(f"  Note: {existing_note}", end="")
        print()
        try:
            again = input("  Re-review? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return True
        if again != "y":
            return True

    resolution = _prompt_resolution(
        show_fix_option=bool(suggestions),
        fix_label=fix_label,
    )

    if resolution is None:
        return False  # quit signal
    if resolution == "skip":
        return True

    # --- Dictionary fix path ---
    if resolution == "fix_dictionary":
        chosen = _pick_suggestion(suggestions)
        if chosen is None:
            print("  No match selected — skipping.")
            return True

        dict_path = Path(context["dict_path"])

        # Determine old/new names based on issue type.
        if issue_type == "missing_definition":
            # Dictionary has the wrong name; rename it to match the CSV.
            old_name, new_name = chosen, column
        else:
            # dictionary_only: dictionary name is fine; CSV has different name.
            # We still update the dictionary to match the CSV column name.
            old_name, new_name = column, chosen

        print()
        print(f"  Will rename '{old_name}' → '{new_name}'")
        print(f"  in: {dict_path}")
        print()

        try:
            confirm = input("  Confirm? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return True

        if confirm != "y":
            print("  Cancelled.")
            return True

        success = _apply_dictionary_fix(dict_path, old_name, new_name)
        if not success:
            print(f"  Could not find '{old_name}' in the dictionary — no changes made.")
            return True

        note = f"Renamed '{old_name}' → '{new_name}' in dictionary"
        kb.add_learning(
            column_name=column,
            issue_type=issue_type,
            expected_type=expected_type,
            detail=detail,
            resolution="naming_mismatch_fixed",
            note=note,
        )
        print(f"  Dictionary updated. Learning recorded.")
        return True

    # --- Standard resolution path ---
    note = _prompt_note()
    kb.add_learning(
        column_name=column,
        issue_type=issue_type,
        expected_type=expected_type,
        detail=detail,
        resolution=resolution,
        note=note,
    )
    print(f"  Saved — {resolution}.")
    return True


def run_review(raw_findings: dict[str, Any]) -> int:
    """Interactive terminal review loop.

    Iterates through all findings from the last run, shows each one to the
    human, and records their decision in the knowledge base.

    Parameters
    ----------
    raw_findings : dict, either:
        - Legacy flat finding payload
        - Structured payload:
          { "task_order": [...], "task_results": { "<task_name>": { ...raw... } } }

    Returns
    -------
    int : number of new learnings recorded in this session.
    """
    if not sys.stdin.isatty():
        # Non-interactive environment (e.g. piped output, CI). Skip review.
        return 0

    task_results = raw_findings.get("task_results")
    if isinstance(task_results, dict):
        task_order_raw = raw_findings.get("task_order", list(task_results.keys()))
        task_order = [t for t in task_order_raw if t in task_results]
        if not task_order:
            task_order = list(task_results.keys())
        task_payloads = [(task_name, task_results[task_name]) for task_name in task_order]
    else:
        # Backward compatibility for older merged/flat payloads.
        task_payloads: list[tuple[str, dict[str, Any]]] = []
        if any(k in raw_findings for k in ("missing_defs", "extra_dict_vars", "inconsistencies")):
            task_payloads.append(("data_dictionary", raw_findings))
        if any(k in raw_findings for k in ("always_null", "high_null")):
            task_payloads.append(("missing_values", raw_findings))
        if not task_payloads:
            task_payloads.append(("unknown", raw_findings))

    kb_path = None
    for _task_name, payload in task_payloads:
        if payload.get("kb_path"):
            kb_path = payload["kb_path"]
            break
    if not kb_path:
        print("\nNo knowledge-base path in findings payload; skipping review.")
        return 0

    kb = KnowledgeBase(Path(kb_path))

    queue: list[dict[str, Any]] = []

    for task_name, payload in task_payloads:
        for col in payload.get("missing_defs", []):
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": col,
                    "issue_type": "missing_definition",
                    "expected_type": "—",
                    "detail": "Column exists in CSV but has no dictionary entry",
                }
            )

        for var in payload.get("extra_dict_vars", []):
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": var,
                    "issue_type": "dictionary_only",
                    "expected_type": "—",
                    "detail": "Variable defined in dictionary but not found in CSV",
                }
            )

        for row in payload.get("inconsistencies", []):
            issue_type = "unmappable_type" if row.get("category") is None else "type_mismatch"
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["column"],
                    "issue_type": issue_type,
                    "expected_type": row.get("expected_type", "—"),
                    "detail": row.get("notes", ""),
                }
            )

        for col in payload.get("always_null", []):
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": col,
                    "issue_type": "always_null",
                    "expected_type": "—",
                    "detail": "Column is 100% null in the sampled rows",
                }
            )

        for row in payload.get("high_null", []):
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["column"],
                    "issue_type": "high_null",
                    "expected_type": "—",
                    "detail": f"Column is {row['null_rate']:.1%} null (threshold exceeded)",
                }
            )

        for row in payload.get("invalid_entries", []):
            sample_str = ", ".join(row.get("sample_values", []))
            detail = (
                f"{row['description']} — "
                f"{row['violation_count']:,} violation(s) "
                f"({row['violation_rate']:.1%} of evaluable rows); "
                f"examples: {sample_str}"
            )
            if row.get("prior_note"):
                detail += f" [Prior note: {row['prior_note']}]"
            issue_type = (
                "placeholder_value" if row["rule_type"] == "placeholder"
                else "whitespace_anomaly" if row["rule_type"] == "whitespace"
                else "invalid_entry"
            )
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["label"],
                    "issue_type": issue_type,
                    "expected_type": row["rule_type"],
                    "detail": detail,
                }
            )

        for row in payload.get("categorical_findings", []):
            parts = []
            if row["has_case_variants"]:
                n = len(row["case_variant_groups"])
                parts.append(f"{n} case/whitespace variant group(s)")
            if row["has_fuzzy_pairs"]:
                n = len(row["fuzzy_pairs"])
                top = row["fuzzy_pairs"][0]
                parts.append(
                    f"{n} fuzzy pair(s) (top: '{top['a']}' vs '{top['b']}' "
                    f"at {top['similarity']:.0%})"
                )
            if row["has_low_frequency"]:
                n = len(row["low_frequency"])
                parts.append(f"{n} low-frequency value(s)")
            detail = f"{row['distinct_values']} distinct values — " + "; ".join(parts)
            if row.get("prior_note"):
                detail += f" [Prior note: {row['prior_note']}]"
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["column"],
                    "issue_type": "categorical_cleaning",
                    "expected_type": "categorical",
                    "detail": detail,
                }
            )

        for row in payload.get("outliers", []):
            detail = row.get("detail", "")
            if row.get("prior_note"):
                detail += f" [Prior note: {row['prior_note']}]"
            issue_type = (
                "outlier_temporal" if row["check_type"] == "temporal" else "outlier"
            )
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["column"],
                    "issue_type": issue_type,
                    "expected_type": row["check_type"],
                    "detail": detail,
                }
            )

        for row in payload.get("impossible_values", []):
            sample_str = ", ".join(row.get("sample_values", []))
            detail = (
                f"{row['description']} — "
                f"{row['violation_count']:,} violation(s) "
                f"({row['violation_rate']:.1%} of evaluable rows); "
                f"examples: {sample_str}"
            )
            if row.get("prior_note"):
                detail += f" [Prior note: {row['prior_note']}]"
            queue.append(
                {
                    "task_name": task_name,
                    "context": payload,
                    "column": row["label"],
                    "issue_type": "impossible_value",
                    "expected_type": row["rule_type"],
                    "detail": detail,
                }
            )

    if not queue:
        print("\nNo findings to review.")
        return 0

    before_count = len(kb.all_learnings())

    print(f"\n{'=' * 60}")
    print(f"  HUMAN REVIEW — {len(queue)} finding(s) to assess")
    print(f"  Learnings file: {kb_path}")
    print(f"{'=' * 60}")

    current_task = ""
    for i, item in enumerate(queue, start=1):
        if item["task_name"] != current_task:
            current_task = item["task_name"]
            print(f"\n{'-' * 60}")
            print(f"  REVIEW TASK: {current_task}")
            print(f"{'-' * 60}")
        keep_going = _review_finding(
            kb=kb,
            index=i,
            total=len(queue),
            task_name=item["task_name"],
            column=item["column"],
            issue_type=item["issue_type"],
            expected_type=item["expected_type"],
            detail=item["detail"],
            context=item["context"],
        )
        if not keep_going:
            print("\n  Review stopped. Progress saved.")
            break

    after_count = len(kb.all_learnings())
    new_learnings = after_count - before_count

    print()
    print(_DIVIDER)
    summary = kb.summary()
    print(f"  Session complete — {new_learnings} new learning(s) recorded.")
    print(f"  Knowledge base totals: {summary}")
    print(_DIVIDER)
    print()

    return new_learnings
