"""Tests for the Track B probe runner + 8-probe catalogue.

Conventions:
- All OpenAI calls are mocked at the runner level via the
  ``openai_call`` parameter (injection-friendly), NOT via patching
  ``core.src.openai_http.chat_completions_create``. This keeps the
  tests independent of the production HTTP module and means a probe
  test can never accidentally hit a live endpoint.
- Each test seeds its own canned response shape so probes are exercised
  against representative success and failure modes.
"""

from __future__ import annotations

import json
import math
from typing import Any
from unittest.mock import patch

import pytest

from evaluation.probes import (
    cli,
    diff,
    probe_b1_constraint,
    probe_b2_overconstraint,
    probe_b3_confabulation,
    probe_b4_omission,
    probe_b5_format,
    probe_b6_consistency,
    probe_b10_cite,
    probe_b11_empty_pool,
    runner,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _canned_response(
    content: str,
    *,
    prompt_tokens: int = 100,
    completion_tokens: int = 60,
) -> dict:
    """Build a minimal OpenAI-shaped chat completion response."""
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      prompt_tokens + completion_tokens,
        },
    }


class _CannedCaller:
    """Mock OpenAI callable. Returns canned responses in order; raises on
    over-consume so tests fail loudly when the call count is wrong."""

    def __init__(self, *responses: dict):
        self._queue = list(responses)
        self.calls: list[dict] = []

    def __call__(self, *, model: str, messages: list, temperature: float,
                 response_format: dict | None) -> dict:
        self.calls.append({
            "model":           model,
            "messages":        messages,
            "temperature":     temperature,
            "response_format": response_format,
        })
        if not self._queue:
            raise AssertionError("CannedCaller exhausted")
        return self._queue.pop(0)


# ── Runner contract ───────────────────────────────────────────────────

class TestRunnerEnvelope:
    def test_temperature_is_zero(self):
        caller = _CannedCaller(_canned_response('{"colours": []}'))
        runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        # B-1 has 3 variants × 1 run = 3 calls; we only checked first because
        # of the 1-item queue. Replenish + re-call for full assertion.
        caller2 = _CannedCaller(
            _canned_response('{"colours": []}'),
            _canned_response('{"colours": []}'),
            _canned_response('{"colours": []}'),
        )
        runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller2)
        assert all(c["temperature"] == 0.0 for c in caller2.calls)
        assert len(caller2.calls) == 3

    def test_result_carries_tokens_and_cost(self):
        caller = _CannedCaller(
            _canned_response('{"colours": ["red"]}', prompt_tokens=200, completion_tokens=80),
            _canned_response('{"colours": []}',     prompt_tokens=200, completion_tokens=80),
            _canned_response('{"colours": []}',     prompt_tokens=200, completion_tokens=80),
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        assert all(r.tokens_in == 200 for r in results)
        assert all(r.tokens_out == 80 for r in results)
        # Cost for mini: 0.15 in + 0.60 out per 1M tokens.
        expected = (200 / 1_000_000.0) * 0.15 + (80 / 1_000_000.0) * 0.60
        assert all(math.isclose(r.cost_usd, expected, rel_tol=1e-9) for r in results)

    def test_call_failure_recorded_but_does_not_abort_battery(self):
        class _ExplodingCaller:
            def __init__(self):
                self.n = 0
            def __call__(self, **_kwargs):
                self.n += 1
                if self.n == 1:
                    raise RuntimeError("simulated API failure")
                return _canned_response('{"colours": []}')

        results = runner.run_probe(
            probe_b1_constraint, "gpt-5.4-mini", openai_call=_ExplodingCaller()
        )
        assert len(results) == 3
        assert results[0].error is not None
        assert "simulated API failure" in results[0].error
        assert results[1].error is None and results[2].error is None

    def test_safe_json_loads_handles_code_fences(self):
        # parsed_json must be a dict even though the response was fenced.
        body = "```json\n{\"colours\": [\"red\"]}\n```"
        caller = _CannedCaller(
            _canned_response(body), _canned_response(body), _canned_response(body)
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        assert all(r.parsed_json == {"colours": ["red"]} for r in results)

    def test_safe_json_loads_handles_unparseable_response(self):
        body = "I cannot answer that."
        caller = _CannedCaller(
            _canned_response(body), _canned_response(body), _canned_response(body)
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        assert all(r.parsed_json is None for r in results)
        assert all(r.error is None for r in results)        # bad JSON != exception


# ── B-1: constraint grammar ──────────────────────────────────────────

class TestB1Constraint:
    def test_perfect_compliance_all_variants(self):
        ok = json.dumps({"colours": [
            "blank", "ruby",  "lilac", "mauv",
            "puc",   "salm",  "wisp",  "tofu",
        ]})
        # 8 colours, all without 'e' — primary quota AND avoid-e both met.
        caller = _CannedCaller(_canned_response(ok), _canned_response(ok), _canned_response(ok))
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)

        by_v = {r.variant: r for r in results}
        assert by_v["soft"].scores["soft_compliance"] == 1.0
        assert by_v["hard"].scores["hard_compliance"] == 1.0
        assert by_v["hard_with_quota"].scores["quota_preserved_under_hard"] == 1.0
        assert by_v["hard_with_quota"].scores["primary_quota_met"] == 1.0

    def test_collapse_under_hard_quota(self):
        # Mini's R1.3-strict failure mode: returned only 4 colours.
        body = json.dumps({"colours": ["ruby", "tan", "lilac", "wisp"]})
        caller = _CannedCaller(
            _canned_response(body), _canned_response(body), _canned_response(body)
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        hq = next(r for r in results if r.variant == "hard_with_quota")
        assert hq.scores["primary_quota_met"] == 0.0
        # 4 < 6, so secondary_quota_met is 0.0 — collapse on both axes.
        assert hq.scores["secondary_quota_met"] == 0.0
        assert hq.scores["quota_preserved_under_hard"] == 0.0

    def test_soft_partial_compliance(self):
        # 8 returned, 6 of them avoid 'e' => soft_compliance=0.75.
        body = json.dumps({"colours": [
            "ruby", "tan", "lilac", "wisp", "puc", "salm",
            "green",  # has 'e'
            "beige",  # has 'e'
        ]})
        caller = _CannedCaller(
            _canned_response(body), _canned_response(body), _canned_response(body)
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini", openai_call=caller)
        soft = next(r for r in results if r.variant == "soft")
        assert math.isclose(soft.scores["soft_compliance"], 0.75)
        hard = next(r for r in results if r.variant == "hard")
        assert hard.scores["hard_compliance"] == 0.0     # any 'e' is a fail


# ── B-2: over-constraint collapse ────────────────────────────────────

class TestB2Overconstraint:
    def test_free_variant_healthy(self):
        body = json.dumps({
            "playlist": [f"Song {i}" for i in range(10)],
            "rejected_candidates": [
                {"title": f"Rej {i}", "reason": "off-vibe"} for i in range(20)
            ],
        })
        caller = _CannedCaller(_canned_response(body), _canned_response(body))
        results = runner.run_probe(probe_b2_overconstraint, "gpt-5.4-mini",
                                   openai_call=caller)
        free = next(r for r in results if r.variant == "free")
        assert free.scores["primary_length"] == 10.0
        assert free.scores["primary_length_ratio"] == 1.0
        assert free.scores["secondary_quota_met"] == 1.0

    def test_strict_collapse(self):
        # Model padded rejected to 20 but only returned 6 picks.
        body = json.dumps({
            "playlist": [f"Song {i}" for i in range(6)],
            "rejected_candidates": [
                {"title": f"Rej {i}", "reason": "x"} for i in range(20)
            ],
        })
        caller = _CannedCaller(_canned_response(body), _canned_response(body))
        results = runner.run_probe(probe_b2_overconstraint, "gpt-5.4-mini",
                                   openai_call=caller)
        strict = next(r for r in results if r.variant == "strict")
        assert math.isclose(strict.scores["primary_length_ratio"], 0.6)
        assert strict.scores["secondary_quota_met"] == 1.0


# ── B-3: confabulation pressure ──────────────────────────────────────

class TestB3Confabulation:
    def test_calibrated_empty_list(self):
        body = json.dumps({"novels": []})
        caller = _CannedCaller(_canned_response(body))
        results = runner.run_probe(probe_b3_confabulation, "gpt-5.4-mini",
                                   openai_call=caller)
        r = results[0]
        assert r.scores["returned_count"] == 0.0
        assert r.scores["omission_rate"] == 1.0
        assert r.scores["well_calibrated"] == 1.0

    def test_full_confabulation(self):
        body = json.dumps({
            "novels": [
                {"title": f"Fake Novel {i}", "year": 2010 + i, "uncertain": False}
                for i in range(12)
            ],
        })
        caller = _CannedCaller(_canned_response(body))
        results = runner.run_probe(probe_b3_confabulation, "gpt-5.4-mini",
                                   openai_call=caller)
        r = results[0]
        assert r.scores["returned_count"] == 12.0
        assert r.scores["omission_rate"] == 0.0
        assert r.scores["uncertainty_rate"] == 0.0
        assert r.scores["well_calibrated"] == 0.0

    def test_all_flagged_uncertain_counts_as_calibrated(self):
        body = json.dumps({
            "novels": [
                {"title": "Maybe", "year": None, "uncertain": True} for _ in range(3)
            ],
        })
        caller = _CannedCaller(_canned_response(body))
        results = runner.run_probe(probe_b3_confabulation, "gpt-5.4-mini",
                                   openai_call=caller)
        r = results[0]
        assert r.scores["uncertainty_rate"] == 1.0
        assert r.scores["well_calibrated"] == 1.0   # all flagged → calibrated


# ── B-4: omission discipline ─────────────────────────────────────────

class TestB4Omission:
    def test_perfect_precision_and_recall(self):
        # Echo the 25 fictitious names verbatim; leave the 5 famous out.
        from evaluation.probes.probe_b4_omission import _FICTITIOUS
        body = json.dumps({"unknown_artists": list(_FICTITIOUS)})
        caller = _CannedCaller(_canned_response(body))
        results = runner.run_probe(probe_b4_omission, "gpt-5.4-mini",
                                   openai_call=caller)
        s = results[0].scores
        assert s["omission_precision"] == 1.0
        assert s["omission_recall"]    == 1.0
        assert s["padding_rate"]       == 0.0

    def test_padding_pulls_in_famous_artists(self):
        from evaluation.probes.probe_b4_omission import _FICTITIOUS, _FAMOUS
        body = json.dumps({"unknown_artists": list(_FICTITIOUS) + list(_FAMOUS)})
        caller = _CannedCaller(_canned_response(body))
        results = runner.run_probe(probe_b4_omission, "gpt-5.4-mini",
                                   openai_call=caller)
        s = results[0].scores
        assert s["omission_recall"] == 1.0
        assert s["padding_rate"]    == 1.0
        # precision drops: only 25 of 30 declared are true positives.
        assert math.isclose(s["omission_precision"], 25 / 30, rel_tol=1e-6)


# ── B-5: format adherence under contradiction ───────────────────────

class TestB5Format:
    def test_bucket_a_clean_refusal(self):
        body = json.dumps({"artists": [], "note": None})
        caller = _CannedCaller(_canned_response(body))
        r = runner.run_probe(probe_b5_format, "gpt-5.4-mini", openai_call=caller)[0]
        assert r.scores["bucket_a"] == 1.0
        assert r.scores["format_healthy"] == 1.0

    def test_bucket_b_refusal_with_note(self):
        body = json.dumps({"artists": [], "note": "Cannot satisfy both constraints."})
        caller = _CannedCaller(_canned_response(body))
        r = runner.run_probe(probe_b5_format, "gpt-5.4-mini", openai_call=caller)[0]
        assert r.scores["bucket_b"] == 1.0
        assert r.scores["format_healthy"] == 1.0

    def test_bucket_e_rule_violation(self):
        # Latin-letter (romaji) names trigger the forbidden-script check.
        body = json.dumps({"artists": ["Cornelius", "Yoshimi", "Cibo Matto",
                                       "Boris", "Melt-Banana"]})
        caller = _CannedCaller(_canned_response(body))
        r = runner.run_probe(probe_b5_format, "gpt-5.4-mini", openai_call=caller)[0]
        assert r.scores["bucket_e"] == 1.0
        assert r.scores["format_healthy"] == 0.0


# ── B-6: self-consistency floor ──────────────────────────────────────

class TestB6Consistency:
    def test_five_calls_zero_sigma_when_responses_identical(self):
        body = json.dumps({
            "playlist": [f"Song {i}" for i in range(10)],
            "rejected_candidates": [
                {"title": f"Rej {i}", "reason": "x"} for i in range(20)
            ],
        })
        caller = _CannedCaller(*[_canned_response(body) for _ in range(5)])
        results = runner.run_probe(probe_b6_consistency, "gpt-5.4-mini",
                                   openai_call=caller)
        assert len(results) == 5
        assert len(caller.calls) == 5
        # All 5 calls are identical → sigma 0 → n_required_for_5pp_signal == 1.
        agg = probe_b6_consistency.aggregate(
            "strict_repeated", [r.scores for r in results],
        )
        assert agg["primary_entries_sigma"] == 0.0
        assert agg["secondary_entries_sigma"] == 0.0
        assert agg["n_required_for_5pp_signal"] == 1.0

    def test_high_variance_drives_n_required_up(self):
        # primary lengths 4..12 — large sigma.
        bodies = [
            json.dumps({"playlist": [f"S{i}" for i in range(L)],
                        "rejected_candidates": [{"title": f"R{i}", "reason": "x"}
                                                 for i in range(20)]})
            for L in (4, 6, 8, 10, 12)
        ]
        caller = _CannedCaller(*[_canned_response(b) for b in bodies])
        results = runner.run_probe(probe_b6_consistency, "gpt-5.4-mini",
                                   openai_call=caller)
        agg = probe_b6_consistency.aggregate(
            "strict_repeated", [r.scores for r in results],
        )
        assert agg["primary_entries_sigma"] > 2.5
        assert agg["n_required_for_5pp_signal"] > 5.0


# ── B-10: cite fidelity ──────────────────────────────────────────────

class TestB10Cite:
    def test_verbatim_rate_one(self):
        body = json.dumps({"picks": [
            {"title": "T1", "cite": "dreamy ambient"},
            {"title": "T2", "cite": "slow-builds"},
            {"title": "T3", "cite": "soft synthesisers"},
            {"title": "T4", "cite": "gentle textures"},
            {"title": "T5", "cite": "calm meditative pace"},
        ]})
        caller = _CannedCaller(_canned_response(body))
        r = runner.run_probe(probe_b10_cite, "gpt-5.4-mini", openai_call=caller)[0]
        assert r.scores["verbatim_rate"] == 1.0

    def test_paraphrasing_drops_score(self):
        # All five 'cite' fields paraphrase rather than substring-quote.
        body = json.dumps({"picks": [
            {"title": "T1", "cite": "dreamlike ambient music"},
            {"title": "T2", "cite": "gradual builds"},
            {"title": "T3", "cite": "soft electronic tones"},
            {"title": "T4", "cite": "easy texture"},
            {"title": "T5", "cite": "tranquil meditative tempo"},
        ]})
        caller = _CannedCaller(_canned_response(body))
        r = runner.run_probe(probe_b10_cite, "gpt-5.4-mini", openai_call=caller)[0]
        assert r.scores["verbatim_rate"] == 0.0
        assert r.scores["any_nonempty_cite"] == 1.0


# ── B-11: empty pool recovery ────────────────────────────────────────

class TestB11EmptyPool:
    def test_messages_load_production_prompt(self):
        msgs = probe_b11_empty_pool.build_messages("empty_pool")
        assert len(msgs) == 2
        sys_content = msgs[0]["content"]
        # Production prompt's HC1 phrase + anti-confabulation guard.
        assert "ANTI-CONFABULATION" in sys_content
        assert "HARD CONSTRAINTS" in sys_content
        # User message has empty approved_artists block.
        user = msgs[1]["content"]
        assert "APPROVED_ARTISTS:" in user
        # No artists between APPROVED_ARTISTS: and TASTE SUMMARY:.
        head, _, _ = user.partition("TASTE SUMMARY:")
        body = head.split("APPROVED_ARTISTS:", 1)[1].strip()
        assert body == "", f"expected empty pool, got: {body!r}"

    def test_bucket_a_empty_playlist_with_reasoning(self):
        body = json.dumps({
            "reasoning": {
                "pool_assessment": "Pool is empty — cannot ground any picks.",
            },
            "playlist": [],
        })
        caller = _CannedCaller(_canned_response(body), _canned_response(body))
        results = runner.run_probe(probe_b11_empty_pool, "gpt-5.4-mini",
                                   openai_call=caller)
        for r in results:
            assert r.scores["bucket_a"] == 1.0
            assert r.scores["pool_recovery_healthy"] == 1.0

    def test_bucket_c_invented_tracks(self):
        body = json.dumps({"playlist": [
            {"artist": "made up band", "track": "imagined song", "energy": 0.5,
             "valence": 0.5, "genres": ["ambient"], "rationale": []}
        ]})
        caller = _CannedCaller(_canned_response(body), _canned_response(body))
        results = runner.run_probe(probe_b11_empty_pool, "gpt-5.4-mini",
                                   openai_call=caller)
        for r in results:
            assert r.scores["bucket_c"] == 1.0
            assert r.scores["pool_recovery_healthy"] == 0.0

    def test_bucket_e_artist_echo_failure(self):
        body = json.dumps({"playlist": [
            {"artist": "ghosts", "track": "ghosts"},          # echo
        ]})
        caller = _CannedCaller(_canned_response(body), _canned_response(body))
        r = runner.run_probe(probe_b11_empty_pool, "gpt-5.4-mini",
                             openai_call=caller)[0]
        assert r.scores["bucket_e"] == 1.0


# ── Fingerprint aggregation ──────────────────────────────────────────

class TestFingerprint:
    def test_aggregate_uses_probe_aggregate_when_present(self):
        # B-6 defines a custom aggregate that returns sigma fields the
        # default mean-aggregator would never produce.
        body = json.dumps({
            "playlist": [f"S{i}" for i in range(10)],
            "rejected_candidates": [{"title": f"R{i}", "reason": "x"}
                                     for i in range(20)],
        })
        caller = _CannedCaller(*[_canned_response(body) for _ in range(5)])
        results = runner.run_probe(probe_b6_consistency, "gpt-5.4-mini",
                                   openai_call=caller)
        fp = runner.aggregate_fingerprint(
            results,
            model="gpt-5.4-mini",
            captured_at="2026-05-12T00:00:00Z",
            probe_modules=[probe_b6_consistency],
        )
        assert len(fp.probes) == 1
        assert "n_required_for_5pp_signal" in fp.probes[0].scores

    def test_fingerprint_totals_match_per_call(self):
        caller = _CannedCaller(
            _canned_response('{"colours": []}', prompt_tokens=100, completion_tokens=50),
            _canned_response('{"colours": []}', prompt_tokens=100, completion_tokens=50),
            _canned_response('{"colours": []}', prompt_tokens=100, completion_tokens=50),
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini",
                                   openai_call=caller)
        fp = runner.aggregate_fingerprint(
            results,
            model="gpt-5.4-mini",
            captured_at="2026-05-12T00:00:00Z",
            probe_modules=[probe_b1_constraint],
        )
        assert fp.total_tokens_in == 300
        assert fp.total_tokens_out == 150
        expected_cost = sum(r.cost_usd for r in results)
        assert math.isclose(fp.total_cost_usd, expected_cost, rel_tol=1e-9)


# ── results_to_jsonl + JSON shape ────────────────────────────────────

class TestResultsToJsonl:
    def test_each_line_is_valid_json(self):
        caller = _CannedCaller(
            _canned_response('{"colours": ["red"]}'),
            _canned_response('{"colours": ["red"]}'),
            _canned_response('{"colours": ["red"]}'),
        )
        results = runner.run_probe(probe_b1_constraint, "gpt-5.4-mini",
                                   openai_call=caller)
        text = runner.results_to_jsonl(results)
        lines = text.splitlines()
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert obj["probe_id"] == "B-1.constraint_grammar"
            assert obj["model"] == "gpt-5.4-mini"


# ── CLI ──────────────────────────────────────────────────────────────

class TestCli:
    def test_default_battery_has_eight_probes(self):
        assert len(cli._BATTERIES["default"]) == 8
        ids = {m.PROBE_ID for m in cli._BATTERIES["default"]}
        assert ids == {
            "B-1.constraint_grammar",
            "B-2.over_constraint_collapse",
            "B-3.confabulation_pressure",
            "B-4.omission_discipline",
            "B-5.format_under_contradiction",
            "B-6.self_consistency_floor",
            "B-10.cite_fidelity",
            "B-11.empty_pool_recovery",
        }

    def test_dry_run_does_not_call_api(self, capsys):
        # No mock needed — we assert via output that the CLI never tried
        # to hit OpenAI. If it did, the chat_completions_create call would
        # raise OpenAIConfigError (no API key in test env) and the test
        # would error out.
        rc = cli.main([
            "--model", "gpt-5.4-mini",
            "--battery", "minimal",
            "--dry-run",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Dry-run plan" in out
        assert "no API calls made" in out

    def test_probes_flag_overrides_battery(self):
        ns = cli._parse_args(["--model", "x", "--probes", "B-1,B-6"])
        mods = cli._select_probes(ns)
        ids = [m.PROBE_ID for m in mods]
        assert ids == ["B-1.constraint_grammar", "B-6.self_consistency_floor"]

    def test_unknown_probe_prefix_errors_loudly(self):
        ns = cli._parse_args(["--model", "x", "--probes", "B-999"])
        with pytest.raises(SystemExit, match="Unknown probe prefix"):
            cli._select_probes(ns)


# ── Diff + regression detection ──────────────────────────────────────


def _fp(model: str, *probe_entries: tuple[str, str, dict]) -> dict:
    """Build a minimal fingerprint dict from (probe_id, variant, scores) tuples."""
    return {
        "model": model,
        "fingerprint_version": 1,
        "captured_at": "2026-05-12T00:00:00Z",
        "probes": [
            {"probe_id": pid, "variant": v, "runs": 1, "scores": dict(s)}
            for (pid, v, s) in probe_entries
        ],
    }


class TestDiffDirectionality:
    def test_no_regressions_when_scores_identical(self):
        a = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                      {"quota_preserved_under_hard": 1.0}))
        regs = diff.detect_regressions(a, a)
        assert regs == []

    def test_regression_on_higher_is_better(self):
        base = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 1.0}))
        new  = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 0.0}))
        regs = diff.detect_regressions(base, new)
        assert len(regs) == 1
        r = regs[0]
        assert r.score == "quota_preserved_under_hard"
        assert r.direction == "higher"
        assert math.isclose(r.delta, -1.0)

    def test_regression_on_lower_is_better(self):
        base = _fp("m", ("B-4.omission_discipline", "mixed", {"padding_rate": 0.0}))
        new  = _fp("m", ("B-4.omission_discipline", "mixed", {"padding_rate": 0.5}))
        regs = diff.detect_regressions(base, new)
        assert len(regs) == 1
        assert regs[0].direction == "lower"

    def test_tolerance_avoids_false_alarm(self):
        # 0.02 drop on a higher-is-better metric, tolerance 0.05 → no regression.
        base = _fp("m", ("B-10.cite_fidelity", "verbatim_substring",
                         {"verbatim_rate": 1.00}))
        new  = _fp("m", ("B-10.cite_fidelity", "verbatim_substring",
                         {"verbatim_rate": 0.98}))
        assert diff.detect_regressions(base, new) == []

    def test_informational_score_never_flags(self):
        # 'returned_count' has no direction set → must never flag.
        base = _fp("m", ("B-1.constraint_grammar", "soft", {"returned_count": 8.0}))
        new  = _fp("m", ("B-1.constraint_grammar", "soft", {"returned_count": 0.0}))
        assert diff.detect_regressions(base, new) == []

    def test_b6_n_required_count_uses_count_tolerance(self):
        # Default 0.05 tol would flag a 1-run shift as regression; the override
        # bumps it to 5.0 so a 1-run drift is ignored but a 6-run drift fires.
        mk = lambda val: _fp("m",
            ("B-6.self_consistency_floor", "strict_repeated",
             {"n_required_for_5pp_signal": val}))
        assert diff.detect_regressions(mk(10), mk(11)) == []      # within 5
        regs = diff.detect_regressions(mk(10), mk(20))
        assert len(regs) == 1                                     # > 5 tolerance


class TestDiffRendering:
    def test_renders_markdown_with_regress_flag(self):
        base = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 1.0}))
        new  = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 0.0}))
        text = diff.render_fingerprint_diff(base, new)
        assert "Fingerprint diff" in text
        assert "REGRESS" in text
        assert "quota_preserved_under_hard" in text

    def test_renders_improved_flag_too(self):
        # Mini regressed from 0.0 → improving back to 1.0 should show ✅.
        base = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 0.0}))
        new  = _fp("m", ("B-1.constraint_grammar", "hard_with_quota",
                         {"quota_preserved_under_hard": 1.0}))
        text = diff.render_fingerprint_diff(base, new)
        assert "improved" in text


class TestBaselinePathing:
    def test_baseline_path_for_simple(self, tmp_path):
        p = diff.baseline_path_for("gpt-5.4-mini", fingerprints_dir=tmp_path)
        assert p.name == "gpt-5.4-mini.v1.json"
        assert p.parent == tmp_path

    def test_load_fingerprint_round_trip(self, tmp_path):
        fp = _fp("m", ("B-1.constraint_grammar", "soft", {"soft_compliance": 1.0}))
        path = tmp_path / "m.v1.json"
        path.write_text(json.dumps(fp), encoding="utf-8")
        loaded = diff.load_fingerprint(path)
        assert loaded["model"] == "m"
        assert loaded["probes"][0]["variant"] == "soft"


# ── Pricing fallback ─────────────────────────────────────────────────

class TestPricing:
    def test_unknown_model_uses_fallback(self):
        cost = runner.estimate_cost_usd("totally-fake-model", 1_000_000, 0)
        # Fallback = gpt-4o pricing $2.50/M input.
        assert math.isclose(cost, 2.50)

    def test_local_llm_zero_tokens_zero_cost(self):
        # Local LLMs typically don't return usage; tokens_in/out=0.
        cost = runner.estimate_cost_usd("ollama/llama3", 0, 0)
        assert cost == 0.0
