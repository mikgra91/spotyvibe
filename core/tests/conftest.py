"""Pytest configuration — adds the spotyvibe directory to sys.path."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Allow imports like `from config import ...` and `from core.xxx import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def isolated_profiles_env(tmp_path):
    """Fixture that isolates profile storage to a temp directory.

    Patches ONLY the directory/file constants (PROFILES_DIR, SETTINGS_FILE,
    _APP_DIR) so the real path resolution logic in config.py runs
    (get_active_profile_id, set_active_profile_id, get_active_profile_path,
    validate_profile_id, etc.) against an isolated filesystem.

    This catches integration bugs that unit tests with mocked paths miss.
    """
    from dotenv import load_dotenv

    app_dir = tmp_path / "appdir"
    app_dir.mkdir()
    profiles_dir = app_dir / "profiles"
    profiles_dir.mkdir()
    settings_file = app_dir / "settings.conf"
    settings_file.write_text("ACTIVE_PROFILE_ID=\n")

    # Load the temp settings into os.environ
    load_dotenv(str(settings_file), override=True)

    # Save original env value for cleanup
    original_pid = os.environ.get("ACTIVE_PROFILE_ID")

    with patch("config.PROFILES_DIR", profiles_dir), \
         patch("config.SETTINGS_FILE", settings_file), \
         patch("config._APP_DIR", app_dir), \
         patch("core.src.profile.PROFILES_DIR", profiles_dir):
        yield {
            "profiles_dir": profiles_dir,
            "settings_file": settings_file,
            "app_dir": app_dir,
        }

    # Cleanup os.environ
    if original_pid is not None:
        os.environ["ACTIVE_PROFILE_ID"] = original_pid
    else:
        os.environ.pop("ACTIVE_PROFILE_ID", None)
