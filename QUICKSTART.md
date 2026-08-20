# Quickstart

Get the Data Quality Agent running and producing reports in about two minutes —
no data download required for the first run.

Every command below has been executed end-to-end against a clean copy of this
repository. Copy them one block at a time.

---

## Before you start

You need **Python 3.10 or newer**. Check:

```bash
python3 --version
```

> **The single most common mistake:** almost every command in this guide must be
> run from the **inner** `data-quality-agent/` directory, not the repository
> root. The repository root also contains a folder called `data-quality-agent`,
> so the path you want looks doubled — that is correct and intentional.
>
> If you see `ModuleNotFoundError: No module named 'agent'`, you are in the
> wrong directory. Jump to [Troubleshooting](#troubleshooting).

---

## Step 1 — Get the code

```bash
git clone https://github.com/guiarpi/data-quality-agent.git
cd data-quality-agent/data-quality-agent
```

That second `cd` is the doubled path described above. Confirm you are in the
right place — you should see an `agent` folder listed:

```bash
ls
```

Expected output includes: `agent`, `ci`, `config`, `knowledge`, `requirements.txt`

---

## Step 2 — Install dependencies

Using a virtual environment (recommended, keeps things isolated):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Prefer to skip the virtual environment? This works too:

```bash
pip install pandas PyYAML markdown
```

Three packages are required: `pandas`, `PyYAML`, `markdown`. A fourth,
`anthropic`, is optional and only needed for the LLM feature in Step 5.

---

## Step 3 — First run, no download needed

The repository ships a generator that builds a 2,000-row synthetic dataset with
data quality problems deliberately planted in it. This is the fastest way to see
the agent work.

**Generate the data:**

```bash
python3 ci/generate_ci_data.py
```

Expected output:

```
Generated 2,000 rows → ci/outputs/contacts_ci.csv
```

**Run all seven checks:**

```bash
python3 -m agent.runner --config ci/ci_agent_config.yaml
```

When run in an interactive terminal, you will first be asked which tasks to run.
**Press Enter** to run all of them.

You should then see seven blocks scroll past, one per task, ending with a line
pointing at the HTML dashboard.

**Open the dashboard:**

```bash
open ci/outputs/reports/data_quality_dashboard_*.html      # macOS
# xdg-open on Linux, start on Windows
```

You now have a single self-contained HTML page with KPI cards, a sidebar, and
every finding from all seven tasks.

### What the agent should find

The synthetic data has known problems planted in it, so you can confirm the
agent is working correctly:

| Task | What it should report |
|---|---|
| `data_dictionary` | 13 columns missing a dictionary definition; 3 type inconsistencies |
| `missing_values` | 4 high-null columns; 0 always-null |
| `data_types` | 36 columns profiled and classified by semantic type |
| `impossible_values` | 0 violations — the generated data respects all 4 rules |
| `invalid_entries` | 0 rule violations |
| `outliers` | 0 numeric outliers |
| `categorical_cleaning` | 3 columns with case variants, 4 with fuzzy near-duplicates |

The headline result is `categorical_cleaning`: it should catch that `Email`,
`email` and `EMAIL` are the same value, and likewise `chat` and `Chat`.

**Optional — run the CI quality gate**, which fails the build when issue counts
exceed configured thresholds:

```bash
python3 ci/quality_gate.py
```

Expected: `Quality gate: 4 checks, 0 failure(s)` and exit code 0.

---

## Step 4 — Run against real public data

Now point the agent at a genuinely messy real-world dataset: [NYC 311 Service
Requests][nyc311], roughly 24 million rows, updated daily. A ready-made data
dictionary and config are bundled in `examples/nyc311/`.

**Download a 50,000-row sample.** Note the `cd` moves you to the example folder
and back — run this as one block:

```bash
cd ../examples/nyc311
curl -o nyc311.csv "https://data.cityofnewyork.us/resource/erm2-nwe9.csv?\$limit=50000"
cd ../../data-quality-agent
```

The download is roughly 40 MB and takes one to three minutes.

> Use the `curl` command above rather than the portal's Export button. The API
> returns snake_case headers (`unique_key`, `created_date`) that match the
> bundled dictionary. The Export button returns Title Case headers
> (`Unique Key`, `Created Date`), which will not match.

**Run the agent:**

```bash
python3 -m agent.runner --config ../examples/nyc311/agent_config.yaml
```

Reports are written to `examples/nyc311/reports/`.

### What to look for

Against real 311 data the agent typically surfaces:

- **Bad geocodes** — `latitude`/`longitude` of exactly `0.0`, caught by the
  configured NYC bounding-box rules
- **Placeholder values** — `Unspecified` in `borough` and `city`, `N/A` in
  `facility_type`; non-null strings that are functionally missing
- **Casing inconsistencies** — variants of the same `complaint_type`
- **Always-null columns** — the taxi, bridge/highway and park fields only apply
  to specific complaint types, so they are empty for most rows

That last category is a good illustration of why the review loop exists: those
columns are not *wrong*, they are conditional. Mark them as false positives once
and they stay suppressed on every future run.

---

## Step 5 — Optional: LLM-assisted deduplication

The categorical cleaning task can send near-duplicate label pairs to Claude,
along with the column's dictionary definition, to judge whether two labels mean
the same thing. It is off by default.

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

Then set `enabled: true` under `llm_dedup` in whichever config you are using.

Each pair costs a small Haiku call; `max_pairs_per_column` caps the spend. If
the key or package is missing, the agent silently falls back to plain string
similarity rather than failing.

---

## Using your own data

1. Write a data dictionary as a Markdown pipe table with at minimum `Variable`
   and `Data Type` columns. See `examples/nyc311/NYC_311_Data_Dictionary.md` for
   a complete worked example.
2. Copy the project template:

   ```bash
   cp -r projects/new_project_template projects/my_project
   ```

3. Edit `projects/my_project/agent_config.yaml` — set `csv_path` and
   `dictionary_path`, then adjust the rules for your domain.
4. Run it:

   ```bash
   python3 -m agent.runner --config projects/my_project/agent_config.yaml
   ```

Each project keeps its own `learnings.json`, so false-positive decisions made on
one dataset never leak into another.

Recognised `Data Type` values are `Boolean`, `Integer`, `Number`, `Timestamp`,
`String` and `Text`. Anything else is reported as an unmappable type rather than
silently ignored.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'agent'`**

You are in the wrong directory. The runner must be invoked from the inner
`data-quality-agent/` folder. Check with `ls` — you should see an `agent`
folder. If you see a folder named `data-quality-agent` instead, go one level
deeper with `cd data-quality-agent`.

**`CSV not found:` / `Data dictionary not found:`**

The agent tells you the exact path it tried and which config key to fix.
Relative paths in a config are resolved against the inner
`data-quality-agent/` directory, not your current working directory.

**`cd: no such file or directory`, then later commands fail strangely**

If a `cd` fails, subsequent commands still run — in whatever directory you were
already in. This can drop downloads and copies in unexpected places. Chain
commands with `&&` so a failed `cd` stops the rest:

```bash
cd ../examples/nyc311 && curl -o nyc311.csv "..."
```

**`ModuleNotFoundError: No module named 'pandas'` (or `yaml`, or `markdown`)**

Dependencies are not installed, or your virtual environment is not active.
Re-run Step 2. If you used a venv, activate it first with
`source .venv/bin/activate`.

**The task selection prompt never appears**

By design. The prompt only shows in an interactive terminal; when output is
piped or redirected, or in CI, all tasks run automatically.

**`CSV contains no data rows`**

The file was found but has only a header. A truncated or failed download is the
usual cause — check the file size and download again.

---

## Where things end up

| Path | Contents |
|---|---|
| `data-quality-agent/outputs/reports/` | Default output — timestamped Markdown reports and the HTML dashboard |
| `data-quality-agent/ci/outputs/reports/` | Output from the synthetic CI run in Step 3 |
| `examples/nyc311/reports/` | Output from the NYC 311 run in Step 4 |
| `data-quality-agent/knowledge/learnings.json` | Human-reviewed false positives, created after your first review session |

Reports are timestamped rather than overwritten, so runs stay comparable over
time and diff cleanly in git.

[nyc311]: https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9
