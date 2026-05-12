"""Track existence verifier abstraction (Track A — verifier decoupling).

Production today: every track suggested by Stage 3 is verified against
Spotify's search API to confirm it exists and to enrich the entry with
album cover, preview URL, release date, etc. That single Spotify call
is the rate-limit bottleneck of the evaluation harness — burning the
user's quota and stretching full evals to 40+ minutes.

This module abstracts the "does this track exist?" question behind a
``Verifier`` Protocol so the eval harness can swap in cheaper, offline,
or no-op verifiers. Production code continues to use ``SpotifyVerifier``
by default; ``NullVerifier`` is the deferred-mode shortcut used by
fingerprint probes and "fast" eval runs (per S.6 #1 the harness skips
push-to-Spotify whenever the verifier is anything but Spotify).

Production behaviour is unchanged: ``playlist.iter_search_tracks`` only
consults a verifier when one has been explicitly installed via
``playlist.set_verifier(...)``. The eval harness installs / clears the
verifier in a try/finally so production callers (the Flask SSE
endpoint) always see the default path.

See next-steps.md §"Research Track A" §A.4 for the layered architecture
(L0 overlay → L1 MusicBrainz/Last.fm → L2 Spotify) that ``ChainVerifier``
will eventually compose. This first slice only ships the two endpoints
the harness needs today: Spotify ground-truth and Null.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Verifier(Protocol):
    """Single-track existence verifier.

    Implementations must return a tuple matching the contract of
    ``playlist._do_spotify_search``:

    - ``("found", enriched_track)`` where ``enriched_track`` is the
      input dict merged with whatever extras the verifier can provide
      (Spotify URI, release date, …). At minimum the result MUST
      preserve every key in the input.
    - ``("not_found", label)`` where ``label`` is the human-readable
      ``"{artist} - {track}"`` string used by the SSE event payload.

    Implementations should be safe to call concurrently from a
    ``ThreadPoolExecutor`` — the production search path uses up to 5
    workers (see ``playlist._resolve_search_pool_size``).
    """

    name: str

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]: ...


class SpotifyVerifier:
    """Wraps the existing Spotify search path.

    This is the production default. The verifier itself is intentionally
    very thin: it owes its retry, throttle, cache, and 429 handling to
    ``playlist._do_spotify_search``. Keeping the logic in one place
    means the abstraction does not change Spotify behaviour by an iota.

    Constructed with a ``shared_sp`` spotipy client so the verifier
    can hand it to the worker thread the way ``iter_search_tracks``
    does today.
    """

    name = "spotify"

    def __init__(self, shared_sp: Any):
        self._sp = shared_sp

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        # Imported here (not at module top) to avoid a circular import:
        # playlist.py imports verify.py at module load time.
        from .playlist import _do_spotify_search
        return _do_spotify_search(track, self._sp)


class NullVerifier:
    """No-op verifier — every track is treated as ``"found"``.

    Returned dicts are the input dict with synthetic / empty enrichment
    fields so downstream code (release_year parsing, cover-URL display)
    does not need to special-case ``None``. The eval harness should
    never push a ``NullVerifier`` playlist to Spotify — there are no
    URIs.

    Use in:

    - Probe runs that only care about Stage 3 output shape.
    - "Fast" eval mode (no Spotify rate-limit ceiling).
    - Deferred mode where the late-verify pass fills URIs in batch
      after the session ends.
    """

    name = "null"

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        enriched = dict(track)
        # Synthetic Spotify-shaped enrichment so iter_search_tracks's
        # release_year parsing and the SSE event payload don't crash.
        enriched.setdefault("uri", None)
        enriched.setdefault("track_id", None)
        enriched.setdefault("cover_url", None)
        enriched.setdefault("preview_url", None)
        enriched.setdefault("spotify_url", None)
        enriched.setdefault("album_url", None)
        enriched.setdefault("release_date", None)
        enriched.setdefault("artist_url", None)
        enriched.setdefault("artist_id", None)
        return "found", enriched


# ── Title normalisation helper ───────────────────────────────────────

_TITLE_TRAIL_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")


def normalise_title(title: str) -> str:
    """Lowercase, strip diacritics, drop trailing parenthetical / bracketed
    annotations (``" (Remastered 2020)"``, ``"[Live]"``), collapse
    punctuation + whitespace.

    Designed so production picks like ``"Good Day (Remastered 2024)"``
    still match an overlay entry of ``"Good Day"``. Strips only the
    LAST trailing bracketed group — multiple suffixes are rare and the
    second is usually meaningful (e.g. ``"Track (Acoustic) (2020)"`` →
    ``"track (acoustic)"`` keeps the version distinction).
    """
    if not title:
        return ""
    s = unicodedata.normalize("NFKD", str(title))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _TITLE_TRAIL_BRACKETS.sub("", s)
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ── OverlayVerifier ──────────────────────────────────────────────────

class OverlayVerifier:
    """Verifies tracks against the RAG corpus's ``top_tracks`` overlay.

    Lookup procedure:
      1. Normalise the artist name and look it up in
         ``corpus.by_name_normalised``. Miss → ``("not_found", label)``.
      2. Fetch the artist's ``top_tracks`` list. Empty → ``("not_found",
         label)``. (An artist with no grounding tracks cannot be
         verified offline — the user should fall back to a chain that
         consults L1 / L2.)
      3. Compare the normalised query title to each normalised overlay
         title. Match rules: equality OR either-side substring (handles
         remaster / live / single-edit suffixes). First match wins.
      4. On match: return ``("found", enriched)`` with Spotify-shaped
         enrichment fields set to ``None`` (same shape as
         ``NullVerifier``) so downstream code never KeyErrors.

    Construction:
        from core.src.suggestions import get_rag_corpus
        v = OverlayVerifier(get_rag_corpus())

    Future ``ChainVerifier`` (Step 5) will wrap
    ``[OverlayVerifier, MusicBrainzVerifier, SpotifyVerifier]`` so a
    miss here cascades automatically.
    """

    name = "overlay"

    def __init__(self, corpus: Any):
        if corpus is None:
            raise ValueError(
                "OverlayVerifier requires a loaded RagCorpus; got None. "
                "Ensure the eval harness called suggestions.set_rag_corpus "
                "(or the production startup wiring) before constructing."
            )
        self._corpus = corpus

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        artist  = str(track.get("artist") or "").strip()
        title   = str(track.get("track")  or "").strip()
        label   = f"{artist} - {title}"
        if not artist or not title:
            return "not_found", label

        from .rag.corpus import normalise_name
        nkey = normalise_name(artist)
        idx  = self._corpus.by_name_normalised.get(nkey)
        if idx is None:
            return "not_found", label

        row = self._corpus.artists[idx]
        overlay_titles = list(row.top_tracks or [])
        if not overlay_titles:
            return "not_found", label

        q = normalise_title(title)
        if not q:
            return "not_found", label
        for ot in overlay_titles:
            n_ot = normalise_title(ot)
            if not n_ot:
                continue
            if n_ot == q or n_ot in q or q in n_ot:
                # Match — synthesise Spotify-shape enrichment so the
                # consumer never has to special-case the missing keys.
                enriched = dict(track)
                enriched.setdefault("uri", None)
                enriched.setdefault("track_id", None)
                enriched.setdefault("cover_url", None)
                enriched.setdefault("preview_url", None)
                enriched.setdefault("spotify_url", None)
                enriched.setdefault("album_url", None)
                enriched.setdefault("release_date", None)
                enriched.setdefault("artist_url", None)
                enriched.setdefault("artist_id", None)
                # Audit breadcrumb so trace consumers can tell L0 hits
                # apart from L2 ground-truth hits.
                enriched["verified_by"] = "overlay"
                enriched["overlay_match"] = ot
                return "found", enriched

        return "not_found", label


# ── Persistent cache (shared by MB + Lastfm verifiers) ───────────────


class _SqliteVerifyCache:
    """Tiny SQLite-backed cache: ``(verifier, artist_norm, title_norm)`` →
    ``("found", payload_json)`` or ``("not_found", None)``.

    Used by ``MusicBrainzVerifier`` and ``LastfmVerifier`` so each
    unique (artist, track) query hits the live API at most once across
    every eval session. The cache lives at
    ``<APP_DIR>/.verify_cache.sqlite`` by default; tests pass a tmpdir.
    """

    _DDL = (
        "CREATE TABLE IF NOT EXISTS verify_cache ("
        "  verifier TEXT NOT NULL, "
        "  artist   TEXT NOT NULL, "
        "  title    TEXT NOT NULL, "
        "  kind     TEXT NOT NULL, "
        "  payload  TEXT, "
        "  ts       REAL NOT NULL, "
        "  PRIMARY KEY (verifier, artist, title)"
        ")"
    )

    def __init__(self, path: Path | str):
        self._path = str(path)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(self._DDL)

    def _connect(self):
        # check_same_thread=False is safe because we serialise via _lock.
        return sqlite3.connect(self._path, isolation_level=None,
                                check_same_thread=False)

    def get(self, verifier: str, artist: str, title: str
            ) -> tuple[str, str | None] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT kind, payload FROM verify_cache "
                "WHERE verifier=? AND artist=? AND title=?",
                (verifier, artist, title),
            ).fetchone()
        if row is None:
            return None
        return row[0], row[1]

    def put(self, verifier: str, artist: str, title: str,
            kind: str, payload: str | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO verify_cache VALUES (?,?,?,?,?,?)",
                (verifier, artist, title, kind, payload, time.time()),
            )


_DEFAULT_CACHE: _SqliteVerifyCache | None = None
_CACHE_LOCK = threading.Lock()


def _default_cache() -> _SqliteVerifyCache:
    """Lazily create the process-wide cache under ``config._APP_DIR``."""
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is not None:
        return _DEFAULT_CACHE
    with _CACHE_LOCK:
        if _DEFAULT_CACHE is None:
            try:
                import config
                app_dir = Path(config._APP_DIR)
            except Exception:                                          # noqa: BLE001
                # In tests / standalone scripts; fall back to cwd.
                app_dir = Path(".")
            app_dir.mkdir(parents=True, exist_ok=True)
            _DEFAULT_CACHE = _SqliteVerifyCache(app_dir / ".verify_cache.sqlite")
    return _DEFAULT_CACHE


# ── MusicBrainzVerifier ──────────────────────────────────────────────

_MB_BASE = "https://musicbrainz.org/ws/2"
_MB_USER_AGENT = "spotivibe-eval/1.0 ( https://github.com/Michael-Gratzl/spotyvibe )"
_MB_MIN_INTER_REQUEST = 1.05                                            # 1 req/s hard cap + slack
_MB_TIMEOUT = 15
_MB_RETRY_AFTER_CAP = 90


class MusicBrainzVerifier:
    """Verifies tracks against the MusicBrainz ``recording`` endpoint.

    One HTTP call per (artist, track) miss; subsequent calls hit the
    SQLite cache so the second eval session pays zero rate-limit cost.
    Throttles to ~1 req/s (MB's hard limit; bursts → IP block). On
    ``Retry-After`` > 90 s the verifier raises so the harness can
    cleanly abort the run.

    On match, the verifier returns the input dict enriched with
    ``release_date`` (first-release-date from MB) and a
    ``verified_by="musicbrainz"`` breadcrumb. Other Spotify-shaped
    enrichment keys default to ``None`` so downstream consumers don't
    KeyError.
    """

    name = "musicbrainz"

    def __init__(self, *, cache: "_SqliteVerifyCache | None" = None,
                 session: Any = None, min_inter_request: float = _MB_MIN_INTER_REQUEST):
        self._cache = cache if cache is not None else _default_cache()
        self._min_interval = min_inter_request
        self._last_request_at = 0.0
        if session is None:
            import requests
            session = requests.Session()
            session.headers.setdefault("User-Agent", _MB_USER_AGENT)
        self._session = session

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    @staticmethod
    def _build_query(artist: str, title: str) -> str:
        # MB Lucene-style query - quote both terms to survive spaces.
        def esc(v: str) -> str:
            return v.replace('\\', '\\\\').replace('"', '\\"')
        return f'artist:"{esc(artist)}" AND recording:"{esc(title)}"'

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        import json as _json
        artist = str(track.get("artist") or "").strip()
        title  = str(track.get("track")  or "").strip()
        label  = f"{artist} - {title}"
        if not artist or not title:
            return "not_found", label

        a_norm, t_norm = artist.lower(), title.lower()
        cached = self._cache.get(self.name, a_norm, t_norm)
        if cached is not None:
            kind, payload = cached
            if kind == "found":
                extras = _json.loads(payload) if payload else {}
                return "found", {**track, **extras, "verified_by": self.name}
            return "not_found", label

        params = {
            "query": self._build_query(artist, title),
            "fmt": "json",
            "limit": "1",
        }
        self._throttle()
        self._last_request_at = time.time()
        try:
            resp = self._session.get(f"{_MB_BASE}/recording", params=params,
                                      timeout=_MB_TIMEOUT)
        except Exception as exc:                                       # noqa: BLE001
            # Transient network errors degrade to "not_found" without
            # polluting the cache - next session will retry.
            return "not_found", label

        if resp.status_code == 503 or resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After") or 1)
            if retry_after > _MB_RETRY_AFTER_CAP:
                raise RuntimeError(
                    f"MusicBrainz Retry-After={retry_after}s exceeds cap "
                    f"{_MB_RETRY_AFTER_CAP}s — aborting verifier"
                )
            time.sleep(retry_after)
            return "not_found", label                                   # don't cache
        if resp.status_code != 200:
            return "not_found", label

        try:
            data = resp.json()
        except Exception:                                              # noqa: BLE001
            return "not_found", label

        recordings = data.get("recordings") or []
        if not recordings:
            self._cache.put(self.name, a_norm, t_norm, "not_found", None)
            return "not_found", label

        first = recordings[0]
        extras = {
            "release_date": first.get("first-release-date") or None,
            "mb_recording_id": first.get("id"),
            "uri": None, "track_id": None, "cover_url": None,
            "preview_url": None, "spotify_url": None, "album_url": None,
            "artist_url": None, "artist_id": None,
        }
        self._cache.put(self.name, a_norm, t_norm, "found", _json.dumps(extras))
        return "found", {**track, **extras, "verified_by": self.name}


# ── LastfmVerifier ───────────────────────────────────────────────────

_LASTFM_API_BASE = "https://ws.audioscrobbler.com/2.0/"
_LASTFM_TIMEOUT = 15


class LastfmVerifier:
    """Verifies tracks via Last.fm's ``track.getInfo``.

    Last.fm returns ``error: 6`` for an unknown track; anything else
    with a ``track.name`` field is treated as a hit. Uses the same
    SQLite cache as ``MusicBrainzVerifier`` (separate row namespace
    via the ``verifier=lastfm`` key).

    Requires ``LASTFM_API_KEY`` in the environment; if absent, every
    call short-circuits to ``not_found`` without raising — let the
    chain fall through to the next verifier.
    """

    name = "lastfm"

    def __init__(self, *, api_key: str | None = None,
                 cache: "_SqliteVerifyCache | None" = None,
                 session: Any = None):
        import os
        self._api_key = api_key or os.environ.get("LASTFM_API_KEY") or ""
        self._cache = cache if cache is not None else _default_cache()
        if session is None:
            import requests
            session = requests.Session()
            session.headers.setdefault("User-Agent",
                                       "spotivibe-eval/1.0")
        self._session = session

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        import json as _json
        artist = str(track.get("artist") or "").strip()
        title  = str(track.get("track")  or "").strip()
        label  = f"{artist} - {title}"
        if not artist or not title or not self._api_key:
            return "not_found", label

        a_norm, t_norm = artist.lower(), title.lower()
        cached = self._cache.get(self.name, a_norm, t_norm)
        if cached is not None:
            kind, payload = cached
            if kind == "found":
                extras = _json.loads(payload) if payload else {}
                return "found", {**track, **extras, "verified_by": self.name}
            return "not_found", label

        params = {
            "method": "track.getInfo",
            "api_key": self._api_key,
            "artist": artist,
            "track":  title,
            "format": "json",
            "autocorrect": "1",
        }
        try:
            resp = self._session.get(_LASTFM_API_BASE, params=params,
                                      timeout=_LASTFM_TIMEOUT)
            data = resp.json()
        except Exception:                                              # noqa: BLE001
            return "not_found", label

        if "error" in data:
            self._cache.put(self.name, a_norm, t_norm, "not_found", None)
            return "not_found", label

        tr = data.get("track") or {}
        if not tr.get("name"):
            self._cache.put(self.name, a_norm, t_norm, "not_found", None)
            return "not_found", label

        extras = {
            "release_date": None,                                       # Last.fm rarely surfaces this
            "lastfm_url":   tr.get("url"),
            "uri": None, "track_id": None, "cover_url": None,
            "preview_url": None, "spotify_url": None, "album_url": None,
            "artist_url": None, "artist_id": None,
        }
        self._cache.put(self.name, a_norm, t_norm, "found", _json.dumps(extras))
        return "found", {**track, **extras, "verified_by": self.name}


# ── ChainVerifier ────────────────────────────────────────────────────

class ChainVerifier:
    """Composite verifier — first-hit-wins across an ordered list.

    Construction::

        ChainVerifier([OverlayVerifier(corpus),
                       MusicBrainzVerifier(),
                       LastfmVerifier()])

    Each constituent is consulted in order. The first ``("found", ...)``
    return wins; ``("not_found", ...)`` cascades to the next verifier.
    When every verifier misses, returns the LAST verifier's not_found
    tuple (so the label is stable).
    """

    name = "chain"

    def __init__(self, verifiers: list[Any]):
        if not verifiers:
            raise ValueError("ChainVerifier requires at least one verifier")
        self._verifiers = list(verifiers)

    def verify(self, track: dict[str, Any]) -> tuple[str, Any]:
        last_miss: tuple[str, Any] | None = None
        for v in self._verifiers:
            try:
                kind, payload = v.verify(track)
            except Exception as exc:                                   # noqa: BLE001
                # A misbehaving verifier shouldn't break the chain.
                last_miss = ("not_found",
                              f"{track.get('artist','?')} - {track.get('track','?')}")
                continue
            if kind == "found":
                return kind, payload
            last_miss = (kind, payload)
        return last_miss or (
            "not_found",
            f"{track.get('artist','?')} - {track.get('track','?')}",
        )


__all__ = [
    "Verifier", "SpotifyVerifier", "NullVerifier", "OverlayVerifier",
    "MusicBrainzVerifier", "LastfmVerifier", "ChainVerifier",
    "normalise_title",
]
