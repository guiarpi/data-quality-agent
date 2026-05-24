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
| Invalid entries | `v5_invalid_entries.md` | Planned |
| Outliers | `v6_outliers.md` | Planned |
| Categorical cleaning | `v7_categorical_cleaning.md` | Planned |

---

## Next recommended task: Invalid Entries

With four tasks complete, invalid entries is the natural next step.

**Why now:**
- Impossible values covered range and ordering constraints — invalid entries covers
  *format* constraints (email addresses, phone numbers, enum membership, regex patterns).
- It operates on the same column profiles already computed by the data types task.
- Together, impossible values + invalid entries give a complete picture of "is this
  value structurally plausible?" before moving to statistical outlier detection.

**Suggested order from here:**

| Priority | Reasoning |
| --- | --- |
| 1. Invalid entries | Format checks (email, phone, enum membership, regex); builds on type task |
| 2. Outliers | Statistical; works best once types, nulls, and formats are clean |
| 3. Categorical cleaning | Most complex; benefits from all prior tasks being done first |
