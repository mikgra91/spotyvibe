"""Spotify playlist management and OAuth authentication.

Technologies & patterns used:
- **spotipy** (v2.23+): Python wrapper for the Spotify Web API. Handles
  OAuth 2.0 token management, automatic token refresh, and provides
  Pythonic methods for every Spotify REST endpoint.
- **SpotifyOAuth (Authorization Code Flow)**: The OAuth 2.0 flow that
  requires user login via browser redirect. This grants access to
  private user data (playlists, profile) as opposed to the simpler
  Client Credentials flow (which only accesses public data).
- **Token caching**: Spotipy stores the OAuth token in a local file
  (`.spotify-cache` in AppData). On subsequent runs, the cached token
  is reused and automatically refreshed when expired, avoiding repeated
  browser-based logins.
- **concurrent.futures.ThreadPoolExecutor**: Used for parallel Spotify
  search requests. The Spotify search API is IO-bound (network calls),
  so threading achieves near-linear speedup. Each thread gets its own
  `spotipy.Spotify` client to avoid sharing non-thread-safe HTTP
  sessions.
- **current_user_* methods**: Modern spotipy methods that use `/me/`
  endpoints instead of the deprecated `/users/{user_id}/` variants.
  This avoids the need to look up the user's Spotify ID.
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
# concurrent.futures provides a high-level interface for asynchronous
# execution. ThreadPoolExecutor is used here (not ProcessPoolExecutor)
# because the workload is I/O-bound (HTTP requests to Spotify API),
# not CPU-bound. Threads share memory and have lower overhead than
# processes for this use case.
from concurrent.futures import ThreadPoolExecutor, as_completed

# requests is spotipy's HTTP transport layer and a transitive dependency.
# We use it here to create a shared Session with connection pooling for
# parallel Spotify searches, avoiding the cost of a fresh TLS handshake
# per thread.
import requests
from requests.adapters import HTTPAdapter

# spotipy is a lightweight Python wrapper for all Spotify Web API
# endpoints. It handles OAuth token lifecycle, request serialization,
# pagination, and error mapping.
import spotipy
from spotipy.exceptions import SpotifyException
# SpotifyOAuth implements the Authorization Code Flow — the user
# authorises via browser, the app receives a code, exchanges it for
# access + refresh tokens, and caches them locally.
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from config import CACHE_FILE
from .errors import TranslatableError
from .utils import app_log

logger = logging.getLogger(__name__)

_legacy_track_key_warned = False


# L2 (2026-05-06): per-run search-result cache. ``None`` when caching
# is off; ``{}`` when bracketed by ``start_run_search_cache()`` /
# ``end_run_search_cache()``. The cache is single-flight, matching the
# rest of the suggestion pipeline (one playlist generation at a time).
#
# Key shape: ``"<artist_lower>|<track_lower>"`` (same normalisation as
# the in-call dedup at line 521-525, so the two never disagree).
# Value shape: ``("found", enriched_dict)`` or ``("not_found", label)``
# — exactly what ``search_one`` would have returned, so a cache hit
# slots into the result aggregation without any other branch change.
#
# Within a single ``search_tracks()`` call the existing dedup already
# guards against double-search. This cache exists for the cross-batch
# case: in a multi-batch generation run the LLM occasionally re-proposes
# an (artist, track) pair from an earlier batch (deny-list slips), and
# without this cache each repeat costs another Spotify roundtrip.
_RUN_SEARCH_CACHE: dict | None = None


def start_run_search_cache() -> None:
    """Open the per-run search-result cache.

    Call once at the start of a generation run; subsequent
    ``search_tracks()`` invocations will skip Spotify for any
    ``(artist, track)`` pair already verified in this run. Idempotent —
    re-opening clears any leftover state from a prior run.
    """
    global _RUN_SEARCH_CACHE
    _RUN_SEARCH_CACHE = {}


def end_run_search_cache() -> None:
    """Close the per-run search-result cache.

    Call from a ``finally`` so the cache always tears down even when
    the generation run errors out — leaving it on between runs would
    return stale ``not_found`` labels for tracks the LLM tries again
    later.
    """
    global _RUN_SEARCH_CACHE
    _RUN_SEARCH_CACHE = None


def _search_cache_key(artist: str, track: str) -> str:
    return f"{(artist or '').lower().strip()}|{(track or '').lower().strip()}"


def _warn_legacy_track_key_once():
    """Log once per process when Spotify's playlist item still uses the
    pre-Feb-2026 'track' key instead of the current 'item' key.
    A regression here would otherwise be silent — the read-side fallback
    keeps things working but should not stay invisible.
    """
    global _legacy_track_key_warned
    if not _legacy_track_key_warned:
        _legacy_track_key_warned = True
        logger.warning(
            "Spotify playlist item missing 'item' key — falling back to legacy 'track' key. "
            "API may have regressed; verify against current Spotify docs."
        )

# Name used for the managed playlist. If a playlist with this name
# already exists, new tracks are added to it (idempotent). This avoids
# creating duplicate playlists on every generation.
PLAYLIST_NAME = "SpotyVibe Playlist"
# Redirect URI must match what is configured in the Spotify Developer
# Dashboard — a local HTTP server callback.
REDIRECT_URI = "http://127.0.0.1:5000/callback"


def _pick_album_cover(images: list) -> str | None:
    """Pick a mid-sized album cover URL.

    Spotify returns images sorted largest-first (typically 640 / 300 / 64).
    We pick the middle entry so it stays crisp at ~140px (preview player)
    while avoiding the giant 640px asset.

    With fewer images returned, the middle index degrades gracefully:
    - 2 images  → index 1 (the smaller one)
    - 1 image   → index 0 (the only one available — *not* a "smallest"
                  fallback; whatever Spotify returned is what we use)
    - 0 images  → ``None``
    """
    if not images:
        return None
    return images[len(images) // 2].get("url")


def _sanitize_spotify_search_value(value):
    """Sanitize values used inside Spotify search quotes.

    Spotify search queries often use the syntax: track:"..." artist:"...".
    We want to preserve real artist/track names (including punctuation like
    apostrophes), while preventing malformed queries.

    We therefore:
    - strip ASCII control characters (including newlines, null bytes)
    - remove double-quotes and backslashes (they break quoted syntax)
    - collapse whitespace
    """
    if value is None:
        return ""

    s = str(value)
    s = re.sub(r"[\x00-\x1F\x7F]", " ", s)
    # Remove characters that can break Spotify's quoted query syntax.
    s = s.replace('"', " ").replace("\\", " ")
    # Also handle common “smart quotes”.
    s = s.replace("“", " ").replace("”", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_track_artist_query(artist, track):
    artist_q = _sanitize_spotify_search_value(artist)
    track_q = _sanitize_spotify_search_value(track)
    return f'track:"{track_q}" artist:"{artist_q}"'





def get_spotify_oauth():
    """Create a SpotifyOAuth instance with the token cache in AppData.

    Configuration choices:
    - Scopes: ``playlist-modify-private`` and ``playlist-read-private`` for
      playlist management; ``user-read-private`` so Spotify can resolve the
      user's country when ``market="from_token"`` is used in search calls.
    - `cache_path`: Token is stored in AppData alongside credentials,
      keeping secrets out of the project directory.
    - `open_browser=False`: The app controls when/how the browser opens
      (via the UI), rather than letting spotipy auto-launch it.
    """
    cache_handler = CacheFileHandler(cache_path=str(CACHE_FILE))
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=REDIRECT_URI,
        scope="playlist-modify-private playlist-read-private user-read-private streaming",
        cache_handler=cache_handler,
        open_browser=False,
    )


def get_spotify_client():
    """Create an authenticated Spotify client using cached OAuth credentials."""
    return spotipy.Spotify(auth_manager=get_spotify_oauth())


# Cache for get_spotify_auth_status() — avoids redundant /v1/me/ calls
# when multiple callers check status within a short window.
_auth_status_cache = {"status": None, "expires": 0.0}
_AUTH_STATUS_TTL = 5  # seconds


def get_spotify_auth_status():
    """Check whether Spotify credentials are configured and authenticated.

    Returns one of: "not_configured", "not_authenticated", "authenticated".

    Results are cached for a few seconds to avoid redundant API calls
    when multiple callers (e.g., the frontend status poll and the
    /api/run guard) check in quick succession.
    """
    now = time.monotonic()
    if _auth_status_cache["status"] and now < _auth_status_cache["expires"]:
        return _auth_status_cache["status"]

    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        _auth_status_cache["status"] = "not_configured"
        _auth_status_cache["expires"] = now + _AUTH_STATUS_TTL
        return "not_configured"

    try:
        oauth = get_spotify_oauth()
        token = oauth.validate_token(oauth.cache_handler.get_cached_token())
        if not token:
            _auth_status_cache["status"] = "not_authenticated"
            _auth_status_cache["expires"] = now + _AUTH_STATUS_TTL
            return "not_authenticated"

        # Validate via auth_manager so expired tokens are auto-refreshed
        sp = spotipy.Spotify(auth_manager=oauth)
        sp.current_user()
        _auth_status_cache["status"] = "authenticated"
        _auth_status_cache["expires"] = now + _AUTH_STATUS_TTL
        return "authenticated"
    except Exception as e:
        logger.warning("Spotify auth check failed: %s", e)
        _auth_status_cache["status"] = "not_authenticated"
        _auth_status_cache["expires"] = now + _AUTH_STATUS_TTL
        return "not_authenticated"


def get_spotify_access_token():
    """Return a valid access token, refreshing via spotipy if expired.

    Used by the frontend Web Playback SDK via /api/spotify/token. The
    token is never embedded in HTML; the SDK fetches it on demand.
    Returns None if the user isn't authenticated.
    """
    try:
        oauth = get_spotify_oauth()
        token_info = oauth.validate_token(oauth.cache_handler.get_cached_token())
        if not token_info:
            return None
        return token_info.get("access_token")
    except Exception as e:
        logger.warning("Spotify token fetch failed: %s", e)
        return None


def get_spotify_session_info():
    """Return session info the frontend needs to pick a playback path.

    Keys: ``is_premium`` (bool), ``product`` (raw Spotify product string
    — "premium" / "free" / "open" / None). Safe to call unauthenticated;
    fields are None in that case.
    """
    info = {"is_premium": False, "product": None}
    try:
        if get_spotify_auth_status() != "authenticated":
            return info
        sp = get_spotify_client()
        me = sp.current_user()
        product = me.get("product") if isinstance(me, dict) else None
        info["product"] = product
        info["is_premium"] = (product == "premium")
    except Exception as e:
        logger.warning("Spotify session info failed: %s", e)
    return info


def disconnect_spotify():
    """Remove the cached Spotify token so the user can re-authenticate.

    This is useful when the token is stale, revoked, or was obtained with
    outdated scopes.
    """
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            logger.info("Spotify token cache removed.")
        return True
    except Exception as e:
        logger.error("Error removing Spotify cache: %s", e)
        return False


def get_spotify_auth_url():
    """Return the Spotify authorization URL the user must visit.

    Clears any stale ``.spotify-cache`` first. A leftover cache from a
    previous OAuth round (e.g. after credentials rotation or a revoked
    token) makes spotipy reuse the old client_id when exchanging the
    callback code, producing ``400 invalid_client`` on every reconnect.
    """
    CACHE_FILE.unlink(missing_ok=True)
    return get_spotify_oauth().get_authorize_url()


def handle_spotify_callback(code):
    """Exchange an authorization code for an access token and cache it."""
    try:
        get_spotify_oauth().get_access_token(code, as_dict=False)
        return True
    except Exception as e:
        logger.error("Spotify callback error: %s", e)
        return False


def find_existing_playlist(sp):
    """Search the current user's playlists for one matching PLAYLIST_NAME."""
    offset = 0
    while True:
        # GET /me/playlists (still available)
        playlists = sp.current_user_playlists(limit=50, offset=offset)
        for pl in playlists["items"]:
            if pl["name"] == PLAYLIST_NAME:
                return pl
        if playlists["next"] is None:
            return None
        offset += 50


def get_existing_track_uris(sp, playlist_id):
    """Load all track URIs already in the playlist to avoid duplicates."""
    existing = set()
    # playlist_items() maps to GET /playlists/{id}/items (the current endpoint
    # after Spotify removed /tracks in February 2026).
    # Feb 2026: each playlist item uses the key "item" instead of "track".
    results = sp.playlist_items(playlist_id, fields="items(item(uri)),next", limit=100)
    while True:
        for entry in results.get("items", []):
            track = entry.get("item")
            if track is None and entry.get("track") is not None:
                _warn_legacy_track_key_once()
                track = entry.get("track")
            if track and track.get("uri"):
                existing.add(track["uri"])
        if results.get("next") is None:
            break
        results = sp.next(results)
    return existing


def remove_from_playlist(artist, track, playlist_id=None, track_id=None):
    """Remove a single track from a Spotify playlist.

    When ``playlist_id`` is given it is used directly (supports custom names,
    preset-renamed playlists, and the Refine flow). Otherwise falls back to
    looking up the default SpotyVibe Playlist by name.

    When ``track_id`` is given the URI is built from it directly. Otherwise
    falls back to a text search over ``artist + track``.

    Returns a dict:  {"removed": True/False, "reason": "..." (on failure)}
    """
    sp = get_spotify_client()

    if playlist_id:
        pid = playlist_id
    else:
        playlist = find_existing_playlist(sp)
        if not playlist:
            return {"removed": False, "reason": "Playlist not found"}
        pid = playlist["id"]

    if track_id:
        uri = f"spotify:track:{track_id}"
    else:
        query = _build_track_artist_query(artist, track)
        res = sp.search(q=query, type="track", limit=1)
        if not res or not res["tracks"]["items"]:
            return {"removed": False, "reason": "Track not found on Spotify"}
        uri = res["tracks"]["items"][0]["uri"]

    existing_uris = get_existing_track_uris(sp, pid)
    if uri not in existing_uris:
        return {"removed": False, "reason": "Track not in playlist"}

    sp.playlist_remove_all_occurrences_of_items(pid, [uri])
    logger.info("Removed from playlist %s: %s - %s", pid, artist, track)

    return {"removed": True}


def remove_all_tracks_by_artist(artist, playlist_id=None):
    """Remove every track whose primary artist matches *artist* from a playlist.

    Used by the "dislike entire band" flow (Item 6, 2026-04). Matches
    artist names case-insensitively after stripping whitespace, against
    *every* artist credit on the track (Spotify exposes a list).

    Returns a dict::

        {"removed": True/False,
         "removed_count": int,
         "removed_tracks": [{"artist": str, "track": str}, ...],
         "reason": str (only when removed=False)}
    """
    sp = get_spotify_client()
    if playlist_id:
        pid = playlist_id
    else:
        playlist = find_existing_playlist(sp)
        if not playlist:
            return {"removed": False, "removed_count": 0,
                    "removed_tracks": [], "reason": "Playlist not found"}
        pid = playlist["id"]

    target = (artist or "").strip().lower()
    if not target:
        return {"removed": False, "removed_count": 0,
                "removed_tracks": [], "reason": "Empty artist name"}

    uris_to_remove: list[str] = []
    removed_tracks: list[dict] = []
    # Feb 2026: Spotify renamed the inner key from "track" to "item".
    # Mirror what get_existing_track_uris does — request "item" by name.
    results = sp.playlist_items(pid, fields="items(item(uri,name,artists(name))),next")
    while results:
        for entry in results.get("items", []):
            track = entry.get("item")
            if track is None and entry.get("track") is not None:
                _warn_legacy_track_key_once()
                track = entry.get("track")
            if not track or not track.get("uri"):
                continue
            artists = [(a.get("name") or "").strip().lower()
                       for a in (track.get("artists") or [])]
            if target in artists:
                uris_to_remove.append(track["uri"])
                removed_tracks.append({
                    "artist": (track.get("artists") or [{}])[0].get("name", artist),
                    "track": track.get("name", ""),
                })
        if results.get("next") is None:
            break
        results = sp.next(results)

    if not uris_to_remove:
        return {"removed": False, "removed_count": 0,
                "removed_tracks": [],
                "reason": "No tracks by this artist in playlist"}

    # Spotify caps removals at 100 URIs per call.
    for i in range(0, len(uris_to_remove), 100):
        sp.playlist_remove_all_occurrences_of_items(pid, uris_to_remove[i:i + 100])

    logger.info("Removed %d tracks by '%s' from playlist %s",
                len(uris_to_remove), artist, pid)
    return {"removed": True, "removed_count": len(uris_to_remove),
            "removed_tracks": removed_tracks}


def _parse_release_year(release_date: str | None) -> int | None:
    """Extract a 4-digit year from a Spotify release_date string.

    Spotify returns dates in 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD' format.
    Returns None if the date is missing or unparseable.
    """
    if not release_date or not isinstance(release_date, str):
        return None
    try:
        year = int(release_date[:4])
        return year if 1900 < year <= 2100 else None
    except (ValueError, IndexError):
        return None


def _enrich_tracks_with_metadata(tracks: list) -> None:
    """Enrich track dicts with release_year from Spotify search data.

    - Parses release_year from each track's release_date (returned by
      Spotify search).
    - Ensures a 'genres' key exists (genres are provided by GPT in the
      suggestion response and already present on the track dict).
    - Mutates track dicts in-place.
    """
    for t in tracks:
        t["release_year"] = _parse_release_year(t.get("release_date"))
        # Genres come from GPT (set in normalize_response).
        # Ensure the key exists for downstream consumers.
        t.setdefault("genres", [])


def _make_pooled_session(pool_size=10):
    """Create a ``requests.Session`` with enlarged connection pool.

    ``urllib3``'s default pool_maxsize is 10, but its pool_connections
    default is only 1 (one host-slot). By mounting an ``HTTPAdapter``
    with ``pool_connections`` and ``pool_maxsize`` both equal to
    *pool_size*, all concurrent threads reuse persistent TCP+TLS
    connections to ``api.spotify.com`` instead of opening a fresh
    TLS handshake per request.

    The ``requests.Session`` object itself is thread-safe for making
    concurrent requests — ``urllib3`` synchronises access to the
    underlying connection pool internally.
    """
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _dedup_tracks_for_search(tracks):
    """Deduplicate `(artist, track)` pairs, lower-cased + stripped.

    Same shape as the L2 cache key (so both stay consistent) and the
    only place this dedup lives — both ``search_tracks`` and
    ``iter_search_tracks`` (L3, 2026-05-06) reuse it.
    """
    seen = set()
    out = []
    for t in tracks:
        key = f'{t["artist"]} - {t["track"]}'.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _do_spotify_search(t, shared_sp):
    """Single-track Spotify search with L2 cache + 429 retry.

    Module-level (not a closure) so both ``search_tracks`` and
    ``iter_search_tracks`` can hand it to a ``ThreadPoolExecutor``.
    Returns the same ``("found", enriched)`` / ``("not_found", label)``
    tuple either generator/wrapper consumes.
    """
    cache_key = _search_cache_key(t["artist"], t["track"])
    if _RUN_SEARCH_CACHE is not None:
        cached = _RUN_SEARCH_CACHE.get(cache_key)
        if cached is not None:
            kind, payload = cached
            if kind == "found":
                return "found", {**t, **payload}
            return "not_found", f"{t['artist']} - {t['track']}"

    query = _build_track_artist_query(t["artist"], t["track"])

    res = None
    for attempt in range(4):
        try:
            res = shared_sp.search(q=query, type="track", limit=1, market="from_token")
            break
        except SpotifyException as e:
            if e.http_status == 429 and attempt < 3:
                retry_after = int(e.headers.get("Retry-After", 1))
                backoff_floor = 2 ** attempt
                time.sleep(min(max(retry_after, backoff_floor), 30))
                continue
            raise

    if res and res["tracks"]["items"]:
        item = res["tracks"]["items"][0]
        uri = item["uri"]
        track_id = uri.split(":")[-1] if uri else None
        images = item.get("album", {}).get("images", [])
        cover_url = _pick_album_cover(images)
        preview_url = item.get("preview_url")
        spotify_url = item.get("external_urls", {}).get("spotify")
        album_url = item.get("album", {}).get("external_urls", {}).get("spotify")
        release_date = item.get("album", {}).get("release_date")
        artists = item.get("artists", [])
        artist_url = artists[0].get("external_urls", {}).get("spotify") if artists else None
        artist_id = artists[0].get("id") if artists else None
        spotify_extras = {
            "uri": uri,
            "track_id": track_id,
            "cover_url": cover_url,
            "preview_url": preview_url,
            "spotify_url": spotify_url,
            "album_url": album_url,
            "release_date": release_date,
            "artist_url": artist_url,
            "artist_id": artist_id,
        }
        enriched = {**t, **spotify_extras}
        if _RUN_SEARCH_CACHE is not None:
            _RUN_SEARCH_CACHE[cache_key] = ("found", spotify_extras)
        return "found", enriched
    if _RUN_SEARCH_CACHE is not None:
        _RUN_SEARCH_CACHE[cache_key] = ("not_found", None)
    return "not_found", f"{t['artist']} - {t['track']}"


def iter_search_tracks(tracks):
    """L3 (2026-05-06) — streaming generator over Spotify track search.

    Yields ``("found", enriched_track)`` or ``("not_found", label)`` as
    each search completes (in completion order, *not* input order; the
    underlying ``ThreadPoolExecutor`` is the same one ``search_tracks``
    uses, so the parallelism profile is identical).

    Why this exists: ``search_tracks`` blocks the SSE generator until
    every track in a batch is verified. For a 10-track batch that's
    2-3 s during which the user sees no progress. Calling
    ``iter_search_tracks`` from the SSE generator and yielding a
    ``track_verified`` event per item gives the user immediate feedback
    on each Spotify match without any other architectural change.

    Each found track has ``release_year`` already populated (parsed
    from ``release_date``) so the consumer doesn't need a second
    enrichment pass — the original ``_enrich_tracks_with_metadata``
    runs once per batch in the wrapper, but per-track in the
    generator.

    Same L2 cache, same 429-retry, same per-track-cache populate as
    ``search_tracks`` — the implementations share ``search_one``.
    """
    unique_tracks = _dedup_tracks_for_search(tracks)
    if not unique_tracks:
        return

    oauth = get_spotify_oauth()
    token_info = oauth.validate_token(oauth.cache_handler.get_cached_token())
    if not token_info:
        logger.error("Spotify token unavailable — cannot search tracks")
        for t in unique_tracks:
            yield "not_found", f"{t['artist']} - {t['track']}"
        return
    access_token = token_info["access_token"]

    pool_size = min(5, len(unique_tracks)) or 1
    shared_session = _make_pooled_session(pool_size)
    shared_sp = spotipy.Spotify(
        auth=access_token,
        requests_session=shared_session,
    )

    def search_one(t):
        return _do_spotify_search(t, shared_sp)

    try:
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = {executor.submit(search_one, t): t for t in unique_tracks}
            for future in as_completed(futures):
                try:
                    result_type, result_data = future.result()
                except Exception as e:
                    t = futures[future]
                    label = f"{t['artist']} - {t['track']}"
                    logger.error("Spotify search error for %s: %s", label, e)
                    app_log(f"Spotify search error for {label}: {e}")
                    yield "not_found", label
                    continue
                if result_type == "found":
                    # Inline the per-track release_year enrichment so a
                    # streaming consumer doesn't need a post-pass. Genres
                    # default already-set by GPT survives untouched.
                    result_data["release_year"] = _parse_release_year(
                        result_data.get("release_date")
                    )
                    result_data.setdefault("genres", [])
                    yield "found", result_data
                else:
                    logger.warning("Not found on Spotify: %s", result_data)
                    app_log(f"Spotify search miss (possible LLM hallucination): {result_data}")
                    yield "not_found", result_data
    finally:
        shared_session.close()


def search_tracks(tracks, on_progress=None):
    """Search Spotify for each track using parallel requests.

    **Concurrency model**: Uses ``ThreadPoolExecutor`` with 10 workers
    sharing a single ``requests.Session`` with a matching connection
    pool. The access token is fetched **once** before the pool starts,
    and each worker creates a lightweight ``spotipy.Spotify`` client
    that reuses the shared session and pre-fetched token. This avoids:

    - N redundant cache-file reads + token validations
    - N fresh TLS handshakes (connections are pooled and reused)

    Why 10 workers? This is a practical sweet spot — enough to saturate
    the network for typical batch sizes (10–30 tracks) without hitting
    Spotify's rate limits. Spotify's API allows ~30 req/sec for most
    endpoints.

    **Progress callback**: The optional ``on_progress(completed, total)``
    callback enables the UI to show a real-time progress bar via
    Server-Sent Events (SSE). Each completed search triggers a callback.

    Returns:
        found:     list of track dicts (original fields + added "uri" and "cover_url")
        not_found: list of "artist - track" strings
    """
    found = []
    not_found = []
    unique_tracks = _dedup_tracks_for_search(tracks)
    total = len(unique_tracks)
    completed = 0
    # L3 (2026-05-06): consume the streaming generator so search_tracks
    # and iter_search_tracks share one code path. release_year is
    # already populated per-track inside iter_search_tracks, but we
    # still call _enrich_tracks_with_metadata at the end as a no-op
    # safety net (it's idempotent — sets release_year only if missing).
    for kind, payload in iter_search_tracks(tracks):
        if kind == "found":
            found.append(payload)
        else:
            not_found.append(payload)
        completed += 1
        if on_progress:
            on_progress(completed, total)
    _enrich_tracks_with_metadata(found)
    return found, not_found


def filter_emerging_artists(tracks, cutoff_months=6):
    """Filter tracks to keep only those whose album release_date is within
    the last *cutoff_months* months.

    The ``release_date`` field returned by Spotify search can be:
    - ``"YYYY-MM-DD"`` (full date — most common)
    - ``"YYYY-MM"``    (month precision)
    - ``"YYYY"``       (year precision)

    We use the *latest* possible date for each precision level when the
    exact date is not given (e.g., ``"2024"`` → Dec 31 2024), which gives
    new artists the benefit of the doubt.

    Args:
        tracks: list of track dicts (as returned by search_tracks).
        cutoff_months: integer number of months defining "emerging" window.

    Returns:
        (survivors, rejected) — two lists of track dicts.
    """
    now = datetime.now(timezone.utc)
    # Compute the cutoff date: go back cutoff_months calendar months.
    cutoff_month = now.month - cutoff_months
    cutoff_year = now.year
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = datetime(cutoff_year, cutoff_month, 1, tzinfo=timezone.utc)

    survivors = []
    rejected = []

    for track in tracks:
        raw = (track.get("release_date") or "").strip()
        if not raw:
            # No release_date available — keep track (benefit of the doubt)
            survivors.append(track)
            continue

        try:
            if len(raw) == 10:
                # YYYY-MM-DD
                release = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            elif len(raw) == 7:
                # YYYY-MM — use first day of next month (benefit of the doubt)
                year, month = int(raw[:4]), int(raw[5:7])
                if month == 12:
                    last_day = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    last_day = datetime(year, month + 1, 1, tzinfo=timezone.utc)
                release = last_day
            elif len(raw) == 4:
                # YYYY — use Dec 31 of that year (benefit of the doubt)
                release = datetime(int(raw), 12, 31, tzinfo=timezone.utc)
            else:
                # Unrecognised format — keep
                survivors.append(track)
                continue
        except (ValueError, OverflowError):
            survivors.append(track)
            continue

        if release >= cutoff:
            survivors.append(track)
        else:
            logger.debug(
                "Emerging filter rejected %s - %s (release_date=%s, cutoff=%s)",
                track.get("artist"), track.get("track"), raw, cutoff.date()
            )
            rejected.append(track)

    return survivors, rejected


def get_user_playlists():
    """Return the current user's Spotify playlists as a list of dicts.

    Returns: [{"id": "...", "name": "...", "track_count": N}]

    Delegates to fetch_user_playlists() and strips fields not needed by
    the playlist management UI (owner, cover_url).
    """
    rich = fetch_user_playlists(limit=500)
    return [{"id": p["id"], "name": p["name"], "track_count": p["track_count"]} for p in rich]


def get_playlist_tracks(playlist_id):
    """Return all tracks in a playlist with enriched metadata.

    Returns: list of dicts with keys: artist, track, uri, track_id,
    cover_url, spotify_url, artist_url, album_url.
    """
    sp = get_spotify_client()
    tracks = []
    # Feb 2026: Spotify renamed the inner key from "track" to "item".
    results = sp.playlist_items(
        playlist_id,
        fields="items(item(uri,name,artists(name,external_urls),album(images,external_urls),external_urls)),next",
        limit=100,
    )
    while True:
        for entry in results.get("items", []):
            t = entry.get("item") or entry.get("track")
            if not t or not t.get("uri"):
                continue
            uri = t["uri"]
            track_id = uri.split(":")[-1] if uri else None
            artists = t.get("artists", [])
            artist_name = artists[0]["name"] if artists else "Unknown"
            images = t.get("album", {}).get("images", [])
            cover_url = _pick_album_cover(images)
            tracks.append({
                "artist": artist_name,
                "track": t.get("name", ""),
                "uri": uri,
                "track_id": track_id,
                "cover_url": cover_url,
                "spotify_url": t.get("external_urls", {}).get("spotify"),
                "artist_url": artists[0].get("external_urls", {}).get("spotify") if artists else None,
                "album_url": t.get("album", {}).get("external_urls", {}).get("spotify"),
            })
        if results.get("next") is None:
            break
        results = sp.next(results)
    return tracks


def _render_playlist_name(name_template, profile=None):
    """Replace template tokens in a playlist name string.

    Supported tokens: {date} → today's date (YYYY-MM-DD),
                      {style} → first 30 chars of core_description.
    """
    from datetime import date
    name = name_template
    name = name.replace("{date}", date.today().isoformat())
    if profile:
        style = profile.get("preferences", {}).get("core_description", "")[:30].strip()
        name = name.replace("{style}", style)
    else:
        name = name.replace("{style}", "")
    return name.strip() or PLAYLIST_NAME


def add_to_playlist(verified_tracks, mode="default", playlist_id=None,
                    playlist_name=None, profile=None):
    """Add pre-verified tracks to a Spotify playlist.

    Parameters:
        verified_tracks: list of track dicts with "uri" key.
        mode: "default" (create/append to SpotyVibe Playlist),
              "create"  (always create a new playlist),
              "append"  (append to existing playlist by playlist_id),
              "replace" (clear then add to existing playlist by playlist_id).
        playlist_id: required for "append" and "replace" modes.
        playlist_name: optional name template for new playlists.
        profile: optional profile dict for name template tokens.

    Returns: {"url": str, "added": int}
    """
    sp = get_spotify_client()
    playlist = None
    uris = [t["uri"] for t in verified_tracks]

    try:
        if mode == "replace" and playlist_id:
            # Clear existing tracks then add new ones
            playlist = sp.playlist(playlist_id)
            sp.playlist_replace_items(playlist_id, [])
            sp.playlist_add_items(playlist_id, uris)
            logger.info("Replaced playlist %s with %d tracks.", playlist_id, len(uris))

        elif mode == "append" and playlist_id:
            # Append to existing playlist, skipping duplicates
            playlist = sp.playlist(playlist_id)
            existing_uris = get_existing_track_uris(sp, playlist_id)
            new_uris = [u for u in uris if u not in existing_uris]
            if new_uris:
                sp.playlist_add_items(playlist_id, new_uris)
            uris = new_uris
            logger.info("Appended %d track(s) to playlist %s.", len(uris), playlist_id)

        elif mode == "create":
            # Always create a new playlist
            name = _render_playlist_name(playlist_name or PLAYLIST_NAME, profile)
            playlist = sp.current_user_playlist_create(name, public=False)
            sp.playlist_add_items(playlist["id"], uris)
            logger.info("Created new playlist '%s' with %d tracks.", name, len(uris))

        else:
            # Default: create or append to the SpotyVibe Playlist
            playlist = find_existing_playlist(sp)
            if playlist:
                logger.info("Found existing playlist: %s (%s)", playlist["name"], playlist["id"])
                existing_uris = get_existing_track_uris(sp, playlist["id"])
            else:
                name = _render_playlist_name(playlist_name or PLAYLIST_NAME, profile)
                logger.info("No existing playlist found — creating '%s'.", name)
                playlist = sp.current_user_playlist_create(name, public=False)
                existing_uris = set()

            new_uris = []
            for t in verified_tracks:
                if t["uri"] in existing_uris:
                    logger.debug("Already in playlist: %s - %s", t["artist"], t["track"])
                else:
                    new_uris.append(t["uri"])

            if new_uris and playlist:
                sp.playlist_add_items(playlist["id"], new_uris)
                logger.info("Added %d new track(s).", len(new_uris))
            else:
                logger.info("No new tracks to add.")
            uris = new_uris

    except SpotifyException as e:
        if e.http_status == 403:
            disconnect_spotify()
            raise TranslatableError(
                "error.spotify.reconnect_required",
                "Spotify returned 403 Forbidden. Your session has expired or "
                "permissions were revoked. Please reconnect via "
                "⚙️ Settings → 🔌 Disconnect Spotify, then Connect to Spotify.",
                status_code=403,
            ) from e
        raise

    if not playlist:
        raise RuntimeError("No playlist resolved — unexpected state in add_to_playlist().")

    playlist_url = playlist["external_urls"]["spotify"]
    logger.info("Playlist: %s", playlist_url)

    return {"url": playlist_url, "added": len(uris), "playlist_id": playlist["id"]}


def delete_playlist(playlist_id):
    """Unfollow (delete) a Spotify playlist by ID.

    Spotify does not have a true 'delete' — current_user_unfollow_playlist()
    is the correct method. For playlists the user owns, unfollowing effectively
    deletes them.
    """
    sp = get_spotify_client()
    sp.current_user_unfollow_playlist(playlist_id)
    logger.info("Deleted (unfollowed) playlist: %s", playlist_id)


def fetch_user_playlists(limit=50):
    """Fetch the current user's playlists for the seed-from-playlist picker.

    Returns a list of dicts: {id, name, owner, track_count, cover_url}.
    Paginates when the user has more playlists than *limit*.
    """
    sp = get_spotify_client()
    playlists = []
    offset = 0
    while True:
        results = sp.current_user_playlists(limit=min(limit - len(playlists), 50), offset=offset)
        for item in results.get("items", []):
            if not item:
                continue
            images = item.get("images") or []
            cover_url = images[0]["url"] if images else ""
            owner = (item.get("owner") or {}).get("display_name", "")
            # Feb 2026: Spotify moved the summary from "tracks" to "items".
            summary = item.get("items") or item.get("tracks") or {}
            playlists.append({
                "id": item["id"],
                "name": item.get("name", ""),
                "owner": owner,
                "track_count": summary.get("total", 0) if isinstance(summary, dict) else 0,
                "cover_url": cover_url,
            })
        if results.get("next") is None or len(playlists) >= limit:
            break
        offset += 50
    return playlists


def fetch_playlist_items_for_seed(playlist_id):
    """Fetch playlist items for seeding a taste profile.

    Uses sp.playlist_items() (not playlist_tracks per CLAUDE.md rule 2).
    Inner key is 'item' (Feb 2026 change).

    Returns: {name, owner, track_count, tracks: [{artist, title, artist_id, album, release_date}], top_artists, top_genres}
    """
    sp = get_spotify_client()

    # Get playlist metadata.
    # Defensive: the Feb-2026 Spotify rename added an ``items`` key
    # alongside the legacy ``tracks`` key on some endpoints. Request both
    # and read whichever is present (mirrors the pattern in
    # ``fetch_user_playlists``).
    playlist_info = sp.playlist(
        playlist_id,
        fields="name,owner(display_name),items(total),tracks(total)",
    )
    name = playlist_info.get("name", "")
    owner = (playlist_info.get("owner") or {}).get("display_name", "")
    items_or_tracks = playlist_info.get("items") or playlist_info.get("tracks") or {}
    total = items_or_tracks.get("total", 0)

    # Fetch items (up to 100 for seed — enough for a good profile)
    results = sp.playlist_items(playlist_id, limit=100,
                                fields="items(item(name,artists(name,id),album(name,release_date)))")
    tracks = []
    artist_counts = {}
    artist_ids = set()
    for item_wrapper in results.get("items", []):
        item = item_wrapper.get("item")
        if not item:
            continue
        artists = item.get("artists") or []
        primary_artist = artists[0] if artists else {}
        artist_name = primary_artist.get("name", "")
        artist_id = primary_artist.get("id", "")
        album = item.get("album") or {}

        tracks.append({
            "artist": artist_name,
            "title": item.get("name", ""),
            "artist_id": artist_id,
            "album": album.get("name", ""),
            "release_date": album.get("release_date", ""),
        })

        if artist_name:
            artist_counts[artist_name] = artist_counts.get(artist_name, 0) + 1
        if artist_id:
            artist_ids.add(artist_id)

    # Top artists by frequency
    top_artists = sorted(artist_counts.keys(), key=lambda a: artist_counts[a], reverse=True)[:5]

    return {
        "name": name,
        "owner": owner,
        "track_count": total,
        "tracks": tracks,
        "top_artists": top_artists,
        "artist_ids": list(artist_ids),
    }
