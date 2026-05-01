"""Canonical evaluation scenarios.

Each :class:`Scenario` bundles every per-run input the harness needs:

  - ``seed_sections`` — initial ``train_profile`` payload
  - ``analysis_artist`` / ``analysis_track`` — Band/Song Analysis target
  - ``like_indices`` / ``dislike_indices`` — deterministic feedback rule
  - ``like_reason`` / ``dislike_reason``
  - ``refine_sections`` — second ``train_profile`` payload (post-feedback)

Two scenarios are shipped:

  - ``default`` — broad theatrical-pop-rock taste used for cost/quality
    A/B comparisons across models. Avoid prose is mostly tag-detectable
    (``classic rock``, ``EDM``, ``synthwave``) so Stage-1 filters and
    Stage-2 LLM both have something to bite on.
  - ``regression_japanese_theatrical`` — F8.2 (2026-05-01) regression
    fixture mirroring the user's actual failing profile. Avoid prose
    contains semantic content the legacy tokeniser cannot reduce to
    corpus tags (``American artists`` / ``80s production style`` /
    ``Songs that are not uplifting``) AND a hard must-have phrase
    (``Music must be Japanese``) the production code currently fails
    to enforce. Run this scenario AFTER F1/F2/F5 ship to verify the
    leakage gate flips from fail → pass.

Module-level constants (``SEED_SECTIONS`` etc.) are preserved as
aliases of the default scenario so existing imports keep working.

The dispatcher is :func:`get_scenario` — call by name or fall back to
the default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Scenario:
    """One canonical evaluation scenario. All fields are deterministic."""

    name: str
    description: str
    seed_sections: dict[str, str]
    refine_sections: dict[str, str]
    analysis_artist: str
    analysis_track: str
    like_indices: tuple[int, ...]
    dislike_indices: tuple[int, ...]
    like_reason: str
    dislike_reason: str


# ── Default scenario — broad theatrical-pop-rock ────────────────────

_DEFAULT_SEED: dict[str, str] = {
    "core_description": (
        "Modern theatrical pop-rock with strong hooks and quirky personality. "
        "Polished but not generic. Vocal-forward, melodic, post-2010 lean."
    ),
    "must_have": (
        "punchy guitars; strong hooks; modern production; theatrical or "
        "quirky personality; clear vocal melody"
    ),
    "soft_preferences": (
        "art-pop influences; J-rock or J-pop crossover; orchestral or "
        "horn-section flourishes; storytelling lyrics"
    ),
    "avoid": (
        "classic rock straight-ahead; vintage 60s/70s arena rock; pure "
        "EDM/synthwave; lo-fi indie guitar dominance; unmastered demos"
    ),
}

_DEFAULT_REFINE: dict[str, str] = {
    "core_description": "",
    "must_have": "",
    "soft_preferences": "",
    "avoid": "and avoid suggestions that drift into vintage 60s/70s territory",
    "vibe_description": (
        "Looking at recent feedback, please tighten the avoid list around "
        "vintage rock and emphasise the modern, theatrical, hook-forward "
        "anchor in must_have."
    ),
}

DEFAULT_SCENARIO = Scenario(
    name="default",
    description="Broad theatrical-pop-rock taste; avoid prose is mostly "
                "tag-detectable. Used for model A/B cost/quality comparison.",
    seed_sections=_DEFAULT_SEED,
    refine_sections=_DEFAULT_REFINE,
    analysis_artist="Bear Ghost",
    analysis_track="Mr. Bubbles",
    like_indices=(0, 3, 6, 9, 12),
    dislike_indices=(2, 7, 11),
    like_reason="fits the modern theatrical-pop-rock anchor exactly",
    dislike_reason="drifts into avoided territory (vintage / generic)",
)


# ── Regression scenario — production-failure reproducer ─────────────
#
# Mirrors the `japanese_Theatrical_music` profile documented in
# `context/claudeAnalyse.md`. Three failure-mode signals encoded:
#
#   1. Hard must-have prose ("Music must be Japanese") that the legacy
#      tokeniser folds into a noisy bag-of-words rather than enforcing.
#   2. Avoid traits the legacy tokeniser cannot reduce to corpus tags
#      ("American artists", "80s production style", "Songs that are not
#      uplifting") — these trigger the F3 unsafe Stage-2 skip.
#   3. Refine sections that ask the model to absorb the dislike reasons
#      ("not Japanese", "80s feel", "American artist") into avoid.
#
# A passing leakage gate on this scenario is the load-bearing
# acceptance criterion for F1 + F2 + F5.

_REGRESSION_SEED: dict[str, str] = {
    "core_description": (
        "Uplifting Japanese theatrical music with harmonized vocals "
        "and modern production. No screaming. Music must be Japanese."
    ),
    "must_have": (
        "Uplifting music; harmonized vocals; no screaming; "
        "Music must be Japanese"
    ),
    "soft_preferences": (
        "J-pop and J-rock; theatrical or cinematic flourishes; "
        "anime soundtrack adjacency; melodic vocal harmony"
    ),
    "avoid": (
        "Electronic music; Excessive use of synthesizers; "
        "80s production style; American artists; "
        "Songs that are not uplifting"
    ),
}

_REGRESSION_REFINE: dict[str, str] = {
    "core_description": "",
    "must_have": "",
    "soft_preferences": "",
    "avoid": (
        "and reinforce: songs must be Japanese; no 80s production feel; "
        "no American artists"
    ),
    "vibe_description": (
        "From recent feedback, please make the Japanese-only constraint "
        "harder, tighten the avoid list around 80s production and "
        "American artists, and keep uplifting + harmonized-vocals as "
        "the must-have anchor."
    ),
}

REGRESSION_JAPANESE_SCENARIO = Scenario(
    name="regression_japanese_theatrical",
    description="Reproduces the production failure documented in "
                "`context/claudeAnalyse.md`: semantic avoid traits the "
                "legacy tokeniser cannot enforce + a hard must-have "
                "phrase. Used to verify F1/F2/F5 close the leakage gap.",
    seed_sections=_REGRESSION_SEED,
    refine_sections=_REGRESSION_REFINE,
    # Pick a Japanese band the major models recognise, so the analysis
    # step exercises structured-output and not parametric recall.
    analysis_artist="One Ok Rock",
    analysis_track="Wherever you are",
    # Like the strong fits, dislike a few "drift" slots so the
    # post-feedback profile has plenty of material to escalate.
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 2, 3, 5, 9, 13),  # 6 dislikes → likely F4 trigger
    like_reason="hits the Japanese theatrical anchor with uplifting vocals",
    dislike_reason="drifts into 80s/American/non-uplifting territory",
)


# ── Registry + dispatcher ────────────────────────────────────────────

SCENARIOS: dict[str, Scenario] = {
    DEFAULT_SCENARIO.name: DEFAULT_SCENARIO,
    REGRESSION_JAPANESE_SCENARIO.name: REGRESSION_JAPANESE_SCENARIO,
}


def get_scenario(name: str | None) -> Scenario:
    """Return the named scenario, defaulting to ``default`` for empty/None.

    Raises :class:`KeyError` for unknown names so a typo in
    ``settings.ini`` fails loud instead of silently picking the default.
    """
    if not name or not name.strip():
        return DEFAULT_SCENARIO
    key = name.strip()
    if key not in SCENARIOS:
        raise KeyError(
            f"Unknown evaluation scenario {key!r}. Known: {sorted(SCENARIOS)}"
        )
    return SCENARIOS[key]


# ── Back-compat module-level aliases ─────────────────────────────────
#
# Older callers (and the existing contract tests) read these constants
# directly. Keep them pointing at the default scenario so behaviour is
# unchanged unless a caller explicitly opts into a named scenario.

SEED_SECTIONS: dict[str, str] = DEFAULT_SCENARIO.seed_sections
REFINE_SECTIONS: dict[str, str] = DEFAULT_SCENARIO.refine_sections
ANALYSIS_ARTIST: str = DEFAULT_SCENARIO.analysis_artist
ANALYSIS_TRACK: str = DEFAULT_SCENARIO.analysis_track
LIKE_INDICES: tuple[int, ...] = DEFAULT_SCENARIO.like_indices
DISLIKE_INDICES: tuple[int, ...] = DEFAULT_SCENARIO.dislike_indices
LIKE_REASON: str = DEFAULT_SCENARIO.like_reason
DISLIKE_REASON: str = DEFAULT_SCENARIO.dislike_reason


@dataclass
class ScenarioStep:
    """One step in the canonical evaluation flow.

    Each ``run`` callable receives the harness context and is expected
    to log its own telemetry (the production code paths already do
    this — eval.jsonl gets the rows).
    """
    name: str
    description: str
    run: Callable[..., dict] = field(repr=False)


__all__ = [
    "Scenario",
    "DEFAULT_SCENARIO",
    "REGRESSION_JAPANESE_SCENARIO",
    "SCENARIOS",
    "get_scenario",
    "SEED_SECTIONS",
    "REFINE_SECTIONS",
    "ANALYSIS_ARTIST",
    "ANALYSIS_TRACK",
    "LIKE_INDICES",
    "DISLIKE_INDICES",
    "LIKE_REASON",
    "DISLIKE_REASON",
    "ScenarioStep",
]
