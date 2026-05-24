from __future__ import annotations

from collections import deque

from agent.review.models import ReviewItem


class ReviewQueue:
    """In-memory review queue (stub until human-in-the-loop is wired)."""

    def __init__(self) -> None:
        self._items: deque[ReviewItem] = deque()

    def add(self, item: ReviewItem) -> None:
        self._items.append(item)

    def pending(self) -> list[ReviewItem]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
