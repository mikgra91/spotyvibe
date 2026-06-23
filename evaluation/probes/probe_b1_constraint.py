"""B-1. Constraint-grammar sensitivity (MUST vs SHOULD vs MAY).

Predicts whether a prompt switching from SHOULD to MUST will surprise-
collapse the model — the R1.3-strict finding (next-steps.md §B-1).

Task: return 8 English colour words; the secondary constraint varies in
strength across three variants:
    - soft           : SHOULD avoid colours containing 'e'
    - hard           : MUST avoid colours containing 'e'
    - hard_with_quota: MUST contain >= 6 colours avoiding 'e'

The load-bearing score is ``quota_preserved_under_hard`` — a model that
drops the primary 8-colour quota to satisfy the hard avoid-'e'
constraint will score 0 here (mini did exactly this on R1.3-strict).
"""

from __future__ import annotations

from typing import Any


PROBE_ID = "B-1.constraint_grammar"
VARIANTS = ["soft", "hard", "hard_with_quota"]
RUNS_PER_VARIANT = {"soft": 1, "hard": 1, "hard_with_quota": 1}


_SYSTEM = (
    "You answer with valid JSON only. No prose, no markdown fences. "
    "Schema: {\"colours\": [\"colour\", ...]}."
)


_USER_BY_VARIANT = {
    "soft": (
        "Return a JSON list of 8 colours, each a single English word. "
        "SHOULD avoid colours containing the letter 'e'."
    ),
    "hard": (
        "Return a JSON list of 8 colours, each a single English word. "
        "MUST avoid colours containing the letter 'e'."
    ),
    "hard_with_quota": (
        "Return a JSON list of 8 colours, each a single English word. "
        "MUST contain at least 6 colours that do NOT contain the letter 'e'."
    ),
}


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "colour_list",
        "schema": {
            "type": "object",
            "properties": {
                "colours": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["colours"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def build_messages(variant: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _USER_BY_VARIANT[variant]},
    ]


def response_format(variant: str) -> dict | None:
    return _SCHEMA


def _extract_colours(parsed: Any) -> list[str]:
    if isinstance(parsed, dict):
        col = parsed.get("colours")
        if isinstance(col, list):
            return [str(c).strip() for c in col if isinstance(c, (str, int, float))]
    if isinstance(parsed, list):
        return [str(c).strip() for c in parsed if isinstance(c, (str, int, float))]
    return []


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    colours = _extract_colours(parsed)
    n = len(colours)
    avoid_e_count = sum(1 for c in colours if "e" not in c.lower())
    primary_quota_met = 1.0 if n == 8 else 0.0
    avoid_rate = (avoid_e_count / n) if n else 0.0

    out: dict[str, float] = {
        "returned_count":           float(n),
        "primary_quota_met":        primary_quota_met,
        "avoid_e_rate":             avoid_rate,
    }

    if variant == "soft":
        out["soft_compliance"] = avoid_rate
    elif variant == "hard":
        out["hard_compliance"] = 1.0 if avoid_e_count == n and n > 0 else 0.0
    elif variant == "hard_with_quota":
        # Both quotas must hold simultaneously.
        out["hard_compliance"] = 1.0 if avoid_e_count == n and n > 0 else 0.0
        out["secondary_quota_met"] = 1.0 if avoid_e_count >= 6 else 0.0
        out["quota_preserved_under_hard"] = (
            1.0 if (primary_quota_met == 1.0 and avoid_e_count >= 6) else 0.0
        )
    return out
