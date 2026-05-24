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

## Enhancements shipped

| Enhancement | Module | Notes |
| --- | --- | --- |
| HTML dashboard | `agent/report/html_report.py` | Single self-contained file: KPI cards, sidebar nav, styled tables |
| LLM semantic deduplication | `agent/tasks/llm_dedup.py` | claude-haiku-4-5 assesses fuzzy pairs; opt-in via config + API key |
| CI/CD | `.github/workflows/data_quality.yml` | GitHub Actions: synthetic data → all tasks → quality gate → artifacts |

## Future enhancements

| Enhancement | Notes |
| --- | --- |
| Referential integrity | Foreign key validation across multiple CSV files |
| Duplicate row detection | Exact and fuzzy row-level deduplication |
