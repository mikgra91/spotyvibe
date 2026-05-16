"""Heuristic matching of MusicBrainz artists to Spotify artists.

Goal: for each MB artist, decide which (if any) Spotify search result
is the same artist. Conservative — better to skip enrichment than to
mis-attribute (a wrong genre list would actively poison retrieval).

Score components:
- exact normalised-name match: +1.0
- year proximity (|diff| ≤ 3): +0.5
- shared MB tag ↔ Spotify genre: +0.1 each (capped at +0.5)

Acceptance threshold: ``MIN_MATCH_SCORE`` (1.0 by default).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Confidence threshold for accepting a Spotify match. 1.0 is the
# minimum payload of "exact name match" — anything below means the
# names differ and we shouldn't trust it.
MIN_MATCH_SCORE = 1.0

# Cap shared-tag bonus so a generic "rock" overlap can't push a wrong
# match across the threshold on its own.
_MAX_TAG_BONUS = 0.5

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


@dataclass
class MatchCandidate:
    spotify_id: str
    name: str
    genres: list[str]
    score: float


def normalise_artist_name(name: str) -> str:
    """Lowercase, strip diacritics + punctuation, collapse whitespace."""
    if not name:
        return ""
    # NFKD splits combined chars (é → e + ́ ); we drop combining marks.
    decomposed = unicodedata.normalize("NFKD", name)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = no_marks.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", no_punct).strip()


def score_candidate(*,
                    mb_name: str,
                    mb_begin_year: int | None,
                    mb_tags: list[str],
                    sp_name: str,
                    sp_genres: list[str],
                    sp_first_release_year: int | None = None) -> float:
    """Return a confidence score for a single Spotify candidate."""
    score = 0.0

    if normalise_artist_name(mb_name) == normalise_artist_name(sp_name):
        score += 1.0

    if mb_begin_year is not None and sp_first_release_year is not None:
        if abs(mb_begin_year - sp_first_release_year) <= 3:
            score += 0.5

    if mb_tags and sp_genres:
        mb_set = {normalise_artist_name(t) for t in mb_tags if t}
        sp_set = {normalise_artist_name(g) for g in sp_genres if g}
        overlap = len(mb_set & sp_set)
        score += min(_MAX_TAG_BONUS, 0.1 * overlap)

    return round(score, 3)


def pick_best_match(mb_name: str,
                    mb_begin_year: int | None,
                    mb_tags: list[str],
                    candidates: list[dict]) -> MatchCandidate | None:
    """Score Spotify search-result *candidates* and return the best one.

    *candidates* are raw Spotify ``artists.items`` dicts from
    ``/v1/search``. Returns ``None`` if none clear ``MIN_MATCH_SCORE``.

    Note: Spotify search results don't carry a ``first_release_year``
    field. We pass ``None`` for the year-proximity check unless a caller
    has fetched the artist's discography (currently we don't, to save
    API calls — the name + genre signals are enough for most cases).
    """
    best: MatchCandidate | None = None
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        sp_id = str(raw.get("id") or "")
        if not sp_id:
            continue
        sp_name = str(raw.get("name") or "")
        sp_genres = [str(g) for g in (raw.get("genres") or [])]

        s = score_candidate(
            mb_name=mb_name,
            mb_begin_year=mb_begin_year,
            mb_tags=mb_tags,
            sp_name=sp_name,
            sp_genres=sp_genres,
            sp_first_release_year=None,
        )
        if best is None or s > best.score:
            best = MatchCandidate(
                spotify_id=sp_id,
                name=sp_name,
                genres=sp_genres,
                score=s,
            )
    if best is None or best.score < MIN_MATCH_SCORE:
        return None
    return best

