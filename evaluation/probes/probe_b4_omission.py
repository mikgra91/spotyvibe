"""B-4. Omission discipline.

Mixes 25 fictitious-sounding artist names with 5 genuinely-famous ones.
A well-calibrated model adds the 25 fictitious to ``unknown_artists`` and
leaves the 5 famous ones out. A padding model marks fewer than it should,
or marks famous artists as unknown (poor precision).

Scores:
    precision = |unknown ∩ fictitious| / |unknown|
    recall    = |unknown ∩ fictitious| / |fictitious|
    padding   = |famous ∩ unknown| / |famous|   (false-positive rate)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROBE_ID = "B-4.omission_discipline"
VARIANTS = ["mixed"]
RUNS_PER_VARIANT = {"mixed": 1}


_ALLOWLIST_PATH = Path(__file__).parent / "allowlists" / "famous_artists.json"


def _load_allowlists() -> tuple[list[str], list[str]]:
    data = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return list(data["famous"]), list(data["fictitious"])


_FAMOUS, _FICTITIOUS = _load_allowlists()
_ALL_ARTISTS = _FAMOUS + _FICTITIOUS                          # ordering preserved later


_SYSTEM = (
    "You answer with valid JSON only. No prose, no markdown fences. "
    "Schema: {\"unknown_artists\": [\"name\", ...]}."
)


def _build_user_message() -> str:
    bullet_list = "\n".join(f"- {a}" for a in _ALL_ARTISTS)
    return (
        "ARTISTS:\n"
        f"{bullet_list}\n\n"
        "For each artist above for which you cannot confidently name a "
        "real released track, add the artist's name VERBATIM to "
        "'unknown_artists'. Do NOT include artists you can confidently "
        "name a real released track of. JSON only."
    )


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "unknown_artists",
        "schema": {
            "type": "object",
            "properties": {
                "unknown_artists": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["unknown_artists"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def build_messages(variant: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _build_user_message()},
    ]


def response_format(variant: str) -> dict | None:
    return _SCHEMA


def _norm(name: str) -> str:
    return name.strip().lower()


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    declared: list[str] = []
    if isinstance(parsed, dict):
        v = parsed.get("unknown_artists")
        if isinstance(v, list):
            declared = [str(x) for x in v if isinstance(x, (str, int, float))]

    declared_set    = {_norm(x) for x in declared}
    famous_set      = {_norm(x) for x in _FAMOUS}
    fictitious_set  = {_norm(x) for x in _FICTITIOUS}

    true_pos  = declared_set & fictitious_set
    false_pos = declared_set & famous_set

    precision = len(true_pos) / len(declared_set) if declared_set    else 0.0
    recall    = len(true_pos) / len(fictitious_set)
    padding   = len(false_pos) / len(famous_set) if famous_set       else 0.0

    return {
        "declared_count":         float(len(declared_set)),
        "true_positive":          float(len(true_pos)),
        "false_positive":         float(len(false_pos)),
        "omission_precision":     precision,
        "omission_recall":        recall,
        "padding_rate":           padding,
    }
