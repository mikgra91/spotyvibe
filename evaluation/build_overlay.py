"""Build a minimal top_tracks_overlay.json from yesterday's eval traces.

Reads every Stage-1 candidate list from a set of trace files, unions by mbid,
calls Spotify search per artist to get top track names, and writes the result
to ``%LOCALAPPDATA%/spotyvibe/rag_corpus/top_tracks_overlay.json`` keyed by mbid.

Diagnostic: 2026-05-15 — RAG corpus shipped without top_tracks; Stage 3 has no
anchors → DS / Llama / mini all under-fill under verify=spotify because they
correctly refuse to confabulate. This builds a small per-scenario overlay so we
can verify that populating top_tracks lifts the under-fill rate. If yes,
upstream corpus-creation pipeline needs the same enrichment for production.

Usage:
    python -m evaluation.build_overlay [trace_dir ...]

If no trace_dir args are given, defaults to yesterday's DS run dirs that
hit the under-fill (default + niche + post_FB scenarios).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = Path(os.environ["LOCALAPPDATA"]) / "spotyvibe"
CACHE_FILE = APP_DIR / ".spotify-cache"
OVERLAY_OUT = APP_DIR / "rag_corpus" / "top_tracks_overlay.json"
SETTINGS_INI = REPO_ROOT / "evaluation" / "settings.ini"

DEFAULT_TRACE_DIRS = [
    REPO_ROOT / "evaluation" / "results" / "20260514-154934",  # DS lean ON, all 3 scenarios
    REPO_ROOT / "evaluation" / "results" / "20260514-193832",  # DS lean OFF, default
]

# Spotify search: max 10 results, request 5 to keep prompts lean.
TOP_N_PER_ARTIST = 5
SEARCH_LIMIT = 5
# Polite throttle between artist searches to stay clear of the rate limit.
THROTTLE_S = 0.4


def _load_spotipy_credentials() -> tuple[str, str]:
    """Pull Spotify client id+secret from evaluation/settings.ini (gitignored)."""
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(SETTINGS_INI)
    cid = cfg.get("spotify", "client_id").strip()
    csec = cfg.get("spotify", "client_secret").strip()
    return cid, csec


def _gather_candidates(trace_dirs: list[Path]) -> dict[str, str]:
    """Union (mbid → name) across every Stage-1 candidate list found under trace_dirs."""
    by_mbid: dict[str, str] = {}
    n_files = 0
    for d in trace_dirs:
        for trace in d.rglob("trace_A.json"):
            n_files += 1
            try:
                t = json.loads(trace.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidates = t.get("stages", {}).get("stage1_candidates", [])
            for c in candidates:
                mbid = c.get("mbid")
                name = c.get("name")
                if mbid and name:
                    by_mbid.setdefault(mbid, name)
        for trace in d.rglob("trace_B.json"):
            try:
                t = json.loads(trace.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidates = t.get("stages", {}).get("stage1_candidates", [])
            for c in candidates:
                mbid = c.get("mbid")
                name = c.get("name")
                if mbid and name:
                    by_mbid.setdefault(mbid, name)
    print(f"Scanned {n_files} trace files → {len(by_mbid)} unique artists.")
    return by_mbid


def _fetch_top_tracks(sp: spotipy.Spotify, artist_name: str) -> list[str]:
    """Search Spotify for tracks by exact-artist string, return up to TOP_N_PER_ARTIST titles."""
    # Quote the artist name so Spotify treats it as a phrase match.
    q = f'artist:"{artist_name}"'
    try:
        resp = sp.search(q=q, type="track", limit=SEARCH_LIMIT, market="from_token")
    except spotipy.exceptions.SpotifyException as exc:
        print(f"  ! Spotify {exc.http_status} on '{artist_name}': {exc.msg}")
        return []
    except Exception as exc:
        print(f"  ! search failed for '{artist_name}': {exc}")
        return []
    items = (resp or {}).get("tracks", {}).get("items", []) or []
    titles: list[str] = []
    seen: set[str] = set()
    for it in items:
        title = (it or {}).get("name", "").strip()
        if not title:
            continue
        # Filter the artist's-name-as-title bug + dup-strip
        if title.lower() == artist_name.lower():
            continue
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        titles.append(title)
        if len(titles) >= TOP_N_PER_ARTIST:
            break
    return titles


def main(argv: list[str]) -> int:
    trace_dirs = [Path(a) for a in argv[1:]] or DEFAULT_TRACE_DIRS
    trace_dirs = [d for d in trace_dirs if d.exists()]
    if not trace_dirs:
        print("No trace directories found. Pass paths as args, or run yesterday's DS evals first.")
        return 2

    by_mbid = _gather_candidates(trace_dirs)
    if not by_mbid:
        print("No candidates extracted from traces — check trace_A.json shape.")
        return 3

    cid, csec = _load_spotipy_credentials()
    cache_handler = CacheFileHandler(cache_path=str(CACHE_FILE))
    oauth = SpotifyOAuth(
        client_id=cid,
        client_secret=csec,
        redirect_uri="http://127.0.0.1:5000/callback",
        scope="playlist-modify-private playlist-read-private user-read-private streaming",
        cache_handler=cache_handler,
        open_browser=False,
    )
    sp = spotipy.Spotify(auth_manager=oauth)

    # Preserve existing overlay entries — only add new ones (so re-runs are
    # idempotent and we accumulate coverage).
    existing: dict[str, list[str]] = {}
    if OVERLAY_OUT.exists():
        try:
            existing = json.loads(OVERLAY_OUT.read_text(encoding="utf-8"))
            print(f"Loaded existing overlay: {len(existing)} entries.")
        except (OSError, json.JSONDecodeError):
            print("Existing overlay unreadable — starting from empty.")

    OVERLAY_OUT.parent.mkdir(parents=True, exist_ok=True)

    n_total = len(by_mbid)
    n_done = 0
    n_with_tracks = 0
    t0 = time.monotonic()
    for mbid, name in by_mbid.items():
        n_done += 1
        if mbid in existing and existing[mbid]:
            # Already populated — skip the Spotify call.
            n_with_tracks += 1
            continue
        tracks = _fetch_top_tracks(sp, name)
        if tracks:
            existing[mbid] = tracks
            n_with_tracks += 1
        # Write incrementally every 25 entries so a mid-run crash doesn't lose work.
        if n_done % 25 == 0:
            OVERLAY_OUT.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            elapsed = time.monotonic() - t0
            print(f"  [{n_done}/{n_total}] populated={n_with_tracks} ({elapsed:.0f}s elapsed)")
        time.sleep(THROTTLE_S)

    OVERLAY_OUT.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    elapsed = time.monotonic() - t0
    print(f"\nDone. Wrote {len(existing)} entries to {OVERLAY_OUT} ({n_with_tracks} non-empty, {elapsed:.0f}s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
