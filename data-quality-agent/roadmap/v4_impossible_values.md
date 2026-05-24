# V4 — Impossible Values Task

**Status:** Complete

## Goal

Flag values that are logically impossible given what a column represents — not just
the wrong type, but outside a valid range or violating a business rule.

Examples from a SaaS support dataset:
- NPS or CSAT score outside 0–10
- TOTAL_HANDLING_TIME_SEC is negative
- EXIT_QUEUE_DATE_TIME is earlier than ENTER_QUEUE_DATE_TIME
- MONTHS_IN_COMPANY is negative or implausibly large

## What it would check

| Check type | Example |
| --- | --- |
| Numeric range | NPS must be 0–10; handling time must be ≥ 0 |
| Date ordering | Exit queue must be after enter queue |
| Cross-column constraint | COMPLETE_DATETIME must be after START_DATETIME |
| Logical dependency | If ABANDONED is true, START_DATETIME should be null |

## Where the rules come from

Rules cannot be inferred from the data alone — they require domain knowledge.
Two sources:

**1. A rules file per project** (new concept)
```yaml
# projects/my_project/rules.yaml
impossible_values:
  - column: NPS
    min: 0
    max: 10
  - column: TOTAL_HANDLING_TIME_SEC
    min: 0
  - columns: [ENTER_QUEUE_DATE_TIME, EXIT_QUEUE_DATE_TIME]
    rule: "EXIT_QUEUE_DATE_TIME >= ENTER_QUEUE_DATE_TIME"
```

**2. Learned from the data dictionary**
If the dictionary definition says "score out of 10", the agent could eventually
use an LLM to extract the implied range. This is a future enhancement.

## Connection to the knowledge base

If a rule fires but the human knows it is a legitimate edge case (e.g. a
zero-second handling time is valid for automated contacts), they can label it
as a `known_exception` and it will be annotated on future runs.

## Open questions

- Should rules be defined in a separate `rules.yaml` or inside `agent_config.yaml`?
- Cross-column constraints require evaluating pandas expressions — need a safe
  eval approach (avoid raw `eval()`).
- What is the right threshold for flagging? Even one impossible value may be
  significant (e.g. a negative handling time is never valid).
