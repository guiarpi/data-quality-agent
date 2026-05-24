# Data Quality Agent

A configurable Python agent for validating tabular datasets against a markdown data dictionary. Given a CSV and a schema definition, it detects missing column coverage, type inconsistencies, and null-value anomalies — then surfaces findings through an interactive review loop that learns which issues are false positives, so each subsequent run is cleaner than the last. Built to be dataset-agnostic: no hardcoded schema assumptions, all thresholds configurable via YAML.

---

## What it does

Given a CSV file and a markdown data dictionary, the agent runs a full suite of automated quality checks:

**1. Data Dictionary Coverage & Type Consistency**
Compares every column in the CSV against the dictionary. Flags columns missing from the dictionary, columns in the dictionary not present in the CSV, and columns where the actual data type conflicts with the declared type (Boolean, Integer, Timestamp, String).

**2. Missing Values Profiling**
Profiles null rates across all columns. Flags always-null columns, high-null columns (configurable threshold), and produces a ranked summary of missingness — the inputs a data analyst needs to decide whether a column is usable.

**3. Data Type Profiling**
Builds a full column-level profile: pandas dtype, inferred semantic type (identifier, boolean-like, categorical, timestamp, integer, decimal, free text), cardinality, uniqueness rate, min/max/mean for numeric and datetime columns, and a sample of representative values. Produces a summary of semantic type distribution across the dataset.

**4. Impossible Values Detection**
Evaluates configurable domain rules against the data and flags violations. Supports three rule types: numeric range checks (e.g. NPS must be 0–10), date ordering constraints (e.g. queue exit must be after queue entry), and logical dependency checks (e.g. non-abandoned contacts must have a resolution timestamp). Rules are defined in `agent_config.yaml` — no code changes required to add or adjust them.

**5. Invalid Entries Detection**
Flags values that are structurally malformed or semantically wrong in context. Runs configured rules (enum membership checks against an allowed-values list, regex pattern matching) alongside two automatic scans that require zero configuration: placeholder detection (catches functional nulls like `N/A`, `null`, `unknown`, `tbd` disguised as real values) and whitespace anomaly detection (leading/trailing spaces and double spaces that cause silent mismatches in joins and filters).

**6. Outlier Detection**
Runs both IQR (interquartile range) and Z-score methods on every numeric column and reports them side by side — letting the human reviewer decide which signal is more meaningful for each column. Also detects temporal outliers in timestamp columns (dates outside a configurable year range). Identifier columns can be excluded via config. All findings flow through the same knowledge-base review loop.

**7. Categorical Cleaning**
Surfaces consistency issues in low-cardinality string columns. Detects case and whitespace variants of the same concept (e.g. `"Email"` vs `"email"` vs `"EMAIL"`), fuzzy near-duplicate labels using difflib similarity scoring (e.g. `"Amend Booking"` vs `"Amend a Booking"`), and low-frequency categories that may be noise or data entry errors. The agent surfaces candidates with similarity scores and occurrence counts — the human decides whether to merge.

**8. HTML Dashboard**
After all tasks complete, the agent generates a single self-contained HTML file combining every task report into one page — KPI summary cards at the top (colour-coded green/amber by finding count), a sticky sidebar for navigation, and fully styled Markdown tables. Enabled by default; toggled with `html_report.enabled` in config.

**9. LLM Semantic Deduplication (optional)**
When `llm_dedup.enabled: true` is set and `ANTHROPIC_API_KEY` is present, fuzzy near-duplicate label pairs from the categorical cleaning task are sent to `claude-haiku-4-5` alongside the column's dictionary definition. The model returns a verdict (`same` / `different` / `uncertain`) and a one-line reasoning string, surfaced in both Markdown and HTML reports. Gracefully skipped when the package or key is absent.

**10. CI/CD**
A GitHub Actions workflow (`.github/workflows/data_quality.yml`) runs on every push and pull request. It generates a synthetic 2,000-row CSV covering all dictionary columns, executes all quality tasks, and evaluates configurable thresholds via `ci/quality_gate.py` — failing the build if critical issue counts are exceeded. Reports are uploaded as downloadable workflow artifacts.

Reports are written as timestamped Markdown files so every run is traceable and comparable over time.

---

## Architecture

```
data-quality-agent/
├── agent/
│   ├── runner.py               # CLI orchestrator — task selection, pipeline, HTML dashboard
│   ├── report/
│   │   └── html_report.py      # Combines all task reports into a single HTML dashboard
│   ├── review/
│   │   └── reviewer.py         # Interactive terminal review loop + dictionary fix
│   └── tasks/
│       ├── base_task.py            # Abstract base class (BaseTask, RunContext, TaskResult)
│       ├── data_dictionary.py      # Coverage + type consistency checks
│       ├── missing_values.py       # Null profiling
│       ├── data_types.py           # Semantic type, cardinality, stats, sample values
│       ├── impossible_values.py    # Domain rule evaluation: range, date order, logic
│       ├── invalid_entries.py      # Enum, regex, placeholder, whitespace checks
│       ├── outliers.py             # IQR + Z-score + temporal outlier detection
│       ├── categorical_cleaning.py # Case variants, fuzzy near-duplicates, low-frequency
│       └── llm_dedup.py            # Optional LLM semantic deduplication (claude-haiku)
├── ci/
│   ├── generate_ci_data.py     # Synthetic CSV generator for GitHub Actions
│   ├── ci_agent_config.yaml    # CI-specific agent config
│   └── quality_gate.py         # Parses reports and fails CI on threshold breaches
├── config/
│   └── agent_config.yaml       # Default thresholds and paths — no code changes to reconfigure
├── knowledge/
│   └── knowledge_base.py       # Load / save / query learnings.json
├── projects/
│   └── new_project_template/   # Copy this to create an isolated per-project config
├── outputs/
│   └── reports/                # Timestamped Markdown + HTML reports written here
└── Documentation/
    └── SaaS_Support_Contact_Data_Dictionary.md  # Sample dictionary (fictional dataset)
```

---

## Setup

```bash
git clone https://github.com/guiarpi/data-quality-agent.git
cd data-quality-agent/data-quality-agent
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Configuration

Edit `config/agent_config.yaml`. The file is organised into sections — one per task plus two global sections:

**`data_dictionary`** (core — required for all tasks)

| Key | Description | Default |
|---|---|---|
| `csv_path` | Path to the CSV file to validate (relative to `data-quality-agent/` or absolute) | — |
| `dictionary_path` | Path to the markdown data dictionary (pipe table: Variable, Definition, Data Type) | — |
| `sample_rows` | Rows to read from the CSV — keeps large files tractable | `50000` |
| `case_insensitive_column_match` | Match dictionary names to CSV headers ignoring case | `true` |
| `inconsistency_threshold` | Min fraction of non-null values violating declared type before flagging | `0.05` |
| `reports_dir` | Output directory for timestamped Markdown + HTML reports | `outputs/reports` |
| `knowledge_base_path` | Path to the learnings JSON file | `knowledge/learnings.json` |

**Other sections** (all optional — sensible defaults apply if omitted):
`missing_values` · `data_types` · `impossible_values` · `invalid_entries` · `outliers` · `categorical_cleaning` · `html_report` · `llm_dedup`

See the inline comments in `config/agent_config.yaml` for every key and its default.

---

## Running the agent

```bash
cd data-quality-agent
python -m agent.runner
```

The runner prompts for task selection:

```
Press Enter    → run all tasks
missing_values → run only the missing values check
-data_dictionary → run all tasks except the dictionary check
```

For non-interactive / CI runs, the prompt is skipped and all tasks execute automatically.

Custom config path:

```bash
python -m agent.runner --config /path/to/agent_config.yaml
```

---

## Output

Each run writes timestamped files to `outputs/reports/` (or the `reports_dir` configured for each task):

```
data_dictionary_report_YYYYMMDD_HHMMSS.md
missing_values_report_YYYYMMDD_HHMMSS.md
data_types_report_YYYYMMDD_HHMMSS.md
impossible_values_report_YYYYMMDD_HHMMSS.md
invalid_entries_report_YYYYMMDD_HHMMSS.md
outliers_report_YYYYMMDD_HHMMSS.md
categorical_cleaning_report_YYYYMMDD_HHMMSS.md
data_quality_dashboard_YYYYMMDD_HHMMSS.html   ← combined dashboard
```

Each Markdown report is self-contained — readable in any editor, committable to git, and diffable across runs. The HTML dashboard combines all reports into a single page with KPI cards and sidebar navigation.

---

## Type checking logic

The dictionary's `Data Type` column is mapped to a coarse category:

| Category | Check applied |
|---|---|
| Boolean | Non-null values must match true/false, yes/no, or 0/1 (case-insensitive) |
| Integer/Number | Integer dtypes pass; object columns checked with `pd.to_numeric`; float columns checked for whole-number values |
| Timestamp | `pd.to_datetime` applied to non-null sample; high parse failure rate is flagged |
| String/Text | Coarse type only; all-null handling is owned by the missing-values task |

Unrecognised `Data Type` text is listed under inconsistencies with a note that the type could not be mapped.

---

## Sample data dictionary

A fictional B2B SaaS customer support contact dictionary (`Documentation/SaaS_Support_Contact_Data_Dictionary.md`) is included to demonstrate the agent on a realistic schema — 60+ columns spanning Booleans, Timestamps, Integers, and Strings across contact routing, agent performance, AI deflection, and customer sentiment fields.

To use your own dictionary, update `dictionary_path` in `agent_config.yaml`. The dictionary must be a Markdown pipe table with at minimum `Variable` and `Data Type` columns.

---

## Roadmap

- [x] Data dictionary coverage & type consistency
- [x] Missing values profiling
- [x] Data type profiling (semantic type inference, cardinality, uniqueness, min/max, sample values)
- [x] Impossible values — range checks, date ordering, logical dependency rules
- [x] Invalid entries — enum checks, regex patterns, placeholder detection, whitespace anomalies
- [x] Outlier detection — IQR + Z-score on numeric columns, temporal outliers on timestamps
- [x] Categorical cleaning — case variants, fuzzy near-duplicates, low-frequency categories

- [x] HTML dashboard — single self-contained HTML file per run combining all task reports with KPI cards, sidebar navigation, and styled tables
- [x] LLM-assisted semantic deduplication — optional claude-haiku-4-5 call to assess fuzzy near-duplicate label pairs with data dictionary context (opt-in via config + `ANTHROPIC_API_KEY`)
- [x] CI/CD — GitHub Actions workflow that generates synthetic data, runs all tasks, and enforces configurable quality gate thresholds

**Future enhancements**
- [ ] Referential integrity checks across multiple CSV files
- [ ] Duplicate row detection

---

## Collaboration

Initial architecture and planning by [Sean McIver](https://github.com/seanmciv) (AI Lead). Agent development, task implementation, and documentation by [Guilherme Arpi](https://github.com/guiarpi).

---

## Tech stack

- **Python** — pandas, PyYAML, markdown, anthropic (optional)
- **Output** — Markdown reports (timestamped) + single-file HTML dashboard
- **Config** — YAML (zero code changes to reconfigure for a new dataset)
