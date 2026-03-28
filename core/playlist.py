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

import os
import re
# concurrent.futures provides a high-level interface for asynchronous
# execution. ThreadPoolExecutor is used here (not ProcessPoolExecutor)
# because the workload is I/O-bound (HTTP requests to Spotify API),
# not CPU-bound. Threads share memory and have lower overhead than
# processes for this use case.
from concurrent.futures import ThreadPoolExecutor, as_completed

# spotipy is a lightweight Python wrapper for all Spotify Web API
# endpoints. It handles OAuth token lifecycle, request serialization,
# pagination, and error mapping.
import spotipy
from spotipy.exceptions import SpotifyException
# SpotifyOAuth implements the Authorization Code Flow — the user
# authorises via browser, the app receives a code, exchanges it for
# access + refresh tokens, and caches them locally.
from spotipy.oauth2 import SpotifyOAuth
from config import CACHE_FILE, IS_ANDROID


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
    - `scope="playlist-modify-private playlist-read-private"`: Minimal
      scopes — only requests the permissions actually needed. This is a
      security best practice (principle of least privilege).
    - `cache_path`: Token is stored in AppData alongside credentials,
      keeping secrets out of the project directory.
    - `open_browser=False`: The app controls when/how the browser opens
      (via the UI), rather than letting spotipy auto-launch it.
    """
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=REDIRECT_URI,
        scope="playlist-modify-private playlist-read-private",
        cache_path=str(CACHE_FILE),
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
        token = oauth.get_cached_token()
        if not token:
            return "not_authenticated"

        # Validate via auth_manager so expired tokens are auto-refreshed
        sp = spotipy.Spotify(auth_manager=oauth)
        sp.current_user()
        return "authenticated"
    except Exception:
        return "not_authenticated"


def disconnect_spotify():
    """Remove the cached Spotify token so the user can re-authenticate.

    This is useful when the token is stale, revoked, or was obtained with
    outdated scopes.
    """
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            print("Spotify token cache removed.")
        return True
    except Exception as e:
        print(f"Error removing Spotify cache: {e}")
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
        print(f"Spotify callback error: {e}")
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
    results = sp.playlist_tracks(playlist_id, fields="items(track(uri)),next", limit=100)
    while True:
        for entry in results.get("items", []):
            track = entry.get("track")
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
    print(f"Removed from playlist: {artist} - {track}")

    return {"removed": True}


def search_tracks(tracks, on_progress=None):
    """Search Spotify for each track using parallel requests.

    **Concurrency model**: Uses `ThreadPoolExecutor` with 10 workers.
    Each worker creates its own `spotipy.Spotify` client because the
    underlying `requests.Session` is NOT thread-safe. This is a common
    pattern: share-nothing threading where each thread owns its state.

    Why 10 workers? This is a practical sweet spot — enough to saturate
    the network for typical batch sizes (10–30 tracks) without hitting
    Spotify's rate limits. Spotify's API allows ~30 req/sec for most
    endpoints.

    **Progress callback**: The optional `on_progress(completed, total)`
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

    def search_one(t):
        # Each thread gets its own client to avoid sharing a non-thread-safe
        # requests.Session across concurrent workers.
        thread_sp = get_spotify_client()
        query = _build_track_artist_query(t["artist"], t["track"])
        res = thread_sp.search(q=query, type="track", limit=1)

        if res and res["tracks"]["items"]:
            item = res["tracks"]["items"][0]
            uri = item["uri"]
            # Extract the smallest album cover (typically 64×64)
            images = item.get("album", {}).get("images", [])
            cover_url = images[-1]["url"] if images else None
            return "found", {**t, "uri": uri, "cover_url": cover_url}
        return "not_found", f"{t['artist']} - {t['track']}"

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(search_one, t): t for t in unique_tracks}
        completed = 0
        for future in as_completed(futures):
            try:
                result_type, result_data = future.result()
                if result_type == "found":
                    found.append(result_data)
                else:
                    print(f"Not found on Spotify: {result_data}")
                    not_found.append(result_data)
            except Exception as e:
                t = futures[future]
                label = f"{t['artist']} - {t['track']}"
                print(f"Spotify search error for {label}: {e}")
                not_found.append(label)
            completed += 1
            if on_progress:
                on_progress(completed, len(unique_tracks))

    return found, not_found


def add_to_playlist(verified_tracks):
    """Add pre-verified tracks (must have a "uri" key) to the SpotyVibe Playlist.

    **Idempotent design**: Checks for existing tracks in the playlist
    before adding, so calling this function multiple times with the same
    tracks won't create duplicates.

    **Playlist creation**: Uses `current_user_playlist_create()` (maps to
    `POST /v1/me/playlists`) — the modern endpoint. The deprecated
    `POST /v1/users/{user_id}/playlists` is NOT used.

    **Error recovery**: On a 403 Forbidden (expired/revoked token), the
    token cache is cleared and a descriptive error is raised so the UI
    can guide the user to re-authenticate.

    Returns:  {"url": str, "added": int}
    """
    sp = get_spotify_client()
    playlist = None

    try:
        playlist = find_existing_playlist(sp)
        if playlist:
            print(f"Found existing playlist: {playlist['name']} ({playlist['id']})")
            existing_uris = get_existing_track_uris(sp, playlist["id"])
        else:
            print("No existing playlist found — creating a new one.")
            playlist = sp.current_user_playlist_create(PLAYLIST_NAME, public=False)
            existing_uris = set()

        uris = []
        for t in verified_tracks:
            if t["uri"] in existing_uris:
                print(f"Already in playlist: {t['artist']} - {t['track']}")
            else:
                uris.append(t["uri"])

        if uris and playlist:
            sp.playlist_add_items(playlist["id"], uris)
            print(f"Added {len(uris)} new track(s).")
        else:
            print("No new tracks to add.")

    except SpotifyException as e:
        if e.http_status == 403:
            # Token is stale or permissions were revoked — clear cache so
            # the UI shows the "Connect to Spotify" banner on next check.
            disconnect_spotify()
            raise RuntimeError(
                "Spotify returned 403 Forbidden. Your session has expired or "
                "permissions were revoked. Please reconnect via "
                "⚙️ Settings → 🔌 Disconnect Spotify, then Connect to Spotify."
            ) from e
        raise

    playlist_url = playlist["external_urls"]["spotify"] if playlist else ""
    print("Playlist:", playlist_url)

    return {"url": playlist_url, "added": len(uris)}
