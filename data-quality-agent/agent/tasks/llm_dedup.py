"""LLM-assisted semantic deduplication.

When ``llm_dedup.enabled`` is true in agent_config.yaml and an
``ANTHROPIC_API_KEY`` environment variable is set, this module passes
fuzzy near-duplicate label pairs to claude-haiku-4-5 with the column's
dictionary definition for context.  The model returns a verdict
(same / different / uncertain) and a one-line reasoning string.

The anthropic package is an optional dependency — when it is not installed
or the API key is absent, this module returns early and findings are
unchanged.

Usage (from categorical_cleaning.py):
    from agent.tasks.llm_dedup import assess_pairs
    fuzzy_pairs = assess_pairs(
        pairs=fuzzy_pairs,
        column=col,
        dict_definition="Human-readable definition from data dictionary",
        cfg=config.get("llm_dedup", {}),
    )

Each pair dict gains two extra keys when the LLM is invoked:
    "llm_verdict":    "same" | "different" | "uncertain"
    "llm_reasoning":  one-line explanation
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_VERDICTS = frozenset({"same", "different", "uncertain"})

_SYSTEM_PROMPT = """\
You are a data quality expert reviewing label variants in a categorical column.
For each pair of labels, decide whether they represent the same concept and
should be merged in the data.

Respond with a JSON object matching this schema exactly:
{
  "verdict": "same" | "different" | "uncertain",
  "reasoning": "<one sentence, max 20 words>"
}

Rules:
- "same"      — the labels clearly refer to the same real-world concept.
- "different" — the labels clearly refer to distinct real-world concepts.
- "uncertain" — not enough context to be sure; a domain expert should decide.
"""


def assess_pairs(
    *,
    pairs: list[dict[str, Any]],
    column: str,
    dict_definition: str,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return `pairs` with optional llm_verdict / llm_reasoning keys added.

    Parameters
    ----------
    pairs:
        Output of ``_fuzzy_pairs()`` — list of dicts with keys
        'a', 'b', 'similarity', 'count_a', 'count_b'.
    column:
        Column name (used in the prompt for context).
    dict_definition:
        Dictionary definition for this column (may be empty string).
    cfg:
        The ``llm_dedup`` config block.  Expected keys:
        - enabled (bool, default False)
        - model (str, default "claude-haiku-4-5-20251001")
        - min_similarity (float, default 0.70) — lower floor; only pairs
          at or above this similarity are sent to the LLM.  Pairs already
          above the main fuzzy threshold were surfaced by difflib; this
          floor lets the LLM evaluate borderline cases too.
        - max_pairs_per_column (int, default 10)
        - timeout (int seconds, default 10)
    """
    if not cfg.get("enabled", False):
        return pairs

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.debug("llm_dedup: ANTHROPIC_API_KEY not set — skipping LLM assessment")
        return pairs

    try:
        import anthropic  # optional dependency
    except ImportError:
        log.warning("llm_dedup: 'anthropic' package not installed — run: pip install anthropic")
        return pairs

    model = cfg.get("model", "claude-haiku-4-5-20251001")
    min_sim = float(cfg.get("min_similarity", 0.70))
    max_pairs = int(cfg.get("max_pairs_per_column", 10))
    timeout = int(cfg.get("timeout", 10))

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    assessed = 0

    for pair in pairs:
        if assessed >= max_pairs:
            break
        if pair.get("similarity", 0) < min_sim:
            continue
        if "llm_verdict" in pair:
            continue  # already assessed (e.g. from cache)

        a, b = pair["a"], pair["b"]
        user_msg = (
            f"Column: {column}\n"
            f"Definition: {dict_definition or 'No definition available.'}\n"
            f"\nPair to evaluate:\n"
            f"  Label A: {a!r}  (appears {pair['count_a']:,} times)\n"
            f"  Label B: {b!r}  (appears {pair['count_b']:,} times)\n"
            f"  String similarity score: {pair['similarity']:.0%}\n"
        )

        try:
            response = client.messages.create(
                model=model,
                max_tokens=120,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if the model wraps the JSON.
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            parsed = json.loads(raw)
            verdict = parsed.get("verdict", "uncertain").lower()
            if verdict not in _VERDICTS:
                verdict = "uncertain"
            pair["llm_verdict"] = verdict
            pair["llm_reasoning"] = parsed.get("reasoning", "")
            assessed += 1
        except Exception as exc:  # network errors, JSON parse failures, etc.
            log.warning("llm_dedup: error assessing pair (%r, %r): %s", a, b, exc)
            pair["llm_verdict"] = "uncertain"
            pair["llm_reasoning"] = f"Assessment failed: {exc}"

    return pairs
