# V5 — Invalid Entries Task

**Status:** Complete

## Goal

Flag values that are syntactically or semantically malformed — values that could
exist numerically but are clearly wrong in context. Distinct from impossible values
(which are about range/logic) — invalid entries are about format and referential
integrity.

Examples:
- An email address column containing values without "@"
- A reservation ID that doesn't match the expected format
- A language code that is not a valid ISO 639-1 code
- A free-text field containing placeholder values ("N/A", "null", "test", "123")

## What it would check

| Check type | Example |
| --- | --- |
| Format pattern | Reservation ID matches expected regex |
| Reference list | LANGUAGE is a valid ISO language code |
| Placeholder detection | Values like "N/A", "n/a", "NULL", "TBD", "test" treated as de-facto nulls |
| Whitespace anomalies | Leading/trailing spaces, double spaces in string columns |
| Encoding issues | Non-printable characters, unexpected unicode |

## Where validation rules come from

Similar to impossible values — requires a rules file:
```yaml
invalid_entries:
  - column: LANGUAGE
    valid_values_file: "reference/iso_language_codes.csv"
  - column: RESERVATION_ID
    pattern: "^[A-Z]{2}[0-9]{8}$"
  - columns: [CHANNEL, BRAND, HANDLING_TYPE]
    flag_placeholders: true
```

Reference lists (ISO codes, country codes, etc.) can be bundled as small CSV files
inside the project folder.

## Placeholder detection

A common and valuable check that requires no configuration. A shared list of
placeholder strings ("n/a", "none", "null", "unknown", "tbd", "-", ".", "0" in
string columns, etc.) can be detected automatically and surfaced for human review.
These are technically non-null but functionally missing.

## Connection to v2 (missing values)

Placeholder detection extends the missing values task. A column might appear to
have a low null rate but actually have many functional nulls disguised as "N/A"
or "Unknown". Combining both tasks gives a true picture of data completeness.

## Open questions

- Should placeholder detection be part of the missing values task (v2) rather
  than a separate task?
- How do we manage reference lists (ISO codes, etc.) — ship a default set or
  require the user to supply them?
