"""B-11. Empty-pool recovery (A6-predictor).

Uses the PRODUCTION track-select system prompt verbatim and sends a user
message in which APPROVED_ARTISTS is empty (or near-empty). Predicts
whether the A6 "pool-starvation refusal" feature is necessary on each
model.

5-bucket rubric:
    bucket_a : empty valid playlist + honest 'pool_assessment' reasoning
               (calibrated refusal — what A6 would produce automatically).
    bucket_b : valid JSON with a single explanation/note field and empty
               playlist (close cousin of A; acceptable).
    bucket_c : non-empty playlist with invented artists/tracks (the
               failure mode A6 protects against).
    bucket_d : malformed / no JSON.
    bucket_e : valid JSON, valid shape, but playlist contains the
               artist-name-as-track confabulation pattern explicitly
               called out in the system prompt's HC anti-confabulation
               block.

Failure: bucket_c (and bucket_e). Healthy: bucket_a, bucket_b.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


PROBE_ID = "B-11.empty_pool_recovery"
VARIANTS = ["empty_pool", "single_artist_no_known"]
RUNS_PER_VARIANT = {"empty_pool": 1, "single_artist_no_known": 1}


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SYSTEM_PROMPT_PATH = _REPO_ROOT / "prompts" / "track_select_system.txt"
_USER_PROMPT_PATH   = _REPO_ROOT / "prompts" / "track_select_user.txt"


# Production prompts use Python ``.format()`` placeholders. We fill the
# minimum set the probe needs; any placeholder not listed here is left
# intact so a future addition fails loudly during the format call.
_SYSTEM_DEFAULTS = {
    "gpt_language":    "English",
    "rationale_count": "2",
    "omission_rule":   "",          # softened omission discipline; empty = no extra hint
}


_USER_DEFAULTS_EMPTY = {
    "approved_artists":   "",
    "taste_summary":      (
        "Must: dreamy ambient, slow-builds, soft synthesisers. "
        "Avoid: harsh distortion, aggressive percussion."
    ),
    "recent_feedback":    "",
    "audio_filters_block":"",
    "batch_size":         "8",
    "min_new_artists":    "2",
}


# Single artist, no `known:` examples - this triggers the system prompt's
# "OMIT that artist unless you are sure of a real released track" path.
_USER_DEFAULTS_SINGLE = {
    **_USER_DEFAULTS_EMPTY,
    "approved_artists": "- brian eno\n  known: (no track examples available — only suggest if you recall a real release)",
}


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _load_user_template() -> str:
    return _USER_PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(variant: str) -> list[dict]:
    system_raw = _load_system_prompt()
    user_raw   = _load_user_template()

    # Format the system prompt with the placeholders we care about and
    # leave the rest unchanged so any future placeholder addition raises
    # KeyError loudly (rather than producing a silently-degraded probe).
    try:
        system = system_raw.format(**_SYSTEM_DEFAULTS)
    except KeyError:
        # Some production prompts have stray `{...}` that are not
        # placeholders (JSON examples inside the prompt). Fall back to a
        # safe per-placeholder string replace for the keys we know about.
        system = system_raw
        for k, v in _SYSTEM_DEFAULTS.items():
            system = system.replace("{" + k + "}", v)

    user_defaults = _USER_DEFAULTS_EMPTY if variant == "empty_pool" else _USER_DEFAULTS_SINGLE
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
    # The production system prompt embeds its own JSON schema in prose
    # and HC1 explicitly allows shorter playlists. Use json_object so
    # the model can return `{"playlist": []}` or a `reasoning`-only
    # response without a schema rejection masking the behaviour.
    return {"type": "json_object"}


_PLACEHOLDER_TRACKS = {"untitled", "intro", "outro", "track", "track 1", "song", "-", ""}


def _playlist_entries(parsed: Any) -> list[dict]:
    if isinstance(parsed, dict):
        v = parsed.get("playlist")
        if isinstance(v, list):
            return [e for e in v if isinstance(e, dict)]
    return []


def _is_artist_echo(entry: dict) -> bool:
    artist = str(entry.get("artist") or "").strip().lower()
    track  = str(entry.get("track")  or "").strip().lower()
    if not artist or not track:
        return False
    if artist == track:
        return True
    if track in _PLACEHOLDER_TRACKS:
        return True
    return False


def _classify(parsed: Any, raw: str) -> str:
    if parsed is None:
        return "d"
    if not isinstance(parsed, dict):
        return "d"

    entries = _playlist_entries(parsed)

    if not entries:
        # Empty playlist + reasoning -> bucket_a. Empty playlist + note -> bucket_b.
        reasoning = parsed.get("reasoning")
        if isinstance(reasoning, dict) and reasoning.get("pool_assessment"):
            return "a"
        if any(parsed.get(k) for k in ("note", "warning", "explanation")):
            return "b"
        return "a"  # empty + nothing-else-said still counts as honest refusal

    # Non-empty playlist - either confabulation or artist-echo failure.
    if any(_is_artist_echo(e) for e in entries):
        return "e"
    return "c"


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    bucket = _classify(parsed, raw)
    playlist_len = len(_playlist_entries(parsed))
    return {
        "bucket_a":            1.0 if bucket == "a" else 0.0,
        "bucket_b":            1.0 if bucket == "b" else 0.0,
        "bucket_c":            1.0 if bucket == "c" else 0.0,
        "bucket_d":            1.0 if bucket == "d" else 0.0,
        "bucket_e":            1.0 if bucket == "e" else 0.0,
        "pool_recovery_healthy": 1.0 if bucket in ("a", "b") else 0.0,
        "playlist_length":     float(playlist_len),
    }
