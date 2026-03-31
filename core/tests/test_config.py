"""Tests for config.py — credential management and settings getters."""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock


import config


class TestGetModel:
    def test_returns_env_value(self):
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4o"}):
            assert config.get_model() == "gpt-4o"

    def test_falls_back_to_default(self):
        with patch.dict(os.environ, {"OPENAI_MODEL": ""}, clear=False):
            assert config.get_model() == config.DEFAULT_OPENAI_MODEL

    def test_falls_back_when_unset(self):
        env = os.environ.copy()
        env.pop("OPENAI_MODEL", None)
        with patch.dict(os.environ, env, clear=True):
            assert config.get_model() == config.DEFAULT_OPENAI_MODEL


class TestGetDebugMode:
    @patch.dict(os.environ, {"DEBUG_MODE": "true"})
    def test_true_when_true(self):
        assert config.get_debug_mode() is True

    @patch.dict(os.environ, {"DEBUG_MODE": "1"})
    def test_true_when_one(self):
        assert config.get_debug_mode() is True

    @patch.dict(os.environ, {"DEBUG_MODE": "on"})
    def test_true_when_on(self):
        assert config.get_debug_mode() is True

    @patch.dict(os.environ, {"DEBUG_MODE": "ON"})
    def test_case_insensitive(self):
        assert config.get_debug_mode() is True

    @patch.dict(os.environ, {"DEBUG_MODE": ""})
    def test_false_when_empty(self):
        assert config.get_debug_mode() is False

    @patch.dict(os.environ, {"DEBUG_MODE": "false"})
    def test_false_when_false(self):
        assert config.get_debug_mode() is False


class TestGetPlaylistSize:
    @patch.dict(os.environ, {"PLAYLIST_SIZE": "25"})
    def test_returns_configured_value(self):
        assert config.get_playlist_size() == 25

    @patch.dict(os.environ, {"PLAYLIST_SIZE": "3"})
    def test_clamps_to_batch_size(self):
        # Must be at least BATCH_SIZE
        assert config.get_playlist_size() == config.BATCH_SIZE

    @patch.dict(os.environ, {"PLAYLIST_SIZE": ""})
    def test_falls_back_to_default(self):
        assert config.get_playlist_size() == config.DEFAULT_PLAYLIST_SIZE

    @patch.dict(os.environ, {"PLAYLIST_SIZE": "not_a_number"})
    def test_falls_back_on_invalid(self):
        assert config.get_playlist_size() == config.DEFAULT_PLAYLIST_SIZE


class TestGetNewArtistPercentage:
    @patch.dict(os.environ, {"NEW_ARTIST_PERCENTAGE": "50"})
    def test_returns_configured_value(self):
        assert config.get_new_artist_percentage() == 50

    @patch.dict(os.environ, {"NEW_ARTIST_PERCENTAGE": "0"})
    def test_clamps_low_to_one(self):
        assert config.get_new_artist_percentage() == 1

    @patch.dict(os.environ, {"NEW_ARTIST_PERCENTAGE": "200"})
    def test_clamps_high_to_hundred(self):
        assert config.get_new_artist_percentage() == 100

    @patch.dict(os.environ, {"NEW_ARTIST_PERCENTAGE": ""})
    def test_falls_back_to_default(self):
        assert config.get_new_artist_percentage() == config.DEFAULT_NEW_ARTIST_PERCENTAGE

    @patch.dict(os.environ, {"NEW_ARTIST_PERCENTAGE": "abc"})
    def test_falls_back_on_invalid(self):
        assert config.get_new_artist_percentage() == config.DEFAULT_NEW_ARTIST_PERCENTAGE


class TestGetSettings:
    @patch.dict(os.environ, {
        "OPENAI_MODEL": "gpt-4o",
        "DEBUG_MODE": "true",
        "PLAYLIST_SIZE": "20",
        "NEW_ARTIST_PERCENTAGE": "40",
    })
    def test_returns_all_settings(self):
        settings = config.get_settings()
        assert settings["model"] == "gpt-4o"
        assert settings["debug_mode"] is True
        assert settings["playlist_size"] == 20
        assert settings["new_artist_percentage"] == 40


class TestGetCredentials:
    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_masks_secrets(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "sk-abcdef123456",
            "SPOTIPY_CLIENT_ID": "myclientid1234",
            "SPOTIPY_CLIENT_SECRET": "mysecret5678",
            "OPENAI_MODEL": "gpt-4o",
            "DEBUG_MODE": "",
            "PLAYLIST_SIZE": "20",
            "NEW_ARTIST_PERCENTAGE": "30",
        }
        creds = config.get_credentials()
        # Secrets should be masked — last 4 characters visible
        assert creds["OPENAI_API_KEY"]["masked"].endswith("3456")
        assert creds["OPENAI_API_KEY"]["is_set"] is True
        assert "*" in creds["OPENAI_API_KEY"]["masked"]

        # Non-secrets should return full value
        assert creds["OPENAI_MODEL"]["value"] == "gpt-4o"
        assert creds["OPENAI_MODEL"]["is_set"] is True

    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_empty_secret_returns_empty_mask(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "",
            "SPOTIPY_CLIENT_ID": "",
            "SPOTIPY_CLIENT_SECRET": "",
            "OPENAI_MODEL": "",
            "DEBUG_MODE": "",
            "PLAYLIST_SIZE": "",
            "NEW_ARTIST_PERCENTAGE": "",
        }
        creds = config.get_credentials()
        assert creds["OPENAI_API_KEY"]["masked"] == ""
        assert creds["OPENAI_API_KEY"]["is_set"] is False

    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_short_secret_shows_stars(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "abc",
            "SPOTIPY_CLIENT_ID": "",
            "SPOTIPY_CLIENT_SECRET": "",
            "OPENAI_MODEL": "",
            "DEBUG_MODE": "",
            "PLAYLIST_SIZE": "",
            "NEW_ARTIST_PERCENTAGE": "",
        }
        creds = config.get_credentials()
        # Short secrets (≤4 chars) → "****"
        assert creds["OPENAI_API_KEY"]["masked"] == "****"
        assert creds["OPENAI_API_KEY"]["is_set"] is True


class TestSaveCredentials:
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_saves_known_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"OPENAI_MODEL": "gpt-4o"})
        mock_set_key.assert_called_once_with(
            str(config.CREDENTIALS_FILE), "OPENAI_MODEL", "gpt-4o"
        )
        mock_load.assert_called_once()

    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_skips_none_values(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"OPENAI_MODEL": None, "DEBUG_MODE": "true"})
        mock_set_key.assert_called_once_with(
            str(config.CREDENTIALS_FILE), "DEBUG_MODE", "true"
        )

    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_ignores_unknown_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"UNKNOWN_KEY": "value"})
        mock_set_key.assert_not_called()


class TestEnsureEnv:
    def test_creates_credentials_file(self, tmp_path):
        cred_file = tmp_path / ".credentials"
        app_dir = tmp_path
        old_env = tmp_path / ".env"

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        assert cred_file.exists()
        content = cred_file.read_text()
        for key in config.USER_KEYS:
            assert f"{key}=" in content

    def test_appends_missing_keys(self, tmp_path):
        cred_file = tmp_path / ".credentials"
        cred_file.write_text("OPENAI_API_KEY=sk-test\n")
        app_dir = tmp_path
        old_env = tmp_path / ".env"

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        content = cred_file.read_text()
        # Original key preserved
        assert "OPENAI_API_KEY=sk-test" in content
        # Missing keys were appended
        assert "OPENAI_MODEL=" in content

    def test_migrates_old_env_file(self, tmp_path):
        old_env = tmp_path / ".env"
        old_env.write_text("OPENAI_API_KEY=sk-old\n")
        cred_file = tmp_path / ".credentials"
        app_dir = tmp_path

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        assert cred_file.exists()
        assert not old_env.exists()
        content = cred_file.read_text()
        assert "OPENAI_API_KEY=sk-old" in content

    def test_skips_migration_on_android(self, tmp_path):
        """On Android the old .env migration must be skipped."""
        old_env = tmp_path / ".env"
        old_env.write_text("OPENAI_API_KEY=sk-old\n")
        cred_file = tmp_path / ".credentials"
        app_dir = tmp_path

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env), \
             patch.object(config, "IS_ANDROID", True):
            config.ensure_env()

        # .env should NOT have been migrated
        assert old_env.exists()
        # A fresh credentials file should have been created instead
        assert cred_file.exists()


class TestGetAppDir:
    def test_desktop_uses_localappdata(self):
        with patch.object(config, "IS_ANDROID", False), \
             patch.dict(os.environ, {"LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}):
            result = config._get_app_dir()
            assert result == Path("C:\\Users\\test\\AppData\\Local") / "spotyvibe"

    def test_desktop_falls_back_to_home(self):
        env = os.environ.copy()
        env.pop("LOCALAPPDATA", None)
        with patch.object(config, "IS_ANDROID", False), \
             patch.dict(os.environ, env, clear=True):
            result = config._get_app_dir()
            assert result == Path(os.path.expanduser("~")) / "spotyvibe"

    def test_android_uses_files_dir_env(self):
        with patch.object(config, "IS_ANDROID", True), \
             patch.dict(os.environ, {"SPOTYVIBE_FILES_DIR": "/data/data/com.spotyvibe.app/files"}):
            result = config._get_app_dir()
            assert result == Path("/data/data/com.spotyvibe.app/files") / "spotyvibe"

    def test_android_falls_back_to_home(self):
        env = os.environ.copy()
        env.pop("SPOTYVIBE_FILES_DIR", None)
        with patch.object(config, "IS_ANDROID", True), \
             patch.dict(os.environ, env, clear=True):
            result = config._get_app_dir()
            assert result == Path(os.path.expanduser("~")) / "spotyvibe"


class TestIsAndroid:
    def test_false_on_desktop(self):
        assert config.IS_ANDROID is False


class TestBaseDir:
    def test_uses_meipass_when_frozen(self, tmp_path):
        """PyInstaller sets sys.frozen + sys._MEIPASS; BASE_DIR should follow."""
        had_frozen = hasattr(sys, "frozen")
        original_frozen = getattr(sys, "frozen", None)
        had_meipass = hasattr(sys, "_MEIPASS")
        original_meipass = getattr(sys, "_MEIPASS", None)

        try:
            setattr(sys, "frozen", True)
            setattr(sys, "_MEIPASS", str(tmp_path))
            reloaded = importlib.reload(config)
            assert reloaded.BASE_DIR == tmp_path.resolve()
        finally:
            if had_frozen:
                setattr(sys, "frozen", original_frozen)
            else:
                try:
                    delattr(sys, "frozen")
                except Exception:
                    pass

            if had_meipass:
                setattr(sys, "_MEIPASS", original_meipass)
            else:
                try:
                    delattr(sys, "_MEIPASS")
                except Exception:
                    pass

            # Restore BASE_DIR for the rest of the test suite.
            importlib.reload(config)

