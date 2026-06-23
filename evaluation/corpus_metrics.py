"""Last.fm-aware coverage metrics for the eval harness (E2 / E3).

After Phase B enrichment shipped (corpus 2026-05-06, 83.6 % Last.fm
listener coverage / 66.6 % weighted-tag coverage), the eval harness
needs to surface whether those signals actually flow through to the
final playlist. Without this:

  - **E2 — tag coverage**: a corpus regression that drops `lastfm_tags`
    or a retrieval bug that picks unenriched rows is invisible — the
    legacy must_have_cite metric only knows about MB tags.
  - **E3 — listener-popularity distribution**: there is no signal for
    the "all-mainstream vs all-niche" axis. The new `niche_only_strict`
    scenario relies on this metric for its acceptance check.

The metric is computed against the production corpus by looking up each
playlist track's artist via :meth:`RagCorpus.by_name_normalised`. Tracks
whose artist is not in the corpus are counted as "unmatched" and
excluded from the coverage / popularity rollups (so a small number of
Spotify-only artists can't skew the metric to either extreme).

The resulting :class:`CorpusMetricsReport` is JSON-serialisable so the
harness can persist it on ``ModelRunResult`` and the reporting module
can emit a table in ``comparison.md``.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# E2 acceptance gate per next-steps.md "Post-Phase B agenda → E":
# corpus-level Last.fm tag coverage is 66.6 %; the popularity-weighted
# retriever biases toward enriched rows, so the per-playlist coverage
# is expected to land at ≥ 75 %. Below this is a silent regression.
LASTFM_TAG_COVERAGE_GATE = 0.75

# E5 (lastfm-aware niche scenario) acceptance gate. p95 listener count
# above this means the retrieval failed to de-bias from popularity.
NICHE_LISTENER_P95_GATE = 100_000


@dataclass
class CorpusMetricsReport:
    """One playlist's Last.fm-aware coverage rollup.

    All ``*_count`` fields are absolute counts; ``*_pct`` fields are
    floats in [0, 1]. ``listeners_*`` are taken over tracks whose
    artist matched the corpus AND has a non-None ``lastfm_listeners``
    value — None / missing entries are excluded so a single zero-row
    can't drag the median to 0.
    """
    total_tracks: int = 0
    matched_in_corpus: int = 0
    lastfm_tag_populated: int = 0
    lastfm_tag_coverage_pct: float | None = None
    lastfm_listeners_median: int | None = None
    lastfm_listeners_p95: int | None = None
    lastfm_listeners_sample_size: int = 0

    @property
    def passed_tag_coverage(self) -> bool:
        """E2 gate: ≥ ``LASTFM_TAG_COVERAGE_GATE`` (75 % by default).

        Returns True when the metric isn't measurable yet (no tracks)
        so an empty playlist doesn't double-count as a coverage failure
        — the playlist-completion gate already catches that case.
        """
        if self.lastfm_tag_coverage_pct is None:
            return True
        return self.lastfm_tag_coverage_pct >= LASTFM_TAG_COVERAGE_GATE

    def to_json(self) -> dict[str, Any]:
        return {
            "total_tracks": self.total_tracks,
            "matched_in_corpus": self.matched_in_corpus,
            "lastfm_tag_populated": self.lastfm_tag_populated,
            "lastfm_tag_coverage_pct": (
                round(self.lastfm_tag_coverage_pct, 3)
                if self.lastfm_tag_coverage_pct is not None else None
            ),
            "lastfm_listeners_median": self.lastfm_listeners_median,
            "lastfm_listeners_p95": self.lastfm_listeners_p95,
            "lastfm_listeners_sample_size": self.lastfm_listeners_sample_size,
            "passed_tag_coverage": self.passed_tag_coverage,
        }


def _percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile; safe for tiny samples (n < 20).

    ``statistics.quantiles`` requires n ≥ 2 and uses an interpolation
    method that's overkill for our 15-track playlists. Nearest-rank
    matches what users intuitively expect when they read "p95" off a
    short list.
    """
    if not values:
        raise ValueError("percentile of empty list")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    # Nearest-rank: ceil(pct * n) — 1-indexed to 0-indexed
    rank = max(1, int(round(pct * len(s) + 0.5)) - 1)
    rank = min(rank, len(s) - 1)
    return s[rank]


def compute_corpus_metrics(tracks: list[dict], corpus: Any | None) -> CorpusMetricsReport:
    """Roll up Last.fm coverage + listener distribution for *tracks*.

    *corpus* is a :class:`core.src.rag.corpus.RagCorpus` instance (or
    None when RAG is disabled / the corpus failed to load — in that case
    the harness still produces a report, just with everything in the
    "unmatched" bucket so the metric clearly degrades to "unknown").

    *tracks* is the production-shape playlist (list of dicts each with
    at least an ``artist`` field). Missing / blank artist entries are
    skipped silently — they don't count toward total_tracks either, so
    the coverage % stays meaningful.
    """
    report = CorpusMetricsReport()

    if not tracks:
        return report

    # Late import keeps this module importable from contexts that don't
    # have the RAG package on the path (e.g. ad-hoc scripts).
    try:
        from core.src.rag.corpus import normalise_name
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("[corpus_metrics] cannot import normalise_name: %s", exc)
        return report

    listeners: list[int] = []
    for t in tracks:
        if not isinstance(t, dict):
            continue
        artist = (t.get("artist") or "").strip()
        if not artist:
            continue
        report.total_tracks += 1
        if corpus is None:
            continue
        idx = corpus.by_name_normalised.get(normalise_name(artist))
        if idx is None:
            continue
        row = corpus.artists[idx]
        report.matched_in_corpus += 1
        if getattr(row, "lastfm_tags", None):
            report.lastfm_tag_populated += 1
        listeners_val = getattr(row, "lastfm_listeners", None)
        if isinstance(listeners_val, int) and listeners_val > 0:
            listeners.append(listeners_val)

    if report.total_tracks > 0 and report.matched_in_corpus > 0:
        # Coverage is over MATCHED tracks (the question E2 actually
        # asks: of the tracks the corpus knows about, how many carry
        # Last.fm tags?). Coverage over total_tracks would conflate the
        # corpus-miss problem with the enrichment problem and obscure
        # both.
        report.lastfm_tag_coverage_pct = (
            report.lastfm_tag_populated / report.matched_in_corpus
        )

    if listeners:
        report.lastfm_listeners_sample_size = len(listeners)
        report.lastfm_listeners_median = int(statistics.median(listeners))
        report.lastfm_listeners_p95 = _percentile(listeners, 0.95)

    return report


__all__ = [
    "LASTFM_TAG_COVERAGE_GATE",
    "NICHE_LISTENER_P95_GATE",
    "CorpusMetricsReport",
    "compute_corpus_metrics",
]

