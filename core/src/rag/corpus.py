"""In-memory artist corpus for RAG retrieval.

Loads a `.jsonl.gz` MusicBrainz-derived artist file plus a tag-alias map,
builds inverted tag indices and TF-IDF statistics, and exposes the result
as a ``RagCorpus`` object. Pure Python — no numpy dependency.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

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
    # ── Spotify enrichment (Phase 2 / 2026-04). All optional so legacy
    # corpus files without these fields still load cleanly.
    spotify_id: str | None = None
    spotify_popularity: int | None = None     # 0..100 from Spotify
    spotify_followers: int | None = None
    spotify_genres: list[str] = field(default_factory=list)


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
            for nt in seen_tags:
                doc_freq[nt] = doc_freq.get(nt, 0) + 1

        for tag, df in doc_freq.items():
            # Smoothed IDF; +1 keeps very common tags from going negative.
            self.tag_idf[tag] = math.log((n_docs + 1) / (df + 1)) + 1.0

    # ── loading ─────────────────────────────────────────────────────

    @classmethod
    def load(cls, corpus_path: str | Path,
             aliases_path: str | Path | None = None) -> "RagCorpus":
        """Load a `.jsonl.gz` corpus + optional `tag_aliases.json`.

        Raises FileNotFoundError if *corpus_path* is missing. The aliases
        file is optional — retrieval still works without it, just with
        fewer synonym hits.
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

        n_enriched = sum(1 for a in artists if a.spotify_id)
        logger.info("RagCorpus loaded: %d artists, %d enriched (%.1f%%), %d aliases",
                    len(artists), n_enriched,
                    100.0 * n_enriched / max(1, len(artists)),
                    len(aliases))
        return cls(artists, aliases)

    @staticmethod
    def _iter_rows(path: Path) -> Iterable[ArtistRow]:
        opener = gzip.open if path.suffix == ".gz" else open
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
                    spotify_popularity=(int(raw["spotify_popularity"])
                                        if raw.get("spotify_popularity") is not None else None),
                    spotify_followers=(int(raw["spotify_followers"])
                                       if raw.get("spotify_followers") is not None else None),
                    spotify_genres=[str(g) for g in (raw.get("spotify_genres") or [])],
                )

    # ── lookup helpers ──────────────────────────────────────────────

    def resolve_alias(self, tag: str) -> str:
        """Map a raw tag to its canonical form; returns the input if unknown."""
        nt = normalise_tag(tag)
        return self.aliases.get(nt, nt)

    def __len__(self) -> int:
        return len(self.artists)
