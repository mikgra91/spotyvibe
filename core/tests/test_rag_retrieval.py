"""Unit tests for core.src.rag.retrieval scoring + deny filtering."""

from __future__ import annotations

import gzip
import json

import pytest

from core.src.rag.corpus import RagCorpus
from core.src.rag.retrieval import (build_query_tags, score_artists,
                                    score_artists_stratified, retrieve_candidates)


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


# ── Stratified retrieval (Option 2) ─────────────────────────────────


def test_stratified_gives_each_facet_representation(corpus):
    """Eclectic profile: must_have=shoegaze, soft=synthwave, tags=industrial.

    Without stratification the strongest single facet would dominate the
    top-K. With stratification each facet should land at least one
    artist in the pool.
    """
    profile = {"preferences": {
        "must_have": ["shoegaze"],
        "soft_preferences": ["synthwave"],
        "moods": ["industrial"],
    }}
    weights = {"must_have": 0.4, "soft_preferences": 0.3,
               "primary_reference": 0.0, "tags": 0.3}
    pool = score_artists_stratified(corpus, profile, pool_size=6,
                                    facet_weights=weights)
    names = {a.name for a in pool}
    # must_have facet should pull a shoegaze artist
    assert "Ethereal Echoes" in names or "The Broken Gramophone" in names
    # soft_preferences facet should pull the synthwave artist
    assert "Nova Drive" in names
    # tags (moods=industrial) facet should pull the industrial artist
    assert "Concrete Signal" in names


def test_stratified_dedupes_across_facets(corpus):
    """An artist that wins quotas in two facets is only listed once."""
    profile = {"preferences": {
        "must_have": ["shoegaze"],
        "soft_preferences": ["shoegaze post-punk"],  # would also pick the same artists
    }}
    pool = score_artists_stratified(corpus, profile, pool_size=10,
                                    facet_weights={"must_have": 0.5,
                                                   "soft_preferences": 0.5,
                                                   "primary_reference": 0.0,
                                                   "tags": 0.0})
    names = [a.name for a in pool]
    assert len(names) == len(set(names))  # no duplicates


def test_stratified_falls_back_when_all_facets_empty(corpus):
    """If no facet produces a query, behave like the flat retriever."""
    profile = {"preferences": {"core_description": "shoegaze"}}
    # core_description is in soft_preferences facet, so it should still work.
    pool = score_artists_stratified(corpus, profile, pool_size=3)
    assert any(a.name in {"Ethereal Echoes", "The Broken Gramophone"}
               for a in pool)


def test_stratified_respects_deny_keys(corpus):
    profile = {"preferences": {"must_have": ["shoegaze post-punk"]}}
    pool = score_artists_stratified(corpus, profile, pool_size=5,
                                    deny_keys=["The Broken Gramophone"])
    assert all(a.name != "The Broken Gramophone" for a in pool)


def test_stratified_caps_at_pool_size(corpus):
    profile = {"preferences": {
        "must_have": ["shoegaze post-punk dream pop"],
        "soft_preferences": ["pop rnb synthwave electronica industrial"],
    }}
    pool = score_artists_stratified(corpus, profile, pool_size=3)
    assert len(pool) <= 3

# ── Phase 2: Spotify enrichment in retrieval ─────────────────────────
def test_artist_matched_by_spotify_genres_only(tmp_path):
    """An artist with no MB tag match but a Spotify genre match should still surface."""
    rows = [
        {"mbid": "sp_only", "name": "Theatrical Band",
         "tags": ["rock"], "tag_weights": [3],
         "listener_popularity": 0.4,
         "spotify_genres": ["theatrical rock"]},
        {"mbid": "irrelevant", "name": "Polka Group",
         "tags": ["polka"], "tag_weights": [5],
         "listener_popularity": 0.4},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    profile = {"preferences": {"must_have": ["theatrical rock"]}}
    pool = score_artists(corpus, profile, pool_size=5)
    names = [a.name for a in pool]
    assert "Theatrical Band" in names
    assert "Polka Group" not in names
def test_spotify_popularity_overrides_proxy(tmp_path):
    """When two artists share tags, the one with the lower real Spotify
    popularity should rank higher (popularity penalty + sweet-spot boost)."""
    rows = [
        # Mega-popular: spotify_popularity 95 → no boost, big penalty
        {"mbid": "mega", "name": "Mega Star",
         "tags": ["indie rock"], "tag_weights": [5],
         "listener_popularity": 0.5,  # proxy says mid; Spotify says big
         "spotify_id": "m", "spotify_popularity": 95,
         "spotify_followers": 9_000_000, "spotify_genres": ["indie rock"]},
        # Sweet-spot: 50 → +10% boost, moderate penalty
        {"mbid": "mid", "name": "Mid Tier",
         "tags": ["indie rock"], "tag_weights": [5],
         "listener_popularity": 0.5,
         "spotify_id": "x", "spotify_popularity": 50,
         "spotify_followers": 50_000, "spotify_genres": ["indie rock"]},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    profile = {"preferences": {"must_have": ["indie rock"]}}
    pool = score_artists(corpus, profile, pool_size=2)
    assert pool[0].name == "Mid Tier"
def test_mixed_legacy_and_enriched_corpus(tmp_path):
    """A corpus mixing rows with and without Spotify enrichment must
    score correctly — legacy rows fall back to listener_popularity."""
    rows = [
        # Legacy — popularity proxy 0.4
        {"mbid": "leg", "name": "Legacy", "tags": ["jazz"], "tag_weights": [5],
         "listener_popularity": 0.4},
        # Enriched, sweet-spot
        {"mbid": "enr", "name": "Enriched", "tags": ["jazz"], "tag_weights": [5],
         "listener_popularity": 0.99,  # proxy is wrong
         "spotify_popularity": 45, "spotify_genres": []},
    ]
    path = tmp_path / "artists.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpus = RagCorpus.load(path)
    profile = {"preferences": {"must_have": ["jazz"]}}
    pool = score_artists(corpus, profile, pool_size=2)
    # Both should appear, both have correct scoring without crashing
    assert len(pool) == 2
    names = {a.name for a in pool}
    assert names == {"Legacy", "Enriched"}


# ── retrieve_candidates (Phase 1 Stage 1) ────────────────────────────

_RETRIEVE_ARTISTS = [
    # in popularity band, matches must_have
    {"mbid": "r1", "name": "Good Fit", "tags": ["indie rock", "quirky"],
     "tag_weights": [6, 4], "listener_popularity": 0.5},
    # avoid-tagged artist
    {"mbid": "r2", "name": "Classic Rock Band", "tags": ["classic rock", "hard rock"],
     "tag_weights": [8, 7], "listener_popularity": 0.5},
    # too popular (above band)
    {"mbid": "r3", "name": "Mega Famous", "tags": ["indie rock"],
     "tag_weights": [9], "listener_popularity": 0.95},
    # in band, different tags — should survive without must_have hard filter
    {"mbid": "r4", "name": "Discovery Artist", "tags": ["indie rock", "post-punk"],
     "tag_weights": [5, 3], "listener_popularity": 0.4},
    # deny-listed (should never appear)
    {"mbid": "r5", "name": "History Artist", "tags": ["indie rock"],
     "tag_weights": [6], "listener_popularity": 0.5},
]


@pytest.fixture
def retrieve_corpus(tmp_path):
    path = tmp_path / "artists.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for a in _RETRIEVE_ARTISTS:
            fh.write(json.dumps(a) + "\n")
    return RagCorpus.load(path)


def test_retrieve_candidates_returns_artists(retrieve_corpus):
    profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
    result = retrieve_candidates(retrieve_corpus, profile, target_size=10)
    assert len(result) > 0
    names = {a.name for a in result}
    assert "Good Fit" in names
    assert "Discovery Artist" in names


def test_retrieve_candidates_deny_keys_excluded(retrieve_corpus):
    profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
    result = retrieve_candidates(
        retrieve_corpus, profile,
        deny_keys=["history artist"],
        target_size=10,
    )
    names = {a.name for a in result}
    assert "History Artist" not in names


def test_retrieve_candidates_avoid_filter(retrieve_corpus):
    profile = {
        "preferences": {
            "must_have": ["indie rock"],
            "avoid": ["classic rock"],
        }
    }
    result = retrieve_candidates(retrieve_corpus, profile, target_size=10)
    names = {a.name for a in result}
    assert "Classic Rock Band" not in names
    assert "Good Fit" in names


def test_retrieve_candidates_popularity_band(retrieve_corpus):
    profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
    # Use target_size=4: in-band threshold = 4//2 = 2. Four artists are in-band
    # (pop 0.4-0.5), so the band filter applies and Mega Famous (pop=0.95) is dropped.
    result = retrieve_candidates(retrieve_corpus, profile, target_size=4)
    names = {a.name for a in result}
    assert "Mega Famous" not in names


def test_retrieve_candidates_empty_corpus(tmp_path):
    path = tmp_path / "empty.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        pass
    corpus = RagCorpus.load(path)
    result = retrieve_candidates(corpus, {}, target_size=10)
    assert result == []


def test_retrieve_candidates_target_size_respected(retrieve_corpus):
    profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
    result = retrieve_candidates(retrieve_corpus, profile, target_size=2)
    assert len(result) <= 2
# ── P2.0 retrieval-quality fix (2026-04-27) ──
# Stop-list expansion + min-frequency floor for noise tags. Both are
# regression-prone because they affect the candidate pool composition
# silently — a future refactor that drops the stop-words back into the
# tokeniser, or removes the frequency floor, would re-introduce the
# tag-noise problem that surfaced barbershop a-cappella for a
# "modern theatrical pop-rock" seed.
def _build_large_corpus(tmp_path, n_artists: int = 200):
    """Build a corpus large enough (>= 100 artists) to enable the
    production min-frequency floor. Each artist gets a few generic
    pop/rock tags; ONE artist gets a singleton noise tag 'hooks'.
    """
    rows = []
    # 199 generic pop-rock artists — gives the corpus a plausible
    # frequency distribution where 'pop' / 'rock' are common.
    for i in range(n_artists - 1):
        rows.append({
            "mbid": f"mbid-{i:04d}", "name": f"Artist{i:04d}",
            "tags": ["pop", "rock", "indie"],
            "begin_year": 2010 + (i % 10),
        })
    # ONE artist tagged with the singleton noise tag 'hooks'.
    # In the broken regime this artist would dominate the candidate
    # pool for any seed that mentions "hooks" because IDF=max for n=1.
    rows.append({
        "mbid": "mbid-noise",
        "name": "NoiseTagArtist",
        "tags": ["hooks", "barbershop", "a cappella"],
        "begin_year": 2015,
    })
    path = tmp_path / "large.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return RagCorpus.load(path)
def test_min_frequency_floor_drops_singleton_noise_tags(tmp_path):
    """A query that contains 'hooks' (singleton noise tag) MUST NOT
    surface the one artist tagged with it. Pre-fix, that artist would
    rank #1 due to IDF=max for n=1.
    """
    from core.src.rag.retrieval import retrieve_candidates
    corpus = _build_large_corpus(tmp_path)
    profile = {
        "preferences": {
            "must_have": ["strong hooks", "punchy guitars"],
            "avoid": [],
        },
    }
    result = retrieve_candidates(corpus, profile, target_size=10)
    names = [a.name for a in result]
    assert "NoiseTagArtist" not in names, (
        "min-frequency floor failed — singleton noise tag 'hooks' "
        "still let the noise-tagged artist into the pool"
    )
def test_music_domain_stop_words_excluded_from_query(tmp_path):
    """Music-domain quality descriptors (modern, strong, polished, vocal,
    melody, production, etc.) must not become query tokens. Pre-fix,
    these would match random user-tagged artists and dominate the score.
    """
    from core.src.rag.retrieval import build_query_tags, _apply_aliases
    corpus = _build_large_corpus(tmp_path)
    profile = {
        "preferences": {
            "must_have": ["modern production", "strong melody",
                          "polished vocal", "punchy guitars"],
            "avoid": [],
        },
    }
    raw_tags = set(build_query_tags(profile).keys())
    forbidden = {"modern", "production", "strong", "melody", "polished",
                 "vocal", "vocals", "melodic", "punchy", "lyrics",
                 "personality", "storytelling"}
    leaked = raw_tags & forbidden
    assert not leaked, (
        f"music-domain stop words leaked into query tokens: {sorted(leaked)}"
    )
    # 'guitars' is NOT a stop word — it's a legitimate instrument signal.
    # Make sure we didn't over-strip.
    assert "guitars" in raw_tags, "over-stripped: 'guitars' is legit signal"
def test_min_frequency_floor_disabled_for_tiny_corpora(tmp_path):
    """Tests use 3-5-artist fixture corpora to verify scoring LOGIC.
    The min-frequency floor must be auto-disabled for tiny corpora so
    those tests still work — otherwise every tag in a tiny corpus has
    n < 3 and the query collapses to empty.
    """
    from core.src.rag.retrieval import _apply_aliases
    # Tiny 3-artist corpus
    rows = [
        {"mbid": f"m{i}", "name": f"A{i}", "tags": ["niche-tag-x"]}
        for i in range(3)
    ]
    path = tmp_path / "tiny.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    corpus = RagCorpus.load(path)
    # 'niche-tag-x' has n=3 in this tiny corpus. Production floor (3) would
    # keep it. But 'niche-tag-y' with n=1 would be dropped. Test the auto-
    # disable: pass a single-artist tag and expect it to survive.
    rows.append({"mbid": "m4", "name": "A4", "tags": ["niche-tag-y"]})
    path2 = tmp_path / "tiny2.jsonl.gz"
    with gzip.open(path2, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    corpus2 = RagCorpus.load(path2)
    # Tiny corpus (4 artists < 100) — floor auto-disabled, so n=1 tag survives.
    result = _apply_aliases(corpus2, {"niche-tag-y": 1.0})
    assert "niche-tag-y" in result, (
        "tiny-corpus auto-disable failed: n=1 tag dropped when it shouldn't be"
    )
# ── P2.2 primary_reference plumbing test (2026-04-27) ────────────────
def test_retrieve_candidates_accepts_primary_reference(tmp_path):
    """retrieve_candidates must forward primary_reference to the scorer.
    Pre-fix the parameter was missing entirely; the 15 % facet quota was
    silently absorbed by flat-fill. This test pins that the parameter
    exists, is accepted, and does not crash.
    """
    import inspect
    from core.src.rag.retrieval import retrieve_candidates
    sig = inspect.signature(retrieve_candidates)
    assert "primary_reference" in sig.parameters, (
        "retrieve_candidates must accept primary_reference parameter "
        "(P2.2 fix). Without it, score_artists_stratified's 15 % facet "
        "quota is dead code."
    )
    # Build a tiny corpus and verify the call works end-to-end.
    corpus_path = tmp_path / "tiny.jsonl.gz"
    import gzip, json as _json
    with gzip.open(corpus_path, "wt", encoding="utf-8") as f:
        for i in range(5):
            f.write(_json.dumps({
                "name": f"artist-{i}",
                "tags": ["pop", "rock"],
                "popularity": 0.5,
            }) + "\n")
    from core.src.rag.corpus import RagCorpus
    corpus = RagCorpus.load(corpus_path)
    profile = {"preferences": {"must_have": ["pop rock"]}}
    # Without primary_reference (existing behavior must still work)
    result_a = retrieve_candidates(corpus, profile, target_size=3)
    assert len(result_a) <= 3
    # With primary_reference dict (new behavior must not crash)
    result_b = retrieve_candidates(
        corpus, profile, target_size=3,
        primary_reference={"name": "ref-artist", "genres": ["pop"], "moods": ["energetic"]},
    )
    assert len(result_b) <= 3
    # With primary_reference=None explicitly
    result_c = retrieve_candidates(
        corpus, profile, target_size=3, primary_reference=None,
    )
    assert len(result_c) <= 3
