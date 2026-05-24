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
| Outliers | `v6_outliers.md` | Complete |
| Categorical cleaning | `v7_categorical_cleaning.md` | Planned |

---

## Next recommended task: Categorical Cleaning

With six tasks complete, categorical cleaning is the final planned task.

**Why now:**
- All structural and statistical issues are resolved — categorical cleaning is the
  most complex task and benefits from the full picture established by prior tasks.
- Fuzzy deduplication of low-cardinality string columns (e.g. "New York" vs "new york"
  vs "NY") directly extends the data types task's categorical detection.

**Suggested order from here:**

| Priority | Reasoning |
| --- | --- |
| 1. Categorical cleaning | Fuzzy deduplication on categorical columns; rounds out the full pipeline |
