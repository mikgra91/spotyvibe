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
import collections
import logging
import os
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

# Spotify rate-limit safety — hardened 2026-05-16 after the dev-mode
# 24 h temp-ban incident:
#
# Spotify post-Feb-2026 puts every new app on "Development Mode" by
# default with an undocumented, much-tighter rate budget on /search.
# Empirically: 700 calls at 0.17 s throttle (~6 req/s) → 24 h ban.
# The previous "176 req per 30 s is safe" assumption was wrong for
# dev-mode apps.
#
# New defaults:
#  - 1.0 s throttle (1 req/s = 30 / 30 s rolling window — far below
#    the dev-mode ceiling, leaves headroom for any concurrent SDK
#    work the user runs locally).
#  - 60 s Retry-After cap: a small ban means we hit the rolling
#    window briefly; sleep + retry is the right move. Big numbers
#    are the escalation system kicking in; abort and let humans
#    investigate.
#  - Adaptive backoff: if any 429 lands in the last 50 calls the
#    throttle doubles to 2 s, then 4 s, etc. After 200 clean calls
#    the throttle halves back, never below the env-configured floor.
#  - Per-process daily budget (env SPOTIFY_DAILY_BUDGET) so we stop
#    cleanly before Spotify does it for us. Defaults to 0 = unbounded
#    (preserves test/dev compatibility).
#
# Most of these constants are overridable via env so we can tune in
# production without a redeploy.
_MAX_RETRY_AFTER_SEC = float(os.environ.get("SPOTIFY_MAX_RETRY_AFTER_SEC", "60"))
_MIN_INTER_REQUEST_SEC = float(os.environ.get("SPOTIFY_MIN_INTER_REQUEST_SEC", "1.0"))
_MAX_TOTAL_BACKOFF_SEC = float(os.environ.get("SPOTIFY_MAX_TOTAL_BACKOFF_SEC", "300"))
_DAILY_BUDGET = int(os.environ.get("SPOTIFY_DAILY_BUDGET", "0"))
# Adaptive throttle window: number of recent calls inspected for 429s
# when deciding whether to widen or narrow the throttle.
_ADAPTIVE_WINDOW = 50
_ADAPTIVE_CLEAN_TO_HALVE = 200
_ADAPTIVE_MAX_MULTIPLIER = 8


class SpotifyRateLimitedError(RuntimeError):
    """Raised when Spotify's Retry-After exceeds our safety cap.

    Indicates the app has been temp-banned (typically a multi-hour
    cooldown). The caller should abort the run cleanly — sleeping for
    that long inside a Cloud Run Job would burn credits with nothing
    to show.
    """


class SpotifyBackoffBudgetExhausted(RuntimeError):
    """Raised when cumulative 429 backoff exceeds the per-process budget."""


class SpotifyDailyBudgetExhausted(RuntimeError):
    """Raised when the per-process daily request budget is hit.

    Not an error condition — the enricher converts this to a clean exit
    that preserves the GCS checkpoint, so the next scheduled run picks
    up where this one stopped without triggering a 429.
    """


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
        # Adaptive-throttle state. _recent_429 tracks the last
        # _ADAPTIVE_WINDOW HTTP statuses so we can react to a single
        # 429 by widening the throttle on the very next call.
        self._recent_429: collections.deque[bool] = collections.deque(
            maxlen=_ADAPTIVE_WINDOW)
        self._clean_streak: int = 0
        self._throttle_multiplier: int = 1
        # Per-process daily-budget counter. The enricher reads
        # `requests_made` between calls so it can decide whether to
        # checkpoint + exit before the next fetch.
        self.requests_made: int = 0
        self.daily_budget: int = _DAILY_BUDGET

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
        """Sleep enough to honour the adaptive per-request floor.

        The effective floor is ``_MIN_INTER_REQUEST_SEC * multiplier``
        where ``multiplier`` doubles after a 429 in the recent window
        and halves back after _ADAPTIVE_CLEAN_TO_HALVE consecutive
        clean calls.
        """
        floor = _MIN_INTER_REQUEST_SEC * self._throttle_multiplier
        elapsed = time.time() - self._last_request_at
        if elapsed < floor:
            time.sleep(floor - elapsed)

    def _record_call_outcome(self, was_429: bool) -> None:
        """Update adaptive-throttle state after a request completes."""
        self._recent_429.append(was_429)
        if was_429:
            self._clean_streak = 0
            if self._throttle_multiplier < _ADAPTIVE_MAX_MULTIPLIER:
                self._throttle_multiplier = min(
                    _ADAPTIVE_MAX_MULTIPLIER,
                    self._throttle_multiplier * 2,
                )
                logger.warning(
                    "Adaptive throttle: 429 observed — widening floor "
                    "to %.2fs (multiplier=%d)",
                    _MIN_INTER_REQUEST_SEC * self._throttle_multiplier,
                    self._throttle_multiplier,
                )
            return
        self._clean_streak += 1
        # Only halve when the entire recent window is clean AND we've
        # accumulated enough consecutive clean calls.
        if (self._throttle_multiplier > 1
                and self._clean_streak >= _ADAPTIVE_CLEAN_TO_HALVE
                and not any(self._recent_429)):
            self._throttle_multiplier = max(1, self._throttle_multiplier // 2)
            self._clean_streak = 0
            logger.info(
                "Adaptive throttle: %d clean calls — halving floor "
                "to %.2fs (multiplier=%d)",
                _ADAPTIVE_CLEAN_TO_HALVE,
                _MIN_INTER_REQUEST_SEC * self._throttle_multiplier,
                self._throttle_multiplier,
            )

    def _check_daily_budget(self) -> None:
        if self.daily_budget > 0 and self.requests_made >= self.daily_budget:
            raise SpotifyDailyBudgetExhausted(
                f"Daily budget {self.daily_budget} requests reached — "
                "stopping cleanly to preserve quota for the next run."
            )

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
        self._check_daily_budget()
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
            self.requests_made += 1
            if resp.status_code == 429:
                self._record_call_outcome(was_429=True)
                retry_after = float(resp.headers.get("Retry-After", "1"))
                if retry_after > _MAX_RETRY_AFTER_SEC:
                    # Big ban (multi-minute → multi-hour). Spotify's
                    # escalation system has kicked in. Abort cleanly —
                    # sleeping inside Cloud Run would burn credits with
                    # nothing to show, and the next retry will likely
                    # re-ban us anyway.
                    raise SpotifyRateLimitedError(
                        f"Spotify Retry-After={retry_after:.0f}s exceeds "
                        f"safety cap {_MAX_RETRY_AFTER_SEC}s — "
                        "app is rate-limited; abort the run, wait at "
                        "least 48 h, then rerun with a smaller --limit, "
                        "a stricter --min-popularity, or a new client_id."
                    )
                # Small Retry-After (≤ 60 s): just transient pressure
                # on the 30 s rolling window. Sleep and retry. The
                # adaptive throttle will widen on subsequent calls.
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
                self._record_call_outcome(was_429=False)
                backoff = 2 ** attempt
                logger.warning("Spotify %d — backoff %ds (attempt %d/%d)",
                               resp.status_code, backoff, attempt + 1,
                               max_retries)
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
            self._record_call_outcome(was_429=False)
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Spotify GET {path} exceeded {max_retries} retries")

    # ── Pre-flight smoke ─────────────────────────────────────────────

    def smoke(self, n: int = 3) -> None:
        """Send *n* cheap search calls to confirm we're not pre-banned.

        Run at job start. If even one of these 429s the run is aborted
        immediately, before the real workload has a chance to consume
        budget. The smoke calls themselves count against
        ``requests_made`` so the daily budget stays consistent.
        """
        if n <= 0:
            return
        probes = ["beatles", "bowie", "abba"][:n]
        for q in probes:
            try:
                self._get("/search", params={
                    "q": f'artist:"{q}"', "type": "artist", "limit": 1,
                })
            except SpotifyRateLimitedError:
                # _get already raised cleanly — let the caller handle it.
                raise
        logger.info("Spotify smoke OK (%d probes, requests_made=%d).",
                    len(probes), self.requests_made)

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





