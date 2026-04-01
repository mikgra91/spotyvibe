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
from itertools import zip_longest

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
    cache_handler = CacheFileHandler(cache_path=str(CACHE_FILE))
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=REDIRECT_URI,
        scope="playlist-modify-private playlist-read-private",
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
    # playlist_items() maps to GET /playlists/{id}/items (the current endpoint
    # after Spotify removed /tracks in February 2026).
    results = sp.playlist_items(playlist_id, fields="items(track(uri)),next", limit=100)
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
        res = thread_sp.search(q=query, type="track", limit=1, market="from_token")

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
            artists = item.get("artists", [])
            artist_url = artists[0].get("external_urls", {}).get("spotify") if artists else None
            enriched = {
                **t,
                "uri": uri,
                "track_id": track_id,
                "cover_url": cover_url,
                "preview_url": preview_url,
                "spotify_url": spotify_url,
                "album_url": album_url,
                "artist_url": artist_url,
            }
            return "found", enriched
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


def filter_by_audio_features(sp, tracks: list, filters: dict) -> tuple:
    """Filter tracks by Spotify audio features.

    Parameters:
        sp: authenticated spotipy.Spotify client
        tracks: list of track dicts with "uri" key
        filters: dict of {feature: {"min": float, "max": float}}
                 Supported features: energy, tempo, valence, danceability,
                 acousticness, instrumentalness, speechiness, loudness.
                 Any feature can be omitted or set to None to skip it.

    Returns (passing, filtered_out) — both are lists of track dicts.
    """
    if not filters or not tracks:
        return tracks, []

    uris = [t["uri"] for t in tracks]
    if not uris:
        return tracks, []

    try:
        features_list = sp.audio_features(uris)
    except Exception as e:
        print(f"audio_features call failed: {e}")
        return tracks, []

    passing = []
    filtered_out = []

    for track, features in zip_longest(tracks, features_list or [], fillvalue=None):
        if track is None:
            continue
        if features is None:
            passing.append(track)
            continue

        ok = True
        for feature, bounds in filters.items():
            if not bounds:
                continue
            val = features.get(feature)
            if val is None:
                continue
            lo = bounds.get("min")
            hi = bounds.get("max")
            if lo is not None and val < lo:
                ok = False; break
            if hi is not None and val > hi:
                ok = False; break

        if ok:
            passing.append(track)
        else:
            label = f"{track.get('artist','?')} - {track.get('track','?')}"
            print(f"Audio-feature filtered: {label}")
            filtered_out.append(track)

    return passing, filtered_out


def get_user_playlists():
    """Return the current user's Spotify playlists as a list of dicts.

    Returns: [{"id": "...", "name": "...", "track_count": N}]
    """
    sp = get_spotify_client()
    result = []
    offset = 0
    while True:
        playlists = sp.current_user_playlists(limit=50, offset=offset)
        for pl in playlists.get("items", []):
            result.append({
                "id": pl["id"],
                "name": pl["name"],
                "track_count": pl.get("tracks", {}).get("total", 0),
            })
        if playlists.get("next") is None:
            break
        offset += 50
    return result


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
            print(f"Replaced playlist {playlist_id} with {len(uris)} tracks.")

        elif mode == "append" and playlist_id:
            # Append to existing playlist, skipping duplicates
            playlist = sp.playlist(playlist_id)
            existing_uris = get_existing_track_uris(sp, playlist_id)
            new_uris = [u for u in uris if u not in existing_uris]
            if new_uris:
                sp.playlist_add_items(playlist_id, new_uris)
            uris = new_uris
            print(f"Appended {len(uris)} track(s) to playlist {playlist_id}.")

        elif mode == "create":
            # Always create a new playlist
            name = _render_playlist_name(playlist_name or PLAYLIST_NAME, profile)
            playlist = sp.current_user_playlist_create(name, public=False)
            sp.playlist_add_items(playlist["id"], uris)
            print(f"Created new playlist '{name}' with {len(uris)} tracks.")

        else:
            # Default: create or append to the SpotyVibe Playlist
            playlist = find_existing_playlist(sp)
            if playlist:
                print(f"Found existing playlist: {playlist['name']} ({playlist['id']})")
                existing_uris = get_existing_track_uris(sp, playlist["id"])
            else:
                name = _render_playlist_name(playlist_name or PLAYLIST_NAME, profile)
                print(f"No existing playlist found — creating '{name}'.")
                playlist = sp.current_user_playlist_create(name, public=False)
                existing_uris = set()

            new_uris = []
            for t in verified_tracks:
                if t["uri"] in existing_uris:
                    print(f"Already in playlist: {t['artist']} - {t['track']}")
                else:
                    new_uris.append(t["uri"])

            if new_uris and playlist:
                sp.playlist_add_items(playlist["id"], new_uris)
                print(f"Added {len(new_uris)} new track(s).")
            else:
                print("No new tracks to add.")
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

    playlist_url = playlist["external_urls"]["spotify"] if playlist else ""
    print("Playlist:", playlist_url)

    return {"url": playlist_url, "added": len(uris), "playlist_id": playlist["id"] if playlist else None}
