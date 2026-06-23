"""Tests for the layered corpus merge (build-tools/rag/merge_corpus.py).

Proves the property the project owner asked for: each enrichment layer
(MusicBrainz base, Last.fm, AI) updates **independently** — rebuilding
one layer carries the other two forward by ``mbid`` instead of losing
them. Fixtures are taken verbatim from the real production corpus
(``%LOCALAPPDATA%/spotyvibe/rag_corpus/artists.jsonl.gz``) so the merge
is exercised against real-shaped data, then mutated with dummy values.
"""

from __future__ import annotations

import gzip
import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools" / "rag"))

import merge_corpus as M  # noqa: E402

# ── Real corpus rows (sampled from the production corpus) ─────────────
# Three enriched (MB + Last.fm) and two MB-only — exactly the mix the
# merge must handle. `lastfm_tags` use the on-disk [[name, weight], ...]
# pair shape.
BEATLES = {
    "mbid": "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d", "name": "The Beatles",
    "begin_year": 1960,
    "tags": ["rock", "pop", "pop rock", "british", "psychedelic pop", "merseybeat"],
    "tag_weights": [10, 8, 7, 6, 5, 4], "listener_popularity": 0.999,
    "lastfm_listeners": 6537415, "lastfm_playcount": 700000000,
    "lastfm_tags": [["classic rock", 100], ["rock", 79], ["british", 45], ["60s", 43]],
    "top_tracks": ["Here Comes the Sun - Remastered 2009", "Hey Jude", "Eleanor Rigby"],
}
METALLICA = {
    "mbid": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab", "name": "Metallica",
    "begin_year": 1981,
    "tags": ["thrash metal", "heavy metal", "metal", "hard rock", "american"],
    "tag_weights": [9, 8, 7, 5, 3], "listener_popularity": 0.997,
    "lastfm_listeners": 5204537, "lastfm_playcount": 600000000,
    "lastfm_tags": [["heavy metal", 100], ["metal", 64], ["hard rock", 40]],
    "top_tracks": ["Enter Sandman", "Nothing Else Matters", "Master of Puppets"],
}
SB19 = {
    "mbid": "9252ca18-015c-484c-ae59-5670784887d3", "name": "SB19",
    "begin_year": 2018,
    "tags": ["p-pop", "filipino", "pinoy pop", "opm", "pinoy", "ppop"],
    "tag_weights": [6, 5, 4, 3, 2, 1], "listener_popularity": 0.40,
    "lastfm_listeners": 98350, "lastfm_playcount": 5000000,
    "lastfm_tags": [["filipino", 100], ["pop", 100], ["ppop", 66]],
    "top_tracks": ["Gento", "MAPA", "I WANT YOU"],
}
KISS = {  # MB-only — no Last.fm fields
    "mbid": "e1f1e33e-2e4c-4d43-b91b-7064068d3283", "name": "KISS",
    "begin_year": 1973,
    "tags": ["hard rock", "glam rock", "glam metal", "rock", "classic rock", "heavy metal"],
    "tag_weights": [7, 6, 5, 4, 3, 2], "listener_popularity": 0.95,
}
YE = {  # MB-only — no Last.fm fields
    "mbid": "164f0d73-1234-4e2c-8743-d77bf2191051", "name": "Ye",
    "begin_year": 1996,
    "tags": ["hip hop", "pop rap", "experimental hip hop", "pop", "christian hip hop", "producer"],
    "tag_weights": [8, 6, 5, 4, 3, 2], "listener_popularity": 0.96,
}

REAL_CORPUS = Path("C:/Users/micha/AppData/Local/spotyvibe/rag_corpus/artists.jsonl.gz")


def _mb_only(row: dict) -> dict:
    """A fresh-MB-build view of *row* — mbid + MB-owned fields only."""
    out = {"mbid": row["mbid"]}
    out.update({f: row[f] for f in M.MB_FIELDS if f in row})
    return out


# ── 1. MB update keeps Last.fm + AI (carry-forward) ──────────────────

def test_mb_update_preserves_lastfm_and_carried_ai():
    # Previous published row had Last.fm baked AND ai_tags from a prior
    # local enrichment cycle.
    prev = dict(BEATLES, ai_tags=["british invasion", "60s pop rock"],
                ai_confidence="high")
    # Fresh MB dump changed the tag list (dummy mutation) + popularity drift.
    new = _mb_only(BEATLES)
    new["tags"] = ["rock", "pop rock", "baroque pop"]   # genuinely changed
    new["tag_weights"] = [10, 7, 3]
    new["listener_popularity"] = 0.998                  # rank drift only

    merged, stats = M.merge_layers([new], [prev])
    row = merged[0]

    # MB layer updated from the fresh build …
    assert row["tags"] == ["rock", "pop rock", "baroque pop"]
    assert row["tag_weights"] == [10, 7, 3]
    # … Last.fm layer carried forward untouched …
    assert row["lastfm_listeners"] == 6537415
    assert row["lastfm_tags"] == BEATLES["lastfm_tags"]
    assert row["top_tracks"] == BEATLES["top_tracks"]
    # … AI layer survived.
    assert row["ai_tags"] == ["british invasion", "60s pop rock"]
    assert row["ai_confidence"] == "high"
    assert stats["mb_changed"] == 1
    assert stats["lastfm_carried"] == 1
    assert stats["ai_carried"] == 1
    assert stats["needs_lastfm"] == []


# ── 2. Last.fm update keeps MB + AI ──────────────────────────────────

def test_lastfm_refresh_preserves_mb_and_ai():
    prev = dict(METALLICA, ai_tags=["bay area thrash"], ai_confidence="high")
    new = _mb_only(METALLICA)  # MB unchanged this cycle
    # A fresh Last.fm fetch returns new listener counts + tags (dummy).
    lastfm_overlay = {
        METALLICA["mbid"]: {
            "lastfm_listeners": 5300000,
            "lastfm_playcount": 610000000,
            "lastfm_tags": [["thrash metal", 100], ["metal", 70]],
            "top_tracks": ["One", "Battery", "Fade to Black"],
        }
    }
    merged, stats = M.merge_layers([new], [prev], lastfm_overlay=lastfm_overlay)
    row = merged[0]

    # Last.fm layer replaced by the fresh fetch …
    assert row["lastfm_listeners"] == 5300000
    assert row["top_tracks"] == ["One", "Battery", "Fade to Black"]
    # … MB layer untouched …
    assert row["tags"] == METALLICA["tags"]
    assert row["name"] == "Metallica"
    # … AI layer survived.
    assert row["ai_tags"] == ["bay area thrash"]
    assert stats["lastfm_fresh"] == 1
    assert stats["mb_unchanged"] == 1


# ── 3. AI overlay survives a full rebuild of MB + Last.fm ────────────

def test_ai_overlay_survives_full_rebuild():
    # Previous corpus carries NO ai_tags; the AI layer arrives only as a
    # separate overlay (mirrors today's ai_tags_overlay.json shape).
    prev = [BEATLES, METALLICA, SB19]
    # Brutal rebuild: every MB field changes; Last.fm comes fresh too.
    new_mb = []
    for r in prev:
        m = _mb_only(r)
        m["tags"] = ["totally", "different", "tags"]
        m["name"] = r["name"] + " (remastered dump)"
        m["listener_popularity"] = 0.123
        new_mb.append(m)
    ai_overlay = {
        BEATLES["mbid"]: {"ai_tags": ["british invasion"], "ai_confidence": "high"},
        SB19["mbid"]: {"ai_tags": ["p-pop", "k-pop influence"], "ai_confidence": "med"},
        # Metallica intentionally absent from the AI overlay.
    }
    merged, stats = M.merge_layers(new_mb, prev, ai_overlay=ai_overlay)
    by_mbid = {r["mbid"]: r for r in merged}

    # AI tags attach to the right artist by mbid despite the rebuild.
    assert by_mbid[BEATLES["mbid"]]["ai_tags"] == ["british invasion"]
    assert by_mbid[SB19["mbid"]]["ai_tags"] == ["p-pop", "k-pop influence"]
    assert "ai_tags" not in by_mbid[METALLICA["mbid"]]
    # Last.fm carried forward through the rebuild …
    assert by_mbid[METALLICA["mbid"]]["lastfm_listeners"] == 5204537
    # … and the fresh MB layer is the authoritative one.
    assert by_mbid[BEATLES["mbid"]]["tags"] == ["totally", "different", "tags"]
    assert stats["ai_fresh"] == 2
    assert stats["lastfm_carried"] == 3


# ── 4. New artist is flagged for Last.fm; enriched ones are not ──────

def test_new_artist_flagged_for_lastfm_fetch():
    prev = [BEATLES]                       # only Beatles previously enriched
    new_mb = [_mb_only(BEATLES), _mb_only(KISS), _mb_only(YE)]
    merged, stats = M.merge_layers(new_mb, prev)

    # Beatles already has Last.fm → not in the delta; KISS + Ye are new.
    assert set(stats["needs_lastfm"]) == {KISS["mbid"], YE["mbid"]}
    assert stats["added"] == 2
    assert stats["lastfm_carried"] == 1
    # The delta is exactly what the Last.fm pass must fetch — far fewer
    # than the full corpus.
    assert BEATLES["mbid"] not in stats["needs_lastfm"]


# ── 5. Removed MB record is dropped ──────────────────────────────────

def test_removed_artist_is_dropped():
    prev = [BEATLES, METALLICA, SB19]
    new_mb = [_mb_only(BEATLES), _mb_only(SB19)]   # Metallica gone from MB dump
    merged, stats = M.merge_layers(new_mb, prev)

    assert {r["mbid"] for r in merged} == {BEATLES["mbid"], SB19["mbid"]}
    assert stats["removed"] == 1


# ── 6. Popularity drift alone is NOT an MB change ────────────────────

def test_popularity_rank_drift_is_not_a_change():
    prev = [BEATLES]
    new = _mb_only(BEATLES)
    new["listener_popularity"] = 0.501     # only the derived rank moved
    merged, stats = M.merge_layers([new], prev)

    assert stats["mb_unchanged"] == 1
    assert stats["mb_changed"] == 0
    # Hash ignores popularity but reflects a real tag change.
    assert M.mb_content_hash(prev[0]) == M.mb_content_hash(new)
    new["tags"] = new["tags"] + ["new-tag"]
    assert M.mb_content_hash(prev[0]) != M.mb_content_hash(new)


# ── 7. Seed-checkpoint contains only Last.fm-carrying rows ───────────

def test_seed_checkpoint_selection(tmp_path):
    prev = [BEATLES, METALLICA]            # both enriched
    new_mb = [_mb_only(BEATLES), _mb_only(METALLICA), _mb_only(KISS)]  # +KISS new
    merged, _ = M.merge_layers(new_mb, prev)
    seeded = [r for r in merged if M._pick(r, M.LASTFM_FIELDS)]

    seeded_ids = {r["mbid"] for r in seeded}
    assert seeded_ids == {BEATLES["mbid"], METALLICA["mbid"]}  # KISS excluded
    # Seeded rows carry the *refreshed* MB fields, not stale ones.
    beatles_seed = next(r for r in seeded if r["mbid"] == BEATLES["mbid"])
    assert beatles_seed["name"] == "The Beatles"
    assert "lastfm_tags" in beatles_seed


# ── 8. First-ever build (no previous corpus) ─────────────────────────

def test_first_build_everything_needs_lastfm():
    new_mb = [_mb_only(BEATLES), _mb_only(KISS)]
    merged, stats = M.merge_layers(new_mb, prev_rows=None)
    assert stats["added"] == 2
    assert set(stats["needs_lastfm"]) == {BEATLES["mbid"], KISS["mbid"]}
    assert stats["lastfm_carried"] == 0


# ── 9. CLI round-trip + seed-checkpoint file ─────────────────────────

def test_cli_round_trip(tmp_path):
    prev_path = tmp_path / "previous.jsonl.gz"
    new_path = tmp_path / "new-mb.jsonl"
    out_path = tmp_path / "merged.jsonl.gz"
    seed_path = tmp_path / "seed.jsonl"
    ai_path = tmp_path / "ai_overlay.json"

    with gzip.open(prev_path, "wt", encoding="utf-8") as fh:
        for r in (BEATLES, METALLICA):
            fh.write(json.dumps(r) + "\n")
    # Fresh MB build: Beatles tags changed, Metallica unchanged, KISS new.
    beatles_new = _mb_only(BEATLES); beatles_new["tags"] = ["rock", "baroque pop"]
    with open(new_path, "w", encoding="utf-8") as fh:
        for r in (beatles_new, _mb_only(METALLICA), _mb_only(KISS)):
            fh.write(json.dumps(r) + "\n")
    # AI overlay in the enrichment-probe {entries: {...}} shape.
    ai_path.write_text(json.dumps({
        "schema_version": 1,
        "entries": {BEATLES["mbid"]: {"ai_tags": ["british invasion"]}},
    }), encoding="utf-8")

    rc = M.main(["--new-mb", str(new_path), "--previous", str(prev_path),
                 "--ai-overlay", str(ai_path),
                 "--out", str(out_path), "--seed-checkpoint", str(seed_path)])
    assert rc == 0

    with gzip.open(out_path, "rt", encoding="utf-8") as fh:
        merged = [json.loads(line) for line in fh if line.strip()]
    by_mbid = {r["mbid"]: r for r in merged}
    assert by_mbid[BEATLES["mbid"]]["tags"] == ["rock", "baroque pop"]   # MB fresh
    assert by_mbid[BEATLES["mbid"]]["lastfm_listeners"] == 6537415        # LFM carried
    assert by_mbid[BEATLES["mbid"]]["ai_tags"] == ["british invasion"]    # AI applied

    with open(seed_path, encoding="utf-8") as fh:
        seeded = [json.loads(line) for line in fh if line.strip()]
    assert {r["mbid"] for r in seeded} == {BEATLES["mbid"], METALLICA["mbid"]}


# ── 10. Integration against the real corpus (skipped if absent) ──────

@pytest.mark.skipif(not REAL_CORPUS.exists(),
                    reason="production corpus not present on this machine")
def test_real_corpus_rows_merge_and_layers_survive():
    # Pull a handful of genuinely enriched rows straight from the corpus.
    real_enriched: list[dict] = []
    with gzip.open(REAL_CORPUS, "rt", encoding="utf-8") as fh:
        for line in itertools.islice(fh, 0, 6000):
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            if a.get("lastfm_tags") and a.get("mbid"):
                real_enriched.append(a)
            if len(real_enriched) >= 5:
                break
    assert real_enriched, "expected some Last.fm-enriched rows in the real corpus"

    # Bake an AI layer on top of the real rows, then simulate a brutal
    # MB rebuild and confirm both Last.fm + AI survive by mbid.
    prev = [dict(r, ai_tags=[f"ai-{i}"]) for i, r in enumerate(real_enriched)]
    new_mb = []
    for r in real_enriched:
        m = _mb_only(r)
        m["tags"] = (m.get("tags") or [])[:1] + ["dummy-rebuild-tag"]
        new_mb.append(m)

    merged, stats = M.merge_layers(new_mb, prev)
    assert stats["removed"] == 0
    assert len(merged) == len(real_enriched)
    for i, row in enumerate(merged):
        src = real_enriched[i]
        assert row["tags"][-1] == "dummy-rebuild-tag"          # MB rebuilt
        assert row["lastfm_tags"] == src["lastfm_tags"]        # Last.fm survived
        assert row["ai_tags"] == [f"ai-{i}"]                   # AI survived
    assert stats["needs_lastfm"] == []                          # all carried
