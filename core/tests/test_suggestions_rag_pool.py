"""Tests for the get_last_rag_pool_names() contract added in follow-up #1.

This is what the eval log relies on to capture the *actual* candidate pool
shown to the LLM (rather than re-running the scorer).
"""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus
from core.src import suggestions as sugg


_ARTISTS = [
    {"mbid": "a1", "name": "Ethereal Echoes",
     "tags": ["dream pop", "shoegaze"], "tag_weights": [5, 3],
     "listener_popularity": 0.1},
    {"mbid": "a2", "name": "The Broken Gramophone",
     "tags": ["shoegaze", "post-punk"], "tag_weights": [4, 4],
     "listener_popularity": 0.05},
]


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for a in _ARTISTS:
            fh.write(json.dumps(a) + "\n")
    aliases = tmp_path / "tag_aliases.json"
    aliases.write_text(json.dumps({}), encoding="utf-8")
    return RagCorpus.load(path, aliases)


def _profile() -> dict:
    return {
        "preferences": {
            "must_have": ["dream pop"],
            "soft_preferences": ["shoegaze"],
            "avoid": [],
        },
        "history": {"suggested_artists": [], "suggested_tracks": []},
        "artists": {"confirmed": [], "rejected": []},
        "feedback": {"liked_tracks": [], "disliked_tracks": [], "disliked_artists": []},
    }


def test_get_last_rag_pool_names_none_when_no_corpus():
    """When no corpus is installed, the captured pool must be None — *not* []
    — so the eval log can still distinguish "RAG off" from "RAG on, empty pool"."""
    sugg.set_rag_corpus(None)
    sugg.build_messages(_profile(), batch_size=10)
    assert sugg.get_last_rag_pool_names() is None


def test_get_last_rag_pool_names_captures_actual_pool(corpus):
    """When RAG is enabled, the captured names must match the artists the
    prompt actually carries — i.e. what the LLM was shown."""
    sugg.set_rag_corpus(corpus)
    try:
        messages = sugg.build_messages(_profile(), batch_size=10)
        captured = sugg.get_last_rag_pool_names()
        assert captured is not None
        assert len(captured) > 0
        # Each captured name must appear verbatim in the user message —
        # this is the actual pool the LLM saw.
        user_msg = messages[1]["content"]
        for name in captured:
            assert name in user_msg, f"{name!r} missing from prompt"
    finally:
        sugg.set_rag_corpus(None)


def test_get_last_rag_pool_names_resets_on_new_call(corpus):
    """A subsequent build_messages() with no corpus must clear the previous pool."""
    sugg.set_rag_corpus(corpus)
    sugg.build_messages(_profile(), batch_size=10)
    assert sugg.get_last_rag_pool_names() is not None

    sugg.set_rag_corpus(None)
    sugg.build_messages(_profile(), batch_size=10)
    assert sugg.get_last_rag_pool_names() is None


def test_rag_bypassed_when_emerging_only(corpus):
    """When ``emerging_only=True``, RAG must NOT inject a candidate pool.

    The corpus is built quarterly and cannot contain artists who debuted in
    the last 6 months, so injecting it would contradict the system constraint
    *"only suggest tracks by artists whose debut release is within the last
    6 months"*. This verifies the bypass introduced together with the
    stratified retrieval (Option 2) decision — see report
    spotyvibe-decisions-2026-04-21.md.
    """
    sugg.set_rag_corpus(corpus)
    try:
        messages = sugg.build_messages(_profile(), batch_size=10,
                                       emerging_only=True)
        assert sugg.get_last_rag_pool_names() is None
        # The CANDIDATE_POOL block header must NOT appear in the prompt.
        user_msg = messages[1]["content"]
        assert "CANDIDATE_POOL" not in user_msg
    finally:
        sugg.set_rag_corpus(None)


def test_rag_active_when_emerging_only_false(corpus):
    """Counterpart: with ``emerging_only=False`` the pool must still inject."""
    sugg.set_rag_corpus(corpus)
    try:
        messages = sugg.build_messages(_profile(), batch_size=10,
                                       emerging_only=False)
        assert sugg.get_last_rag_pool_names() is not None
        assert "CANDIDATE_POOL" in messages[1]["content"]
    finally:
        sugg.set_rag_corpus(None)


