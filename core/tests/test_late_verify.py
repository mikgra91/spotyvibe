"""Tests for evaluation/late_verify.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.late_verify import (
    discover_run_dirs, iter_tracks_from_eval_log, process_run_dir,
    verify_tracks,
)


def _write_eval_log(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


class _StubVerifier:
    name = "stub"
    def __init__(self, mapping=None):
        self._map = mapping or {}
        self.calls: list[dict] = []
    def verify(self, track):
        self.calls.append(track)
        key = (track["artist"].lower(), track["track"].lower())
        return self._map.get(key, ("not_found",
                                    f"{track['artist']} - {track['track']}"))


# ── iter_tracks_from_eval_log ─────────────────────────────────────────

class TestIterTracksFromEvalLog:
    def test_extracts_batch_summary_tracks(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        _write_eval_log(log, [
            {"kind": "batch_summary", "suggested_playlist": [
                {"artist": "Tally Hall", "track": "Good Day"},
                {"artist": "Bear Ghost", "track": "Necromancin Dancin"},
            ]},
        ])
        out = list(iter_tracks_from_eval_log(log))
        assert out == [
            {"artist": "Tally Hall", "track": "Good Day"},
            {"artist": "Bear Ghost", "track": "Necromancin Dancin"},
        ]

    def test_dedups_across_batches(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        _write_eval_log(log, [
            {"kind": "batch_summary",
             "suggested_playlist": [{"artist": "X", "track": "Y"}]},
            {"kind": "batch_summary",
             "suggested_playlist": [{"artist": "x", "track": "y"},   # dup
                                      {"artist": "X", "track": "Z"}]},
        ])
        out = list(iter_tracks_from_eval_log(log))
        assert len(out) == 2
        assert {(t["artist"].lower(), t["track"].lower()) for t in out} == {
            ("x", "y"), ("x", "z"),
        }

    def test_ignores_non_batch_summary_rows(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        _write_eval_log(log, [
            {"kind": "stage1_query", "suggested_playlist": [{"artist": "X", "track": "Y"}]},
            {"kind": "batch_summary", "suggested_playlist": [{"artist": "A", "track": "B"}]},
        ])
        out = list(iter_tracks_from_eval_log(log))
        assert out == [{"artist": "A", "track": "B"}]

    def test_skips_malformed_json_lines(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        log.write_text(
            'not-json\n'
            + json.dumps({"kind": "batch_summary",
                           "suggested_playlist": [{"artist": "A", "track": "B"}]})
            + '\n', encoding="utf-8",
        )
        out = list(iter_tracks_from_eval_log(log))
        assert out == [{"artist": "A", "track": "B"}]

    def test_skips_entries_missing_artist_or_track(self, tmp_path):
        log = tmp_path / "eval.jsonl"
        _write_eval_log(log, [
            {"kind": "batch_summary", "suggested_playlist": [
                {"artist": "",  "track": "X"},
                {"artist": "A", "track": ""},
                {"artist": "A", "track": "B"},
            ]},
        ])
        out = list(iter_tracks_from_eval_log(log))
        assert out == [{"artist": "A", "track": "B"}]


# ── verify_tracks ─────────────────────────────────────────────────────

class TestVerifyTracks:
    def test_found_counts_and_payload(self):
        v = _StubVerifier({
            ("x", "y"): ("found",
                          {"uri": "spotify:track:abc",
                           "track_id": "abc",
                           "release_date": "2024-01-01"}),
        })
        summary = verify_tracks(
            [{"artist": "X", "track": "Y"}, {"artist": "U", "track": "V"}], v,
        )
        assert summary["total"] == 2
        assert summary["found"] == 1
        assert summary["not_found"] == 1
        # The 'found' record carries verified_by from the verifier.
        found_row = next(r for r in summary["results"] if r["status"] == "found")
        assert found_row["uri"] == "spotify:track:abc"
        assert found_row["verified_by"] == "stub"

    def test_exception_recorded_as_error(self):
        class _Boom:
            name = "boom"
            def verify(self, _): raise RuntimeError("explode")
        summary = verify_tracks(
            [{"artist": "X", "track": "Y"}], _Boom(),
        )
        assert summary["errors"] == 1
        assert summary["results"][0]["status"] == "error"


# ── process_run_dir ──────────────────────────────────────────────────

class TestProcessRunDir:
    def test_writes_late_verify_json(self, tmp_path):
        d = tmp_path / "run1"
        d.mkdir()
        _write_eval_log(d / "eval.jsonl", [
            {"kind": "batch_summary", "suggested_playlist": [
                {"artist": "A", "track": "B"},
            ]},
        ])
        v = _StubVerifier({("a", "b"): ("found", {"uri": "spotify:track:1"})})
        summary = process_run_dir(d, v)
        assert summary["found"] == 1
        out_file = d / "late_verify.json"
        assert out_file.exists()
        on_disk = json.loads(out_file.read_text(encoding="utf-8"))
        assert on_disk["found"] == 1

    def test_idempotent_unless_force(self, tmp_path):
        d = tmp_path / "run1"
        d.mkdir()
        _write_eval_log(d / "eval.jsonl", [
            {"kind": "batch_summary", "suggested_playlist": [
                {"artist": "A", "track": "B"},
            ]},
        ])
        v = _StubVerifier({("a", "b"): ("found", {"uri": "spotify:track:1"})})
        process_run_dir(d, v)
        v2 = _StubVerifier()                                        # would say not_found
        # Second invocation must NOT re-call the verifier — returns cached.
        summary2 = process_run_dir(d, v2)
        assert summary2["found"] == 1                               # from cache
        assert v2.calls == []

    def test_force_redoes(self, tmp_path):
        d = tmp_path / "run1"
        d.mkdir()
        _write_eval_log(d / "eval.jsonl", [
            {"kind": "batch_summary", "suggested_playlist": [
                {"artist": "A", "track": "B"},
            ]},
        ])
        process_run_dir(d, _StubVerifier())                          # 0 found
        v_new = _StubVerifier({("a", "b"): ("found", {})})
        summary = process_run_dir(d, v_new, force=True)
        assert summary["found"] == 1

    def test_returns_none_when_no_eval_log(self, tmp_path):
        d = tmp_path / "run1"
        d.mkdir()
        assert process_run_dir(d, _StubVerifier()) is None


# ── discover_run_dirs ────────────────────────────────────────────────

class TestDiscoverRunDirs:
    def test_session_root_returns_per_run_subdirs(self, tmp_path):
        for name in ("default__gpt-5.4-iter1", "default__gpt-5.4-iter2"):
            d = tmp_path / name
            d.mkdir()
            (d / "eval.jsonl").write_text("", encoding="utf-8")
        # Subdir without eval.jsonl must be skipped.
        (tmp_path / "skipme").mkdir()
        out = discover_run_dirs(tmp_path)
        assert len(out) == 2
        assert all(d.name.startswith("default__") for d in out)

    def test_passing_a_run_dir_directly_returns_it(self, tmp_path):
        d = tmp_path / "run1"
        d.mkdir()
        (d / "eval.jsonl").write_text("", encoding="utf-8")
        assert discover_run_dirs(d) == [d]
