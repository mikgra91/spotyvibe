"""B-10. Cite-rate fidelity (verbatim vs paraphrase).

Predicts R1.1's cite-rate parity question. Each pick MUST contain a
``cite`` field that is a verbatim substring of the supplied TASTE line.

Healthy: ``verbatim_rate >= 0.9``.
Paraphrasing models score below 0.5 — they pick semantically-correct but
not-substring values for ``cite``.
"""

from __future__ import annotations

from typing import Any


PROBE_ID = "B-10.cite_fidelity"
VARIANTS = ["verbatim_substring"]
RUNS_PER_VARIANT = {"verbatim_substring": 1}


_TASTE_LINE = (
    "Must: dreamy ambient, slow-builds, soft synthesisers, gentle textures, "
    "calm meditative pace. Avoid: harsh distortion, aggressive percussion."
)


_SYSTEM = (
    "You answer with valid JSON only. No prose, no markdown fences. "
    "Schema: {\"picks\": [{\"title\": str, \"cite\": str}, ...]}."
)


_USER = (
    f"TASTE: '{_TASTE_LINE}'\n\n"
    "Return exactly 5 fictional song-title picks for this taste. Each pick "
    "MUST contain a 'cite' field that is a VERBATIM SUBSTRING of the TASTE "
    "line above — not paraphrased, not summarised, not rewritten. Match "
    "the substring exactly including punctuation and spacing."
)


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cite_picks",
        "schema": {
            "type": "object",
            "properties": {
                "picks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "cite":  {"type": "string"},
                        },
                        "required": ["title", "cite"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["picks"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


_TARGET_PICKS = 5


def build_messages(variant: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _USER},
    ]


def response_format(variant: str) -> dict | None:
    return _SCHEMA


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    picks: list = []
    if isinstance(parsed, dict):
        v = parsed.get("picks")
        if isinstance(v, list):
            picks = v
    if not picks:
        return {
            "returned_count":       0.0,
            "verbatim_rate":        0.0,
            "any_nonempty_cite":    0.0,
        }

    verbatim_count = 0
    nonempty_count = 0
    for p in picks:
        if not isinstance(p, dict):
            continue
        cite = str(p.get("cite") or "").strip()
        if cite:
            nonempty_count += 1
            if cite in _TASTE_LINE:
                verbatim_count += 1

    n = len(picks)
    return {
        "returned_count":     float(n),
        "verbatim_rate":      verbatim_count / n if n else 0.0,
        "any_nonempty_cite":  1.0 if nonempty_count > 0 else 0.0,
        "target_picks":       float(_TARGET_PICKS),
    }
