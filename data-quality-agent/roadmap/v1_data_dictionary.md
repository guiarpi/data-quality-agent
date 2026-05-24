# V1 — Data Dictionary Task

**Status:** Complete

## What it does

Compares a CSV file against a markdown data dictionary and produces a report covering:

- **Missing definitions** — CSV columns that have no entry in the dictionary
- **Dictionary-only variables** — dictionary entries that do not appear in the CSV
- **Type inconsistencies** — columns whose actual data does not match the declared type
  (boolean, integer, timestamp, string)

## Key features built

- Case-insensitive column matching (dictionary is uppercase, CSV is lowercase)
- Configurable sample size (default 50 000 rows) to keep large files tractable
- Human review loop with fuzzy match suggestions (difflib) for naming mismatches
- Dictionary fix: reviewer can rename a variable in the markdown file in place
- Knowledge base (learnings.json) suppresses known false positives on future runs
- Per-project isolation — each data set has its own config, knowledge base, and reports

## Files

| File | Purpose |
| --- | --- |
| `agent/tasks/data_dictionary.py` | Core analysis task |
| `agent/review/reviewer.py` | Interactive terminal review loop |
| `knowledge/knowledge_base.py` | Load / save / query learnings |
| `projects/<name>/agent_config.yaml` | Per-project configuration |
| `projects/<name>/knowledge/learnings.json` | Human-reviewed decisions |

## Known limitations / future improvements

- Type checking is coarse (four categories). A dedicated data types task would go deeper.
- "All null" columns are flagged as type inconsistencies — the missing values task
  will handle this more precisely.
- The dictionary fix only renames variables; it cannot add new entries or update
  definitions automatically.
