"""B-6. Self-consistency floor (variance, not mean).

Re-issues B-2's strict variant 5x at temperature=0 and reports the
sigma of the primary + secondary output lengths. The mean is not the
point; the variance is. If sigma on a fixed prompt is 15 pp, an n=3
eval signal of "+5 pp" is noise.

Output ``n_required_for_5pp_signal`` becomes the recommended-n field on
the fingerprint card. Formula: rough Welch's-style; n >= ceil((1.96*sigma
/ 0.05)^2). Plenty conservative; not a real power calc.

The probe reuses ``probe_b2_overconstraint`` so the prompt cannot drift.
"""

from __future__ import annotations

import math
from typing import Any

from . import probe_b2_overconstraint as _b2


PROBE_ID = "B-6.self_consistency_floor"
VARIANTS = ["strict_repeated"]
RUNS_PER_VARIANT = {"strict_repeated": 5}


def build_messages(variant: str) -> list[dict]:
    # Same wire bytes as B-2/strict every call. Determinism floor is
    # then a property of the model, not of an unstable prompt.
    return _b2.build_messages("strict")


def response_format(variant: str) -> dict | None:
    return _b2.response_format("strict")


def score(variant: str, parsed: Any, raw: str) -> dict[str, float]:
    # Reuse B-2's per-call scoring so the same primary/secondary lengths
    # surface in the result for downstream aggregation.
    return _b2.score("strict", parsed, raw)


def _stddev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)            # sample sigma
    return math.sqrt(var)


def _n_for_5pp(sigma_units: float, target_metric_max: float) -> int:
    """How many runs to detect a 5 pp shift in the *ratio* metric.

    ``sigma_units`` is sigma in units of the raw metric (e.g. number of
    items). ``target_metric_max`` rescales it to a 0..1 ratio (e.g. 10
    for primary_length where ratio = length/10).
    """
    if target_metric_max <= 0:
        return 1
    sigma_ratio = sigma_units / target_metric_max
    if sigma_ratio == 0:
        return 1
    # 95% CI width formula on the mean: 2 * 1.96 * sigma / sqrt(n) <= 0.05.
    n = math.ceil((2 * 1.96 * sigma_ratio / 0.05) ** 2)
    return max(1, min(n, 100))                                       # cap at 100


def aggregate(variant: str, per_call_scores: list[dict[str, float]]) -> dict[str, float]:
    """Fingerprint-level aggregation — sigma + recommended-n."""
    if not per_call_scores:
        return {}

    primary_lengths   = [float(s.get("primary_length",   0.0)) for s in per_call_scores]
    secondary_lengths = [float(s.get("secondary_length", 0.0)) for s in per_call_scores]
    primary_ratios    = [float(s.get("primary_length_ratio", 0.0)) for s in per_call_scores]

    sigma_primary       = _stddev(primary_lengths)
    sigma_secondary     = _stddev(secondary_lengths)
    sigma_primary_ratio = _stddev(primary_ratios)

    n_for_primary   = _n_for_5pp(sigma_primary,   target_metric_max=10.0)
    n_for_secondary = _n_for_5pp(sigma_secondary, target_metric_max=20.0)
    n_required      = max(n_for_primary, n_for_secondary)

    n_runs = len(per_call_scores)
    return {
        "runs":                          float(n_runs),
        "primary_entries_sigma":         sigma_primary,
        "secondary_entries_sigma":       sigma_secondary,
        "primary_ratio_sigma":           sigma_primary_ratio,
        "mean_primary_length":           sum(primary_lengths)   / n_runs,
        "mean_secondary_length":         sum(secondary_lengths) / n_runs,
        "n_required_for_5pp_signal":     float(n_required),
    }
