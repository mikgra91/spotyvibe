"""Tests for core/history.py — Run History & Undo."""
import json
from unittest.mock import patch, MagicMock
import pytest
from core.src.history import save_run, load_runs, undo_last_run, _HISTORY_FILE


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

    def test_caps_at_50_entries(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        # Pre-populate with 50 entries
        existing = [{"run_id": f"old-{i}", "timestamp": "", "playlist_id": "", "playlist_url": "", "tracks": []} for i in range(50)]
        hist_file.write_text(json.dumps(existing))
        with patch("core.src.history._HISTORY_FILE", hist_file):
            save_run("new", "pl", "url", [])
        data = json.loads(hist_file.read_text())
        assert len(data) == 50
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


class TestUndoLastRun:
    def test_removes_tracks_and_entry(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [{
            "run_id": "r1",
            "timestamp": "2026-01-01",
            "playlist_id": "pl1",
            "playlist_url": "url",
            "tracks": [{"artist": "a", "track": "t", "uri": "spotify:track:1"}]
        }]
        hist_file.write_text(json.dumps(data))
        sp = MagicMock()
        with patch("core.src.history._HISTORY_FILE", hist_file):
            result = undo_last_run(sp)
        assert result["undone"] is True
        assert result["removed"] == 1
        sp.playlist_remove_all_occurrences_of_items.assert_called_once_with("pl1", ["spotify:track:1"])
        remaining = json.loads(hist_file.read_text())
        assert len(remaining) == 0

    def test_raises_when_empty(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        hist_file.write_text("[]")
        with patch("core.src.history._HISTORY_FILE", hist_file):
            with pytest.raises(ValueError, match="No run history"):
                undo_last_run(MagicMock())

    def test_raises_when_no_playlist_id(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [{"run_id": "r1", "playlist_id": "", "playlist_url": "", "tracks": [{"uri": "x"}]}]
        hist_file.write_text(json.dumps(data))
        with patch("core.src.history._HISTORY_FILE", hist_file):
            with pytest.raises(ValueError, match="no playlist ID"):
                undo_last_run(MagicMock())

    def test_raises_when_no_uris(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [{"run_id": "r1", "playlist_id": "pl1", "playlist_url": "", "tracks": [{"artist": "a", "track": "t"}]}]
        hist_file.write_text(json.dumps(data))
        with patch("core.src.history._HISTORY_FILE", hist_file):
            with pytest.raises(ValueError, match="no track URIs"):
                undo_last_run(MagicMock())
