from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.tasks.base_task import BaseTask, RunContext, TaskResult
from knowledge.knowledge_base import KnowledgeBase


class MissingValuesTask(BaseTask):
    """Profile column-level missingness and flag always/high-null columns."""

    @property
    def name(self) -> str:
        return "missing_values"

    def run(self, ctx: RunContext) -> TaskResult:
        cfg = ctx.config.get("missing_values", {})
        dd_cfg = ctx.config.get("data_dictionary", {})

        csv_path = (ctx.base_dir / dd_cfg["csv_path"]).resolve()
        sample_rows = int(dd_cfg.get("sample_rows", 50_000))
        high_null_threshold = float(cfg.get("high_null_threshold", 0.50))
        always_null_threshold = float(cfg.get("always_null_threshold", 1.00))
        reports_dir = (ctx.base_dir / cfg.get("reports_dir", "outputs/reports")).resolve()
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
        total_rows = len(df)

        null_profile: list[dict[str, Any]] = []
        always_null: list[str] = []
        high_null: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []

        for col in df.columns:
            series = df[col]
            null_count = int(series.isna().sum())
            null_rate = (null_count / total_rows) if total_rows else 0.0
            null_profile.append(
                {
                    "column": col,
                    "null_count": null_count,
                    "null_rate": null_rate,
                    "dtype": str(series.dtype),
                }
            )

            if null_rate >= always_null_threshold:
                issue_type = "always_null"
                if kb.is_false_positive(col, issue_type):
                    suppressed.append({"column": col, "issue_type": issue_type})
                    continue
                always_null.append(col)
                continue

            if null_rate >= high_null_threshold:
                issue_type = "high_null"
                if kb.is_false_positive(col, issue_type):
                    suppressed.append({"column": col, "issue_type": issue_type})
                    continue
                high_null.append(
                    {
                        "column": col,
                        "null_rate": null_rate,
                        "note": kb.get_note(col, issue_type) or "",
                    }
                )

        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"missing_values_report_{stamp}.md"
        report_path.write_text(
            _render_report(
                csv_path=csv_path,
                sample_rows=sample_rows,
                high_null_threshold=high_null_threshold,
                always_null_threshold=always_null_threshold,
                null_profile=sorted(null_profile, key=lambda row: row["null_rate"], reverse=True),
                always_null=sorted(always_null),
                high_null=sorted(high_null, key=lambda row: row["null_rate"], reverse=True),
                suppressed=suppressed,
            ),
            encoding="utf-8",
        )

        return TaskResult(
            ok=True,
            message="Missing values report written",
            findings={
                "columns_profiled": len(null_profile),
                "always_null_count": len(always_null),
                "high_null_count": len(high_null),
                "suppressed_by_learnings_count": len(suppressed),
            },
            report_path=report_path,
            raw_findings={
                "null_profile": null_profile,
                "always_null": always_null,
                "high_null": high_null,
                "kb_path": str(kb_path),
            },
        )


def _render_report(
    *,
    csv_path: Path,
    sample_rows: int,
    high_null_threshold: float,
    always_null_threshold: float,
    null_profile: list[dict[str, Any]],
    always_null: list[str],
    high_null: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
) -> str:
    lines = [
        "# Missing values quality report",
        "",
        f"- **CSV:** `{csv_path}`",
        f"- **Sample rows:** {sample_rows}",
        f"- **High-null threshold:** {high_null_threshold:.0%}",
        f"- **Always-null threshold:** {always_null_threshold:.0%}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Columns profiled | {len(null_profile)} |",
        f"| Always-null columns | {len(always_null)} |",
        f"| High-null columns | {len(high_null)} |",
        f"| Findings suppressed by prior learnings | {len(suppressed)} |",
        "",
        "## Null profile",
        "",
    ]
    if null_profile:
        lines.append("| Column | Null count | Null rate | Dtype |")
        lines.append("| --- | ---: | ---: | --- |")
        for row in null_profile:
            lines.append(
                f"| `{row['column']}` | {row['null_count']} | {row['null_rate']:.1%} | `{row['dtype']}` |"
            )
    else:
        lines.append("_None._")

    lines.extend(["", "## Always-null columns", ""])
    if always_null:
        lines.append("| Column |")
        lines.append("| --- |")
        for col in always_null:
            lines.append(f"| `{col}` |")
    else:
        lines.append("_None._")

    lines.extend(["", "## High-null columns", ""])
    if high_null:
        lines.append("| Column | Null rate | Prior note |")
        lines.append("| --- | ---: | --- |")
        for row in high_null:
            note = row["note"] if row["note"] else ""
            lines.append(f"| `{row['column']}` | {row['null_rate']:.1%} | {note} |")
    else:
        lines.append("_None._")

    lines.extend(["", "## Suppressed by prior learnings", ""])
    if suppressed:
        lines.append("| Column | Issue type |")
        lines.append("| --- | --- |")
        for row in suppressed:
            lines.append(f"| `{row['column']}` | {row['issue_type']} |")
    else:
        lines.append("_None — no findings have been marked as false positives yet._")
    lines.append("")
    return "\n".join(lines)
