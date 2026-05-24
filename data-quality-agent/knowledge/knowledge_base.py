from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The three resolutions a human can assign to a finding.
RESOLUTIONS = {"false_positive", "confirmed_issue", "known_exception", "naming_mismatch_fixed"}


class KnowledgeBase:
    """Loads, stores, and queries human-reviewed findings.

    Every learning is a dict saved to a JSON file on disk.  The file is
    re-written after every new learning so nothing is lost if the process
    ends early.

    Typical usage
    -------------
    kb = KnowledgeBase(Path("knowledge/learnings.json"))

    # Ask whether to skip a finding
    if kb.is_false_positive(column="FCR", issue_type="type_mismatch"):
        continue

    # Save what the human just told us
    kb.add_learning(
        column_name="FCR",
        issue_type="type_mismatch",
        expected_type="Integer/Number",
        detail="float dtype with many non-integer floats",
        resolution="false_positive",
        note="FCR is always 0 or 1; the float dtype is a pandas artefact",
    )
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._learnings: list[dict[str, Any]] = self._load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_false_positive(self, column: str, issue_type: str) -> bool:
        """Return True if this (column, issue_type) pair was previously
        marked as a false positive by a human reviewer."""
        for learning in self._learnings:
            if (
                learning.get("column_name") == column
                and learning.get("issue_type") == issue_type
                and learning.get("resolution") == "false_positive"
            ):
                return True
        return False

    def get_note(self, column: str, issue_type: str) -> str | None:
        """Return the most recent human note for this (column, issue_type)
        pair, or None if there is no recorded learning."""
        matches = [
            l for l in self._learnings
            if l.get("column_name") == column and l.get("issue_type") == issue_type
        ]
        if not matches:
            return None
        # Return the note from the most recently added match.
        return matches[-1].get("note")

    def add_learning(
        self,
        *,
        column_name: str | None,
        issue_type: str,
        expected_type: str,
        detail: str,
        resolution: str,
        note: str = "",
    ) -> dict[str, Any]:
        """Record a human-reviewed finding and immediately persist it.

        Parameters
        ----------
        column_name:   CSV column the finding relates to (None for file-level issues).
        issue_type:    One of: type_mismatch, missing_definition, dictionary_only,
                       unmappable_type.
        expected_type: The data type string from the dictionary (e.g. "Integer/Number").
        detail:        The original finding text the human was shown.
        resolution:    One of: false_positive, confirmed_issue, known_exception.
        note:          Optional free-text comment from the human.
        """
        if resolution not in RESOLUTIONS:
            raise ValueError(f"resolution must be one of {RESOLUTIONS}, got {resolution!r}")

        learning: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "column_name": column_name,
            "issue_type": issue_type,
            "expected_type": expected_type,
            "detail": detail,
            "resolution": resolution,
            "note": note,
        }
        self._learnings.append(learning)
        self._save()
        return learning

    def all_learnings(self) -> list[dict[str, Any]]:
        """Return a copy of all stored learnings."""
        return list(self._learnings)

    def summary(self) -> dict[str, int]:
        """Return a count of learnings by resolution type."""
        counts: dict[str, int] = {r: 0 for r in RESOLUTIONS}
        for l in self._learnings:
            res = l.get("resolution", "")
            if res in counts:
                counts[res] += 1
        return counts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        """Read learnings from disk.  Returns an empty list if the file
        does not exist or contains something other than a JSON array."""
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _save(self) -> None:
        """Write all learnings to disk as pretty-printed JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._learnings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
