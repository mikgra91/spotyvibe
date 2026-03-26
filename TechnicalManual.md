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
| `BATCH_SIZE` | Number of tracks GPT generates per single request (default: 10). |
| `DEFAULT_PLAYLIST_SIZE` | Default total tracks per generation run (default: 10). |
| `DEFAULT_NEW_ARTIST_PERCENTAGE` | Default minimum percentage of suggestions from artists not yet in history (default: 30). |
| `GPT_HISTORY_LIMIT` | Max history entries sent to GPT to bound token usage (default: 200). |
| `EXHAUSTED_ARTIST_THRESHOLD` | An artist with this many tracks in history is marked [EXHAUSTED] in the exclusion block (default: 4). |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | How many consecutive all-filtered batches are allowed before the loop breaks and the playlist is created with whatever was found (default: 3). |
| `DEFAULT_OPENAI_MODEL` | Fallback model when none is configured (default: `gpt-4.1-mini`). |
| `CREDENTIALS_FILE` | Path to `%LOCALAPPDATA%\spotyvibe\.credentials`. |
| `PROFILE_FILE` | Path to the personalised taste profile in AppData. |
| `CACHE_FILE` | Path to the cached Spotify OAuth token. |
| `DEBUG_LOG_FILE` | Path to the debug log file (`%LOCALAPPDATA%\spotyvibe\debug.log`). |

**Key helpers:**

- **`get_model()`** — Returns the user's configured `OPENAI_MODEL` from the credentials file, falling back to `DEFAULT_OPENAI_MODEL`.
- **`get_debug_mode()`** — Returns `True` if the `DEBUG_MODE` setting is enabled.
- **`get_playlist_size()`** — Returns the configured playlist size (minimum `BATCH_SIZE`).
- **`get_new_artist_percentage()`** — Returns the configured new-artist percentage, clamped to 1–100, falling back to `DEFAULT_NEW_ARTIST_PERCENTAGE`.
- **`get_settings()`** — Returns a dict of non-secret settings (model name, debug mode flag, playlist size, new artist percentage) for the Settings UI.

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
| POST | `/api/run` | Runs the full generation pipeline. Returns an **SSE stream** with progress events. Accepts optional JSON body `{"run_id": "..."}`. |
| POST | `/api/cancel` | Cancels an active generation run by `run_id`. Accepts `{"run_id": "...", "finalize": bool}`. When `finalize` is `true`, the playlist is created with however many tracks have been verified so far. |
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
| GET | `/api/settings` | Returns non-secret settings (model, debug mode, playlist size, new artist percentage). |
| POST | `/api/settings` | Updates non-secret settings (model, debug mode, playlist size, new artist percentage). |
| GET | `/api/settings/models` | Returns available OpenAI chat models and the currently selected one. |
| DELETE | `/api/settings/debug-log` | Clears the debug log file. |
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
- **Train Taste Profile** — text area for describing music taste. Shows an inline warning and disables inputs if the OpenAI API key is missing.
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

**Debug mode:** When enabled via the Settings modal, all GPT interactions (both suggestion generation and profile training) are logged to `%LOCALAPPDATA%\spotyvibe\debug.log` via the `debug_log()` utility. Each log entry includes a timestamp, the full message array sent to GPT, and the raw response content.

---

### Prompt Files

The AI's behaviour is controlled by text files in the `prompts/` directory. These can be edited without touching any Python code.

| File | Used by | Purpose |
|---|---|---|
| `system_prompt.txt` | `suggestions.py` | Defines all rules for music recommendation. Contains: profile section guide, **Bear Ghost primary-reference section**, exclusion rules, discovery rules, **hard negative disqualification rules**, selection criteria, self-verification checklist, and the output JSON schema (including the `validation` block). |
| `prompt_template.txt` | `suggestions.py` | Template for the user message. Embeds the profile JSON via `{profile_json}` and the exclusion block via `{exclusion_block}`. |
| `profile_training_prompt.txt` | `profile.py` | System message for the taste profile training. Defines which fields to fill and which to preserve. |

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

