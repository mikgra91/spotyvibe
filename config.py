"""Centralised credential management.

Stores credentials in a platform-appropriate directory:
  - Windows:  %LOCALAPPDATA%\\spotyvibe\\.credentials
  - Android:  internal app storage (set via SPOTYVIBE_FILES_DIR env var)
  - Fallback: ~/spotyvibe/.credentials
so the user never has to put secrets inside the project directory.
"""

import os
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
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
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
CACHE_FILE = _APP_DIR / ".spotify-cache"
PROFILE_FILE = _APP_DIR / "personalized_music_profile.json"
PROFILE_HISTORY_FILE = _APP_DIR / "personalized_music_profile.history.json"
DEBUG_LOG_FILE = _APP_DIR / "debug.log"

# Keys the user configures via the Settings UI
USER_KEYS = ["OPENAI_API_KEY", "OPENAI_MODEL", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "DEBUG_MODE", "PLAYLIST_SIZE", "NEW_ARTIST_PERCENTAGE", "GPT_LANGUAGE", "ONBOARDING_COMPLETED"]

# Old file name used before the rename
_OLD_ENV_FILE = _APP_DIR / ".env"


def ensure_env():
    """Create the AppData .credentials with all required keys if missing."""
    _APP_DIR.mkdir(parents=True, exist_ok=True)

    # Migrate from the old .env file if it exists (desktop only)
    if not IS_ANDROID and _OLD_ENV_FILE.exists() and not CREDENTIALS_FILE.exists():
        _OLD_ENV_FILE.rename(CREDENTIALS_FILE)

    if not CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            for key in USER_KEYS:
                f.write(f"{key}=\n")
        return

    # File exists — make sure every required key is present
    existing = set()
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                existing.add(stripped.partition("=")[0].strip())

    with open(CREDENTIALS_FILE, "a", encoding="utf-8") as f:
        for key in USER_KEYS:
            if key not in existing:
                f.write(f"{key}=\n")


def load_config():
    """Load credentials from the AppData .credentials into os.environ."""
    ensure_env()
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)


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
    val = os.getenv("ONBOARDING_COMPLETED", "")
    if val.lower() in ("1", "true", "yes"):
        return True
    # Fallback: re-read .credentials file in case os.environ is stale
    if CREDENTIALS_FILE.exists():
        from dotenv import dotenv_values
        vals = dotenv_values(CREDENTIALS_FILE)
        return vals.get("ONBOARDING_COMPLETED", "").lower() in ("1", "true", "yes")
    return False


def set_onboarding_completed(completed: bool = True) -> None:
    """Persist the onboarding completion flag."""
    from dotenv import set_key
    ensure_env()
    set_key(str(CREDENTIALS_FILE), "ONBOARDING_COMPLETED", "true" if completed else "")
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)


def set_gpt_language(language: str):
    """Persist the GPT language setting."""
    from dotenv import set_key
    ensure_env()
    set_key(str(CREDENTIALS_FILE), "GPT_LANGUAGE", language)
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)


def get_settings():
    """Return non-secret settings for the Settings UI."""
    return {
        "model": get_model(),
        "debug_mode": get_debug_mode(),
        "playlist_size": get_playlist_size(),
        "new_artist_percentage": get_new_artist_percentage(),
        "gpt_language": get_gpt_language(),
        "debug_log_path": "" if IS_ANDROID else str(DEBUG_LOG_FILE),
        "debug_controls_available": not IS_ANDROID,
        "is_android": IS_ANDROID,
    }



# Keys that contain secrets and should be masked in the UI
_SECRET_KEYS = {"OPENAI_API_KEY", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"}


def get_credentials():
    """Return current credential values, masked for safe display."""
    ensure_env()
    raw = dotenv_values(str(CREDENTIALS_FILE))

    result = {}
    for key in USER_KEYS:
        value = raw.get(key, "") or ""
        if key in _SECRET_KEYS:
            if value and len(value) > 4:
                masked = "*" * (len(value) - 4) + value[-4:]
            elif value:
                masked = "****"
            else:
                masked = ""
            result[key] = {"masked": masked, "is_set": bool(value)}
        else:
            # Non-secret keys (e.g. model name) — return the full value
            result[key] = {"value": value, "is_set": bool(value)}

    return result


def save_credentials(credentials):
    """Update credential values in the AppData .credentials and reload.

    A value of ``None`` means "not provided" and is skipped.
    An empty string ``""`` explicitly clears the key.
    """
    ensure_env()

    # Guarantee the file ends with a newline so set_key doesn't
    # concatenate the new entry onto the last existing line.
    with open(CREDENTIALS_FILE, "r+", encoding="utf-8") as f:
        content = f.read()
        if content and not content.endswith("\n"):
            f.write("\n")

    for key, value in credentials.items():
        if key in USER_KEYS and value is not None:
            set_key(str(CREDENTIALS_FILE), key, value)
    # Reload so os.environ reflects the new values immediately
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)
