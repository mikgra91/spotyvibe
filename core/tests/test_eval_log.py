"""Tests for ``core/src/eval_log.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.src.eval_log import (compute_profile_hash, log_batch_outcome,
                               log_batch_summary, compute_config_signature)


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

