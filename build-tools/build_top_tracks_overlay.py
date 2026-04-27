"""Build a top-tracks overlay for the canonical evaluation seed.

Validation step (2026-04-27) for the track-grounding fix. Runs Stage 1
retrieval against the user's real corpus using a profile derived from
``evaluation/scenario.SEED_SECTIONS``, then fetches up to 5 top tracks
per surfaced artist via Spotify's ``/v1/artists/{id}/top-tracks``.
Writes the result as ``top_tracks_overlay.json`` next to the corpus
file, where the ``RagCorpus.load()`` auto-detect path picks it up.

This is a one-shot script for the validation phase. Once the diagnosis
is confirmed, the same logic moves into the real corpus enrichment
pipeline (``build-tools/spotify_enrichment/``) and the overlay file
becomes redundant.

Usage:
    python build-tools/build_top_tracks_overlay.py [--target-size N] [--max-tracks K]

The user's existing Spotify OAuth cache is used (read from the real
app dir via ``config.load_config()``); no new auth flow.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

# Imports must follow path setup.
import config  # noqa: E402
from core.src.rag.corpus import RagCorpus  # noqa: E402
from core.src.rag.retrieval import retrieve_candidates  # noqa: E402
from core.src.playlist import get_spotify_client  # noqa: E402
from evaluation.scenario import SEED_SECTIONS  # noqa: E402

logger = logging.getLogger("build_top_tracks_overlay")


def _split_section(value: str) -> list[str]:
    """Split a SEED_SECTIONS prose string into a list of trait phrases."""
    if not value:
        return []
    parts = [p.strip() for p in value.split(";")]
    return [p for p in parts if p]


def _build_seed_profile() -> dict:
    """Construct the minimal profile shape that retrieve_candidates expects.

    Mirrors the canonical eval seed (``evaluation/scenario.SEED_SECTIONS``)
    so the overlay we build is exactly the set of artists the harness
    will retrieve.
    """
    return {
        "preferences": {
            "core_description": SEED_SECTIONS.get("core_description", ""),
            "must_have": _split_section(SEED_SECTIONS.get("must_have", "")),
            "soft_preferences": _split_section(SEED_SECTIONS.get("soft_preferences", "")),
            "avoid": _split_section(SEED_SECTIONS.get("avoid", "")),
        },
        "artists": {"confirmed": [], "rejected": [], "moderate": []},
        "history": {"suggested_artists": [], "suggested_tracks": []},
        "feedback": {"liked_tracks": [], "disliked_tracks": []},
        "meta": {},
    }


def _fetch_top_tracks(sp, spotify_id: str, max_tracks: int) -> list[str]:
    """DEPRECATED — kept for reference only.

    The ``/v1/artists/{id}/top-tracks`` endpoint returns HTTP 403 for
    apps that do not have Extended Quota Mode (which newly-created
    Development Mode apps never have by default, post-Nov-2024 Service
    Terms update). Use :func:`_search_top_tracks_by_name` instead — it
    works on every app tier and only costs one API call per artist
    instead of two (no separate id-resolution step).
    """
    try:
        resp = sp.artist_top_tracks(spotify_id, country="from_token")
    except Exception as exc:  # broad — any Spotify or network error
        logger.warning("artist_top_tracks(%s) failed: %s", spotify_id, exc)
        return []
    out: list[str] = []
    for tr in (resp.get("tracks") or [])[:max_tracks]:
        name = (tr.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _search_top_tracks_by_name(sp, name: str, max_tracks: int) -> list[str]:
    """Return up to *max_tracks* relevance-ranked tracks for *name*.

    Uses Spotify's ``/v1/search?type=track&q=artist:"NAME"`` endpoint,
    which is available on every app tier (unlike ``artist_top_tracks``
    which requires Extended Quota Mode post-Nov-2024). Filters results
    to tracks where one of the primary artists actually matches the
    requested name, so search-engine fuzziness can't poison the
    overlay with wrong-artist titles.

    Returns ``[]`` on any error so a single missing artist never
    breaks the whole overlay build.
    """
    if not name or not name.strip():
        return []
    target = _normalise_name(name)
    try:
        # limit=10 gives us headroom to discard mis-attributed hits and
        # still return up to max_tracks (typically 5).
        resp = sp.search(
            q=f'artist:"{name}"', type="track",
            limit=max(10, max_tracks * 2), market="from_token",
        )
    except Exception as exc:  # broad — any Spotify or network error
        logger.warning("search(track artist=%r) failed: %s", name, exc)
        return []
    items = ((resp or {}).get("tracks") or {}).get("items") or []
    out: list[str] = []
    seen: set[str] = set()
    for tr in items:
        if len(out) >= max_tracks:
            break
        # Require an exact normalised-name match on at least one
        # credited artist. Otherwise search may return e.g. a feature
        # by an unrelated artist that mentions the target name.
        artists = tr.get("artists") or []
        if not any(_normalise_name(a.get("name", "")) == target for a in artists):
            continue
        title = (tr.get("name") or "").strip()
        if not title:
            continue
        # Dedupe — search often returns multiple regional / remastered
        # editions of the same song. Compare on lowercase to keep the
        # overlay tight (5 distinct titles, not 5 versions of one).
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


def _normalise_name(name: str) -> str:
    """Same shape as core.src.rag.corpus.normalise_name — used to verify
    that a Spotify search hit really is the artist we asked for."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _resolve_spotify_id(sp, name: str) -> str | None:
    """Best-effort resolution of an artist name to a Spotify artist id.

    Conservative: only accepts the top search hit when its normalised
    name matches the input exactly. Anything else returns ``None`` so
    we never grab top tracks from a mis-matched artist (which would
    actively poison the overlay with wrong-artist titles).
    """
    if not name or not name.strip():
        return None
    target = _normalise_name(name)
    try:
        resp = sp.search(q=f'artist:"{name}"', type="artist", limit=3)
    except Exception as exc:
        logger.debug("search artist=%r failed: %s", name, exc)
        return None
    items = ((resp or {}).get("artists") or {}).get("items") or []
    for it in items:
        if _normalise_name(it.get("name", "")) == target:
            return it.get("id")
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, default=50,
                        help="Stage 1 candidate pool size (default 50, matches RETRIEVE_CANDIDATES_SIZE).")
    parser.add_argument("--max-tracks", type=int, default=5,
                        help="Top tracks per artist to write into the overlay.")
    parser.add_argument("--throttle-ms", type=int, default=210,
                        help="Sleep between Spotify calls (ms). 4.7 req/s = 210 ms.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the overlay in memory; print stats; do not write the file.")
    parser.add_argument("--release-lock", action="store_true",
                        help="Force-release a stale run lock left behind by a "
                             "hard-killed previous run, then exit.")
    args = parser.parse_args()

    # Same lock kind as the eval harness: both write to the user's
    # Spotify quota, and concurrent runs is exactly what triggered the
    # 2026-04-27 quota disaster (3 orphan instances → HTTP 429).
    from evaluation._runlock import (
        LockHeldError,
        acquire as _acquire_lock,
        release_stale_lock,
    )
    lock_path = REPO_ROOT / "evaluation" / ".run.lock"
    if args.release_lock:
        removed = release_stale_lock(lock_path)
        print(f"Run lock {'removed' if removed else 'not present'}: {lock_path}")
        return 0
    try:
        _acquire_lock(lock_path, kind="overlay-build")
    except LockHeldError as exc:
        print(f"\n  ❌ {exc}\n", file=sys.stderr)
        return 4

    config.load_config()

    # Resolve the real (non-sandbox) corpus directory.
    rag_dir = config._APP_DIR / "rag_corpus"  # type: ignore[attr-defined]
    corpus_path = rag_dir / "artists.jsonl.gz"
    if not corpus_path.exists():
        logger.error("RAG corpus not found at %s — refresh the corpus first.", corpus_path)
        return 2

    logger.info("Loading corpus from %s", corpus_path)
    corpus = RagCorpus.load(corpus_path)

    profile = _build_seed_profile()
    logger.info("Running Stage 1 retrieve_candidates (target_size=%d)…", args.target_size)
    candidates = retrieve_candidates(
        corpus, profile,
        deny_keys=set(),
        target_size=args.target_size,
        popularity_penalty=0.4,
    )
    logger.info("Retrieved %d candidates (%d with spotify_id, %d without).",
                len(candidates),
                sum(1 for a in candidates if a.spotify_id),
                sum(1 for a in candidates if not a.spotify_id))

    sp = get_spotify_client()
    overlay: dict[str, list[str]] = {}
    n_fetched = 0
    n_empty = 0
    # Endpoint choice (2026-04-27): /v1/artists/{id}/top-tracks returns
    # 403 Forbidden for apps without Extended Quota Mode (the default
    # for newly-created Development Mode apps post-Nov-2024). The
    # `search?type=track&q=artist:"NAME"` endpoint is unrestricted and
    # returns relevance-ranked tracks — for an artist-only query that
    # is effectively the artist's most-played catalogue, which is what
    # we want for the `known:` grounding block. One call per artist
    # (vs. two for the resolve→top-tracks path), so it's also faster.
    for i, a in enumerate(candidates, 1):
        tracks = _search_top_tracks_by_name(sp, a.name, args.max_tracks)
        if tracks:
            overlay[a.mbid] = tracks
            n_fetched += 1
        else:
            n_empty += 1
        if i % 10 == 0:
            logger.info("  progress: %d/%d (overlay size=%d)", i, len(candidates), len(overlay))
        time.sleep(args.throttle_ms / 1000.0)

    out_path = rag_dir / "top_tracks_overlay.json"
    logger.info(
        "Built overlay: %d artists with tracks, %d empty results.",
        n_fetched, n_empty,
    )
    if args.dry_run:
        logger.info("--dry-run: NOT writing %s", out_path)
        # Print first 5 entries for sanity check.
        for k, v in list(overlay.items())[:5]:
            row = corpus.artists[corpus.by_mbid[k]] if k in corpus.by_mbid else None
            name = row.name if row else "?"
            logger.info("  %s (%s) → %s", name, k, v)
        return 0

    out_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote overlay to %s (%d entries)", out_path, len(overlay))
    return 0


if __name__ == "__main__":
    sys.exit(main())






