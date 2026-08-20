# Example: NYC 311 Service Requests

A ready-to-run configuration that points the agent at a real, messy, public
dataset — [NYC 311 Service Requests from 2010 to Present][dataset]
(asset `erm2-nwe9`, ~24M rows, 44 columns, updated daily).

This dataset is a good test case because it is genuinely dirty: bad geocodes,
`Unspecified` and `N/A` placeholders standing in for nulls, casing
inconsistencies in complaint types, and columns that are almost entirely empty.

## 1. Download a sample

Pull 50,000 rows via the Socrata API. This returns snake_case headers that match
the bundled data dictionary exactly:

```bash
cd examples/nyc311

curl -o nyc311.csv \
  "https://data.cityofnewyork.us/resource/erm2-nwe9.csv?\$limit=50000"
```

Want a specific slice instead? SoQL supports filtering:

```bash
# Only 2024 Brooklyn requests
curl -o nyc311.csv \
  "https://data.cityofnewyork.us/resource/erm2-nwe9.csv?\$limit=50000&\$where=created_date%20between%20'2024-01-01'%20and%20'2024-12-31'&borough=BROOKLYN"
```

> **Note on the portal Export button.** Downloading through the website's
> Export button produces Title Case headers (`Unique Key`, `Created Date`)
> rather than snake_case (`unique_key`, `created_date`). The bundled dictionary
> uses snake_case, so prefer the API command above. If you do use the portal
> export, rename the dictionary's `Variable` values to match.

## 2. Run the agent

```bash
cd ../../data-quality-agent
python -m agent.runner --config ../examples/nyc311/agent_config.yaml
```

Reports land in `examples/nyc311/reports/`, including the combined
`data_quality_dashboard_*.html`.

## 3. What you should expect to see

Running against a real 50k sample typically surfaces:

| Task | Representative findings |
|---|---|
| `data_dictionary` | Full column coverage; a few type mismatches where numeric-looking IDs are stored as text |
| `missing_values` | Many always-null columns — the taxi, bridge/highway and park fields only apply to specific complaint types |
| `data_types` | `unique_key` detected as an identifier; `latitude`/`longitude` as decimals; timestamps parsed correctly |
| `impossible_values` | `0.0` latitude/longitude from failed geocoding; requests closed before they were created |
| `invalid_entries` | `Unspecified` in `borough`/`city`, `N/A` in `facility_type`, malformed `incident_zip` values |
| `outliers` | Coordinate outliers from bad geocodes |
| `categorical_cleaning` | Casing variants in `complaint_type` (e.g. `Illegal Parking` vs `Illegal parking`) and `open_data_channel_type` |

Many of these are *expected* rather than wrong — the conditional columns really
are null for most rows. That is exactly what the review loop is for: mark them
as false positives once, and they stay suppressed in
`examples/nyc311/learnings.json` on every later run.

## Files

| File | Purpose |
|---|---|
| `NYC_311_Data_Dictionary.md` | 44 variables with official definitions and types, transcribed from the dataset's published column metadata |
| `agent_config.yaml` | Paths, plus 5 domain rules and 3 validation rules tuned to this schema |
| `nyc311.csv` | Your downloaded sample (gitignored — not committed) |
| `reports/` | Generated Markdown + HTML output |

## Other datasets worth trying

| Dataset | Why it's a good test | Dictionary |
|---|---|---|
| [CMS Medicare Physician & Other Practitioners][cms] | ~10M rows, strict numeric/currency fields, formal methodology doc | Published data dictionary + methodology PDF |
| [NYC TLC Trip Records][tlc] | Huge, well-documented, classic impossible-value cases (negative fares, zero-distance trips) | PDF data dictionary per service type |
| [UK Police Street-Level Crime][ukpolice] | Monthly CSVs, lots of nulls and category churn over time | Published field definitions |

[dataset]: https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9
[cms]: https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners
[tlc]: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
[ukpolice]: https://data.police.uk/data/
