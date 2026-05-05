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
_MIN_INTER_REQUEST_SEC = 0.18

# Cap on Retry-After we will respect; longer means abort the run.
_MAX_RETRY_AFTER_SEC = 300

# Cumulative 429/5xx backoff budget per process; if exceeded we abort
# (something structural is wrong).
_MAX_TOTAL_BACKOFF_SEC = 300

# Consecutive transient-failure circuit breaker. After this many
# back-to-back artists fail with non-recoverable transients (network
# error, non-JSON body), abort the whole run — Last.fm is likely down
# or the egress path is broken, and there is no point spending the
# remaining 18h budget on doomed lookups. Resets on any success.
_MAX_CONSECUTIVE_TRANSIENT_FAILURES = 25

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


class LastfmTransientFailure(LastfmError):
    """Network / non-JSON / empty-body failure after exhausting retries.

    Distinct from :class:`LastfmError` (API-level error) so the driver
    can choose to skip the offending artist while still aborting on
    structural problems (auth, rate-limit, budget).
    """


class LastfmServiceUnavailable(RuntimeError):
    """Too many consecutive transient failures — service likely down."""


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
        self._consecutive_transient_failures: int = 0

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
        """GET ``_API_BASE`` with the given params; retry on 429 / 5xx /
        network errors / non-JSON bodies.

        Returns the parsed JSON body. Raises :class:`LastfmAuthError`,
        :class:`LastfmArtistNotFound`, or :class:`LastfmError` on
        API-level error responses (HTTP 200 + ``error`` JSON field).

        After ``max_retries`` exhausts on transient failures, raises
        :class:`LastfmTransientFailure` so the driver can skip the
        offending artist without aborting the whole run.
        """
        full = {"api_key": self._api_key, "format": "json", **params}
        last_transient: str | None = None
        for attempt in range(max_retries):
            self._throttle()
            self._last_request_at = time.time()
            try:
                resp = self._session.get(
                    _API_BASE, params=full, timeout=_REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                # Connection reset, DNS failure, timeout, SSL error,
                # chunked-encoding error mid-stream. All transient.
                backoff = 2 ** attempt
                last_transient = f"network: {type(exc).__name__}: {exc}"
                logger.warning(
                    "Last.fm network error (%s) — backoff %ds (attempt %d/%d)",
                    type(exc).__name__, backoff, attempt + 1, max_retries,
                )
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
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
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                # Non-2xx that isn't 429/5xx (e.g. 400 / 403). Our request
                # is bad — propagate as LastfmError, do not retry.
                raise LastfmError(
                    f"Last.fm HTTP {resp.status_code}: {exc}"
                ) from exc
            # 2xx body — must be JSON. Last.fm has been observed to
            # return HTML maintenance pages, empty bodies, and
            # truncated chunked responses with a 200 status; treat any
            # of these as transient.
            try:
                data = resp.json()
            except ValueError as exc:
                backoff = 2 ** attempt
                body_preview = (resp.text or "")[:120].replace("\n", " ")
                last_transient = (
                    f"non-JSON body (status={resp.status_code}, "
                    f"len={len(resp.content)}): {body_preview!r}"
                )
                logger.warning(
                    "Last.fm non-JSON body (status=%d, len=%d) — "
                    "backoff %ds (attempt %d/%d): %s",
                    resp.status_code, len(resp.content), backoff,
                    attempt + 1, max_retries, body_preview,
                )
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
            if not isinstance(data, dict):
                # Last.fm always returns an object at top level; a list
                # or scalar means the body is corrupt. Retry.
                backoff = 2 ** attempt
                last_transient = f"non-object JSON: {type(data).__name__}"
                logger.warning(
                    "Last.fm non-object JSON (%s) — backoff %ds (attempt %d/%d)",
                    type(data).__name__, backoff, attempt + 1, max_retries,
                )
                self._account_backoff(backoff)
                time.sleep(backoff)
                continue
            err = data.get("error")
            if err is not None:
                msg = data.get("message") or "unknown Last.fm error"
                if err in _AUTH_ERROR_CODES:
                    raise LastfmAuthError(f"[{err}] {msg}")
                if err in _NOT_FOUND_CODES:
                    raise LastfmArtistNotFound(f"[{err}] {msg}")
                raise LastfmError(f"[{err}] {msg}")
            return data
        raise LastfmTransientFailure(
            f"Last.fm GET {params.get('method')} exceeded "
            f"{max_retries} retries (last: {last_transient or 'unknown'})"
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
        """Convenience: ``get_artist_info`` + ``get_top_tags`` merged.

        Single-artist transient failures (network, non-JSON body) are
        swallowed and returned as an empty :class:`LastfmArtistInfo` so
        one bad MBID does not kill an 18 h enrichment run. A consecutive
        run of transient failures trips the circuit breaker
        (:class:`LastfmServiceUnavailable`) — Last.fm is likely down or
        the egress path is broken, and continuing wastes compute.
        """
        try:
            info = self.get_artist_info(mbid)
            tags = self.get_top_tags(mbid)
        except LastfmTransientFailure as exc:
            self._consecutive_transient_failures += 1
            logger.warning(
                "Last.fm transient failure for mbid=%s (consecutive=%d): %s",
                mbid, self._consecutive_transient_failures, exc,
            )
            if (self._consecutive_transient_failures
                    >= _MAX_CONSECUTIVE_TRANSIENT_FAILURES):
                raise LastfmServiceUnavailable(
                    f"{self._consecutive_transient_failures} consecutive "
                    f"transient failures — Last.fm likely unavailable, "
                    f"aborting (last: {exc})"
                ) from exc
            return LastfmArtistInfo()
        # Any successful fetch resets the consecutive-failure counter —
        # even getInfo succeeding while getTopTags fails would not get
        # here, so this only fires on a fully clean lookup.
        self._consecutive_transient_failures = 0
        info.tags = tags
        return info


def _safe_int(value) -> int | None:
    """Coerce a Last.fm scalar to int, returning None when unparsable."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
