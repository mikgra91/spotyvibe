# Technical Manual

This document covers the architecture, component interactions, and developer-level details of SpotyVibe.

---

## Architecture Overview

SpotyVibe is a Python web application built with **Flask** that connects two external APIs:

- **OpenAI API** — generates personalised music suggestions based on a structured taste profile.
- **Spotify Web API** — searches for tracks, manages a private playlist, and handles user authentication via OAuth 2.0.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Browser (frontend/templates/)                    │
│                                                                    │
│  OpenAI Section ─── Spotify Section ─── Like/Dislike/Remove         │
│  (Profile/Analysis)  (Metadata/Playlist/History)                   │
└──────────┬────────────────┬────────────────────┬────────────────────┘
           │ POST           │ POST (SSE stream)  │ POST
           ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Flask App (app.py)                          │
│                                                                    │
│  /api/train-profile   /api/run              /api/feedback          │
│  /api/save-profile    /api/spotify/status   /api/remove            │
│  /api/profile/status  /api/analyze          /api/playlists         │
│  /api/spotify/auth    /api/spotify/disconnect  /api/cancel          │
│  /callback            /api/settings/*        /api/help             │
│  /api/settings        /api/settings/debug-log                      │
│  /api/runs            /api/run/<run_id>/status                      │
│  /api/onboarding/status  /api/onboarding/complete                  │
│  /api/settings/language                                            │
└──────┬───────────────────┬──────────────┬──────────┬────────────────┘
       │                   │              │          │
       ▼                   ▼              ▼          ▼
┌──────────────┐   ┌──────────────┐   ┌──────────┐ ┌──────────────────┐
│ core/profile │   │    core/     │   │  core/   │ │  core/playlist   │
│              │   │ suggestions  │   │ analysis │ │                  │
│ - load/save  │   │              │   │          │ │ - search_tracks  │
│ - train via  │   │ - build_msgs │   │ - GPT    │ │   (parallel)     │
│   OpenAI     │   │ - call_gpt   │   │   struct │ │ - add_to_playlist│
│ - save_profile│  │ - dedup      │   │   output │ │ - remove_from_   │
│   _sections  │   │              │   │          │ │   playlist       │
│              │   │              │   └────┬─────┘ │ - OAuth flow     │
└──────┬───────┘   └──────┬───────┘        │       └──────┬───────────┘
       │                  │                │              │
       ▼                  ▼                ▼              ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐ ┌──────────────┐
│  OpenAI API  │   │  OpenAI API  │   │  OpenAI API  │ │ Spotify API  │
│ (configurable│   │ (configurable│   │  (analysis)  │ │  (Web API)   │
│    model)    │   │    model)    │   │              │ │              │
└──────────────┘   └──────────────┘   └──────────────┘ └──────────────┘

┌──────────────┐
│ core/history │
│              │
│ - save_run   │
│ - load_runs  │
└──────────────┘
```

---

## Project Structure

```
spotyvibe/
├── app.py                  # Flask web server — all HTTP endpoints
├── config.py               # Centralised configuration, credentials & settings management
├── requirements.txt        # Python dependencies (pinned version ranges)
├── README.md               # Project overview
├── documentation/
│   ├── help.md       # End-user documentation
│   ├── TechnicalManual.md  # This file
│   ├── learning-android.md # Android architecture guide
│   └── learning-core.md    # Core module guide
│
├── core/                   # Business logic modules
│   ├── __init__.py         # Package marker (empty)
│   ├── utils.py            # Shared utilities (OpenAI client, code-fence stripping)
│   ├── profile.py          # Taste profile I/O and GPT-based training
│   ├── suggestions.py      # GPT suggestion engine and deduplication logic
│   ├── playlist.py         # Spotify playlist management and OAuth
│   ├── feedback.py         # Like/dislike recording
│   ├── analysis.py         # Band/song AI analysis (structured GPT output)
│   └── history.py          # Run history persistence
│
├── prompts/                # AI prompt templates (editable without code changes)
│   ├── system_prompt.txt          # Default system message: rules, matching, output format
│   ├── system_prompt_gpt-4-1.txt  # GPT-4.1-specific system prompt (step-by-step reasoning)
│   ├── system_prompt_gpt-5-4.txt  # GPT-5.4-specific system prompt (candidate-pool reasoning)
│   ├── prompt_template.txt        # User message: embeds the profile JSON
│   ├── profile_training_prompt.txt # System message for taste profile training
│   └── analysis_prompt.txt        # Band/song analysis prompt template
│
├── data/                   # Template data
│   └── music_profile.json  # Empty profile template (seeded on first run)
│
├── profiles/               # Per-user profile storage (created at runtime)
│   ├── <uuid>.json         # Individual profile data (UUID-named)
│   └── <uuid>.history.json # One-step profile backup (per profile)
│
├── static/                 # Static assets served by Flask
│   ├── css/
│   │   └── styles.css      # Main stylesheet — dark glass design system + theme definitions
│   └── i18n/
│       ├── en.json         # UI translation file (English)
│       └── de.json         # UI translation file (German)
│
├── frontend/
│   ├── templates/          # Flask templates (base.html + partials)
│   │   ├── base.html       # Root layout with shared head/scripts
│   │   ├── onboarding.html # Multi-page swipeable onboarding
│   │   ├── tracklist.html  # Track list partial
│   │   ├── modals/         # Modal partials (credentials, settings, help, quickstart)
│   │   └── ...             # Other UI partials
│   └── static/js/
│       ├── main.js         # Entry point — wires up all modules
│       └── modules/        # Feature modules (auth, pipeline, theme-switcher, …)
├── build-tools/            # Build helper scripts (desktop + Android)
│   ├── build_apk.sh        # Builds the Android APK (copies sources + runs Gradle)
│   └── build_exe.sh        # Builds the Windows executable via PyInstaller
│
│├── android/                # Android APK build scaffolding (Chaquopy + Gradle)
│   ├── build.gradle        # Root Gradle config with pinned AGP 8.2.2, Kotlin 1.9.22, Chaquopy 15.0.1
│   ├── settings.gradle     # Gradle project settings

│   ├── gradle.properties   # JVM and Android build properties
│   ├── gradle/wrapper/     # Gradle wrapper config
│   └── app/                # Android application module
│       ├── build.gradle    # App-level Gradle: Chaquopy Python 3.10, pinned pip deps, arm64-v8a/x86_64
│       └── src/main/
│           ├── AndroidManifest.xml   # INTERNET + ACCESS_NETWORK_STATE permissions
│           ├── kotlin/.../MainActivity.kt  # Flask thread, splash, WebView, OAuth popups
│           ├── python/              # Python sources (copied at build time)
│           └── res/                 # Layouts, icons, strings
├── .github/workflows/
│   └── ci.yml              # GitHub Actions CI
│
├── core/tests/              # Unit tests for core modules
│   ├── conftest.py          # Pytest configuration (sys.path setup)
│   ├── test_utils.py        # Tests for shared utilities
│   ├── test_suggestions.py  # Tests for suggestion logic
│   └── test_feedback.py     # Tests for feedback recording
│
└── frontend/tests/          # Frontend (Playwright) tests
    ├── conftest.py          # Playwright browser setup
    └── test_frontend.py     # End-to-end UI tests
```

#### Theme System

The application supports two visual background themes, switchable at runtime via a pill-button bar below the page title.

| Theme | Implementation | Body class |
|---|---|---|
| **Equalizer** | Canvas — 56 spring-physics bars with beat simulation, rounded tops, reflections, and per-bar glow | `.theme-equalizer` |
| **Pulse** | Canvas — ring pool (120 slots) with 5 emitters, floating particles, breathing ambient glow, and bass-drop bursts | `.theme-pulse` |

**Switching mechanism:**
1. `switchTheme(name)` sets `document.body.className` to `theme-{name}`
2. Replaces `#themeBackground` innerHTML with a `<canvas>` element for the selected theme
3. Canvas themes start a `requestAnimationFrame` loop; the previous loop is stopped via a returned cleanup function
4. Preference is persisted in `localStorage` under key `spotyvibe-theme` and restored on page load

All canvas renderers are registered in the `THEME_RENDERERS` object in `frontend/static/js/modules/theme-switcher.js`.

---

## macOS & Linux Distribution (Python Wheel)

SpotyVibe is distributed to macOS and Linux users as a standard Python wheel (`.whl`). No PyInstaller, no native binaries, no source files to navigate — just `pip install` and `spotyvibe`.

### How it works

```
pip install spotyvibe-*.whl
spotyvibe                        ← console_scripts entry point
    │
    └── spotyvibe.cli:main()
         ├── 1. Check port 5000 availability
         ├── 2. Import Flask app (triggers config + logging init)
         ├── 3. Open default browser (after 1.5 s delay)
         └── 4. Run Flask server (Ctrl+C to stop)
```

The wheel bundles only the files needed at runtime:

| Contents | Source (repo) |
|---|---|
| `spotyvibe/__init__.py`, `__main__.py`, `cli.py` | `spotyvibe/` |
| `spotyvibe/app.py`, `spotyvibe/config.py` | `app.py`, `config.py` (force-included) |
| `spotyvibe/core/src/` | `core/src/` (force-included) |
| `spotyvibe/frontend/` | `frontend/templates/`, `frontend/static/` (force-included) |
| `spotyvibe/prompts/` | `prompts/` (force-included) |
| `spotyvibe/data/` | `data/` (force-included) |
| `spotyvibe/documentation/` | `documentation/help.md` + screenshots (force-included) |

Tests, Android scaffolding, build scripts, PyInstaller specs, and dev-only files are excluded.

### Key design decisions

| Decision | Rationale |
|---|---|
| `hatchling` build backend with `force-include` | Bundles repo-root files into the `spotyvibe/` package without physically moving any source files |
| `sys.path.insert(0, pkg_dir)` in `cli.py` | Ensures `app.py`'s internal imports (`from config import ...`, `from core.src...`) resolve from the installed wheel location |
| `config.py`'s `BASE_DIR = Path(__file__).resolve().parent` | Automatically points to the wheel's install directory — all asset paths (prompts, templates, data) resolve correctly |
| Single `.whl` for both platforms | Python wheels with tag `py3-none-any` are platform-independent — one artifact serves macOS and Linux |
| `console_scripts` entry point | `pip install` creates a `spotyvibe` command in the user's PATH — no shell scripts needed |
| Hard-coded port 5000 | Spotify OAuth redirect URI is fixed to `http://127.0.0.1:5000/callback` |

### Build command

```bash
pip install build
python -m build --wheel     # produces dist/spotyvibe-<version>-py3-none-any.whl
```

### CI/CD

The GitHub Actions release workflows (`release.yml`, `beta.yml`) include a `build-wheel` job that builds the wheel and attaches it to the GitHub Release alongside the Windows EXE and Android APK.

### Development mode

Developers who clone the repo can still run SpotyVibe directly:

```bash
python app.py                          # classic Flask entry point
# or
pip install -e .                       # editable install, then: spotyvibe
# or
bash build-tools/start.sh             # shell launcher (creates .venv, manages deps)
```

---

## Android Build Versions

The Android packaging layer uses fixed versions so APK builds are reproducible:

| Component | Version |
|---|---|
| Android Gradle Plugin | 8.2.2 |
| Kotlin Gradle plugin | 1.9.22 |
| Chaquopy Gradle plugin | 15.0.1 |
| Android compile SDK | 34 |
| Android target SDK | 34 |
| Android min SDK | 26 |
| Java/Kotlin bytecode target | 17 |
| Python runtime | 3.10 |
| AndroidX core-ktx | 1.12.0 |
| AndroidX appcompat | 1.6.1 |
| AndroidX webkit | 1.10.0 |

The app module also pins its Python dependencies in `android/app/build.gradle`, so the APK build uses the same dependency set every time.

---

## Component Details

### `config.py` — Configuration & Credentials

Manages all application settings and credentials. Secrets (API keys) are stored in the OS keychain (Windows Credential Manager / macOS Keychain) when available, with `.credentials` as a plaintext fallback for platforms without a usable keyring (e.g. Android). Non-secret preferences and app state are stored in `settings.conf` (dotenv format) in the platform-appropriate app data directory (`%LOCALAPPDATA%\spotyvibe\` on Windows).

On first load, any non-secret keys still present in `.credentials` (from older versions) are automatically migrated to `settings.conf`. Plaintext credentials in `.credentials` are automatically migrated to the OS keychain when a usable keyring is detected.

**Key constants:**

| Constant | Purpose |
|---|---|
| `BASE_DIR` | Absolute path to the runtime asset root. In source runs this is the project directory; in PyInstaller builds it resolves to `sys._MEIPASS` so bundled files (templates/static/prompts/data/documentation/help.md) can be found. |

| `BATCH_SIZE` | Number of tracks GPT generates per single request (default: 10). |
| `DEFAULT_PLAYLIST_SIZE` | Default total tracks per generation run (default: 10). |
| `DEFAULT_NEW_ARTIST_PERCENTAGE` | Default minimum percentage of suggestions from artists not yet in history (default: 30). |
| `GPT_HISTORY_LIMIT` | Max history entries sent to GPT to bound token usage (default: 200). |
| `EXHAUSTED_ARTIST_THRESHOLD` | An artist with this many tracks in history is marked [EXHAUSTED] in the exclusion block (default: 4). |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | How many consecutive all-filtered batches are allowed before the loop breaks and the playlist is created with whatever was found (default: 3). |
| `DEFAULT_OPENAI_MODEL` | Fallback model when none is configured (default: `gpt-5.4-mini`). |
| `IS_ANDROID` | `True` when running under Chaquopy (detected via `sys.getandroidapilevel`). All Android-specific logic is gated behind this flag; desktop behaviour is unaffected. |
| `CREDENTIALS_FILE` | Path to `%LOCALAPPDATA%\spotyvibe\.credentials` — plaintext fallback for API secrets when OS keychain is unavailable. On desktop with a usable keyring, this file only holds empty placeholder keys. |
| `SETTINGS_FILE` | Path to `%LOCALAPPDATA%\spotyvibe\settings.conf` — stores non-secret app preferences (`OPENAI_MODEL`, `DEBUG_MODE`, `PLAYLIST_SIZE`, `NEW_ARTIST_PERCENTAGE`, `GPT_LANGUAGE`, `ONBOARDING_COMPLETED`, `ACTIVE_PROFILE_ID`). |
| `PROFILES_DIR` | Path to `%LOCALAPPDATA%\spotyvibe\profiles\` — each profile is a UUID-named `.json` file with an accompanying `.history.json` backup. |
| `MAX_PROFILE_NAME_LEN` | Maximum character length for a profile display name (default: 40). |
| `PROFILE_FILE` | Legacy reference to the old single-profile path (retained for migration awareness). |
| `CACHE_FILE` | Path to the cached Spotify OAuth token. |
| `DEBUG_LOG_FILE` | Path to the debug log file (`%LOCALAPPDATA%\spotyvibe\debug.log`). |
| `PROFILE_IMPORT_MAX_BYTES` | Maximum allowed request size for `POST /api/profile/import` (default: 10MB). |
| `GENERAL_REQUEST_MAX_BYTES` | Maximum request size for all other endpoints (default: 1MB). |
| `MAX_GPT_CALLS_PER_RUN` | Hard ceiling on GPT API calls per generation run (default: 20). |
| `MAX_CORE_DESCRIPTION_LEN` | Maximum character length for profile core description (default: 5000). |
| `MAX_FEEDBACK_ARTIST_LEN` | Maximum character length for feedback artist name (default: 200). |
| `MAX_FEEDBACK_TRACK_LEN` | Maximum character length for feedback track name (default: 200). |
| `MAX_FEEDBACK_REASON_LEN` | Maximum character length for feedback reason text (default: 500). |
| `CREDENTIAL_KEYS` | List of secret key names stored in the OS keychain (or `.credentials` as fallback). |
| `SETTINGS_KEYS` | List of non-secret key names stored in `settings.conf`. |


**Key helpers:**

- **`_get_app_dir()`** — Returns the platform-appropriate storage directory. On Android: reads `SPOTYVIBE_FILES_DIR` env var (set by `MainActivity.kt`), falling back to `/data/data/com.spotyvibe.app/files/spotyvibe/`. On desktop: returns `%LOCALAPPDATA%\spotyvibe` (unchanged). All file paths (`CREDENTIALS_FILE`, `PROFILE_FILE`, `CACHE_FILE`, `DEBUG_LOG_FILE`) are resolved from this base.
- **`get_model()`** — Returns the user's configured `OPENAI_MODEL` from the credentials file, falling back to `DEFAULT_OPENAI_MODEL`.
- **`get_gpt_language()`** — Returns the configured GPT language from the credentials file (default: `"English"`).
- **`get_debug_mode()`** — Returns `True` if the `DEBUG_MODE` setting is enabled (**desktop only**; always `False` on Android).

- **`get_playlist_size()`** — Returns the configured playlist size (minimum `BATCH_SIZE`).
- **`get_new_artist_percentage()`** — Returns the configured new-artist percentage, clamped to 1–100, falling back to `DEFAULT_NEW_ARTIST_PERCENTAGE`.
- **`get_active_profile_id()`** / **`set_active_profile_id(id)`** — Read/write the `ACTIVE_PROFILE_ID` pointer in `settings.conf`. Returns empty string when no profile is active.
- **`get_active_profile_path()`** / **`get_active_history_path()`** — Resolve the full path to the active profile's JSON and history files from `PROFILES_DIR` + `ACTIVE_PROFILE_ID`.
- **`get_settings()`** — Returns `{"model": str, "debug_mode": bool, "playlist_size": int, "new_artist_percentage": int, "debug_log_path": str, "debug_controls_available": bool, "is_android": bool, "gpt_language": str}` for the Settings UI. Debug controls are desktop-only; Android receives `debug_controls_available=false` and an empty `debug_log_path`.


**Credential storage:** On desktop, credentials are stored in the OS keychain (Windows Credential Manager / macOS Keychain) via the `keyring` library. The `.credentials` file (dotenv format, at `%LOCALAPPDATA%\spotyvibe\`) only holds empty placeholder keys when keyring is available; it serves as a plaintext fallback on platforms without a usable keyring (e.g. Android). On startup, `load_config()` reads the `.credentials` file first, then overlays keyring values so the OS keychain always takes precedence. A one-time auto-migration (`_migrate_credentials_to_keyring()`) moves any plaintext secrets from `.credentials` into keyring and clears the plaintext copy. The `save_credentials()` function stores values in keyring when available and only writes to `.credentials` as a fallback.

**Android storage:** On Android, `_get_app_dir()` resolves to the app's internal storage (`/data/data/com.spotyvibe.app/files/`). The `.env` migration from legacy locations is guarded by `if not IS_ANDROID` so it only runs on desktop.

---

### `core/spotify_metadata.py` — Spotify Metadata Lookup (deprecated)

> **Note:** The Spotify Metadata Analysis UI feature was removed because Spotify's February 2026 API changes removed `popularity`, `followers`, and `audio_features` endpoints, making the returned data too sparse to be useful. The module still exists in the codebase but is no longer exposed via any endpoint.

---

### `core/openai_http.py` — Direct HTTP Client for OpenAI API

Replaces the `openai` Python SDK with a stdlib-only HTTP wrapper (`urllib.request` + `json`). This eliminates the native/Rust transitive dependencies (`jiter`, `pydantic-core`) that prevented Android/Chaquopy builds with newer SDK versions.

**Public API:**
- **`chat_completions_create(model, messages, temperature, response_format)`** — `POST /v1/chat/completions`. Validates the model against `OPENAI_SUPPORTED_MODELS_JSON` locally before making the request.
- **`extract_chat_content(response)`** — Extracts the assistant content string from a chat completions response dict.
- **`list_models()`** — `GET /v1/models`. Available for direct use; the Settings UI instead uses the local allowlist via `get_openai_models()`.

**Error hierarchy:** `OpenAIError` → `OpenAIConfigError`, `OpenAIRequestError` (`OpenAIAuthError`, `OpenAIRateLimitError`), `OpenAITimeoutError`, `OpenAIResponseError`, `OpenAIUnsupportedModelError`.

**Retry policy:** 2 retries for `list_models`, 1 retry for `chat_completions_create`. Retries on 429/5xx with exponential back-off.

---

### `core/utils.py` — Shared Utilities

Contains functions used across multiple modules:

- **`get_openai_models()`** — Returns structured model objects `{"id", "label", "supported"}` from the curated allowlist (`OPENAI_SUPPORTED_MODELS_JSON` in `config.py`). No API call is made. The currently configured model is appended at the end if it is not in the allowlist (marked `supported: false`).
- **`strip_code_fences(text)`** — Removes markdown code fences (`` ```json ... ``` ``) from GPT responses. Used by both `suggestions.py` and `profile.py`.
- **`debug_log(label, messages, response_content)`** — Appends a timestamped GPT request/response pair to the debug log file. Only writes when debug mode is enabled. Used by `call_gpt()` (suggestions) and `train_profile()` (profile training).
- **`sanitize_text(text)`** — Removes null bytes and control characters, normalizes whitespace. Used to sanitize untrusted user input before processing or storage.
- **`sanitize_profile(profile)`** — Recursively applies `sanitize_text()` to all string values in a profile dict/list structure. Used during profile import to prevent injection of malicious content.

---

### `core/profile.py` — Taste Profile Management

Handles loading, saving, training, and multi-profile CRUD for user music taste profiles.

**Multi-profile architecture:**

Profiles are stored as individual JSON files in the `profiles/` directory under the app data path. Each file is named with a UUID (e.g. `a1b2c3d4-...-.json`) and contains a `"name"` field for the user-facing display name. The active profile is tracked via `ACTIVE_PROFILE_ID` in `settings.conf`.

**Profile CRUD:**

| Function | Purpose |
|---|---|
| `list_profiles()` | Scans `profiles/*.json` (excluding `*.history.json`), returns `[{id, name, trained, last_updated}]` sorted alphabetically. Silently skips corrupt files. |
| `create_profile(name)` | Validates name (non-empty, ≤40 chars, no case-insensitive duplicates), creates a UUID-named file from the template, auto-activates it. |
| `delete_profile(profile_id)` | Removes both `.json` and `.history.json` files. Clears the active pointer if the deleted profile was active. |
| `activate_profile(profile_id)` | Sets `ACTIVE_PROFILE_ID` in settings. Validates the file exists first. |

**Profile lifecycle:**

1. The user creates a profile from the UI dropdown (or one is created on first use). The empty template from `data/music_profile.json` is copied with the chosen display name.
2. The user fills in structured accordion sections (core description, must-have, soft preferences, avoid) in the UI. Existing profile data is pre-filled via `GET /api/profile/data`.
3. The user can save changes in two ways:
   - **Direct save** (`POST /api/save-profile`): `save_profile_sections()` writes the user's input directly to the profile preferences without AI processing. Multi-line fields (must-have, soft preferences, avoid) are split into arrays by newline.
   - **AI Profile Update** (`POST /api/train-profile`): `train_profile()` receives a `sections` dict and builds a labelled GPT message with `## VIBE DESCRIPTION`, `## CORE DESCRIPTION`, `## MUST HAVE`, `## SOFT PREFERENCES`, and `## AVOID` headers so GPT understands the purpose and priority of each section. The vibe description field undergoes **automatic classification**: GPT analyses the free-form text for directional language (e.g. "must have", "never", "would be nice") and routes each statement to the correct profile section (`must_have`, `avoid`, `soft_preferences`, or `core_description`). This ensures that conversational input like "music must have heavy bass and no autotune" is properly split into structured profile entries rather than being lost in the core description. GPT returns an updated profile JSON. History and feedback sections are preserved server-side (GPT's version is discarded for these sections). After the update, `vibe_description` is cleared — it was a one-time instruction now incorporated into the structured profile.
4. The profile is saved with a `last_updated` timestamp.

**History backup:** Every save a
