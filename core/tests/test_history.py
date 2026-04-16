"""Tests for core/history.py — Run History."""
import json
from unittest.mock import patch
import pytest
from core.src.history import save_run, load_runs, update_track_sentiment


def _patch_hist(tmp_path):
    """Return a patch that redirects _history_file() to a tmp dir."""
    return patch("core.src.history._history_file", return_value=tmp_path / "run_history.json")


class TestSaveRun:
    def test_saves_run_entry(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "https://spotify.com/pl1", [
                {"artist": "a", "track": "t", "uri": "spotify:track:1"}
            ])
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert len(data) == 1
        assert data[0]["run_id"] == "r1"
        assert data[0]["playlist_id"] == "pl1"
        assert len(data[0]["tracks"]) == 1

    def test_appends_multiple_runs(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url1", [])
            save_run("r2", "pl2", "url2", [])
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert len(data) == 2

    def test_caps_at_5_entries(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        existing = [{"run_id": f"old-{i}", "timestamp": "", "playlist_id": "", "playlist_url": "", "tracks": []} for i in range(5)]
        hist_file.write_text(json.dumps(existing))
        with _patch_hist(tmp_path):
            save_run("new", "pl", "url", [])
        data = json.loads(hist_file.read_text())
        assert len(data) == 5
        assert data[-1]["run_id"] == "new"
        assert data[0]["run_id"] == "old-1"  # old-0 was dropped

    def test_new_run_tracks_have_neutral_sentiment(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "A", "track": "T", "uri": "u"}
            ])
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert data[0]["tracks"][0]["sentiment"] == "neutral"


class TestLoadRuns:
    def test_returns_empty_when_no_file(self, tmp_path):
        with _patch_hist(tmp_path):
            assert load_runs() == []

    def test_returns_newest_first(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [
            {"run_id": "r1", "timestamp": "2026-01-01"},
            {"run_id": "r2", "timestamp": "2026-01-02"},
        ]
        hist_file.write_text(json.dumps(data))
        with _patch_hist(tmp_path):
            runs = load_runs()
        assert runs[0]["run_id"] == "r2"
        assert runs[1]["run_id"] == "r1"

    def test_handles_corrupt_file(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        hist_file.write_text("not json")
        with _patch_hist(tmp_path):
            assert load_runs() == []

    def test_migrates_missing_sentiment_to_neutral(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        data = [{"run_id": "r1", "tracks": [
            {"artist": "A", "track": "T", "uri": "u",
             "rationale": [{"type": "fallback"}]}
        ]}]
        hist_file.write_text(json.dumps(data))
        with _patch_hist(tmp_path):
            runs = load_runs()
        assert runs[0]["tracks"][0]["sentiment"] == "neutral"


class TestSchemaVersionMigration:
    """C9: schema_version and rationale migration tests."""

    def test_new_run_has_schema_version_4(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "https://spotify.com/pl1", [
                {"artist": "Artist", "track": "Song", "uri": "spotify:track:1",
                 "rationale": [{"type": "genre", "arg": "rock"}],
                 "energy": 0.8, "valence": 0.6,
                 "genres": ["rock", "alternative"], "release_year": 2023}
            ])
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert data[0]["schema_version"] == 4
        track = data[0]["tracks"][0]
        assert track["energy"] == 0.8
        assert track["valence"] == 0.6
        assert track["genres"] == ["rock", "alternative"]
        assert track["release_year"] == 2023
        assert track["sentiment"] == "neutral"

    def test_new_run_handles_missing_metadata(self, tmp_path):
        """Tracks without energy/valence/genres/release_year get None/empty defaults."""
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "A", "track": "T", "uri": "u"}
            ])
        data = json.loads((tmp_path / "run_history.json").read_text())
        track = data[0]["tracks"][0]
        assert track["energy"] is None
        assert track["valence"] is None
        assert track["genres"] == []
        assert track["release_year"] is None
        assert track["sentiment"] == "neutral"

    def test_legacy_run_reads_with_rationale_migration(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        legacy_data = [{
            "run_id": "legacy-1",
            "timestamp": "2025-01-01T00:00:00",
            "playlist_id": "pl1",
            "playlist_url": "https://spotify.com/pl1",
            "tracks": [
                {"artist": "Band", "track": "Tune", "uri": "spotify:track:x",
                 "reason": "Great energy and tempo"},
            ]
        }]
        hist_file.write_text(json.dumps(legacy_data))
        with _patch_hist(tmp_path):
            runs = load_runs()
        assert len(runs) == 1
        track = runs[0]["tracks"][0]
        assert "rationale" in track
        assert track["rationale"] == [{"type": "legacy", "arg": "Great energy and tempo"}]
        assert track["sentiment"] == "neutral"

    def test_legacy_run_without_reason_gets_fallback(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        legacy_data = [{
            "run_id": "legacy-2",
            "timestamp": "2025-01-01T00:00:00",
            "playlist_id": "pl2",
            "playlist_url": "url",
            "tracks": [
                {"artist": "A", "track": "T", "uri": "u"},
            ]
        }]
        hist_file.write_text(json.dumps(legacy_data))
        with _patch_hist(tmp_path):
            runs = load_runs()
        track = runs[0]["tracks"][0]
        assert track["rationale"] == [{"type": "fallback"}]

    def test_v2_run_preserves_rationale(self, tmp_path):
        hist_file = tmp_path / "run_history.json"
        v2_data = [{
            "run_id": "v2-1",
            "schema_version": 2,
            "timestamp": "2026-01-01T00:00:00",
            "playlist_id": "pl3",
            "playlist_url": "url",
            "tracks": [
                {"artist": "X", "track": "Y", "uri": "u",
                 "rationale": [{"type": "genre", "arg": "rock"}, {"type": "energy"}]},
            ]
        }]
        hist_file.write_text(json.dumps(v2_data))
        with _patch_hist(tmp_path):
            runs = load_runs()
        track = runs[0]["tracks"][0]
        assert track["rationale"] == [{"type": "genre", "arg": "rock"}, {"type": "energy"}]


class TestUpdateTrackSentiment:
    def test_updates_matching_track(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "Muse", "track": "Hysteria", "uri": "u"}
            ])
            result = update_track_sentiment("muse", "hysteria", "liked")
        assert result is True
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert data[0]["tracks"][0]["sentiment"] == "liked"

    def test_returns_false_for_no_match(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "Muse", "track": "Hysteria", "uri": "u"}
            ])
            result = update_track_sentiment("radiohead", "creep", "disliked")
        assert result is False

    def test_rejects_invalid_sentiment(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "A", "track": "T", "uri": "u"}
            ])
            result = update_track_sentiment("A", "T", "love")
        assert result is False

    def test_case_insensitive_match(self, tmp_path):
        with _patch_hist(tmp_path):
            save_run("r1", "pl1", "url", [
                {"artist": "The Wombats", "track": "Tokyo", "uri": "u"}
            ])
            result = update_track_sentiment("the wombats", "tokyo", "disliked")
        assert result is True
        data = json.loads((tmp_path / "run_history.json").read_text())
        assert data[0]["tracks"][0]["sentiment"] == "disliked"
