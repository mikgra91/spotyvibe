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
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


class TestHelpContent:
    @patch("app.BASE_DIR")
    def test_returns_html_from_manual(self, mock_base_dir, client, tmp_path):
        manual = tmp_path / "UserManual.md"
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


class TestClearDebugLog:
    def test_clears_log(self, client, tmp_path):
        log_file = tmp_path / "debug.log"
        log_file.write_text("log data")
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            resp = client.delete("/api/settings/debug-log")
        assert resp.status_code == 200
        assert not log_file.exists()

    def test_ok_when_no_log(self, client, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
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
