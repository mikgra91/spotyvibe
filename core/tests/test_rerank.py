"""Tests for the taste re-ranker (core/src/rerank.py) and anchor-seeded
retrieval (core/src/rag/retrieval.retrieve_anchor_candidates)."""

from __future__ import annotations

import gzip
import json
from unittest.mock import patch

import pytest

from core.src.rag.corpus import RagCorpus, normalise_name
from core.src.rag.retrieval import (build_anchor_query_tags,
                                     retrieve_anchor_candidates)
from core.src import rerank


ARTISTS = [
    {"mbid": "g", "name": "Glam King", "tags": ["glam rock", "power pop"],
     "tag_weights": [5, 5], "listener_popularity": 0.6},
    {"mbid": "p", "name": "Power Trio", "tags": ["power pop", "rock"],
     "tag_weights": [5, 3], "listener_popularity": 0.5},
    {"mbid": "j", "name": "Jazz Cat", "tags": ["jazz", "fusion"],
     "tag_weights": [5, 5], "listener_popularity": 0.4},
    {"mbid": "s", "name": "Slow Sad", "tags": ["ambient", "glam rock"],
     "tag_weights": [9, 1], "listener_popularity": 0.3},
    {"mbid": "r", "name": "Reject Band", "tags": ["power pop"],
     "tag_weights": [5], "listener_popularity": 0.5},
]


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for a in ARTISTS:
            fh.write(json.dumps(a) + "\n")
    return RagCorpus.load(path)


def _row(corpus, name):
    return corpus.artists[corpus.by_name_normalised[normalise_name(name)]]


# ── build_anchor_query_tags ──────────────────────────────────────────────
def test_anchor_query_from_confirmed_tags(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]}}
    q = build_anchor_query_tags(corpus, profile)
    assert q.get("glam rock") == 1.0
    assert q.get("power pop") == 1.0
    assert "jazz" not in q


def test_anchor_query_empty_when_no_confirmed_in_corpus(corpus):
    profile = {"artists": {"confirmed": ["Nonexistent Band"]}}
    assert build_anchor_query_tags(corpus, profile) == {}


# ── retrieve_anchor_candidates ───────────────────────────────────────────
def test_anchor_retrieve_surfaces_tag_neighbours_excludes_known(corpus):
    profile = {"artists": {"confirmed": ["Glam King"],
                           "rejected": [{"name": "Reject Band"}]}}
    out = retrieve_anchor_candidates(corpus, profile, target_size=10)
    names = {a.name for a in out}
    assert "Power Trio" in names      # shares 'power pop' with the anchor
    assert "Glam King" not in names   # confirmed → never re-suggested
    assert "Reject Band" not in names # rejected → excluded
    assert "Jazz Cat" not in names    # no tag overlap → not scored


def test_anchor_retrieve_applies_avoid_gate(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]},
               "preferences": {"avoid": ["ambient"]}}
    out = retrieve_anchor_candidates(corpus, profile, target_size=10)
    assert "Slow Sad" not in {a.name for a in out}  # ambient is an avoid tag


def test_anchor_retrieve_respects_deny_keys(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]}}
    out = retrieve_anchor_candidates(corpus, profile, deny_keys={"power trio"},
                                     target_size=10)
    assert "Power Trio" not in {a.name for a in out}


def test_anchor_retrieve_falls_back_when_no_anchor(corpus):
    # No confirmed anchors → falls back to prose retrieve_candidates.
    profile = {"artists": {}, "preferences": {"must_have": ["power pop"]}}
    out = retrieve_anchor_candidates(corpus, profile, target_size=10)
    assert isinstance(out, list)  # does not raise; prose path returns a pool


# ── rerank_pool ──────────────────────────────────────────────────────────
def _mock_llm(scores_json):
    return (patch("core.src.rerank.chat_completions_create", return_value={}),
            patch("core.src.rerank.extract_chat_content", return_value=scores_json))


def test_rerank_pool_orders_by_score(corpus):
    profile = {"artists": {"confirmed": ["Glam King"],
                           "rejected": [{"name": "X", "reason": "y"}]}}
    cands = [_row(corpus, n) for n in ("Jazz Cat", "Power Trio", "Slow Sad")]
    payload = json.dumps({"scores": [{"n": 1, "s": 10}, {"n": 2, "s": 90},
                                     {"n": 3, "s": 50}]})
    m1, m2 = _mock_llm(payload)
    with m1, m2:
        out = rerank.rerank_pool(profile, cands, model="m")
    assert [a.name for a in out] == ["Power Trio", "Slow Sad", "Jazz Cat"]


def test_rerank_pool_drop_frac_trims_lowest(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]}}
    cands = [_row(corpus, n) for n in ("Jazz Cat", "Power Trio", "Slow Sad", "Reject Band")]
    payload = json.dumps({"scores": [{"n": 1, "s": 10}, {"n": 2, "s": 90},
                                     {"n": 3, "s": 50}, {"n": 4, "s": 70}]})
    m1, m2 = _mock_llm(payload)
    with m1, m2:
        out = rerank.rerank_pool(profile, cands, model="m", drop_frac=0.5)
    assert [a.name for a in out] == ["Power Trio", "Reject Band"]  # top half


def test_rerank_pool_graceful_on_llm_failure(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]}}
    cands = [_row(corpus, n) for n in ("Jazz Cat", "Power Trio")]
    with patch("core.src.rerank.chat_completions_create",
               side_effect=RuntimeError("boom")):
        out = rerank.rerank_pool(profile, cands, model="m")
    assert out == cands  # unchanged — re-ranker never breaks a run


def test_rerank_pool_no_exemplars_returns_unchanged(corpus):
    profile = {"artists": {}}  # nothing to anchor the judge on
    cands = [_row(corpus, n) for n in ("Jazz Cat", "Power Trio")]
    out = rerank.rerank_pool(profile, cands, model="m")
    assert out == cands


# ── taste_scores parsing robustness ──────────────────────────────────────
def test_taste_scores_matches_name_with_tag_suffix(corpus):
    profile = {"artists": {"confirmed": ["Glam King"]}}
    # Model echoes "Name [tags]" instead of the index — must still map.
    payload = json.dumps({"scores": [{"n": "Power Trio [power pop]", "s": 88}]})
    m1, m2 = _mock_llm(payload)
    with m1, m2:
        scores = rerank.taste_scores(profile, [("Power Trio", ["power pop"])], model="m")
    assert scores.get(normalise_name("Power Trio")) == 88


def test_exemplars_include_must_have_and_avoid():
    profile = {"preferences": {
        "core_description": "theatrical rock",
        "must_have": ["upbeat tempo", "high energy"],
        "avoid": ["slow-tempo", "melancholic"],
    }}
    taste, _, _ = rerank._exemplars(profile)
    assert "upbeat tempo" in taste and "high energy" in taste
    assert "slow-tempo" in taste and "melancholic" in taste
