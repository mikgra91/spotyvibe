"""Minimal Last.fm Web API client for the RAG corpus enrichment job.

Read-only public endpoints — only ``api_key`` query param needed (no
session, no signing, no callback URL). Designed for the Cloud Run build
job — single process, no concurrency, simple exponential backoff on
429 / 5xx with a cumulative-budget abort.

Endpoints used:
  - ``artist.getInfo``    (mbid)  → ``listeners``, ``playcount``, ``tags``
  - ``artist.getTopTags`` (mbid)  → up to 100 weighted tags (0-100)

Why not a higher-level Last.fm wrapper?
  - We only need 2 endpoints.
  - The container stays slim → matters for cold-start cost on Cloud Run.

Last.fm error semantics:
  - HTTP 200 + JSON ``{"error": N, "message": ...}`` is how Last.fm
    signals API-level errors (invalid mbid, missing param, etc.).
  - HTTP 429 / 5xx are honoured with backoff.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger("lastfm_enrichment.client")

_API_BASE = "https://ws.audioscrobbler.com/2.0/"

_REQUEST_TIMEOUT = 15.0

# Last.fm publishes no hard rate limit but the docs recommend ~5 req/s;
# 210 ms ≈ 4.7 req/s sits comfortably under that.
_MIN_INTER_REQUEST_SEC = 0.21

# Cap on Retry-After we will respect; longer means abort the run.
_MAX_RETRY_AFTER_SEC = 300

# Cumulative 429/5xx backoff budget per process; if exceeded we abort
# (something structural is wrong).
_MAX_TOTAL_BACKOFF_SEC = 300

# Last.fm error codes that indicate the *artist* request is bad and
# retrying would not help — propagate as ``LastfmArtistNotFound``
# instead of generic LastfmError so the driver can skip cleanly.
#   6 = "The artist you supplied could not be found"
#   7 = "Invalid resource specified"
_NOT_FOUND_CODES = frozenset({6, 7})

# Codes that indicate the API key / app itself is bad (auth problem).
# Surface as LastfmAuthError so the driver fails loudly rather than
# silently producing an empty corpus.
#   10 = "Invalid API key"
#   26 = "Suspended API key"
_AUTH_ERROR_CODES = frozenset({10, 26})


class LastfmError(RuntimeError):
    """Generic Last.fm API error."""


class LastfmAuthError(LastfmError):
    """API key invalid / suspended — abort the run."""


class LastfmArtistNotFound(LastfmError):
    """Last.fm has no record matching the supplied artist/mbid."""


class LastfmRateLimitedError(RuntimeError):
    """Server-supplied Retry-After exceeded our safety cap."""


class LastfmBackoffBudgetExhausted(RuntimeError):
    """Cumulative 429/5xx backoff exceeded the per-process budget."""


@dataclass
class LastfmArtistInfo:
    """Per-artist Last.fm enrichment payload."""
    listeners: int | None = None
    playcount: int | None = None
    # ``tags`` is the merged + deduped 0-100 weighted tag list from
    # ``getTopTags`` — driver-side filtering (min weight) lives in
    # ``enrich_with_lastfm.py`` so the client stays raw.
    tags: list[tuple[str, int]] = field(default_factory=list)


class LastfmClient:
    """Minimal Last.fm REST client with retry + budget."""

    def __init__(self, api_key: str,
                 session: Optional[requests.Session] = None,
                 user_agent: str = "spotivibe-rag-builder/1.0"):
        if not api_key:
            raise ValueError("Last.fm api_key is required")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", user_agent)
        self._last_request_at: float = 0.0
        self._cumulative_backoff: float = 0.0

    # ── Throttling / budgeting ───────────────────────────────────────

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < _MIN_INTER_REQUEST_SEC:
            time.sleep(_MIN_INTER_REQUEST_SEC - elapsed)

    def _account_backoff(self, seconds: float) -> None:
        self._cumulative_backoff += seconds
        if self._cumulative_backoff > _MAX_TOTAL_BACKOFF_SEC:
            raise LastfmBackoffBudgetExhausted(
                f"Cumulative Last.fm backoff {self._cumulative_backoff:.0f}s "
                f"exceeds budget {_MAX_TOTAL_BACKOFF_SEC}s — aborting"
            )

    # ── Generic GET with retry ───────────────────────────────────────

    def _get(self, params: dict, max_retries: int = 5) -> dict:
        """GET ``_API_BASE`` with the given params; retry on 429 / 5xx.

        Returns the parsed JSON body. Raises :class:`LastfmAuthError`,
        :class:`LastfmArtistNotFound`, or :class:`LastfmError` on
        API-level error responses (HTTP 200 + ``error`` JSON field).
        """
        full = {"api_key": self._api_key, "format": "json", **params}
        for attempt in range(max_retries):
            self._throttle()
            self._last_request_at = time.time()
            resp = self._session.get(
                _API_BASE, params=full, timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                if retry_after > _MAX_RETRY_AFTER_SEC:
                    raise LastfmRateLimitedError(
                        f"Last.fm Retry-After={retry_after:.0f}s exceeds "
                        f"safety cap {_MAX_RETRY_AFTER_SEC}s — aborting"
                    )
                logger.warning("Last.fm 429 — sleeping %.1fs (attempt %d/%d)",
                               retry_after, attempt + 1, max_retries)
                self._account_backoff(retry_after)
                time.sleep(retry_after)
                continue
            if 500 <= resp.status_code < 600:
                backoff = 2 ** attempt
                logger.warning("Last.fm %d — backoff %ds (attempt %d/%d)",
                               resp.status_code, backoff, attempt + 1,
                               max_retries)
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            data = resp.json()
            err = data.get("error")
            if err is not None:
                msg = data.get("message") or "unknown Last.fm error"
                if err in _AUTH_ERROR_CODES:
                    raise LastfmAuthError(f"[{err}] {msg}")
                if err in _NOT_FOUND_CODES:
                    raise LastfmArtistNotFound(f"[{err}] {msg}")
                raise LastfmError(f"[{err}] {msg}")
            return data
        raise RuntimeError(
            f"Last.fm GET {params.get('method')} exceeded {max_retries} retries"
        )

    # ── High-level operations ────────────────────────────────────────

    def get_artist_info(self, mbid: str) -> LastfmArtistInfo:
        """Fetch ``artist.getInfo`` for *mbid*.

        Returns listeners + playcount; *tags* on the returned object are
        left empty (caller should merge in ``get_top_tags``).
        """
        if not mbid:
            return LastfmArtistInfo()
        try:
            data = self._get({"method": "artist.getInfo", "mbid": mbid})
        except LastfmArtistNotFound:
            return LastfmArtistInfo()
        artist = (data or {}).get("artist") or {}
        stats = artist.get("stats") or {}
        return LastfmArtistInfo(
            listeners=_safe_int(stats.get("listeners")),
            playcount=_safe_int(stats.get("playcount")),
        )

    def get_top_tags(self, mbid: str) -> list[tuple[str, int]]:
        """Fetch ``artist.getTopTags`` for *mbid*.

        Returns ``[(tag_name_lower, weight), ...]`` where weight is the
        Last.fm 0-100 normalised popularity score. Empty list if the
        artist is not found or has no tags.
        """
        if not mbid:
            return []
        try:
            data = self._get({"method": "artist.getTopTags", "mbid": mbid})
        except LastfmArtistNotFound:
            return []
        toptags = (data or {}).get("toptags") or {}
        raw_tags = toptags.get("tag") or []
        # ``tag`` is sometimes a single dict instead of a list when
        # there is exactly one tag — normalise.
        if isinstance(raw_tags, dict):
            raw_tags = [raw_tags]
        out: list[tuple[str, int]] = []
        seen: set[str] = set()
        for entry in raw_tags:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip().lower()
            if not name or name in seen:
                continue
            weight = _safe_int(entry.get("count")) or 0
            if weight < 0:
                weight = 0
            if weight > 100:
                weight = 100
            seen.add(name)
            out.append((name, weight))
        return out

    def fetch_artist(self, mbid: str) -> LastfmArtistInfo:
        """Convenience: ``get_artist_info`` + ``get_top_tags`` merged."""
        info = self.get_artist_info(mbid)
        info.tags = self.get_top_tags(mbid)
        return info


def _safe_int(value) -> int | None:
    """Coerce a Last.fm scalar to int, returning None when unparsable."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
