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
