"""Per-scenario pass/fail gates for the production-readiness benchmark.

A :class:`BenchmarkGate` declares the THRESHOLDS one scenario must
meet. :func:`evaluate_gate` reads a ``ModelRunResult`` (the harness's
per-run record) and returns a :class:`GateResult` that says:

  - the overall verdict (PASS / WARN / FAIL),
  - which sub-gates fired,
  - a numeric score (0-100) for the scorecard rollup,
  - one human-readable diagnostic hint per failed sub-gate.

Design rule: every gate has an explicit numeric threshold backed by
a known failure-mode receipt in [next-steps.md]. No "feels about
right" thresholds — each one points to data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Verdict constants ────────────────────────────────────────────────

VERDICT_PASS = "PASS"
VERDICT_WARN = "WARN"
VERDICT_FAIL = "FAIL"
VERDICT_SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class BenchmarkGate:
    """Threshold pack for one benchmark scenario.

    All thresholds are LOWER BOUNDS (minimums) except the ``max_*``
    fields which are upper bounds. Setting a field to ``None`` disables
    that sub-gate.

    Field meanings:

    - ``min_verified_count`` — playlist must have at least this many
      Spotify-verified tracks. Maps to ``ModelRunResult.playlist_track_count``.
      The single most important gate — a 4/30 playlist is unusable.
    - ``min_spotify_found_rate`` — across all Stage 3 picks the harness
      saw, at least this fraction must have resolved on Spotify.
      Catches the corpus-vs-Spotify cascade (production trace 435c7016).
    - ``max_leakage_count`` — combined count of disliked-track,
      rejected-artist, and dislike-pattern hits in the second playlist
      (post-feedback). Production bug class flagged in CLAUDE.md.
    - ``min_unique_artist_count`` — diversity floor; catches the
      "Stage 3 recycles the same 6 anchor artists" anti-pattern.
    - ``max_wall_seconds`` — full-cycle wall time ceiling. Soft cap;
      breaches downgrade to WARN, not FAIL.
    - ``max_cost_usd`` — same: soft cap, WARN on breach.

    A WARN means the scenario is degraded but not broken; FAIL means
    the model fails the scenario outright.
    """

    min_verified_count: int
    min_spotify_found_rate: float = 0.0
    max_leakage_count: int = 0
    min_unique_artist_count: int = 0
    max_wall_seconds: float | None = None
    max_cost_usd: float | None = None


@dataclass
class GateResult:
    """Outcome of evaluating one :class:`BenchmarkGate` against a run.

    ``verdict`` is the headline. ``score`` aggregates the sub-gates
    onto a 0-100 scale for the scorecard average. ``hints`` carries
    one short string per failed sub-gate — these are what the
    scorecard surfaces to the user as "likely causes".
    """

    scenario_name: str
    verdict: str
    score: float
    verified_count: int
    target_count: int
    spotify_found_rate: float | None
    leakage_count: int
    unique_artist_count: int
    wall_seconds: float | None
    cost_usd: float | None
    hints: list[str] = field(default_factory=list)


# ── Sub-gate weights for the 0-100 score ─────────────────────────────
#
# Quality dimensions are NOT equally important: a model that fills the
# playlist with garbage scores worse than one that under-fills with
# good picks. Weights chosen so a model passing every hard gate scores
# in the 90s; soft-cap breaches knock 5-10 pts off.

_W_VERIFIED = 40.0     # fill rate is the single most user-visible metric
_W_FOUND = 20.0        # Spotify-resolvability gates downstream UX
_W_LEAKAGE = 20.0      # anti-leakage is binary trust
_W_DIVERSITY = 10.0    # recycling makes playlists feel broken
_W_LATENCY = 5.0       # latency is a soft preference
_W_COST = 5.0          # cost is a soft preference


def _spotify_found_rate_from_eval_log(eval_log_path) -> float | None:
    """Pull the cumulative Spotify-found rate from an eval.jsonl file.

    Returns None when the file is missing or has no batch_summary rows.
    The harness writes one ``kind: batch_summary`` row per batch with
    ``gpt_returned_count`` and ``spotify_found_count`` — the ratio
    across all batches is the headline diversity metric.
    """
    import json
    from pathlib import Path

    p = Path(eval_log_path) if not isinstance(eval_log_path, Path) else eval_log_path
    if not p.exists():
        return None
    total_returned = 0
    total_found = 0
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if row.get("kind") != "batch_summary":
                    continue
                total_returned += int(row.get("gpt_returned_count") or 0)
                total_found += int(row.get("spotify_found_count") or 0)
    except OSError:
        return None
    if total_returned <= 0:
        return None
    return total_found / total_returned


def _unique_artist_count(eval_log_path) -> int:
    """Count distinct artists across the per-track eval.jsonl rows.

    The harness emits one ``kind: track`` row per generated track
    with an ``artist`` field. Distinct lowercased artists across
    those rows is a faithful diversity proxy — catches the
    "Stage 3 recycles the same 6 anchors" failure mode without
    needing harness changes. Returns 0 when the file is missing
    or has no track rows (caller should not over-interpret 0).
    """
    if eval_log_path is None:
        return 0
    import json
    from pathlib import Path
    p = Path(eval_log_path) if not isinstance(eval_log_path, Path) else eval_log_path
    if not p.exists():
        return 0
    artists: set[str] = set()
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if row.get("kind") != "track":
                    continue
                a = row.get("artist")
                if isinstance(a, str) and a.strip():
                    artists.add(a.lower().strip())
    except OSError:
        return 0
    return len(artists)


def evaluate_gate(
    *,
    gate: BenchmarkGate,
    scenario_name: str,
    result_obj: Any,
    eval_log_path=None,
    cost_usd: float | None = None,
    wall_seconds: float | None = None,
) -> GateResult:
    """Score *result_obj* against *gate*. Always returns a GateResult.

    Designed to be SAFE on partial / errored results — a run that
    blew up mid-pipeline (``playlist_status = "error"``) still gets a
    GateResult with FAIL + a hint pointing at the error. Never raises.
    """
    verified = int(getattr(result_obj, "playlist_track_count", 0) or 0)
    leakage_count = 0
    leakage = getattr(result_obj, "leakage", None)
    if isinstance(leakage, dict):
        leakage_count = (
            int(leakage.get("disliked_track_count") or 0)
            + int(leakage.get("rejected_artist_count") or 0)
            + int(leakage.get("dislike_pattern_count") or 0)
        )
    found_rate = (
        _spotify_found_rate_from_eval_log(eval_log_path)
        if eval_log_path is not None else None
    )
    unique = _unique_artist_count(eval_log_path)

    hints: list[str] = []
    score = 0.0
    hard_fail = False
    warn = False

    # Verified count (HARD gate) — the user-visible failure
    if gate.min_verified_count > 0:
        ratio = min(1.0, verified / gate.min_verified_count)
        score += _W_VERIFIED * ratio
        if verified < gate.min_verified_count:
            hard_fail = True
            shortfall_pct = round(100 * (1 - ratio))
            hints.append(
                f"Verified {verified}/{gate.min_verified_count} "
                f"(short by {shortfall_pct}%). Likely causes: "
                "pool starvation, Spotify cascade, or model refusal. "
                "Inspect trace_a `run_batches[*].outcome`."
            )

    # Spotify-found rate (HARD gate when threshold > 0)
    if gate.min_spotify_found_rate > 0:
        if found_rate is None:
            hard_fail = True
            hints.append(
                "Cannot compute Spotify-found rate — eval.jsonl missing or "
                "empty. Pipeline likely aborted before any batch ran."
            )
        else:
            ratio = min(1.0, found_rate / gate.min_spotify_found_rate)
            score += _W_FOUND * ratio
            if found_rate < gate.min_spotify_found_rate:
                hard_fail = True
                hints.append(
                    f"Spotify-found rate {found_rate*100:.1f}% < "
                    f"{gate.min_spotify_found_rate*100:.0f}% threshold. "
                    "Stage 3 is picking tracks Spotify cannot resolve. "
                    "Check Q2 overlay pruning + corpus `top_tracks` coverage."
                )
    else:
        # Gate disabled — give credit by default so the score isn't
        # artificially depressed when the scenario doesn't care.
        score += _W_FOUND

    # Anti-leakage (HARD gate; binary)
    if leakage_count <= gate.max_leakage_count:
        score += _W_LEAKAGE
    else:
        hard_fail = True
        hints.append(
            f"Leakage = {leakage_count} (max allowed {gate.max_leakage_count}). "
            "Disliked tracks or rejected artists re-appeared. "
            "Inspect feedback pipeline + Stage 3 `recently_filtered_tracks` "
            "prompt block."
        )

    # Diversity floor (SOFT — WARN, not FAIL). Skip when we have no
    # telemetry to read from: a missing eval log means we can't
    # measure diversity, not that diversity is 0. Score awarded by
    # default so a no-telemetry run isn't artificially depressed.
    if gate.min_unique_artist_count > 0 and eval_log_path is not None:
        ratio = min(1.0, unique / gate.min_unique_artist_count) if unique else 0.0
        score += _W_DIVERSITY * ratio
        if unique < gate.min_unique_artist_count:
            warn = True
            hints.append(
                f"Only {unique} unique artists "
                f"(target {gate.min_unique_artist_count}). "
                "Stage 3 is recycling. Check Q1 pool shuffle + "
                "approved-pool size."
            )
    else:
        score += _W_DIVERSITY

    # Latency (SOFT — WARN)
    if gate.max_wall_seconds and wall_seconds is not None:
        if wall_seconds <= gate.max_wall_seconds:
            score += _W_LATENCY
        else:
            warn = True
            hints.append(
                f"Wall {wall_seconds:.0f}s > {gate.max_wall_seconds:.0f}s "
                "soft cap. Model may be too slow for the UX target."
            )
    else:
        score += _W_LATENCY

    # Cost (SOFT — WARN)
    if gate.max_cost_usd and cost_usd is not None:
        if cost_usd <= gate.max_cost_usd:
            score += _W_COST
        else:
            warn = True
            hints.append(
                f"Cost ${cost_usd:.3f} > ${gate.max_cost_usd:.3f} "
                "soft cap. Per-playlist economics flagged."
            )
    else:
        score += _W_COST

    if hard_fail:
        verdict = VERDICT_FAIL
    elif warn:
        verdict = VERDICT_WARN
    else:
        verdict = VERDICT_PASS

    # Pipeline-level failures override (e.g., harness raised before any
    # playlist was generated). Surface them as hard FAIL.
    err = getattr(result_obj, "error", None)
    if err:
        verdict = VERDICT_FAIL
        hints.insert(0, f"Pipeline error: {str(err)[:200]}")

    return GateResult(
        scenario_name=scenario_name,
        verdict=verdict,
        score=round(score, 1),
        verified_count=verified,
        target_count=gate.min_verified_count,
        spotify_found_rate=found_rate,
        leakage_count=leakage_count,
        unique_artist_count=unique,
        wall_seconds=wall_seconds,
        cost_usd=cost_usd,
        hints=hints,
    )
