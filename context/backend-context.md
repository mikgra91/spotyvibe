# Backend Context Summary

Generated: 2026-04-03

---

## Architecture

Flask single-page app (`app.py`) orchestrating two external APIs: **OpenAI** (suggestions, profile training, band analysis) and **Spotify Web API** (track search, playlist CRUD, OAuth). All business logic lives in `core/src/`. Configuration and credentials are managed by `config.py`. The frontend is vanilla HTML/CSS/JS served by Flask templates.

---

## Module Map

### `config.py` — Configuration & Credentials

**Storage:** `%LOCALAPPDATA%\spotyvibe\.credentials` (dotenv format). On Android: internal app storage via `SPOTYVIBE_FILES_DIR` env var.

**Key constants:**

| Constant | Default | Purpose |
|---|---|---|
| `BATCH_SIZE` | 10 | Tracks per single GPT request |
| `DEFAULT_PLAYLIST_SIZE` | 10 | Total tracks per generation run |
| `GPT_HISTORY_LIMIT` | 200 | Max history entries sent to GPT |
| `EXHAUSTED_ARTIST_THRESHOLD` | 4 | Tracks before an artist is marked exhausted |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | 3 | All-filtered batches before loop breaks |
| `MAX_GPT_CALLS_PER_RUN` | 20 | Hard cost ceiling per generation |
| `DEFAULT_NEW_ARTIST_PERCENTAGE` | 30 | Min % of suggestions from new artists |
| `DEFAULT_OPENAI_MODEL` | `gpt-4.1-mini` | Fallback model |
| `PROFILE_IMPORT_MAX_BYTES` | 10 MB | Profile import size limit |
| `GENERAL_REQUEST_MAX_BYTES` | 1 MB | General request size limit |
| `MAX_SONG_LIST_SIZE` | 100 | Max songs in persistent song list |

**Key helpers:** `load_config()`, `get_model()`, `get_gpt_language()`, `get_debug_mode()`, `get_playlist_size()`, `get_new_artist_percentage()`, `get_settings()`, `get_credentials()`, `save_credentials()`, `is_onboarding_completed()`, `set_onboarding_completed()`, `set_gpt_language()`.

**File paths (all under `_APP_DIR`):** `CREDENTIALS_FILE` (`.credentials`), `CACHE_FILE` (`.spotify-cache`), `PROFILE_FILE` (`personalized_music_profile.json`), `PROFILE_HISTORY_FILE` (`.history.json`), `DEBUG_LOG_FILE` (`debug.log`).

**Platform detection:** `IS_ANDROID` — `True` when `sys.getandroidapilevel` exists. All Android-specific logic gated behind this flag.

---

### `core/src/openai_http.py` — Direct HTTP Client for OpenAI

Stdlib-only HTTP wrapper (`urllib.request` + `json`) replacing the `openai` SDK. Eliminates Rust transitive dependencies (`jiter`, `pydantic-core`) for Android/Chaquopy compatibility.

**Public functions:**
- `chat_completions_create(model, messages, temperature, response_format)` — POST `/v1/chat/completions`. Validates model against local allowlist before sending.
- `extract_chat_content(response)` — Extracts assistant content string from response dict.
- `list_models()` — GET `/v1/models` (not used by UI; settings uses local allowlist).

**Error hierarchy:** `OpenAIError` base → `OpenAIConfigError`, `OpenAIRequestError` (→ `OpenAIAuthError`, `OpenAIRateLimitError`), `OpenAITimeoutError`, `OpenAIResponseError`, `OpenAIUnsupportedModelError`.

**Retry policy:** Exponential backoff (2s, 4s…) on 429/5xx. 1 retry for chat completions, 2 for list_models. Non-retriable: 400, 401.

**Internal:** `_get_api_key()` reads `OPENAI_API_KEY` from env. `_request_json(method, path, body, retries)` handles all HTTP logic.

---

### `core/src/profile.py` — Taste Profile Management

**Profile lifecycle:**
1. First run → template from `data/music_profile.json` copied to AppData.
2. User fills structured sections (core_description, must_have, soft_preferences, avoid).
3. Two save paths:
   - **Manual save** (`save_profile_sections()`) — writes directly, no AI.
   - **AI training** (`train_profile()`) — sends to GPT, merges result preserving history/feedback.
4. Every save creates `.history.json` backup (copy-on-write with single backup).

**Key functions:**
- `load_profile()` / `save_profile(profile)` — Thread-safe (via `_profile_lock` mutex). Save backs up to `.history.json`.
- `ensure_profile()` — Creates from template if missing.
- `train_profile(sections)` — Builds labelled GPT message with `## CORE DESCRIPTION` etc., temperature 0.3, `json_object` format. Preserves history/feedback from original.
- `save_profile_sections(sections)` — Direct write, splits multi-line fields into arrays.
- `swap_profile_with_history()` — Atomic-ish swap via renames for one-step revert.
- `export_profile_dict()` / `import_profile_dict(imported)` — Export returns dict; import validates schema, sanitizes, deep-merges with template.
- `validate_profile_schema(data)` — Whitelists top-level keys, validates types, enforces length caps. Unknown keys stripped.
- `is_profile_trained()` / `get_profile_status()` — Check `last_updated` field.
- `_deep_merge(dst, src)` — Recursive dict merge for imports.

**Allowed profile keys:** `last_updated`, `meta`, `preferences`, `artists`, `history`, `feedback`, `taste_rules`.

**Validation limits:** Strings max 5000 chars, lists max 100 items, list items max 500 chars.

---

### `core/src/suggestions.py` — GPT Suggestion Engine

The core recommendation logic. Multi-batch generation with deduplication and retry.

**Flow (called from `app.py` `/api/run` loop):**
1. `normalize_history(profile)` — Lowercases, migrates legacy string entries to `{"artist","track"}` dicts, deduplicates.
2. `build_messages(profile, ...)` — Builds system + user message pair:
   - Loads system prompt (model-specific variant if exists, e.g. `system_prompt_gpt-4-1.txt`).
   - Fills placeholders: `{batch_size}`, `{new_artist_percentage}`, `{min_new_artists}`, `{gpt_language}`.
   - Builds consolidated JSON deny set (`_build_deny_set_json()`): forbidden_artists, exhausted_artists, forbidden_tracks, disliked_tracks, retry_forbidden_tracks.
   - Strips exclusion fields from profile copy (deny set is sole source of truth).
   - Injects feedback summary via `build_feedback_summary()`.
   - Injects audio filter constraints via `_format_audio_filters()`.
   - Appends already-accepted tracks on multi-batch runs.
   - Adds diversity hints when history > 50 tracks (rotating by batch_num).
   - Over-requests by +3 to absorb filtering.
3. `call_gpt(messages, temperature)` — Sends to OpenAI, parses JSON, calls `normalize_response()`.
4. `normalize_response(result)` — Force-lowercases names, strips `validation` key, sanitizes GPT annotations from artist names, drops self-excluded placeholder entries.
5. `filter_duplicate_suggestions(profile, result)` — Code-side dedup (defense in depth):
   - Exclusion sources: artists.rejected, feedback.disliked_artists, exhausted artists (≥ threshold), history.suggested_tracks, feedback.disliked_tracks, within-batch duplicates, max 2 per artist per batch.
   - Uses `_normalize_key()` for fuzzy matching (NFKD normalization, strip punctuation, collapse whitespace).
   - Stores removed tracks in `result["_filtered_out"]` for retry context.
   - Recomputes `profile_updates` and `new_artists` code-side (authoritative after truncation).
6. `update_profile(profile, result)` — Appends new artists/tracks to history (set-based dedup, append-only).

**Key helpers:**
- `build_feedback_summary(profile, max_chars=2000)` — Last 10 likes/dislikes formatted as text.
- `_build_deny_set_json(profile, ephemeral_deny_tracks)` — Consolidated JSON exclusion set.
- `_format_audio_filters(audio_filters)` — Converts filter dict to human-readable prompt block.
- `_normalize_key(text)` — NFKD-normalized, lowercase, punctuation-stripped key for fuzzy matching.
- `_migrate_suggested_tracks(profile)` — Converts legacy string entries to `{"artist","track"}` dicts.
- `_strip_gpt_annotation(artist, annotation_words)` — Strips trailing parenthetical GPT meta-commentary.

---

### `core/src/playlist.py` — Spotify Integration

All Spotify Web API interactions via `spotipy`.

**OAuth:**
- `get_spotify_oauth()` — Creates `SpotifyOAuth` with `playlist-modify-private playlist-read-private` scope. Token cached in AppData. Redirect URI: `spotyvibe://callback` (Android) or `http://127.0.0.1:5000/callback` (desktop).
- `get_spotify_client()` — Authenticated client from cached token.
- `get_spotify_auth_status()` — Three-state: `not_configured` / `not_authenticated` / `authenticated`. Validates token with live `current_user()` call.
- `get_spotify_auth_url()` / `handle_spotify_callback(code)` / `disconnect_spotify()` — OAuth lifecycle.

**Track search:**
- `search_tracks(tracks, on_progress)` — Parallel search via `ThreadPoolExecutor(max_workers=10)`. Each worker gets own `spotipy.Spotify` client. Returns `(found, not_found)`. Found tracks enriched with `uri`, `track_id`, `cover_url`, `preview_url`, `spotify_url`, `album_url`, `artist_url`.
- `_build_track_artist_query(artist, track)` — Builds `track:"..." artist:"..."` query.
- `_sanitize_spotify_search_value(value)` — Strips control chars, quotes, backslashes.

**Playlist management:**
- `add_to_playlist(verified_tracks, mode, playlist_id, playlist_name, profile)` — Four modes: `default` (find/create "SpotyVibe Playlist"), `create` (always new), `append` (skip duplicates), `replace` (clear then add). Catches 403 → auto-disconnects + raises RuntimeError.
- `find_existing_playlist(sp)` — Paginates user playlists to find by name.
- `get_existing_track_uris(sp, playlist_id)` — Loads all URIs from playlist.
- `remove_from_playlist(artist, track)` — Search + remove from playlist.
- `get_user_playlists()` — Returns `[{"id", "name", "track_count"}]`.
- `_render_playlist_name(name_template, profile)` — Replaces `{date}`, `{style}` tokens.

**API compatibility (Feb 2026):** Uses `current_user_playlist_create()`, `sp.playlist_items()` (not removed `sp.playlist_tracks()`). Search `limit=1`.

---

### `core/src/feedback.py` — Like/Dislike Recording

**Two-tier rejection model:**
- `like_track(artist, track, reason)` — Adds to `feedback.liked_tracks`, adds artist to `artists.confirmed`.
- `dislike_track(artist, track, reason)` — With track: track-level dislike only (artist NOT rejected). Without track: artist added to `artists.rejected` (full exclusion).

All inputs sanitized via `sanitize_text()`.

---

### `core/src/analysis.py` — Band/Song AI Analysis

- `analyze_band_song(artist, track="")` — Sends to GPT via `analysis_prompt.txt`, temperature 0.3, `json_object` format. Returns structured JSON: `artist`, `track`, `genre[]`, `style_tags[]`, `characteristics{}`, `audio_features{}` (GPT-estimated 0–1 scale + tempo BPM), `profile_suggestions[]`. Prompt uses `{gpt_language}` placeholder.

---

### `core/src/history.py` — Run History & Undo

- `save_run(run_id, playlist_id, playlist_url, tracks)` — Appends to `run_history.json`, capped at 5 entries.
- `load_runs()` — Returns all runs newest-first.
- `undo_last_run(sp)` — Removes tracks via `sp.playlist_remove_all_occurrences_of_items()`, deletes entry.

Storage: `run_history.json` in AppData.

---

### `core/src/utils.py` — Shared Utilities

- `debug_log(label, messages, response_content)` — Appends timestamped GPT I/O to debug log (only when debug mode enabled).
- `clear_debug_log()` — Deletes debug log file.
- `strip_code_fences(text)` — Removes markdown ````json...```` fences.
- `sanitize_text(text)` — Removes null bytes, control chars, normalizes whitespace.
- `sanitize_profile(profile)` — Recursive `sanitize_text()` on all string values.
- `get_openai_models()` — Returns model list from curated allowlist (no API call). Appends configured model if not in list (marked unsupported).

---

### `core/src/spotify_metadata.py` — Spotify Metadata Lookup

Client Credentials flow (no user OAuth needed). Uses stdlib `urllib` directly (no spotipy).

- `get_client_credentials_token()` — Thread-safe cached token with 60s early expiry.
- `spotify_api_request(path, token, params)` — Generic GET with 429 retry.
- `analyze_metadata(artist, track, market)` — Main entry: searches for track/artist, scores candidates, returns canonical response dict with match confidence, track/artist metadata.
- `search_track_candidates()` / `search_artist_candidates()` — Fielded search helpers.
- `score_track_candidate()` / `score_artist_candidate()` — Scoring: +0.6 track name match, +0.3 artist match / +1.0 exact artist match.
- `normalize_compare_text()` / `strip_version_suffixes()` — Text normalization for matching.

**Note:** UI feature removed (Spotify Feb 2026 changes removed `popularity`, `followers`, `audio_features`). Module exists but no endpoint exposes it.

---

## `app.py` — Flask Server & API

**Endpoints summary (31 routes):**

| Category | Endpoints |
|---|---|
| **Page** | `GET /` (index), `GET /onboarding` |
| **Generation** | `POST /api/run` (SSE stream), `POST /api/cancel`, `GET /api/run/<run_id>/status` |
| **Profile** | `GET /api/profile/status`, `GET /api/profile/data`, `GET /api/profile/export`, `POST /api/profile/import`, `POST /api/profile/reset-to-history`, `POST /api/train-profile`, `POST /api/save-profile` |
| **Feedback** | `POST /api/feedback`, `POST /api/remove` |
| **Analysis** | `POST /api/analyze` |
| **Song List** | `GET /api/songlist`, `POST /api/songlist`, `DELETE /api/songlist/track` |
| **Spotify Auth** | `GET /api/spotify/status`, `GET /api/spotify/auth`, `POST /api/spotify/disconnect`, `GET /callback` |
| **Settings** | `GET /api/settings`, `POST /api/settings`, `GET /api/settings/credentials`, `POST /api/settings/credentials`, `GET /api/settings/models`, `DELETE /api/settings/debug-log` |
| **Playlists** | `GET /api/playlists` |
| **History** | `GET /api/runs`, `POST /api/runs/undo` |
| **Onboarding** | `GET /api/onboarding/status`, `POST /api/onboarding/complete` |
| **Help** | `GET /api/help`, `GET /api/help/section/<anchor>` |
| **Settings (lang)** | Language set via `POST /api/settings` (`gpt_language` field) |

**Generation pipeline (`/api/run`):**

1. Validates profile trained + Spotify connected.
2. Loops until `playlist_size` reached or exhaustion/cancellation:
   - Check cancel event → build messages → call GPT (increment `gpt_call_count`) → check cancel again → filter duplicates → search Spotify (parallel) → update history → save profile → yield SSE events.
3. Adaptive temperature: starts at 0.7, decreases by 0.2 per consecutive empty batch (min 0.3).
4. Two-pass mode: when history > 150, boosts new-artist percentage by +40 (capped at 95) after half the playlist is filled.
5. On completion: adds to Spotify playlist, saves run history, appends to persistent song list, yields `result` SSE event.

**Cancellation:** `run_id` → `threading.Event` in `_runs` dict. Two modes: `finalize: false` (discard), `finalize: true` (create playlist with what's found). Stale runs swept after 600s.

**SSE event types:** `progress`, `batch_verified`, `result`, `cancelled`, `error`.

**Song list persistence:** `songlist.json` in AppData, max `MAX_SONG_LIST_SIZE` entries. CRUD via `/api/songlist` endpoints.

---

## Data Storage

All runtime data lives in `%LOCALAPPDATA%\spotyvibe\` (desktop) or app internal storage (Android):

| File | Content |
|---|---|
| `.credentials` | API keys, model, settings (dotenv format) |
| `.spotify-cache` | Spotify OAuth token (managed by spotipy) |
| `personalized_music_profile.json` | Active taste profile |
| `personalized_music_profile.history.json` | Previous profile (one-step undo) |
| `debug.log` | GPT request/response log (desktop only, when debug enabled) |
| `run_history.json` | Last 5 generation runs |
| `songlist.json` | Persistent song list (max 100) |

---

## Security Measures

- Input sanitization at every entry point (`sanitize_text()`, `sanitize_profile()`).
- Request size limits (1 MB general, 10 MB profile import).
- Per-field character caps.
- Profile schema validation with key whitelisting.
- Prompt injection hardening (untrusted data warnings in system prompts).
- Spotify search query sanitization.
- Credentials stored outside project directory, masked in API responses.
- Android WebView: downloads restricted to profile export URL only.

---

## Thread Safety

- `_profile_lock` (threading.Lock) guards all profile read-modify-write cycles.
- `_runs_lock` guards the active runs dict.
- `_token_lock` guards the Spotify client credentials token cache.
- Each Spotify search worker gets its own `spotipy.Spotify` client (share-nothing).

---

## Prompt Files

| File | Used by | Key placeholders |
|---|---|---|
| `system_prompt.txt` | suggestions.py | `{batch_size}`, `{new_artist_percentage}`, `{min_new_artists}`, `{gpt_language}` |
| `prompt_template.txt` | suggestions.py | `{profile_json}`, `{deny_set_json}`, `{batch_size}`, `{recent_feedback}`, `{audio_filters_block}` |
| `profile_training_prompt.txt` | profile.py | `{gpt_language}` |
| `analysis_prompt.txt` | analysis.py | `{gpt_language}` |

Model-specific system prompts supported: `system_prompt_{model-slug}.txt` (e.g. `system_prompt_gpt-4-1.txt`).
