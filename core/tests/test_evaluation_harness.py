"""Pure-function tests for evaluation/harness.py helpers.

The harness itself is a real-billing operation gated on explicit
invocation per evaluation/README.md. These tests cover only the
deterministic helpers (P1 #5 completion gate) so a regression in the
gate logic surfaces in the normal CI run, not the manual eval pass.
"""
from __future__ import annotations

import pytest


# ── P1 #5: completion gate ───────────────────────────────────────────

class TestCompletionStatus:
    def test_empty_returns_empty(self):
        from evaluation.harness import _completion_status
        assert _completion_status(0, 30) == "empty"

    def test_above_threshold_returns_ok(self):
        from evaluation.harness import _completion_status
        # 30 of 30 → 100 %
        assert _completion_status(30, 30) == "ok"
        # 29 of 30 → 96.7 %, above the 95 % threshold
        assert _completion_status(29, 30) == "ok"

    def test_at_exact_threshold_returns_ok(self):
        from evaluation.harness import _completion_status
        # 0.95 * 20 = 19 → exactly 19 should pass
        assert _completion_status(19, 20) == "ok"

    def test_just_below_threshold_returns_under(self):
        from evaluation.harness import _completion_status
        # 28 of 30 → 93.3 % < 95 %
        assert _completion_status(28, 30) == "under"
        # 18 of 20 → 90 % < 95 %
        assert _completion_status(18, 20) == "under"

    def test_one_track_against_large_target_is_under(self):
        from evaluation.harness import _completion_status
        # The 'under_filled' anti-confab status historically masked
        # this — pure-count gate now flags it.
        assert _completion_status(1, 30) == "under"

    def test_zero_target_does_not_divide_by_zero(self):
        from evaluation.harness import _completion_status
        assert _completion_status(5, 0) == "ok"

    def test_threshold_constant_pinned_at_95_pct(self):
        from evaluation.harness import COMPLETION_THRESHOLD
        # next-steps.md fixes the 0.95 floor explicitly. Bumping it
        # here without changing next-steps.md is a silent eval-policy
        # change; pin it so the change has to be intentional.
        assert COMPLETION_THRESHOLD == pytest.approx(0.95)


# ── P1 #5: ModelRunResult fields surface the gate ────────────────────

class TestCompletionFieldsOnResult:
    def test_default_completion_status_fields_present(self):
        from evaluation.harness import ModelRunResult
        r = ModelRunResult(model="gpt-x", iteration=0, started_at="now")
        # Both must default to 'skipped' so a crash before the playlist
        # step doesn't surface as a passing 'ok' completion.
        assert r.completion_a_status == "skipped"
        assert r.completion_b_status == "skipped"


# ── P1 #7: F9 trace-bundle copy ──────────────────────────────────────

class TestCopyTraceBundle:
    def test_copies_existing_bundle_with_label(self, tmp_path):
        from evaluation.harness import _copy_trace_bundle
        run_id = "run-abc"
        sandbox = tmp_path / "sandbox"
        bundle_dir = sandbox / "debug" / run_id
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "trace.json").write_text('{"run_id": "run-abc"}', encoding="utf-8")
        dest = tmp_path / "results" / "gpt-x-iter0"
        out = _copy_trace_bundle(sandbox, run_id, dest, "A")
        assert out is not None
        copied = dest / "trace_A.json"
        assert copied.exists()
        assert '"run_id": "run-abc"' in copied.read_text(encoding="utf-8")

    def test_returns_none_when_bundle_missing(self, tmp_path):
        from evaluation.harness import _copy_trace_bundle
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        dest = tmp_path / "results"
        # No debug/<run_id>/trace.json — DEBUG_MODE off path.
        assert _copy_trace_bundle(sandbox, "run-missing", dest, "A") is None
        # Destination NOT created when there's nothing to copy.
        assert not (dest / "trace_A.json").exists()

    def test_returns_none_when_run_id_falsy(self, tmp_path):
        from evaluation.harness import _copy_trace_bundle
        assert _copy_trace_bundle(tmp_path, None, tmp_path, "A") is None
        assert _copy_trace_bundle(tmp_path, "", tmp_path, "A") is None

    def test_label_is_baked_into_filename(self, tmp_path):
        """A and B bundles for the same run must land at distinct paths."""
        from evaluation.harness import _copy_trace_bundle
        sandbox = tmp_path / "sandbox"
        for rid, label in (("rA", "A"), ("rB", "B")):
            d = sandbox / "debug" / rid
            d.mkdir(parents=True)
            (d / "trace.json").write_text(f'{{"id":"{rid}"}}', encoding="utf-8")
        dest = tmp_path / "results"
        a = _copy_trace_bundle(sandbox, "rA", dest, "A")
        b = _copy_trace_bundle(sandbox, "rB", dest, "B")
        assert a and b and a != b
        assert (dest / "trace_A.json").exists()
        assert (dest / "trace_B.json").exists()


# ── E1 (2026-05-06): per-stage rollup extraction ─────────────────────

class TestExtractStageMetrics:
    """Pin _extract_stage_metrics() — the bridge between trace.py's
    on-disk JSON and the harness's ModelRunResult fields."""

    def test_returns_metrics_when_present(self, tmp_path):
        import json
        from evaluation.harness import _extract_stage_metrics
        bundle = tmp_path / "trace_A.json"
        payload = {
            "run_id": "x",
            "stage_metrics": {
                "rag_retrieve": {"duration_s": 0.12, "calls": 1,
                                  "tokens_in": 0, "tokens_out": 0},
                "stage3_select": {"duration_s": 1.5, "calls": 3,
                                   "tokens_in": 9000, "tokens_out": 1200},
            },
        }
        bundle.write_text(json.dumps(payload), encoding="utf-8")
        out = _extract_stage_metrics(str(bundle))
        assert out is not None
        assert "rag_retrieve" in out
        assert out["stage3_select"]["calls"] == 3
        assert out["stage3_select"]["tokens_in"] == 9000

    def test_returns_none_for_missing_path(self):
        from evaluation.harness import _extract_stage_metrics
        assert _extract_stage_metrics(None) is None
        assert _extract_stage_metrics("") is None

    def test_returns_none_for_missing_file(self, tmp_path):
        from evaluation.harness import _extract_stage_metrics
        # Path that doesn't exist on disk.
        assert _extract_stage_metrics(str(tmp_path / "nope.json")) is None

    def test_returns_none_when_bundle_lacks_field(self, tmp_path):
        """Legacy bundles (pre-E1) have no stage_metrics key — caller
        must get None, not an empty dict, so the comparison renderer's
        `if any(...)` guard skips the section cleanly."""
        import json
        from evaluation.harness import _extract_stage_metrics
        bundle = tmp_path / "old.json"
        bundle.write_text(json.dumps({"run_id": "x", "stages": {}}),
                          encoding="utf-8")
        assert _extract_stage_metrics(str(bundle)) is None

    def test_returns_none_when_metrics_empty(self, tmp_path):
        """An empty dict is treated the same as missing — keeps the
        renderer's guard logic single-branch."""
        import json
        from evaluation.harness import _extract_stage_metrics
        bundle = tmp_path / "empty.json"
        bundle.write_text(json.dumps({"stage_metrics": {}}),
                          encoding="utf-8")
        assert _extract_stage_metrics(str(bundle)) is None

    def test_returns_none_on_malformed_json(self, tmp_path):
        from evaluation.harness import _extract_stage_metrics
        bundle = tmp_path / "broken.json"
        bundle.write_text("{not json", encoding="utf-8")
        assert _extract_stage_metrics(str(bundle)) is None


class TestStageMetricsFieldsOnResult:
    """ModelRunResult must carry the new fields with safe defaults."""

    def test_default_stage_metrics_fields_present(self):
        from evaluation.harness import ModelRunResult
        r = ModelRunResult(
            model="gpt-x", iteration=0, started_at="2026-05-06T00:00:00Z",
        )
        assert r.stage_metrics_a is None
        assert r.stage_metrics_b is None

    def test_stage_metrics_fields_serialise_through_asdict(self):
        from dataclasses import asdict
        from evaluation.harness import ModelRunResult
        r = ModelRunResult(
            model="gpt-x", iteration=0, started_at="2026-05-06T00:00:00Z",
            stage_metrics_a={"rag_retrieve": {"duration_s": 0.1, "calls": 1,
                                                "tokens_in": 0, "tokens_out": 0}},
        )
        d = asdict(r)
        assert d["stage_metrics_a"]["rag_retrieve"]["duration_s"] == 0.1
        assert d["stage_metrics_b"] is None


# ── P1 #6: stateful profile import via Scenario.seed_profile_path ────

class TestSeedProfileFixture:
    def test_scenario_field_defaults_to_none(self):
        """Existing scenarios stay clean-room (no fixture path)."""
        from evaluation.scenario import (DEFAULT_SCENARIO,
                                         REGRESSION_JAPANESE_SCENARIO)
        assert DEFAULT_SCENARIO.seed_profile_path is None
        assert REGRESSION_JAPANESE_SCENARIO.seed_profile_path is None

    def test_scenario_field_accepts_path(self, tmp_path):
        from dataclasses import replace
        from evaluation.scenario import DEFAULT_SCENARIO
        fixture = tmp_path / "fixture.json"
        fixture.write_text("{}", encoding="utf-8")
        scn = replace(DEFAULT_SCENARIO, seed_profile_path=fixture)
        assert scn.seed_profile_path == fixture
        # Frozen dataclass — original is unchanged.
        assert DEFAULT_SCENARIO.seed_profile_path is None

    def test_step_seed_profile_imports_file(self, tmp_path):
        """_step_seed_profile must call profile_mod.import_profile_dict
        with the JSON payload and return profile_chars in the status."""
        from dataclasses import replace
        from evaluation.harness import _step_seed_profile
        from evaluation.scenario import DEFAULT_SCENARIO

        fixture = tmp_path / "aged.json"
        payload = {
            "preferences": {"must_have": ["jazz"], "avoid": ["pop"]},
            "feedback": {"disliked_tracks": [
                {"artist": "X", "track": "Y", "reason": "bad"},
            ]},
        }
        import json as _json
        fixture.write_text(_json.dumps(payload), encoding="utf-8")
        scn = replace(DEFAULT_SCENARIO, seed_profile_path=fixture)

        captured: dict = {}

        class _FakeProfileMod:
            @staticmethod
            def import_profile_dict(d):
                captured["payload"] = d
                # Production import_profile_dict returns the merged
                # profile; mimic that shape.
                return {**d, "merged": True}

        result = _step_seed_profile(_FakeProfileMod, scn)
        assert result["status"] == "ok"
        assert result["profile_chars"] > 0
        # Imported the exact payload we wrote.
        assert captured["payload"]["preferences"]["must_have"] == ["jazz"]
        assert captured["payload"]["feedback"]["disliked_tracks"][0]["artist"] == "X"

    def test_step_seed_profile_raises_on_missing_file(self, tmp_path):
        from dataclasses import replace
        from evaluation.harness import _step_seed_profile
        from evaluation.scenario import DEFAULT_SCENARIO
        scn = replace(DEFAULT_SCENARIO,
                      seed_profile_path=tmp_path / "does-not-exist.json")

        class _FakeProfileMod:
            @staticmethod
            def import_profile_dict(d):
                raise AssertionError("should not be called")

        with pytest.raises(FileNotFoundError, match="seed_profile fixture not found"):
            _step_seed_profile(_FakeProfileMod, scn)


# ── P1 #6: new coverage scenarios ────────────────────────────────────

class TestCoverageScenarios:
    """Scenario registry must include the six coverage fixtures so a typo
    in a scenario name fails loud at the get_scenario step."""

    def test_registry_includes_six_new_scenarios(self):
        from evaluation.scenario import SCENARIOS
        for name in (
            "ambient_instrumental_focus",
            "boom_bap_90s",
            "brazilian_samba_funk",
            "club_techno_strict",
            "original_recordings_only",
            "contradictory_profile",
        ):
            assert name in SCENARIOS, f"missing scenario {name}"

    def test_each_scenario_has_required_seed_fields(self):
        from evaluation.scenario import SCENARIOS
        new_names = (
            "ambient_instrumental_focus", "boom_bap_90s",
            "brazilian_samba_funk", "club_techno_strict",
            "original_recordings_only", "contradictory_profile",
        )
        for name in new_names:
            scn = SCENARIOS[name]
            for required in ("core_description", "must_have",
                              "soft_preferences", "avoid"):
                assert scn.seed_sections.get(required, "").strip(), \
                    f"{name}: seed_sections.{required} is empty"
            assert scn.analysis_artist
            assert scn.analysis_track
            assert scn.like_indices
            assert scn.dislike_indices

    def test_feedback_indices_are_disjoint(self):
        from evaluation.scenario import SCENARIOS
        for name, scn in SCENARIOS.items():
            likes = set(scn.like_indices)
            dislikes = set(scn.dislike_indices)
            assert likes.isdisjoint(dislikes), \
                f"{name}: like/dislike index collision {likes & dislikes}"
