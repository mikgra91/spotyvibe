"""Tests for the Spotify-enrichment build helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make build-tools/ importable like the CLI does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools"))

from spotify_enrichment.matching import (  # noqa: E402
    MIN_MATCH_SCORE,
    normalise_artist_name,
    pick_best_match,
    score_candidate,
)


# ── normalise_artist_name ────────────────────────────────────────────

def test_normalise_handles_diacritics_and_punct():
    assert normalise_artist_name("Beyoncé!") == "beyonce"
    assert normalise_artist_name("Sigur Rós") == "sigur ros"
    assert normalise_artist_name("AC/DC") == "ac dc"
    assert normalise_artist_name("  Multi   Spaces  ") == "multi spaces"


def test_normalise_empty_inputs():
    assert normalise_artist_name("") == ""
    assert normalise_artist_name(None) == ""  # type: ignore[arg-type]


# ── score_candidate ──────────────────────────────────────────────────

def test_score_exact_name_only():
    s = score_candidate(
        mb_name="Bear Ghost", mb_begin_year=2014, mb_tags=["rock"],
        sp_name="Bear Ghost", sp_genres=[],
    )
    assert s == 1.0  # name match alone clears MIN_MATCH_SCORE


def test_score_full_match_includes_year_and_overlap():
    s = score_candidate(
        mb_name="Bear Ghost", mb_begin_year=2014,
        mb_tags=["progressive rock", "rock"],
        sp_name="Bear Ghost",
        sp_genres=["progressive rock", "theatrical rock"],
        sp_first_release_year=2015,
    )
    # 1.0 (name) + 0.5 (year) + 0.1 (1 shared genre) = 1.6
    assert s == pytest.approx(1.6, rel=0.001)


def test_score_no_name_match_returns_low():
    s = score_candidate(
        mb_name="Bear Ghost", mb_begin_year=2014, mb_tags=["rock"],
        sp_name="Polar Wolf", sp_genres=["rock"],
    )
    # Only 1 shared tag (+0.1) → 0.1, well below 1.0
    assert s == pytest.approx(0.1, rel=0.001)


def test_score_tag_bonus_capped():
    s = score_candidate(
        mb_name="X", mb_begin_year=None,
        mb_tags=["a", "b", "c", "d", "e", "f", "g", "h"],
        sp_name="X",
        sp_genres=["a", "b", "c", "d", "e", "f", "g", "h"],
    )
    # 1.0 (name) + min(0.5, 0.1*8) = 1.5 — bonus capped at 0.5
    assert s == pytest.approx(1.5, rel=0.001)


# ── pick_best_match ──────────────────────────────────────────────────

def test_pick_best_match_returns_top_scorer_above_threshold():
    candidates = [
        {"id": "low", "name": "Bear Ghost", "genres": []},
        {"id": "high", "name": "Bear Ghost",
         "genres": ["progressive rock"]},
    ]
    match = pick_best_match(
        mb_name="Bear Ghost", mb_begin_year=2014,
        mb_tags=["progressive rock"], candidates=candidates,
    )
    assert match is not None
    assert match.spotify_id == "high"


def test_pick_best_match_returns_none_below_threshold():
    candidates = [
        {"id": "wrong", "name": "Polar Wolf", "genres": ["pop"]},
    ]
    match = pick_best_match(
        mb_name="Bear Ghost", mb_begin_year=2014,
        mb_tags=["rock"], candidates=candidates,
    )
    assert match is None


def test_pick_best_match_tolerates_garbage_entries():
    candidates = [
        None,
        "not a dict",
        {},
        {"id": "ok", "name": "Bear Ghost", "genres": []},
    ]
    match = pick_best_match(
        mb_name="Bear Ghost", mb_begin_year=None, mb_tags=[],
        candidates=candidates,  # type: ignore[arg-type]
    )
    assert match is not None
    assert match.spotify_id == "ok"


def test_min_match_score_is_one():
    # Sanity — if this changes, related tests/docs need updating too.
    assert MIN_MATCH_SCORE == 1.0

