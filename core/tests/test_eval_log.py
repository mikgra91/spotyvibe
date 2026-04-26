"""Tests for ``core/src/eval_log.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.src.eval_log import (compute_profile_hash, log_batch_outcome,
                               log_batch_summary, compute_config_signature,
                               log_stage2_summary, log_profile_update_summary,
                               log_analysis_summary)


@pytest.fixture
def tmp_log(tmp_path: Path) -> Path:
    return tmp_path / "eval.jsonl"


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_no_op_when_debug_off(tmp_log):
    log_batch_outcome(
        run_id="r1", batch_num=1, model="m", rag_enabled=False,
        rag_corpus_meta_path=None, candidate_pool_names=None,
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=[],
        eval_log_path=tmp_log, debug_mode=False,
    )
    assert not tmp_log.exists()


def test_writes_one_row_per_track(tmp_log):
    log_batch_outcome(
        run_id="r1", batch_num=2, model="gpt-x",
        rag_enabled=True, rag_corpus_meta_path=None,
        candidate_pool_names=["Massive Attack", "Portishead"],
        profile_id="prof-a",
        profile={"must_have": ["trip-hop"]},
        suggested_playlist=[
            {"artist": "Massive Attack", "track": "Teardrop",
             "rationale": [{"type": "profile_match", "arg": "trip-hop"}]},
            {"artist": "Hallucinated Band", "track": "Imaginary Song"},
        ],
        found_keys=["massive attack - teardrop"],
        eval_log_path=tmp_log, debug_mode=True,
    )
    rows = _read_rows(tmp_log)
    assert len(rows) == 2
    found_row, miss_row = rows
    assert found_row["artist"] == "massive attack"
    assert found_row["found_on_spotify"] is True
    assert found_row["in_candidate_pool"] is True
    assert found_row["rationale_types"] == ["profile_match"]
    assert miss_row["found_on_spotify"] is False
    assert miss_row["in_candidate_pool"] is False
    assert miss_row["model"] == "gpt-x"
    assert miss_row["candidate_pool_size"] == 2


def test_in_candidate_pool_null_when_rag_off(tmp_log):
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=False, rag_corpus_meta_path=None,
        candidate_pool_names=None,
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=[],
        eval_log_path=tmp_log, debug_mode=True,
    )
    rows = _read_rows(tmp_log)
    assert rows[0]["in_candidate_pool"] is None
    assert rows[0]["candidate_pool_size"] is None


def test_appends_across_calls(tmp_log):
    for i in range(3):
        log_batch_outcome(
            run_id=f"r{i}", batch_num=1, model="m",
            rag_enabled=False, rag_corpus_meta_path=None,
            candidate_pool_names=None,
            profile_id="p", profile={},
            suggested_playlist=[{"artist": "a", "track": str(i)}],
            found_keys=[],
            eval_log_path=tmp_log, debug_mode=True,
        )
    assert len(_read_rows(tmp_log)) == 3


def test_corpus_version_read_from_meta(tmp_log, tmp_path):
    meta = tmp_path / "artists.meta.json"
    meta.write_text(json.dumps({"corpus_version": "2026-04-19"}), encoding="utf-8")
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=True, rag_corpus_meta_path=meta,
        candidate_pool_names=[],
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=[],
        eval_log_path=tmp_log, debug_mode=True,
    )
    assert _read_rows(tmp_log)[0]["rag_corpus_version"] == "2026-04-19"


def test_profile_hash_stable_across_history_changes():
    base = {"must_have": ["pop"], "avoid": ["country"]}
    p1 = {**base, "history": {"suggested_tracks": []}}
    p2 = {**base, "history": {"suggested_tracks": [{"artist": "x", "track": "y"}]}}
    assert compute_profile_hash(p1) == compute_profile_hash(p2)


def test_profile_hash_changes_with_must_have():
    p1 = {"must_have": ["pop"]}
    p2 = {"must_have": ["jazz"]}
    assert compute_profile_hash(p1) != compute_profile_hash(p2)


# ── 2026-04-22 additions: batch summary + config signature + extended track row ──

def test_track_row_now_includes_kind_field(tmp_log):
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=False, rag_corpus_meta_path=None,
        candidate_pool_names=None,
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=[],
        eval_log_path=tmp_log, debug_mode=True,
    )
    row = _read_rows(tmp_log)[0]
    # Distinguishes per-track rows from per-batch summary rows.
    assert row["kind"] == "track"


def test_track_row_carries_effective_batch_size_and_config_signature(tmp_log):
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=True, rag_corpus_meta_path=None,
        candidate_pool_names=["a"],
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=["a - t"],
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=5,
        config_signature="abc123",
    )
    row = _read_rows(tmp_log)[0]
    assert row["effective_batch_size"] == 5
    assert row["config_signature"] == "abc123"


def test_track_row_optional_kwargs_default_to_none(tmp_log):
    """Backwards-compat: callers that don't pass the new kwargs still work."""
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=False, rag_corpus_meta_path=None,
        candidate_pool_names=None,
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=[],
        eval_log_path=tmp_log, debug_mode=True,
    )
    row = _read_rows(tmp_log)[0]
    assert row["effective_batch_size"] is None
    assert row["config_signature"] is None


# ── compute_config_signature ──

def test_config_signature_is_short_and_stable():
    sig = compute_config_signature(
        rag_enabled=True, rag_pool_size=100,
        rag_stratified=True, effective_batch_size=5,
        extra={"compact_json": True},
    )
    assert isinstance(sig, str)
    assert len(sig) == 8  # truncated sha1
    # Stable across calls with the same inputs.
    again = compute_config_signature(
        rag_enabled=True, rag_pool_size=100,
        rag_stratified=True, effective_batch_size=5,
        extra={"compact_json": True},
    )
    assert sig == again


def test_config_signature_changes_with_pool_size():
    a = compute_config_signature(rag_enabled=True, rag_pool_size=20,
                                 rag_stratified=True, effective_batch_size=5)
    b = compute_config_signature(rag_enabled=True, rag_pool_size=100,
                                 rag_stratified=True, effective_batch_size=5)
    assert a != b


def test_config_signature_changes_with_extra_flag():
    a = compute_config_signature(rag_enabled=True, rag_pool_size=100,
                                 rag_stratified=True, effective_batch_size=5,
                                 extra={"slim_pool_format": True})
    b = compute_config_signature(rag_enabled=True, rag_pool_size=100,
                                 rag_stratified=True, effective_batch_size=5,
                                 extra={"slim_pool_format": False})
    assert a != b


# ── log_batch_summary ──

def test_batch_summary_no_op_when_debug_off(tmp_log):
    log_batch_summary(
        run_id="r", batch_num=1, model="m",
        rag_enabled=True, rag_corpus_meta_path=None,
        profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=False,
    )
    assert not tmp_log.exists()


def test_batch_summary_writes_one_row_with_kind_marker(tmp_log):
    log_batch_summary(
        run_id="r", batch_num=2, model="gpt-x",
        rag_enabled=True, rag_corpus_meta_path=None,
        profile_id="p", profile={"must_have": ["jazz"]},
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=5, rag_pool_size=100, rag_stratified=True,
        candidate_pool_names=["Miles", "Coltrane"],
        prompt_components={"system": 1800, "user_total": 4900,
                           "profile": 800, "deny_set": 1200,
                           "pool": 1100, "accepted": 0,
                           "feedback": 200, "diversity_hint": 0,
                           "audio_filters": 0},
        usage={"prompt_tokens": 1900, "completion_tokens": 720,
               "total_tokens": 2620},
        gpt_returned_count=8, after_filter_count=6,
        spotify_found_count=5, in_pool_count=2,
        consecutive_empty_batches=0,
        config_signature="abc123",
    )
    rows = _read_rows(tmp_log)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "batch_summary"
    assert row["batch_num"] == 2
    assert row["effective_batch_size"] == 5
    assert row["rag_pool_size"] == 100
    assert row["rag_stratified"] is True
    assert row["candidate_pool_size"] == 2
    assert row["prompt_components"]["pool"] == 1100
    assert row["prompt_components"]["system"] == 1800
    assert row["usage"]["total_tokens"] == 2620
    assert row["gpt_returned_count"] == 8
    assert row["after_filter_count"] == 6
    assert row["spotify_found_count"] == 5
    assert row["in_pool_count"] == 2
    assert row["config_signature"] == "abc123"
    # Profile hash always derived from profile.
    assert row["profile_hash"] == compute_profile_hash({"must_have": ["jazz"]})


def test_batch_summary_handles_missing_usage(tmp_log):
    """Local LLM providers (Ollama, LM Studio) often omit `usage`."""
    log_batch_summary(
        run_id="r", batch_num=1, model="ollama-llama3",
        rag_enabled=False, rag_corpus_meta_path=None,
        profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=10, rag_pool_size=None, rag_stratified=None,
        candidate_pool_names=None,
        prompt_components={"system": 1500, "user_total": 3200},
        usage=None,
        gpt_returned_count=10, after_filter_count=10,
        spotify_found_count=8, in_pool_count=0,
    )
    row = _read_rows(tmp_log)[0]
    assert row["usage"] is None
    assert row["candidate_pool_size"] is None
    assert row["rag_pool_size"] is None


def test_batch_summary_carries_top_level_latency_and_stage_counts(tmp_log):
    """Phase 1 review fix: latency_s is top-level (not buried in prompt_components),
    and stage1/stage2 counts are first-class fields for staged-pipeline analysis."""
    log_batch_summary(
        run_id="r", batch_num=1, model="gpt-x",
        rag_enabled=True, rag_corpus_meta_path=None,
        profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=10, candidate_pool_names=["a", "b"],
        prompt_components={"system": 600, "user_total": 1500, "pool": 80},
        latency_s=4.236,
        usage={"prompt_tokens": 500, "completion_tokens": 700, "total_tokens": 1200},
        gpt_returned_count=10, after_filter_count=8,
        spotify_found_count=7, in_pool_count=2,
        stage1_candidate_count=50, stage2_approved_count=32,
    )
    row = _read_rows(tmp_log)[0]
    assert row["latency_s"] == 4.236
    assert row["stage1_candidate_count"] == 50
    assert row["stage2_approved_count"] == 32
    # latency_s lives at top level, not inside prompt_components.
    assert "latency_s" not in row["prompt_components"]


# ── log_stage2_summary ──

def test_stage2_summary_writes_row(tmp_log):
    log_stage2_summary(
        run_id="r1", model="gpt-5.4-mini",
        profile_id="p", profile={"must_have": ["jazz"]},
        eval_log_path=tmp_log, debug_mode=True,
        candidates_in=50, approved_out=32, avoid_traits_count=3,
        status="ok", latency_s=1.234,
        usage={"prompt_tokens": 800, "completion_tokens": 50,
               "total_tokens": 850},
        prompt_chars=2400, config_signature="sig1",
    )
    row = _read_rows(tmp_log)[0]
    assert row["kind"] == "stage2_summary"
    assert row["candidates_in"] == 50
    assert row["approved_out"] == 32
    assert row["avoid_traits_count"] == 3
    assert row["status"] == "ok"
    assert row["latency_s"] == 1.234
    assert row["usage"]["total_tokens"] == 850
    assert row["prompt_chars"] == 2400
    assert row["config_signature"] == "sig1"


def test_stage2_summary_no_op_when_debug_off(tmp_log):
    log_stage2_summary(
        run_id="r", model="m", profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=False,
        candidates_in=0, approved_out=0, avoid_traits_count=0,
        status="ok", latency_s=None, usage=None,
    )
    assert not tmp_log.exists()


def test_stage2_summary_status_error_serialised(tmp_log):
    log_stage2_summary(
        run_id="r", model="m", profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=True,
        candidates_in=10, approved_out=10, avoid_traits_count=2,
        status="error", latency_s=None, usage=None, prompt_chars=500,
    )
    row = _read_rows(tmp_log)[0]
    assert row["status"] == "error"
    assert row["latency_s"] is None


# ── log_profile_update_summary ──

def test_profile_update_summary_carries_before_and_after_hashes(tmp_log):
    before = {"must_have": ["pop"]}
    after = {"must_have": ["pop", "indie"]}
    log_profile_update_summary(
        run_id="r", model="gpt-5.5", profile_id="p",
        profile_before=before, profile_after=after,
        eval_log_path=tmp_log, debug_mode=True,
        label="train_profile", status="ok", latency_s=2.5,
        usage={"prompt_tokens": 5000, "completion_tokens": 3000,
               "total_tokens": 8000},
        prompt_chars=22000, response_chars=14000,
    )
    row = _read_rows(tmp_log)[0]
    assert row["kind"] == "profile_update_summary"
    assert row["label"] == "train_profile"
    assert row["latency_s"] == 2.5
    assert row["prompt_chars"] == 22000
    # Before/after hashes differ when profile changed.
    assert row["profile_hash_before"] != row["profile_hash_after"]


def test_profile_update_summary_after_none_when_call_failed(tmp_log):
    log_profile_update_summary(
        run_id="r", model="m", profile_id="p",
        profile_before={"must_have": ["x"]},
        profile_after=None,
        eval_log_path=tmp_log, debug_mode=True,
        label="train_profile", status="empty_response",
        latency_s=None, usage=None,
    )
    row = _read_rows(tmp_log)[0]
    assert row["status"] == "empty_response"
    assert row["profile_hash_after"] is None


# ── log_analysis_summary ──

def test_analysis_summary_writes_row_with_quality_counts(tmp_log):
    log_analysis_summary(
        run_id="r", model="gpt-5.5", profile_id="p",
        eval_log_path=tmp_log, debug_mode=True,
        artist="Bear Ghost", track="Mr. Bubbles",
        status="ok", latency_s=1.8,
        usage={"prompt_tokens": 600, "completion_tokens": 400,
               "total_tokens": 1000},
        prompt_chars=2300, response_chars=1500,
        genre_count=3, style_tag_count=5, suggestion_count=4,
    )
    row = _read_rows(tmp_log)[0]
    assert row["kind"] == "analysis_summary"
    assert row["artist"] == "bear ghost"
    assert row["track"] == "mr. bubbles"
    assert row["genre_count"] == 3
    assert row["style_tag_count"] == 5
    assert row["suggestion_count"] == 4


def test_batch_summary_appends_alongside_track_rows(tmp_log):
    """Both row kinds coexist in the same JSONL so analysts can join them."""
    log_batch_outcome(
        run_id="r", batch_num=1, model="m",
        rag_enabled=True, rag_corpus_meta_path=None,
        candidate_pool_names=["a"],
        profile_id="p", profile={},
        suggested_playlist=[{"artist": "a", "track": "t"}],
        found_keys=["a - t"],
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=5, config_signature="sig1",
    )
    log_batch_summary(
        run_id="r", batch_num=1, model="m",
        rag_enabled=True, rag_corpus_meta_path=None,
        profile_id="p", profile={},
        eval_log_path=tmp_log, debug_mode=True,
        effective_batch_size=5, config_signature="sig1",
        gpt_returned_count=1, after_filter_count=1, spotify_found_count=1,
    )
    rows = _read_rows(tmp_log)
    assert len(rows) == 2
    # Batch summary and track row are joinable on (run_id, batch_num, config_signature).
    assert rows[0]["kind"] == "track"
    assert rows[1]["kind"] == "batch_summary"
    assert rows[0]["run_id"] == rows[1]["run_id"] == "r"
    assert rows[0]["batch_num"] == rows[1]["batch_num"] == 1
    assert rows[0]["config_signature"] == rows[1]["config_signature"] == "sig1"

