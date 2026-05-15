"""Minimal Spotify Web API client for the RAG corpus enrichment job.

Uses the Client Credentials flow (app-only token, no user data, no
scopes). Designed for the Cloud Run build job — single process, no
concurrency, simple exponential backoff on 429 / 5xx.

Why not Spotipy?
  - We only need 2 endpoints (search artists, get-artist by id).
  - Spotipy pulls in an OAuth dance that's not needed here.
  - Keeping the build container tiny matters for cold-start cost.
"""

from __future__ import annotations

import base64
import logging
import time
import urllib.parse
from dataclasses import dataclass
from typing import Iterable

import requests

logger = logging.getLogger("spotify_enrichment.client")

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"

# Per-request timeout. Spotify is usually <500ms; 15 s is generous.
_REQUEST_TIMEOUT = 15.0

# Token refresh cushion — refresh 5 min before expiry to avoid mid-batch
# token expiry during a long enrichment run.
_TOKEN_REFRESH_CUSHION_SEC = 300

# Spotify rate-limit safety:
#  - hard-cap the server-supplied Retry-After. If Spotify asks us to
#    sleep longer than this (we've seen 21h temp-bans in the wild) we
#    abort the run cleanly instead of hanging.
#  - throttle proactively: a small per-request sleep keeps us well
#    under the documented limits and avoids triggering the temp-ban
#    in the first place.
#  - total backoff budget per process: if cumulative 429 sleeps go
#    above this we abort (something is structurally wrong).
_MAX_RETRY_AFTER_SEC = 300
# 170 ms ≈ 5.9 req/s ≈ 176 req per 30s window — within Spotify's
# undocumented dev-app rolling-window quota (~180-300 req/30s for
# /search). The 21h temp-ban we saw at 70ms (14 req/s = 420/30s)
# confirmed we were over the limit. Conservative margin retained.
_MIN_INTER_REQUEST_SEC = 0.17
_MAX_TOTAL_BACKOFF_SEC = 300


class SpotifyRateLimitedError(RuntimeError):
    """Raised when Spotify's Retry-After exceeds our safety cap.

    Indicates the app has been temp-banned (typically a multi-hour
    cooldown). The caller should abort the run cleanly — sleeping for
    that long inside a Cloud Run Job would burn credits with nothing
    to show.
    """


class SpotifyBackoffBudgetExhausted(RuntimeError):
    """Raised when cumulative 429 backoff exceeds the per-process budget."""


@dataclass
class SpotifyArtist:
    """Subset of Spotify artist fields used by the enrichment pipeline.

    Note: Spotify removed ``popularity`` and ``followers`` from artist
    objects in Feb 2026. ``genres`` is the only field still worth
    keeping; ``id`` is retained for future top-tracks overlay lookups.
    """
    id: str
    name: str
    genres: list[str]


class SpotifyClient:
    """Thin Client-Credentials Spotify HTTP client with retry/backoff."""

    def __init__(self, client_id: str, client_secret: str,
                 session: requests.Session | None = None):
        if not client_id or not client_secret:
            raise ValueError("Spotify client_id and client_secret are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session or requests.Session()
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._last_request_at: float = 0.0
        self._cumulative_backoff: float = 0.0

    # ── Auth ─────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        """Fetch a fresh app-only token via the Client Credentials flow."""
        creds = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        auth = base64.b64encode(creds).decode("ascii")
        resp = self._session.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        logger.info("Spotify token refreshed (expires in %d s)",
                    int(data.get("expires_in", 3600)))

    def _ensure_token(self) -> str:
        if (self._token is None
                or time.time() + _TOKEN_REFRESH_CUSHION_SEC >= self._token_expires_at):
            self._refresh_token()
        assert self._token is not None
        return self._token

    # ── Generic GET with retry ───────────────────────────────────────

    def _throttle(self) -> None:
        """Sleep just enough to keep us under the per-second ceiling."""
        elapsed = time.time() - self._last_request_at
        if elapsed < _MIN_INTER_REQUEST_SEC:
            time.sleep(_MIN_INTER_REQUEST_SEC - elapsed)

    def _account_backoff(self, seconds: float) -> None:
        """Track cumulative 429 backoff; abort if budget exhausted."""
        self._cumulative_backoff += seconds
        if self._cumulative_backoff > _MAX_TOTAL_BACKOFF_SEC:
            raise SpotifyBackoffBudgetExhausted(
                f"Cumulative 429 backoff {self._cumulative_backoff:.0f}s "
                f"exceeds budget {_MAX_TOTAL_BACKOFF_SEC}s — aborting"
            )

    def _get(self, path: str, params: dict | None = None,
             max_retries: int = 5) -> dict:
        """GET /v1<path> with retry on 429 / 5xx."""
        url = f"{_API_BASE}{path}"
        for attempt in range(max_retries):
            self._throttle()
            token = self._ensure_token()
            self._last_request_at = time.time()
            resp = self._session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                if retry_after > _MAX_RETRY_AFTER_SEC:
                    # Spotify temp-banned the app (we've seen 21h cooldowns).
                    # Abort cleanly — nothing useful can happen by waiting.
                    raise SpotifyRateLimitedError(
                        f"Spotify Retry-After={retry_after:.0f}s exceeds "
                        f"safety cap {_MAX_RETRY_AFTER_SEC}s — "
                        "app is rate-limited; abort the run, wait, and "
                        "rerun with a smaller --limit or higher --min-popularity."
                    )
                logger.warning("Spotify 429 — sleeping %.1fs (attempt %d/%d)",
                               retry_after, attempt + 1, max_retries)
                self._account_backoff(retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code == 401:
                # Token expired between our cushion check and the call.
                logger.info("Spotify 401 — forcing token refresh")
                self._token = None
                continue
            if 500 <= resp.status_code < 600:
                backoff = 2 ** attempt
                logger.warning("Spotify %d — backoff %ds (attempt %d/%d)",
                               resp.status_code, backoff, attempt + 1,
                               max_retries)
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Spotify GET {path} exceeded {max_retries} retries")

    # ── High-level operations ────────────────────────────────────────

    def search_artists(self, name: str, limit: int = 5) -> list[dict]:
        """Search for artists matching *name*. Returns raw item dicts.

        We use a quoted artist filter (``artist:"<name>"``) which Spotify
        treats as a phrase match — far fewer false positives than a bare
        keyword search.
        """
        if not name or not name.strip():
            return []
        q = f'artist:"{name.strip()}"'
        try:
            data = self._get("/search", params={
                "q": q,
                "type": "artist",
                "limit": min(limit, 50),
            })
        except requests.HTTPError as exc:
            logger.warning("Spotify search failed for %r: %s", name, exc)
            return []
        return (data.get("artists") or {}).get("items") or []

    def search_top_tracks(self, name: str, max_tracks: int = 5) -> list[str]:
        """Return up to *max_tracks* relevance-ranked track titles for *name*.

        Uses Spotify's ``/v1/search?type=track&q=artist:"NAME"`` endpoint,
        which works on every app tier (the cleaner
        ``/v1/artists/{id}/top-tracks`` returns 403 in Development Mode
        post-2024 Service Terms). Filters results to tracks where one of
        the primary artists actually matches the requested name, so
        search-engine fuzziness can't poison the overlay with
        wrong-artist titles.

        Returns ``[]`` on any error so a single missing artist never
        breaks the whole enrichment run.
        """
        if not name or not name.strip():
            return []
        target = name.strip().lower()
        try:
            data = self._get("/search", params={
                "q": f'artist:"{name.strip()}"',
                "type": "track",
                "limit": max(10, max_tracks * 2),
            })
        except requests.HTTPError as exc:
            logger.warning("Spotify track-search failed for %r: %s", name, exc)
            return []
        items = ((data or {}).get("tracks") or {}).get("items") or []
        out: list[str] = []
        seen: set[str] = set()
        for tr in items:
            if len(out) >= max_tracks:
                break
            # Require an exact-ish artist-name match on at least one
            # credited artist to filter out features by unrelated acts.
            artists = tr.get("artists") or []
            if not any((a.get("name", "") or "").strip().lower() == target
                       for a in artists):
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

    def get_artists(self, ids: Iterable[str]) -> list[SpotifyArtist]:
        """Fetch artist details one at a time via ``GET /artists/{id}``.

        Spotify removed the batch ``GET /artists?ids=…`` endpoint in
        Feb 2026; per-id calls are the supported replacement. Throughput
        is ~4.7 req/s with the throttle, which still fits inside the
        Cloud Run job budget for the enrichment slice.
        """
        out: list[SpotifyArtist] = []
        ids_list = [i for i in ids if i]
        for sp_id in ids_list:
            try:
                raw = self._get(f"/artists/{urllib.parse.quote(sp_id)}")
            except requests.HTTPError as exc:
                logger.warning("Spotify get-artist %s failed: %s", sp_id, exc)
                continue
            if not raw:
                continue
            out.append(SpotifyArtist(
                id=str(raw.get("id") or ""),
                name=str(raw.get("name") or ""),
                genres=[str(g) for g in (raw.get("genres") or [])],
            ))
        return out





