"""Centralised credential and settings management.

Stores data in a platform-appropriate directory:
  - Windows:  %LOCALAPPDATA%\\spotyvibe\\
  - Fallback: ~/spotyvibe/

Credentials (API keys/secrets) are stored in the OS keychain when available
(Windows Credential Manager / macOS Keychain) with ``.credentials`` as a
fallback for platforms without a usable keyring.
App preferences and state live in ``settings.conf``.
"""

import os
import re as _re
import sys
from pathlib import Path
from dotenv import load_dotenv, set_key, dotenv_values

# OS keychain integration — graceful fallback when keyring is unavailable.
_KEYRING_SERVICE = "spotyvibe"
try:
    import keyring as _keyring
    # Verify the backend is actually usable (not the null backend)
    _backend_name = type(_keyring.get_keyring()).__name__
    _KEYRING_AVAILABLE = _backend_name != "NullKeyring"
except Exception:
    _keyring = None
    _KEYRING_AVAILABLE = False

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


# ── RAG (retrieval-augmented candidate pool) ─────────────────────
# See documentation/guides/rag-implementation.md for the design.
# Master off-switch is the user-facing setting RAG_ENABLED in settings.conf;
# the constants below are corpus paths and tuning knobs.
#
# Path layout (since Apr-2026):
#   - The downloadable corpus + meta sidecar live in the user's app dir
#     (e.g. %LOCALAPPDATA%/spotyvibe/rag_corpus/) so they survive across
#     PyInstaller-EXE launches and live alongside other user-specific
#     state. _APP_DIR is defined further below — RAG_CORPUS_DIR/PATH/META
#     are therefore initialised in `_init_rag_paths()` after _APP_DIR is
#     known.
#   - The tag-alias map is bundled with the app and stays under BASE_DIR.
RAG_TAG_ALIASES_PATH = BASE_DIR / "data" / "rag_corpus" / "tag_aliases.json"
RAG_MANIFEST_URL = os.environ.get(
    "RAG_MANIFEST_URL",
    "https://storage.googleapis.com/spotivibe-rag-corpus/manifest.json",
)
RAG_POOL_SIZE = 20
RAG_POPULARITY_PENALTY = 0.4
DEFAULT_RAG_ENABLED = True
# Stratified retrieval: split RAG_POOL_SIZE across profile facets (must_have,
# soft_preferences, primary_reference, genres/moods/eras) so an eclectic
# profile gets guaranteed per-facet coverage instead of one strong facet
# starving the others. See documentation/guides/rag-implementation.md §4.
RAG_STRATIFIED = True
# Per-facet quotas (must sum to <= 1.0 — remainder is filled from the
# undifferentiated flat ranking). Tuned for the 100-slot default.
RAG_FACET_WEIGHTS = {
    "must_have": 0.50,
    "soft_preferences": 0.25,
    "primary_reference": 0.15,
    "tags": 0.10,  # genres + moods + eras combined
}

# Populated by _init_rag_paths() once _APP_DIR exists.
RAG_CORPUS_DIR: Path  # type: ignore[assignment]
RAG_CORPUS_PATH: Path  # type: ignore[assignment]
RAG_META_PATH: Path  # type: ignore[assignment]


def get_rag_enabled() -> bool:
    """Return True if the candidate-pool RAG pass is active.

    Gated on both the user setting and the presence of the corpus file —
    if the corpus isn't downloaded we silently fall back to the legacy
    prompt rather than crashing on startup.
    """
    raw = os.getenv("RAG_ENABLED", "").lower()
    if raw in ("1", "true", "on", "yes"):
        return RAG_CORPUS_PATH.exists()
    if raw in ("0", "false", "off", "no"):
        return False
    return DEFAULT_RAG_ENABLED and RAG_CORPUS_PATH.exists()


def set_rag_enabled(enabled: bool) -> None:
    """Persist the user-facing RAG toggle."""
    _persist_setting("RAG_ENABLED", "true" if enabled else "false")


def _get_app_dir() -> Path:
    """Return the platform-appropriate storage directory.

    Resolves to:
    - Windows: %LOCALAPPDATA%/spotyvibe/
    - macOS: ~/Library/Application Support/spotyvibe/
    - Linux: ~/.local/share/spotyvibe/ (or $XDG_DATA_HOME/spotyvibe/)
    """
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe"
    elif sys.platform == "darwin":
        return Path(os.path.expanduser("~/Library/Application Support")) / "spotyvibe"
    else:  # Linux / other
        xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return Path(xdg) / "spotyvibe"


_APP_DIR = _get_app_dir()
CREDENTIALS_FILE = _APP_DIR / ".credentials"
SETTINGS_FILE = _APP_DIR / "settings.conf"
CACHE_FILE = _APP_DIR / ".spotify-cache"
PROFILES_DIR = _APP_DIR / "profiles"


def _init_rag_paths() -> None:
    """Resolve RAG corpus paths once _APP_DIR is known.

    The downloadable corpus + meta sidecar live in the user's app dir so
    they survive across PyInstaller-EXE launches. A one-time migration
    moves any legacy file from ``BASE_DIR/data/rag_corpus/`` (older dev
    installs) into the new location.
    """
    global RAG_CORPUS_DIR, RAG_CORPUS_PATH, RAG_META_PATH
    RAG_CORPUS_DIR = _APP_DIR / "rag_corpus"
    RAG_CORPUS_PATH = RAG_CORPUS_DIR / "artists.jsonl.gz"
    RAG_META_PATH = RAG_CORPUS_DIR / "artists.meta.json"

    # One-time migration from the legacy in-repo location.
    legacy_dir = BASE_DIR / "data" / "rag_corpus"
    legacy_corpus = legacy_dir / "artists.jsonl.gz"
    legacy_meta = legacy_dir / "artists.meta.json"
    if legacy_corpus.exists() and not RAG_CORPUS_PATH.exists():
        try:
            RAG_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
            legacy_corpus.replace(RAG_CORPUS_PATH)
            if legacy_meta.exists():
                legacy_meta.replace(RAG_META_PATH)
        except OSError:
            # Read-only legacy dir (e.g. frozen EXE temp dir) — leave the
            # legacy file alone; the user just needs to download afresh.
            pass


_init_rag_paths()

# Legacy single-profile paths (kept for reference / migration awareness)
PROFILE_FILE = _APP_DIR / "personalized_music_profile.json"
PROFILE_HISTORY_FILE = _APP_DIR / "personalized_music_profile.history.json"
DEBUG_LOG_FILE = _APP_DIR / "debug.log"       # Backend application log
PROMPT_LOG_FILE = _APP_DIR / "prompt.log"      # GPT request/response log (was debug.log)
EVAL_LOG_FILE = _APP_DIR / "eval.jsonl"        # One JSONL row per suggested track for offline analysis

# Secret keys — stored in .credentials
CREDENTIAL_KEYS = ["OPENAI_API_KEY", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]

# Non-secret keys — stored in settings.conf
SETTINGS_KEYS = ["OPENAI_MODEL", "DEBUG_MODE", "PLAYLIST_SIZE", "NEW_ARTIST_PERCENTAGE", "GPT_LANGUAGE", "ONBOARDING_COMPLETED", "ACTIVE_PROFILE_ID", "UI_LANGUAGE", "LLM_BASE_URL", "PROVIDER_PRESET", "RAG_ENABLED"]

# Maximum length for profile display names
MAX_PROFILE_NAME_LEN = 40

# Combined list for backward compatibility
USER_KEYS = CREDENTIAL_KEYS + SETTINGS_KEYS

# Default LLM provider configuration (Wave 4)
DEFAULT_LLM_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_PROVIDER_PRESET = 'openai'
LOCAL_PRESETS = {'ollama', 'lmstudio'}

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

    # Migrate from the old .env file if it exists
    if _OLD_ENV_FILE.exists() and not CREDENTIALS_FILE.exists():
        _OLD_ENV_FILE.rename(CREDENTIALS_FILE)

    _ensure_file(CREDENTIALS_FILE, CREDENTIAL_KEYS)
    _ensure_file(SETTINGS_FILE, SETTINGS_KEYS)

    # One-time migration: move settings keys from .credentials to settings.conf
    _migrate_settings_from_credentials()


def _migrate_credentials_to_keyring():
    """One-time migration: move plaintext secrets from .credentials into keyring.

    For each credential key that has a non-empty value in .credentials but
    no value in keyring yet, stores the value in keyring and clears the
    plaintext entry in .credentials.  This runs silently on every startup
    but only does work when there is something to migrate.
    """
    raw = dotenv_values(str(CREDENTIALS_FILE))
    migrated_any = False

    for key in CREDENTIAL_KEYS:
        file_val = (raw.get(key) or "").strip()
        if not file_val:
            continue  # nothing to migrate

        # Check if keyring already has a value for this key
        try:
            kr_val = _keyring.get_password(_KEYRING_SERVICE, key)
        except Exception:
            continue  # keyring read failed — skip this key

        if kr_val:
            # Keyring already populated — just clear the plaintext copy
            set_key(str(CREDENTIALS_FILE), key, "")
            migrated_any = True
            continue

        # Store in keyring, then clear from file
        try:
            _keyring.set_password(_KEYRING_SERVICE, key, file_val)
            set_key(str(CREDENTIALS_FILE), key, "")
            migrated_any = True
        except Exception:
            pass  # keyring write failed — keep plaintext as fallback

    if migrated_any:
        # Reload the (now-emptied) .credentials so os.environ reflects it;
        # keyring overlay will restore the values moments later.
        load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)


def load_config():
    """Load credentials and settings into os.environ.

    Reads from dotenv files first, then overlays keyring values (if available)
    so the OS keychain takes precedence over the plaintext .credentials file.
    On the first run with a usable keyring, credentials are automatically
    migrated from .credentials into the OS keychain and the plaintext values
    are cleared.
    """
    ensure_env()
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)
    load_dotenv(dotenv_path=str(SETTINGS_FILE), override=True)

    # One-time migration: copy plaintext credentials into keyring and clear
    # them from .credentials so secrets no longer sit in a flat file.
    if _KEYRING_AVAILABLE:
        _migrate_credentials_to_keyring()

    # Overlay keyring values — these take precedence over dotenv
    if _KEYRING_AVAILABLE:
        for key in CREDENTIAL_KEYS:
            try:
                val = _keyring.get_password(_KEYRING_SERVICE, key)
                if val:
                    os.environ[key] = val
            except Exception:
                pass


def get_model():
    """Return the configured OpenAI model, falling back to the default."""
    return os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def get_debug_mode():
    """Return True if debug mode is enabled."""
    return os.getenv("DEBUG_MODE", "").lower() in ("1", "true", "on")



def get_playlist_size():
    """Return the configured total playlist size, falling back to the default."""
    raw = os.getenv("PLAYLIST_SIZE", "")
    try:
        val = int(raw)
        return max(val, 5)  # hard minimum of 5 tracks
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


def _persist_setting(key: str, value: str):
    """Write a key=value pair to settings.conf and sync to os.environ."""
    ensure_env()
    set_key(str(SETTINGS_FILE), key, value)
    os.environ[key] = value


def set_onboarding_completed(completed: bool = True) -> None:
    """Persist the onboarding completion flag."""
    _persist_setting("ONBOARDING_COMPLETED", "true" if completed else "")


def set_gpt_language(language: str):
    """Persist the GPT language setting."""
    _persist_setting("GPT_LANGUAGE", language)


def get_ui_language():
    """Return the persisted UI language code ('en', 'de', etc.), or empty string."""
    return os.getenv("UI_LANGUAGE", "")


def set_ui_language(lang: str):
    """Persist the UI language setting."""
    _persist_setting("UI_LANGUAGE", lang)


def get_settings():
    """Return non-secret settings for the Settings UI."""
    return {
        "model": get_model(),
        "debug_mode": get_debug_mode(),
        "playlist_size": get_playlist_size(),
        "new_artist_percentage": get_new_artist_percentage(),
        "gpt_language": get_gpt_language(),
        "ui_language": get_ui_language(),
        "debug_log_path": str(DEBUG_LOG_FILE),
        "prompt_log_path": str(PROMPT_LOG_FILE),
        "debug_controls_available": True,
        "provider_preset": get_llm_provider_preset(),
        "llm_base_url": get_llm_base_url(),
        "llm_api_key_required": llm_api_key_required(),
        "rag_enabled": get_rag_enabled(),
        "rag_corpus_available": RAG_CORPUS_PATH.exists(),
    }



def get_credentials():
    """Return current credential values, masked for safe display.

    Reads from OS keychain first (if available), falling back to .credentials.
    """
    ensure_env()
    raw = dotenv_values(str(CREDENTIALS_FILE))

    result = {}
    for key in CREDENTIAL_KEYS:
        # Try keyring first, then dotenv
        value = ""
        if _KEYRING_AVAILABLE:
            try:
                kr_val = _keyring.get_password(_KEYRING_SERVICE, key)
                if kr_val:
                    value = kr_val
            except Exception:
                pass
        if not value:
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
    """Update secret credential values and reload into os.environ.

    When a usable OS keychain is available, secrets are stored there and the
    .credentials file only holds empty placeholder keys (no plaintext).
    When keyring is unavailable, secrets fall back to the
    .credentials dotenv file.

    A value of ``None`` means "not provided" and is skipped.
    An empty string ``""`` explicitly clears the key.
    """
    ensure_env()
    _ensure_trailing_newline(CREDENTIALS_FILE)

    for key, value in credentials.items():
        if key in CREDENTIAL_KEYS and value is not None:
            stored_in_keyring = False
            if _KEYRING_AVAILABLE:
                try:
                    if value:
                        _keyring.set_password(_KEYRING_SERVICE, key, value)
                    else:
                        _keyring.delete_password(_KEYRING_SERVICE, key)
                    stored_in_keyring = True
                except Exception:
                    pass  # fall through to dotenv

            if stored_in_keyring:
                # Keep the key present in .credentials but without plaintext
                set_key(str(CREDENTIALS_FILE), key, "")
            else:
                # Keyring unavailable — write to dotenv as fallback
                set_key(str(CREDENTIALS_FILE), key, value)

            # Update os.environ immediately
            os.environ[key] = value
    load_dotenv(dotenv_path=str(CREDENTIALS_FILE), override=True)
    # Re-overlay keyring so os.environ has the real values
    if _KEYRING_AVAILABLE:
        for key in CREDENTIAL_KEYS:
            try:
                val = _keyring.get_password(_KEYRING_SERVICE, key)
                if val:
                    os.environ[key] = val
            except Exception:
                pass


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
    ensure_env()
    return os.getenv("ACTIVE_PROFILE_ID", "")


def set_active_profile_id(profile_id: str):
    """Store the active profile UUID in settings.conf."""
    _persist_setting("ACTIVE_PROFILE_ID", profile_id)


def get_active_profile_path():
    """Return the Path to the active profile JSON, or None if none set."""
    pid = get_active_profile_id()
    if not pid:
        return None
    validate_profile_id(pid)
    return PROFILES_DIR / pid / "profile.json"


def get_active_history_path():
    """Return the Path to the active profile's history backup, or None."""
    pid = get_active_profile_id()
    if not pid:
        return None
    validate_profile_id(pid)
    return PROFILES_DIR / pid / "profile.history.json"


# ── Wave 4: LLM provider helpers ──────────────────────────────────

def get_llm_base_url() -> str:
    """Return the configured LLM base URL."""
    return os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip() or DEFAULT_LLM_BASE_URL


def set_llm_base_url(url: str):
    """Persist the LLM base URL in settings.conf."""
    _persist_setting("LLM_BASE_URL", url.strip())


def get_llm_provider_preset() -> str:
    """Return the active provider preset id."""
    return os.getenv("PROVIDER_PRESET", DEFAULT_PROVIDER_PRESET).strip() or DEFAULT_PROVIDER_PRESET


def set_llm_provider_preset(preset: str):
    """Persist the provider preset in settings.conf."""
    _persist_setting("PROVIDER_PRESET", preset.strip())


def llm_api_key_required() -> bool:
    """Return True if the current provider requires an API key."""
    return get_llm_provider_preset() not in LOCAL_PRESETS


