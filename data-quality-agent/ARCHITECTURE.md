# Data Quality Agent — Architecture

```mermaid
flowchart TD

    subgraph INPUTS ["  Inputs  "]
        CSV[("CSV File")]
        MD[("Data Dictionary\n.md file")]
        CFG["agent_config.yaml\ncsv_path · dict_path\nsample_rows · thresholds"]
    end

    subgraph ANALYSIS ["  DataDictionaryTask  "]
        PARSE["Parse dictionary\nread markdown pipe table"]
        SAMPLE["Sample CSV\n50 000 rows"]
        GAPS["Gap analysis\n① Missing definitions\n   CSV cols with no dict entry\n② Dictionary-only vars\n   dict entries absent from CSV\n③ Type inconsistencies\n   boolean / integer / timestamp / string"]
        FILTER["Filter via Knowledge Base\nremove known false positives\nannotate confirmed issues\nwith prior human notes"]
    end

    subgraph KB_STORE ["  Knowledge Base  "]
        KB[("learnings.json\ncolumn · issue_type\nresolution · note\ncreated_at")]
    end

    subgraph OUTPUTS ["  Outputs  "]
        REPORT[("Markdown Report\noutputs/reports/\ndata_dictionary_report_\nYYYYMMDD_HHMMSS.md")]
    end

    subgraph REVIEW ["  Human Review Loop (terminal)  "]
        SHOW["Show finding\n+ fuzzy match suggestions\n  difflib similarity score"]
        DECIDE{"Human\ndecision"}
        FIX["[m] Fix dictionary\nrename variable in .md\npreserves all other content"]
        LABEL["[f] false positive\n[c] confirmed issue\n[k] known exception\nsave to learnings.json"]
    end

    subgraph NEXT ["  Next Run  "]
        SUPPRESS["Known false positives\nsuppressed automatically\nReport focuses on\nnew / unresolved issues"]
    end

    %% Data flow into analysis
    CFG --> ANALYSIS
    CSV --> SAMPLE
    MD --> PARSE
    KB --> FILTER

    %% Internal analysis flow
    PARSE --> GAPS
    SAMPLE --> GAPS
    GAPS --> FILTER

    %% Analysis outputs
    FILTER --> REPORT
    FILTER --> SHOW

    %% Review loop
    SHOW --> DECIDE
    DECIDE -->|naming mismatch| FIX
    DECIDE -->|label finding| LABEL

    %% Feedback back into source files
    FIX -->|updates| MD
    LABEL -->|persists to| KB

    %% Knowledge base feeds next run
    KB -.->|"loaded at start\nof every run"| FILTER

    %% Next run outcome
    KB --> SUPPRESS
```

## Component summary

| Component | File | Purpose |
| --- | --- | --- |
| Runner | `agent/runner.py` | CLI entry point, loads config, calls tasks then review |
| Task — Data Dictionary | `agent/tasks/data_dictionary.py` | Gap detection: missing definitions, extra vars, type conflicts |
| Task — Missing Values | `agent/tasks/missing_values.py` | Null profiling: always-null, high-null columns |
| Task — Data Types | `agent/tasks/data_types.py` | Column profiling: semantic type, cardinality, stats, samples |
| Task — Impossible Values | `agent/tasks/impossible_values.py` | Domain rule evaluation: range, date order, logical dependency |
| Task — Invalid Entries | `agent/tasks/invalid_entries.py` | Format checks: enum, regex pattern, placeholder detection, whitespace |
| Task — Outliers | `agent/tasks/outliers.py` | IQR + Z-score on numeric columns; temporal outliers on timestamps |
| Task — Categorical Cleaning | `agent/tasks/categorical_cleaning.py` | Case variants, fuzzy near-duplicates (difflib), low-frequency categories |
| Reviewer | `agent/review/reviewer.py` | Interactive terminal loop, fuzzy suggestions, dictionary fix |
| Knowledge Base | `knowledge/knowledge_base.py` | Load / save / query learnings.json |
| Config | `projects/<name>/agent_config.yaml` | Per-project paths and thresholds |
| Learnings | `projects/<name>/knowledge/learnings.json` | Human decisions, isolated per project |

## The feedback loop in plain English

1. **Run** — agent compares CSV against dictionary, filters anything already reviewed, writes report
2. **Review** — human labels each finding; naming mismatches can fix the dictionary in place
3. **Learn** — labels persist to `learnings.json`
4. **Next run** — false positives are silently suppressed; the report shrinks to only what is new or unresolved
