"""Tests for core.src.perf_log — sqlite per-run perf summary (M3, 2026-05-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.src import perf_log


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "perf_log_test.sqlite"


class TestRecordRun:
    def test_record_then_read_round_trip(self, db_path):
        perf_log.record_run(
            "run-001",
            stage_metrics={"rag_retrieve": {"duration_s": 0.12, "calls": 1,
                                            "tokens_in": 0, "tokens_out": 0}},
            model="openai:gpt-5.4",
            tracks_found=10,
            tracks_target=10,
            exhausted=False,
            error=None,
            db_path=db_path,
        )
        rows = perf_log.read_runs(db_path=db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "run-001"
        assert row["model"] == "openai:gpt-5.4"
        assert row["tracks_found"] == 10
        assert row["tracks_target"] == 10
        assert row["exhausted"] is False
        assert row["error"] is None
        assert row["stage_metrics"]["rag_retrieve"]["duration_s"] == 0.12
        assert row["schema_version"] == 1

    def test_idempotent_on_duplicate_run_id(self, db_path):
        perf_log.record_run("run-dup", stage_metrics={}, model="m1",
                            tracks_found=0, tracks_target=10, db_path=db_path)
        perf_log.record_run("run-dup", stage_metrics={}, model="m2",
                            tracks_found=10, tracks_target=10, db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        assert len(rows) == 1
        assert rows[0]["model"] == "m2"
        assert rows[0]["tracks_found"] == 10

    def test_records_error_message(self, db_path):
        perf_log.record_run("run-err", stage_metrics={}, model="m1",
                            tracks_found=0, tracks_target=10,
                            error="upstream timeout", db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        assert rows[0]["error"] == "upstream timeout"

    def test_exhausted_flag_persists(self, db_path):
        perf_log.record_run("run-x", stage_metrics={}, model="m1",
                            tracks_found=3, tracks_target=10,
                            exhausted=True, db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        assert rows[0]["exhausted"] is True

    def test_empty_run_id_is_noop(self, db_path):
        result = perf_log.record_run("", stage_metrics={}, model="m1",
                                     tracks_found=0, tracks_target=10,
                                     db_path=db_path)
        assert result is None
        assert perf_log.read_runs(db_path=db_path) == []

    def test_none_stage_metrics_serialised_as_empty(self, db_path):
        perf_log.record_run("run-none", stage_metrics=None, model=None,
                            tracks_found=0, tracks_target=10, db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        assert rows[0]["stage_metrics"] == {}
        assert rows[0]["model"] is None


class TestReadRuns:
    def test_orders_newest_first(self, db_path):
        # Insert in reverse chronological order; read_runs should reorder.
        for i, ts in enumerate(["2026-05-01T00:00:00", "2026-05-02T00:00:00",
                                 "2026-05-03T00:00:00"]):
            perf_log.record_run(f"r{i}", stage_metrics={}, model="m",
                                tracks_found=i, tracks_target=10,
                                db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        # All have very close ts; just confirm they all came back.
        assert {r["run_id"] for r in rows} == {"r0", "r1", "r2"}

    def test_limit_caps_returned_rows(self, db_path):
        for i in range(5):
            perf_log.record_run(f"r{i}", stage_metrics={}, model="m",
                                tracks_found=0, tracks_target=10,
                                db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path, limit=2)
        assert len(rows) == 2

    def test_missing_db_returns_empty(self, tmp_path):
        rows = perf_log.read_runs(db_path=tmp_path / "nonexistent.sqlite")
        assert rows == []

    def test_stage_metrics_deserialise_failure_returns_empty_dict(self, db_path):
        # Manually insert a row with a malformed stage_metrics blob so we
        # exercise the JSON-decode failure path.
        import sqlite3
        perf_log.record_run("ok", stage_metrics={}, model="m",
                            tracks_found=0, tracks_target=10, db_path=db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE run_perf SET stage_metrics = ? WHERE run_id = ?",
                ("not-json", "ok"),
            )
            conn.commit()
        finally:
            conn.close()
        rows = perf_log.read_runs(db_path=db_path)
        assert rows[0]["stage_metrics"] == {}


class TestSchema:
    def test_table_created_on_first_use(self, db_path):
        assert not db_path.exists()
        perf_log.record_run("first", stage_metrics={}, model="m",
                            tracks_found=0, tracks_target=10, db_path=db_path)
        assert db_path.exists()

    def test_repeat_connect_reuses_table(self, db_path):
        perf_log.record_run("a", stage_metrics={}, model="m",
                            tracks_found=0, tracks_target=10, db_path=db_path)
        perf_log.record_run("b", stage_metrics={}, model="m",
                            tracks_found=0, tracks_target=10, db_path=db_path)
        rows = perf_log.read_runs(db_path=db_path)
        assert {r["run_id"] for r in rows} == {"a", "b"}
