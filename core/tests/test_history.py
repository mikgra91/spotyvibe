"""Tests for core/history.py — Run History."""
import json
from unittest.mock import patch
import pytest
from core.src.history import save_run, load_runs, _HISTORY_FILE


class TestSaveRun:
    def test_saves_run_entry(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        with patch("core.src.history._HISTORY_FILE", hist_file):
            save_run("r1", "pl1", "https://spotify.com/pl1", [
                {"artist": "a", "track": "t", "uri": "spotify:track:1"}
            ])
        data = json.loads(hist_file.read_text())
        assert len(data) == 1
        assert data[0]["run_id"] == "r1"
        assert data[0]["playlist_id"] == "pl1"
        assert len(data[0]["tracks"]) == 1

    def test_appends_multiple_runs(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        with patch("core.src.history._HISTORY_FILE", hist_file):
            save_run("r1", "pl1", "url1", [])
            save_run("r2", "pl2", "url2", [])
        data = json.loads(hist_file.read_text())
        assert len(data) == 2

    def test_caps_at_5_entries(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        # Pre-populate with 5 entries
        existing = [{"run_id": f"old-{i}", "timestamp": "", "playlist_id": "", "playlist_url": "", "tracks": []} for i in range(5)]
        hist_file.write_text(json.dumps(existing))
        with patch("core.src.history._HISTORY_FILE", hist_file):
            save_run("new", "pl", "url", [])
        data = json.loads(hist_file.read_text())
        assert len(data) == 5
        assert data[-1]["run_id"] == "new"
        assert data[0]["run_id"] == "old-1"  # old-0 was dropped


class TestLoadRuns:
    def test_returns_empty_when_no_file(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        with patch("core.src.history._HISTORY_FILE", hist_file):
            assert load_runs() == []

    def test_returns_newest_first(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [
            {"run_id": "r1", "timestamp": "2026-01-01"},
            {"run_id": "r2", "timestamp": "2026-01-02"},
        ]
        hist_file.write_text(json.dumps(data))
        with patch("core.src.history._HISTORY_FILE", hist_file):
            runs = load_runs()
        assert runs[0]["run_id"] == "r2"
        assert runs[1]["run_id"] == "r1"

    def test_handles_corrupt_file(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        hist_file.write_text("not json")
        with patch("core.src.history._HISTORY_FILE", hist_file):
            assert load_runs() == []


