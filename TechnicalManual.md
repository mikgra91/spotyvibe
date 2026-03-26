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
│  /api/profile/status  /api/spotify/status   /api/remove            │
│  /api/spotify/auth    /api/spotify/disconnect                      │
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
├── templates/              # Flask templates
│   └── index.html          # Single-page web UI (HTML + CSS + JS)
│
└── tests/                  # Automated tests
    ├── conftest.py         # Pytest configuration
    ├── test_utils.py       # Tests for shared utilities
    ├── test_suggestions.py # Tests for suggestion logic
    └── test_feedback.py    # Tests for feedback recording
```

---

## Component Details

### `config.py` — Configuration & Credentials

Manages all application settings and credentials.

**Key constants:**

| Constant | Purpose |
|---|---|
| `BASE_DIR` | Absolute path to the `spotyvibe/` directory. All file paths are resolved from here. |
| `TARGET_COUNT` | Number of tracks per generation run (default: 30). |
| `GPT_HISTORY_LIMIT` | Max history entries sent to GPT to bound token usage (default: 200). |
| `DEFAULT_OPENAI_MODEL` | Fallback model when none is configured (default: `gpt-4.1-mini`). |
| `CREDENTIALS_FILE` | Path to `%LOCALAPPDATA%\spotyvibe\.credentials`. |
| `PROFILE_FILE` | Path to the personalised taste profile in AppData. |
| `CACHE_FILE` | Path to the cached Spotify OAuth token. |
| `DEBUG_LOG_FILE` | Path to the debug log file (`%LOCALAPPDATA%\spotyvibe\debug.log`). |

**Key helpers:**

- **`get_model()`** — Returns the user's configured `OPENAI_MODEL` from the credentials file, falling back to `DEFAULT_OPENAI_MODEL`.
- **`get_debug_mode()`** — Returns `True` if the `DEBUG_MODE` setting is enabled.
- **`get_settings()`** — Returns a dict of non-secret settings (model name, debug mode flag) for the Settings UI.

**Credential storage:** Credentials and settings (including the selected model) are stored in `%LOCALAPPDATA%\spotyvibe\.credentials` as a dotenv file, outside the project directory. The `load_config()` function loads them into `os.environ`. The `save_credentials()` function ensures the file always ends with a newline before appending new keys, preventing `python-dotenv` parse errors from concatenated lines.

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
2. The user describes their taste in the UI → `train_profile()` sends the description + current profile to GPT.
3. GPT returns an updated profile JSON. History and feedback sections are preserved server-side (GPT's version is discarded for these sections).
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
   - Embeds a **truncated** copy of the profile (history capped at `GPT_HISTORY_LIMIT` entries).
   - On retries, appends an addendum listing already-accepted tracks.
3. `call_gpt()` — Sends messages to GPT and parses the JSON response.
4. `normalize_response()` — Force-lowercases all artist/track names.
5. `filter_duplicate_suggestions()` — Code-side dedup against full history + disliked tracks (uses fuzzy matching via `_normalize_key()`).
6. `update_profile()` — Merges new suggestions into the profile's history.

**GPT interaction for suggestions:**
- Model: Configurable via Settings (default: `gpt-4.1-mini`)
- Temperature: `0.7` (higher creativity for diverse suggestions)
- Response format: `json_object`

**Deduplication strategy:** GPT is instructed to avoid duplicates, but compliance is not guaranteed. `filter_duplicate_suggestions()` applies a second pass using fuzzy key normalisation (lowercase, strip punctuation, collapse whitespace) to catch any duplicates GPT missed.

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

**Parallelised search:** `search_tracks()` uses `ThreadPoolExecutor` with 10 workers to verify tracks on Spotify concurrently, reducing the search time from ~15s (sequential) to ~2s for 30 tracks.

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
| POST | `/api/run` | Runs the full generation pipeline. Returns an **SSE stream** with progress events. |
| POST | `/api/feedback` | Records a like or dislike. Dislikes also remove the track from Spotify. |
| POST | `/api/remove` | Removes a track from Spotify without recording feedback. |
| GET | `/api/profile/status` | Returns whether the profile is trained and when. |
| POST | `/api/train-profile` | Sends a taste description to GPT and updates the profile. |
| GET | `/api/spotify/status` | Returns Spotify auth status (`not_configured`, `not_authenticated`, `authenticated`). Validates the token with a live API call. |
| GET | `/api/spotify/auth` | Redirects to Spotify's authorisation page. |
| POST | `/api/spotify/disconnect` | Clears the cached Spotify token to force re-authentication. |
| GET | `/callback` | Handles the OAuth callback from Spotify. |
| GET | `/api/settings/credentials` | Returns masked credential values. |
| POST | `/api/settings/credentials` | Updates credentials. Ensures trailing newline to prevent dotenv parse errors. |
| GET | `/api/settings` | Returns non-secret settings (model, debug mode). |
| POST | `/api/settings` | Updates non-secret settings (model, debug mode). |
| GET | `/api/settings/models` | Returns available OpenAI chat models and the currently selected one. |
| DELETE | `/api/settings/debug-log` | Clears the debug log file. |
| GET | `/api/help` | Returns the User Manual content as rendered HTML. |

**SSE streaming (`/api/run`):**
The generation pipeline returns a `text/event-stream` response. Each event is a JSON line with a `type` field:
- `progress` — status update (e.g., "Attempt 1/3: Asking GPT for suggestions…")
- `result` — final result with playlist data, Spotify URL, and stats
- `error` — error message

The frontend reads the stream via `fetch` + `ReadableStream` and updates the UI in real time.

---

### `templates/index.html` — Web UI

A self-contained single-page application (HTML + CSS + vanilla JavaScript, no framework). Communicates with the Flask backend via `fetch` API calls.

**Layout:** The UI is divided into two labelled sections with subheaders and short descriptions:
- **Step 1 — Taste Profile:** Train the AI on your music preferences.
- **Step 2 — Generate Playlist:** Create a Spotify playlist from the trained profile.

Both sections are wrapped in styled cards (`.train-section` and `.generate-section`) for visual consistency.

**Key UI components:**
- **Train Taste Profile** — text area for describing music taste. Shows an inline warning and disables inputs if the OpenAI API key is missing.
- **Generate button** — triggers the pipeline with live progress updates. Shows an inline warning and disables the button if OpenAI key or Spotify credentials/authentication are missing.
- **Track list** — displays suggestions with album cover thumbnails (48×48px, sourced from Spotify), like/dislike/remove actions.
- **Feedback form** — expandable per-track form with artist, track, and reason fields.
- **Gear dropdown menu** — Credentials, Settings, Disconnect Spotify (visible only when connected), and Help.
- **Credentials modal** (`🔑 Credentials`) — manages API keys (OpenAI, Spotify). Secrets only.
- **Settings modal** (`⚙️ Settings`) — model selection ("Used Model" dropdown) and debug mode toggle. Non-secret configuration.
- **Help modal** — loads the User Manual content from `/api/help`.
- **Toast notifications** — brief confirmation messages after feedback/remove actions.

**Debug mode:** When enabled via the Settings modal, all GPT interactions (both suggestion generation and profile training) are logged to `%LOCALAPPDATA%\spotyvibe\debug.log` via the `debug_log()` utility. Each log entry includes a timestamp, the full message array sent to GPT, and the raw response content.

---

### Prompt Files

The AI's behaviour is controlled by text files in the `prompts/` directory. These can be edited without touching any Python code.

| File | Used by | Purpose |
|---|---|---|
| `system_prompt.txt` | `suggestions.py` | Defines all rules for music recommendation: how to read the profile, matching/exclusion logic, diversity requirements, and the output JSON schema. |
| `prompt_template.txt` | `suggestions.py` | Template for the user message. Embeds the profile JSON via `{profile_json}`. |
| `profile_training_prompt.txt` | `profile.py` | System message for the taste profile training. Defines which fields to fill and which to preserve. |

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
          │ 30 suggestions
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

