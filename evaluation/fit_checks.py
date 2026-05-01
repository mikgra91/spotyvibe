"""Deterministic per-track fit-checks for the eval harness.

Where :mod:`evaluation.leakage` answers "did production respect prior
feedback?" these checks answer "does each track on playlist B actually
honour the profile's hard constraints, even ones never expressed as a
dislike?". They run on the same playlist B and use the same track-dict
shape (``artist`` / ``track`` / ``release_year`` / ``release_date``).

The first shipped check is :class:`DecadeAvoidCheck`. The user's
failure profile contains ``80s production style`` in the avoid block.
The model continued recommending 80s-era artists because nothing in
the pipeline reads the avoid prose for era constraints. This check
mines decade tokens out of the avoid prose (``80s`` / ``1980s``
synonyms) and audits each track's Spotify-reported album release year
against them. Tracks with no ``release_year`` are given the benefit of
the doubt — same convention as the production emerging-only filter
(``playlist.py:_parse_release_year``).

Future checks can extend the same pattern (Japanese-script verification,
country-of-origin, etc) without changing the harness wiring.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Decade prose → numeric range. Both short (`80s`) and long (`1980s`)
# forms appear in user prose; map both to the same decade tuple.
_DECADE_PROSE: dict[str, tuple[int, int]] = {
    "60s": (1960, 1969),
    "1960s": (1960, 1969),
    "70s": (1970, 1979),
    "1970s": (1970, 1979),
    "80s": (1980, 1989),
    "1980s": (1980, 1989),
    "90s": (1990, 1999),
    "1990s": (1990, 1999),
    "00s": (2000, 2009),
    "2000s": (2000, 2009),
    "10s": (2010, 2019),
    "2010s": (2010, 2019),
    "20s": (2020, 2029),
    "2020s": (2020, 2029),
}


@dataclass
class FitHit:
    """One track that failed a fit-check, with rule + detail context."""
    artist: str
    track: str
    rule: str
    detail: str = ""


@dataclass
class FitReport:
    """Aggregate fit-check finding for one playlist-B generation.

    *checks_applied* lists the checks that decided to apply on this
    profile (e.g. DecadeAvoidCheck only applies if the avoid prose
    contains a decade keyword). When ``checks_applied`` is empty the
    report is informational only — *passed* is still True.
    """
    decade_avoid_count: int = 0
    total_tracks: int = 0
    checks_applied: list[str] = field(default_factory=list)
    hits: list[FitHit] = field(default_factory=list)

    @property
    def total_fails(self) -> int:
        return self.decade_avoid_count

    @property
    def passed(self) -> bool:
        return self.total_fails == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "decade_avoid_count": self.decade_avoid_count,
            "total_fails": self.total_fails,
            "total_tracks": self.total_tracks,
            "checks_applied": list(self.checks_applied),
            "passed": self.passed,
            "hits": [
                {
                    "artist": h.artist,
                    "track": h.track,
                    "rule": h.rule,
                    "detail": h.detail,
                }
                for h in self.hits
            ],
        }


def _avoid_prose(profile: dict) -> str:
    """Concatenate the user's avoid prose into a single lower-case string.

    Handles both list-of-strings and bare-string forms — same shape
    contract as ``preferences.avoid`` consumers in
    ``rag/retrieval.py`` and ``suggestions.py``.
    """
    prefs = (profile or {}).get("preferences") or {}
    avoid = prefs.get("avoid")
    if isinstance(avoid, str):
        return avoid.lower()
    if isinstance(avoid, list):
        return " | ".join(s.lower() for s in avoid if isinstance(s, str))
    return ""


def _avoided_decades(profile: dict) -> list[tuple[int, int]]:
    """Mine decade ranges out of the avoid prose.

    Returns a list of ``(start_year, end_year)`` tuples. Empty list when
    the avoid prose mentions no decade — DecadeAvoidCheck then becomes
    a no-op for this profile (recorded as not-applied).
    """
    text = _avoid_prose(profile)
    if not text:
        return []
    found: set[tuple[int, int]] = set()
    # Match short forms only when bracketed by non-digit chars so we
    # don't catch the `80` in `1980` twice.
    for prose, decade in _DECADE_PROSE.items():
        if len(prose) <= 3:
            # short form — guard against substring of long form
            pattern = rf"(?<!\d){re.escape(prose)}(?!\d)"
        else:
            pattern = re.escape(prose)
        if re.search(pattern, text):
            found.add(decade)
    return sorted(found)


def _track_release_year(track: dict) -> int | None:
    """Extract the release year from a track dict.

    Prefers ``release_year`` (already parsed by the production code) and
    falls back to a 4-digit prefix of ``release_date``. Returns None
    when neither is present — the caller treats unknown years as a pass
    so the harness never penalises legitimate metadata gaps.
    """
    if not isinstance(track, dict):
        return None
    yr = track.get("release_year")
    if isinstance(yr, int):
        return yr
    rd = track.get("release_date")
    if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
        try:
            return int(rd[:4])
        except ValueError:
            return None
    return None


def compute_fit(tracks: list[dict], profile: dict) -> FitReport:
    """Run every applicable fit-check on *tracks* against *profile*.

    Currently only the DecadeAvoidCheck ships. Future checks slot in
    by extending this function with their own apply/evaluate steps.
    """
    report = FitReport(total_tracks=len(tracks or []))

    # DecadeAvoidCheck — applies only if avoid prose mentions a decade.
    decades = _avoided_decades(profile)
    if decades:
        report.checks_applied.append("decade_avoid")
        for t in tracks or []:
            if not isinstance(t, dict):
                continue
            artist = t.get("artist") or ""
            track = t.get("track") or ""
            # Skip malformed entries — same convention as leakage.py.
            # An empty artist is not a meaningful playlist row; counting
            # it as a fit-check fail would mask real failures.
            if not (artist or "").strip():
                continue
            year = _track_release_year(t)
            if year is None:
                continue  # unknown year → benefit of the doubt
            for start, end in decades:
                if start <= year <= end:
                    report.decade_avoid_count += 1
                    report.hits.append(FitHit(
                        artist=artist, track=track, rule="decade_avoid",
                        detail=f"release_year={year} falls in avoided "
                               f"{start}s decade",
                    ))
                    break  # one hit per track is enough

    if report.total_fails:
        logger.warning(
            "Fit-check failures on playlist-B: %d decade_avoid "
            "(over %d tracks, checks=%s)",
            report.decade_avoid_count, report.total_tracks,
            ", ".join(report.checks_applied) or "(none)",
        )
    return report


__all__ = [
    "FitHit",
    "FitReport",
    "compute_fit",
]
