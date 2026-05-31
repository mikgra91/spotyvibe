"""Tests for evaluation/benchmark — gates, scenarios, scorecard.

The benchmark package is the prescriptive production-readiness layer
over the existing harness. Its correctness gates real model rollouts,
so the behaviour locked in here is load-bearing:

  - Gate verdicts at boundary conditions (one shortfall = FAIL).
  - Scorecard aggregation rules (any FAIL = NOT_PRODUCTION_READY).
  - Scenario registry coverage (every scenario points at a real
    harness scenario; aged-state fixtures resolve to a file).
  - Pattern diagnoses fire on the right shapes.

No LLM / Spotify is invoked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from evaluation.benchmark.gates import (
    BenchmarkGate, GateResult, evaluate_gate,
    VERDICT_FAIL, VERDICT_PASS, VERDICT_WARN, VERDICT_SKIPPED,
)
from evaluation.benchmark.scenarios import (
    BENCHMARK_SCENARIOS, BenchmarkScenario, get_benchmark_scenario,
)
from evaluation.benchmark.scorecard import (
    Scorecard, finalise, render_console, render_markdown,
    _diagnose_pattern,
    VERDICT_PRODUCTION_READY, VERDICT_DEGRADED, VERDICT_NOT_READY,
)


# ── Fake ModelRunResult shape — enough for gate evaluation ───────────


@dataclass
class _FakeResult:
    playlist_track_count: int = 0
    leakage: dict | None = None
    error: str | None = None


# ── Gate evaluation ──────────────────────────────────────────────────


class TestEvaluateGate:
    """Per-sub-gate boundary behaviour. One gate at a time."""

    def _gate(self, **kw):
        defaults = dict(
            min_verified_count=27, min_spotify_found_rate=0.5,
            max_leakage_count=0, min_unique_artist_count=15,
            max_wall_seconds=120, max_cost_usd=0.10,
        )
        defaults.update(kw)
        return BenchmarkGate(**defaults)

    def _ok_inputs(self, **kw):
        defaults = dict(
            gate=self._gate(),
            scenario_name="x",
            result_obj=_FakeResult(
                playlist_track_count=30,
                leakage={"playlist_b_artists": [f"a{i}" for i in range(20)],
                         "disliked_track_count": 0,
                         "rejected_artist_count": 0,
                         "dislike_pattern_count": 0},
            ),
            eval_log_path=None,
            cost_usd=0.05,
            wall_seconds=60,
        )
        defaults.update(kw)
        return defaults

    def test_pass_when_all_gates_met_and_no_eval_log(self):
        # Without an eval log, the found-rate gate is treated as
        # MISSING — but min_spotify_found_rate > 0 still expects data.
        # So we set min_spotify_found_rate=0 here to isolate the
        # other gates.
        gate = self._gate(min_spotify_found_rate=0.0)
        r = evaluate_gate(**self._ok_inputs(gate=gate))
        assert r.verdict == VERDICT_PASS
        assert r.score >= 95

    def test_fail_when_verified_short(self):
        r = evaluate_gate(**self._ok_inputs(
            gate=self._gate(min_spotify_found_rate=0.0),
            result_obj=_FakeResult(playlist_track_count=10,
                                    leakage={"playlist_b_artists": ["a"]}),
        ))
        assert r.verdict == VERDICT_FAIL
        assert any("Verified 10/27" in h for h in r.hints)

    def test_fail_when_leakage_present(self):
        r = evaluate_gate(**self._ok_inputs(
            gate=self._gate(min_spotify_found_rate=0.0),
            result_obj=_FakeResult(
                playlist_track_count=30,
                leakage={"disliked_track_count": 2,
                          "playlist_b_artists": [f"a{i}" for i in range(20)]},
            ),
        ))
        assert r.verdict == VERDICT_FAIL
        assert any("Leakage" in h for h in r.hints)

    def test_warn_on_low_diversity_only(self, tmp_path):
        # Verified met, leakage 0, found rate high — but diversity
        # below floor. Diversity is read from per-track rows in
        # eval.jsonl; write a tiny file with 3 unique artists.
        import json
        log = tmp_path / "eval.jsonl"
        rows = [
            {"kind": "batch_summary", "gpt_returned_count": 10,
             "spotify_found_count": 10},
            {"kind": "track", "artist": "alpha", "track": "t1"},
            {"kind": "track", "artist": "beta", "track": "t2"},
            {"kind": "track", "artist": "gamma", "track": "t3"},
        ]
        log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        r = evaluate_gate(**self._ok_inputs(
            gate=self._gate(min_spotify_found_rate=0.0,
                            min_unique_artist_count=15),
            eval_log_path=log,
        ))
        assert r.verdict == VERDICT_WARN
        assert any("unique artists" in h for h in r.hints)

    def test_warn_on_latency_breach_only(self):
        r = evaluate_gate(**self._ok_inputs(
            gate=self._gate(min_spotify_found_rate=0.0, max_wall_seconds=10),
            wall_seconds=500,
        ))
        assert r.verdict == VERDICT_WARN
        assert any("Wall" in h for h in r.hints)

    def test_fail_on_pipeline_error_overrides_pass(self):
        r = evaluate_gate(**self._ok_inputs(
            gate=self._gate(min_spotify_found_rate=0.0),
            result_obj=_FakeResult(
                playlist_track_count=30,
                leakage={"playlist_b_artists": [f"a{i}" for i in range(20)]},
                error="OpenAI 429 burned through retry budget",
            ),
        ))
        assert r.verdict == VERDICT_FAIL
        assert r.hints[0].startswith("Pipeline error:")

    def test_found_rate_gate_fails_when_eval_log_missing(self, tmp_path):
        # min_spotify_found_rate > 0 + no eval.jsonl → fail with clear hint
        r = evaluate_gate(**self._ok_inputs(
            eval_log_path=tmp_path / "nope.jsonl",
        ))
        assert r.verdict == VERDICT_FAIL
        assert any("eval.jsonl missing" in h for h in r.hints)

    def test_found_rate_pass_with_eval_log(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        # 30 returned, 21 found = 70 % > 50 % threshold.
        # Also include enough track rows to satisfy the diversity
        # floor (default min_unique_artist_count=15).
        import json
        rows = [
            {"kind": "batch_summary", "gpt_returned_count": 10,
             "spotify_found_count": 7},
            {"kind": "batch_summary", "gpt_returned_count": 10,
             "spotify_found_count": 7},
            {"kind": "batch_summary", "gpt_returned_count": 10,
             "spotify_found_count": 7},
        ] + [
            {"kind": "track", "artist": f"a{i}", "track": f"t{i}"}
            for i in range(20)
        ]
        log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        r = evaluate_gate(**self._ok_inputs(eval_log_path=log))
        assert r.verdict == VERDICT_PASS
        assert r.spotify_found_rate is not None
        assert 0.69 < r.spotify_found_rate < 0.71

    def test_found_rate_fail_below_threshold(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        # 30 returned, 9 found = 30 % < 50 % threshold
        import json
        log.write_text(
            json.dumps({"kind": "batch_summary",
                         "gpt_returned_count": 30, "spotify_found_count": 9}),
            encoding="utf-8",
        )
        r = evaluate_gate(**self._ok_inputs(eval_log_path=log))
        assert r.verdict == VERDICT_FAIL
        assert any("Spotify-found rate 30" in h for h in r.hints)


# ── Scorecard aggregation rules ──────────────────────────────────────


class TestScorecardVerdict:

    def _mk(self, *results: GateResult) -> Scorecard:
        sc = Scorecard(model="x", started_at="t", finished_at="t")
        for r in results:
            sc.add(r)
        return finalise(sc)

    def _gr(self, verdict: str, score: float,
            scenario_name: str = "s") -> GateResult:
        return GateResult(
            scenario_name=scenario_name, verdict=verdict, score=score,
            verified_count=0, target_count=30,
            spotify_found_rate=None, leakage_count=0,
            unique_artist_count=0, wall_seconds=None, cost_usd=None,
            hints=[],
        )

    def test_all_pass_high_score_is_production_ready(self):
        sc = self._mk(self._gr(VERDICT_PASS, 95), self._gr(VERDICT_PASS, 88))
        assert sc.overall_verdict == VERDICT_PRODUCTION_READY
        assert sc.exit_code == 0

    def test_any_fail_is_not_ready(self):
        sc = self._mk(self._gr(VERDICT_PASS, 95), self._gr(VERDICT_FAIL, 10))
        assert sc.overall_verdict == VERDICT_NOT_READY
        assert sc.exit_code == 1

    def test_warn_with_no_fails_is_degraded(self):
        sc = self._mk(self._gr(VERDICT_PASS, 90), self._gr(VERDICT_WARN, 72))
        assert sc.overall_verdict == VERDICT_DEGRADED
        assert sc.exit_code == 0

    def test_low_avg_is_not_ready_even_without_fail(self):
        sc = self._mk(self._gr(VERDICT_WARN, 40), self._gr(VERDICT_WARN, 50))
        # avg 45 — under 60 → NOT_READY
        assert sc.overall_verdict == VERDICT_NOT_READY
        assert sc.exit_code == 1

    def test_skipped_rows_dont_count_in_average(self):
        sc = self._mk(
            self._gr(VERDICT_PASS, 100),
            self._gr(VERDICT_SKIPPED, 0),
        )
        # Average computed over scored only — 100, all PASS, high score
        assert sc.average_score == 100.0
        assert sc.overall_verdict == VERDICT_PRODUCTION_READY

    def test_counters_match_results(self):
        sc = self._mk(
            self._gr(VERDICT_PASS, 90),
            self._gr(VERDICT_PASS, 85),
            self._gr(VERDICT_WARN, 70),
            self._gr(VERDICT_FAIL, 10),
            self._gr(VERDICT_SKIPPED, 0),
        )
        assert (sc.pass_count, sc.warn_count, sc.fail_count,
                sc.skipped_count) == (2, 1, 1, 1)


class TestDiagnosePattern:

    def _gr(self, name, verdict, found_rate=None, leakage=0,
            hints=None) -> GateResult:
        return GateResult(
            scenario_name=name, verdict=verdict, score=0,
            verified_count=0, target_count=30,
            spotify_found_rate=found_rate, leakage_count=leakage,
            unique_artist_count=0, wall_seconds=None, cost_usd=None,
            hints=hints or [],
        )

    def test_niche_fail_with_mainstream_pass_yields_corpus_diagnosis(self):
        results = [
            self._gr("broad_mainstream_clean", VERDICT_PASS),
            self._gr("niche_japanese_clean", VERDICT_FAIL),
        ]
        d = _diagnose_pattern(results)
        assert any("corpus-coverage gap" in s for s in d)

    def test_aged_fail_clean_pass_yields_dedup_diagnosis(self):
        results = [
            self._gr("broad_mainstream_clean", VERDICT_PASS),
            self._gr("aged_mainstream_session5", VERDICT_FAIL),
        ]
        d = _diagnose_pattern(results)
        assert any("dedup-driven pool exhaustion" in s for s in d)

    def test_multiple_low_found_rates_yields_confab_diagnosis(self):
        results = [
            self._gr("a", VERDICT_FAIL, found_rate=0.10),
            self._gr("b", VERDICT_FAIL, found_rate=0.20),
        ]
        d = _diagnose_pattern(results)
        assert any("Spotify cannot resolve" in s for s in d)

    def test_no_fails_yields_empty_diagnosis(self):
        results = [self._gr("a", VERDICT_PASS), self._gr("b", VERDICT_PASS)]
        assert _diagnose_pattern(results) == []

    def test_multi_leakage_yields_feedback_diagnosis(self):
        results = [
            self._gr("a", VERDICT_FAIL, leakage=2),
            self._gr("b", VERDICT_FAIL, leakage=1),
        ]
        d = _diagnose_pattern(results)
        assert any("recently_filtered_tracks" in s for s in d)

    def test_pipeline_error_yields_infra_diagnosis(self):
        results = [
            self._gr("a", VERDICT_FAIL,
                     hints=["Pipeline error: timeout"]),
        ]
        d = _diagnose_pattern(results)
        assert any("pipeline error" in s for s in d)


# ── Scenario registry sanity ─────────────────────────────────────────


class TestScenarioRegistry:

    def test_registry_has_at_least_six_scenarios(self):
        # Locks in coverage of the failure axes — broad/niche, clean/aged,
        # contradictory, post-feedback.
        assert len(BENCHMARK_SCENARIOS) >= 6

    def test_every_scenario_references_an_existing_harness_scenario(self):
        from evaluation.scenario import SCENARIOS as HS
        for bench in BENCHMARK_SCENARIOS.values():
            assert bench.harness_scenario_name in HS, (
                f"{bench.name} points at unknown harness scenario "
                f"{bench.harness_scenario_name!r}"
            )

    def test_aged_state_fixtures_resolve_to_existing_files(self):
        for bench in BENCHMARK_SCENARIOS.values():
            if bench.seed_profile_path:
                assert bench.seed_profile_path.exists(), (
                    f"{bench.name}: fixture {bench.seed_profile_path} missing"
                )

    def test_every_scenario_has_nontrivial_gate(self):
        for bench in BENCHMARK_SCENARIOS.values():
            g = bench.gate
            # At a minimum: verified-count + leakage gates are active.
            assert g.min_verified_count > 0, (
                f"{bench.name} has no min_verified_count — useless gate"
            )
            assert g.max_leakage_count == 0, (
                f"{bench.name} allows leakage — every scenario must "
                "be zero-leakage"
            )

    def test_get_unknown_scenario_raises(self):
        with pytest.raises(KeyError):
            get_benchmark_scenario("nonexistent_scenario")

    def test_aged_japanese_session5_is_present(self):
        # The post-mortem regression test — production failure
        # reproducer. If this scenario is renamed or removed,
        # the production guarantee evaporates.
        assert "aged_japanese_session5" in BENCHMARK_SCENARIOS


# ── Rendering sanity (no asserts on cosmetic formatting) ─────────────


class TestRendering:

    def test_console_render_works_with_zero_results(self):
        sc = finalise(Scorecard(model="x", started_at="t", finished_at="t"))
        out = render_console(sc)
        assert "SpotyVibe Benchmark - x" in out
        assert "VERDICT" in out

    def test_markdown_render_works_with_results(self):
        sc = Scorecard(model="x", started_at="t", finished_at="t")
        sc.add(GateResult(
            scenario_name="s", verdict=VERDICT_PASS, score=95,
            verified_count=30, target_count=30,
            spotify_found_rate=0.9, leakage_count=0,
            unique_artist_count=18, wall_seconds=60, cost_usd=0.02,
            hints=[],
        ))
        md = render_markdown(finalise(sc))
        assert "| `s` |" in md
        assert "PRODUCTION_READY" in md
