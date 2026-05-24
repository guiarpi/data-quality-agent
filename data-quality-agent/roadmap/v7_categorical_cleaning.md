# V7 — Categorical Cleaning Task

**Status:** Planned

## Goal

Identify categorical columns where the same concept appears under multiple labels,
and surface candidates for consolidation. This is the most complex task because it
requires a mix of exact matching, fuzzy string matching, and potentially LLM-based
semantic reasoning.

Examples from the CBC data set:
- "chat translated" vs "Chat Translated" vs "CHAT_TRANSLATED" (case variants)
- "original lanuage" vs "original language" (typo — already seen in the data)
- Disposition codes that are near-duplicates: "Amend Booking" vs "Amend a Booking"
- Low-frequency categories that could be merged into an "Other" bucket

## What it would check

| Check | Method |
| --- | --- |
| Case variants | Casefold + exact match |
| Whitespace variants | Strip + normalize spaces |
| Typo/near-duplicates | difflib or rapidfuzz similarity |
| Semantic duplicates | LLM reasoning (future) |
| Low-frequency categories | Count-based threshold |
| Category count vs expectation | Compare to dictionary definition if available |

## Output

For each categorical column, the report would show:
- Total distinct values
- Suggested merge groups (near-duplicates)
- Low-frequency values below a configurable threshold
- Proposed canonical name for each group

## Why this is last

Categorical cleaning is the most subjective task. Whether "Amend Booking" and
"Amend a Booking" should be merged depends on business context that only a domain
expert can confirm. The human review loop becomes especially important here — the
agent surfaces candidates, the human decides.

It also benefits from all prior tasks being complete:
- Nulls are understood (v2) so we know the true cardinality
- Types are profiled (v3) so we only apply this to genuinely categorical columns
- Invalid entries are cleaned (v5) so near-duplicate detection isn't confused
  by placeholder values

## Connection to the knowledge base

Merge decisions are high-value learnings to persist:
- "Amend Booking" and "Amend a Booking" → canonical: "Amend Booking"
- Resolution: `confirmed_issue` with note explaining the merge

On future data refreshes, the agent can flag if new variants of a known category
appear.

## LLM integration opportunity

This task is the strongest candidate for an LLM call. Semantic duplicates
("Cancel reservation" vs "Booking cancellation") are hard to detect with string
similarity but straightforward for a language model. A future version could:

1. Detect fuzzy candidates with difflib
2. Pass borderline pairs to Claude with context from the data dictionary
3. Surface the LLM's reasoning to the human reviewer alongside the suggestion

## New config options to consider

```yaml
categorical_cleaning:
  max_cardinality: 50             # only analyse columns with fewer than N distinct values
  similarity_threshold: 0.85      # difflib cutoff for near-duplicate detection
  low_frequency_threshold: 0.01   # flag categories representing < 1% of rows
  columns_include: []             # if set, only analyse these columns
  columns_exclude: []             # columns to skip (e.g. free-text fields)
```

## Open questions

- Should suggested merges be applied automatically (with confirmation) or only
  reported?
- If applied, should changes be made to the CSV or written to a separate
  "cleaning script" that the user can run themselves?
- At what cardinality does a column stop being categorical? (The data types task
  should inform this threshold.)
