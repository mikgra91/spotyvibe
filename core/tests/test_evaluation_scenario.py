"""Lightweight contract tests for the evaluation scenario constants.

These do NOT execute the harness (which is a real-billing operation
gated on explicit invocation per evaluation/README.md). They only pin
the deterministic feedback rule + the seed taste profile so a future
edit can't silently change what every model is being judged against.
"""
from __future__ import annotations


def test_seed_sections_cover_required_fields():
    from evaluation.scenario import SEED_SECTIONS
    for required in ("core_description", "must_have", "soft_preferences", "avoid"):
        assert required in SEED_SECTIONS, f"seed missing {required}"
        assert SEED_SECTIONS[required].strip(), f"seed {required} is empty"


def test_feedback_rule_is_deterministic_and_disjoint():
    """Likes and dislikes must not collide — same index can't be both."""
    from evaluation.scenario import LIKE_INDICES, DISLIKE_INDICES
    likes = set(LIKE_INDICES)
    dislikes = set(DISLIKE_INDICES)
    assert likes.isdisjoint(dislikes), \
        f"feedback indices overlap: {likes & dislikes}"
    assert len(likes) >= 3, "scenario should apply enough likes to be meaningful"
    assert len(dislikes) >= 2, "scenario should apply enough dislikes to be meaningful"


def test_feedback_indices_fit_a_30_track_playlist():
    """All indices must be < default playlist_size or harness skips them silently."""
    from evaluation.scenario import LIKE_INDICES, DISLIKE_INDICES
    for i in LIKE_INDICES + DISLIKE_INDICES:
        assert 0 <= i < 30, f"index {i} would be skipped on a default 30-track run"


def test_analysis_target_set():
    from evaluation.scenario import ANALYSIS_ARTIST, ANALYSIS_TRACK
    assert ANALYSIS_ARTIST.strip()
    assert ANALYSIS_TRACK.strip()


# ── F8.2 (2026-05-01): scenario registry + regression fixture ────────

def test_scenario_registry_has_default_and_regression():
    from evaluation.scenario import SCENARIOS
    assert "default" in SCENARIOS
    assert "regression_japanese_theatrical" in SCENARIOS


def test_get_scenario_returns_default_for_empty_name():
    from evaluation.scenario import DEFAULT_SCENARIO, get_scenario
    assert get_scenario(None) is DEFAULT_SCENARIO
    assert get_scenario("") is DEFAULT_SCENARIO
    assert get_scenario("   ") is DEFAULT_SCENARIO


def test_get_scenario_raises_on_unknown_name():
    """Typos must fail loud — silently picking the default would mask
    misconfiguration in settings.ini and waste a real-billing run."""
    import pytest
    from evaluation.scenario import get_scenario
    with pytest.raises(KeyError):
        get_scenario("does_not_exist")


def test_default_scenario_back_compat_aliases_match():
    """The module-level constants (SEED_SECTIONS etc.) must continue
    pointing at the default scenario so existing imports keep working."""
    from evaluation import scenario as scn
    assert scn.SEED_SECTIONS is scn.DEFAULT_SCENARIO.seed_sections
    assert scn.REFINE_SECTIONS is scn.DEFAULT_SCENARIO.refine_sections
    assert scn.LIKE_INDICES == scn.DEFAULT_SCENARIO.like_indices
    assert scn.DISLIKE_INDICES == scn.DEFAULT_SCENARIO.dislike_indices


def test_regression_scenario_mirrors_production_failure():
    """Pin the F8.2 reproducer's load-bearing prose so a future scenario
    edit cannot silently neuter the regression fixture. See
    `context/claudeAnalyse.md` F1/F2/F3 for the failure modes encoded
    in this scenario."""
    from evaluation.scenario import REGRESSION_JAPANESE_SCENARIO
    avoid = REGRESSION_JAPANESE_SCENARIO.seed_sections["avoid"].lower()
    must_have = REGRESSION_JAPANESE_SCENARIO.seed_sections["must_have"].lower()

    # Hard must-have phrase the legacy code fails to enforce
    assert "japanese" in must_have

    # Semantic avoid traits the legacy tokeniser cannot reduce to
    # corpus tags — this is what triggers the unsafe Stage-2 skip.
    assert "american" in avoid
    assert "80s" in avoid
    assert "uplifting" in avoid

    # Enough dislikes to plausibly trigger F4 auto-escalation on
    # repeated playlist-B leakage.
    assert len(REGRESSION_JAPANESE_SCENARIO.dislike_indices) >= 3
