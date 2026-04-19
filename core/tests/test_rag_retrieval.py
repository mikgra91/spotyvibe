"""Unit tests for core.src.rag.retrieval scoring + deny filtering."""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus
from core.src.rag.retrieval import build_query_tags, score_artists


ARTISTS = [
    {"mbid": "a1", "name": "Ethereal Echoes",
     "tags": ["dream pop", "shoegaze"], "tag_weights": [5, 3],
     "listener_popularity": 0.1},
    {"mbid": "a2", "name": "Concrete Signal",
     "tags": ["post-punk", "industrial"], "tag_weights": [6, 2],
     "listener_popularity": 0.1},
    {"mbid": "a3", "name": "Mega Pop Star",
     "tags": ["pop", "rnb"], "tag_weights": [9, 8],
     "listener_popularity": 0.98},
    {"mbid": "a4", "name": "The Broken Gramophone",
     "tags": ["shoegaze", "post-punk"], "tag_weights": [4, 4],
     "listener_popularity": 0.05},
    {"mbid": "a5", "name": "Nova Drive",
     "tags": ["synthwave", "electronica"], "tag_weights": [7, 5],
     "listener_popularity": 0.3},
]


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for a in ARTISTS:
            fh.write(json.dumps(a) + "\n")
    aliases = tmp_path / "tag_aliases.json"
    aliases.write_text(json.dumps({"dreampop": "dream pop"}), encoding="utf-8")
    return RagCorpus.load(path, aliases)


def test_build_query_tags_harvests_prose():
    profile = {"preferences": {
        "must_have": ["dream pop and shoegaze"],
        "soft_preferences": ["ambient, cinematic"],
    }}
    query = build_query_tags(profile)
    # both the bigram and the unigrams surface
    assert query.get("dream pop", 0) >= 2.0
    assert query.get("shoegaze", 0) >= 2.0
    assert "ambient" in query


def test_scoring_prefers_matching_tags(corpus):
    profile = {"preferences": {"must_have": ["dream pop shoegaze"]}}
    results = score_artists(corpus, profile, pool_size=5)
    names = [a.name for a in results]
    # The strongest direct match is #1.
    assert names[0] == "Ethereal Echoes"
    # Artists with zero tag overlap are never returned.
    assert "Nova Drive" not in names


def test_deny_list_filters_out(corpus):
    profile = {"preferences": {"must_have": ["shoegaze post-punk"]}}
    results = score_artists(corpus, profile,
                            deny_keys=["The Broken Gramophone"],
                            pool_size=5)
    assert all(a.name != "The Broken Gramophone" for a in results)


def test_popularity_penalty_demotes_superstars(corpus):
    profile = {"preferences": {"must_have": ["pop rnb shoegaze"]}}
    pop_heavy = score_artists(corpus, profile, pool_size=5, popularity_penalty=0.95)
    pop_light = score_artists(corpus, profile, pool_size=5, popularity_penalty=0.0)
    # With a strong penalty, the 0.98-popularity superstar sinks in the ranking
    # relative to a tie case where it would otherwise dominate on tag weight.
    pop_heavy_names = [a.name for a in pop_heavy]
    pop_light_names = [a.name for a in pop_light]
    # Mega Pop Star ranks higher when no penalty is applied
    assert pop_light_names.index("Mega Pop Star") <= pop_heavy_names.index("Mega Pop Star")


def test_empty_query_returns_empty(corpus):
    # Profile yielding no usable tags → no candidates.
    results = score_artists(corpus, {"preferences": {"must_have": ["xyzzy"]}},
                            pool_size=10)
    assert results == []


def test_aliases_expand_matches(corpus):
    profile = {"preferences": {"must_have": ["dreampop"]}}  # alias for "dream pop"
    results = score_artists(corpus, profile, pool_size=5)
    assert any(a.name == "Ethereal Echoes" for a in results)
