"""Tests for app.py — Flask endpoints."""

import json
from unittest.mock import patch

import pytest

# Import the Flask app so we can use test_client
from app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestIndex:
    @patch("app.is_onboarding_completed", return_value=True)
    def test_returns_html(self, _mock_onboarding, client):
        resp = client.get("/")
        assert resp.status_code == 200

    @patch("app.is_onboarding_completed", return_value=True)
    def test_contains_theme_switcher(self, _mock_onboarding, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'id="styleSwitcher"' in html
        for theme in ("equalizer", "pulse"):
            assert f'data-theme="{theme}"' in html
        for removed in ("aurora", "soundwave"):
            assert f'data-theme="{removed}"' not in html

    @patch("app.is_onboarding_completed", return_value=False)
    def test_redirects_to_onboarding_when_not_completed(self, _mock_onboarding, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/onboarding" in resp.headers.get("Location", "")


class TestOnboarding:
    def test_returns_html(self, client):
        resp = client.get("/onboarding")
        assert resp.status_code == 200

    def test_contains_onboarding_pages(self, client):
        resp = client.get("/onboarding")
        html = resp.data.decode()
        assert "SpotyVibe" in html
        assert "ob-page" in html

    def test_contains_credentials_section(self, client):
        resp = client.get("/onboarding")
        html = resp.data.decode()
        assert "OpenAI" in html
        assert "Spotify" in html


class TestHelpContent:
    @patch("app.BASE_DIR")
    def test_returns_html_from_manual(self, mock_base_dir, client, tmp_path):
        (tmp_path / "documentation").mkdir()
        manual = tmp_path / "documentation" / "help.md"
        manual.write_text("# Help\n\nSome **bold** text.")
        mock_base_dir.__truediv__ = lambda self, x: tmp_path / x
        # Need to patch the actual path resolution
        with patch("app.BASE_DIR", tmp_path):
            resp = client.get("/api/help")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "html" in data
        assert "<h1>" in data["html"] or "<strong>" in data["html"]


class TestReadCredentials:
    @patch("app.get_credentials")
    def test_returns_credentials(self, mock_creds, client):
        mock_creds.return_value = {
            "OPENAI_API_KEY": {"masked": "****key1", "is_set": True},
        }
        resp = client.get("/api/settings/credentials")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["OPENAI_API_KEY"]["is_set"] is True


class TestWriteCredentials:
    @patch("app.save_credentials")
    def test_saves_and_returns_ok(self, mock_save, client):
        resp = client.post(
            "/api/settings/credentials",
            data=json.dumps({"OPENAI_API_KEY": "sk-new"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_save.assert_called_once_with({"OPENAI_API_KEY": "sk-new"})


class TestListModels:
    @patch("app.get_model", return_value="gpt-4o")
    @patch("app.get_openai_models")
    def test_returns_models(self, mock_models, mock_get_model, client):
        mock_models.return_value = ["gpt-3.5-turbo", "gpt-4o"]
        resp = client.get("/api/settings/models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "gpt-4o" in data["models"]
        assert data["selected"] == "gpt-4o"

    @patch("app.get_model", return_value="gpt-4o")
    @patch("app.get_openai_models", side_effect=ValueError("No API key"))
    def test_returns_error_on_missing_key(self, mock_models, mock_get_model, client):
        # Clear the models cache so the error path is hit
        import app as app_module
        app_module._models_cache["data"] = None
        app_module._models_cache["expires"] = 0
        resp = client.get("/api/settings/models")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


class TestReadSettings:
    @patch("app.get_settings")
    def test_returns_settings(self, mock_settings, client):
        mock_settings.return_value = {
            "model": "gpt-4o",
            "debug_mode": False,
            "playlist_size": 20,
            "new_artist_percentage": 30,
        }
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["model"] == "gpt-4o"
        assert data["playlist_size"] == 20


class TestWriteSettings:
    @patch("app.save_credentials")
    def test_saves_model_and_debug(self, mock_save, client):
        resp = client.post(
            "/api/settings",
            data=json.dumps({"model": "gpt-4o", "debug_mode": True, "playlist_size": 25}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        mock_save.assert_called_once()
        call_args = mock_save.call_args[0][0]
        assert call_args["OPENAI_MODEL"] == "gpt-4o"
        assert call_args["DEBUG_MODE"] == "true"
        assert call_args["PLAYLIST_SIZE"] == "25"

    @patch("app.save_credentials")
    def test_clamps_new_artist_percentage(self, mock_save, client):
        resp = client.post(
            "/api/settings",
            data=json.dumps({"new_artist_percentage": 200}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        call_args = mock_save.call_args[0][0]
        assert call_args["NEW_ARTIST_PERCENTAGE"] == "100"

    def test_rejects_non_numeric_playlist_size(self, client):
        resp = client.post(
            "/api/settings",
            data=json.dumps({"playlist_size": "not_a_number"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "playlist_size" in resp.get_json()["error"]

    def test_rejects_non_numeric_new_artist_percentage(self, client):
        resp = client.post(
            "/api/settings",
            data=json.dumps({"new_artist_percentage": "abc"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "new_artist_percentage" in resp.get_json()["error"]

    def test_rejects_none_playlist_size(self, client):
        resp = client.post(
            "/api/settings",
            data=json.dumps({"playlist_size": None}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestClearDebugLog:
    def test_clears_log(self, client, tmp_path):
        log_file = tmp_path / "debug.log"
        log_file.write_text("log data")
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            resp = client.delete("/api/settings/debug-log")
        assert resp.status_code == 200
        assert not log_file.exists()

    def test_ok_when_no_log(self, client, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            resp = client.delete("/api/settings/debug-log")
        assert resp.status_code == 200


class TestProfileStatus:
    @patch("app.get_profile_status")
    def test_returns_status(self, mock_status, client):
        mock_status.return_value = {"trained": True, "last_updated": "2025-01-01"}
        resp = client.get("/api/profile/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trained"] is True


class TestProfileData:
    @patch("app.load_profile")
    def test_returns_profile(self, mock_load, client):
        mock_load.return_value = {"preferences": {"core_description": "rock"}}
        resp = client.get("/api/profile/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferences"]["core_description"] == "rock"


class TestProfileImportExport:
    @patch("app.export_profile_dict")
    def test_export_downloads_json(self, mock_export, client):
        mock_export.return_value = {"preferences": {"core_description": "rock"}}
        resp = client.get("/api/profile/export")
        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        dispo = resp.headers.get("Content-Disposition", "")
        assert "attachment" in dispo
        assert "spotyvibe_profile.json" in dispo
        assert "core_description" in resp.data.decode("utf-8")

    @patch("app.import_profile_dict")
    def test_import_replaces_profile(self, mock_import, client):
        mock_import.return_value = {"last_updated": "2026-01-01T00:00:00Z"}
        resp = client.post(
            "/api/profile/import",
            data=json.dumps({"profile": {"preferences": {"core_description": "x"}}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["last_updated"] == "2026-01-01T00:00:00Z"
        mock_import.assert_called_once()

    def test_import_rejects_missing_profile(self, client):
        resp = client.post(
            "/api/profile/import",
            data=json.dumps({"nope": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestTrainProfile:

    @patch("app.train_profile")
    def test_trains_and_returns_ok(self, mock_train, client):
        mock_train.return_value = {"last_updated": "2025-06-01T00:00:00"}
        resp = client.post(
            "/api/train-profile",
            data=json.dumps({"core_description": "I love rock"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["last_updated"] == "2025-06-01T00:00:00"

    def test_rejects_empty_core_description(self, client):
        resp = client.post(
            "/api/train-profile",
            data=json.dumps({"core_description": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("app.train_profile", side_effect=Exception("GPT error"))
    def test_returns_500_on_error(self, mock_train, client):
        resp = client.post(
            "/api/train-profile",
            data=json.dumps({"core_description": "rock"}),
            content_type="application/json",
        )
        assert resp.status_code == 500


class TestSaveProfile:
    @patch("app.save_profile_sections")
    def test_saves_and_returns_ok(self, mock_save, client):
        mock_save.return_value = {"last_updated": "2025-06-01T00:00:00"}
        resp = client.post(
            "/api/save-profile",
            data=json.dumps({"core_description": "I love rock"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["last_updated"] == "2025-06-01T00:00:00"

    def test_rejects_empty_core_description(self, client):
        resp = client.post(
            "/api/save-profile",
            data=json.dumps({"core_description": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("app.save_profile_sections", side_effect=Exception("IO error"))
    def test_returns_500_on_error(self, mock_save, client):
        resp = client.post(
            "/api/save-profile",
            data=json.dumps({"core_description": "rock"}),
            content_type="application/json",
        )
        assert resp.status_code == 500


class TestSubmitFeedback:
    @patch("app.remove_from_playlist")
    @patch("app.dislike_track")
    def test_dislike_with_track_removes_from_playlist(self, mock_dislike, mock_remove, client):
        mock_remove.return_value = {"removed": True}
        resp = client.post(
            "/api/feedback",
            data=json.dumps({"action": "dislike", "artist": "Bad", "track": "Song"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["removal"]["removed"] is True
        mock_dislike.assert_called_once()

    @patch("app.like_track")
    def test_like(self, mock_like, client):
        resp = client.post(
            "/api/feedback",
            data=json.dumps({"action": "like", "artist": "Good", "track": "Hit"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        mock_like.assert_called_once_with("Good", track="Hit", reason=None)

    def test_rejects_missing_artist(self, client):
        resp = client.post(
            "/api/feedback",
            data=json.dumps({"action": "like"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_invalid_action(self, client):
        resp = client.post(
            "/api/feedback",
            data=json.dumps({"action": "love", "artist": "A"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestRemoveTrack:
    @patch("app.remove_from_playlist")
    def test_removes_track(self, mock_remove, client):
        mock_remove.return_value = {"removed": True}
        resp = client.post(
            "/api/remove",
            data=json.dumps({"artist": "A", "track": "B"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is True

    def test_rejects_missing_fields(self, client):
        resp = client.post(
            "/api/remove",
            data=json.dumps({"artist": "A"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestSpotifyStatus:
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    def test_returns_status(self, mock_status, client):
        resp = client.get("/api/spotify/status")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "authenticated"


class TestSpotifyDisconnect:
    @patch("app.disconnect_spotify")
    def test_disconnects(self, mock_disconnect, client):
        resp = client.post("/api/spotify/disconnect")
        assert resp.status_code == 200
        mock_disconnect.assert_called_once()


class TestSpotifyAuth:
    @patch("app.get_spotify_auth_url", return_value="https://accounts.spotify.com/authorize")
    def test_redirects(self, mock_url, client):
        resp = client.get("/api/spotify/auth")
        assert resp.status_code == 302


class TestCancelRun:
    def test_cancel_nonexistent_run(self, client):
        resp = client.post(
            "/api/cancel",
            data=json.dumps({"run_id": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "not_found"


class TestRunPipeline:
    @patch("app.is_profile_trained", return_value=False)
    def test_error_when_profile_not_trained(self, mock_trained, client):
        resp = client.post(
            "/api/run",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        # Parse SSE events
        data = resp.data.decode()
        assert "train your taste profile" in data.lower()

    @patch("app.get_spotify_auth_status", return_value="not_authenticated")
    @patch("app.is_profile_trained", return_value=True)
    def test_error_when_spotify_not_connected(self, mock_trained, mock_spotify, client):
        resp = client.post(
            "/api/run",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = resp.data.decode()
        assert "spotify is not connected" in data.lower()

    @patch("app.add_to_playlist")
    @patch("app.search_tracks")
    @patch("app.filter_duplicate_suggestions")
    @patch("app.call_gpt")
    @patch("app.save_profile")
    @patch("app.update_profile")
    @patch("app.normalize_history")
    @patch("app.load_profile")
    @patch("app.get_new_artist_percentage", return_value=30)
    @patch("app.get_playlist_size", return_value=10)
    @patch("app.get_debug_mode", return_value=False)
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    @patch("app.is_profile_trained", return_value=True)
    def test_successful_run(
        self, mock_trained, mock_spotify, mock_debug, mock_size,
        mock_percentage, mock_load, mock_norm, mock_update,
        mock_save, mock_gpt, mock_filter, mock_search, mock_add, client
    ):
        mock_load.return_value = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
            "preferences": {},
        }
        mock_norm.return_value = mock_load.return_value
        mock_gpt.return_value = {
            "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        mock_filter.return_value = {
            "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        mock_update.return_value = mock_load.return_value
        mock_search.return_value = (
            [{"artist": "a", "track": "b", "uri": f"spotify:track:{i}", "cover_url": None} for i in range(10)],
            [],
        )
        mock_add.return_value = {"url": "https://open.spotify.com/playlist/test", "added": 10}

        resp = client.post(
            "/api/run",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = resp.data.decode()
        assert "result" in data
        assert "open.spotify.com" in data


class TestSpotifyCallback:
    def test_xss_in_error_param_is_escaped(self, client):
        xss_payload = '<script>alert("xss")</script>'
        resp = client.get(f"/callback?error={xss_payload}")
        html = resp.data.decode()
        # The raw script tag must NOT appear — it should be HTML-escaped
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_xss_in_error_description_is_escaped(self, client):
        xss_payload = '<img src=x onerror=alert(1)>'
        resp = client.get(f"/callback?error=access_denied&error_description={xss_payload}")
        html = resp.data.decode()
        # The raw tag must be escaped — check that no unescaped <img is present
        assert "<img " not in html
        assert "&lt;img" in html

    @patch("app.handle_spotify_callback", return_value=True)
    def test_successful_callback(self, mock_handle, client):
        resp = client.get("/callback?code=valid_code")
        html = resp.data.decode()
        assert "Spotify Connected" in html

    @patch("app.handle_spotify_callback", return_value=False)
    def test_failed_code_exchange(self, mock_handle, client):
        resp = client.get("/callback?code=bad_code")
        html = resp.data.decode()
        assert "Authentication Failed" in html


class TestAnalyzeEndpoint:
    @patch("app.analyze_band_song")
    def test_returns_analysis(self, mock_analyze, client):
        mock_analyze.return_value = {"artist": "Test", "genre": ["Rock"]}
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"artist": "Test", "track": "Song"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["artist"] == "Test"

    def test_rejects_missing_artist(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"track": "Song"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_empty_artist(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"artist": "", "track": "Song"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_long_artist(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"artist": "x" * 201}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("app.analyze_band_song", side_effect=ValueError("AI error"))
    def test_returns_400_on_value_error(self, mock_analyze, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"artist": "Test"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestRunHistoryEndpoints:
    @patch("app.load_runs")
    def test_get_runs(self, mock_load, client):
        mock_load.return_value = [{"run_id": "r1", "tracks": []}]
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["runs"]) == 1

    @patch("app.load_runs", return_value=[])
    def test_get_runs_empty(self, mock_load, client):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        assert resp.get_json()["runs"] == []

    @patch("app.undo_last_run")
    @patch("core.src.playlist.get_spotify_client")
    def test_undo_run(self, mock_sp, mock_undo, client):
        mock_undo.return_value = {"undone": True, "removed": 3, "run_id": "r1"}
        resp = client.post("/api/runs/undo")
        assert resp.status_code == 200
        assert resp.get_json()["undone"] is True

    @patch("app.undo_last_run", side_effect=ValueError("No run history"))
    @patch("core.src.playlist.get_spotify_client")
    def test_undo_run_empty_history(self, mock_sp, mock_undo, client):
        resp = client.post("/api/runs/undo")
        assert resp.status_code == 400
        assert "error" in resp.get_json()


class TestOnboardingEndpoints:
    @patch("app.is_onboarding_completed", return_value=False)
    def test_onboarding_status_not_completed(self, mock_status, client):
        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 200
        assert resp.get_json()["completed"] is False

    @patch("app.is_onboarding_completed", return_value=True)
    def test_onboarding_status_completed(self, mock_status, client):
        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 200
        assert resp.get_json()["completed"] is True

    @patch("app.set_onboarding_completed")
    def test_mark_onboarding_complete(self, mock_set, client):
        resp = client.post("/api/onboarding/complete")
        assert resp.status_code == 200
        mock_set.assert_called_once_with(True)


class TestPlaylistsEndpoint:
    @patch("app.get_user_playlists")
    def test_lists_playlists(self, mock_playlists, client):
        mock_playlists.return_value = [{"id": "pl1", "name": "My Playlist", "track_count": 5}]
        resp = client.get("/api/playlists")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["playlists"]) == 1
        assert data["playlists"][0]["id"] == "pl1"

    @patch("app.get_user_playlists", side_effect=Exception("Not connected"))
    def test_returns_error_when_not_connected(self, mock_playlists, client):
        resp = client.get("/api/playlists")
        assert resp.status_code == 500
        assert "error" in resp.get_json()


class TestRunStatusEndpoint:
    def test_unknown_run_returns_status(self, client):
        resp = client.get("/api/run/nonexistent/status")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "not_found"
