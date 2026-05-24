# Agent Roadmap

Each task lives in its own file. The architecture (BaseTask, RunContext, KnowledgeBase,
human review loop) is already in place — new tasks slot in without touching the core.

## Task status

| Task | File | Status |
| --- | --- | --- |
| Data dictionary | `v1_data_dictionary.md` | Complete |
| Missing values | `v2_missing_values.md` | Complete |
| Data types | `v3_data_types.md` | Planned |
| Impossible values | `v4_impossible_values.md` | Planned |
| Invalid entries | `v5_invalid_entries.md` | Planned |
| Outliers | `v6_outliers.md` | Planned |
| Categorical cleaning | `v7_categorical_cleaning.md` | Planned |

---

## Next recommended task: Data Types

Data types should come next for three reasons.

**1. We already have the skeleton from v1.**
The dictionary task includes coarse type checks; the next task should make those
checks richer (ranges, structured parsing, stricter category-specific logic).

**2. Better types improve all downstream tasks.**
Impossible values, invalid-entry checks, and outlier detection all become more
accurate when type inference and validation are stronger.

**3. It uses the same review and knowledge-base loop.**
No new infrastructure is needed: reviewers can still classify findings and persist
learnings for future suppression/annotation.

**Suggested order from here:**

| Priority | Reasoning |
| --- | --- |
| 1. Data types | We have the skeleton; a dedicated task makes it much richer |
| 2. Impossible values | High business value; requires domain rules (min/max, allowed ranges) |
| 3. Invalid entries | Format-level checks; builds on type task |
| 4. Outliers | Statistical; works best once types and nulls are clean |
| 5. Categorical cleaning | Most complex; benefits from all prior tasks being done first |
