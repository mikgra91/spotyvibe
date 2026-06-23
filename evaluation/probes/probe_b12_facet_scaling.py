"""B-12. Facet-count scaling — taste-summary degradation under big profiles.

Measures whether the model's adherence to ``must_have`` constraints
degrades as the taste summary grows from few facets to many. Variants
vary ONLY the count of facets in the ``Must:`` / ``Avoid:`` lines while
holding everything else (system prompt, candidate pool, schema) fixed,
so a delta across variants is attributable to facet-count alone.

Research backing (2025): Liu et al. TACL ("Lost in the Middle"), Chroma
"Context Rot", LongLLMLingua / Focused-CoT. All find that LLM accuracy
degrades as input length and distractor count grow. SpotyVibe's Stage 3
relies on the taste summary as its sole profile signal; a user who
refines their profile over months can easily accumulate 15-25 facets.
This probe makes that degradation visible BEFORE it ships as a quality
regression in production.

5-bucket rubric:
    healthy_cite : pick set has ≥ 60 % must_have-cited rationales.
    partial_cite : 30-60 % cite rate.
    weak_cite    : < 30 % cite rate (the failure mode P-compact targets).
    refusal      : valid empty playlist (anti-confab worked).
    invalid      : malformed JSON / unparseable schema.

Failure: ``weak_cite`` rising with facet count.
Healthy: ``healthy_cite`` flat across variants.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


PROBE_ID = "B-12.facet_scaling"
VARIANTS = ["facets_2", "facets_6", "facets_12", "facets_20"]
RUNS_PER_VARIANT = {v: 1 for v in VARIANTS}


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SYSTEM_PROMPT_PATH = _REPO_ROOT / "prompts" / "track_select_system.txt"
_USER_PROMPT_PATH = _REPO_ROOT / "prompts" / "track_select_user.txt"


_SYSTEM_DEFAULTS = {
    "gpt_language":    "English",
    "rationale_count": "2",
    "omission_rule":   "",
}


# Two grounded artists with `known:` examples — keeps the anti-confab
# clause satisfied so any degradation we measure is downstream of
# grounding (i.e. attention / context-rot, not refusal).
_APPROVED_ARTISTS_BLOCK = (
    "- tally hall\n"
    "    known: \"good day\", \"hidden in the sand\", \"&\""
    "\n"
    "- bear ghost\n"
    "    known: \"necromancin' dancin'\", \"taking back the title\""
)


# Facet pool — first N items per category are used per variant. The
# *first* must_have (always "hooks") is the must we'll later check for
# cite-rate. If the model cites "hooks", it noticed the load-bearing
# facet despite the distractors.
_MUST_HAVE_POOL = [
    "hooks",                  # 1 — index 0, always present
    "punchy guitars",         # 2
    "theatrical vocals",      # 3
    "quirky lyrics",          # 4
    "modern production",      # 5
    "playful rhythms",        # 6
    "energetic tempo",        # 7
    "lush layering",          # 8
    "wide stereo",            # 9
    "dynamic contrast",       # 10
    "anthemic choruses",      # 11
    "bright timbres",         # 12
    "melodic bass",           # 13
    "vocal harmonies",        # 14
    "narrative storytelling", # 15
    "uplifting energy",       # 16
    "fast cadence",           # 17
    "tight arrangements",     # 18
    "memorable bridges",      # 19
    "polished mixing",        # 20
]

_AVOID_POOL = [
    "screamo growls",
    "lo-fi production",
    "80s hair metal",
    "trap drums",
    "country twang",
    "dubstep drops",
    "barbershop a-cappella",
    "industrial noise",
    "throat singing",
    "demoscene chiptune",
    "elevator muzak",
    "auto-tune over-correction",
    "drone meditation",
    "atonal jazz",
    "speed metal blast beats",
    "experimental harsh noise",
    "comedy parody",
    "kids' music",
    "spoken-word recordings",
    "tape hiss aesthetic",
]


_VARIANT_FACET_COUNTS = {
    "facets_2":  (1, 1),    # 1 must, 1 avoid → total 2 facets
    "facets_6":  (3, 3),
    "facets_12": (6, 6),
    "facets_20": (10, 10),
}


def _taste_summary(must_n: int, avoid_n: int) -> str:
    must = ", ".join(_MUST_HAVE_POOL[:must_n])
    avoid = ", ".join(_AVOID_POOL[:avoid_n])
    return f"Must: {must}. Avoid: {avoid}."


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _load_user_template() -> str:
    return _USER_PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(variant: str) -> list[dict]:
    must_n, avoid_n = _VARIANT_FACET_COUNTS[variant]
    user_defaults = {
        "approved_artists":    _APPROVED_ARTISTS_BLOCK,
        "taste_summary":       _taste_summary(must_n, avoid_n),
        "recent_feedback":     "",
        "audio_filters_block": "",
        "batch_size":          "5",
        "min_new_artists":     "1",
    }

    system_raw = _load_system_prompt()
    user_raw = _load_user_template()
    try:
        system = system_raw.format(**_SYSTEM_DEFAULTS)
    except KeyError:
        system = system_raw
        for k, v in _SYSTEM_DEFAULTS.items():
            system = system.replace("{" + k + "}", v)
    try:
        user = user_raw.format(**user_defaults)
    except KeyError:
        user = user_raw
        for k, v in user_defaults.items():
            user = user.replace("{" + k + "}", v)

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


def response_format(variant: str) -> dict | None:
    return {"type": "json_object"}


def _playlist_entries(parsed: Any) -> list[dict]:
    if isinstance(parsed, dict):
        v = parsed.get("playlist")
        if isinstance(v, list):
            return [e for e in v if isinstance(e, dict)]
    return []


def _cites_first_must(entry: dict) -> bool:
    """Return True iff any rationale entry cites the load-bearing must_have.

    The first entry in ``_MUST_HAVE_POOL`` ("hooks") is always present
    across all variants, so cite-rate on that exact facet is a stable
    signal across the facet-count axis.
    """
    rats = entry.get("rationale") or []
    if not isinstance(rats, list):
        return False
    for r in rats:
        if not isinstance(r, dict):
            continue
        if r.get("type") != "profile_match":
            continue
        arg = str(r.get("arg") or "").lower()
        if "hooks" in arg:
            return True
    return False


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    entries = _playlist_entries(parsed)
    if parsed is None or not isinstance(parsed, dict):
        return _scores(bucket="invalid", cite_rate=0.0, n_picks=0)

    n_picks = len(entries)
    if n_picks == 0:
        return _scores(bucket="refusal", cite_rate=0.0, n_picks=0)

    cited = sum(1 for e in entries if _cites_first_must(e))
    cite_rate = cited / n_picks
    if cite_rate >= 0.6:
        bucket = "healthy_cite"
    elif cite_rate >= 0.3:
        bucket = "partial_cite"
    else:
        bucket = "weak_cite"
    return _scores(bucket=bucket, cite_rate=cite_rate, n_picks=n_picks)


def _scores(bucket: str, cite_rate: float, n_picks: int) -> dict[str, float]:
    return {
        "bucket_healthy_cite": 1.0 if bucket == "healthy_cite" else 0.0,
        "bucket_partial_cite": 1.0 if bucket == "partial_cite" else 0.0,
        "bucket_weak_cite":    1.0 if bucket == "weak_cite"    else 0.0,
        "bucket_refusal":      1.0 if bucket == "refusal"      else 0.0,
        "bucket_invalid":      1.0 if bucket == "invalid"      else 0.0,
        "cite_rate":           round(cite_rate, 3),
        "n_picks":             float(n_picks),
    }
