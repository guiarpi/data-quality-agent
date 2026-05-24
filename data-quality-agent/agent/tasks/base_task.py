from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class RunContext:
    """Execution context passed to each task."""

    base_dir: Path
    config: dict[str, Any]
    sample_df: "pd.DataFrame | None" = None


@dataclass
class TaskResult:
    ok: bool
    message: str = ""
    findings: dict[str, Any] = field(default_factory=dict)
    report_path: Path | None = None
    # Structured finding lists used by the human review step.
    # Keys: "missing_defs", "extra_dict_vars", "inconsistencies", "kb_path"
    raw_findings: dict[str, Any] = field(default_factory=dict)


class BaseTask(ABC):
    """Abstract base for quality tasks."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def run(self, ctx: RunContext) -> TaskResult:
        pass
