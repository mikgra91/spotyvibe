# Learning Guide: The `core/` Module

This document explains **why** the `core/` module is implemented the way it is, what technologies and patterns are used, and what options they open up for future development.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Breakdown](#module-breakdown)
   - [utils.py — Shared Utilities](#utilspy--shared-utilities)
   - [profile.py — Profile Management](#profilepy--profile-management)
   - [suggestions.py — GPT Suggestion Engine](#suggestionspy--gpt-suggestion-engine)
   - [playlist.py — Spotify Integration & OAuth](#playlistpy--spotify-integration--oauth)
   - [feedback.py — Like / Dislike System](#feedbackpy--like--dislike-system)
3. [Technology Deep-Dives](#technology-deep-dives)
   - [OpenAI Python SDK (v1.x)](#openai-python-sdk-v1x)
   - [Spotipy & Spotify Web API](#spotipy--spotify-web-api)
   - [OAuth 2.0 Authorization Code Flow](#oauth-20-authorization-code-flow)
   - [python-dotenv for Credential Management](#python-dotenv-for-credential-management)
   - [Threading with concurrent.futures](#threading-with-concurrentfutures)
   - [JSON as a Document Store](#json-as-a-document-store)
4. [Design Patterns Used](#design-patterns-used)
5. [What This Architecture Enables](#what-this-architecture-enables)
6. [Alternatives Considered](#alternatives-considered)

---

## Architecture Overview

The `core/` package follows a **layered, single-responsibility design**:

```
core/
├── utils.py         → Shared infrastructure (OpenAI client, debug logging)
├── profile.py       → Profile CRUD + AI-powered training
├── suggestions.py   → GPT prompt assembly, dedup, retry logic
├── playlist.py      → Spotify OAuth, search, playlist management
└── feedback.py      → Like/dislike recording
```

Each module owns a single domain. Dependencies flow **downward** (specific → general):

```
feedback.py  →  profile.py  →  utils.py
suggestions.py  →  utils.py
playlist.py  (independent — talks to Spotify, not GPT)
```

**Why this separation matters:**
- You can modify the suggestion engine without touching Spotify code.
- Feedback recording is decoupled from suggestion generation — feedback writes data, suggestions read it.
- The Flask routes in `app.py` act as a thin orchestration layer that calls into these modules.

---

## Module Breakdown

### `utils.py` — Shared Utilities

**Purpose:** Provides the OpenAI client singleton, debug logging, and text-cleaning helpers.

#### Key Decisions

| Decision | Why |
|---|---|
| **Lazy singleton for OpenAI client** | Creating an `OpenAI()` client spins up an `httpx.Client` with connection pooling. Reusing it avoids repeated TLS handshakes. The client is recreated automatically if the API key changes at runtime. |
| **Key-change detection** | The Settings UI lets users update their API key without restarting the app. The singleton compares the current `os.environ` value to the cached key and rebuilds the client if they differ. |
| **File-append debug logging** | Standard Python `logging` is designed for operational log levels (INFO, WARNING, ERROR). The debug log here captures full GPT prompt/response pairs — structured I/O that doesn't fit conventional log levels. A simple append-to-file approach keeps it straightforward. |
| **`strip_code_fences()` helper** | Even with `response_format={"type": "json_object"}`, some models occasionally wrap output in markdown fences. Stripping them defensively avoids `json.loads()` failures. |

#### What This Enables

- **Hot credential rotation:** Change your OpenAI key in the UI and the next API call uses the new key — no restart needed.
- **Full GPT I/O tracing:** Enable debug mode to see exactly what prompts were sent and what GPT returned, invaluable for prompt engineering.
- **Model listing:** `get_openai_models()` dynamically queries the OpenAI API, so new model releases appear in the Settings UI without code changes.

---

### `profile.py` — Profile Management

**Purpose:** Loads, saves, and trains the user's music taste profile (a JSON document).

#### Key Decisions

| Decision | Why |
|---|---|
| **JSON file as storage** | A single-user desktop app doesn't need a database. A JSON file is human-readable, editable, and portable. The profile is essentially a NoSQL document — a single nested object with arrays and key-value pairs. |
| **Single-file backup (`shutil.copy2`)** | Before each save, the current profile is copied to a `.history.json` file. This gives a one-level undo. More complex versioning (git-like history, append-only log) was considered unnecessary for infrequent writes. |
| **Dual save paths (manual vs AI)** | `save_profile_sections()` writes the user's input directly — zero API cost, instant. `train_profile()` sends the input to GPT for intelligent refinement — slower, costs tokens, but produces more nuanced profiles. Users choose which path to take. |
| **`response_format={"type": "json_object"}`** | OpenAI's Structured Outputs mode. Forces the model to return valid JSON, eliminating the need for brittle regex-based parsing or retry-on-parse-failure loops. |
| **Temperature 0.3 for training** | Low temperature = less creativity = more faithful to user input. Profile training should represent what the user said, not hallucinate preferences. Compare with 0.7 used in suggestions where creativity is desirable. |
| **Safety merge for history/feedback** | After GPT returns the updated profile, the code force-restores the `history` and `feedback` sections from the original. GPT might accidentally modify or drop these sections — this safety net prevents data loss. |

#### What This Enables

- **Portable profiles:** The JSON file can be backed up, shared, or version-controlled independently.
- **Manual control:** Users who don't want AI involvement can edit their profile directly.
- **Progressive refinement:** Each training session builds on the previous profile — GPT sees the existing data and merges new input.

---

### `suggestions.py` — GPT Suggestion Engine

**Purpose:** Assembles GPT prompts, calls the API, deduplicates results, and manages multi-batch retry logic.

This is the most complex module and the heart of the application.

#### Key Decisions

| Decision | Why |
|---|---|
| **Prompt template files** | System and user prompts live in `prompts/` as plain text with `{placeholder}` variables. Prompt engineers can iterate on wording without touching Python code. This is a production best practice for LLM applications. |
| **Grouped exclusion block** | Early versions sent a flat JSON array of `"artist track"` strings. GPT frequently failed to match entries. The current format groups tracks by artist with bullet points — LLMs parse structured text much better than deeply nested JSON for set-membership checks. |
| **EXHAUSTED artist threshold** | When an artist has ≥4 tracks in history, they are marked `[EXHAUSTED]` in the exclusion block. This pushes GPT toward discovering new artists rather than exhausting the same few. |
| **Code-side dedup filter** | GPT cannot be trusted to never repeat tracks. `filter_duplicate_suggestions()` is a deterministic Python filter that catches any duplicates the model misses. This is **defence in depth** — the prompt tries to prevent duplicates, and the code guarantees it. |
| **Fuzzy key normalisation** | `_normalize_key()` strips punctuation and collapses whitespace (`"Don't Stop Me Now"` → `"dont stop me now"`). This catches near-duplicates that exact string matching would miss. |
| **Adaptive retry with escalating warnings** | When an entire batch is filtered out (all duplicates), the retry prompt includes the specific tracks that failed, with increasingly stern language. This is an LLM prompt-engineering technique called "iterative correction" — it works because GPT responds to explicit negative examples. |
| **`_filtered_out` internal key** | Tracks removed by the dedup filter are preserved in the result dict so the caller (the retry loop in `app.py`) can feed them back to GPT. This key is stripped before returning results to the UI. |
| **`normalize_response()`** | Lowercases all artist/track names in GPT's output immediately, so all downstream comparisons are case-insensitive without repeated `.lower()` calls scattered through the code. |

#### The Suggestion Pipeline

```
1. Load profile → normalize history
2. Build system prompt (from file + placeholders)
3. Build user prompt (profile JSON + exclusion block + batch size)
4. Call GPT → parse JSON response
5. Normalize response (lowercase everything)
6. Filter duplicates (code-side safety net)
7. If all filtered → retry with escalating warning (up to MAX_CONSECUTIVE_EMPTY_BATCHES)
8. Update profile history with accepted tracks
9. Return results to caller
```

#### What This Enables

- **Prompt iteration without deployments:** Change `prompts/system_prompt.txt` and restart — no code changes needed.
- **Configurable batch sizes and artist diversity:** The `new_artist_percentage` parameter and `BATCH_SIZE` config let users tune the discovery vs. familiarity balance.
- **Reliable dedup at scale:** Even with thousands of tracks in history, the code-side filter guarantees no repeats.

---

### `playlist.py` — Spotify Integration & OAuth

**Purpose:** Manages Spotify OAuth flow, track searching, and playlist creation/modification.

#### Key Decisions

| Decision | Why |
|---|---|
| **Authorization Code Flow** (not Client Credentials) | The app needs to create playlists in the user's account and read their private playlists. This requires user-level permissions, which only the Authorization Code Flow provides. Client Credentials only access public data. |
| **Minimal OAuth scopes** | `playlist-modify-private playlist-read-private` — only the permissions actually needed. This is the principle of least privilege, a security best practice. Users see exactly what the app can do when they authorise. |
| **Token caching in AppData** | The OAuth token (access + refresh) is cached to `.spotify-cache` in AppData. On subsequent runs, the cached token is reused and auto-refreshed when expired, so users don't have to re-login every time. |
| **`open_browser=False`** | The app controls when/how the auth browser opens via the UI (returning a URL to the frontend), rather than letting spotipy auto-launch a browser — which wouldn't work in a web-app context. |
| **ThreadPoolExecutor for search** | Track searching is I/O-bound (network requests to Spotify). Threading achieves near-linear speedup for batch sizes of 10–30. Each thread creates its own `spotipy.Spotify` client because `requests.Session` is NOT thread-safe. |
| **10 worker threads** | Practical sweet spot — saturates the network for typical batches without hitting Spotify's rate limits (~30 req/sec). |
| **Idempotent playlist additions** | Before adding, the code checks which URIs are already in the playlist. Calling `add_to_playlist()` multiple times with the same tracks doesn't create duplicates. |
| **`current_user_playlist_create()`** | Uses the modern `POST /me/playlists` endpoint, not the deprecated `POST /users/{user_id}/playlists`. This is forward-compatible with Spotify API changes. |
| **403 recovery** | On a 403 Forbidden, the token cache is cleared and a descriptive error guides the user to re-authenticate. This handles token revocation, expired sessions, and scope changes gracefully. |
| **Platform-aware redirect URI** | Desktop uses `http://127.0.0.1:5000/callback` (local HTTP server). Android uses `spotyvibe://callback` (custom URI scheme / deep link). The `IS_ANDROID` flag from config switches automatically. |

#### What This Enables

- **One-click Spotify connection:** Users authorise once, and the cached token handles everything after that — including automatic refresh.
- **Fast batch search:** 10 tracks are searched in ~1 second (parallel) instead of ~5 seconds (sequential).
- **Progress reporting:** The `on_progress` callback lets the UI show a real-time progress bar during search.
- **Cross-platform:** The same module works on desktop (Flask redirect) and Android (deep link) without code changes.

---

### `feedback.py` — Like / Dislike System

**Purpose:** Records user feedback (likes and dislikes) into the profile.

#### Key Decisions

| Decision | Why |
|---|---|
| **Append-only feedback** | Likes and dislikes are appended, never deleted. This creates a growing signal that improves both GPT prompts (which include feedback context) and code-side filtering (which excludes disliked tracks). |
| **Two-tier rejection** | Track-level dislike records only the track. Artist-level dislike adds the artist to `artists.rejected` (a hard exclusion). This prevents over-filtering — you can dislike one song without losing an entire artist. |
| **Optional `reason` field** | Capturing WHY the user liked/disliked something gives GPT richer context. "Too slow" teaches GPT about tempo preferences; "wrong genre" teaches about genre boundaries. |
| **Artist confirmation on like** | Liking a track automatically adds the artist to `artists.confirmed`, strengthening it as a reference for future suggestions. |
| **Separate module** | Feedback recording is in its own module (not in `suggestions.py`) because it's a write-only operation. The suggestion engine is read-only with respect to the profile. This follows the Single Responsibility Principle. |

#### What This Enables

- **Learning from feedback:** Each like/dislike makes future suggestions more accurate.
- **Granular control:** Users control whether a dislike targets a track or an entire artist.
- **Transparent training data:** The feedback is stored in plain JSON, visible and editable.

---

## Technology Deep-Dives

### OpenAI Python SDK (v1.x)

The project uses `openai>=1.0,<3.0` — the modern, class-based SDK.

**Key features used:**
- `OpenAI(api_key=...)` — Resource-based client (replaced the old `openai.api_key` global).
- `client.chat.completions.create()` — Chat Completions API for multi-turn conversations.
- `client.models.list()` — Lists available models for the Settings UI.
- `response_format={"type": "json_object"}` — Structured Outputs (forces valid JSON output).
- `temperature` parameter — Controls randomness (0.3 for training, 0.7 for suggestions).

**Why v1.x matters:** The v1.0 rewrite introduced proper typing, async support, automatic retries, and streaming — all available for future enhancements without changing the SDK.

### Spotipy & Spotify Web API

The project uses `spotipy>=2.23,<3.0`.

**Key methods used:**
| Method | Spotify API Endpoint | Purpose |
|---|---|---|
| `current_user_playlists()` | `GET /me/playlists` | List user's playlists |
| `current_user_playlist_create()` | `POST /me/playlists` | Create a new playlist |
| `playlist_tracks()` | `GET /playlists/{id}/tracks` | Get tracks in a playlist |
| `playlist_add_items()` | `POST /playlists/{id}/tracks` | Add tracks to playlist |
| `playlist_remove_all_occurrences_of_items()` | `DELETE /playlists/{id}/tracks` | Remove a track |
| `search()` | `GET /search` | Search for tracks by name/artist |
| `current_user()` | `GET /me` | Validate authentication |

### OAuth 2.0 Authorization Code Flow

```
User clicks "Connect"
        │
        ▼
App generates auth URL → Browser opens Spotify login
        │
        ▼
User grants permission → Spotify redirects to /callback with ?code=...
        │
        ▼
App exchanges code for access_token + refresh_token
        │
        ▼
Tokens cached to .spotify-cache → auto-refreshed on expiry
```

**Scopes requested:** `playlist-modify-private`, `playlist-read-private`

### python-dotenv for Credential Management

Credentials live in `%LOCALAPPDATA%\spotyvibe\.credentials` (dotenv format).

**Why dotenv?**
- Human-readable key=value format.
- `load_dotenv()` injects values into `os.environ`, making them available to any module via `os.getenv()` — the standard twelve-factor-app approach.
- `set_key()` updates individual values without rewriting the entire file.
- The credentials file lives outside the project directory, so it's never accidentally committed to git.

### Threading with `concurrent.futures`

```python
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(search_one, t): t for t in tracks}
    for future in as_completed(futures):
        result_type, result_data = future.result()
```

**Why `ThreadPoolExecutor` (not `asyncio` or `multiprocessing`)?**
- The workload is **I/O-bound** (HTTP requests to Spotify), not CPU-bound.
- Threads are simpler than async — no need to rewrite the entire call stack with `async`/`await`.
- `concurrent.futures` provides a clean, high-level API with `submit()` and `as_completed()`.
- Each thread gets its own spotipy client (share-nothing), avoiding thread-safety issues.

### JSON as a Document Store

The profile is a single JSON file that acts like a NoSQL document.

**Advantages for this project:**
- No database engine to install or manage.
- Human-readable and hand-editable.
- Portable — copy the file to move your profile.
- Natural fit for the nested, schema-flexible data structure (preferences, history, feedback).

**Trade-offs accepted:**
- No concurrent write safety (acceptable — single user).
- No transactions (acceptable — writes are infrequent).
- Entire file is read/written on every operation (acceptable — file is small, typically <100KB).

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Lazy Singleton** | `utils.py` → OpenAI client | Avoid repeated client creation; support runtime key rotation. |
| **Template Method** | `prompts/*.txt` files | Prompts are templates with `{placeholders}` filled at runtime — separates content from logic. |
| **Defence in Depth** | `suggestions.py` dedup | GPT is told to avoid repeats (prompt layer) AND a code filter catches misses (code layer). |
| **Copy-on-Write** | `profile.py` → `save_profile()` | Backup before overwrite provides simple undo without complex versioning. |
| **Share-Nothing Threading** | `playlist.py` → `search_tracks()` | Each thread owns its HTTP client — no shared mutable state, no locks. |
| **Strategy / Dual Path** | `profile.py` → manual vs AI save | Two save strategies (direct write vs GPT-powered) selectable by the user. |
| **Append-Only Log** | `feedback.py` | Feedback is only added, never deleted — growing training signal for future suggestions. |
| **Iterative Correction** | `suggestions.py` → retry logic | Failed batches trigger progressively stronger prompts, correcting GPT's behaviour. |

---

## What This Architecture Enables

Because of the choices made in the `core/` module, the following features and extensions are possible:

1. **Swap the AI provider:** The OpenAI client is isolated in `utils.py`. Replacing it with Anthropic, Google Gemini, or a local model only requires changing that module — everything else talks through `get_openai_client()` and `call_gpt()`.

2. **Add streaming responses:** The OpenAI SDK v1.x supports `stream=True`. Adding real-time token streaming to the UI would only require changes to `call_gpt()` and the Flask route.

3. **Multi-user support:** Replace the JSON file store with a database (SQLite, PostgreSQL), and the profile I/O functions in `profile.py` become the data-access layer. The rest of the code doesn't change.

4. **Async Spotify search:** Replace `ThreadPoolExecutor` with `asyncio` + `aiohttp` for even higher throughput. The `search_tracks()` interface stays the same.

5. **Webhook-based feedback:** The feedback module's append-only design makes it trivial to add webhook notifications or analytics — just hook into `like_track()` / `dislike_track()`.

6. **Profile import/export:** Since profiles are plain JSON, import/export is just file copy. A future UI could offer "Share your taste profile" functionality.

7. **Fine-tuned models:** The `get_model()` function already supports dynamic model selection. If you fine-tune a model on your feedback data, just enter its ID in Settings.

---

## Alternatives Considered

| Current Choice | Alternative | Why It Was Rejected |
|---|---|---|
| JSON file storage | SQLite database | Overhead of a DB engine for a single-document, single-user dataset. JSON is simpler and human-readable. |
| `ThreadPoolExecutor` | `asyncio` + `aiohttp` | Async would require rewriting the entire call stack. Threads are simpler for a 10-worker I/O workload. |
| Module-level singleton | Dependency injection | Every Flask route and core function would need the client threaded through — boilerplate with no practical benefit for a single-user app. |
| File-append debug log | Python `logging` module | The debug log captures structured GPT I/O (full prompts + responses), not conventional log messages. A simple file-append is more appropriate. |
| Single-file backup | Git-like version history | One-level undo is sufficient. Full version history adds complexity for rare rollback needs. |
| Prompt template files | Inline prompt strings | Prompts change frequently during development. External files allow iteration without code changes and can be edited by non-developers. |
| `response_format={"type": "json_object"}` | Manual JSON parsing with retries | Structured Outputs is more reliable and eliminates an entire class of parse-failure bugs. |
