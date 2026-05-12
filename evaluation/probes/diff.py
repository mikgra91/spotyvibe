"""Fingerprint diff + regression detection.

Compares a newly-captured fingerprint against a committed baseline card
and reports per-score deltas + a list of regressions. A regression is a
delta that moves a *load-bearing* score in the wrong direction by more
than ``tolerance`` (default 0.05).

Direction-of-improvement per score is hard-coded in ``DIRECTION``
below. Scores not listed are informational only (printed in the diff
but never flag a regression — e.g. raw counts).

Used by ``evaluation/run_evaluation.py``'s ``--probe-check`` gate to
abort a full eval BEFORE any OpenAI/Spotify quota is spent when a
prompt PR has measurably regressed a known load-bearing property.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Direction = Literal["higher", "lower"]


# Direction of improvement per (probe_id, score_name). Omitted entries
# are informational. Keep names in lock-step with each probe module's
# ``score()`` return keys + B-6's ``aggregate()`` keys.
DIRECTION: dict[tuple[str, str], Direction] = {
    # B-1 constraint grammar
    ("B-1.constraint_grammar", "soft_compliance"):            "higher",
    ("B-1.constraint_grammar", "hard_compliance"):            "higher",
    ("B-1.constraint_grammar", "quota_preserved_under_hard"): "higher",
    ("B-1.constraint_grammar", "primary_quota_met"):          "higher",
    ("B-1.constraint_grammar", "secondary_quota_met"):        "higher",

    # B-2 over-constraint collapse
    ("B-2.over_constraint_collapse", "primary_length_ratio"): "higher",
    ("B-2.over_constraint_collapse", "secondary_quota_met"):  "higher",

    # B-3 confabulation - more omission = more calibrated for a fictional author
    ("B-3.confabulation_pressure", "well_calibrated"):        "higher",
    ("B-3.confabulation_pressure", "omission_rate"):          "higher",
    ("B-3.confabulation_pressure", "uncertainty_rate"):       "higher",

    # B-4 omission discipline
    ("B-4.omission_discipline", "omission_precision"):        "higher",
    ("B-4.omission_discipline", "omission_recall"):           "higher",
    ("B-4.omission_discipline", "padding_rate"):              "lower",

    # B-5 format under contradiction
    ("B-5.format_under_contradiction", "bucket_a"):           "higher",
    ("B-5.format_under_contradiction", "bucket_b"):           "higher",
    ("B-5.format_under_contradiction", "bucket_c"):           "lower",
    ("B-5.format_under_contradiction", "bucket_d"):           "lower",
    ("B-5.format_under_contradiction", "bucket_e"):           "lower",
    ("B-5.format_under_contradiction", "format_healthy"):     "higher",

    # B-6 self-consistency floor
    ("B-6.self_consistency_floor", "primary_entries_sigma"):     "lower",
    ("B-6.self_consistency_floor", "secondary_entries_sigma"):   "lower",
    ("B-6.self_consistency_floor", "primary_ratio_sigma"):       "lower",
    ("B-6.self_consistency_floor", "n_required_for_5pp_signal"): "lower",

    # B-10 cite fidelity
    ("B-10.cite_fidelity", "verbatim_rate"):                  "higher",
    ("B-10.cite_fidelity", "any_nonempty_cite"):              "higher",

    # B-11 empty pool recovery
    ("B-11.empty_pool_recovery", "bucket_a"):                 "higher",
    ("B-11.empty_pool_recovery", "bucket_b"):                 "higher",
    ("B-11.empty_pool_recovery", "bucket_c"):                 "lower",
    ("B-11.empty_pool_recovery", "bucket_d"):                 "lower",
    ("B-11.empty_pool_recovery", "bucket_e"):                 "lower",
    ("B-11.empty_pool_recovery", "pool_recovery_healthy"):    "higher",
}


# Default tolerance applied uniformly. Per-score overrides go here.
DEFAULT_TOLERANCE = 0.05


# Some scores (like n_required_for_5pp_signal) are counts, not 0..1
# ratios — a "delta > 0.05" tolerance there means "off by 0.05 of a
# run", which is silly. Per-score absolute tolerance overrides:
TOLERANCE_OVERRIDES: dict[tuple[str, str], float] = {
    ("B-6.self_consistency_floor", "n_required_for_5pp_signal"): 5.0,
    ("B-6.self_consistency_floor", "primary_entries_sigma"):     0.5,
    ("B-6.self_consistency_floor", "secondary_entries_sigma"):   1.0,
    ("B-6.self_consistency_floor", "primary_ratio_sigma"):       0.05,
}


@dataclass
class Regression:
    probe_id: str
    variant: str
    score:   str
    direction: Direction
    baseline: float
    new:      float
    delta:    float

    def describe(self) -> str:
        arrow = "down" if self.delta < 0 else "up"
        return (
            f"{self.probe_id}/{self.variant} | {self.score}: "
            f"{self.baseline:.4f} -> {self.new:.4f} ({arrow} {abs(self.delta):.4f}) "
            f"[expected: {self.direction}]"
        )


# ── Loading helpers ──────────────────────────────────────────────────

def load_fingerprint(path: Path) -> dict:
    """Read a fingerprint JSON file. Raises FileNotFoundError if absent."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def baseline_path_for(model: str, *, fingerprints_dir: Path) -> Path:
    """Canonical baseline location: ``<dir>/<model>.v1.json``."""
    return Path(fingerprints_dir) / f"{model}.v1.json"


# ── Diff + regression detection ──────────────────────────────────────

def _index_by_variant(probes: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    out: dict[tuple[str, str], dict[str, float]] = {}
    for p in probes:
        out[(p["probe_id"], p["variant"])] = dict(p.get("scores") or {})
    return out


def _tolerance(probe_id: str, score: str) -> float:
    return TOLERANCE_OVERRIDES.get((probe_id, score), DEFAULT_TOLERANCE)


def detect_regressions(
    baseline: dict, new: dict, *,
    extra_tolerance: float = 0.0,
) -> list[Regression]:
    """Return a list of regression objects. Empty list = no regression.

    ``extra_tolerance`` is added on top of the per-score default; the
    CLI exposes this so a noisy CI run can be soft-gated without
    rewriting the table.
    """
    new_idx      = _index_by_variant(new.get("probes", []))
    baseline_idx = _index_by_variant(baseline.get("probes", []))

    regressions: list[Regression] = []
    for key, new_scores in new_idx.items():
        probe_id, variant = key
        base_scores = baseline_idx.get(key)
        if not base_scores:
            continue                                # new probe — no baseline yet
        for score, new_val in new_scores.items():
            direction = DIRECTION.get((probe_id, score))
            if direction is None:
                continue                            # informational
            base_val = base_scores.get(score)
            if base_val is None:
                continue
            delta = float(new_val) - float(base_val)
            tol = _tolerance(probe_id, score) + extra_tolerance
            if direction == "higher" and delta < -tol:
                regressions.append(Regression(
                    probe_id=probe_id, variant=variant, score=score,
                    direction=direction, baseline=float(base_val),
                    new=float(new_val), delta=delta,
                ))
            elif direction == "lower" and delta > tol:
                regressions.append(Regression(
                    probe_id=probe_id, variant=variant, score=score,
                    direction=direction, baseline=float(base_val),
                    new=float(new_val), delta=delta,
                ))
    return regressions


def render_fingerprint_diff(baseline: dict, new: dict) -> str:
    """Markdown table of every directional score, with the delta + a flag
    column indicating regression / improvement / no-change.
    """
    new_idx      = _index_by_variant(new.get("probes", []))
    baseline_idx = _index_by_variant(baseline.get("probes", []))

    rows = []
    rows.append("| Probe / variant | Score | Baseline | New | Delta | Direction | Flag |")
    rows.append("|---|---|---:|---:|---:|:---:|:---:|")

    keys = sorted(set(new_idx.keys()) | set(baseline_idx.keys()))
    for probe_id, variant in keys:
        new_scores  = new_idx.get((probe_id, variant), {})
        base_scores = baseline_idx.get((probe_id, variant), {})
        score_keys  = sorted(set(new_scores.keys()) | set(base_scores.keys()))
        for s in score_keys:
            direction = DIRECTION.get((probe_id, s))
            if direction is None:
                continue                            # informational — skip
            base_val = base_scores.get(s)
            new_val  = new_scores.get(s)
            if base_val is None and new_val is None:
                continue
            if base_val is None:
                flag = "NEW"
                delta_str = "—"
                base_str  = "—"
                new_str   = f"{new_val:.4f}"
            elif new_val is None:
                flag = "DROP"
                delta_str = "—"
                base_str  = f"{base_val:.4f}"
                new_str   = "—"
            else:
                delta = float(new_val) - float(base_val)
                tol = _tolerance(probe_id, s)
                if direction == "higher" and delta < -tol:
                    flag = "REGRESS"
                elif direction == "lower" and delta > tol:
                    flag = "REGRESS"
                elif direction == "higher" and delta > tol:
                    flag = "improved"
                elif direction == "lower" and delta < -tol:
                    flag = "improved"
                else:
                    flag = "-"
                base_str  = f"{base_val:.4f}"
                new_str   = f"{new_val:.4f}"
                delta_str = f"{delta:+.4f}"
            rows.append(
                f"| {probe_id}/{variant} | {s} | {base_str} | {new_str} "
                f"| {delta_str} | {direction} | {flag} |"
            )

    header = f"### Fingerprint diff: {baseline.get('model','?')} (v{baseline.get('fingerprint_version','?')} baseline)\n"
    return header + "\n".join(rows)
