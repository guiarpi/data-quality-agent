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
| Categorical cleaning | `v7_categorical_cleaning.md` | Complete |

---

## All planned tasks complete 🎉

All seven validation tasks are implemented. The pipeline now covers the full
data quality lifecycle:

| Stage | What it detects |
| --- | --- |
| Schema | Missing definitions, extra dictionary variables, type conflicts |
| Completeness | Always-null columns, high-null columns |
| Type profile | Semantic type, cardinality, uniqueness, stats, sample values |
| Domain logic | Range violations, date ordering, logical dependencies |
| Format validity | Enum mismatches, regex patterns, placeholder strings, whitespace |
| Statistics | IQR outliers, Z-score outliers, temporal anomalies |
| Consistency | Case variants, near-duplicate labels, low-frequency categories |

## Future enhancements

| Enhancement | Notes |
| --- | --- |
| LLM-assisted semantic deduplication | Pass fuzzy candidate pairs to Claude with dictionary context |
| HTML report output | Single-file dashboard across all tasks |
| CI/CD integration | GitHub Actions workflow example |
| Referential integrity | Foreign key validation across multiple CSV files |
| Duplicate row detection | Exact and fuzzy row-level deduplication |
