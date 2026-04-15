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
from config import CACHE_FILE, IS_ANDROID

logger = logging.getLogger(__name__)

# Name used for the managed playlist. If a playlist with this name
# already exists, new tracks are added to it (idempotent). This avoids
# creating duplicate playlists on every generation.
PLAYLIST_NAME = "SpotyVibe Playlist"
# Redirect URI must match what is configured in the Spotify Developer
# Dashboard. The Android variant uses a custom URI scheme (deep link)
# while the desktop variant uses a local HTTP server callback.
REDIRECT_URI = "spotyvibe://callback" if IS_ANDROID else "http://127.0.0.1:5000/callback"


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
        scope="playlist-modify-private playlist-read-private user-read-private",
        cache_handler=cache_handler,
        open_browser=False,
    )


def get_spotify_client():
    """Create an authenticated Spotify client using cached OAuth credentials."""
    return spotipy.Spotify(auth_manager=get_spotify_oauth())


def get_spotify_auth_status():
    """Check whether Spotify credentials are configured and authenticated.

    Returns one of: "not_configured", "not_authenticated", "authenticated".

    Beyond checking for a cached token this also makes a lightweight API
    call (``current_user``) to verify the token is still valid.  Stale or
    revoked tokens are detected and reported as "not_authenticated" so the
    UI can prompt the user to re-connect.

    This three-state return value drives the UI's conditional rendering:
    - not_configured  → show "Enter Spotify credentials" form
    - not_authenticated → show "Connect to Spotify" button
    - authenticated → show the main playlist generation UI
    """
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return "not_configured"

    try:
        oauth = get_spotify_oauth()
        token = oauth.validate_token(oauth.cache_handler.get_cached_token())
        if not token:
            return "not_authenticated"

        # Validate via auth_manager so expired tokens are auto-refreshed
        sp = spotipy.Spotify(auth_manager=oauth)
        sp.current_user()
        return "authenticated"
    except Exception as e:
        logger.warning("Spotify auth check failed: %s", e)
        return "not_authenticated"


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
    """Return the Spotify authorization URL the user must visit."""
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
            track = entry.get("item") or entry.get("track")
            if track and track.get("uri"):
                existing.add(track["uri"])
        if results.get("next") is None:
            break
        results = sp.next(results)
    return existing


def remove_from_playlist(artist, track):
    """Remove a single track from the SpotyVibe Playlist.

    Searches Spotify for the artist + track combination, then removes all
    occurrences of its URI from the playlist.

    Returns a dict:  {"removed": True/False, "reason": "..." (on failure)}
    """
    sp = get_spotify_client()

    playlist = find_existing_playlist(sp)
    if not playlist:
        return {"removed": False, "reason": "Playlist not found"}

    query = _build_track_artist_query(artist, track)
    res = sp.search(q=query, type="track", limit=1)

    if not res or not res["tracks"]["items"]:
        return {"removed": False, "reason": "Track not found on Spotify"}

    uri = res["tracks"]["items"][0]["uri"]

    existing_uris = get_existing_track_uris(sp, playlist["id"])
    if uri not in existing_uris:
        return {"removed": False, "reason": "Track not in playlist"}

    sp.playlist_remove_all_occurrences_of_items(playlist["id"], [uri])
    logger.info("Removed from playlist: %s - %s", artist, track)

    return {"removed": True}


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

    # Deduplicate input
    seen = set()
    unique_tracks = []
    for t in tracks:
        key = f'{t["artist"]} - {t["track"]}'.lower()
        if key not in seen:
            seen.add(key)
            unique_tracks.append(t)

    # ── Pre-fetch token + shared session ──────────────────────────────
    # Validate / refresh the token once.  All workers then use the raw
    # access_token string, skipping per-thread OAuth overhead.
    oauth = get_spotify_oauth()
    token_info = oauth.validate_token(oauth.cache_handler.get_cached_token())
    if not token_info:
        logger.error("Spotify token unavailable — cannot search tracks")
        return [], [f"{t['artist']} - {t['track']}" for t in unique_tracks]
    access_token = token_info["access_token"]

    pool_size = min(10, len(unique_tracks)) or 1
    shared_session = _make_pooled_session(pool_size)

    def search_one(t):
        # Lightweight client: pre-fetched token + shared session.
        # No auth_manager needed — the token was already validated above.
        thread_sp = spotipy.Spotify(
            auth=access_token,
            requests_session=shared_session,
        )
        query = _build_track_artist_query(t["artist"], t["track"])

        # Retry once on 429 (rate limit) using Retry-After header,
        # mirroring the pattern in spotify_metadata.py.
        res = None
        for attempt in range(2):
            try:
                res = thread_sp.search(q=query, type="track", limit=1, market="from_token")
                break
            except SpotifyException as e:
                if e.http_status == 429 and attempt == 0:
                    retry_after = int(e.headers.get("Retry-After", 1))
                    time.sleep(min(retry_after, 10))
                    continue
                raise

        if res and res["tracks"]["items"]:
            item = res["tracks"]["items"][0]
            uri = item["uri"]
            track_id = uri.split(":")[-1] if uri else None
            # Extract the smallest album cover (typically 64×64)
            images = item.get("album", {}).get("images", [])
            cover_url = images[-1]["url"] if images else None
            preview_url = item.get("preview_url")
            spotify_url = item.get("external_urls", {}).get("spotify")
            album_url = item.get("album", {}).get("external_urls", {}).get("spotify")
            release_date = item.get("album", {}).get("release_date")
            artists = item.get("artists", [])
            artist_url = artists[0].get("external_urls", {}).get("spotify") if artists else None
            artist_id = artists[0].get("id") if artists else None
            enriched = {
                **t,
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
            return "found", enriched
        return "not_found", f"{t['artist']} - {t['track']}"

    try:
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = {executor.submit(search_one, t): t for t in unique_tracks}
            completed = 0
            for future in as_completed(futures):
                try:
                    result_type, result_data = future.result()
                    if result_type == "found":
                        found.append(result_data)
                    else:
                        logger.warning("Not found on Spotify: %s", result_data)
                        not_found.append(result_data)
                except Exception as e:
                    t = futures[future]
                    label = f"{t['artist']} - {t['track']}"
                    logger.error("Spotify search error for %s: %s", label, e)
                    not_found.append(label)
                completed += 1
                if on_progress:
                    on_progress(completed, len(unique_tracks))
    finally:
        shared_session.close()

    # ── Batch-enrich: artist genres + release_year ────────────────────
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
            cover_url = images[-1]["url"] if images else None
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
            raise RuntimeError(
                "Spotify returned 403 Forbidden. Your session has expired or "
                "permissions were revoked. Please reconnect via "
                "⚙️ Settings → 🔌 Disconnect Spotify, then Connect to Spotify."
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

    # Get playlist metadata
    playlist_info = sp.playlist(playlist_id, fields="name,owner(display_name),tracks(total)")
    name = playlist_info.get("name", "")
    owner = (playlist_info.get("owner") or {}).get("display_name", "")
    total = (playlist_info.get("tracks") or {}).get("total", 0)

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
