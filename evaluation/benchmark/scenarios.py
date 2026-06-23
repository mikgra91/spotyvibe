"""Curated production-readiness scenarios.

Each entry is a :class:`BenchmarkScenario` pairing a harness
``Scenario`` (the eval input) with a :class:`BenchmarkGate` (the
pass/fail threshold pack). Six scenarios cover the real production
failure axes; every one is here because it caught a known bug.

Coverage matrix:

| Scenario                          | Pool size | Aged state | Stresses                                  |
|-----------------------------------|----------:|:----------:|-------------------------------------------|
| broad_mainstream_clean            | Big       | No         | Baseline. Failure here = system-wide bug. |
| niche_japanese_clean              | Medium    | No         | Niche-genre corpus coverage.              |
| aged_japanese_session5            | Medium    | YES        | THE PRODUCTION FAILURE (Q1/Q2/Q3 fix).    |
| aged_mainstream_session5          | Big       | YES        | Dedup correctness on broad profiles.      |
| contradictory_facets              | Medium    | No         | Conflicting must_haves; model confusion.  |
| post_dislike_regression           | Big       | Implicit   | Anti-leakage across feedback cycle.       |

To add a scenario: declare a new ``BenchmarkScenario`` here with an
existing ``Scenario`` from :mod:`evaluation.scenario` (or a fresh one)
plus a :class:`BenchmarkGate`, register it in ``BENCHMARK_SCENARIOS``,
and add a row to the coverage matrix above.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gates import BenchmarkGate

# Resolve aged-state fixtures relative to this module so paths work
# from any cwd / packaged install.
_SEED_PROFILES_DIR = Path(__file__).resolve().parent.parent / "seed_profiles"


@dataclass(frozen=True)
class BenchmarkScenario:
    """A scenario the benchmark runs + its pass/fail gate.

    *harness_scenario_name* refers to an entry in
    :data:`evaluation.scenario.SCENARIOS` (the harness's existing
    scenario registry — we wrap, not duplicate). *seed_profile_path*
    optionally overrides the scenario's seed with a pre-aged fixture
    (mimics "session 5 of this profile" without running sessions 1-4).
    *playlist_size* overrides the default 15 — the benchmark uses 30
    because that's what production users hit.
    """

    name: str
    description: str
    harness_scenario_name: str
    gate: BenchmarkGate
    seed_profile_path: Path | None = None
    playlist_size: int = 30


# ── 1. broad_mainstream_clean ────────────────────────────────────────
#
# Easy baseline. Reuses the harness's ``default`` scenario (theatrical
# pop-rock). A model that fails THIS has a system-wide bug — likely
# in Stage 3 + Spotify verify, not anywhere niche-specific.

BENCHMARK_SCENARIOS: dict[str, BenchmarkScenario] = {}


BENCHMARK_SCENARIOS["broad_mainstream_clean"] = BenchmarkScenario(
    name="broad_mainstream_clean",
    description=(
        "Fresh broad-rock profile. Big approved pool. Lots of "
        "Spotify-resolvable artists. Should fill easily."
    ),
    harness_scenario_name="default",
    gate=BenchmarkGate(
        min_verified_count=27,          # 90% of 30
        min_spotify_found_rate=0.70,
        max_leakage_count=0,
        min_unique_artist_count=18,     # ≥ 60% diverse
        max_wall_seconds=180,
        max_cost_usd=0.10,
    ),
)


# ── 2. niche_japanese_clean ──────────────────────────────────────────
#
# Reuses the existing ``regression_japanese_theatrical`` scenario.
# Tests Stage 1 coverage on a narrow language constraint without
# the dedup-driven exhaustion of session-5 state.

BENCHMARK_SCENARIOS["niche_japanese_clean"] = BenchmarkScenario(
    name="niche_japanese_clean",
    description=(
        "Fresh Japanese rock/metal profile. Narrow language constraint "
        "(must_have_tags = [japanese, j-rock, j-pop]). Tests whether "
        "Stage 1 + corpus can find enough Japanese material."
    ),
    harness_scenario_name="regression_japanese_theatrical",
    gate=BenchmarkGate(
        min_verified_count=24,          # 80% of 30 — niche is harder
        min_spotify_found_rate=0.50,
        max_leakage_count=0,
        min_unique_artist_count=12,
        max_wall_seconds=240,
        max_cost_usd=0.10,
    ),
)


# ── 3. aged_japanese_session5 ────────────────────────────────────────
#
# THE PRODUCTION FAILURE. Uses the pre-aged fixture
# `seed_profiles/aged_japanese_s5.json` (25 history entries + 5
# disliked tracks + 2 rejected artists). Before Q1/Q2/Q3, this
# scenario reproduced the 4/30 collapse the user reported.

BENCHMARK_SCENARIOS["aged_japanese_session5"] = BenchmarkScenario(
    name="aged_japanese_session5",
    description=(
        "Aged Japanese profile (simulated session 5). 25 prior "
        "history entries, 5 disliked tracks, 2 rejected artists. "
        "Reproduces the production failure: Spotify-found rate "
        "collapses run-over-run as dedup state grows. "
        "REGRESSION TEST for Q1/Q2/Q3 fixes (2026-05-23)."
    ),
    harness_scenario_name="regression_japanese_theatrical",
    seed_profile_path=_SEED_PROFILES_DIR / "aged_japanese_s5.json",
    gate=BenchmarkGate(
        # Aged state is hard. 70% threshold acknowledges that — but
        # a model dropping to 4/30 (as before the fix) catastrophically
        # fails. Pre-fix: 4/30. Target post-fix: ≥21/30.
        min_verified_count=21,          # 70% of 30
        min_spotify_found_rate=0.40,
        max_leakage_count=0,
        min_unique_artist_count=10,
        max_wall_seconds=300,
        max_cost_usd=0.15,
    ),
)


# ── 4. aged_mainstream_session5 ──────────────────────────────────────
#
# Same aged-state stress on a broad-coverage profile. If this fails
# too, the dedup logic itself is broken (not niche-specific).

BENCHMARK_SCENARIOS["aged_mainstream_session5"] = BenchmarkScenario(
    name="aged_mainstream_session5",
    description=(
        "Aged mainstream alt-rock profile (simulated session 5). "
        "30 history entries, 3 disliked tracks, 1 rejected artist. "
        "Control variant of aged_japanese_session5: this profile "
        "should NOT have corpus coverage issues, so a failure here "
        "isolates dedup/state bugs from corpus bugs."
    ),
    harness_scenario_name="default",
    seed_profile_path=_SEED_PROFILES_DIR / "aged_mainstream_s5.json",
    gate=BenchmarkGate(
        min_verified_count=25,          # 83% — easier than aged-niche
        min_spotify_found_rate=0.65,
        max_leakage_count=0,
        min_unique_artist_count=15,
        max_wall_seconds=240,
        max_cost_usd=0.10,
    ),
)


# ── 5. contradictory_facets ──────────────────────────────────────────
#
# Reuses the existing ``contradictory_profile`` scenario. Tests
# whether the model gracefully degrades on impossible constraints
# (lo-fi AND polished production) or produces garbage.

BENCHMARK_SCENARIOS["contradictory_facets"] = BenchmarkScenario(
    name="contradictory_facets",
    description=(
        "Profile with self-contradicting must_have items (lo-fi AND "
        "polished production). Model should either pick a side "
        "consistently or admit reduced fill. Confabulation here "
        "would produce technically-on-profile garbage."
    ),
    harness_scenario_name="contradictory_profile",
    gate=BenchmarkGate(
        # Contradictory profiles are intentionally hard. Lower bar:
        # if the model can fill 20/30 without leakage, it's handling
        # the ambiguity gracefully.
        min_verified_count=18,          # 60% of 30
        min_spotify_found_rate=0.50,
        max_leakage_count=0,
        min_unique_artist_count=10,
        max_wall_seconds=240,
        max_cost_usd=0.12,
    ),
)


# ── 6. post_dislike_regression ───────────────────────────────────────
#
# Reuses ``post_feedback_tag_regression``. The harness's two-playlist
# pattern (A → feedback → B) is the load-bearing test. Gate hard on
# leakage in playlist B; verified-count tolerance matches playlist A.

BENCHMARK_SCENARIOS["post_dislike_regression"] = BenchmarkScenario(
    name="post_dislike_regression",
    description=(
        "Generate playlist A, dislike 3 tracks, generate playlist B. "
        "Playlist B MUST NOT contain any disliked track or rejected "
        "artist. Validates the anti-leakage path end-to-end."
    ),
    harness_scenario_name="post_feedback_tag_regression",
    gate=BenchmarkGate(
        min_verified_count=24,          # 80%
        min_spotify_found_rate=0.60,
        max_leakage_count=0,            # ZERO leakage — non-negotiable
        min_unique_artist_count=15,
        max_wall_seconds=300,
        max_cost_usd=0.15,
    ),
)


def get_benchmark_scenario(name: str) -> BenchmarkScenario:
    """Look up a scenario by name. Raises KeyError on unknown name."""
    if name not in BENCHMARK_SCENARIOS:
        known = ", ".join(sorted(BENCHMARK_SCENARIOS))
        raise KeyError(
            f"Unknown benchmark scenario {name!r}. Known: {known}"
        )
    return BENCHMARK_SCENARIOS[name]
