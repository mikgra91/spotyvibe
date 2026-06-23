"""B-2. Over-constraint collapse (output-shape inflation).

Direct analogue of R1.3-strict: mini inflated ``omitted_artists`` to
(N-M) and dropped picks. We test whether a secondary "MUST be huge"
constraint causes the primary playlist to shrink.

Variants:
    - free   : Request 10 picks + AIM for >= 20 rejected_candidates.
    - strict : Request 10 picks + MUST contain >= 20 rejected_candidates.

The load-bearing score is ``primary_length_ratio`` (returned / 10):
    1.0  = healthy (10 picks, secondary quota irrelevant)
    < 1.0 = collapse — model traded picks for rejected_candidates.
"""

from __future__ import annotations

from typing import Any


PROBE_ID = "B-2.over_constraint_collapse"
VARIANTS = ["free", "strict"]
RUNS_PER_VARIANT = {"free": 1, "strict": 1}


_SYSTEM = (
    "You answer with valid JSON only. No prose, no markdown fences. "
    "Schema: {\"playlist\": [\"song title\", ...], "
    "\"rejected_candidates\": [{\"title\": str, \"reason\": str}, ...]}."
)


_USER_FREE = (
    "Return 10 song-title suggestions for a hypothetical 'cyberpunk lo-fi' "
    "playlist. Also return rejected_candidates with reasons; AIM for at "
    "least 20."
)
_USER_STRICT = (
    "Return 10 song-title suggestions for a hypothetical 'cyberpunk lo-fi' "
    "playlist. Also return rejected_candidates with reasons. MUST contain "
    ">= 20 rejected_candidates."
)


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "playlist_with_rejects",
        "schema": {
            "type": "object",
            "properties": {
                "playlist": {"type": "array", "items": {"type": "string"}},
                "rejected_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title":  {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["title", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["playlist", "rejected_candidates"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


_PRIMARY_TARGET = 10
_SECONDARY_TARGET = 20


def build_messages(variant: str) -> list[dict]:
    user = _USER_FREE if variant == "free" else _USER_STRICT
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user},
    ]


def response_format(variant: str) -> dict | None:
    return _SCHEMA


def _lengths(parsed: Any) -> tuple[int, int]:
    if not isinstance(parsed, dict):
        return 0, 0
    primary = parsed.get("playlist") or []
    secondary = parsed.get("rejected_candidates") or []
    return (
        len(primary)   if isinstance(primary, list)   else 0,
        len(secondary) if isinstance(secondary, list) else 0,
    )


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    primary_len, secondary_len = _lengths(parsed)
    return {
        "primary_length":         float(primary_len),
        "secondary_length":       float(secondary_len),
        "primary_length_ratio":   primary_len / _PRIMARY_TARGET,
        "secondary_quota_met":    1.0 if secondary_len >= _SECONDARY_TARGET else 0.0,
        "primary_target":         float(_PRIMARY_TARGET),
        "secondary_target":       float(_SECONDARY_TARGET),
    }
