# Agent Roadmap

Each task lives in its own file. The architecture (BaseTask, RunContext, KnowledgeBase,
human review loop) is already in place — new tasks slot in without touching the core.

## Task status

| Task | File | Status |
| --- | --- | --- |
| Data dictionary | `v1_data_dictionary.md` | Complete |
| Missing values | `v2_missing_values.md` | Complete |
| Data types | `v3_data_types.md` | Complete |
| Impossible values | `v4_impossible_values.md` | Complete |
| Invalid entries | `v5_invalid_entries.md` | Complete |
| Outliers | `v6_outliers.md` | Planned |
| Categorical cleaning | `v7_categorical_cleaning.md` | Planned |

---

## Next recommended task: Outliers

With five tasks complete, outlier detection is the natural next step.

**Why now:**
- Types, nulls, impossible values, and format issues are all resolved — outlier
  detection on dirty data produces noisy results, so doing it last is correct.
- Statistical methods (IQR, z-score) are well-understood and produce findings
  that are immediately legible to a data analyst or hiring reviewer.
- It uses the same review and knowledge-base loop with no new infrastructure.

**Suggested order from here:**

| Priority | Reasoning |
| --- | --- |
| 1. Outliers | Statistical; IQR + z-score on numeric columns; benefits from clean types |
| 2. Categorical cleaning | Most complex; normalises free-text categories (fuzzy deduplication) |
