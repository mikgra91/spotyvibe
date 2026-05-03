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
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Scenario:
    """One canonical evaluation scenario. All fields are deterministic.

    P1 #6 (2026-05-02): when ``seed_profile_path`` is set, the harness
    bypasses ``train_profile(seed_sections)`` and writes the JSON file
    verbatim into the sandbox profile slot. This is the swap point for
    running an eval against an anonymised production profile (large /
    aged / accumulated dislikes) instead of a clean-room seed —
    ``seed_sections`` stays as documentation of what the file
    represents but is unused at run time. Any caller (run_evaluation
    `--seed-profile <path>` CLI flag, downstream scripts) can override
    a scenario's path without subclassing.
    """

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
    seed_profile_path: Path | None = None


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
# Mirrors the `japanese_Theatrical_music` production-failure profile.
# Three failure-mode signals encoded:
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
    # F1 (2026-05-01): "Music must be Japanese" is the load-bearing
    # hard constraint. The training LLM is expected to translate this
    # prose into ``preferences.must_have_tags = ["japanese", "j-pop",
    # "j-rock"]`` per the MUST_HAVE_TAGS instruction in
    # prompts/profile_training_prompt.txt; the eval verifies that
    # translation actually happens by inspecting the post-train
    # profile and by checking that playlist B contains no American
    # artists.
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
    description="Reproduces the production failure: semantic avoid "
                "traits the legacy tokeniser cannot enforce + a hard "
                "must-have phrase. Used to verify F1/F2/F5 close the "
                "leakage gap.",
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


# ── Coverage scenarios (recommended order) ──────────────────────────
#
# Each one targets a blind spot in retrieval/avoid coverage. Definitions
# are pure data: prose seed + deterministic feedback rule + analysis
# anchor known to exist on Spotify. Scoring relies on the existing
# leakage + fit gates; per-scenario oracle checks (geo, language,
# instrumental-only) are deferred to a future phase.

# S05 — ambient instrumental focus. Catches vocal leakage, ambient/
# downtempo confusion, over-dramatic soundtrack picks.
AMBIENT_INSTRUMENTAL_SCENARIO = Scenario(
    name="ambient_instrumental_focus",
    description="Beatless instrumental ambient for concentration. "
                "Vocal/beat leakage and ambient-vs-downtempo confusion "
                "are the failure modes.",
    seed_sections={
        "core_description": (
            "Beatless or near-beatless ambient music for concentration. "
            "Slow development, atmospheric textures, instrumental only."
        ),
        "must_have": (
            "Instrumental only; atmospheric; slow development; "
            "no vocals; no drums or beats"
        ),
        "soft_preferences": (
            "Drone; texture; field recordings; gentle synth pads"
        ),
        "avoid": (
            "Vocals; dance beats; drum-driven structure; "
            "cinematic trailer crescendos; pop song form"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: no vocals, no beat-driven structure, no dramatic crescendos",
        "vibe_description": (
            "Tighten the instrumental + ambient anchor. Suppress any "
            "track with vocals or a dance beat — even if marketed as "
            "ambient."
        ),
    },
    analysis_artist="Brian Eno",
    analysis_track="An Ending (Ascent)",
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 5, 9),
    like_reason="instrumental ambient texture with no vocal focus",
    dislike_reason="vocals, beat-driven structure, or dramatic crescendo",
)

# S04 — 90s boom bap hip-hop. Catches era leakage, modern production
# leakage, genre-adjacency collapse (trap / pop rap / drill).
BOOM_BAP_90S_SCENARIO = Scenario(
    name="boom_bap_90s",
    description="1990s East Coast / golden-age boom bap. Era drift "
                "and modern production leakage are the failure modes.",
    seed_sections={
        "core_description": (
            "1990s East Coast / golden-age boom bap with grounded drums "
            "and gritty production. No modern trap or pop-rap drift."
        ),
        "must_have": (
            "Boom-bap drums; rap vocals; 90s production feel; "
            "rooted in 1990-1999 sound"
        ),
        "soft_preferences": (
            "Sample-based production; DJ scratches; jazzy loops; "
            "East Coast lyricism"
        ),
        "avoid": (
            "Trap hi-hats; autotune; pop rap; drill; "
            "glossy 2010s production; mumble rap"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: no trap hi-hats, no autotune, nothing post-2005 in production feel",
        "vibe_description": (
            "Tighten the 90s boom-bap era anchor. Anything that smells "
            "like 2010s glossy production or trap should be suppressed."
        ),
    },
    analysis_artist="Gang Starr",
    analysis_track="Mass Appeal",
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 5, 9),
    like_reason="grounded 90s boom-bap sound",
    dislike_reason="modern trap / pop-rap / glossy production drift",
)

# S03 — Brazilian samba-funk party. Catches Latin-region overgener-
# alisation, Spanish-vs-Portuguese miss, EDM remix false positives.
BRAZILIAN_SAMBA_FUNK_SCENARIO = Scenario(
    name="brazilian_samba_funk",
    description="Brazilian Portuguese party music with live percussion. "
                "Latin-region overgeneralisation and Spanish/Portuguese "
                "confusion are the failure modes.",
    seed_sections={
        "core_description": (
            "Brazilian party music with live percussion and groove. "
            "Portuguese vocals only. Samba, samba-funk, carnival energy."
        ),
        "must_have": (
            "Brazilian artist; Portuguese vocals; samba or samba-funk; "
            "live percussion; carnival / party energy"
        ),
        "soft_preferences": (
            "Brass section; call-and-response vocals; danceable rhythm; "
            "Tropicália adjacency"
        ),
        "avoid": (
            "Reggaeton; Latin trap; Spanish vocals; generic EDM "
            "remixes; non-Brazilian Latin pop"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: no Spanish vocals, no reggaeton, no EDM remix versions",
        "vibe_description": (
            "Tighten the Brazilian Portuguese anchor. Spanish-language "
            "Latin pop is the most likely drift to suppress."
        ),
    },
    analysis_artist="Jorge Ben Jor",
    analysis_track="Mas Que Nada",
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 5, 9),
    like_reason="Brazilian Portuguese groove with organic percussion",
    dislike_reason="Spanish / reggaeton / EDM-remix drift",
)

# S12 — strict club techno. Catches electronic-subgenre collapse
# (house / trance / EDM / pop-vocal contamination).
CLUB_TECHNO_STRICT_SCENARIO = Scenario(
    name="club_techno_strict",
    description="Functional club techno. Electronic-subgenre collapse "
                "(house / trance / EDM / pop-vocal) is the failure mode.",
    seed_sections={
        "core_description": (
            "Functional club techno with hypnotic repetition. "
            "Berlin / Detroit influence, dark warehouse feel. "
            "Minimal vocals, no festival EDM."
        ),
        "must_have": (
            "Techno pulse; minimal vocals; hypnotic repetition; "
            "dark warehouse feel"
        ),
        "soft_preferences": (
            "Berlin techno; Detroit techno; dub techno; long-form "
            "build; analogue drum machines"
        ),
        "avoid": (
            "House piano; EDM festival drops; trance leads; "
            "pop vocals; melodic vocal hooks"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: no house piano, no trance leads, no festival EDM, no pop vocals",
        "vibe_description": (
            "Tighten the strict-techno anchor. Adjacent electronic "
            "subgenres (house / trance / EDM) are the leakage to "
            "suppress hardest."
        ),
    },
    analysis_artist="Jeff Mills",
    analysis_track="The Bells",
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 5, 9),
    like_reason="strict techno pulse with hypnotic repetition",
    dislike_reason="house / trance / EDM / pop-vocal drift",
)

# S16 — original studio recordings only. Catches track-title variant
# leakage (live / remix / acoustic / cover / sped-up / slowed).
ORIGINAL_RECORDINGS_ONLY_SCENARIO = Scenario(
    name="original_recordings_only",
    description="Original studio recordings only. Track-title variant "
                "leakage (live / remix / acoustic / cover / sped-up) "
                "is the failure mode.",
    seed_sections={
        "core_description": (
            "Modern indie pop, but original studio recordings only. "
            "No live versions, no remixes, no acoustic versions, "
            "no covers, no sped-up / slowed-and-reverb edits."
        ),
        "must_have": (
            "Original studio recording; canonical album version; "
            "indie pop / art-pop"
        ),
        "soft_preferences": (
            "Polished production; melodic hooks; emotive vocals"
        ),
        "avoid": (
            "Live versions; remixes; acoustic versions; covers; "
            "karaoke; sped-up; slowed-and-reverb; radio edits"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: never a live, remix, acoustic, cover, sped-up, or slowed track",
        "vibe_description": (
            "Tighten the originals-only anchor. Track titles ending in "
            "(Live), (Remix), (Acoustic), (Cover), (Sped Up), or "
            "(Slowed) are the leakage to suppress."
        ),
    },
    analysis_artist="Phoebe Bridgers",
    analysis_track="Motion Sickness",
    like_indices=(0, 4, 8, 12, 16),
    dislike_indices=(1, 5, 9),
    like_reason="original studio recording, canonical version",
    dislike_reason="track is a live / remix / acoustic / cover / sped-up variant",
)

# S19 — contradictory profile. Catches under-fill quality + instruction
# conflict handling. Acceptance criterion is "graceful refusal", not
# leakage zero.
CONTRADICTORY_PROFILE_SCENARIO = Scenario(
    name="contradictory_profile",
    description="Contradictory must_have + avoid (calm + aggressive). "
                "Graceful under-fill is acceptable; hallucination or "
                "random picks are not.",
    seed_sections={
        "core_description": (
            "Music that is simultaneously calm + minimal AND aggressive "
            "+ high-energy. Both mood states must be present in every "
            "track. (This is intentionally contradictory — the eval "
            "checks how the system handles instruction conflict.)"
        ),
        "must_have": (
            "Calm; minimal; aggressive; high-energy; "
            "both moods present simultaneously"
        ),
        "soft_preferences": (
            "Cross-genre fusion; experimental structure; "
            "dynamic-range extremes"
        ),
        "avoid": (
            "Tracks that are only calm; tracks that are only "
            "aggressive; tracks that compromise on either mood; "
            "ambient drones without intensity; pure noise without rest"
        ),
    },
    refine_sections={
        "core_description": "",
        "must_have": "",
        "soft_preferences": "",
        "avoid": "and reinforce: no track may be only calm or only aggressive; both must coexist",
        "vibe_description": (
            "Reinforce the contradictory dual-mood requirement. Tracks "
            "that satisfy only one side are unacceptable."
        ),
    },
    analysis_artist="Swans",
    analysis_track="Some Things We Do",
    like_indices=(0, 4),
    dislike_indices=(1, 5, 9),
    like_reason="manages to hold calm and aggressive at once",
    dislike_reason="only one mood present; compromises on the other",
)


# ── Registry + dispatcher ────────────────────────────────────────────

SCENARIOS: dict[str, Scenario] = {
    DEFAULT_SCENARIO.name: DEFAULT_SCENARIO,
    REGRESSION_JAPANESE_SCENARIO.name: REGRESSION_JAPANESE_SCENARIO,
    AMBIENT_INSTRUMENTAL_SCENARIO.name: AMBIENT_INSTRUMENTAL_SCENARIO,
    BOOM_BAP_90S_SCENARIO.name: BOOM_BAP_90S_SCENARIO,
    BRAZILIAN_SAMBA_FUNK_SCENARIO.name: BRAZILIAN_SAMBA_FUNK_SCENARIO,
    CLUB_TECHNO_STRICT_SCENARIO.name: CLUB_TECHNO_STRICT_SCENARIO,
    ORIGINAL_RECORDINGS_ONLY_SCENARIO.name: ORIGINAL_RECORDINGS_ONLY_SCENARIO,
    CONTRADICTORY_PROFILE_SCENARIO.name: CONTRADICTORY_PROFILE_SCENARIO,
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
    "AMBIENT_INSTRUMENTAL_SCENARIO",
    "BOOM_BAP_90S_SCENARIO",
    "BRAZILIAN_SAMBA_FUNK_SCENARIO",
    "CLUB_TECHNO_STRICT_SCENARIO",
    "ORIGINAL_RECORDINGS_ONLY_SCENARIO",
    "CONTRADICTORY_PROFILE_SCENARIO",
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
