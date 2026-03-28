# Technical Manual

This document covers the architecture, component interactions, and developer-level details of SpotyVibe.

---

## Architecture Overview

SpotyVibe is a Python web application built with **Flask** that connects two external APIs:

- **OpenAI API** — generates personalised music suggestions based on a structured taste profile.
- **Spotify Web API** — searches for tracks, manages a private playlist, and handles user authentication via OAuth 2.0.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser (index.html)                        │
│                                                                    │
│  Train Profile ─── Generate Playlist ─── Like/Dislike/Remove       │
└──────────┬────────────────┬────────────────────┬────────────────────┘
           │ POST           │ POST (SSE stream)  │ POST
           ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Flask App (app.py)                          │
│                                                                    │
│  /api/train-profile   /api/run              /api/feedback          │
│  /api/save-profile    /api/spotify/status   /api/remove            │
│  /api/profile/status                                               │
│  /api/spotify/auth    /api/spotify/disconnect  /api/cancel          │
│  /callback            /api/settings/*       /api/help              │
│  /api/settings        /api/settings/debug-log                      │
└──────┬───────────────────┬───────────────────────┬──────────────────┘
       │                   │                       │
       ▼                   ▼                       ▼
┌──────────────┐   ┌──────────────┐   ┌────────────────────────────┐
│ core/profile │   │    core/     │   │  core/playlist             │
│              │   │ suggestions  │   │                            │
│ - load/save  │   │              │   │ - search_tracks (parallel) │
│ - train via  │   │ - build_msgs │   │ - add_to_playlist          │
│   OpenAI     │   │ - call_gpt   │   │ - remove_from_playlist     │
│ - save_profile│  │ - dedup      │   │ - OAuth flow               │
│   _sections  │   │              │   │                            │
│              │   │ - dedup      │   │ - OAuth flow               │
└──────┬───────┘   └──────┬───────┘   └──────┬─────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  OpenAI API  │   │  OpenAI API  │   │ Spotify API  │
│ (configurable│   │ (configurable│   │  (Web API)   │
│    model)    │   │    model)    │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
```

---

## Project Structure

```
spotyvibe/
├── app.py                  # Flask web server — all HTTP endpoints
├── config.py               # Centralised configuration & credential management
├── requirements.txt        # Python dependencies (pinned version ranges)
├── README.md               # Project overview
├── UserManual.md           # End-user documentation
├── TechnicalManual.md      # This file
│
├── core/                   # Business logic modules
│   ├── __init__.py         # Package marker (empty)
│   ├── utils.py            # Shared utilities (OpenAI client, code-fence stripping)
│   ├── profile.py          # Taste profile I/O and GPT-based training
│   ├── suggestions.py      # GPT suggestion engine and deduplication logic
│   ├── playlist.py         # Spotify playlist management and OAuth
│   └── feedback.py         # Like/dislike recording
│
├── prompts/                # AI prompt templates (editable without code changes)
│   ├── system_prompt.txt          # System message: rules, matching, output format
│   ├── prompt_template.txt        # User message: embeds the profile JSON
│   └── profile_training_prompt.txt # System message for taste profile training
│
├── data/                   # Template data
│   └── music_profile.json  # Empty profile template (seeded on first run)
│
├── static/                 # Static assets served by Flask
│   └── css/
│       └── styles.css      # Main stylesheet — dark glass design system + theme definitions
│
├── templates/              # Flask templates
│   └── index.html          # Single-page web UI (HTML + JS)
│├── android/                # Android APK build scaffolding (Chaquopy + Gradle)
│   ├── build.gradle        # Root Gradle config with pinned AGP 8.2.2, Kotlin 1.9.22, Chaquopy 15.0.1
│   ├── build_apk.sh        # One-command build script (copies sources + runs Gradle)
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
│└── tests/                  # Automated tests
    ├── conftest.py         # Pytest configuration
    ├── test_utils.py       # Tests for shared utilities
    ├── test_suggestions.py # Tests for suggestion logic
    └── test_feedback.py    # Tests for feedback recording
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

All canvas renderers are registered in the `THEME_RENDERERS` object in `index.html`.

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

Manages all application settings and credentials.

**Key constants:**

| Constant | Purpose |
|---|---|
| `BASE_DIR` | Absolute path to the `spotyvibe/` directory. All file paths are resolved from here. |
| `BATCH_SIZE` | Number of tracks GPT generates per single request (default: 10). |
| `DEFAULT_PLAYLIST_SIZE` | Default total tracks per generation run (default: 10). |
| `DEFAULT_NEW_ARTIST_PERCENTAGE` | Default minimum percentage of suggestions from artists not yet in history (default: 30). |
| `GPT_HISTORY_LIMIT` | Max history entries sent to GPT to bound token usage (default: 200). |
| `EXHAUSTED_ARTIST_THRESHOLD` | An artist with this many tracks in history is marked [EXHAUSTED] in the exclusion block (default: 4). |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | How many consecutive all-filtered batches are allowed before the loop breaks and the playlist is created with whatever was found (default: 3). |
| `DEFAULT_OPENAI_MODEL` | Fallback model when none is configured (default: `gpt-4.1-mini`). |
| `IS_ANDROID` | `True` when running under Chaquopy (detected via `sys.getandroidapilevel`). All Android-specific logic is gated behind this flag; desktop behaviour is unaffected. |
| `CREDENTIALS_FILE` | Path to `%LOCALAPPDATA%\spotyvibe\.credentials`. |
| `PROFILE_FILE` | Path to the personalised taste profile in AppData. |
| `CACHE_FILE` | Path to the cached Spotify OAuth token. |
| `DEBUG_LOG_FILE` | Path to the debug log file (`%LOCALAPPDATA%\spotyvibe\debug.log`). |
| `PROFILE_IMPORT_MAX_BYTES` | Maximum allowed request size for `POST /api/profile/import` (default: 10MB). |


**Key helpers:**

- **`_get_app_dir()`** — Returns the platform-appropriate storage directory. On Android: reads `SPOTYVIBE_FILES_DIR` env var (set by `MainActivity.kt`), falling back to `/data/data/com.spotyvibe.app/files/spotyvibe/`. On desktop: returns `%LOCALAPPDATA%\spotyvibe` (unchanged). All file paths (`CREDENTIALS_FILE`, `PROFILE_FILE`, `CACHE_FILE`, `DEBUG_LOG_FILE`) are resolved from this base.
- **`get_model()`** — Returns the user's configured `OPENAI_MODEL` from the credentials file, falling back to `DEFAULT_OPENAI_MODEL`.
- **`get_debug_mode()`** — Returns `True` if the `DEBUG_MODE` setting is enabled (**desktop only**; always `False` on Android).

- **`get_playlist_size()`** — Returns the configured playlist size (minimum `BATCH_SIZE`).
- **`get_new_artist_percentage()`** — Returns the configured new-artist percentage, clamped to 1–100, falling back to `DEFAULT_NEW_ARTIST_PERCENTAGE`.
- **`get_settings()`** — Returns `{"model": str, "debug_mode": bool, "playlist_size": int, "new_artist_percentage": int, "debug_log_path": str, "debug_controls_available": bool, "is_android": bool}` for the Settings UI. Debug controls are desktop-only; Android receives `debug_controls_available=false` and an empty `debug_log_path`.


**Credential storage:** Credentials and settings (including the selected model) are stored in `%LOCALAPPDATA%\spotyvibe\.credentials` as a dotenv file, outside the project directory. The `load_config()` function loads them into `os.environ`. The `save_credentials()` function ensures the file always ends with a newline before appending new keys, preventing `python-dotenv` parse errors from concatenated lines.

**Android storage:** On Android, `_get_app_dir()` resolves to the app's internal storage (`/data/data/com.spotyvibe.app/files/spotyvibe/`). The `.env` migration from legacy locations is guarded by `if not IS_ANDROID` so it only runs on desktop.

---

### `core/utils.py` — Shared Utilities

Contains functions used across multiple modules:

- **`get_openai_client()`** — Returns a lazily-initialised OpenAI client. Re-creates the client when the API key changes (e.g., after a settings update). Raises a clear error if the key is not configured.
- **`strip_code_fences(text)`** — Removes markdown code fences (`` ```json ... ``` ``) from GPT responses. Used by both `suggestions.py` and `profile.py`.
- **`get_openai_models()`** — Fetches the list of available GPT chat models from the OpenAI API. Filters to models suitable for chat completions (prefixed `gpt-`, `o1`, `o3`, `o4`) and excludes audio, realtime, transcription, TTS, and embedding variants.
- **`debug_log(label, messages, response_content)`** — Appends a timestamped GPT request/response pair to the debug log file. Only writes when debug mode is enabled. Used by `call_gpt()` (suggestions) and `train_profile()` (profile training).

---

### `core/profile.py` — Taste Profile Management

Handles loading, saving, and training the user's music taste profile.

**Profile lifecycle:**

1. On first run, the empty template from `data/music_profile.json` is copied to AppData.
2. The user fills in structured accordion sections (core description, must-have, soft preferences, avoid) in the UI. Existing profile data is pre-filled via `GET /api/profile/data`.
3. The user can save changes in two ways:
   - **Direct save** (`POST /api/save-profile`): `save_profile_sections()` writes the user's input directly to the profile preferences without AI processing. Multi-line fields (must-have, soft preferences, avoid) are split into arrays by newline.
   - **AI Profile Update** (`POST /api/train-profile`): `train_profile()` receives a `sections` dict and builds a labelled GPT message with `## CORE DESCRIPTION`, `## MUST HAVE`, `## SOFT PREFERENCES`, and `## AVOID` headers so GPT understands the purpose and priority of each section. GPT returns an updated profile JSON. History and feedback sections are preserved server-side (GPT's version is discarded for these sections).
4. The profile is saved with a `last_updated` timestamp.

**History backup:** Every save creates a `.history.json` backup of the previous version, allowing one-step revert.

**GPT interaction for training:**
- Model: Configurable via Settings (default: `gpt-4.1-mini`)
- Temperature: `0.3` (low creativity — profile updates should be deterministic)
- Response format: `json_object` (guaranteed valid JSON)

---

### `core/suggestions.py` — Suggestion Engine

The core recommendation logic. Generates track suggestions by sending the user's taste profile to GPT.

**Flow:**

1. `normalize_history()` — Lowercases and deduplicates history lists.
2. `build_messages()` — Builds the system + user message pair:
   - Loads the system prompt from `prompts/system_prompt.txt`.
   - Fills in three per-run placeholders: `{batch_size}`, `{new_artist_percentage}`, and `{min_new_artists}` (derived as `ceil(batch_size × new_artist_percentage / 100)`). This makes the "minimum new artists" instruction in the system prompt a hard, numerically precise requirement that changes with the user's setting.
   - Embeds a **truncated** copy of the profile (history capped at `GPT_HISTORY_LIMIT` entries).
   - On retries with accepted tracks, appends an addendum listing already-accepted tracks.
   - **On all-filtered retries**, appends a strongly-worded retry warning that lists the exact tracks from the previous batch that were filtered, making it impossible for GPT to plausibly overlook them. The warning escalates with the attempt number and is passed via the `recently_filtered_tracks` / `consecutive_empty` parameters.
3. `call_gpt()` — Sends messages to GPT and parses the JSON response.
4. `normalize_response()` — Force-lowercases all artist/track names.
5. `filter_duplicate_suggestions()` — Code-side dedup against full history + disliked tracks (uses fuzzy matching via `_normalize_key()`). Stores the removed tracks in `result["_filtered_out"]` so the caller can feed them back to GPT as explicit retry context.
6. `update_profile()` — Merges new suggestions into the profile's history.

**GPT interaction for suggestions:**
- Model: Configurable via Settings (default: `gpt-4.1-mini`)
- Temperature: `0.7` (higher creativity for diverse suggestions)
- Response format: `json_object`

**Deduplication strategy:** GPT is instructed to avoid duplicates, but compliance is not guaranteed. `filter_duplicate_suggestions()` applies a second pass using fuzzy key normalisation (lowercase, strip punctuation, collapse whitespace) to catch any duplicates GPT missed. Removed tracks are stored in `result["_filtered_out"]` (an internal key stripped before any data reaches the UI) so the orchestrator in `app.py` can pass them explicitly back to GPT on the next retry.

**Retry / exhaustion guard:** The generation loop in `app.py` tracks how many consecutive batches returned an entirely-filtered result. After `MAX_CONSECUTIVE_EMPTY_BATCHES` (default: 3) consecutive failures, the loop breaks and the playlist is created with however many tracks were verified up to that point (identical behaviour to the "Use X tracks now" user action). Each failed batch passes `recently_filtered_tracks` to `build_messages`, so GPT receives an escalating, explicit list of the tracks it must not suggest.

---

### `core/playlist.py` — Spotify Integration

Manages all interactions with the Spotify Web API via the `spotipy` library.

**Key functions:**

| Function | Purpose |
|---|---|
| `get_spotify_oauth()` | Creates a `SpotifyOAuth` instance with the token cache in AppData. |
| `get_spotify_client()` | Returns an authenticated `spotipy.Spotify` client. |
| `get_spotify_auth_status()` | Checks credentials, cached token, **and** validates the token with a live `current_user()` API call. Returns `not_configured`, `not_authenticated`, or `authenticated`. |
| `disconnect_spotify()` | Deletes the cached token file so the user can re-authenticate. Called automatically on 403 errors or manually via the UI. |
| `search_tracks(tracks)` | Searches Spotify for each track using **parallel requests** (ThreadPoolExecutor, 10 workers). Returns found/not-found lists. Found tracks include the Spotify `uri` and `cover_url` (smallest album image). |
| `add_to_playlist(tracks)` | Finds or creates the "SpotyVibe Playlist" and adds verified tracks. Catches 403 errors, auto-disconnects, and raises a clear `RuntimeError`. |
| `remove_from_playlist(artist, track)` | Searches for a track and removes all occurrences from the playlist. |
| `find_existing_playlist(sp)` | Paginates through the user's playlists to find one matching the playlist name. |

**OAuth flow:**
1. User clicks "Connect to Spotify" → browser opens Spotify's authorisation page.
2. User grants permission → Spotify redirects to `/callback` with an authorisation code.
3. The app exchanges the code for access + refresh tokens, cached in AppData.
4. Subsequent requests use the cached token, refreshing automatically when expired.
5. If a token becomes invalid (e.g., revoked permissions, scope changes), the auth status check detects this and shows the connect banner again.

**Token validation:** `get_spotify_auth_status()` does not just check for a cached token file — it makes a lightweight `current_user()` API call to verify the token is actually valid. Stale or revoked tokens are reported as `not_authenticated` so the UI prompts re-connection.

**403 error handling:** `add_to_playlist()` catches `SpotifyException` with HTTP 403. When this occurs, it automatically calls `disconnect_spotify()` to clear the stale token and raises a `RuntimeError` with a user-friendly message. The UI then shows the "Connect to Spotify" banner on the next status check.

**Spotify API compatibility:** Playlist creation uses `POST /v1/me/playlists` (via `spotipy.Spotify.current_user_playlist_create()`) instead of the deprecated `POST /v1/users/{user_id}/playlists` endpoint, which was removed by Spotify in February 2026.

**Parallelised search:** `search_tracks()` uses `ThreadPoolExecutor` with 10 workers to verify tracks on Spotify concurrently, reducing the search time from ~15s (sequential) to ~2s for typical playlist sizes (e.g., 10–30 tracks).


**Search query sanitisation:** User/model-provided artist and track strings are sanitised before building `track:"..." artist:"..."` queries to avoid malformed Spotify search syntax (e.g., embedded quotes/control characters).


---

### `core/feedback.py` — Feedback Recording

Records user likes and dislikes into the taste profile.

| Action | With track | Without track |
|---|---|---|
| **Like** | Adds `{artist, track, reason}` to `feedback.liked_tracks`. Artist added to `artists.confirmed`. | Artist added to `artists.confirmed` only. |
| **Dislike** | Adds `{artist, track, reason}` to `feedback.disliked_tracks`. Artist is **not** rejected. | Artist added to `artists.rejected` (fully excluded from future suggestions). |

Also usable as a CLI tool: `python -m core.feedback <like|dislike> "Artist" [--track "Track"] [--reason "Why"]`.

---

### `app.py` — Flask Web Server

Exposes all functionality via HTTP endpoints.

**API endpoints:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serves the single-page web UI. |
| POST | `/api/run` | Runs the full generation pipeline. Returns an **SSE stream** with progress events. Accepts optional JSON body `{"run_id": "..."}`. |
| POST | `/api/cancel` | Cancels an active generation run by `run_id`. Accepts `{"run_id": "...", "finalize": bool}`. When `finalize` is `true`, the playlist is created with however many tracks have been verified so far. |
| POST | `/api/feedback` | Records a like or dislike. Dislikes also remove the track from Spotify. |
| POST | `/api/remove` | Removes a track from Spotify without recording feedback. |
| GET | `/api/profile/status` | Returns whether the profile is trained and when. |
| GET | `/api/profile/data` | Returns the full profile JSON for pre-filling the training form. |
| GET | `/api/profile/export` | Downloads the full profile JSON as `spotyvibe_profile.json` (used by the UI Export button). |
| POST | `/api/profile/import` | Replaces the full profile JSON from an imported JSON object (used by the UI Import button). The previous profile is backed up to `.history.json`. Enforces a 10MB request size limit. |
| POST | `/api/profile/reset-to-history` | Swaps the active profile file with its `.history.json` backup (one-step revert). Returns 400 if no history exists yet. |
| POST | `/api/train-profile` | Sends structured taste sections (`core_description`, `must_have`, `soft_preferences`, `avoid`) to GPT and updates the profile. `core_description` is required. |


| GET | `/api/spotify/status` | Returns Spotify auth status (`not_configured`, `not_authenticated`, `authenticated`). Validates the token with a live API call. |
| GET | `/api/spotify/auth` | Redirects to Spotify's authorisation page. |
| POST | `/api/spotify/disconnect` | Clears the cached Spotify token to force re-authentication. |
| GET | `/callback` | Handles the OAuth callback from Spotify. |
| GET | `/api/settings/credentials` | Returns masked credential values. |
| POST | `/api/settings/credentials` | Updates credentials. Ensures trailing newline to prevent dotenv parse errors. |
| GET | `/api/settings` | Returns non-secret settings (model, debug mode, playlist size, new artist percentage). |
| POST | `/api/settings` | Updates non-secret settings (model, debug mode, playlist size, new artist percentage). |
| GET | `/api/settings/models` | Returns available OpenAI chat models and the currently selected one. |
| DELETE | `/api/settings/debug-log` | Clears the debug log file (**desktop only**; returns 404 on Android). |

| GET | `/api/help` | Returns the User Manual content as rendered HTML. |

**SSE streaming (`/api/run`):**
The generation pipeline returns a `text/event-stream` response. Each event is a JSON line with a `type` field:
- `progress` — status update (e.g., "Batch 1: Asking GPT for 10 suggestions…")
- `batch_verified` — emitted after each batch completes: `{"count": N, "total": M}`. The UI uses this to update the **"▶ Use X tracks now"** button label.
- `result` — final result with playlist data, Spotify URL, and stats. Includes `"was_cancelled": true` when produced by a `finalize` cancel.
- `cancelled` — emitted when the run is cancelled without finalisation. Includes a human-readable `message`.
- `error` — error message.

**Cancellation mechanism:**
Each `/api/run` request is assigned a `run_id` (generated client-side via `crypto.randomUUID()` and sent in the JSON body). The server stores a `threading.Event` per run in the module-level `_runs` dict. The generation loop checks the event:
1. At the **start** of each iteration — prevents unnecessary GPT calls.
2. Immediately **after** `call_gpt()` returns — stops processing if cancel was requested during the blocking network call.

When `/api/cancel` is called with `finalize: false`, the generator yields a `cancelled` event and returns without touching the playlist. When `finalize: true` is set, the generator breaks out of the loop, caps the verified tracks at the target size, and continues to the playlist-creation step — yielding a `result` event as normal but with `was_cancelled: true`.

---

### `templates/index.html` — Web UI

A self-contained single-page application (HTML + CSS + vanilla JavaScript, no framework). Communicates with the Flask backend via `fetch` API calls.

**Layout:** The UI is divided into two labelled sections with subheaders and short descriptions:
- **Step 1 — Taste Profile:** Train the AI on your music preferences.
- **Step 2 — Generate Playlist:** Create a Spotify playlist from the trained profile.

Both sections are wrapped in styled cards (`.train-section` and `.generate-section`) for visual consistency.

**Key UI components:**
- **Train Taste Profile** — accordion-style editor with four collapsible sections: Core Description (required, open by default), Must Have, Soft Preferences, and Avoid. Existing profile data is pre-filled via `GET /api/profile/data` when the form is opened. Core Description is validated client-side — submission is blocked with an error highlight if empty. Shows an inline warning and disables inputs if the OpenAI API key is missing.
- **Profile import/export/reset** — when the user explicitly enters Edit Profile mode, the UI exposes **⬆ Import** (posts to `POST /api/profile/import`), **⬇ Export** (downloads from `GET /api/profile/export`), and **↩ Reset to history** (calls `POST /api/profile/reset-to-history`). Import replaces the entire profile file; the previous profile is automatically backed up via `.history.json`.


- **Generate button** — triggers the pipeline with live progress updates. Shows an inline warning and disables the button if OpenAI key or Spotify credentials/authentication are missing.
- **⛔ Cancel button** — visible only during generation. Calls `POST /api/cancel` with `finalize: false` and aborts the SSE reader via `AbortController`. Stops the generation without creating or modifying any playlist.
- **▶ Use X tracks now button** — visible during generation once at least one track has been verified. Calls `POST /api/cancel` with `finalize: true` (does NOT abort the SSE reader). The server stops the loop and emits a `result` event with the partial playlist. Label updates in real time via `batch_verified` SSE events.
- **Track list** — displays suggestions with album cover thumbnails (48×48px, sourced from Spotify), like/dislike/remove actions.
- **Feedback form** — expandable per-track form with artist, track, and reason fields.
- **Gear dropdown menu** — Credentials, Settings, Disconnect Spotify (visible only when connected), and Help.
- **Credentials modal** (`🔑 Credentials`) — manages API keys (OpenAI, Spotify). Secrets only.
- **Settings modal** (`⚙️ Settings`) — model selection ("Used Model" dropdown) and debug mode toggle. Non-secret configuration.
- **Help modal** — loads the User Manual content from `/api/help`.
- **Toast notifications** — brief confirmation messages after feedback/remove actions.

**Debug mode (desktop only):** When enabled via the Settings modal on desktop, all GPT interactions (both suggestion generation and profile training) are logged to `%LOCALAPPDATA%\spotyvibe\debug.log` via the `debug_log()` utility. Android builds do not expose debug controls and do not write prompt logs.


---

### `static/css/styles.css` — Visual Design System

The stylesheet implements a premium aurora-wave dark glass design with the following architecture:

**Color palette:**
- Base: near-black `#050608`
- Primary green: `#1ed760`
- Aurora accents: teal `#19d3c5`, cyan `#4ca8ff`, purple `#8c3dff`, violet `#b14dff`, pink `#ff4db8`

**Background:** Layered stage-like composition with a radial green glow near the top and a purple glow near the bottom, creating a cinematic atmosphere. A `body::after` pseudo-element provides a subtle vignette (inset box-shadow) around the viewport edges for a premium stage-lit feel.

**Wave system:** 6-layer aurora ribbon system with luminous, organic sound-ribbon shapes:
- **Top wave** (3 layers): teal/green/mint ribbon + glow + ambient haze, animated at 20s cycle with 4-keyframe motion.
- **Bottom wave** (3 layers): blue/purple/violet ribbon + glow + ambient haze, animated at 26s cycle with 4-keyframe motion.
- Ribbons are thicker and more visible than before (opacity 0.52–0.58) with stronger blur values (90–100px haze, 55–65px glow, 32–38px core ribbon).

**Glass panels:** All cards, modals, dropdowns, and panels use semi-transparent gradient backgrounds (85–90% opacity) with `backdrop-filter: blur(16px)` for a frosted dark glass effect. Deep multi-layer box-shadows and an inset `0 1px 0 rgba(255,255,255,0.05)` inner highlight give each panel a floating, premium feel.

**Typography:** Inter font (weights 400–800). Title set at 2.8rem / 800 weight with a dual-layer green `text-shadow` glow (60px + 120px). Section labels use pink/magenta `#ff4db8` uppercase text with 2px letter-spacing.

**Buttons:** Primary CTA uses a bright gradient green background (`#24e86d` → `#18cf58`) with inset highlight and triple-layer glow shadow (10px + 60px); pill-shaped with 18px 40px padding. On hover, scales to 1.02× with intensified glow. Secondary buttons use dark glass styling with subtle borders.

**Border radius:** 12px (small elements / inputs), 18px (medium panels), 24px (cards / modals), 999px (pill buttons).

**Inputs:** Darker input background (`#0f1318`) with 3px focus rings and additional glow halo for enhanced accessibility and premium feel.

**Accessibility:** A `prefers-reduced-motion` media query disables all CSS animations and transitions for users who have requested reduced motion in their OS settings.

**Responsive Design:**

The stylesheet includes two CSS media-query breakpoints for mobile and tablet devices. No HTML or JavaScript changes were required — the existing `<meta name="viewport" content="width=device-width, initial-scale=1.0">` tag in `index.html` is sufficient.

| Breakpoint | Target | Key layout changes |
|---|---|---|
| `max-width: 768px` | Tablets | Reduced container padding, smaller headings (`h1` / `h2`), wrapping track actions, smaller modals, adjusted button padding |
| `max-width: 480px` | Phones | Minimal padding, vertical stacking for buttons / forms / modals, full-width modals that slide up from the bottom (bottom-sheet pattern), 44px minimum touch targets on all interactive elements, full-width toast notifications, repositioned tooltips, stacked train header and actions |

The desktop experience is completely unaffected — all responsive rules are scoped inside `@media` blocks. This is relevant to the planned Android APK: the WebView will render the same responsive UI without any additional adaptation.

---

### Android Platform (`android/`)

The `android/` directory contains a complete Android project that packages SpotyVibe as a self-contained APK using **Chaquopy** — a Gradle plugin that embeds a Python interpreter and pip-installed dependencies inside the APK.

**Platform detection:** `config.py` sets `IS_ANDROID = True` when `sys.getandroidapilevel` exists (a Chaquopy-specific attribute). All Android-specific paths and behaviours are gated behind this flag, so the desktop experience is completely unaffected.

**Storage path resolution:** `_get_app_dir()` returns the platform-appropriate base directory. On Android it reads the `SPOTYVIBE_FILES_DIR` environment variable (injected by `MainActivity.kt` at startup) and falls back to `/data/data/com.spotyvibe.app/files/spotyvibe/`. All credential, profile, cache, and log paths derive from this base.

**Chaquopy bundling:** The app-level `build.gradle` configures:
- Python 3.10 interpreter
- pip dependencies from `requirements.txt`
- ABI filters: `arm64-v8a` (production devices) + `x86_64` (emulator testing — remove for release builds)
- Python source directory pointing to the copied project files

**Build script (`build_apk.sh`):** A one-command script that:
1. Copies `app.py`, `config.py`, `core/`, `prompts/`, `data/`, `templates/`, `static/` into `android/app/src/main/python/` using `find` + `cpio`, skipping `__pycache__` directories during the copy itself (avoids copying then cleaning)
2. Copies `requirements.txt` for Chaquopy's pip integration
3. Runs `./gradlew assembleDebug` to produce the APK

**MainActivity lifecycle (`MainActivity.kt`):**
1. Sets `SPOTYVIBE_FILES_DIR` environment variable pointing to the app's internal files directory.
2. Starts Flask in a **daemon thread** so the Android main thread remains free for UI rendering.
3. Shows a splash screen while Flask initialises.
4. Polls `http://127.0.0.1:5000` until the server responds (with exponential backoff).
5. Hides the splash screen and loads the URL in a **WebView** with JavaScript enabled.
6. Enables Android-specific WebView integrations:
   - **File chooser support** (`onShowFileChooser`) so `<input type="file">` works for profile import.
      - **Download handling** (`DownloadListener` + `DownloadManager`) so the profile export endpoint downloads into the device's **Downloads**. Downloads are restricted to `http://127.0.0.1:5000/api/profile/export`.

7. `app.py` sets `use_reloader=False` on Android because Flask's reloader forks a child process, which crashes under Chaquopy's embedded runtime.
8. **`onDestroy()`** interrupts the Flask daemon thread and calls `WebView.destroy()` to release resources when the activity is finishing.
9. **`onNewIntent()`** handles OAuth callback deep-links from the system browser, loading the callback URL in the WebView so the token exchange completes inside the app process.


**OAuth flow on Android:** Desktop browsers handle Spotify OAuth via a `window.open()` popup. On Android WebView this fails because popup URLs that leave `127.0.0.1` (e.g. `accounts.spotify.com`) are routed to the system browser, which cannot reach the localhost `/callback` endpoint since Flask runs only inside the app process.

The fix uses a two-part detection and fallback:
1. **Frontend detection:** `index.html` checks the user-agent for `/; wv\)/` (the Android WebView signature). When detected, `window.location.href = '/api/spotify/auth'` replaces the popup with a same-window redirect.
2. **Backend fallback:** The `/callback` handler's success page checks for `window.opener`. When it is `null` (the direct-navigation case on Android), the page issues a delayed redirect to the home page with `setTimeout(()=>window.location.href="/",1500)` instead of attempting `window.opener.postMessage()`. The 1.5 s delay matches the popup path and lets the user see the success message.
3. **Deep-link return:** `onNewIntent()` in `MainActivity.kt` intercepts the OAuth callback URL from the system browser and loads it in the WebView, completing the token exchange inside the app.

Desktop behaviour is completely unaffected — the popup flow is used whenever WebView is not detected.

**Permissions:** `AndroidManifest.xml` declares `INTERNET` and `ACCESS_NETWORK_STATE` — required for OpenAI API calls, Spotify API calls, and localhost Flask communication.

**Project structure:**

| File | Purpose |
|---|---|
| `build.gradle` (root) | Gradle plugins: Android + Chaquopy. Uses modern Gradle 8.x convention (repositories declared in `settings.gradle` via `dependencyResolutionManagement`, no `allprojects` block). |
| `app/build.gradle` | App config: Python version, pip deps, ABI filters (`arm64-v8a` + `x86_64`), min/target SDK |
| `AndroidManifest.xml` | Permissions and activity declaration |
| `MainActivity.kt` | Flask thread, splash screen, WebView, OAuth popups |
| `activity_main.xml` | FrameLayout: splash ImageView + WebView |
| `build_apk.sh` | Copies Python sources and runs Gradle build |
| `settings.gradle` | Gradle project structure and centralised `dependencyResolutionManagement` repository declarations |
| `gradle.properties` | JVM args and Android build properties |

---

### Prompt Files

The AI's behaviour is controlled by text files in the `prompts/` directory. These can be edited without touching any Python code.

| File | Used by | Purpose |
|---|---|---|
| `system_prompt.txt` | `suggestions.py` | Defines all rules for music recommendation. Contains: profile section guide, **Bear Ghost primary-reference section**, exclusion rules, discovery rules, **hard negative disqualification rules**, selection criteria, self-verification checklist, and the output JSON schema (including the `validation` block). |
| `prompt_template.txt` | `suggestions.py` | Template for the user message. Embeds the profile JSON via `{profile_json}` and the exclusion block via `{exclusion_block}`. |
| `profile_training_prompt.txt` | `profile.py` | System message for the taste profile training. Explains the structured input format (CORE DESCRIPTION, MUST HAVE, SOFT PREFERENCES, AVOID), how each section maps to profile JSON fields, and which sections to preserve. |

**Bear Ghost primary reference:** The system prompt contains an explicit "BEAR GHOST IS YOUR PRIMARY STYLE REFERENCE" section that lists concrete Bear Ghost characteristics (theatrical structure, extreme dynamic range, non-obvious hooks, controlled chaos) and instructs GPT to use these as the primary filter — weighted more heavily than The Beatles or Queen.

**Hard negative rules:** A dedicated "HARD NEGATIVE RULES" section lists concrete disqualifiers: predictable melody, basic verse/chorus structure with no variation, non-evolving chorus, generic pub-rock sound. These are framed as immediate disqualifications, not soft preferences.

**Validation block:** The JSON schema includes a `validation` object that GPT must fill in:
```json
"validation": {
  "new_artist_count": 4,
  "exclusion_violations": [],
  "must_have_check_passed": true
}
```
This forces GPT to perform chain-of-thought verification before finalising output. The `validation` key is stripped by `normalize_response()` before any data reaches the application logic or the UI — it is purely a prompt-engineering technique to improve output quality.

---

## Data Flow: Generation Pipeline

```
User clicks "Generate"
        │
        ▼
 ┌─────────────────┐
 │  Load profile    │◄── %LOCALAPPDATA%\...\personalized_music_profile.json
 │  Normalize hist. │
 └────────┬────────┘
          │
          ▼
 ┌─────────────────┐     ┌──────────────┐
 │  Build messages  │────►│  OpenAI API  │
 │  (profile JSON   │     │  GPT-4.1     │
 │   + system rules)│◄────│  (JSON mode) │
 └────────┬────────┘     └──────────────┘
                    │ N suggestions (until playlist_size is reached)

          ▼
 ┌─────────────────┐
 │  Filter dupes    │ Code-side dedup against full history + disliked
 │  (fuzzy match)   │
 └────────┬────────┘
          │ filtered suggestions
          ▼
 ┌─────────────────┐     ┌──────────────┐
 │  Search Spotify  │────►│ Spotify API  │ 10 parallel requests
 │  (verify tracks) │◄────│ (search)     │
 └────────┬────────┘     └──────────────┘
          │ verified tracks (with URIs)
          ▼
 ┌─────────────────┐
 │  Update history  │───► Save to profile JSON
 └────────┬────────┘
          │
     ┌────┴──── Enough tracks? ──── No ──► Retry (up to 3 attempts)
     │
     ▼ Yes
 ┌─────────────────┐     ┌──────────────┐
 │  Add to playlist │────►│ Spotify API  │
 │                  │     │ (playlist)   │
 └────────┬────────┘     └──────────────┘
          │
          ▼
 ┌─────────────────┐
 │  Return results  │───► SSE stream to browser
 │  (playlist URL,  │
 │   track list)    │
 └─────────────────┘
```

---

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Backend | Python + Flask | 3.10+ / Flask ≥3.0 |
| AI | OpenAI API (configurable, default: GPT-4.1-mini) | openai ≥1.0 |
| Spotify | Spotipy (Spotify Web API wrapper) | spotipy ≥2.23 |
| Credential storage | python-dotenv | ≥1.0 |
| Frontend | Vanilla HTML/CSS/JavaScript | No framework |
| Tests | pytest | ≥7.0 |

---

## Running Tests

```bash
cd spotyvibe
python -m pytest tests/ -v
```

All core logic (normalisation, deduplication, feedback recording, utility functions) is covered by unit tests. External API calls (OpenAI, Spotify) are mocked.

