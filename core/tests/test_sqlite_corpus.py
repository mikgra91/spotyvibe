"""Tests for the on-disk SQLite corpus backend.

Guards the core guarantee: the SQLite-backed corpus serves byte-identical data
and produces identical retrieval results to the in-memory RagCorpus, and its
signature invalidation triggers a rebuild when inputs change.
"""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus
from core.src.rag.retrieval import score_artists
from core.src.rag.sqlite_corpus import (
    SqliteCorpus, build_sqlite_corpus, corpus_signature, is_sqlite_corpus_valid,
)

FIXTURE_ARTISTS = [
    {"mbid": "a1", "name": "Ethereal Echoes", "country": "GB",
     "tags": ["dream pop", "shoegaze", "ambient"], "tag_weights": [5, 3, 1],
     "listener_popularity": 0.2, "spotify_genres": ["shoegaze"],
     "lastfm_tags": [["indie", 40]], "ai_tags": ["dreamy"]},
    {"mbid": "a2", "name": "Concrete Signal", "country": "DE",
     "tags": ["post-punk", "industrial"], "tag_weights": [6, 2],
     "listener_popularity": 0.1},
    {"mbid": "a3", "name": "Nova Drive", "country": "US",
     "tags": ["synthwave", "electronica"], "tag_weights": [7, 5],
     "listener_popularity": 0.3, "top_tracks": ["Midnight Run"]},
    {"mbid": "a4", "name": "The Broken Gramophone", "country": "GB",
     "tags": ["shoegaze", "post-punk"], "tag_weights": [4, 4],
     "listener_popularity": 0.05, "lastfm_tags": [["shoegaze", 90]]},
]


@pytest.fixture
def ram_corpus(tmp_path):
    corpus_file = tmp_path / "artists.jsonl.gz"
    with gzip.open(corpus_file, "wt", encoding="utf-8") as fh:
        for row in FIXTURE_ARTISTS:
            fh.write(json.dumps(row) + "\n")
    aliases_file = tmp_path / "tag_aliases.json"
    aliases_file.write_text(json.dumps({"dreampop": "dream pop"}), encoding="utf-8")
    corpus = RagCorpus.load(corpus_file, aliases_file)
    return corpus, corpus_file, aliases_file


@pytest.fixture
def sqlite_corpus(ram_corpus, tmp_path):
    ram, corpus_file, aliases_file = ram_corpus
    db = tmp_path / "corpus.sqlite"
    sig = corpus_signature(corpus_file, aliases_file)
    build_sqlite_corpus(ram, db, sig)
    return SqliteCorpus.open(db), db, sig


def test_data_parity(ram_corpus, sqlite_corpus):
    ram, corpus_file, aliases_file = ram_corpus
    sq, _db, _sig = sqlite_corpus

    assert len(sq) == len(ram)

    # tag_index + postings identical for every tag
    for tag in ram.tag_index:
        assert tag in sq.tag_index
        assert list(sq.tag_index.get(tag)) == list(ram.tag_index.get(tag))
        r_idf, r_idx, r_w = ram.postings(tag)
        s_idf, s_idx, s_w = sq.postings(tag)
        assert s_idf == pytest.approx(r_idf)
        assert list(s_idx) == list(r_idx)
        assert list(s_w) == list(r_w)

    # unknown tag → empty postings, idf default 1.0 (matches RagCorpus)
    assert sq.postings("no-such-tag") == (1.0, [], []) or \
        (sq.postings("no-such-tag")[0] == 1.0 and len(sq.postings("no-such-tag")[1]) == 0)
    assert "no-such-tag" not in sq.tag_index

    # artists identical (dataclass equality after pickle round-trip)
    for i in range(len(ram.artists)):
        assert sq.artists[i] == ram.artists[i]

    # name + alias lookups identical
    from core.src.rag.corpus import normalise_name
    for a in ram.artists:
        nkey = normalise_name(a.name)
        assert sq.by_name_normalised.get(nkey) == ram.by_name_normalised.get(nkey)
    assert sq.resolve_alias("dreampop") == ram.resolve_alias("dreampop")
    assert sq.resolve_alias("shoegaze") == ram.resolve_alias("shoegaze")


def test_retrieval_identical(ram_corpus, sqlite_corpus):
    ram, *_ = ram_corpus
    sq, *_ = sqlite_corpus
    profile = {"preferences": {
        "genres": ["shoegaze", "post-punk", "dream pop"],
        "must_have": ["synthwave"],
    }}
    r_pool = score_artists(ram, profile, pool_size=4)
    s_pool = score_artists(sq, profile, pool_size=4)
    assert [a.mbid for a in s_pool] == [a.mbid for a in r_pool]
    assert len(s_pool) > 0  # sanity: the query actually matched


def test_signature_invalidation(ram_corpus, sqlite_corpus):
    ram, corpus_file, aliases_file = ram_corpus
    sq, db, sig = sqlite_corpus

    # matching signature is valid
    assert is_sqlite_corpus_valid(db, sig)
    # a different signature (e.g. corpus changed) is stale
    assert not is_sqlite_corpus_valid(db, sig + "-changed")
    # touching the corpus file changes the computed signature
    corpus_file.write_bytes(corpus_file.read_bytes() + b"\n")
    assert corpus_signature(corpus_file, aliases_file) != sig
    assert not is_sqlite_corpus_valid(db, corpus_signature(corpus_file, aliases_file))


def test_missing_db_is_invalid(tmp_path):
    assert not is_sqlite_corpus_valid(tmp_path / "nope.sqlite", "any-sig")
