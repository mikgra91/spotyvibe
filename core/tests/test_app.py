"""Tests for app.py — Flask endpoints."""

import json
from unittest.mock import patch
from pathlib import Path

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
        resp = client.get("/onboarding?replay=1")
        assert resp.status_code == 200

    def test_contains_onboarding_pages(self, client):
        resp = client.get("/onboarding?replay=1")
        html = resp.data.decode()
        assert "SpotyVibe" in html
        assert "ob-page" in html

    def test_contains_credentials_section(self, client):
        resp = client.get("/onboarding?replay=1")
        html = resp.data.decode()
        assert "OpenAI" in html
        assert "Spotify" in html

    @patch("app.is_onboarding_completed", return_value=True)
    def test_redirects_when_completed_without_replay(self, _mock, client):
        resp = client.get("/onboarding")
        assert resp.status_code == 302

    @patch("app.is_onboarding_completed", return_value=False)
    def test_renders_when_not_completed(self, _mock, client):
        resp = client.get("/onboarding")
        assert resp.status_code == 200


class TestSetupGuide:
    def test_guide_openai_returns_json(self, client):
        resp = client.get("/api/help/guide/openai_api_key")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "title" in data
        assert "steps" in data
        assert len(data["steps"]) >= 1

    def test_guide_spotify_returns_json(self, client):
        resp = client.get("/api/help/guide/spotify_developer_app")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "title" in data
        assert "steps" in data
        assert len(data["steps"]) >= 1

    def test_guide_unknown_slug_returns_404(self, client):
        resp = client.get("/api/help/guide/nonexistent")
        assert resp.status_code == 404


class TestHelpContent:
    def test_returns_html_from_manual(self, client, tmp_path):
        doc_root = tmp_path / "documentation"
        doc_root.mkdir()
        (doc_root / "help.en.md").write_text("# Help\n\nSome **bold** text.")
        with patch("core.src.localised_docs.DOC_ROOT", doc_root):
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
        original_data = app_module._models_cache["data"]
        original_expires = app_module._models_cache["expires"]
        try:
            app_module._models_cache["data"] = None
            app_module._models_cache["expires"] = 0
            resp = client.get("/api/settings/models")
            assert resp.status_code == 400
            data = resp.get_json()
            assert "error" in data
        finally:
            app_module._models_cache["data"] = original_data
            app_module._models_cache["expires"] = original_expires


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
    @patch("app.save_settings")
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

    @patch("app.save_settings")
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
    @patch("app.get_active_profile_id", return_value="some-id")
    @patch("app.get_profile_status")
    def test_returns_status(self, mock_status, mock_pid, client):
        mock_status.return_value = {"trained": True, "last_updated": "2025-01-01"}
        resp = client.get("/api/profile/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trained"] is True

    def test_returns_no_profile_when_none_active(self, client):
        with patch("app.get_active_profile_id", return_value=""):
            resp = client.get("/api/profile/status")
        data = resp.get_json()
        assert data["trained"] is False
        assert data["no_profile"] is True


class TestProfileData:
    @patch("app.get_active_profile_id", return_value="some-id")
    @patch("app.load_profile")
    def test_returns_profile(self, mock_load, mock_pid, client):
        mock_load.return_value = {"preferences": {"core_description": "rock"}}
        resp = client.get("/api/profile/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preferences"]["core_description"] == "rock"

    def test_returns_empty_json_when_no_active_profile(self, client):
        with patch("app.get_active_profile_id", return_value=""):
            resp = client.get("/api/profile/data")
        assert resp.status_code == 200
        assert resp.get_json() == {}


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

    @patch("app.save_profile_sections")
    def test_saves_with_empty_descriptions(self, mock_save, client):
        mock_save.return_value = {"last_updated": "2025-06-01T00:00:00"}
        resp = client.post(
            "/api/save-profile",
            data=json.dumps({"core_description": "", "must_have": "guitar"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

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
            data=json.dumps({"action": "dislike", "artist": "Bad", "track": "Song", "source": "review"}),
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
            data=json.dumps({"artist": "A", "track": "B", "source": "review"}),
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

    @patch("app.save_run")
    @patch("app.add_to_playlist")
    @patch("app.iter_search_tracks")
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
        mock_save, mock_gpt, mock_filter, mock_search, mock_add,
        mock_save_run, client
    ):
        mock_load.return_value = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
            "preferences": {},
        }
        mock_norm.return_value = mock_load.return_value
        mock_gpt.return_value = (
            {
                "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
                "new_artists": ["a"],
                "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
            },
            {"usage": None, "latency_s": 0.0},
        )
        mock_filter.return_value = {
            "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        mock_update.return_value = mock_load.return_value
        # L3 (2026-05-06): app.py now consumes iter_search_tracks (a
        # generator yielding ('found' | 'not_found', payload)). side_effect
        # rebuilds the iterator each time the generator is invoked.
        mock_search.side_effect = lambda *_a, **_kw: iter(
            [("found",
              {"artist": "a", "track": "b", "uri": f"spotify:track:{i}",
               "cover_url": None})
             for i in range(10)]
        )
        mock_add.return_value = {"url": "https://open.spotify.com/playlist/test", "added": 10}

        resp = client.post(
            "/api/run",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = resp.data.decode()
        assert "result" in data
        assert '"artist": "a"' in data

    @patch("app.save_run")
    @patch("app.add_to_playlist")
    @patch("app.iter_search_tracks")
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
    def test_accepts_temperature_and_playlist_size(
        self, mock_trained, mock_spotify, mock_debug, mock_size,
        mock_percentage, mock_load, mock_norm, mock_update,
        mock_save, mock_gpt, mock_filter, mock_search, mock_add,
        mock_save_run, client
    ):
        """Wave 2: /api/run accepts temperature and playlist_size from client."""
        mock_load.return_value = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
            "preferences": {},
        }
        mock_norm.return_value = mock_load.return_value
        mock_gpt.return_value = (
            {
                "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 15,
                "new_artists": ["a"],
                "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
            },
            {"usage": None, "latency_s": 0.0},
        )
        mock_filter.return_value = {
            "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 15,
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        mock_update.return_value = mock_load.return_value
        mock_search.side_effect = lambda *_a, **_kw: iter(
            [("found",
              {"artist": "a", "track": "b", "uri": f"spotify:track:{i}",
               "cover_url": None})
             for i in range(15)]
        )
        mock_add.return_value = {"url": "https://open.spotify.com/playlist/test", "added": 15}

        resp = client.post(
            "/api/run",
            data=json.dumps({"temperature": 1.0, "playlist_size": 15}),
            content_type="application/json",
        )
        data = resp.data.decode()
        assert "result" in data
        # Verify call_gpt was called with a temperature near 1.0 (not default 0.7)
        call_args = mock_gpt.call_args
        assert call_args is not None
        used_temp = call_args[1].get("temperature", call_args[0][1] if len(call_args[0]) > 1 else None)
        # Temperature should be close to 1.0 (the base_temp from client)
        assert used_temp is not None
        assert used_temp >= 0.8  # at least 0.8 (1.0 - 0.2 max decay)


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

    @patch("app.load_profile")
    @patch("app.load_runs", return_value=[])
    @patch("app.get_active_profile_id", return_value=None)
    @patch("app.get_spotify_auth_status", return_value="not_authenticated")
    @patch("app.get_credentials", return_value={
        "OPENAI_API_KEY":     {"is_set": False, "masked": ""},
        "SPOTIPY_CLIENT_ID":  {"is_set": False, "masked": ""},
        "SPOTIPY_CLIENT_SECRET": {"is_set": False, "masked": ""},
    })
    def test_progress_initial_state(self, mock_creds, mock_sp, mock_pid, mock_runs, mock_prof, client):
        resp = client.get("/api/onboarding/progress")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["keys_saved"] is False
        assert body["spotify_connected"] is False
        assert body["profile_created"] is False
        assert body["playlist_generated"] is False
        assert body["feedback_count"] == 0
        assert body["feedback_done"] is False
        assert body["feedback_target"] == 3
        # load_profile should not be touched when no profile is active
        mock_prof.assert_not_called()

    @patch("app.load_profile", return_value={"feedback": {
        "liked_tracks": [{"a": 1}, {"a": 2}],
        "disliked_tracks": [{"a": 3}],
    }})
    @patch("app.load_runs", return_value=[{"run_id": "r1"}])
    @patch("app.get_active_profile_id", return_value="profile-uuid")
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    @patch("app.get_credentials", return_value={
        "OPENAI_API_KEY":     {"is_set": True, "masked": "***k"},
        "SPOTIPY_CLIENT_ID":  {"is_set": True, "masked": "***1"},
        "SPOTIPY_CLIENT_SECRET": {"is_set": True, "masked": "***2"},
    })
    def test_progress_fully_set_up(self, mock_creds, mock_sp, mock_pid, mock_runs, mock_prof, client):
        resp = client.get("/api/onboarding/progress")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["keys_saved"] is True
        assert body["spotify_connected"] is True
        assert body["profile_created"] is True
        assert body["playlist_generated"] is True
        assert body["feedback_count"] == 3
        assert body["feedback_done"] is True


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


class TestPlaylistTracksEndpoint:
    @patch("app.get_playlist_tracks")
    def test_returns_tracks(self, mock_tracks, client):
        mock_tracks.return_value = [
            {"artist": "A", "track": "T", "uri": "spotify:track:1", "track_id": "1",
             "cover_url": None, "spotify_url": None, "artist_url": None, "album_url": None},
        ]
        resp = client.get("/api/playlist/pl1/tracks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["artist"] == "A"

    @patch("app.get_playlist_tracks", side_effect=Exception("Not authenticated"))
    def test_returns_error_on_failure(self, mock_tracks, client):
        resp = client.get("/api/playlist/pl1/tracks")
        assert resp.status_code == 500
        assert "error" in resp.get_json()
        assert data["tracks"] == [] if (data := resp.get_json()) else True


class TestRunStatusEndpoint:
    def test_unknown_run_returns_status(self, client):
        resp = client.get("/api/run/nonexistent/status")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "not_found"


class TestGetProfiles:
    @patch("app.get_active_profile_id", return_value="abc-123")
    @patch("app.list_profiles", return_value=[{"id": "abc-123", "name": "Work", "trained": True, "last_updated": "2025-01-01"}])
    def test_returns_profiles_and_active_id(self, mock_list, mock_pid, client):
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["profiles"]) == 1
        assert data["active_id"] == "abc-123"

    @patch("app.get_active_profile_id", return_value="")
    @patch("app.list_profiles", return_value=[])
    def test_returns_empty_list(self, mock_list, mock_pid, client):
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profiles"] == []
        assert data["active_id"] == ""


class TestCreateProfileEndpoint:
    @patch("app.create_profile", return_value={"id": "new-uuid", "name": "Workout"})
    def test_creates_profile(self, mock_create, client):
        resp = client.post("/api/profiles", json={"name": "Workout"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["id"] == "new-uuid"
        assert data["name"] == "Workout"
        mock_create.assert_called_once_with("Workout")

    def test_rejects_empty_name(self, client):
        resp = client.post("/api/profiles", json={"name": ""})
        assert resp.status_code == 400
        assert "required" in resp.get_json()["error"].lower()

    def test_rejects_missing_name(self, client):
        resp = client.post("/api/profiles", json={})
        assert resp.status_code == 400

    def test_rejects_too_long_name(self, client):
        resp = client.post("/api/profiles", json={"name": "A" * 50})
        assert resp.status_code == 400
        assert "too long" in resp.get_json()["error"].lower()

    @patch("app.create_profile", side_effect=ValueError("already exists"))
    def test_returns_400_on_duplicate(self, mock_create, client):
        resp = client.post("/api/profiles", json={"name": "Dup"})
        assert resp.status_code == 400
        assert "already exists" in resp.get_json()["error"]


class TestDeleteProfileEndpoint:
    @patch("app.delete_profile")
    def test_deletes_profile(self, mock_delete, client):
        resp = client.delete("/api/profiles/abc-123")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_delete.assert_called_once_with("abc-123")

    @patch("app.delete_profile", side_effect=ValueError("Profile not found."))
    def test_returns_400_on_not_found(self, mock_delete, client):
        resp = client.delete("/api/profiles/nonexistent")
        assert resp.status_code == 400
        assert "not found" in resp.get_json()["error"].lower()


class TestActivateProfileEndpoint:
    @patch("app.activate_profile")
    def test_activates_profile(self, mock_activate, client):
        resp = client.post("/api/profiles/abc-123/activate")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"
        mock_activate.assert_called_once_with("abc-123")

    @patch("app.activate_profile", side_effect=ValueError("Profile not found."))
    def test_returns_400_on_not_found(self, mock_activate, client):
        resp = client.post("/api/profiles/nonexistent/activate")
        assert resp.status_code == 400
        assert "not found" in resp.get_json()["error"].lower()


# ── HTML structure tests ─────────────────────────────────────────────
#
# Verify that the rendered main page contains all critical interactive
# elements with proper attributes. A missing button, broken dropdown,
# or unregistered onclick handler is caught here.

class TestMainPageStructure:
    """Verify the rendered main page has all critical interactive UI elements."""

    @pytest.fixture(autouse=True)
    def _load_page(self, client):
        with patch("app.is_onboarding_completed", return_value=True):
            resp = client.get("/")
        self.html = resp.data.decode()

    def test_profile_dropdown_exists(self):
        """Profile dropdown must be present for users to switch profiles."""
        assert 'id="profileSelect"' in self.html
        assert 'id="profileDropdownLabel"' in self.html

    def test_profile_create_button_exists(self):
        """New profile button must exist and call createNewProfile."""
        assert 'id="profileCreateToggle"' in self.html
        assert 'onclick="createNewProfile()"' in self.html

    def test_profile_menu_exists(self):
        """Profile context menu (⋯) must exist with export, reset, delete actions."""
        assert 'id="profileMenuTrigger"' in self.html
        assert 'id="profileMenuExport"' in self.html
        assert 'id="profileMenuReset"' in self.html
        assert 'id="profileMenuDelete"' in self.html

    def test_train_buttons_exist(self):
        """AI train and save buttons must exist with proper onclick handlers."""
        assert 'id="trainSendBtn"' in self.html
        assert 'onclick="sendTrainProfile()"' in self.html
        assert 'id="trainSaveBtn"' in self.html
        assert 'onclick="saveProfileDirect()"' in self.html

    def test_generate_button_exists(self):
        """Generate playlist button must exist."""
        assert 'id="runBtn"' in self.html
        assert 'onclick="runPipeline()"' in self.html

    def test_cancel_button_exists(self):
        """Cancel generation button must exist."""
        assert 'id="cancelBtn"' in self.html
        assert 'onclick="cancelGeneration()"' in self.html

    def test_analysis_button_exists(self):
        """Analysis send button must exist."""
        assert 'id="analysisSendBtn"' in self.html
        assert 'onclick="runAnalysis()"' in self.html

    def test_section_toggles_exist(self):
        """All section toggle buttons must have onclick handlers."""
        assert 'onclick="toggleTrainBody()"' in self.html
        assert 'onclick="toggleGenerateBody()"' in self.html
        assert 'onclick="toggleAnalysisBody()"' in self.html
        assert 'onclick="toggleReviewBody()"' in self.html

    def test_credentials_modal_exists(self):
        """Credentials modal must exist with save button."""
        assert 'id="credentialsModal"' in self.html
        assert 'onclick="saveCredentials()"' in self.html

    def test_settings_modal_exists(self):
        """Settings modal must exist with save button."""
        assert 'id="settingsModal"' in self.html or 'onclick="saveSettings()"' in self.html

    def test_help_modal_exists(self):
        assert 'id="helpModal"' in self.html

    def test_preview_overlay_exists(self):
        assert 'id="spotifyPreviewOverlay"' in self.html

    def test_completeness_meter_exists(self):
        """Profile completeness meter must be rendered."""
        assert 'id="profileCompletenessCard"' in self.html
        assert 'id="completenessScore"' in self.html
        assert 'id="completenessBarFill"' in self.html

    def test_taste_dashboard_section_exists(self):
        """Taste dashboard section must be rendered."""
        assert 'id="tasteDashboardSection"' in self.html or 'id="dashboardBody"' in self.html

    def test_tab_navigation_exists(self):
        """Tab bar with all three tabs must exist."""
        assert 'id="tab-openai"' in self.html
        assert 'id="tab-spotify"' in self.html
        assert 'id="tab-history"' in self.html

    def test_main_js_loaded(self):
        """main.js must be loaded as an ES module."""
        assert 'type="module"' in self.html
        assert 'main.js' in self.html

    def test_train_fields_exist(self):
        """Profile editing text fields must be rendered."""
        assert 'id="trainCoreDesc"' in self.html
        assert 'id="trainMustHave"' in self.html
        assert 'id="trainSoftPrefs"' in self.html
        assert 'id="trainAvoid"' in self.html

    def test_playlist_mode_controls_exist(self):
        """Apply playlist modal and playlist picker must exist."""
        assert 'id="applyPlaylistModal"' in self.html or 'id="applyPlaylistPicker"' in self.html


class TestOnclickHandlersRegistered:
    """Verify that every onclick function referenced in the main page HTML
    is either registered as window.X in main.js or defined in a non-module
    script loaded before it.

    This catches dead buttons — elements that look clickable but throw
    ReferenceError because the function was never exposed globally.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        import re
        # Collect all window.X assignments from main.js
        main_js = (Path(__file__).resolve().parent.parent.parent
                   / "frontend" / "static" / "js" / "main.js")
        main_text = main_js.read_text(encoding="utf-8")
        self.window_fns = set(re.findall(r'window\.(\w+)\s*=', main_text))

        # Collect functions from non-module scripts that are globally scoped
        non_module_scripts = [
            "frontend/static/js/modules/setup_guide.js",
        ]
        for script_path in non_module_scripts:
            full = Path(__file__).resolve().parent.parent.parent / script_path
            if full.exists():
                text = full.read_text(encoding="utf-8")
                # Match top-level function declarations
                self.window_fns.update(re.findall(r'^function\s+(\w+)', text, re.MULTILINE))

        # Inline scripts in templates (privacy_modal etc.) define functions too
        templates_dir = (Path(__file__).resolve().parent.parent.parent
                         / "frontend" / "templates")
        for tmpl in templates_dir.rglob("*.html"):
            text = tmpl.read_text(encoding="utf-8")
            # Functions defined in <script> blocks inside templates
            self.window_fns.update(re.findall(r'function\s+(\w+)\s*\(', text))

        # Collect all onclick="fnName(..." from the main page templates
        self.onclick_fns = set()
        for tmpl in templates_dir.rglob("*.html"):
            # Skip onboarding — it has its own script ecosystem
            # Skip macros.html — contains Jinja2 macro definitions, not rendered HTML
            if "onboarding" in tmpl.name or tmpl.name == "macros.html":
                continue
            text = tmpl.read_text(encoding="utf-8")
            self.onclick_fns.update(re.findall(r'onclick="(\w+)\(', text))

        # Remove control-flow keywords that aren't function names
        self.onclick_fns.discard("if")
        self.onclick_fns.discard("event")

    def test_all_onclick_handlers_are_registered(self):
        """Every onclick handler in the main page must resolve to a global function."""
        missing = self.onclick_fns - self.window_fns
        assert missing == set(), (
            f"These onclick handlers are referenced in templates but never "
            f"registered as window globals or top-level functions: {sorted(missing)}"
        )


# ── Endpoint integration tests ───────────────────────────────────────
#
# These use the isolated_profiles_env fixture so the real business logic
# runs against a temp filesystem. No mocking of list_profiles, create_profile,
# etc. — only the filesystem location is redirected.

class TestProfileEndpointIntegration:
    """Integration tests for profile CRUD endpoints with real business logic."""

    def test_create_then_list_via_endpoints(self, client, isolated_profiles_env):
        """POST /api/profiles → GET /api/profiles: created profile must appear."""
        # Create
        resp = client.post("/api/profiles", json={"name": "Rock"})
        assert resp.status_code == 201
        created = resp.get_json()
        pid = created["id"]
        assert created["name"] == "Rock"

        # List
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["profiles"]) == 1
        assert data["profiles"][0]["id"] == pid
        assert data["profiles"][0]["name"] == "Rock"
        assert data["active_id"] == pid  # auto-activated

    def test_create_then_get_profile_data(self, client, isolated_profiles_env):
        """POST /api/profiles → GET /api/profile/data: profile data loads."""
        client.post("/api/profiles", json={"name": "Jazz"})

        resp = client.get("/api/profile/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Jazz"
        assert "preferences" in data

    def test_create_then_get_profile_status(self, client, isolated_profiles_env):
        """POST /api/profiles → GET /api/profile/status: untrained status."""
        client.post("/api/profiles", json={"name": "Test"})

        resp = client.get("/api/profile/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trained"] is False
        assert "no_profile" not in data  # profile exists, just untrained

    def test_create_two_then_activate_first(self, client, isolated_profiles_env):
        """Create two profiles, activate the first, verify it's the active one."""
        r1 = client.post("/api/profiles", json={"name": "Rock"}).get_json()
        r2 = client.post("/api/profiles", json={"name": "Jazz"}).get_json()

        # Jazz is active (last created)
        resp = client.get("/api/profiles")
        assert resp.get_json()["active_id"] == r2["id"]

        # Activate Rock
        resp = client.post(f"/api/profiles/{r1['id']}/activate")
        assert resp.status_code == 200

        # Verify Rock is now active
        resp = client.get("/api/profiles")
        assert resp.get_json()["active_id"] == r1["id"]

        # Profile data should be Rock's
        resp = client.get("/api/profile/data")
        assert resp.get_json()["name"] == "Rock"

    def test_create_then_delete(self, client, isolated_profiles_env):
        """Create → delete → list: profile must be gone."""
        created = client.post("/api/profiles", json={"name": "Temp"}).get_json()
        pid = created["id"]

        resp = client.delete(f"/api/profiles/{pid}")
        assert resp.status_code == 200

        resp = client.get("/api/profiles")
        data = resp.get_json()
        assert len(data["profiles"]) == 0
        assert data["active_id"] == ""

    def test_save_then_load_profile_sections(self, client, isolated_profiles_env):
        """POST /api/save-profile → GET /api/profile/data: sections persist."""
        client.post("/api/profiles", json={"name": "Rock"})

        resp = client.post("/api/save-profile", json={
            "core_description": "Heavy rock with soaring vocals",
            "must_have": "guitar solos\nhigh energy",
            "soft_preferences": "prog",
            "avoid": "country",
        })
        assert resp.status_code == 200
        assert resp.get_json()["last_updated"] is not None

        resp = client.get("/api/profile/data")
        prefs = resp.get_json()["preferences"]
        assert prefs["core_description"] == "Heavy rock with soaring vocals"
        assert prefs["must_have"] == ["guitar solos", "high energy"]
        assert prefs["soft_preferences"] == ["prog"]
        assert prefs["avoid"] == ["country"]

    def test_no_profile_returns_empty_data(self, client, isolated_profiles_env):
        """GET /api/profile/data with no active profile returns empty JSON."""
        resp = client.get("/api/profile/data")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_no_profile_returns_no_profile_status(self, client, isolated_profiles_env):
        """GET /api/profile/status with no active profile returns no_profile flag."""
        resp = client.get("/api/profile/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["no_profile"] is True
        assert data["trained"] is False

    def test_list_profiles_survives_corrupted_profile_dir(self, client, isolated_profiles_env):
        """GET /api/profiles doesn't crash when profiles dir has corrupt data."""
        profiles_dir = isolated_profiles_env["profiles_dir"]

        # Create a valid profile first
        created = client.post("/api/profiles", json={"name": "Good"}).get_json()

        # Add a corrupt subdirectory
        bad_uuid = "deadbeef-dead-beef-dead-beefdeadbeef"
        bad_dir = profiles_dir / bad_uuid
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text("NOT VALID JSON {{{")

        # Must not crash — returns only the valid profile
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["profiles"]) == 1
        assert data["profiles"][0]["name"] == "Good"


class TestSessionAndTokenEndpoints:
    """Endpoints used by the Web Playback SDK (§8a)."""

    @patch("app.get_spotify_session_info")
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    def test_session_returns_premium_flag(self, _mock_auth, mock_info, client):
        mock_info.return_value = {"is_premium": True, "product": "premium"}
        resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_premium"] is True
        assert data["product"] == "premium"
        assert data["authenticated"] is True

    @patch("app.get_spotify_session_info")
    @patch("app.get_spotify_auth_status", return_value="not_authenticated")
    def test_session_unauthenticated(self, _mock_auth, mock_info, client):
        mock_info.return_value = {"is_premium": False, "product": None}
        resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_premium"] is False
        assert data["authenticated"] is False

    @patch("app.get_spotify_access_token", return_value="tok_abc")
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    def test_token_endpoint_returns_access_token(self, _mock_auth, _mock_tok, client):
        resp = client.get("/api/spotify/token")
        assert resp.status_code == 200
        assert resp.get_json() == {"access_token": "tok_abc"}

    @patch("app.get_spotify_auth_status", return_value="not_authenticated")
    def test_token_endpoint_401_when_unauthenticated(self, _mock_auth, client):
        resp = client.get("/api/spotify/token")
        assert resp.status_code == 401

    @patch("app.get_spotify_access_token", return_value=None)
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    def test_token_endpoint_401_when_no_token(self, _mock_auth, _mock_tok, client):
        resp = client.get("/api/spotify/token")
        assert resp.status_code == 401


class TestPerfLogWiring:
    """M3 (2026-05-07): /api/run finally block records one perf_log row
    per generation. Patch ``core.src.perf_log.record_run`` and assert
    the call shape — keeps the wiring honest if a refactor moves the
    call site."""

    @patch("core.src.perf_log.record_run")
    @patch("app.save_run")
    @patch("app.add_to_playlist")
    @patch("app.iter_search_tracks")
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
    def test_perf_log_record_run_called_on_success(
        self, _mock_trained, _mock_spotify, _mock_debug, _mock_size,
        _mock_percentage, mock_load, mock_norm, mock_update,
        _mock_save, mock_gpt, mock_filter, mock_search, mock_add,
        _mock_save_run, mock_record, client,
    ):
        mock_load.return_value = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
            "preferences": {},
        }
        mock_norm.return_value = mock_load.return_value
        mock_gpt.return_value = (
            {
                "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
                "new_artists": ["a"],
                "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
            },
            {"usage": None, "latency_s": 0.0},
        )
        mock_filter.return_value = {
            "playlist": [{"artist": "a", "track": "b", "reason": "r"}] * 10,
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        mock_update.return_value = mock_load.return_value
        mock_search.side_effect = lambda *_a, **_kw: iter(
            [("found",
              {"artist": "a", "track": "b", "uri": f"spotify:track:{i}",
               "cover_url": None})
             for i in range(10)]
        )
        mock_add.return_value = {"url": "https://open.spotify.com/playlist/test", "added": 10}

        resp = client.post(
            "/api/run",
            data=json.dumps({"run_id": "test-run-001"}),
            content_type="application/json",
        )
        # Consume the streaming response so the generator runs to
        # completion (including the finally that calls perf_log).
        resp.data.decode()

        assert mock_record.called, "perf_log.record_run was never called"
        kwargs = mock_record.call_args.kwargs
        args = mock_record.call_args.args
        assert args and args[0] == "test-run-001"
        assert kwargs.get("tracks_target") == 10
        assert kwargs.get("tracks_found") == 10
        assert kwargs.get("exhausted") is False
        assert kwargs.get("error") is None

    @patch("core.src.perf_log.record_run")
    @patch("app.load_profile", side_effect=RuntimeError("boom"))
    @patch("app.get_playlist_size", return_value=10)
    @patch("app.get_debug_mode", return_value=False)
    @patch("app.get_spotify_auth_status", return_value="authenticated")
    @patch("app.is_profile_trained", return_value=True)
    def test_perf_log_record_run_called_on_error(
        self, _mock_trained, _mock_spotify, _mock_debug, _mock_size,
        _mock_load, mock_record, client,
    ):
        resp = client.post(
            "/api/run",
            data=json.dumps({"run_id": "test-run-err"}),
            content_type="application/json",
        )
        resp.data.decode()
        # Even when the run blew up before producing tracks, the finally
        # block should still record a perf-log row with the error
        # message. That's the whole point of writing it pre-finalize.
        assert mock_record.called
        kwargs = mock_record.call_args.kwargs
        assert kwargs.get("error") is not None
        assert "boom" in kwargs.get("error")
        assert kwargs.get("tracks_found") == 0


class TestSseErrorClassification:
    """U2 (2026-05-07): _sse_error tags transient upstream failures."""

    def _parse(self, sse_line):
        # SSE frame format: "data: {json}\n\n"
        assert sse_line.startswith("data: ")
        return json.loads(sse_line[len("data: "):].strip())

    def test_translatable_error_propagates_class(self):
        from app import _sse_error
        from core.src.errors import TranslatableError

        exc = TranslatableError(
            "error.transient.x", "Slow.", error_class="transient",
        )
        payload = self._parse(_sse_error(exc))
        assert payload["type"] == "error"
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.x"

    def test_openai_rate_limit_classified_transient(self):
        from app import _sse_error
        from core.src.openai_http import OpenAIRateLimitError

        exc = OpenAIRateLimitError("429", status_code=429)
        payload = self._parse(_sse_error(exc))
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.openai_rate_limited"

    def test_spotify_429_classified_transient(self):
        from app import _sse_error
        from spotipy.exceptions import SpotifyException

        exc = SpotifyException(429, -1, "rate limited")
        payload = self._parse(_sse_error(exc))
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.spotify_rate_limited"

    def test_spotify_503_classified_transient(self):
        from app import _sse_error
        from spotipy.exceptions import SpotifyException

        exc = SpotifyException(503, -1, "unavailable")
        payload = self._parse(_sse_error(exc))
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.spotify_unavailable"

    def test_spotify_4xx_not_classified_transient(self):
        from app import _sse_error
        from spotipy.exceptions import SpotifyException

        exc = SpotifyException(400, -1, "bad request")
        payload = self._parse(_sse_error(exc))
        assert "error_class" not in payload

    def test_plain_runtime_error_omits_class(self):
        from app import _sse_error

        payload = self._parse(_sse_error(RuntimeError("boom")))
        assert "error_class" not in payload
        assert payload["message"] == "boom"

    def test_string_message_path_unchanged(self):
        from app import _sse_error

        payload = self._parse(_sse_error("plain string error"))
        assert payload == {"type": "error", "message": "plain string error"}

