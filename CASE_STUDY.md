# Case study: NYC 311 Service Requests

A record of what the Data Quality Agent found when pointed at real public data,
and what building it taught us. Every figure below comes from an actual run —
the reports are reproducible by following [QUICKSTART.md](QUICKSTART.md).

**Dataset:** [NYC 311 Service Requests from 2010 to Present][nyc311] (asset
`erm2-nwe9`)
**Sample:** 50,000 rows, 44 columns, retrieved via the Socrata API
**Configuration:** [`examples/nyc311/agent_config.yaml`](examples/nyc311/agent_config.yaml) —
5 domain rules, 3 validation rules

---

## Summary of findings

| Finding | Scale | Why it matters |
|---|---|---|
| `resolution_action_updated_date` earlier than `created_date` | 8,751 rows (20.4%) | Resolution timestamps are truncated to midnight upstream. Any resolution-time metric computed on this data is wrong. |
| `park_facility_name` = `"Unspecified"` | 49,951 rows (100%) | A column that is 0% null and 100% meaningless. |
| `open_data_channel_type` = `"UNKNOWN"` | 3,948 rows (7.9%) | Channel attribution unreliable for roughly 1 in 12 requests. |
| `closed_date` earlier than `created_date` | 53 rows (0.2%) | Sub-minute clock discrepancies between systems. |
| `police_precinct` = `"Unspecified"` | 1,022 rows (2.0%) | Geographic joins will silently drop or misgroup these. |
| `incident_zip` = `"No"` | 1 row | Free-text contamination in a structured field. |
| `longitude` outliers | 627 rows by Z-score | Geocoding failures placing incidents outside NYC. |
| Dictionary coverage | 44/44 columns matched | No schema drift between published dictionary and delivered data. |

---

## The headline finding

The most consequential result is the 20.4% date-ordering violation.

The rule is simple — a request cannot be *updated* before it was *created* — and
it fired on 8,751 of 42,940 evaluable rows. Inspecting the samples shows the
cause immediately:

```
2026-08-18 23:58:19  >  2026-08-18 00:00:00
2026-08-18 23:55:13  >  2026-08-18 00:00:00
2026-08-18 23:49:16  >  2026-08-18 00:00:00
```

`created_date` carries full precision. `resolution_action_updated_date` is
truncated to midnight. For any request created after 00:00 on its resolution
date, the resolution timestamp appears to precede creation.

**Why this is the interesting kind of bug:** every affected record looks
complete. Both fields are populated, both are valid dates, nothing is null. A
completeness check passes. A type check passes. Only a *relational* rule — one
field compared against another — catches it. And the downstream impact is
severe: any dashboard reporting average resolution time on this data produces
plausible-looking numbers that are wrong, and nobody would notice.

---

## Nulls are a weaker signal than they look

The run surfaced 10 high-null columns (over 50% empty) and zero always-null
columns:

| Column | Null rate |
|---|---|
| `taxi_company_borough` | 99.9% |
| `facility_type` | 99.8% |
| `road_ramp` | 99.8% |
| `bridge_highway_direction` | 99.7% |
| `due_date` | 99.7% |
| `bridge_highway_segment` | 99.5% |
| `bridge_highway_name` | 99.5% |
| `taxi_pick_up_location` | 98.8% |
| `vehicle_type` | 95.0% |
| `descriptor_2` | 69.1% |

None of these is a defect. They are *conditional* fields — `vehicle_type` only
applies to taxi complaints, `bridge_highway_name` only to bridge incidents. A
tool that reports ten critical issues here is generating noise, and a reviewer
who sees noise ten runs in a row stops reading the reports.

Set that against `park_facility_name`, which is **0% null and 100%
`"Unspecified"`**. By null rate it is the healthiest column in the dataset. It
contains no information whatsoever.

Two lessons follow:

1. **Null rate alone cannot distinguish broken from conditional.** That judgment
   requires domain knowledge, which is why the agent surfaces candidates with
   evidence and defers the decision to a human, recording it once in the
   knowledge base rather than re-asking every run.
2. **Placeholder detection is not optional.** Functional nulls disguised as
   values — `"Unspecified"`, `"N/A"`, `"UNKNOWN"`, `"Missing"` — are invisible to
   null checks and appeared in nine separate columns in this dataset.

---

## Other findings worth noting

**Type inconsistencies (2).** `latitude` and `longitude` are declared as `Number`
in the published dictionary but hold non-integer floats. This is a dictionary
imprecision rather than a data defect — a good example of a finding a human
should mark as a false positive once, after which it stays suppressed.

**Categorical inconsistencies.** One column with case/whitespace variants, two
with fuzzy near-duplicate pairs, and twelve with low-frequency categories. The
low-frequency findings in `agency` and `agency_name` are mostly legitimate small
agencies (`OTI`, 3 records; `Office of the Sheriff`, 40 records) rather than
data-entry errors — again, exactly the kind of call that needs a human and only
needs making once.

**Outliers.** IQR flagged 1,846 `longitude` values while Z-score flagged 627.
The divergence is the point: longitude here is strongly skewed by geography, so
IQR's robustness to skew makes it the more trustworthy signal. Reporting both
side by side lets the reviewer make that call instead of the tool silently
picking a statistical assumption.

---

## Engineering learnings

### Adversarial fixtures find what normal use does not

Before release, the agent was run against a deliberately hostile dataset: mixed
date formats and timezone offsets in one column, all-null columns, single-valued
columns, unicode and emoji, embedded commas and quotes, leading and trailing
whitespace, placeholder strings, and float values at `1e308`.

It crashed twice. Neither crash was reachable through ordinary use; both were
reachable on the first contact with genuinely messy real data.

### pandas `format="mixed"` needs `utc=True`

Parsing heterogeneous date strings with `format="mixed"` but no `utc=True`
returns **object dtype** rather than `datetime64` whenever UTC offsets vary. Any
downstream `.dt` access then raises `AttributeError`, and pandas emits a
`FutureWarning` warning that this will become a hard error.

```python
# Fails on mixed offsets — returns object dtype
pd.to_datetime(s, errors="coerce", format="mixed")

# Correct
pd.to_datetime(s, errors="coerce", format="mixed", utc=True)
```

Standardised across all 12 parsing sites. Normalising to UTC is safe in this
codebase because every check compares ordering or year ranges rather than local
wall-clock time — a decision worth stating explicitly rather than leaving
implicit.

### Non-finite floats break naive formatting

A display helper contained `if isinstance(v, float) and v == int(v)`. Both
`int(float('inf'))` and `int(float('nan'))` raise. Aggregating columns with
extreme magnitudes overflows to infinity, so this is reachable on real data.
Guard non-finite values before any integer conversion.

### Booleans are numeric to pandas

`pd.api.types.is_numeric_dtype` returns `True` for boolean columns, so boolean
columns flow into IQR computation and fail with
`numpy boolean subtract not supported`. Check `is_bool_dtype` first.

### A quality gate you have never seen fail is not a quality gate

The CI gate's regex patterns were first written against *assumed* report text.
They matched nothing — so the gate passed unconditionally while verifying
nothing, which is worse than having no gate at all, because it looks green.

Patterns were rewritten against actual generated report output, then deliberately
fed data breaching each threshold to confirm the gate fails when it should.

### Optional dependencies must degrade silently

The LLM-assisted deduplication feature degrades through three independent
layers: config disabled, no API key present, package not installed. Any of the
three results in a clean fallback to string similarity. An optional enhancement
should never be capable of breaking the core pipeline.

### Deterministic fixtures make documentation testable

The synthetic data generator is seeded, producing byte-identical output across
runs. That means the expected-findings table in QUICKSTART.md can state exact
numbers rather than approximations, which turns the documentation into a
self-test: if a reader's output differs, something is genuinely wrong.

---

## Design conclusions

**The review loop is the product.** Seven checks that produce findings are
straightforward to build. The hard part is ensuring the findings stay worth
reading by run five. Recording human review decisions and permanently
suppressing confirmed false positives is what separates a tool that gets adopted
from one that gets muted.

**Surface evidence, don't auto-fix.** The agent reports that `"Amend Booking"`
and `"Amend a Booking"` are 92% similar and occur 340 and 12 times respectively.
It does not merge them. Those might be the same disposition entered two ways, or
two genuinely distinct outcomes. The tool cannot know; the analyst can.

**Config over code.** Every threshold, rule, path and exclusion lives in YAML.
The same codebase ran against a fictional SaaS support dataset and against NYC
311 without a line of Python changing. That constraint is what makes the tool
reusable rather than a one-off script.

---

## Reproducing this

```bash
cd examples/nyc311
curl -o nyc311.csv "https://data.cityofnewyork.us/resource/erm2-nwe9.csv?\$limit=50000"
cd ../../data-quality-agent
python -m agent.runner --config ../examples/nyc311/agent_config.yaml
```

Exact figures will differ from those above — 311 is updated daily and the API
returns the most recent records — but the *classes* of finding are stable, and
the date-truncation issue in particular reproduces consistently.

See [QUICKSTART.md](QUICKSTART.md) for full setup, and
[examples/nyc311/README.md](examples/nyc311/README.md) for details on the
configuration.

[nyc311]: https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9
