"""Generate a synthetic CSV for CI runs.

The CSV covers all columns declared in the SaaS support contact data
dictionary.  Values are synthetic but realistic — they exercise every task
(type profiling, null detection, outliers, categorical cleaning, etc.)
without requiring any real customer data in the repository.

Run from the data-quality-agent/ directory:
    python ci/generate_ci_data.py
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

SEED = 42
N_ROWS = 2_000
OUT_PATH = Path("ci/outputs/contacts_ci.csv")

rng = random.Random(SEED)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _choice(opts: list, n: int = N_ROWS, null_rate: float = 0.0) -> list:
    result = [rng.choice(opts) for _ in range(n)]
    if null_rate:
        for i in range(n):
            if rng.random() < null_rate:
                result[i] = None
    return result


def _int_col(lo: int, hi: int, n: int = N_ROWS, null_rate: float = 0.0) -> list:
    result = [rng.randint(lo, hi) for _ in range(n)]
    if null_rate:
        for i in range(n):
            if rng.random() < null_rate:
                result[i] = None
    return result


def _timestamp(n: int = N_ROWS, null_rate: float = 0.0) -> list:
    result = [
        f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} "
        f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        for _ in range(n)
    ]
    if null_rate:
        for i in range(n):
            if rng.random() < null_rate:
                result[i] = None
    return result


# ── Build DataFrame ───────────────────────────────────────────────────────────

df = pd.DataFrame(
    {
        "CONTACT_ID": [f"CNT-{i:06d}" for i in range(1, N_ROWS + 1)],
        "CONTACT_DATE": _timestamp(),
        "CONTACT_MONTH": [
            f"2024-{rng.randint(1, 12):02d}" for _ in range(N_ROWS)
        ],
        "CHANNEL": _choice(
            # Introduce case variants to exercise categorical_cleaning
            ["email", "Email", "EMAIL", "chat", "Chat", "phone", "portal"],
        ),
        "QUEUE_ENTER_AT": _timestamp(),
        "QUEUE_EXIT_AT": _timestamp(),
        "WAIT_TIME_SEC": _int_col(0, 600),
        "AGENT_ID": [f"AGT-{rng.randint(1, 50):03d}" for _ in range(N_ROWS)],
        "AGENT_TEAM": _choice(["Tier 1", "Tier 2", "tier 2", "Escalation", "Billing"]),
        "PREVIOUS_AGENT_ID": _choice(
            [f"AGT-{i:03d}" for i in range(1, 51)], null_rate=0.6
        ),
        "IS_TRANSFER": _choice([True, False]),
        "TRANSFER_COUNT": _int_col(0, 3, null_rate=0.05),
        "IS_ABANDONED": _choice([True, False]),
        "RESOLVED_AT": _timestamp(null_rate=0.15),
        "TOTAL_HANDLING_TIME_SEC": _int_col(30, 3600, null_rate=0.05),
        "HOLD_TIME_SEC": _int_col(0, 600),
        "WRAP_UP_TIME_SEC": _int_col(0, 300),
        "DISPOSITION": _choice(
            [
                "Resolved",
                "Escalated",
                "Unresolved",
                "Amend Booking",
                "Amend a Booking",   # fuzzy near-duplicate for testing
                "Cancel",
                "cancel",            # case variant
                "Refund",
            ]
        ),
        "NPS_SCORE": _int_col(0, 10, null_rate=0.30),
        "CSAT_SCORE": _int_col(1, 5, null_rate=0.25),
        "IS_REPEAT_CONTACT": _choice([True, False]),
        "REPEAT_CONTACT_REASON": _choice(
            ["Unresolved issue", "Follow-up", "Misrouted", None], null_rate=0.50
        ),
        "PLAN_TIER": _choice(["Free", "Starter", "Growth", "Enterprise"]),
        "CUSTOMER_TENURE_DAYS": _int_col(0, 1800),
        "CUSTOMER_JOURNEY_STAGE": _choice(
            ["Onboarding", "Adoption", "Expansion", "Retention", "At Risk"]
        ),
        "IS_CHURNED": _choice([True, False]),
        "AI_DEFLECTED": _choice([True, False]),
        "AI_ASSISTED": _choice([True, False]),
        "AI_CONFIDENCE_SCORE": [
            round(rng.uniform(0, 1), 3) for _ in range(N_ROWS)
        ],
        # High-null column to exercise missing_values task
        "AI_CONVERSATION_SUMMARY": _choice(["Summary A", "Summary B"], null_rate=0.85),
        "LANGUAGE": _choice(["en", "es", "fr", "de", "pt"]),
        "IS_TRANSLATED": _choice([True, False]),
        "PAGE_SOURCE": [f"https://app.example.com/page/{rng.randint(1,100)}" for _ in range(N_ROWS)],
        "SESSION_ID": [f"SES-{rng.randint(100000, 999999)}" for _ in range(N_ROWS)],
        "CUSTOMER_INITIAL_QUERY": _choice(
            ["How do I cancel?", "Billing question", "Technical issue", None], null_rate=0.10
        ),
        "CUSTOMER_COMMENT": _choice(
            ["Great service!", "Poor experience", "Average", None], null_rate=0.40
        ),
    }
)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_PATH, index=False)
print(f"Generated {len(df):,} rows → {OUT_PATH}")
