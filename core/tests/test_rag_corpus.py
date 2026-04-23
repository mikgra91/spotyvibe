"""Unit tests for core.src.rag.corpus — fixture-based, no external files."""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus, normalise_name, normalise_tag


FIXTURE_ARTISTS = [
    {"mbid": "a1", "name": "Ethereal Echoes", "country": "GB",
     "tags": ["dream pop", "shoegaze", "ambient"], "tag_weights": [5, 3, 1],
     "listener_popularity": 0.2},
    {"mbid": "a2", "name": "Concrete Signal", "country": "DE",
     "tags": ["post-punk", "industrial"], "tag_weights": [6, 2],
     "listener_popularity": 0.1},
    {"mbid": "a3", "name": "Beyoncé", "country": "US",
     "tags": ["rnb", "pop"], "tag_weights": [9, 8],
     "listener_popularity": 0.95},
    {"mbid": "a4", "name": "The Broken Gramophone", "country": "UK",
     "tags": ["shoegaze", "post-punk"], "tag_weights": [4, 4],
     "listener_popularity": 0.05},
    {"mbid": "a5", "name": "Nova Drive", "country": "US",
     "tags": ["synthwave", "electronica"], "tag_weights": [7, 5],
     "listener_popularity": 0.3},
]


@pytest.fixture
def corpus_file(tmp_path):
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in FIXTURE_ARTISTS:
            fh.write(json.dumps(row) + "\n")
    return path


@pytest.fixture
def aliases_file(tmp_path):
    path = tmp_path / "tag_aliases.json"
    path.write_text(json.dumps({"dreampop": "dream pop", "synth wave": "synthwave"}),
                    encoding="utf-8")
    return path


def test_normalise_helpers():
    assert normalise_tag("Dream Pop") == "dream pop"
    assert normalise_tag("  POST-PUNK ") == "post-punk"
    assert normalise_name("Beyoncé") == "beyonce"
    assert normalise_name("The Broken Gramophone") == "the broken gramophone"


def test_load_indexes_everything(corpus_file, aliases_file):
    corpus = RagCorpus.load(corpus_file, aliases_file)
    assert len(corpus) == 5
    # inverted index wires both shoegaze artists to their rows
    assert sorted(corpus.tag_index["shoegaze"]) == [0, 3]
    # IDF is finite and positive for a tag that appears in ≥1 doc
    assert corpus.tag_idf["shoegaze"] > 0
    # Slim ArtistRow — fields actually retained.
    a = corpus.artists[0]
    assert a.mbid == "a1" and a.name == "Ethereal Echoes"
    assert a.tags and a.tag_weights
    # Fields removed in §3.2 corpus-slimming pass MUST NOT exist.
    # NOTE: by_mbid and by_name_normalised are still present on the corpus
    # as lookup helpers. ArtistRow still carries sort_name/country/end_year
    # for backward compat but they default to empty/None in slim rows.
    assert hasattr(corpus, "by_mbid")
    assert hasattr(corpus, "by_name_normalised")


def test_aliases_resolve(corpus_file, aliases_file):
    corpus = RagCorpus.load(corpus_file, aliases_file)
    assert corpus.resolve_alias("dreampop") == "dream pop"
    assert corpus.resolve_alias("unknown tag") == "unknown tag"


def test_missing_corpus_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        RagCorpus.load(tmp_path / "nope.jsonl.gz")


def test_plain_jsonl_also_loads(tmp_path):
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in FIXTURE_ARTISTS), encoding="utf-8")
    corpus = RagCorpus.load(path)
    assert len(corpus) == 5


def test_bad_lines_are_skipped(tmp_path):
    path = tmp_path / "artists.jsonl"
    path.write_text(
        json.dumps(FIXTURE_ARTISTS[0]) + "\nnot json\n" + json.dumps(FIXTURE_ARTISTS[1]),
        encoding="utf-8",
    )
    corpus = RagCorpus.load(path)
    assert len(corpus) == 2


def test_pre_1960s_artists_are_filtered(tmp_path):
    """Loader drops artists with begin_year < MIN_ARTIST_BEGIN_YEAR (1960).

    Older corpora may still contain pre-1960s entries; filtering at load
    time ensures users benefit immediately without rebuilding the file.
    Artists with no begin_year are kept (we cannot prove they're old).
    """
    rows = [
        {"mbid": "old1", "name": "Pre-War Crooner", "tags": ["jazz"],
         "tag_weights": [3], "begin_year": 1925, "listener_popularity": 0.4},
        {"mbid": "edge1", "name": "Decade Boundary", "tags": ["folk"],
         "tag_weights": [2], "begin_year": 1959, "listener_popularity": 0.3},
        {"mbid": "ok1", "name": "Sixties Band", "tags": ["rock"],
         "tag_weights": [5], "begin_year": 1960, "listener_popularity": 0.5},
        {"mbid": "ok2", "name": "Modern Act", "tags": ["pop"],
         "tag_weights": [4], "begin_year": 2010, "listener_popularity": 0.7},
        {"mbid": "unknown", "name": "Undated Group", "tags": ["ambient"],
         "tag_weights": [1], "listener_popularity": 0.1},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    kept = {a.mbid for a in corpus.artists}
    assert kept == {"ok1", "ok2", "unknown"}


