"""Spotify metadata lookup using Client Credentials Flow.

This module provides public Spotify metadata (tracks, artists, audio features)
without requiring user OAuth — it uses the Client Credentials flow for
machine-to-machine access to public data only.

Does NOT use spotipy. All HTTP is done via urllib.request.
"""

import base64
import datetime
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import os


class SpotifyMetadataError(Exception):
    """Raised when Spotify metadata lookup fails."""


# ---------------------------------------------------------------------------
# Thread-safe in-memory token cache
# ---------------------------------------------------------------------------

_token_cache: dict = {"token": None, "expires_at": 0.0}
_token_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def get_client_credentials_token() -> str:
    """Get a valid Spotify client credentials token, refreshing if needed.

    Uses SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET from environment
    (loaded via config.load_config()). Token is cached and refreshed
    60 seconds before actual expiry to avoid races.
    """
    with _token_lock:
        now = time.time()
        if _token_cache["token"] and now < _token_cache["expires_at"]:
            return _token_cache["token"]

        client_id = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()

        if not client_id or not client_secret:
            raise SpotifyMetadataError("Spotify credentials not configured")

        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode("utf-8")
        ).decode("utf-8")

        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SpotifyMetadataError(f"Token fetch failed: HTTP {exc.code} {exc.reason}") from exc
        except Exception as exc:
            raise SpotifyMetadataError(f"Token fetch failed: {exc}") from exc

        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3600)

        if not token:
            raise SpotifyMetadataError("Token fetch failed: no access_token in response")

        _token_cache["token"] = token
        # Expire 60s early to avoid using a token right at the boundary
        _token_cache["expires_at"] = now + expires_in - 60

        return token


# ---------------------------------------------------------------------------
# Generic API request
# ---------------------------------------------------------------------------

def spotify_api_request(path: str, token: str, params: dict = None) -> dict:
    """GET https://api.spotify.com/v1/{path} with Bearer token.

    Raises SpotifyMetadataError on 4xx/5xx.
    For 429, reads Retry-After header and sleeps up to 10s, then retries once.
    """
    base_url = f"https://api.spotify.com/v1/{path.lstrip('/')}"
    if params:
        base_url = f"{base_url}?{urllib.parse.urlencode(params)}"

    def _do_request(url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return _do_request(base_url)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            retry_after = int(exc.headers.get("Retry-After", "1"))
            sleep_for = min(retry_after, 10)
            time.sleep(sleep_for)
            try:
                return _do_request(base_url)
            except urllib.error.HTTPError as exc2:
                raise SpotifyMetadataError(
                    f"Spotify API error: HTTP {exc2.code} for {path}"
                ) from exc2
        raise SpotifyMetadataError(
            f"Spotify API error: HTTP {exc.code} for {path}"
        ) from exc
    except Exception as exc:
        raise SpotifyMetadataError(f"Spotify API request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

def normalize_compare_text(text: str) -> str:
    """Lowercase, trim, and collapse internal whitespace for comparison only."""
    return re.sub(r"\s+", " ", text.lower().strip())


# Patterns that represent common version/edition suffixes to strip
_VERSION_SUFFIX_PATTERNS = re.compile(
    r"""[\[\(]                        # opening bracket
    \s*
    (?:
        \d{4}[\s\-]*(?:remaster(?:ed)?|mix|version|edition|release)|  # year-prefixed
        remaster(?:ed)?(?:\s+\d{4})?|
        (?:\d{4}\s+)?(?:mono|stereo)\s+(?:remaster(?:ed)?|mix|version)|
        \d{4}\s+mix|
        (?:deluxe|super\s+deluxe|expanded|special)\s+(?:edition|version)|
        (?:bonus\s+)?(?:track|disc)|
        live(?:\s+(?:at|from|version))?|
        acoustic(?:\s+version)?|
        radio\s+edit|
        single\s+(?:version|edit)|
        original\s+(?:mix|version)|
        [\w\s]+\s+mix|
        [\w\s]+\s+version|
        [\w\s]+\s+remaster(?:ed)?|
        [\w\s]+\s+edition
    )
    \s*
    [\]\)]                            # closing bracket
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_version_suffixes(text: str) -> str:
    """Strip version/edition suffixes like (remastered), [2024 mix], (live), (deluxe edition).

    Case-insensitive. Returns the stripped text with surrounding whitespace removed.
    """
    result = _VERSION_SUFFIX_PATTERNS.sub("", text)
    return result.strip()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_track_candidate(candidate: dict, artist_query: str, track_query: str) -> float:
    """Score a Spotify track search result against query strings.

    Scoring:
      +0.6  exact normalized track name match (after stripping version suffixes)
      +0.3  exact normalized artist name match for any artist on the track

    Note: popularity was previously used as a tie-breaker but was removed
    from the Spotify API in Feb 2026.
    """
    score = 0.0

    norm_track_query = normalize_compare_text(strip_version_suffixes(track_query))
    cand_name = normalize_compare_text(strip_version_suffixes(candidate.get("name", "")))
    if cand_name == norm_track_query:
        score += 0.6

    norm_artist_query = normalize_compare_text(artist_query) if artist_query else ""
    if norm_artist_query:
        for artist in candidate.get("artists", []):
            if normalize_compare_text(artist.get("name", "")) == norm_artist_query:
                score += 0.3
                break

    return score


def score_artist_candidate(candidate: dict, artist_query: str) -> float:
    """Score a Spotify artist search result against an artist query string.

    Scoring:
      +1.0  exact normalized artist name match

    Note: popularity was previously used as a tie-breaker but was removed
    from the Spotify API in Feb 2026.
    """
    score = 0.0

    norm_query = normalize_compare_text(artist_query)
    norm_name = normalize_compare_text(candidate.get("name", ""))
    if norm_name == norm_query:
        score += 1.0

    return score


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def search_track_candidates(artist: str, track: str, market: str, token: str) -> list:
    """Search Spotify for track candidates.

    Uses fielded search (track:{track} artist:{artist}) when both are given,
    otherwise falls back to track:{track}. Returns up to 5 track objects.
    """
    if artist and track:
        q = f'track:"{track}" artist:"{artist}"'
    else:
        q = f'track:"{track}"'

    params = {
        "q": q,
        "type": "track",
        "limit": 5,
        "market": market,
    }
    data = spotify_api_request("search", token, params)
    return data.get("tracks", {}).get("items", [])


def search_artist_candidates(artist: str, market: str, token: str) -> list:
    """Search Spotify for artist candidates.

    Uses fielded search (artist:{artist}). Returns up to 5 artist objects.
    """
    params = {
        "q": f'artist:"{artist}"',
        "type": "artist",
        "limit": 5,
        "market": market,
    }
    data = spotify_api_request("search", token, params)
    return data.get("artists", {}).get("items", [])


# ---------------------------------------------------------------------------
# Individual resource fetchers
# ---------------------------------------------------------------------------

def get_track_metadata(track_id: str, token: str) -> dict:
    """Fetch /v1/tracks/{id} and return a normalized track dict."""
    data = spotify_api_request(f"tracks/{track_id}", token)
    return _normalize_track(data)


def get_artist_metadata(artist_id: str, token: str) -> dict:
    """Fetch /v1/artists/{id} and return a normalized artist dict."""
    data = spotify_api_request(f"artists/{artist_id}", token)
    return _normalize_artist(data)



# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_track(data: dict) -> dict:
    """Extract the fields we care about from a raw Spotify track object.

    Note: 'popularity' was removed from the Spotify API in Feb 2026.
    """
    album = data.get("album") or {}
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "artists": [a.get("name") for a in (data.get("artists") or [])],
        "album": album.get("name"),
        "release_date": album.get("release_date"),
        "duration_ms": data.get("duration_ms"),
        "preview_url": data.get("preview_url"),
        "external_urls": data.get("external_urls") or {},
    }


def _normalize_artist(data: dict) -> dict:
    """Extract the fields we care about from a raw Spotify artist object.

    Note: 'followers' and 'popularity' were removed from the Spotify API
    in Feb 2026.
    """
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "genres": data.get("genres") or [],
        "external_urls": data.get("external_urls") or {},
    }



# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_metadata(
    artist: str | None,
    track: str | None,
    market: str = "US",
) -> dict:
    """Analyze artist/track metadata using Spotify Client Credentials.

    Returns a canonical response dict:
    {
        "query": {"artist": ..., "track": ..., "market": ...},
        "match": {
            "provider": "spotify",
            "type": "track" | "artist",
            "confidence": float,
            "processed_at": ISO8601,
            "spotify_track_id": str | None,
            "spotify_artist_id": str,
        },
        "track": dict | None,
        "artist": dict,
        "warnings": [],
    }

    Note: audio_features and popularity/followers were removed from the
    Spotify Web API in February 2026 and are no longer available.

    Raises SpotifyMetadataError with an appropriate message on failure.
    """
    if not artist and not track:
        raise SpotifyMetadataError("At least one of artist or track is required")

    warnings = []
    token = get_client_credentials_token()
    processed_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # ------------------------------------------------------------------
    # Track + artist search
    # ------------------------------------------------------------------
    if track:
        candidates = search_track_candidates(artist or "", track, market, token)

        if not candidates:
            raise SpotifyMetadataError(
                f"No match found for track '{track}'"
                + (f" by '{artist}'" if artist else "")
            )

        # Score and pick best candidate
        scored = [
            (score_track_candidate(c, artist or "", track), c)
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_track_candidate = scored[0]

        if best_score < 0.5:
            warnings.append("low_confidence_match")

        track_id = best_track_candidate["id"]
        track_data = get_track_metadata(track_id, token)

        # Resolve artist from track result
        primary_artist_name = (
            best_track_candidate.get("artists", [{}])[0].get("name", "")
            if best_track_candidate.get("artists")
            else (artist or "")
        )
        primary_artist_id = (
            best_track_candidate.get("artists", [{}])[0].get("id", "")
            if best_track_candidate.get("artists")
            else None
        )

        if primary_artist_id:
            artist_data = get_artist_metadata(primary_artist_id, token)
        else:
            # Fall back to artist search
            artist_data = _search_and_fetch_artist(
                primary_artist_name or artist or "", market, token, warnings
            )

        return {
            "query": {"artist": artist, "track": track, "market": market},
            "match": {
                "provider": "spotify",
                "type": "track",
                "confidence": round(best_score, 4),
                "processed_at": processed_at,
                "spotify_track_id": track_id,
                "spotify_artist_id": artist_data.get("id"),
            },
            "track": track_data,
            "artist": artist_data,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Artist-only search
    # ------------------------------------------------------------------
    artist_data = _search_and_fetch_artist(artist, market, token, warnings, threshold=0.9)

    return {
        "query": {"artist": artist, "track": None, "market": market},
        "match": {
            "provider": "spotify",
            "type": "artist",
            "confidence": None,  # set by _search_and_fetch_artist via warnings
            "processed_at": processed_at,
            "spotify_track_id": None,
            "spotify_artist_id": artist_data.get("id"),
        },
        "track": None,
        "artist": artist_data,
        "warnings": warnings,
    }


def _search_and_fetch_artist(
    artist: str,
    market: str,
    token: str,
    warnings: list,
    threshold: float = 0.5,
) -> dict:
    """Search for and fetch full artist metadata.

    Appends to warnings in-place. Raises SpotifyMetadataError if not found.
    Returns a normalized artist dict.
    """
    candidates = search_artist_candidates(artist, market, token)

    if not candidates:
        raise SpotifyMetadataError(f"No match found for artist '{artist}'")

    scored = [
        (score_artist_candidate(c, artist), c)
        for c in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_candidate = scored[0]

    if best_score < threshold:
        warnings.append("low_confidence_match")

    artist_id = best_candidate["id"]
    return get_artist_metadata(artist_id, token)
