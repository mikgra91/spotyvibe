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


# ── E4/E5/E6 (2026-05-07): Last.fm-aware coverage scenarios ──────────

class TestLastfmAwareScenarios:
    """Three new scenarios that exercise the Phase B Last.fm signals.

    They live in the same registry as the legacy + coverage scenarios
    so the existing schema/disjoint tests already cover them; these
    tests pin (a) registry membership and (b) that each one carries
    the load-bearing Last.fm vocabulary in its prose.
    """

    NAMES = (
        "lastfm_tag_weighting",
        "niche_only_strict",
        "post_feedback_tag_regression",
    )

    def test_registry_includes_three_lastfm_scenarios(self):
        from evaluation.scenario import SCENARIOS
        for name in self.NAMES:
            assert name in SCENARIOS, f"missing scenario {name}"

    def test_lastfm_tag_weighting_carries_tag_vocabulary(self):
        """Stage 1 retrieval expects to match these tokens against the
        Last.fm tag inverted index — empty / generic prose would defeat
        the scenario."""
        from evaluation.scenario import LASTFM_TAG_WEIGHTING_SCENARIO
        prose = " ".join(
            LASTFM_TAG_WEIGHTING_SCENARIO.seed_sections.values()
        ).lower()
        for token in ("post-rock", "slowcore", "math rock"):
            assert token in prose, f"missing tag vocabulary: {token}"

    def test_niche_only_strict_carries_popularity_avoid_signals(self):
        """E5 acceptance gate is p95 listeners < 100k. The avoid prose
        must explicitly call out the popularity axis or the LLM has no
        anchor to push back against."""
        from evaluation.scenario import NICHE_ONLY_STRICT_SCENARIO
        avoid = NICHE_ONLY_STRICT_SCENARIO.seed_sections["avoid"].lower()
        # At least two of the popularity-axis hints must be present so
        # a single rephrase can't accidentally water the scenario down.
        signals = ("billboard", "radio", "monthly listeners",
                   "major-label", "viral")
        present = sum(1 for s in signals if s in avoid)
        assert present >= 3, (
            f"niche_only_strict avoid prose only mentions {present} "
            f"popularity signals; need ≥ 3 for the scenario to bite"
        )

    def test_post_feedback_tag_regression_names_disliked_tag_in_refine(self):
        """E6 acceptance gate is "0 tracks where matched Last.fm tag
        overlaps the dislike-tag set". The refine prose must surface
        the disliked tag explicitly so the LLM can absorb it into avoid.
        """
        from evaluation.scenario import POST_FEEDBACK_TAG_REGRESSION_SCENARIO
        refine_avoid = (
            POST_FEEDBACK_TAG_REGRESSION_SCENARIO.refine_sections["avoid"]
            .lower()
        )
        assert "synthwave" in refine_avoid


# ── E2/E3 (2026-05-07): corpus_metrics module ────────────────────────

class _FakeArtistRow:
    """Mimics ArtistRow shape just enough for compute_corpus_metrics."""
    def __init__(self, name: str, lastfm_tags=None, lastfm_listeners=None):
        self.name = name
        self.lastfm_tags = lastfm_tags or []
        self.lastfm_listeners = lastfm_listeners


class _FakeCorpus:
    """Minimal corpus surface — only `artists` + `by_name_normalised`."""
    def __init__(self, rows):
        from core.src.rag.corpus import normalise_name
        self.artists = rows
        self.by_name_normalised = {
            normalise_name(r.name): i for i, r in enumerate(rows)
        }


class TestCorpusMetrics:
    def test_empty_tracks_returns_empty_report(self):
        from evaluation.corpus_metrics import compute_corpus_metrics
        report = compute_corpus_metrics([], None)
        assert report.total_tracks == 0
        assert report.lastfm_tag_coverage_pct is None
        assert report.lastfm_listeners_median is None

    def test_no_corpus_counts_total_only(self):
        from evaluation.corpus_metrics import compute_corpus_metrics
        tracks = [{"artist": "X", "track": "Y"},
                  {"artist": "Z", "track": "W"}]
        report = compute_corpus_metrics(tracks, None)
        assert report.total_tracks == 2
        assert report.matched_in_corpus == 0
        assert report.lastfm_tag_coverage_pct is None

    def test_full_lastfm_coverage_passes_gate(self):
        from evaluation.corpus_metrics import compute_corpus_metrics
        rows = [
            _FakeArtistRow("Mogwai", lastfm_tags=["post-rock"], lastfm_listeners=900_000),
            _FakeArtistRow("Boards of Canada", lastfm_tags=["idm"], lastfm_listeners=600_000),
            _FakeArtistRow("Slint", lastfm_tags=["math rock"], lastfm_listeners=400_000),
            _FakeArtistRow("Codeine", lastfm_tags=["slowcore"], lastfm_listeners=200_000),
        ]
        corpus = _FakeCorpus(rows)
        tracks = [{"artist": r.name, "track": "T"} for r in rows]
        report = compute_corpus_metrics(tracks, corpus)
        assert report.matched_in_corpus == 4
        assert report.lastfm_tag_populated == 4
        assert report.lastfm_tag_coverage_pct == 1.0
        assert report.passed_tag_coverage is True
        assert report.lastfm_listeners_sample_size == 4
        # Median of [200k, 400k, 600k, 900k] → 500k.
        assert report.lastfm_listeners_median == 500_000

    def test_partial_coverage_below_gate_flags_fail(self):
        from evaluation.corpus_metrics import compute_corpus_metrics
        rows = [
            _FakeArtistRow("A", lastfm_tags=["x"]),
            _FakeArtistRow("B", lastfm_tags=[]),    # unenriched
            _FakeArtistRow("C", lastfm_tags=[]),    # unenriched
            _FakeArtistRow("D", lastfm_tags=["x"]),
        ]
        corpus = _FakeCorpus(rows)
        tracks = [{"artist": r.name, "track": "T"} for r in rows]
        report = compute_corpus_metrics(tracks, corpus)
        # 2 of 4 = 50 % < 75 % gate.
        assert report.lastfm_tag_coverage_pct == 0.5
        assert report.passed_tag_coverage is False

    def test_unmatched_artists_excluded_from_coverage(self):
        """Spotify-only artists shouldn't drag coverage down — they're
        a corpus-miss problem, not an enrichment problem."""
        from evaluation.corpus_metrics import compute_corpus_metrics
        rows = [_FakeArtistRow("InCorpus", lastfm_tags=["x"])]
        corpus = _FakeCorpus(rows)
        tracks = [
            {"artist": "InCorpus", "track": "T"},
            {"artist": "NotInCorpus", "track": "U"},
        ]
        report = compute_corpus_metrics(tracks, corpus)
        assert report.total_tracks == 2
        assert report.matched_in_corpus == 1
        # Coverage is over MATCHED rows, not total → 100 %.
        assert report.lastfm_tag_coverage_pct == 1.0

    def test_zero_listener_artists_excluded_from_distribution(self):
        from evaluation.corpus_metrics import compute_corpus_metrics
        rows = [
            _FakeArtistRow("A", lastfm_listeners=0),     # excluded
            _FakeArtistRow("B", lastfm_listeners=None),  # excluded
            _FakeArtistRow("C", lastfm_listeners=10_000),
            _FakeArtistRow("D", lastfm_listeners=50_000),
        ]
        corpus = _FakeCorpus(rows)
        tracks = [{"artist": r.name, "track": "T"} for r in rows]
        report = compute_corpus_metrics(tracks, corpus)
        assert report.lastfm_listeners_sample_size == 2
        assert report.lastfm_listeners_median == 30_000  # median of [10k, 50k]

    def test_to_json_round_trip(self):
        from evaluation.corpus_metrics import CorpusMetricsReport
        r = CorpusMetricsReport(
            total_tracks=10, matched_in_corpus=8,
            lastfm_tag_populated=6, lastfm_tag_coverage_pct=0.75,
            lastfm_listeners_median=12_000,
            lastfm_listeners_p95=98_000,
            lastfm_listeners_sample_size=8,
        )
        d = r.to_json()
        assert d["lastfm_tag_coverage_pct"] == 0.75
        assert d["passed_tag_coverage"] is True  # at the gate
        assert d["lastfm_listeners_p95"] == 98_000


class TestCorpusMetricsFieldsOnResult:
    def test_default_corpus_metrics_fields_present(self):
        from evaluation.harness import ModelRunResult
        r = ModelRunResult(
            model="gpt-x", iteration=0, started_at="2026-05-07T00:00:00Z",
        )
        assert r.corpus_metrics_a is None
        assert r.corpus_metrics_b is None

    def test_corpus_metrics_serialise_through_asdict(self):
        from dataclasses import asdict
        from evaluation.harness import ModelRunResult
        r = ModelRunResult(
            model="gpt-x", iteration=0, started_at="2026-05-07T00:00:00Z",
            corpus_metrics_a={"lastfm_tag_coverage_pct": 0.8},
        )
        d = asdict(r)
        assert d["corpus_metrics_a"]["lastfm_tag_coverage_pct"] == 0.8
        assert d["corpus_metrics_b"] is None


class TestExtractCorpusMetrics:
    def test_empty_tracks_returns_none(self):
        from evaluation.harness import _extract_corpus_metrics
        assert _extract_corpus_metrics([]) is None

    def test_returns_dict_with_no_corpus(self, monkeypatch):
        """When no corpus is loaded, still returns a structured rollup
        (so the report shows total_tracks even if matched=0)."""
        from evaluation.harness import _extract_corpus_metrics
        from core.src import suggestions
        monkeypatch.setattr(suggestions, "get_rag_corpus", lambda: None)
        result = _extract_corpus_metrics([{"artist": "X", "track": "Y"}])
        assert result is not None
        assert result["total_tracks"] == 1
        assert result["matched_in_corpus"] == 0



