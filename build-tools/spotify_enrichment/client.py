"""Minimal Spotify Web API client for the RAG corpus enrichment job.

Uses the Client Credentials flow (app-only token, no user data, no
scopes). Designed for the Cloud Run build job — single process, no
concurrency, simple exponential backoff on 429 / 5xx.

Why not Spotipy?
  - We only need 2 endpoints (search artists, get-artists batch).
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

# Spotify allows up to 50 IDs per /artists batch call.
_MAX_ARTISTS_PER_BATCH = 50

# Per-request timeout. Spotify is usually <500ms; 15 s is generous.
_REQUEST_TIMEOUT = 15.0

# Token refresh cushion — refresh 5 min before expiry to avoid mid-batch
# token expiry during a long enrichment run.
_TOKEN_REFRESH_CUSHION_SEC = 300


@dataclass
class SpotifyArtist:
    """Subset of Spotify artist fields used by the enrichment pipeline."""
    id: str
    name: str
    popularity: int          # 0-100
    followers: int
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

    def _get(self, path: str, params: dict | None = None,
             max_retries: int = 5) -> dict:
        """GET /v1<path> with retry on 429 / 5xx."""
        url = f"{_API_BASE}{path}"
        for attempt in range(max_retries):
            token = self._ensure_token()
            resp = self._session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                logger.warning("Spotify 429 — sleeping %.1fs (attempt %d/%d)",
                               retry_after, attempt + 1, max_retries)
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

    def get_artists(self, ids: Iterable[str]) -> list[SpotifyArtist]:
        """Bulk-fetch artist details, batched 50 at a time."""
        out: list[SpotifyArtist] = []
        ids_list = [i for i in ids if i]
        for i in range(0, len(ids_list), _MAX_ARTISTS_PER_BATCH):
            batch = ids_list[i: i + _MAX_ARTISTS_PER_BATCH]
            try:
                data = self._get("/artists", params={"ids": ",".join(batch)})
            except requests.HTTPError as exc:
                logger.warning("Spotify get-artists batch failed: %s", exc)
                continue
            for raw in (data.get("artists") or []):
                if not raw:
                    continue
                out.append(SpotifyArtist(
                    id=str(raw.get("id") or ""),
                    name=str(raw.get("name") or ""),
                    popularity=int(raw.get("popularity") or 0),
                    followers=int((raw.get("followers") or {}).get("total") or 0),
                    genres=[str(g) for g in (raw.get("genres") or [])],
                ))
        return out

