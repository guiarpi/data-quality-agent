# V2 — Missing Values Task

**Status:** Complete

## Goal

Produce a dedicated missing-value profile for every column: how many nulls, whether
the null rate is expected given what the column represents, and whether columns tend
to be null together (suggesting a structural gap rather than random missingness).

## What it checks

| Check | Description |
| --- | --- |
| Null rate per column | % of rows that are null for each column |
| Always-null columns | Columns that are 100% null in the sample |
| High-null threshold | Flag columns above a configurable threshold (e.g. > 50% null) |
| Conditional nulls | Columns that are only populated for certain channels/types (future refinement) |
| Co-null patterns | Groups of columns that are null at the same time (future refinement) |

## Why this comes before other tasks

- Outlier detection and type analysis on a 90%-null column is meaningless
- Some nulls are expected (e.g. SURVEY_CREATE_DATE is null if no survey was submitted)
- The human reviewer can label high-null columns as expected or as a genuine gap

## Connection to v1

The data dictionary task already flags "all null" columns under type inconsistencies.
This task replaces that crude flag with a proper analysis and removes the duplicate
from the v1 report.

## Connection to the knowledge base

Expected null patterns can be saved as learnings:
- "SURVEY_CREATE_DATE is frequently null — expected, only populated when survey submitted"
- Resolution: `known_exception`

On future runs, the column still appears in the profile but is annotated with the
prior note rather than raising an alert.

## Config options

```yaml
missing_values:
  high_null_threshold: 0.50       # flag columns with more than 50% nulls
  always_null_threshold: 1.00     # flag columns that are 100% null
  reports_dir: "projects/<name>/outputs/reports"
  knowledge_base_path: "projects/<name>/knowledge/learnings.json"
```

## Deferred from v2.0

- Co-null pattern detection (kept out of the initial one-hour implementation)
- Potential merged reporting across tasks (currently separate reports per task)
