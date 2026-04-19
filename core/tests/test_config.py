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
    def test_clamps_to_minimum(self):
        # Hard minimum of 5 tracks
        assert config.get_playlist_size() == 5

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
    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_masks_secrets(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "sk-abcdef123456",
            "SPOTIPY_CLIENT_ID": "myclientid1234",
            "SPOTIPY_CLIENT_SECRET": "mysecret5678",
        }
        creds = config.get_credentials()
        # Secrets should be masked — last 4 characters visible
        assert creds["OPENAI_API_KEY"]["masked"].endswith("3456")
        assert creds["OPENAI_API_KEY"]["is_set"] is True
        assert "*" in creds["OPENAI_API_KEY"]["masked"]

        # Only credential keys should be returned
        assert "OPENAI_MODEL" not in creds
        assert "DEBUG_MODE" not in creds

    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_empty_secret_returns_empty_mask(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "",
            "SPOTIPY_CLIENT_ID": "",
            "SPOTIPY_CLIENT_SECRET": "",
        }
        creds = config.get_credentials()
        assert creds["OPENAI_API_KEY"]["masked"] == ""
        assert creds["OPENAI_API_KEY"]["is_set"] is False

    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.ensure_env")
    @patch("config.dotenv_values")
    def test_short_secret_shows_stars(self, mock_dotenv, mock_ensure):
        mock_dotenv.return_value = {
            "OPENAI_API_KEY": "abc",
            "SPOTIPY_CLIENT_ID": "",
            "SPOTIPY_CLIENT_SECRET": "",
        }
        creds = config.get_credentials()
        # Short secrets (≤4 chars) → "****"
        assert creds["OPENAI_API_KEY"]["masked"] == "****"
        assert creds["OPENAI_API_KEY"]["is_set"] is True


class TestSaveCredentials:
    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_saves_credential_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"OPENAI_API_KEY": "sk-new"})
        mock_set_key.assert_called_once_with(
            str(config.CREDENTIALS_FILE), "OPENAI_API_KEY", "sk-new"
        )
        mock_load.assert_called_once()

    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_skips_none_values(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"OPENAI_API_KEY": None, "SPOTIPY_CLIENT_ID": "id123"})
        mock_set_key.assert_called_once_with(
            str(config.CREDENTIALS_FILE), "SPOTIPY_CLIENT_ID", "id123"
        )

    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_ignores_settings_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"OPENAI_MODEL": "gpt-4o", "DEBUG_MODE": "true"})
        mock_set_key.assert_not_called()

    @patch("config._KEYRING_AVAILABLE", False)
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_API_KEY=old\n"))
    def test_ignores_unknown_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_credentials({"UNKNOWN_KEY": "value"})
        mock_set_key.assert_not_called()


class TestSaveSettings:
    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_MODEL=\n"))
    def test_saves_settings_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_settings({"OPENAI_MODEL": "gpt-4o"})
        mock_set_key.assert_called_once_with(
            str(config.SETTINGS_FILE), "OPENAI_MODEL", "gpt-4o"
        )
        mock_load.assert_called_once()

    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_MODEL=\n"))
    def test_skips_none_values(self, mock_ensure, mock_set_key, mock_load):
        config.save_settings({"OPENAI_MODEL": None, "DEBUG_MODE": "true"})
        mock_set_key.assert_called_once_with(
            str(config.SETTINGS_FILE), "DEBUG_MODE", "true"
        )

    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_MODEL=\n"))
    def test_ignores_credential_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_settings({"OPENAI_API_KEY": "sk-test"})
        mock_set_key.assert_not_called()

    @patch("config.load_dotenv")
    @patch("config.set_key")
    @patch("config.ensure_env")
    @patch("builtins.open", mock_open(read_data="OPENAI_MODEL=\n"))
    def test_ignores_unknown_keys(self, mock_ensure, mock_set_key, mock_load):
        config.save_settings({"UNKNOWN_KEY": "value"})
        mock_set_key.assert_not_called()


class TestEnsureEnv:
    def test_creates_both_files(self, tmp_path):
        cred_file = tmp_path / ".credentials"
        settings_file = tmp_path / "settings.conf"
        app_dir = tmp_path
        old_env = tmp_path / ".env"

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "SETTINGS_FILE", settings_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        assert cred_file.exists()
        assert settings_file.exists()
        cred_content = cred_file.read_text()
        settings_content = settings_file.read_text()
        for key in config.CREDENTIAL_KEYS:
            assert f"{key}=" in cred_content
        for key in config.SETTINGS_KEYS:
            assert f"{key}=" in settings_content

    def test_appends_missing_keys(self, tmp_path):
        cred_file = tmp_path / ".credentials"
        cred_file.write_text("OPENAI_API_KEY=sk-test\n")
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("OPENAI_MODEL=gpt-4o\n")
        app_dir = tmp_path
        old_env = tmp_path / ".env"

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "SETTINGS_FILE", settings_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        cred_content = cred_file.read_text()
        settings_content = settings_file.read_text()
        # Original keys preserved
        assert "OPENAI_API_KEY=sk-test" in cred_content
        assert "OPENAI_MODEL=gpt-4o" in settings_content
        # Missing keys were appended
        assert "SPOTIPY_CLIENT_ID=" in cred_content
        assert "DEBUG_MODE=" in settings_content

    def test_migrates_settings_from_credentials(self, tmp_path):
        """Settings keys in .credentials are moved to settings.conf."""
        cred_file = tmp_path / ".credentials"
        cred_file.write_text("OPENAI_API_KEY=sk-test\nOPENAI_MODEL=gpt-4o\nDEBUG_MODE=true\n")
        settings_file = tmp_path / "settings.conf"
        app_dir = tmp_path
        old_env = tmp_path / ".env"

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "SETTINGS_FILE", settings_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        cred_content = cred_file.read_text()
        settings_content = settings_file.read_text()
        # Settings keys should have been migrated out of .credentials
        assert "OPENAI_MODEL" not in cred_content
        assert "DEBUG_MODE" not in cred_content
        # Credentials should remain
        assert "OPENAI_API_KEY=sk-test" in cred_content
        # Settings should be in settings.conf
        assert "OPENAI_MODEL" in settings_content
        assert "DEBUG_MODE" in settings_content

    def test_migrates_old_env_file(self, tmp_path):
        old_env = tmp_path / ".env"
        old_env.write_text("OPENAI_API_KEY=sk-old\n")
        cred_file = tmp_path / ".credentials"
        settings_file = tmp_path / "settings.conf"
        app_dir = tmp_path

        with patch.object(config, "_APP_DIR", app_dir), \
             patch.object(config, "CREDENTIALS_FILE", cred_file), \
             patch.object(config, "SETTINGS_FILE", settings_file), \
             patch.object(config, "_OLD_ENV_FILE", old_env):
            config.ensure_env()

        assert cred_file.exists()
        assert not old_env.exists()
        content = cred_file.read_text()
        assert "OPENAI_API_KEY=sk-old" in content


class TestGetAppDir:
    def test_desktop_uses_localappdata(self):
        with patch("sys.platform", "win32"), \
             patch.dict(os.environ, {"LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}):
            result = config._get_app_dir()
            assert result == Path("C:\\Users\\test\\AppData\\Local") / "spotyvibe"

    def test_desktop_falls_back_to_home(self):
        env = os.environ.copy()
        env.pop("LOCALAPPDATA", None)
        with patch("sys.platform", "win32"), \
             patch.dict(os.environ, env, clear=True):
            result = config._get_app_dir()
            assert result == Path(os.path.expanduser("~")) / "spotyvibe"


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


class TestIsOnboardingCompleted:
    """Tests for is_onboarding_completed — reads from settings.conf file."""

    def test_returns_true_when_file_has_true(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=true\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is True

    def test_returns_true_when_file_has_yes(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=yes\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is True

    def test_returns_true_when_file_has_1(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=1\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is True

    def test_returns_false_when_file_has_false(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=false\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is False

    def test_returns_false_when_file_has_empty_value(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is False

    def test_returns_false_when_key_missing_from_file(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("OPENAI_MODEL=gpt-4o\n")
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is False

    def test_returns_false_when_file_does_not_exist(self, tmp_path):
        settings_file = tmp_path / "settings.conf"
        with patch.object(config, "SETTINGS_FILE", settings_file):
            assert config.is_onboarding_completed() is False

    def test_file_takes_priority_over_stale_env(self, tmp_path):
        """Regression: user sets ONBOARDING_COMPLETED=false in settings
        but os.environ still has 'true' from previous load_dotenv call."""
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("ONBOARDING_COMPLETED=false\n")
        with patch.dict(os.environ, {"ONBOARDING_COMPLETED": "true"}):
            with patch.object(config, "SETTINGS_FILE", settings_file):
                assert config.is_onboarding_completed() is False

    def test_removed_key_detected_despite_stale_env(self, tmp_path):
        """Regression: user deletes ONBOARDING_COMPLETED line from settings
        but os.environ still has 'true' from previous load_dotenv call."""
        settings_file = tmp_path / "settings.conf"
        settings_file.write_text("OPENAI_MODEL=gpt-4o\n")
        with patch.dict(os.environ, {"ONBOARDING_COMPLETED": "true"}):
            with patch.object(config, "SETTINGS_FILE", settings_file):
                assert config.is_onboarding_completed() is False

