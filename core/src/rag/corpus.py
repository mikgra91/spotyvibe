"""In-memory artist corpus for RAG retrieval.

Loads a `.jsonl.gz` MusicBrainz-derived artist file plus a tag-alias map,
builds inverted tag indices and TF-IDF statistics, and exposes the result
as a ``RagCorpus`` object. Pure Python — no numpy dependency.
"""

from __future__ import annotations

import functools
import gzip
import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .ai_vocab import GENERIC_AI_TAGS

logger = logging.getLogger(__name__)

# Expected schema per JSONL line. Extra fields are ignored; missing fields
# default to empty. See documentation/TechnicalManual.md §"RAG design
# reference" → Per-artist schema for the definitive list.
# Filter at load time to catch pre-1960s entries in older corpus files.
MIN_ARTIST_BEGIN_YEAR = 1960


_REQUIRED_FIELDS = ("mbid", "name", "tags")


@dataclass
class ArtistRow:
    mbid: str
    name: str
    sort_name: str = ""
    country: str = ""
    begin_year: int | None = None
    end_year: int | None = None
    tags: list[str] = field(default_factory=list)              # normalised tag strings
    tag_weights: list[int] = field(default_factory=list)       # aligned to tags
    listener_popularity: float = 0.0                            # 0..1 normalised
    # ── Spotify enrichment (Phase 2 / 2026-04). Optional so legacy
    # corpus files without these fields still load cleanly. Spotify
    # removed ``popularity`` and ``followers`` from artist objects in
    # Feb 2026 — only ``id`` + ``genres`` are populated now.
    spotify_id: str | None = None
    spotify_genres: list[str] = field(default_factory=list)
    # ── Track-level grounding (2026-04-27). Up to ~5 known released
    # tracks per artist, sourced either from corpus build (offline
    # enrichment) or a runtime overlay file. Empty list means: no
    # grounding available — Stage 3 must rely on parametric memory or
    # drop the artist (anti-confab clause).
    top_tracks: list[str] = field(default_factory=list)
    # ── Last.fm enrichment (Phase B / 2026-05). All optional so legacy
    # corpus files load cleanly. ``lastfm_tags`` and
    # ``lastfm_tag_weights`` are aligned lists (weight is 0-100 from
    # the Last.fm community-tag popularity score).
    lastfm_listeners: int | None = None
    lastfm_playcount: int | None = None
    lastfm_tags: list[str] = field(default_factory=list)
    lastfm_tag_weights: list[int] = field(default_factory=list)
    # ── AI controlled-vocabulary tags (2026-06). Merged at load time from
    # the ``ai_tags_overlay.json`` sibling file (same durable pattern as
    # top_tracks). The full set is kept here as metadata; only the
    # *discriminative* subset (genre/scene/vocal — see ai_vocab.py) is
    # indexed for retrieval, which densifies the sparse long tail (artists
    # with ≤1 MB tag become findable via their AI tags).
    ai_tags: list[str] = field(default_factory=list)


# Memoised: index build calls this ~2M times but only ~59k tag strings are
# unique (97% duplicates), so caching cuts index-build time ~70% at startup.
# Pure function → cache values are byte-identical to recomputation. The key
# space is bounded (corpus tags + runtime query tags), so an unbounded cache
# is fine and stays small.
@functools.lru_cache(maxsize=None)
def normalise_tag(tag: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace — match the index key."""
    if not tag:
        return ""
    s = unicodedata.normalize("NFKD", str(tag))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalise_name(name: str) -> str:
    """Match the key produced at index build time for deny-list filtering."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def artist_tag_weight(artist: "ArtistRow", qtag: str) -> int:
    """Resolve the per-artist weight for *qtag* across all tag sources.

    MB community tags carry their explicit ``tag_weights`` count.
    Spotify genres don't have per-artist weights so we treat them as
    constant weight 2 (slightly above an average MB tag, reflecting
    that Spotify-curated genres are higher signal than raw community
    tags). Last.fm tags carry a 0-100 community-popularity weight
    which we pass through directly — empirically it lines up well
    with MB tag-count magnitudes. Falls back to 1 if no match —
    defensive, should be unreachable since the index only points us
    at artists that have the tag somewhere.

    Lives here (not in retrieval) so the corpus can precompute a weight
    for every posting entry — see :meth:`RagCorpus.postings` and the
    SQLite corpus builder. ``retrieval`` re-exports it as
    ``_artist_tag_weight`` for backwards compatibility.
    """
    try:
        pos = artist.tags.index(qtag)
        return artist.tag_weights[pos] if pos < len(artist.tag_weights) else 1
    except ValueError:
        pass
    # Last.fm tags are stored normalised already (driver lowercases),
    # so a direct equality is enough — and faster than a per-tag
    # normalise call for the spotify_genres branch below.
    try:
        pos = artist.lastfm_tags.index(qtag)
        return (artist.lastfm_tag_weights[pos]
                if pos < len(artist.lastfm_tag_weights) else 1)
    except ValueError:
        pass
    # Check Spotify genres (normalised match — corpus stores them raw).
    for g in artist.spotify_genres:
        if normalise_tag(g) == qtag:
            return 2
    # AI controlled-vocab tags (only the discriminative subset is indexed,
    # so reaching here means the artist was surfaced via its AI tag — common
    # for sparse tail artists with no usable MB/Last.fm tags). Curated
    # controlled vocabulary → solid constant signal, on par with Spotify.
    for at in artist.ai_tags:
        if normalise_tag(at) == qtag:
            return 2
    return 1


class RagCorpus:
    """In-memory artist corpus with tag inverted index + TF-IDF weights.

    Load once at app startup with :meth:`load` and keep alive for the
    lifetime of the process. Read-only after construction.
    """

    def __init__(self, artists: list[ArtistRow], aliases: dict[str, str] | None = None):
        self.artists: list[ArtistRow] = artists
        self.by_mbid: dict[str, int] = {}
        self.by_name_normalised: dict[str, int] = {}
        self.tag_index: dict[str, list[int]] = {}
        self.tag_idf: dict[str, float] = {}
        self.aliases: dict[str, str] = {normalise_tag(k): normalise_tag(v)
                                        for k, v in (aliases or {}).items()}
        # Lazy per-tag posting weights (idx-aligned to tag_index[tag]).
        # Computed on first postings() access and cached — keeps startup fast
        # while letting the scoring loop avoid re-deriving weights per query.
        self._posting_weights: dict[str, list[int]] = {}
        self._build_indices()

    # ── construction ────────────────────────────────────────────────

    def _build_indices(self) -> None:
        n_docs = max(1, len(self.artists))
        doc_freq: dict[str, int] = {}
        for idx, a in enumerate(self.artists):
            if a.mbid:
                self.by_mbid[a.mbid] = idx
            nkey = normalise_name(a.name)
            if nkey and nkey not in self.by_name_normalised:
                self.by_name_normalised[nkey] = idx
            seen_tags: set[str] = set()
            # Index MB community tags
            for t in a.tags:
                nt = normalise_tag(t)
                if not nt or nt in seen_tags:
                    continue
                seen_tags.add(nt)
                self.tag_index.setdefault(nt, []).append(idx)
            # Phase 2: also index Spotify genres so the retriever matches
            # them too. Spotify genres are denser & more standard than MB
            # community tags, so this is the primary precision boost.
            for g in a.spotify_genres:
                ng = normalise_tag(g)
                if not ng or ng in seen_tags:
                    continue
                seen_tags.add(ng)
                self.tag_index.setdefault(ng, []).append(idx)
            # Phase B: index Last.fm tags. They carry their own 0-100
            # weight (read in _artist_tag_weight) and dominate community
            # consensus where MB community tags are sparse.
            for lt in a.lastfm_tags:
                nlt = normalise_tag(lt)
                if not nlt or nlt in seen_tags:
                    continue
                seen_tags.add(nlt)
                self.tag_index.setdefault(nlt, []).append(idx)
            # AI controlled-vocab tags: index only the DISCRIMINATIVE ones
            # (genre/scene/vocal). Generic mood/rhythm/era/instrumentation
            # AI tags are excluded (GENERIC_AI_TAGS) — they bloat posting
            # lists and dilute precision. This is the densification step:
            # tail artists with no usable MB/Last.fm tags become findable
            # via their AI tags.
            for at in a.ai_tags:
                nat = normalise_tag(at)
                if not nat or nat in seen_tags or nat in GENERIC_AI_TAGS:
                    continue
                seen_tags.add(nat)
                self.tag_index.setdefault(nat, []).append(idx)
            for nt in seen_tags:
                doc_freq[nt] = doc_freq.get(nt, 0) + 1

        for tag, df in doc_freq.items():
            # Smoothed IDF; +1 keeps very common tags from going negative.
            self.tag_idf[tag] = math.log((n_docs + 1) / (df + 1)) + 1.0

    # ── loading ─────────────────────────────────────────────────────

    @classmethod
    def load(cls, corpus_path: str | Path,
             aliases_path: str | Path | None = None,
             top_tracks_overlay_path: str | Path | None = None) -> "RagCorpus":
        """Load a `.jsonl.gz` corpus + optional `tag_aliases.json`.

        Raises FileNotFoundError if *corpus_path* is missing. The aliases
        file is optional — retrieval still works without it, just with
        fewer synonym hits.

        *top_tracks_overlay_path* is an optional JSON file mapping
        ``mbid → list[str]`` (up to ~5 track titles per artist). When
        provided, its entries are merged onto matching ``ArtistRow``
        objects after corpus load. The overlay is the runtime path for
        track-level grounding while the corpus enrichment job catches up;
        once tracks are baked into the corpus itself, this overlay layer
        becomes a no-op for those artists. If not specified, the loader
        auto-detects ``top_tracks_overlay.json`` next to *corpus_path*.
        """
        corpus_path = Path(corpus_path)
        if not corpus_path.exists():
            raise FileNotFoundError(f"RAG corpus not found: {corpus_path}")

        artists = list(cls._iter_rows(corpus_path))
        aliases: dict[str, str] = {}
        if aliases_path:
            ap = Path(aliases_path)
            if ap.exists():
                try:
                    aliases = json.loads(ap.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning("Ignoring unreadable tag_aliases at %s: %s", ap, exc)
            else:
                logger.info("No tag_aliases at %s — running without synonyms.", ap)

        # Auto-detect overlay next to the corpus file if not explicitly given.
        if top_tracks_overlay_path is None:
            candidate = corpus_path.parent / "top_tracks_overlay.json"
            if candidate.exists():
                top_tracks_overlay_path = candidate

        n_overlay_merged = 0
        if top_tracks_overlay_path:
            op = Path(top_tracks_overlay_path)
            if op.exists():
                try:
                    overlay = json.loads(op.read_text(encoding="utf-8"))
                    if isinstance(overlay, dict):
                        # Index artists by mbid for O(1) merge
                        by_mbid_local: dict[str, ArtistRow] = {a.mbid: a for a in artists if a.mbid}
                        for mbid, tracks in overlay.items():
                            if not isinstance(tracks, list):
                                continue
                            row = by_mbid_local.get(str(mbid))
                            if row is None:
                                continue
                            row.top_tracks = [str(t) for t in tracks if t]
                            n_overlay_merged += 1
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning("Ignoring unreadable top_tracks overlay at %s: %s", op, exc)

        # AI-tags overlay — same durable sibling-file pattern as top_tracks.
        # Auto-detected next to the corpus; survives Cloud Run base rebuilds
        # because it lives in its own file. Merged by mbid BEFORE indices are
        # built so the discriminative AI tags are indexed (see _build_indices).
        n_ai_merged = 0
        ai_overlay_path = corpus_path.parent / "ai_tags_overlay.json"
        if ai_overlay_path.exists():
            try:
                ai_doc = json.loads(ai_overlay_path.read_text(encoding="utf-8"))
                ai_entries = (ai_doc.get("entries") if isinstance(ai_doc, dict)
                              else None) or (ai_doc if isinstance(ai_doc, dict) else {})
                if isinstance(ai_entries, dict):
                    by_mbid_ai: dict[str, ArtistRow] = {a.mbid: a for a in artists if a.mbid}
                    for mbid, entry in ai_entries.items():
                        if not isinstance(entry, dict):
                            continue
                        row = by_mbid_ai.get(str(mbid))
                        if row is None:
                            continue
                        tags = entry.get("ai_tags") or []
                        if tags:
                            row.ai_tags = [str(t) for t in tags if t]
                            n_ai_merged += 1
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Ignoring unreadable ai_tags overlay at %s: %s",
                               ai_overlay_path, exc)

        n_enriched = sum(1 for a in artists if a.spotify_id)
        n_with_tracks = sum(1 for a in artists if a.top_tracks)
        logger.info("RagCorpus loaded: %d artists, %d enriched (%.1f%%), %d with top_tracks (%d from overlay), %d with ai_tags, %d aliases",
                    len(artists), n_enriched,
                    100.0 * n_enriched / max(1, len(artists)),
                    n_with_tracks, n_overlay_merged, n_ai_merged,
                    len(aliases))
        return cls(artists, aliases)

    @staticmethod
    def _is_gzipped(path: Path) -> bool:
        """Return True when the file's magic bytes are gzip's ``1f 8b``.

        Cloud Run gsutil sync has been observed to write raw JSONL
        under an ``.jsonl.gz`` filename (no recompression on download).
        Trusting the suffix alone explodes the loader with
        ``BadGzipFile`` even though the payload is perfectly valid
        JSONL. Read the first two bytes once and decide for real.
        """
        try:
            with open(path, "rb") as fh:
                magic = fh.read(2)
            return magic == b"\x1f\x8b"
        except OSError:
            return False

    @staticmethod
    def _iter_rows(path: Path) -> Iterable[ArtistRow]:
        opener = gzip.open if RagCorpus._is_gzipped(path) else open
        with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[arg-type]
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping bad JSONL line %d: %s", line_no, exc)
                    continue
                if not all(raw.get(f) is not None for f in _REQUIRED_FIELDS):
                    continue
                # Filter pre-1960s artists at load time (safety net for old corpus files)
                by = raw.get("begin_year")
                if by is not None and by < MIN_ARTIST_BEGIN_YEAR:
                    continue
                tags = raw.get("tags") or []
                weights = raw.get("tag_weights") or []
                if len(weights) < len(tags):
                    weights = list(weights) + [1] * (len(tags) - len(weights))
                # Last.fm tags arrive as [[name, weight], ...]. Split into
                # parallel lists so the retrieval helpers can do an O(1)
                # weight lookup the same way they do for MB tags.
                lastfm_tag_pairs = raw.get("lastfm_tags") or []
                lastfm_names: list[str] = []
                lastfm_weights: list[int] = []
                for entry in lastfm_tag_pairs:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        name, weight = entry[0], entry[1]
                        if not name:
                            continue
                        try:
                            w_int = int(weight)
                        except (TypeError, ValueError):
                            w_int = 1
                        lastfm_names.append(str(name))
                        lastfm_weights.append(w_int)
                yield ArtistRow(
                    mbid=str(raw["mbid"]),
                    name=str(raw["name"]),
                    sort_name=str(raw.get("sort_name") or ""),
                    country=str(raw.get("country") or ""),
                    begin_year=raw.get("begin_year"),
                    end_year=raw.get("end_year"),
                    tags=[str(t) for t in tags],
                    tag_weights=[int(w) if w is not None else 1 for w in weights[:len(tags)]],
                    listener_popularity=float(raw.get("listener_popularity") or 0.0),
                    spotify_id=(str(raw["spotify_id"]) if raw.get("spotify_id") else None),
                    spotify_genres=[str(g) for g in (raw.get("spotify_genres") or [])],
                    top_tracks=[str(t) for t in (raw.get("top_tracks") or []) if t],
                    lastfm_listeners=(int(raw["lastfm_listeners"])
                                       if raw.get("lastfm_listeners") is not None else None),
                    lastfm_playcount=(int(raw["lastfm_playcount"])
                                       if raw.get("lastfm_playcount") is not None else None),
                    lastfm_tags=lastfm_names,
                    lastfm_tag_weights=lastfm_weights,
                    ai_tags=[str(t) for t in (raw.get("ai_tags") or []) if t],
                )

    # ── retrieval-scoring access ────────────────────────────────────

    def postings(self, tag: str) -> tuple[float, list[int], list[int]]:
        """Return ``(idf, artist_indices, weights)`` for *tag*.

        ``weights`` are aligned to ``artist_indices`` and equal
        ``artist_tag_weight(artists[idx], tag)`` for each posting — computed
        once and cached. This lets the scoring loop accumulate scores from
        pure ints without materialising ArtistRow objects, and is the exact
        shape the SQLite corpus serves from disk. Returns empties for an
        unknown tag (idf defaults to 1.0, matching the old
        ``tag_idf.get(tag, 1.0)``).
        """
        idxs = self.tag_index.get(tag)
        if not idxs:
            return 1.0, [], []
        weights = self._posting_weights.get(tag)
        if weights is None:
            weights = [artist_tag_weight(self.artists[i], tag) for i in idxs]
            self._posting_weights[tag] = weights
        return self.tag_idf.get(tag, 1.0), idxs, weights

    # ── lookup helpers ──────────────────────────────────────────────

    def resolve_alias(self, tag: str) -> str:
        """Map a raw tag to its canonical form; returns the input if unknown."""
        nt = normalise_tag(tag)
        return self.aliases.get(nt, nt)

    def __len__(self) -> int:
        return len(self.artists)
