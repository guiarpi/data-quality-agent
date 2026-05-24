from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

from agent.review.reviewer import run_review
from agent.tasks.base_task import RunContext
from agent.tasks.data_dictionary import DataDictionaryTask
from agent.tasks.data_types import DataTypesTask
from agent.tasks.impossible_values import ImpossibleValuesTask
from agent.tasks.invalid_entries import InvalidEntriesTask
from agent.tasks.missing_values import MissingValuesTask
from agent.tasks.outliers import OutliersTask
from agent.tasks.categorical_cleaning import CategoricalCleaningTask

TaskFactory = Callable[[], object]

TASK_FACTORIES: dict[str, TaskFactory] = {
    "data_dictionary": DataDictionaryTask,
    "missing_values": MissingValuesTask,
    "data_types": DataTypesTask,
    "impossible_values": ImpossibleValuesTask,
    "invalid_entries": InvalidEntriesTask,
    "outliers": OutliersTask,
    "categorical_cleaning": CategoricalCleaningTask,
}


def _default_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _prompt_task_selection(available: list[str]) -> list[str]:
    """Prompt user to choose tasks in interactive terminals.

    Accepted inputs:
      - empty or "all"                -> all tasks
      - "missing_values,data_dictionary" -> include only listed tasks
      - "-data_dictionary"            -> exclude from all tasks
    """
    if not sys.stdin.isatty():
        return available

    print("\n" + "=" * 60)
    print("TASK SELECTION")
    print("=" * 60)
    print("Available tasks:")
    for name in available:
        print(f"  - {name}")
    print()
    print("Choose tasks to run:")
    print("  - Press Enter for all tasks")
    print("  - Type comma-separated task names to include")
    print("  - Type exclusions with '-' prefix (example: -data_dictionary)")
    print()

    while True:
        raw = input("Tasks to run [all]: ").strip()
        if raw == "" or raw.casefold() == "all":
            return available

        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        if not tokens:
            return available

        if all(t.startswith("-") for t in tokens):
            excluded = {t[1:] for t in tokens}
            unknown = sorted(n for n in excluded if n not in available)
            if unknown:
                print(f"Unknown task(s): {', '.join(unknown)}")
                continue
            selected = [name for name in available if name not in excluded]
            if not selected:
                print("Selection excludes all tasks. Please select at least one task.")
                continue
            return selected

        if any(t.startswith("-") for t in tokens):
            print("Use either include list or exclude list, not both.")
            continue

        unknown = sorted(n for n in tokens if n not in available)
        if unknown:
            print(f"Unknown task(s): {', '.join(unknown)}")
            continue
        # Deduplicate while preserving order.
        selected: list[str] = []
        for token in tokens:
            if token not in selected:
                selected.append(token)
        return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Data quality agent runner")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to agent_config.yaml (default: <package>/../config/agent_config.yaml)",
    )
    args = parser.parse_args(argv)

    base_dir = _default_base_dir()
    config_path = args.config or (base_dir / "config" / "agent_config.yaml")
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    config = _load_config(config_path)

    available_tasks = list(TASK_FACTORIES.keys())
    selected_task_names = _prompt_task_selection(available_tasks)
    if not selected_task_names:
        print("No tasks selected. Exiting.")
        return 0

    dd_cfg = config.get("data_dictionary", {})
    csv_path = (base_dir / dd_cfg["csv_path"]).resolve()
    sample_rows = int(dd_cfg.get("sample_rows", 50_000))
    sample_df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

    ctx = RunContext(base_dir=base_dir, config=config, sample_df=sample_df)

    task_raw_findings: dict[str, dict] = {}
    for task_name in selected_task_names:
        print("\n" + "=" * 60)
        print(f"RUNNING TASK: {task_name}")
        print("=" * 60)

        task = TASK_FACTORIES[task_name]()
        result = task.run(ctx)
        if not result.ok:
            print(f"[{task_name}] {result.message}", file=sys.stderr)
            return 1

        print(f"[{task_name}] {result.message}")
        if result.report_path:
            print(f"[{task_name}] Report: {result.report_path}")
        if result.findings:
            print(f"[{task_name}] Findings: {result.findings}")

        print("=" * 60)
        print(f"COMPLETED TASK: {task_name}")
        print("=" * 60)

        task_raw_findings[task_name] = result.raw_findings

    if task_raw_findings:
        run_review(
            {
                "task_order": selected_task_names,
                "task_results": task_raw_findings,
            }
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
