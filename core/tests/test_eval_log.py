"""Tests for ``core/src/eval_log.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.src.eval_log import compute_profile_hash, log_batch_outcome


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
