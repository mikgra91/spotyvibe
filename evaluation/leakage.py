"""Post-feedback leakage detection for the eval harness.

Replaces text-based ``has_must_have_cite`` as the primary quality signal
(F8). After the harness applies likes and
dislikes and re-trains the profile, it generates a SECOND playlist on
the same profile state. ``compute_leakage`` then audits that playlist
against the profile's hard exclusion lists:

  - **rejected_artist** — track artist appears in
    ``profile.artists.rejected`` (any source: manual, F4 auto-escalation).
  - **disliked_track** — exact ``(artist, track)`` matches an entry in
    ``profile.feedback.disliked_tracks`` from the prior playlist.
  - **dislike_pattern** — track artist has ≥
    ``DISLIKE_PATTERN_THRESHOLD`` distinct disliked tracks recorded for
    them — i.e. would have been F4-auto-rejected if the track-level
    feedback had been processed in production. This catches the "did
    F4 escalation actually plumb through to playlist-B?" question
    independently of when in the run F4 fired.

A non-zero count for ANY category means the production code failed to
respect prior feedback when generating playlist B. That is the
definition of a quality regression for this app.

Returns a structured :class:`LeakageReport` so the harness can persist
counts to ``summary.json`` and the reporting module can surface them
in ``comparison.md``. The report is JSON-serialisable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Threshold mirrors ``feedback.DISLIKE_AUTO_REJECT_THRESHOLD`` (F4): if the
# user track-disliked this many distinct tracks for an artist, that
# artist should not reappear in the next playlist regardless of whether
# F4 successfully wrote the artist to ``artists.rejected``.
DISLIKE_PATTERN_THRESHOLD = 3


def _norm(name: str | None) -> str:
    """Case-insensitive, whitespace-trimmed key for artist/track matching.

    Same normalisation rule used by ``feedback.dislike_track`` and
    ``suggestions.collect_forbidden_artists`` so leakage matches the
    production reader's view of "same artist".
    """
    return (name or "").lower().strip()


@dataclass
class LeakageHit:
    """One leaked track in playlist B with the rule that flagged it.

    ``rule`` is one of ``rejected_artist`` / ``disliked_track`` /
    ``dislike_pattern``. ``detail`` carries human-readable context for
    the report (e.g. the manual-rejection reason or the prior dislike
    count).
    """
    artist: str
    track: str
    rule: str
    detail: str = ""


@dataclass
class LeakageReport:
    """Aggregate leakage finding for one playlist-B generation.

    The harness writes this to ``summary.json`` so the reporting module
    can roll counts up across model runs. ``passed`` is True iff every
    rule found zero hits — i.e. playlist B fully respected prior
    feedback. Use that as the single boolean quality gate.
    """
    rejected_artist_count: int = 0
    disliked_track_count: int = 0
    dislike_pattern_count: int = 0
    total_tracks: int = 0
    hits: list[LeakageHit] = field(default_factory=list)

    @property
    def total_leaks(self) -> int:
        return (
            self.rejected_artist_count
            + self.disliked_track_count
            + self.dislike_pattern_count
        )

    @property
    def passed(self) -> bool:
        return self.total_leaks == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "rejected_artist_count": self.rejected_artist_count,
            "disliked_track_count": self.disliked_track_count,
            "dislike_pattern_count": self.dislike_pattern_count,
            "total_leaks": self.total_leaks,
            "total_tracks": self.total_tracks,
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


def compute_leakage(tracks: list[dict], profile: dict) -> LeakageReport:
    """Audit *tracks* (playlist B) against *profile*'s feedback state.

    *tracks* is the list of track dicts returned by the production
    pipeline — same shape as the playlist-A result (each entry has
    ``artist`` and ``track`` string fields).

    *profile* is the post-feedback profile snapshot (i.e. after
    ``feedback.like_track`` / ``dislike_track`` calls and the optional
    refine ``train_profile`` call). The function reads:

      - ``artists.rejected`` for the rejected-artist gate
      - ``feedback.disliked_tracks`` for both the exact-track gate and
        the dislike-pattern gate (≥ ``DISLIKE_PATTERN_THRESHOLD``
        distinct disliked tracks per artist)

    Multiple rules can fire on the same track (e.g. a manually rejected
    artist whose prior track was also disliked); each fires as a
    separate :class:`LeakageHit` so the harness report shows the full
    picture. Counts are by-rule, not de-duplicated.
    """
    if not isinstance(profile, dict):
        return LeakageReport(total_tracks=len(tracks or []))

    artists_block = profile.get("artists") or {}
    rejected_entries = artists_block.get("rejected") or []

    # Map of {normalised_name: rejection_detail}
    rejected_index: dict[str, str] = {}
    for entry in rejected_entries:
        if isinstance(entry, dict):
            name = entry.get("name") or ""
            reason = entry.get("reason") or ""
            auto_flag = " (auto)" if entry.get("auto") else ""
            detail = f"{reason}{auto_flag}".strip() or "no reason recorded"
        else:
            name = str(entry)
            detail = "legacy bare-string entry"
        if name:
            rejected_index[_norm(name)] = detail

    disliked_tracks_raw = (profile.get("feedback") or {}).get("disliked_tracks") or []

    # Map of {(norm_artist, norm_track): reason}
    disliked_index: dict[tuple[str, str], str] = {}
    # Map of {norm_artist: set(norm_track)} for dislike-pattern detection
    artist_dislike_count: dict[str, set[str]] = {}
    for entry in disliked_tracks_raw:
        if not isinstance(entry, dict):
            continue
        a_norm = _norm(entry.get("artist"))
        t_norm = _norm(entry.get("track"))
        if not a_norm:
            continue
        if t_norm:
            disliked_index[(a_norm, t_norm)] = (entry.get("reason") or "").strip()
            artist_dislike_count.setdefault(a_norm, set()).add(t_norm)

    report = LeakageReport(total_tracks=len(tracks or []))
    for t in tracks or []:
        if not isinstance(t, dict):
            continue
        artist = t.get("artist") or ""
        track = t.get("track") or ""
        a_norm = _norm(artist)
        t_norm = _norm(track)
        if not a_norm:
            continue

        # Rule 1 — rejected artist
        if a_norm in rejected_index:
            report.rejected_artist_count += 1
            report.hits.append(LeakageHit(
                artist=artist, track=track, rule="rejected_artist",
                detail=rejected_index[a_norm],
            ))

        # Rule 2 — exact disliked (artist, track) reappears
        if t_norm and (a_norm, t_norm) in disliked_index:
            report.disliked_track_count += 1
            reason = disliked_index[(a_norm, t_norm)] or "no reason recorded"
            report.hits.append(LeakageHit(
                artist=artist, track=track, rule="disliked_track",
                detail=f"prior reason: {reason}",
            ))

        # Rule 3 — artist with ≥ THRESHOLD distinct disliked tracks. Skip
        # when the artist is already counted as rejected (avoid
        # redundant hits on the same artist; the rejected-artist rule is
        # the stronger signal).
        prior_count = len(artist_dislike_count.get(a_norm, set()))
        if (
            a_norm not in rejected_index
            and prior_count >= DISLIKE_PATTERN_THRESHOLD
        ):
            report.dislike_pattern_count += 1
            report.hits.append(LeakageHit(
                artist=artist, track=track, rule="dislike_pattern",
                detail=f"{prior_count} distinct prior dislikes for this artist",
            ))

    if report.total_leaks:
        logger.warning(
            "Leakage detected on playlist-B: %d rejected_artist, "
            "%d disliked_track, %d dislike_pattern (over %d tracks)",
            report.rejected_artist_count,
            report.disliked_track_count,
            report.dislike_pattern_count,
            report.total_tracks,
        )
    return report


__all__ = [
    "DISLIKE_PATTERN_THRESHOLD",
    "LeakageHit",
    "LeakageReport",
    "compute_leakage",
]
