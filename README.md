# Data Quality Agent

A configurable Python agent for validating tabular datasets against a markdown data dictionary. Given a CSV and a schema definition, it detects missing column coverage, type inconsistencies, and null-value anomalies — then surfaces findings through an interactive review loop that learns which issues are false positives, so each subsequent run is cleaner than the last. Built to be dataset-agnostic: no hardcoded schema assumptions, all thresholds configurable via YAML.

---

## What it does

Given a CSV file and a markdown data dictionary, the agent runs two automated quality checks:

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

Reports are written as timestamped Markdown files so every run is traceable and comparable over time.

---

## Architecture

```
data-quality-agent/
├── agent/
│   ├── runner.py          # CLI orchestrator — prompts for task selection, runs pipeline
│   └── tasks/
│       ├── base_task.py       # Abstract base class all tasks inherit from
│       ├── data_dictionary.py # Coverage + type consistency checks
│       └── missing_values.py  # Null profiling
├── config/
│   └── agent_config.yaml  # All thresholds and paths — no code changes needed to reconfigure
├── knowledge/             # Per-run learnings.json — human-reviewed false-positive suppression
├── outputs/
│   └── reports/           # Timestamped Markdown reports written here
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

Edit `config/agent_config.yaml`:

| Key | Description | Default |
|---|---|---|
| `csv_path` | Path to the CSV file to validate (relative to `data-quality-agent/` or absolute) | — |
| `dictionary_path` | Path to the markdown data dictionary (pipe table with Variable, Definition, Data Type columns) | — |
| `sample_rows` | Number of rows to read from the CSV — keeps large files tractable | 10000 |
| `case_insensitive_column_match` | Match dictionary variable names to CSV headers ignoring case | `true` |
| `inconsistency_threshold` | Min fraction of non-null values violating declared type before a column is flagged | `0.05` |
| `reports_dir` | Output directory for timestamped reports | `outputs/reports` |
| `high_null_threshold` | Flag columns at or above this null rate | `0.50` |

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

Reports are written to `outputs/reports/` as:

```
data_dictionary_report_YYYYMMDD_HHMMSS.md
missing_values_report_YYYYMMDD_HHMMSS.md
```

Each report is self-contained Markdown — readable in any editor, committable to git, or convertible to HTML/PDF for sharing.

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
- [ ] Outlier detection
- [ ] Categorical cleaning
- [ ] HTML report output option
- [ ] CI/CD integration example (GitHub Actions)

---

## Collaboration

Initial architecture and planning by [Sean McIver](https://github.com/seanmciv) (AI Lead). Agent development, task implementation, and documentation by [Guilherme Arpi](https://github.com/guiarpi).

---

## Tech stack

- **Python** — pandas, PyYAML
- **Output** — Markdown reports (timestamped)
- **Config** — YAML (zero code changes to reconfigure for a new dataset)
