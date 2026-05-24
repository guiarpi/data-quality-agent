# V3 — Data Types Task

**Status:** Planned

## Goal

Replace the coarse four-category type check in v1 with a full column profile:
actual pandas dtype, inferred semantic type, cardinality, uniqueness, and a
sample of representative values. Useful both as a standalone report and as
input to later tasks (impossible values, outliers).

## What it would check

| Check | Description |
| --- | --- |
| Pandas dtype | The actual dtype pandas assigned (int64, float64, object, datetime64, etc.) |
| Semantic type | Inferred category: identifier, boolean, integer, decimal, timestamp, free text, categorical |
| Cardinality | Number of distinct values; flags columns that look categorical but have high cardinality |
| Uniqueness rate | % of rows with a unique value; useful for spotting ID columns |
| Min / max / mean | For numeric and datetime columns |
| Sample values | A small set of representative non-null values shown in the report |

## Semantic type inference logic (proposed)

```
If unique rate ≈ 100%          → likely identifier
If distinct values ≤ 2         → likely boolean
If distinct values ≤ 20        → likely categorical
If parseable as datetime        → timestamp
If parseable as integer         → integer
If parseable as float           → decimal
Otherwise                       → free text
```

## Connection to v1

The v1 type check compares against the dictionary's declared type.
This task profiles what the data *actually is*, independent of the dictionary.
Combining both gives a clearer picture: "the dictionary says integer, the data
looks categorical — worth investigating."

## New config options to consider

```yaml
data_types:
  categorical_cardinality_max: 20    # max distinct values before flagging as high-cardinality
  sample_values_count: 5             # number of example values shown per column
  uniqueness_id_threshold: 0.99      # unique rate above which a column is flagged as likely ID
```

## Open questions

- Should this task produce its own report, or augment the data dictionary report
  with an extra profile column?
- How do we handle mixed-type columns (e.g. a column that is mostly integer
  but has some string values)?
