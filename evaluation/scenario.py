"""Canonical evaluation scenario.

Defines the deterministic taste profile, analysis target, and
like/dislike rule used by every evaluation run. Keeping this fixed
across runs is what makes model A/B comparisons meaningful — every
model sees the same input and is judged on the same downstream actions.

Edit this file when the scenario itself changes (new genre coverage,
different anchors, etc). DO NOT inline scenario tweaks in the harness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# ── Seed taste profile ───────────────────────────────────────────────
#
# Modelled on the user's actual profile (theatrical-quirky-pop-rock,
# modern lean) so the eval mirrors real usage. Sections map to the
# fields that ``train_profile()`` accepts.

SEED_SECTIONS: dict[str, str] = {
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

# Analysis target — pick a band we expect every model to know so this
# step is not a hallucination test but a structural-output test.
ANALYSIS_ARTIST = "Bear Ghost"
ANALYSIS_TRACK = "Mr. Bubbles"


# ── Like / dislike rule ──────────────────────────────────────────────
#
# Deterministic: same playlist → same likes → same dislikes. Every run
# applies feedback to the SAME slot indices so "like rate" is a
# function of which tracks the model returned, not of randomness in
# the harness.

LIKE_INDICES: tuple[int, ...] = (0, 3, 6, 9, 12)        # 5 likes
DISLIKE_INDICES: tuple[int, ...] = (2, 7, 11)           # 3 dislikes

LIKE_REASON = "fits the modern theatrical-pop-rock anchor exactly"
DISLIKE_REASON = "drifts into avoided territory (vintage / generic)"


# ── Post-feedback re-train sections ──────────────────────────────────
#
# What ``train_profile()`` is asked on the SECOND call (after feedback
# has been applied). Empty strings for sections we don't update — the
# call still exercises the full pipeline and absorbs feedback into the
# profile via the prompt's instruction.

REFINE_SECTIONS: dict[str, str] = {
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
