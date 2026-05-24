from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ReviewItem:
    """Human review queue entry (stub for future workflow)."""

    issue_type: str
    column_name: str | None
    detail: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_utc_now)
    payload: dict[str, Any] = field(default_factory=dict)
