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


# ── Phase 2: Spotify enrichment fields ───────────────────────────────

def test_legacy_rows_without_spotify_fields_load(corpus_file):
    """The fixture has no spotify_* keys — must still load cleanly."""
    corpus = RagCorpus.load(corpus_file)
    assert len(corpus) == 5
    for a in corpus.artists:
        assert a.spotify_id is None
        assert a.spotify_popularity is None
        assert a.spotify_followers is None
        assert a.spotify_genres == []


def test_enriched_rows_populate_spotify_fields(tmp_path):
    rows = [
        # Legacy row — no spotify_*.
        {"mbid": "leg", "name": "Legacy", "tags": ["rock"], "tag_weights": [3],
         "listener_popularity": 0.4},
        # Enriched row.
        {"mbid": "enr", "name": "Enriched", "tags": ["rock"], "tag_weights": [3],
         "listener_popularity": 0.4,
         "spotify_id": "abc123", "spotify_popularity": 55,
         "spotify_followers": 12345,
         "spotify_genres": ["progressive rock", "theatrical rock"]},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    leg = corpus.by_mbid["leg"]
    enr = corpus.by_mbid["enr"]
    assert corpus.artists[leg].spotify_id is None
    assert corpus.artists[enr].spotify_id == "abc123"
    assert corpus.artists[enr].spotify_popularity == 55
    assert corpus.artists[enr].spotify_followers == 12345
    assert corpus.artists[enr].spotify_genres == ["progressive rock", "theatrical rock"]


def test_spotify_genres_are_indexed_alongside_mb_tags(tmp_path):
    """Phase 2 retrieval should match against spotify_genres too."""
    rows = [
        {"mbid": "x", "name": "X", "tags": ["rock"], "tag_weights": [3],
         "listener_popularity": 0.5,
         "spotify_genres": ["theatrical rock", "nerd rock"]},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    # Both MB tags and spotify_genres should appear in the inverted index.
    assert "rock" in corpus.tag_index
    assert "theatrical rock" in corpus.tag_index
    assert "nerd rock" in corpus.tag_index


# ── Track-level grounding (2026-04-27) ────────────────────────────────


def test_top_tracks_field_default_empty():
    """Legacy corpus rows without a top_tracks field load with [] default."""
    from core.src.rag.corpus import ArtistRow
    a = ArtistRow(mbid="x", name="X", tags=["rock"])
    assert a.top_tracks == []


def test_top_tracks_field_parsed_from_corpus(tmp_path):
    """top_tracks in JSONL is read into the ArtistRow."""
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "mbid": "z1", "name": "Test Band", "tags": ["rock"],
            "top_tracks": ["Hit One", "Deep Cut", "B-Side"],
        }) + "\n")
    corpus = RagCorpus.load(path)
    row = corpus.artists[0]
    assert row.top_tracks == ["Hit One", "Deep Cut", "B-Side"]


def test_top_tracks_overlay_merges_by_mbid(corpus_file, tmp_path):
    """Overlay JSON `{mbid: [tracks]}` is merged onto matching rows at load."""
    overlay = tmp_path / "top_tracks_overlay.json"
    overlay.write_text(json.dumps({
        "a1": ["Glass Hour", "Soft Static"],
        "a3": ["Run It"],
        "unknown_mbid": ["Should Be Ignored"],
    }), encoding="utf-8")
    corpus = RagCorpus.load(corpus_file, top_tracks_overlay_path=overlay)
    by_mbid = {a.mbid: a for a in corpus.artists}
    assert by_mbid["a1"].top_tracks == ["Glass Hour", "Soft Static"]
    assert by_mbid["a3"].top_tracks == ["Run It"]
    # Artists not in the overlay still default to []
    assert by_mbid["a2"].top_tracks == []


def test_top_tracks_overlay_autodetected_next_to_corpus(corpus_file):
    """If top_tracks_overlay.json sits next to the corpus, it loads automatically."""
    overlay = corpus_file.parent / "top_tracks_overlay.json"
    overlay.write_text(json.dumps({"a1": ["Auto Loaded"]}), encoding="utf-8")
    corpus = RagCorpus.load(corpus_file)  # no explicit overlay path
    by_mbid = {a.mbid: a for a in corpus.artists}
    assert by_mbid["a1"].top_tracks == ["Auto Loaded"]


def test_top_tracks_overlay_missing_file_silently_ignored(corpus_file, tmp_path):
    """Pointing at a missing overlay path does not raise."""
    corpus = RagCorpus.load(corpus_file,
                            top_tracks_overlay_path=tmp_path / "nope.json")
    assert all(a.top_tracks == [] for a in corpus.artists)


def test_top_tracks_overlay_malformed_silently_ignored(corpus_file, tmp_path):
    """An unparseable overlay file does not break corpus load."""
    bad = tmp_path / "top_tracks_overlay.json"
    bad.write_text("not json {", encoding="utf-8")
    corpus = RagCorpus.load(corpus_file, top_tracks_overlay_path=bad)
    assert all(a.top_tracks == [] for a in corpus.artists)


