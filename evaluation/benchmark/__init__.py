"""Production-readiness benchmark for SpotyVibe.

Wraps the existing ``evaluation.harness`` execution layer with a curated
set of realistic scenarios + hard pass/fail gates + a one-screen
scorecard. Designed for the "I'm trying a new model, is it good
enough?" workflow.

Entry point: ``python -m evaluation.benchmark --model X``.

The benchmark differs from ``evaluation.run_evaluation`` in three ways:

1. **Curated scenarios.** Six scenarios spanning the real failure axes:
   broad/niche, clean/aged state, contradictory facets, multi-session
   anti-leakage. Each one is here because it caught a production bug.

2. **Hard gates per scenario.** Verified count, Spotify-found rate,
   leakage count, diversity floor, latency, cost — each scenario
   declares its own thresholds. A model that misses any gate FAILS that
   scenario.

3. **Production-readiness verdict.** The CLI exits 0 (production-ready)
   or 1 (not ready). The scorecard tells you not just which gates
   failed but WHY they probably failed and what to investigate.

Why not extend ``run_evaluation``? Backwards compatibility — existing
scripts and CI hooks call it with established semantics. The benchmark
is the prescriptive layer; ``run_evaluation`` stays as the open-ended
investigation tool.
"""
from .gates import BenchmarkGate, GateResult, evaluate_gate
from .scenarios import BENCHMARK_SCENARIOS, BenchmarkScenario
from .scorecard import Scorecard, render_scorecard

__all__ = [
    "BenchmarkGate",
    "GateResult",
    "evaluate_gate",
    "BENCHMARK_SCENARIOS",
    "BenchmarkScenario",
    "Scorecard",
    "render_scorecard",
]
