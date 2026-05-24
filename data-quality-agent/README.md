# Data quality agent

Compare a CSV against a markdown data dictionary and write quality reports for:

- dictionary coverage/type consistency
- missing values (null profile, always-null, high-null)

## Setup

From this directory (`data-quality-agent/`):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit [`config/agent_config.yaml`](config/agent_config.yaml):

- `csv_path` — path to the CSV (relative to `data-quality-agent/`, or absolute).
- `dictionary_path` — markdown file with a pipe table containing **Variable**, **Definition**, and **Data Type** columns (see `../Documentation/CBC_Contact_Level_Data_Dictionary.md`).
- `sample_rows` — number of rows to read from the CSV for profiling (keeps large files tractable).
- `case_insensitive_column_match` — when `true`, dictionary variable names are matched to CSV headers ignoring case (recommended when the dictionary is upper case and the CSV is lower case).
- `inconsistency_threshold` — minimum fraction of non-null values that must violate the expected type before a column is flagged (default `0.05`).
- `reports_dir` — where timestamped Markdown reports are written (default `outputs/reports`).

## Run

```bash
cd data-quality-agent
python -m agent.runner
```

In an interactive terminal, the runner prompts you to choose tasks before execution:

- Press Enter to run all tasks
- Enter task names (comma-separated) to include only those tasks (for example `missing_values`)
- Enter exclusions with a leading `-` (for example `-data_dictionary`)

Non-interactive runs (for example CI/piped stdin) skip the prompt and run all tasks.

Optional config path:

```bash
python -m agent.runner --config /path/to/agent_config.yaml
```

Reports are written as:

- `.../data_dictionary_report_YYYYMMDD_HHMMSS.md`
- `.../missing_values_report_YYYYMMDD_HHMMSS.md`

## Type checks (first milestone)

The dictionary **Data Type** cell is mapped to a coarse category using word boundaries (`Boolean`, `Integer`/`Number`, `Timestamp`, `String`/`Text`):

| Category   | Rule (summary) |
| ---------- | -------------- |
| Boolean    | Non-null values should look like true/false, yes/no, 0/1 (case-insensitive). |
| Integer    | Prefer integer dtypes; object columns are checked with `pd.to_numeric`; float columns are checked for whole-number values. |
| Timestamp  | `pd.to_datetime` on non-null sample; high parse failure rate is flagged. |
| String/Text | Checked as a coarse type only; all-null handling is owned by the missing-values task. |

Unrecognized **Data Type** text is listed under inconsistencies with a note that the type could not be mapped.

## Missing values checks (v2)

Configured in the `missing_values:` block:

- `high_null_threshold` — flag columns at or above this null rate (default `0.50`)
- `always_null_threshold` — flag columns that are fully null in the sample (default `1.00`)
- `reports_dir` — output directory for the missing-values report
- `knowledge_base_path` — learnings file used for false-positive suppression and notes

## Layout

- `agent/runner.py` — CLI orchestrator.
- `agent/tasks/` — tasks (`base_task.py`, `data_dictionary.py`).
- `agent/review/` — human review stubs (`queue.py`, `models.py`); not used in the first milestone.
- `knowledge/` — placeholders for future learnings and glossary overrides.
- `config/agent_config.yaml` — thresholds and paths.
