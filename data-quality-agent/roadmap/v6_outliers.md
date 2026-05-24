# V6 — Outliers Task

**Status:** Complete

## Goal

Detect values that are statistically extreme relative to the rest of the column.
Outliers are not necessarily wrong — they may be legitimate edge cases, data entry
errors, or signals of something worth investigating.

## What it would check

| Method | Best for | Description |
| --- | --- | --- |
| IQR (interquartile range) | Skewed distributions | Flag values below Q1 − 1.5×IQR or above Q3 + 1.5×IQR |
| Z-score | Roughly normal distributions | Flag values more than N standard deviations from the mean |
| Min/max sanity | Any numeric column | Surface the actual min and max with their row count |
| Temporal outliers | Timestamp columns | Dates far outside the expected range (e.g. year 1900 or 2099) |

## Why this comes after types, nulls, and impossible values

Outlier detection on a column with 80% nulls or mixed types produces misleading
results. Running this task after v2 and v3 ensures the input is clean enough for
statistics to be meaningful.

## Output

For each flagged column, the report would show:
- The method used
- The threshold applied
- Number of outlier rows
- The actual outlier values (sampled)
- Whether the outlier is on the high end, low end, or both

## Connection to the knowledge base

Some outliers are known and expected (e.g. a handling time of 7200 seconds for a
complex case is unusual but valid). The human can label these as `known_exception`
with a note explaining the business context.

## New config options to consider

```yaml
outliers:
  method: "iqr"                # iqr or zscore
  iqr_multiplier: 1.5
  zscore_threshold: 3.0
  min_non_null_rows: 100       # skip columns with too few values to be meaningful
  columns_exclude: []          # columns to skip entirely (e.g. free-text IDs)
```

## Open questions

- Should both IQR and Z-score be run, or should the task pick based on the
  distribution shape detected in the data types task?
- How do we handle columns where outliers are expected by design (e.g. NPS
  scores of 0 or 10 are valid extremes, not outliers)?
- Should the task output a row-level file listing the actual outlier records,
  or just a column-level summary?
