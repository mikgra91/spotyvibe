"""Build a top-tracks overlay for the canonical evaluation seed.

Validation step (2026-04-27) for the track-grounding fix. Runs Stage 1
retrieval against the user's real corpus using a profile derived from
``evaluation/scenario.SEED_SECTIONS``, then fetches up to 5 top tracks
per surfaced artist via Spotify's ``/v1/artists/{id}/top-tracks``.
Writes the result as ``top_tracks_overlay.json`` next to the corpus
file, where the ``RagCorpus.load()`` auto-detect path picks it up.

This is a one-shot script for the validation phase. Once the diagnosis
is confirmed, the same logic moves into the real corpus enrichment
pipeline (``build-tools/rag/spotify_enrichment/``) and the overlay file
becomes redundant.

Usage:
    python build-tools/rag/build_top_tracks_overlay.py [--target-size N] [--max-tracks K]

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
from evaluation.scenario import SEED_SECTIONS, SCENARIOS  # noqa: E402

logger = logging.getLogger("build_top_tracks_overlay")


def _split_section(value: str) -> list[str]:
    """Split a SEED_SECTIONS prose string into a list of trait phrases."""
    if not value:
        return []
    parts = [p.strip() for p in value.split(";")]
    return [p for p in parts if p]


def _build_seed_profile(seed_sections: dict | None = None) -> dict:
    """Construct the minimal profile shape that retrieve_candidates expects.

    When *seed_sections* is None, defaults to the canonical scenario's
    seed (back-compat with the single-scenario rebuild path). Passing a
    specific scenario's ``seed_sections`` lets the multi-scenario
    overlay build prime L0 across every scenario the eval harness can
    target.
    """
    sec = seed_sections if seed_sections is not None else SEED_SECTIONS
    return {
        "preferences": {
            "core_description": sec.get("core_description", ""),
            "must_have": _split_section(sec.get("must_have", "")),
            "soft_preferences": _split_section(sec.get("soft_preferences", "")),
            "avoid": _split_section(sec.get("avoid", "")),
        },
        "artists": {"confirmed": [], "rejected": [], "moderate": []},
        "history": {"suggested_artists": [], "suggested_tracks": []},
        "feedback": {"liked_tracks": [], "disliked_tracks": []},
        "meta": {},
    }


def _union_candidates_across_scenarios(corpus, scenario_names: list[str],
                                        target_size: int) -> list:
    """For each named scenario, run Stage 1 retrieval and union the
    candidate sets (deduped by mbid, ordered by first appearance).
    """
    seen_mbids: set[str] = set()
    union: list = []
    for scn_name in scenario_names:
        scn = SCENARIOS.get(scn_name)
        if scn is None:
            logger.warning("Skipping unknown scenario: %s", scn_name)
            continue
        profile = _build_seed_profile(scn.seed_sections)
        cands = retrieve_candidates(
            corpus, profile,
            deny_keys=set(),
            target_size=target_size,
            popularity_penalty=0.4,
        )
        new = 0
        for a in cands:
            if a.mbid and a.mbid not in seen_mbids:
                seen_mbids.add(a.mbid)
                union.append(a)
                new += 1
        logger.info("  scenario=%s — %d candidates (%d new in union, %d total)",
                    scn_name, len(cands), new, len(union))
    return union


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
                        help="Sleep between Spotify calls (ms). 4.7 req/s = 210 ms. "
                             "Multi-scenario runs should use --throttle-ms 2000+ "
                             "per S.6 #4 to stay well under Spotify's rolling "
                             "rate-limit ceiling.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the overlay in memory; print stats; do not write the file.")
    parser.add_argument("--release-lock", action="store_true",
                        help="Force-release a stale run lock left behind by a "
                             "hard-killed previous run, then exit.")
    parser.add_argument("--scenarios", default="",
                        help="S.6 #4: comma-separated scenario names OR 'all' to "
                             "iterate every scenario in SCENARIOS, union the "
                             "retrieval pools, and build one combined overlay. "
                             "Default empty = legacy single-scenario behaviour.")
    parser.add_argument("--top-by-popularity", type=int, default=0,
                        help="2026-05-15: bypass scenario-based retrieval and "
                             "process the top-N artists from the corpus sorted by "
                             "listener_popularity descending. Use this for broad "
                             "production-overlay coverage (any future user profile). "
                             "0 = disabled (default).")
    parser.add_argument("--resume", action="store_true",
                        help="S.6 #4: read the existing overlay file and skip "
                             "every artist already present. Lets a multi-session "
                             "build pick up where a 429-kill left off.")
    parser.add_argument("--checkpoint-every", type=int, default=25,
                        help="S.6 #4: flush the overlay to disk after every N "
                             "successful fetches so a 429-kill never loses more "
                             "than N artists of work. Default 25.")
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

    # ── Candidate set ────────────────────────────────────────────
    if args.top_by_popularity > 0:
        # 2026-05-15: broad-coverage mode — feed the top-N most-popular
        # artists from the corpus directly into the fetcher. No
        # scenario-bound retrieval; cover everything a real user profile
        # might surface.
        all_rows = sorted(
            corpus.artists,
            key=lambda a: float(getattr(a, "listener_popularity", 0.0) or 0.0),
            reverse=True,
        )
        candidates = all_rows[: args.top_by_popularity]
        logger.info("Top-by-popularity mode — taking top %d / %d corpus artists by listener_popularity.",
                    len(candidates), len(corpus.artists))
    elif args.scenarios.strip():
        if args.scenarios.strip().lower() == "all":
            scn_names = sorted(SCENARIOS.keys())
        else:
            scn_names = [s.strip() for s in args.scenarios.split(",") if s.strip()]
        logger.info("Multi-scenario mode — unioning candidates across %d scenarios: %s",
                    len(scn_names), ", ".join(scn_names))
        candidates = _union_candidates_across_scenarios(
            corpus, scn_names, args.target_size,
        )
    else:
        profile = _build_seed_profile()
        logger.info("Running Stage 1 retrieve_candidates (target_size=%d)…",
                    args.target_size)
        candidates = retrieve_candidates(
            corpus, profile,
            deny_keys=set(),
            target_size=args.target_size,
            popularity_penalty=0.4,
        )
    logger.info("Final candidate set: %d artists (%d with spotify_id, %d without).",
                len(candidates),
                sum(1 for a in candidates if a.spotify_id),
                sum(1 for a in candidates if not a.spotify_id))

    out_path = rag_dir / "top_tracks_overlay.json"

    # S.6 #4: resume from an existing overlay if present.
    overlay: dict[str, list[str]] = {}
    if args.resume and out_path.exists():
        try:
            overlay = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(overlay, dict):
                logger.warning("Existing overlay at %s is not a dict — starting fresh.",
                                out_path)
                overlay = {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read existing overlay (%s) — starting fresh.", exc)
            overlay = {}
        before = len(candidates)
        candidates = [a for a in candidates if a.mbid and a.mbid not in overlay]
        logger.info("--resume — skipping %d/%d already-fetched artists; %d remaining.",
                    before - len(candidates), before, len(candidates))

    def _checkpoint(reason: str) -> None:
        if args.dry_run:
            return
        try:
            out_path.write_text(
                json.dumps(overlay, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("  ✓ checkpoint (%s): %d entries → %s",
                        reason, len(overlay), out_path.name)
        except OSError as exc:
            logger.error("Checkpoint write failed: %s", exc)

    sp = get_spotify_client()
    n_fetched = 0
    n_empty = 0
    _RETRY_AFTER_ABORT_SEC = 3600  # S.6 #4 — abort on Retry-After > 1 h
    # Endpoint choice (2026-04-27): /v1/artists/{id}/top-tracks returns
    # 403 Forbidden for apps without Extended Quota Mode (the default
    # for newly-created Development Mode apps post-Nov-2024). The
    # `search?type=track&q=artist:"NAME"` endpoint is unrestricted and
    # returns relevance-ranked tracks — for an artist-only query that
    # is effectively the artist's most-played catalogue, which is what
    # we want for the `known:` grounding block. One call per artist
    # (vs. two for the resolve→top-tracks path), so it's also faster.
    from spotipy.exceptions import SpotifyException
    aborted = False
    for i, a in enumerate(candidates, 1):
        try:
            tracks = _search_top_tracks_by_name(sp, a.name, args.max_tracks)
        except SpotifyException as exc:
            # S.6 #4: clean abort on Retry-After > 1 h — checkpoint first.
            if exc.http_status == 429:
                try:
                    retry_after = int(exc.headers.get("Retry-After", "0"))
                except (TypeError, ValueError):
                    retry_after = 0
                if retry_after > _RETRY_AFTER_ABORT_SEC:
                    logger.error(
                        "Spotify Retry-After=%ds exceeds 1 h ceiling — "
                        "checkpointing and aborting. Resume with: "
                        "python build-tools/rag/build_top_tracks_overlay.py "
                        "--resume --scenarios %s --throttle-ms %d",
                        retry_after,
                        args.scenarios or "''",
                        args.throttle_ms,
                    )
                    _checkpoint("retry-after abort")
                    aborted = True
                    break
                # Smaller backoff — log and keep going.
                logger.warning("Spotify 429 — sleeping %ds before retry", retry_after or 60)
                time.sleep(max(retry_after, 60))
                continue
            raise
        if tracks:
            overlay[a.mbid] = tracks
            n_fetched += 1
        else:
            n_empty += 1
        if i % 10 == 0:
            logger.info("  progress: %d/%d (overlay size=%d)",
                        i, len(candidates), len(overlay))
        if n_fetched > 0 and (n_fetched % args.checkpoint_every == 0):
            _checkpoint(f"every-{args.checkpoint_every}")
        time.sleep(args.throttle_ms / 1000.0)

    logger.info(
        "Built overlay: %d artists with tracks, %d empty results%s.",
        n_fetched, n_empty, " (ABORTED)" if aborted else "",
    )
    if aborted:
        return 5
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






