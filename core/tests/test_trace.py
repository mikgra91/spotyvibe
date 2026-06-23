"""Unit tests for ``core.src.trace`` — F9 per-run trace bundle.

Pin the singleton lifecycle (start / record / append / finalize),
DEBUG_MODE gating (off → no-op, on → captures), and serialisation
fail-safes so a future refactor cannot silently break the diagnostic
that every later P0 fix depends on for verification.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _reset_trace_singleton():
    """Each test starts with a clean singleton."""
    from core.src import trace
    trace.reset_for_test()
    yield
    trace.reset_for_test()


@pytest.fixture
def debug_on(monkeypatch):
    monkeypatch.setenv("DEBUG_MODE", "1")
    yield


@pytest.fixture
def debug_off(monkeypatch):
    monkeypatch.setenv("DEBUG_MODE", "0")
    yield


class TestTraceLifecycle:
    def test_no_op_when_debug_off(self, debug_off):
        from core.src import trace
        trace.start_trace("run-x", profile={"a": 1})
        assert trace.is_active() is False
        trace.record("stage1", {"data": "ignored"})
        trace.append("spotify", {"q": "x"})
        assert trace.finalize_trace() is None

    def test_active_after_start_when_debug_on(self, debug_on):
        from core.src import trace
        trace.start_trace("run-1", profile={"a": 1})
        assert trace.is_active() is True

    def test_record_overwrites_same_stage(self, debug_on):
        from core.src import trace
        trace.start_trace("run-1")
        trace.record("stage2_response", {"approved": ["A"]})
        trace.record("stage2_response", {"approved": ["A", "B"]})
        # Pull internals via finalize to verify
        from core.src.trace import _CURRENT  # noqa: PLC2701 — test inspection
        assert _CURRENT.stages["stage2_response"] == {"approved": ["A", "B"]}

    def test_append_builds_list(self, debug_on):
        from core.src import trace
        trace.start_trace("run-1")
        trace.append("spotify_search", {"q": "track 1", "found": True})
        trace.append("spotify_search", {"q": "track 2", "found": False})
        from core.src.trace import _CURRENT
        bucket = _CURRENT.stages["spotify_search"]
        assert len(bucket) == 2
        assert bucket[0]["q"] == "track 1"
        assert bucket[1]["found"] is False

    def test_append_and_record_preserve_independent_buckets(self, debug_on):
        from core.src import trace
        trace.start_trace("run-1")
        trace.record("stage1_query", {"tags": {"rock": 2.0}})
        trace.append("spotify_search", {"q": "x"})
        from core.src.trace import _CURRENT
        assert "stage1_query" in _CURRENT.stages
        assert isinstance(_CURRENT.stages["spotify_search"], list)


class TestFinalize:
    def test_finalize_writes_json_to_run_dir(self, debug_on, tmp_path):
        from core.src import trace
        trace.start_trace("run-abc", profile={"name": "test"})
        trace.record("stage1_candidates", [{"name": "A", "score": 1.5}])
        trace.append("spotify_search", {"q": "track 1"})
        out = trace.finalize_trace(base_dir=tmp_path)
        assert out is not None
        assert out.name == "trace.json"
        assert out.parent.name == "run-abc"
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["run_id"] == "run-abc"
        assert payload["profile"]["name"] == "test"
        assert payload["stages"]["stage1_candidates"][0]["name"] == "A"
        assert payload["stages"]["spotify_search"][0]["q"] == "track 1"
        assert isinstance(payload["duration_s"], (int, float))
        # singleton must clear so the next run starts fresh
        assert trace.is_active() is False

    def test_finalize_returns_none_when_no_run(self, debug_on, tmp_path):
        from core.src import trace
        # No start_trace call — finalize must short-circuit.
        assert trace.finalize_trace(base_dir=tmp_path) is None

    def test_finalize_clears_even_on_write_failure(self, debug_on, tmp_path):
        """If the write fails, the singleton must still clear so the
        next run's start_trace doesn't pick up the stale bundle."""
        from core.src import trace
        trace.start_trace("run-fail", profile={"x": 1})
        # Point at a path where write will fail (a file blocking the dir)
        block = tmp_path / "blocker"
        block.write_text("not a directory")
        out = trace.finalize_trace(base_dir=block)
        assert out is None  # write failed
        assert trace.is_active() is False

    def test_writes_to_default_dir_when_no_base_dir(
        self, debug_on, tmp_path, monkeypatch,
    ):
        """Default DEBUG_TRACE_DIR resolution path."""
        from core.src import trace
        # Patch the lazy import inside finalize_trace
        import config as cfg
        monkeypatch.setattr(cfg, "DEBUG_TRACE_DIR", tmp_path / "debug")
        trace.start_trace("run-default")
        out = trace.finalize_trace()
        assert out is not None
        assert (tmp_path / "debug" / "run-default" / "trace.json").exists()


class TestSerialisationSafety:
    def test_unserialisable_payload_does_not_raise(self, debug_on, tmp_path):
        """A trace.record must NEVER break a generation run, even if the
        caller hands it something json can't encode."""
        from core.src import trace

        class Weird:
            def __repr__(self):
                return "<Weird>"

        trace.start_trace("run-weird")
        trace.record("stage1_candidates", Weird())
        trace.append("spotify_search", Weird())
        out = trace.finalize_trace(base_dir=tmp_path)
        assert out is not None
        payload = json.loads(out.read_text(encoding="utf-8"))
        # Both got coerced to a string-ish form — exact format is
        # internal, just verify nothing was dropped silently.
        assert "stage1_candidates" in payload["stages"]
        assert "spotify_search" in payload["stages"]

    def test_record_clones_so_caller_mutation_does_not_leak(
        self, debug_on, tmp_path,
    ):
        """If we held a live reference, the caller mutating the dict
        after record() would corrupt the trace. Verify a clone is taken."""
        from core.src import trace
        trace.start_trace("run-clone")
        live = {"items": [1, 2, 3]}
        trace.record("stage1_candidates", live)
        live["items"].append(99)  # caller mutates
        out = trace.finalize_trace(base_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["stages"]["stage1_candidates"]["items"] == [1, 2, 3]


class TestProfileSnapshot:
    def test_profile_is_snapshotted_at_start(self, debug_on, tmp_path):
        from core.src import trace
        prof = {"name": "v1", "feedback": {"disliked": []}}
        trace.start_trace("run-p", profile=prof)
        # Mutate after start — snapshot must be unchanged
        prof["name"] = "v2"
        prof["feedback"]["disliked"].append({"a": "b"})
        out = trace.finalize_trace(base_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["profile"]["name"] == "v1"
        assert payload["profile"]["feedback"]["disliked"] == []

    def test_no_profile_handled(self, debug_on, tmp_path):
        from core.src import trace
        trace.start_trace("run-noprof")
        out = trace.finalize_trace(base_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["profile"] is None


# ── F9 capture-from-callsite integration ─────────────────────────────

class TestRetrievalCapture:
    """End-to-end: ensure retrieve_candidates writes Stage 1 sections
    when tracing is active. Guards against a future refactor that
    silently drops the capture wiring."""

    def _build_corpus(self, tmp_path):
        import gzip
        from core.src.rag.corpus import RagCorpus
        path = tmp_path / "artists.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "mbid": "a1", "name": "Indie Band",
                "tags": ["indie rock", "post-punk"],
                "tag_weights": [5, 3], "listener_popularity": 0.5,
            }) + "\n")
            fh.write(json.dumps({
                "mbid": "a2", "name": "Other Band",
                "tags": ["indie rock", "art rock"],
                "tag_weights": [4, 2], "listener_popularity": 0.4,
            }) + "\n")
        return RagCorpus.load(path)

    def test_stage1_sections_captured_when_active(self, debug_on, tmp_path):
        from core.src import trace
        from core.src.rag.retrieval import retrieve_candidates
        corpus = self._build_corpus(tmp_path)

        trace.start_trace("integ-1")
        profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
        retrieve_candidates(corpus, profile, target_size=5)

        out = trace.finalize_trace(base_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        stages = payload["stages"]
        assert "stage1_query" in stages
        assert "stage1_avoid" in stages
        assert "stage1_candidates" in stages
        assert isinstance(stages["stage1_query"]["tags"], dict)
        assert isinstance(stages["stage1_candidates"], list)
        assert len(stages["stage1_candidates"]) >= 1
        assert stages["stage1_candidates"][0]["name"] in {"Indie Band", "Other Band"}

    def test_stage1_no_capture_when_inactive(self, debug_off, tmp_path):
        """No active trace → retrieve_candidates must not crash and
        nothing leaks into the singleton."""
        from core.src import trace
        from core.src.rag.retrieval import retrieve_candidates
        corpus = self._build_corpus(tmp_path)
        # No start_trace call; debug off.
        profile = {"preferences": {"must_have": ["indie rock"], "avoid": []}}
        retrieve_candidates(corpus, profile, target_size=5)
        assert trace.is_active() is False


# ── E1 (2026-05-06) per-stage metrics rollup ─────────────────────────

class TestStageMetrics:
    """Pin the time_stage / add_tokens / stage_metrics_record contract.

    These three helpers are the load-bearing surface for the E1 eval
    telemetry. The harness reads `stage_metrics` straight out of the
    trace bundle JSON — silent breakage here would invalidate every
    later perf comparison without raising.
    """

    def test_time_stage_no_op_when_inactive(self, debug_off):
        """Without an active trace the CM still yields and never raises."""
        from core.src import trace
        # Trace not started; CM is a pass-through.
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        assert trace.is_active() is False

    def test_time_stage_accumulates_duration_and_calls(self, debug_on):
        from core.src import trace
        trace.start_trace("run-time")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        from core.src.trace import _CURRENT
        m = _CURRENT.stage_metrics[trace.STAGE_RAG_RETRIEVE]
        assert m["calls"] == 2
        assert m["duration_s"] >= 0.0
        # tokens stay zero since add_tokens wasn't called
        assert m["tokens_in"] == 0
        assert m["tokens_out"] == 0

    def test_add_tokens_accumulates(self, debug_on):
        from core.src import trace
        trace.start_trace("run-tok")
        trace.add_tokens(trace.STAGE_STAGE2_AVOID, 100, 20)
        trace.add_tokens(trace.STAGE_STAGE2_AVOID, 50, None)
        from core.src.trace import _CURRENT
        m = _CURRENT.stage_metrics[trace.STAGE_STAGE2_AVOID]
        assert m["tokens_in"] == 150
        assert m["tokens_out"] == 20

    def test_stage_metrics_record_one_shot(self, debug_on):
        from core.src import trace
        trace.start_trace("run-rec")
        trace.stage_metrics_record(
            trace.STAGE_STAGE3_SELECT,
            duration_s=0.45,
            tokens_in=1234,
            tokens_out=567,
        )
        trace.stage_metrics_record(
            trace.STAGE_STAGE3_SELECT,
            duration_s=0.30,
            tokens_in=900,
            tokens_out=400,
        )
        from core.src.trace import _CURRENT
        m = _CURRENT.stage_metrics[trace.STAGE_STAGE3_SELECT]
        assert m["calls"] == 2
        assert m["duration_s"] == 0.75
        assert m["tokens_in"] == 1234 + 900
        assert m["tokens_out"] == 567 + 400

    def test_stage_metrics_record_none_skips_field(self, debug_on):
        """Each arg may be None to skip that field (callers without
        usage data still increment calls + duration)."""
        from core.src import trace
        trace.start_trace("run-partial")
        trace.stage_metrics_record(
            trace.STAGE_SPOTIFY_VERIFY,
            duration_s=2.0,
        )
        from core.src.trace import _CURRENT
        m = _CURRENT.stage_metrics[trace.STAGE_SPOTIFY_VERIFY]
        assert m["calls"] == 1
        assert m["duration_s"] == 2.0
        assert m["tokens_in"] == 0  # untouched, default zero

    def test_metrics_serialised_in_finalize(self, debug_on, tmp_path):
        from core.src import trace
        trace.start_trace("run-fin")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        trace.stage_metrics_record(
            trace.STAGE_STAGE2_AVOID, duration_s=0.1,
            tokens_in=10, tokens_out=5,
        )
        out = trace.finalize_trace(base_dir=tmp_path)
        assert out is not None
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "stage_metrics" in payload
        assert trace.STAGE_RAG_RETRIEVE in payload["stage_metrics"]
        s2 = payload["stage_metrics"][trace.STAGE_STAGE2_AVOID]
        assert s2["tokens_in"] == 10
        assert s2["tokens_out"] == 5

    def test_no_capture_when_inactive(self, debug_off):
        """All three helpers no-op without an active trace."""
        from core.src import trace
        # Trace not started.
        with trace.time_stage("anything"):
            pass
        trace.add_tokens("x", 1, 1)
        trace.stage_metrics_record("y", duration_s=1.0, tokens_in=1, tokens_out=1)
        # Nothing crashed; no singleton was created.
        assert trace.is_active() is False


class TestAlwaysOnMetrics:
    """M3 (2026-05-07): stage_metrics are collected even when DEBUG_MODE
    is off so the perf-log can record per-run latency on production
    deployments. Independent of the heavy trace bundle (which still
    requires DEBUG_MODE for the disk write)."""

    def test_metrics_collected_with_debug_off(self, debug_off):
        from core.src import trace
        trace.start_trace("run-prod")
        # No heavy trace bundle exists ...
        assert trace.is_active() is False
        # ... but the lightweight metrics accumulator does capture.
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        trace.stage_metrics_record(
            trace.STAGE_STAGE3_SELECT,
            duration_s=0.123, tokens_in=10, tokens_out=5,
        )
        trace.add_tokens(trace.STAGE_STAGE2_AVOID, 100, 50)
        m = trace.current_stage_metrics()
        assert trace.STAGE_RAG_RETRIEVE in m
        assert m[trace.STAGE_RAG_RETRIEVE]["calls"] == 1
        assert m[trace.STAGE_STAGE3_SELECT]["duration_s"] == 0.123
        assert m[trace.STAGE_STAGE3_SELECT]["tokens_in"] == 10
        assert m[trace.STAGE_STAGE2_AVOID]["tokens_in"] == 100
        assert trace.current_run_id() == "run-prod"

    def test_finalize_clears_metrics(self, debug_off):
        from core.src import trace
        trace.start_trace("run-fin")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        assert trace.current_stage_metrics()  # populated
        trace.finalize_trace()
        assert trace.current_stage_metrics() == {}
        assert trace.current_run_id() is None

    def test_start_resets_previous_metrics(self, debug_off):
        from core.src import trace
        trace.start_trace("run-1")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        trace.start_trace("run-2")
        m = trace.current_stage_metrics()
        assert m == {}  # cleared on new start
        assert trace.current_run_id() == "run-2"

    def test_metrics_returned_as_deep_copy(self, debug_off):
        from core.src import trace
        trace.start_trace("run-deep")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        m1 = trace.current_stage_metrics()
        m1[trace.STAGE_RAG_RETRIEVE]["calls"] = 999
        m2 = trace.current_stage_metrics()
        assert m2[trace.STAGE_RAG_RETRIEVE]["calls"] == 1

    def test_no_run_id_no_capture(self, debug_off):
        from core.src import trace
        # No start_trace call → metrics stay empty.
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        trace.add_tokens(trace.STAGE_STAGE2_AVOID, 1, 1)
        assert trace.current_stage_metrics() == {}
        assert trace.current_run_id() is None

    def test_debug_on_writes_to_both(self, debug_on, tmp_path):
        """When DEBUG_MODE is on, both the trace bundle AND the always-on
        accumulator carry the metrics — they must agree."""
        from core.src import trace
        trace.start_trace("run-both")
        with trace.time_stage(trace.STAGE_RAG_RETRIEVE):
            pass
        trace.add_tokens(trace.STAGE_RAG_RETRIEVE, 5, 3)
        always_on = trace.current_stage_metrics()
        from core.src.trace import _CURRENT
        bundle_metrics = _CURRENT.stage_metrics
        assert always_on[trace.STAGE_RAG_RETRIEVE]["tokens_in"] == 5
        assert bundle_metrics[trace.STAGE_RAG_RETRIEVE]["tokens_in"] == 5
