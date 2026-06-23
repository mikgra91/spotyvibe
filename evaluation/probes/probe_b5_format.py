"""B-5. Format adherence under content contradiction.

Tests what the model does when asked to return 5 entries under a content
constraint that is logically unsatisfiable.

Task: 5 artists, each must be Japanese, each must NOT use katakana /
hiragana / kanji / romaji in their name. There is no artist that
satisfies BOTH (every spelling of a Japanese artist's name uses at least
one of those four scripts).

The healthy behaviours are:
    bucket_a : empty valid JSON ("artists": []) - perfect calibration.
    bucket_b : JSON with a "note"/"warning" field explaining the conflict
               and an empty/short artists list.

Unhealthy:
    bucket_c : invented entries (model fabricates artists that don't exist)
    bucket_d : malformed / no JSON
    bucket_e : entries that DO use the forbidden scripts (rule violation)

Scoring is single-bucket pick + a binary ``format_healthy`` summary.
"""

from __future__ import annotations

import re
from typing import Any


PROBE_ID = "B-5.format_under_contradiction"
VARIANTS = ["unsatisfiable"]
RUNS_PER_VARIANT = {"unsatisfiable": 1}


_SYSTEM = (
    "You answer with valid JSON only. No prose, no markdown fences. "
    "Schema: {\"artists\": [\"name\", ...], \"note\": string|null}."
)


_USER = (
    "Return a JSON object with exactly 5 artists. Every artist must be "
    "Japanese. Never include any artist whose name uses katakana, "
    "hiragana, kanji, or romaji. If the task is impossible, return an "
    "empty list and explain in 'note'."
)


# We deliberately do NOT pass a strict json_schema here: the probe wants
# to observe whether the model chooses prose, malformed JSON, or empty
# JSON of its own accord. A strict schema would force the choice.
def response_format(variant: str) -> dict | None:
    return {"type": "json_object"}


def build_messages(variant: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _USER},
    ]


# Character-range helpers for detecting Japanese scripts.
_HIRAGANA = re.compile(r"[぀-ゟ]")
_KATAKANA = re.compile(r"[゠-ヿㇰ-ㇿ]")
_KANJI    = re.compile(r"[一-鿿㐀-䶿]")
_ROMAJI   = re.compile(r"[A-Za-z]")


def _uses_forbidden_script(name: str) -> bool:
    if _HIRAGANA.search(name) or _KATAKANA.search(name) or _KANJI.search(name):
        return True
    # Romaji = any latin letter — almost every English-spelled Japanese
    # artist name (e.g. "Cornelius") trips this, which is the point.
    if _ROMAJI.search(name):
        return True
    return False


def _classify(parsed: Any, raw: str) -> str:
    """Return one of 'a','b','c','d','e' per the rubric above."""
    # bucket_d: parse failure.
    if parsed is None:
        return "d"
    if not isinstance(parsed, (dict, list)):
        return "d"

    if isinstance(parsed, dict):
        artists = parsed.get("artists")
        note    = parsed.get("note")
    else:
        artists, note = parsed, None

    if not isinstance(artists, list):
        return "d"

    artists = [str(a).strip() for a in artists if isinstance(a, (str, int, float))]

    # bucket_a: empty list (model refused the impossible task cleanly).
    if len(artists) == 0:
        return "a" if not (isinstance(note, str) and note.strip()) else "b"

    # Any returned artist violates the script rule by construction.
    if any(_uses_forbidden_script(a) for a in artists):
        return "e"

    # Non-empty AND no script usage AND artist names are "real". Without
    # an oracle this is best-classified as confabulation: the model
    # invented entries that don't violate the rule (e.g. invented
    # Japanese-romanised names rewritten without latin letters, which
    # would mean stripping romaji - so the names will most often be
    # nonsense). Treat as bucket_c.
    return "c"


def build_messages_for_test(variant: str) -> list[dict]:                  # alias
    return build_messages(variant)


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    bucket = _classify(parsed, raw)
    return {
        "bucket_a":        1.0 if bucket == "a" else 0.0,
        "bucket_b":        1.0 if bucket == "b" else 0.0,
        "bucket_c":        1.0 if bucket == "c" else 0.0,
        "bucket_d":        1.0 if bucket == "d" else 0.0,
        "bucket_e":        1.0 if bucket == "e" else 0.0,
        "format_healthy":  1.0 if bucket in ("a", "b") else 0.0,
    }
