"""Centralised credential and settings management.

Stores data in a platform-appropriate directory:
  - Windows:  %LOCALAPPDATA%\\spotyvibe\\
  - Android:  internal app storage (set via SPOTYVIBE_FILES_DIR env var)
  - Fallback: ~/spotyvibe/

Credentials (API keys/secrets) live in ``.credentials``.
App preferences and state live in ``settings.conf``.
"""

import os
import re as _re
import sys
from pathlib import Path
from dotenv import load_dotenv, set_key, dotenv_values

def _get_base_dir() -> Path:
    """Return the runtime base directory for bundled assets.

    - Source / `python app.py`: the project directory containing config.py
    - PyInstaller (frozen): the temporary extraction directory (sys._MEIPASS)

    This is intentionally resolved at import-time so modules can safely
    use BASE_DIR for locating templates/, static/, prompts/, data/, etc.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


# Absolute path to the spotyvibe runtime directory — used as the base for
# all relative path resolution so that os.chdir() is never needed.
BASE_DIR = _get_base_dir()


# How many tracks GPT generates per single request
BATCH_SIZE = 10

# Default total playlist size — can be overridden via Settings UI
DEFAULT_PLAYLIST_SIZE = 10

# Maximum number of history entries sent to GPT to bound token usage
GPT_HISTORY_LIMIT = 200

# When an artist already has this many tracks in history, GPT is told to
# skip them entirely and look for new artists instead.
EXHAUSTED_ARTIST_THRESHOLD = 4

# Maximum number of songs in the persistent feedback list
MAX_SONG_LIST_SIZE = 100

# How many consecutive batches may return an entirely-filtered result before
# the loop is broken and the playlist is created with whatever was found.
MAX_CONSECUTIVE_EMPTY_BATCHES = 3

# Hard cost guardrails — max GPT calls per single /api/run invocation
MAX_GPT_CALLS_PER_RUN = 20

# Default minimum percentage of suggestions that must come from artists not
# yet present in suggested_artists history (1–100).
DEFAULT_NEW_ARTIST_PERCENTAGE = 30

# Default OpenAI model used when none is configured
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"

# Curated list of known-good OpenAI model IDs for chat completions.
# Order determines display order in the Settings dropdown.
# Maintained here so Android/Chaquopy builds never need to query the API
# for the model list (avoids the openai SDK and its native deps entirely).
OPENAI_SUPPORTED_MODELS_JSON = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
]

# Optional additional model IDs beyond the curated list.
# Extend this list to allow custom or preview model IDs.
OPENAI_EXTRA_ALLOWED_MODELS: list[str] = []

# Default language for GPT communication (prompts and responses)
DEFAULT_GPT_LANGUAGE = "English"

# Maximum allowed size for profile imports (JSON payload size).
# Enforced server-side by POST /api/profile/import.
PROFILE_IMPORT_MAX_BYTES = 10 * 1024 * 1024  # 10MB

# General request body size limit (all endpoints except profile import)
GENERAL_REQUEST_MAX_BYTES = 1 * 1024 * 1024  # 1MB

# Field-level limits for user-supplied text (prevent runaway prompts)
MAX_CORE_DESCRIPTION_LEN = 5000
MAX_PROFILE_SECTION_LEN = 5000
MAX_FEEDBACK_REASON_LEN = 500
MAX_FEEDBACK_ARTIST_LEN = 200
MAX_FEEDBACK_TRACK_LEN = 200


# True when running inside Chaquopy on Android
IS_ANDROID = hasattr(sys, 'getandroidapilevel')


def _get_app_dir():
    """Return the platform-appropriate storage directory."""
    if IS_ANDROID:
        # Running inside Chaquopy on Android — use the files dir
        # passed from Kotlin via environment variable
        android_files = os.environ.get("SPOTYVIBE_FILES_DIR")
        if android_files:
            return Path(android_files) / "spotyvibe"
        # Fallback: use the Python home directory (Chaquopy sets this)
        return Path(os.path.expanduser("~")) / "spotyvibe"
    # Desktop (Windows / macOS / Linux)
    return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe"


_APP_DIR = _get_app_dir()
CREDENTIALS_FILE = _APP_DIR / ".credentials"
SETTINGS_FILE = _APP_DIR / "settings.conf"
CACHE_FILE = _APP_DIR / ".spotify-cache"
PROFILES_DIR = _APP_DIR / "profiles"

# Legacy single-profile paths (kept for reference / migration awareness)
PROFILE_FILE = _APP_DIR / "personalized_music_profile.json"
PROFILE_HISTORY_FILE = _APP_DIR / "personalized_music_profile.history.json"
DEBUG_LOG_FILE = _APP_DIR / "debug.log"       # Backend application log
PROMPT_LOG_FILE = _APP_DIR / "prompt.log"      # GPT request/response log (was debug.log)

# Secret keys — stored in .credentials
CREDENTIAL_KEYS = ["OPENAI_API_KEY", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]

# Non-secret keys — stored in settings.conf
SETTINGS_KEYS = ["OPENAI_MODEL", "DEBUG_MODE", "PLAYLIST_SIZE", "NEW_ARTIST_PERCENTAGE", "GPT_LANGUAGE", "ONBOARDING_COMPLETED", "ACTIVE_PROFILE_ID", "UI_LANGUAGE"]

# Maximum length for profile display names
MAX_PROFILE_NAME_LEN = 40

# Combined list for backward compatibility
USER_KEYS = CREDENTIAL_KEYS + SETTINGS_KEYS

# Old file name used before the rename
_OLD_ENV_FILE = _APP_DIR / ".env"


def _ensure_file(filepath, keys):
    """Ensure a dotenv-style file exists with all required keys."""
    if not filepath.exists():
        with open(filepath, "w", encoding="utf-8") as f:
            for key in keys:
                f.write(f"{key}=\n")
        return

    # File exists — make sure every required key is present
    existing = set()
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                existing.add(stripped.partition("=")[0].strip())

    with open(filepath, "a", encoding="utf-8") as f:
        for key in keys:
            if key not in existing:
                f.write(f"{key}=\n")


def _migrate_settings_from_credentials():
    """Move non-secret keys from .credentials to settings.conf (one-time).

    Reads .credentials for any SETTINGS_KEYS entries, writes their values
    into settings.conf, then removes them from .credentials.
    """
    if not CREDENTIALS_FILE.exists():
        return

    cred_lines = []
    migrated = {}
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.partition("=")[0].strip()
                if key in SETTINGS_KEYS:
                    value = stripped.partition("=")[2]
                    if value:  # only migrate non-empty values
                        migrated[key] = value
                    continue  # drop this line from .credentials
            cred_lines.append(line)

    if not migrated:
        return

    # Write migrated values into settings.conf
    for key, value in migrated.items():
        set_key(str(SETTINGS_FILE), key, value)

    # Rewrite .credentials without the migrated keys
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        f.writelines(cred_lines)


def ensure_env():
    """Create the AppData .credentials and settings.conf with all required keys if missing."""
    _APP_DIR.mkdir(parents=True, exist_ok=True)

    # Migrate from the old .env file if it exists (desktop only)
    if not IS_ANDROID and _OLD_ENV_FILE.exists() and not CREDENTIALS_FILE.exists():
        _OLD_ENV_FILE.rename(CREDENTIALS_FILE)

    _ensure_file(CREDENTIALS_FILE, CREDENTIAL_KEYS)
    _ensure_file(SETTINGS_FILE, SETTINGS_KEYS)

    # One-time migration: move settings keys from .credentials to settings.conf
    _migrate_settings_from_credentials()


def load_config():
    """Load credentials and settings into os.environ."""
    ensure_env()
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)
    load_dotenv(dotenv_path=str(SETTINGS_FILE), override=True)


def get_model():
    """Return the configured OpenAI model, falling back to the default."""
    return os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def get_debug_mode():
    """Return True if debug mode is enabled.

    Debug logging is desktop-only; on Android this always returns False.
    """
    if IS_ANDROID:
        return False
    return os.getenv("DEBUG_MODE", "").lower() in ("1", "true", "on")



def get_playlist_size():
    """Return the configured total playlist size, falling back to the default."""
    raw = os.getenv("PLAYLIST_SIZE", "")
    try:
        val = int(raw)
        return max(val, BATCH_SIZE)  # at least one batch
    except (ValueError, TypeError):
        return DEFAULT_PLAYLIST_SIZE


def get_new_artist_percentage():
    """Return the configured new-artist percentage (1–100), falling back to the default."""
    raw = os.getenv("NEW_ARTIST_PERCENTAGE", "")
    try:
        val = int(raw)
        return max(1, min(100, val))  # clamp to valid range
    except (ValueError, TypeError):
        return DEFAULT_NEW_ARTIST_PERCENTAGE


def get_gpt_language():
    """Return the configured GPT communication language, falling back to English."""
    return os.getenv("GPT_LANGUAGE") or DEFAULT_GPT_LANGUAGE


def is_onboarding_completed() -> bool:
    """Return True if the user has completed (or skipped) onboarding."""
    if SETTINGS_FILE.exists():
        vals = dotenv_values(SETTINGS_FILE)
        return vals.get("ONBOARDING_COMPLETED", "").lower() in ("1", "true", "yes")
    return False


def set_onboarding_completed(completed: bool = True) -> None:
    """Persist the onboarding completion flag."""
    ensure_env()
    set_key(str(SETTINGS_FILE), "ONBOARDING_COMPLETED", "true" if completed else "")
    load_dotenv(dotenv_path=str(SETTINGS_FILE), override=True)


def set_gpt_language(language: str):
    """Persist the GPT language setting."""
    ensure_env()
    set_key(str(SETTINGS_FILE), "GPT_LANGUAGE", language)
    load_dotenv(dotenv_path=str(SETTINGS_FILE), override=True)


def get_ui_language():
    """Return the persisted UI language code ('en', 'de', etc.), or empty string."""
    return os.getenv("UI_LANGUAGE", "")


def set_ui_language(lang: str):
    """Persist the UI language setting."""
    ensure_env()
    set_key(str(SETTINGS_FILE), "UI_LANGUAGE", lang)
    os.environ["UI_LANGUAGE"] = lang


def get_settings():
    """Return non-secret settings for the Settings UI."""
    return {
        "model": get_model(),
        "debug_mode": get_debug_mode(),
        "playlist_size": get_playlist_size(),
        "new_artist_percentage": get_new_artist_percentage(),
        "gpt_language": get_gpt_language(),
        "ui_language": get_ui_language(),
        "debug_log_path": "" if IS_ANDROID else str(DEBUG_LOG_FILE),
        "prompt_log_path": "" if IS_ANDROID else str(PROMPT_LOG_FILE),
        "debug_controls_available": not IS_ANDROID,
        "is_android": IS_ANDROID,
    }



def get_credentials():
    """Return current credential values, masked for safe display."""
    ensure_env()
    raw = dotenv_values(str(CREDENTIALS_FILE))

    result = {}
    for key in CREDENTIAL_KEYS:
        value = raw.get(key, "") or ""
        if value and len(value) > 4:
            masked = "*" * (len(value) - 4) + value[-4:]
        elif value:
            masked = "****"
        else:
            masked = ""
        result[key] = {"masked": masked, "is_set": bool(value)}

    return result


def _ensure_trailing_newline(filepath):
    """Guarantee a file ends with a newline so set_key appends correctly."""
    with open(filepath, "r+", encoding="utf-8") as f:
        content = f.read()
        if content and not content.endswith("\n"):
            f.write("\n")


def save_credentials(credentials):
    """Update secret credential values in .credentials and reload.

    A value of ``None`` means "not provided" and is skipped.
    An empty string ``""`` explicitly clears the key.
    """
    ensure_env()
    _ensure_trailing_newline(CREDENTIALS_FILE)

    for key, value in credentials.items():
        if key in CREDENTIAL_KEYS and value is not None:
            set_key(str(CREDENTIALS_FILE), key, value)
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)


def save_settings(settings):
    """Update non-secret settings in settings.conf and reload.

    A value of ``None`` means "not provided" and is skipped.
    An empty string ``""`` explicitly clears the key.
    """
    ensure_env()
    _ensure_trailing_newline(SETTINGS_FILE)

    for key, value in settings.items():
        if key in SETTINGS_KEYS and value is not None:
            set_key(str(SETTINGS_FILE), key, value)
    load_dotenv(dotenv_path=str(SETTINGS_FILE), override=True)


_UUID_PATTERN = _re.compile(
    r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
)


def validate_profile_id(profile_id):
    """Validate that a profile ID is a well-formed UUID.

    Raises ValueError if the ID is empty or doesn't match the UUID pattern.
    """
    if not profile_id or not _UUID_PATTERN.match(profile_id):
        raise ValueError(f"Invalid profile ID: {profile_id!r}")


def get_active_profile_id():
    """Return the active profile UUID, or empty string if none set."""
    return os.getenv("ACTIVE_PROFILE_ID", "")


def set_active_profile_id(profile_id: str):
    """Store the active profile UUID in settings.conf."""
    ensure_env()
    set_key(str(SETTINGS_FILE), "ACTIVE_PROFILE_ID", profile_id)
    os.environ["ACTIVE_PROFILE_ID"] = profile_id


def get_active_profile_path():
    """Return the Path to the active profile JSON, or None if none set."""
    pid = get_active_profile_id()
    if not pid:
        return None
    validate_profile_id(pid)
    return PROFILES_DIR / f"{pid}.json"


def get_active_history_path():
    """Return the Path to the active profile's history backup, or None."""
    pid = get_active_profile_id()
    if not pid:
        return None
    validate_profile_id(pid)
    return PROFILES_DIR / f"{pid}.history.json"
