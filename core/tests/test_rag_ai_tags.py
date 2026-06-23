"""Tests for the AI-tags overlay wiring into RAG retrieval (2026-06).

Proves: the ``ai_tags_overlay.json`` sibling is merged at load time; the
DISCRIMINATIVE AI tags (genre/scene/vocal) are indexed so sparse artists
become findable by them; the GENERIC AI tags (mood/rhythm/era/
instrumentation) are deliberately NOT indexed; and the scorer weights an
AI-tag match correctly.
"""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus, normalise_name
from core.src.rag.retrieval import _artist_tag_weight, score_artists


# Sparse-ish corpus: each artist has ≤2 weak MB tags. The AI overlay is
# what carries the discriminative scene signal.
ARTISTS = [
    {"mbid": "m1", "name": "Origami Angel", "tags": ["rock"], "tag_weights": [1],
     "listener_popularity": 0.4},
    {"mbid": "m2", "name": "Mom Jeans", "tags": ["pop"], "tag_weights": [1],
     "listener_popularity": 0.4},
    {"mbid": "m3", "name": "Beyonce", "tags": ["rnb", "pop"], "tag_weights": [9, 8],
     "listener_popularity": 0.95},
]

OVERLAY = {
    "schema_version": 1, "layer": "ai_tags", "model": "gpt-4o-mini",
    "vocabulary_version": "3",
    "entries": {
        # m1/m2 share "midwest emo" ONLY via AI tags (not their MB tags).
        "m1": {"name": "Origami Angel",
               "ai_tags": ["midwest emo", "math rock", "twinkly guitars", "energetic"]},
        "m2": {"name": "Mom Jeans",
               "ai_tags": ["midwest emo", "emo pop", "driving rhythm"]},
        # m3 has no AI entry.
    },
}


@pytest.fixture
def corpus(tmp_path):
    cpath = tmp_path / "artists.jsonl.gz"
    with gzip.open(cpath, "wt", encoding="utf-8") as fh:
        for row in ARTISTS:
            fh.write(json.dumps(row) + "\n")
    (tmp_path / "ai_tags_overlay.json").write_text(json.dumps(OVERLAY), encoding="utf-8")
    return RagCorpus.load(cpath)


def test_overlay_merged_onto_rows(corpus):
    by_mbid = {a.mbid: a for a in corpus.artists}
    assert by_mbid["m1"].ai_tags == ["midwest emo", "math rock", "twinkly guitars", "energetic"]
    assert by_mbid["m2"].ai_tags == ["midwest emo", "emo pop", "driving rhythm"]
    assert by_mbid["m3"].ai_tags == []  # no overlay entry → empty


def test_discriminative_ai_tags_indexed(corpus):
    # Scene tags carried only by AI are now in the inverted index …
    assert "midwest emo" in corpus.tag_index
    assert sorted(corpus.tag_index["midwest emo"]) == [0, 1]  # m1 + m2
    assert "math rock" in corpus.tag_index   # m1
    assert "emo pop" in corpus.tag_index     # m2
    # … and they have a finite positive IDF.
    assert corpus.tag_idf["midwest emo"] > 0


def test_generic_ai_tags_NOT_indexed(corpus):
    # Mood / rhythm / instrumentation AI tags must be excluded.
    assert "energetic" not in corpus.tag_index        # mood
    assert "driving rhythm" not in corpus.tag_index   # rhythm
    assert "twinkly guitars" not in corpus.tag_index  # instrumentation


def test_sparse_artist_findable_via_ai_tag(corpus):
    """A profile asking for 'midwest emo' surfaces m1/m2 even though neither
    carries that tag in MB — only via the AI overlay. This is the fix."""
    profile = {"preferences": {"must_have": ["midwest emo"]}}
    result = score_artists(corpus, profile, pool_size=5)
    names = {normalise_name(a.name) for a in result}
    assert normalise_name("Origami Angel") in names
    assert normalise_name("Mom Jeans") in names
    assert normalise_name("Beyonce") not in names  # no midwest-emo signal


def test_ai_tag_weight(corpus):
    m1 = next(a for a in corpus.artists if a.mbid == "m1")
    # Matched only via an AI tag → constant weight 2 (on par with Spotify).
    assert _artist_tag_weight(m1, "math rock") == 2
    # MB tag still takes priority and returns its own weight.
    assert _artist_tag_weight(m1, "rock") == 1  # tag_weights[0] == 1


def test_no_overlay_file_is_harmless(tmp_path):
    """Loading a corpus with no overlay sibling must not error; ai_tags empty."""
    cpath = tmp_path / "artists.jsonl.gz"
    with gzip.open(cpath, "wt", encoding="utf-8") as fh:
        for row in ARTISTS:
            fh.write(json.dumps(row) + "\n")
    corpus = RagCorpus.load(cpath)
    assert all(a.ai_tags == [] for a in corpus.artists)
    assert "midwest emo" not in corpus.tag_index
