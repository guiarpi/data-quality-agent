# Agent Roadmap

Each task lives in its own file. The architecture (BaseTask, RunContext, KnowledgeBase,
human review loop) is already in place — new tasks slot in without touching the core.

## Task status

| Task | File | Status |
| --- | --- | --- |
| Data dictionary | `v1_data_dictionary.md` | Complete |
| Missing values | `v2_missing_values.md` | Complete |
| Data types | `v3_data_types.md` | Complete |
| Impossible values | `v4_impossible_values.md` | Planned |
| Invalid entries | `v5_invalid_entries.md` | Planned |
| Outliers | `v6_outliers.md` | Planned |
| Categorical cleaning | `v7_categorical_cleaning.md` | Planned |

---

## Next recommended task: Impossible Values

With three tasks complete (dictionary coverage, null profiling, and full type profiling),
impossible values is the highest-value next step.

**Why now:**
- The data types task now gives a precise semantic type for every column — impossible
  value rules can reference those types without re-inferring them.
- Domain range rules (NPS 0–10, handling time ≥ 0, date ordering) are the kind of
  business-logic check that is immediately legible to a hiring reviewer.
- It extends the existing `agent_config.yaml` pattern with a `rules:` block — no
  new infrastructure is required.

**Suggested order from here:**

| Priority | Reasoning |
| --- | --- |
| 1. Impossible values | High business value; domain rules + cross-column constraints |
| 2. Invalid entries | Format-level checks (email, phone, enum membership); builds on type task |
| 3. Outliers | Statistical; works best once types and nulls are clean |
| 4. Categorical cleaning | Most complex; benefits from all prior tasks being done first |
