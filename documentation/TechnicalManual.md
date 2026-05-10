# Technical Manual

Architecture and developer reference for SpotyVibe — a Flask app that combines OpenAI (or any OpenAI-compatible LLM) with the Spotify Web API.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Browser (frontend/templates/)                    │
│    OpenAI section (profile, analysis)   Spotify section (runs,      │
│                                         history, refine)            │
└──────────┬──────────────────────┬────────────────────┬──────────────┘
           │ JSON / SSE           │                    │
           ▼                      ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Flask (app.py)                              │
│   /api/run (SSE)  /api/feedback  /api/analyze  /api/profile/*       │
│   /api/spotify/*  /api/settings/*  /api/help/*  /api/onboarding/*   │
│   /api/session  /api/spotify/token  /api/runs  /callback            │
└───┬──────────────┬──────────────┬──────────────┬──────────────┬─────┘
    ▼              ▼              ▼              ▼              ▼
core/src/       core/src/      core/src/      core/src/      core/src/
profile.py      suggestions.py analysis.py    playlist.py    history.py
                │              │              │
                ▼              ▼              ▼
            openai_http.py (stdlib urllib — no SDK)   ─►  OpenAI-compatible API
                                              │
                                              └────────►  Spotify Web API
```

---

## Project Layout

See [ProjectLayout.md](ProjectLayout.md) for the full tree. Key paths:

| Path | Purpose |
|---|---|
| `app.py` | All HTTP endpoints and the generation orchestrator |
| `config.py` | Runtime configuration, credentials, settings keys |
| `core/src/` | Business logic modules (imported as `core.src.*`) |
| `prompts/` | Editable AI prompt templates |
| `frontend/templates/` | Jinja2 partials (`base.html` + modals, panels) |
| `frontend/static/js/modules/` | Feature modules — no bundler |
| `frontend/static/css/` | Modular CSS (`base.css`, `components.css`, …) |
| `frontend/static/i18n/` | `en.json`, `de.json`, `jp.json` (kept in sync) |
| `documentation/` | Help pages, setup guides, manuals |

---

## `config.py` — Configuration & Credentials

Secrets are stored in the OS keychain (Windows Credential Manager / macOS Keychain) via the `keyring` library, with `%LOCALAPPDATA%\spotyvibe\.credentials` as a plaintext fallback on platforms without a usable keyring. Non-secret preferences live in `%LOCALAPPDATA%\spotyvibe\settings.conf` (dotenv format). On first load, plaintext secrets in `.credentials` are migrated into keyring automatically.

**Key constants:**

| Constant | Default | Purpose |
|---|---|---|
| `BASE_DIR` | — | Runtime asset root. Resolves to `sys._MEIPASS` in PyInstaller / wheel installs. |
| `BATCH_SIZE` | 10 | Tracks requested per GPT call. |
| `DEFAULT_PLAYLIST_SIZE` | 10 | Default playlist size; the UI accepts 5–30 and clamps server-side in `/api/run`. |
| `DEFAULT_NEW_ARTIST_PERCENTAGE` | 30 | Minimum % of each batch from artists not in history. |
| `GPT_HISTORY_LIMIT` | 200 | Max history entries considered when building the deny set (bounds the aggregate-counts scope). |
| `RECENT_VERBATIM_TRACKS` | 100 | C3 — only this many most-recent tracks render verbatim in `forbidden_tracks`. Older tracks are represented via the new `artist_track_counts` aggregate. |
| `EXHAUSTED_ARTIST_THRESHOLD` | 4 | Artists with ≥ this many tracks in history are marked `[EXHAUSTED]` in the exclusion block. Computed from the full aggregate (within `GPT_HISTORY_LIMIT`), not just the recent verbatim slice. |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | 3 | Breaks the loop after N all-filtered retries. |
| `MAX_GPT_CALLS_PER_RUN` | 4 | Hard ceiling per generation run (lowered from 20 → 4 during Phase 2.6 — see comment in `config.py`). |
| `DEFAULT_OPENAI_MODEL` | `gpt-5.4-mini` | Fallback model. |
| `STAGE3_FAST_MODEL` | `gpt-5.4-mini` | Stage 3 model used by the **Fast** strategy (and by **Auto** on a cold profile). |
| `STAGE3_BEST_MODEL` | `gpt-5.4` | Stage 3 model used by the **Best** strategy (and by **Auto** once `feedback.disliked_tracks` ≥ 1). |
| `STAGE3_MODE_DEFAULT` | `fast` | Initial Stage 3 strategy for a fresh install — matches pre-L5 behaviour (always mini). |
| `PROFILE_IMPORT_MAX_BYTES` | 10 MB | Per-request cap for profile import. |
| `GENERAL_REQUEST_MAX_BYTES` | 1 MB | Flask `MAX_CONTENT_LENGTH` for all other endpoints. |

**Credential keys (keyring):** `OPENAI_API_KEY`, `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`.

**Settings keys (`settings.conf`):**
`OPENAI_MODEL`, `STAGE3_MODE`, `DEBUG_MODE`, `PLAYLIST_SIZE`, `NEW_ARTIST_PERCENTAGE`, `GPT_LANGUAGE`, `ONBOARDING_COMPLETED`, `ACTIVE_PROFILE_ID`, `UI_LANGUAGE`, `LLM_BASE_URL`, `PROVIDER_PRESET`.

`STAGE3_MODE` (L5 — 2026-05-08) governs Stage 3 model selection. Values: `fast` (always `STAGE3_FAST_MODEL`), `best` (always `STAGE3_BEST_MODEL`), `auto` (fast for cold profile, best once `feedback.disliked_tracks` ≥ 1), `custom` (use whatever `OPENAI_MODEL` resolves to — covers local LLMs). Resolution lives in `core.src.suggestions._resolve_stage3_model`. Default is `fast` so existing installs see no behaviour change; users opt into Auto / Best / Custom from the Settings modal.

`LLM_BASE_URL` and `PROVIDER_PRESET` support pointing the app at any OpenAI-compatible endpoint (Ollama, LM Studio, Groq, OpenRouter, or a custom `/v1` URL).

**Helpers:** `_get_app_dir()`, `get_model()`, `get_gpt_language()`, `get_debug_mode()`, `get_playlist_size()`, `get_new_artist_percentage()`, `get_active_profile_id()`, `get_active_profile_path()`, `get_settings()`.

---

## Core Modules (`core/src/`)

| Module | Responsibility |
|---|---|
| `openai_http.py` | Direct HTTP client for OpenAI-compatible APIs using `urllib.request` only. Retries 429/5xx with exponential back-off. Error hierarchy: `OpenAIError` → `OpenAIConfigError`, `OpenAIAuthError`, `OpenAIRateLimitError`, `OpenAITimeoutError`, `OpenAIResponseError`, `OpenAIUnsupportedModelError`. |
| `utils.py` | Shared helpers: `get_openai_models()`, `strip_code_fences()`, `debug_log()`, `sanitize_text()`, `sanitize_profile()`, `safe_text()` (form/body string extraction), `call_gpt_json()` (one-shot wrapper used by analysis, profile training, seeding), `app_log()`. |
| `profile.py` | Multi-profile CRUD (`list_profiles`, `create_profile`, `delete_profile`, `activate_profile`), load/save, AI training (`train_profile`), direct-save (`save_profile_sections`), validation, automatic `.history.json` backup, vibe-description auto-classification. mtime-based cache avoids redundant JSON reads. |
| `suggestions.py` | Generation engine. `build_messages()` → `call_gpt()` → `normalize_response()` → `filter_duplicate_suggestions()`. Uses a **single** `prompts/system_prompt.txt` with a `{validation_block}` placeholder that the code injects per-model (see below). Injects `{batch_size}`, `{new_artist_percentage}`, `{min_new_artists}`, `{gpt_language}`, `{recent_feedback}`, `{audio_filters_block}`, `{deny_set_json}`. |
| `playlist.py` | All Spotify Web API calls. Includes `search_tracks()` (ThreadPoolExecutor, 10 workers), `_enrich_tracks_with_metadata()` (genres + release year), `add_to_playlist()` (create/append/replace), `get_playlist_tracks()`, `get_user_playlists()`, `filter_emerging_artists()`, `get_spotify_access_token()` / `get_spotify_session_info()` (back the Web Playback SDK). |
| `feedback.py` | Records like/dislike into `profile.feedback.liked_tracks` / `disliked_tracks`. Disliking without a track rejects the entire artist. |
| `analysis.py` | `analyze_band_song()` — structured JSON GPT output (genre, style tags, characteristics, GPT-estimated audio features, profile suggestions). Temperature 0.3. |
| `history.py` | `run_history.json` persistence. `save_run()` (capped at 5 entries) and `load_runs()`. Track entries carry `rationale` array, GPT `energy`/`valence`, Spotify `genres`, `release_year`. Legacy v1 entries are migrated on read. |
| `taste.py` | Aggregates profile + history for the "Your taste at a glance" charts (genre donut, energy×valence scatter, decade bar). |
| `localised_docs.py` | Two-step language fallback for help pages and setup guides (`help.<lang>.md` → `help.en.md`). Returns `(path, served_lang, fallback_used)`. |

### Unified system prompt

`prompts/system_prompt.txt` is the only system prompt file. `build_messages()` calls `_get_validation_block(model_name)` which returns a model-tailored reasoning block (step-by-step for `gpt-4.1`, candidate-pool for `gpt-5.4`, generic fallback otherwise) and substitutes it into the `{validation_block}` placeholder. This replaces the earlier `system_prompt_gpt-4-1.txt` / `system_prompt_gpt-5-4.txt` file variants.

### Dedup & retry

`filter_duplicate_suggestions()` applies fuzzy key normalisation (lowercase, strip punctuation, collapse whitespace) against full history + disliked tracks. Removed tracks are exposed in `result["_filtered_out"]`. The orchestrator passes them back as `recently_filtered_tracks` on the next retry, so the warning block in `system_prompt.txt` lists exactly what GPT must not suggest. After `MAX_CONSECUTIVE_EMPTY_BATCHES` consecutive all-filtered batches, the loop breaks and the playlist is created with whatever was verified.

### Prompt files

| File | Used by | Purpose |
|---|---|---|
| `system_prompt.txt` | `suggestions.py` | Unified system prompt with `{validation_block}` placeholder. |
| `prompt_template.txt` | `suggestions.py` | User message template. |
| `profile_training_prompt.txt` | `profile.py` | Taste profile training system message. |
| `profile_seed_from_playlist.txt` | `profile.py` | Profile seeding from an existing Spotify playlist. |
| `analysis_prompt.txt` | `analysis.py` | Band/song analysis template. |

---

## `app.py` — HTTP Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Single-page UI. |
| POST | `/api/run` | Generation pipeline. **SSE stream.** Body: `run_id`, `playlist_mode`, `playlist_id`, `playlist_name`, `audio_filters`, `emerging_only`, `temperature`, `playlist_size` (clamped 5–30). Event types: `progress`, `batch_verified`, `result`, `cancelled`, `error`. |
| POST | `/api/cancel` | `{run_id, finalize}`. With `finalize:true`, stops the loop and creates the playlist from what was verified. |
| GET | `/api/run/<run_id>/status` | SSE recovery state after disconnect. |
| POST | `/api/feedback` | Record like/dislike. Dislikes also remove from the Spotify playlist. |
| POST | `/api/feedback/dislike-artist` | Record artist-level dislike AND strip every track by that artist from the active playlist. Returns `{removal: {removed_count, removed_tracks}}`. |
| POST | `/api/remove` | Remove a track from Spotify without recording feedback. |
| POST | `/api/analyze` | Band/song analysis. |
| GET | `/api/profile/status` | Trained state + timestamp. |
| GET | `/api/profile/data` | Active profile JSON (for edit-mode pre-fill). |
| GET | `/api/profile/export` | Download active profile as `spotyvibe_profile.json`. |
| POST | `/api/profile/import` | Replace active profile from JSON (10 MB cap; old profile auto-backed up to history). |
| POST | `/api/profile/reset-to-history` | One-step revert. |
| POST | `/api/train-profile` | Structured sections → GPT → updated profile. |
| GET/POST/DELETE | `/api/profiles[/<id>[/activate]]` | Multi-profile CRUD. |
| GET | `/api/spotify/status` | `not_configured` / `not_authenticated` / `authenticated` (validated with live `current_user()`). |
| GET | `/api/spotify/auth`, `/callback` | OAuth. |
| POST | `/api/spotify/disconnect` | Clear cached token. |
| GET | `/api/playlists` | User playlists (picker + append/replace modes). |
| GET | `/api/runs` | Run history (newest-first). |
| GET | `/api/session` | Session metadata consumed by the Web Playback SDK wrapper. |
| GET | `/api/spotify/token` | Short-lived access token for the Web Playback SDK. |
| GET/POST | `/api/settings`, `/api/settings/credentials` | Non-secret prefs / masked credentials. |
| GET | `/api/settings/models` | Model list. **Cached 5 min (`_models_cache`).** |
| DELETE | `/api/settings/debug-log` | Clear debug log. |
| GET | `/api/help` | Rendered help HTML; honours `ui_language` with EN fallback. |
| GET | `/api/help/section/<anchor>` | Single help section by anchor ID. |
| GET | `/api/help/guide/<slug>` | Setup guide as structured JSON. Whitelisted: `openai_api_key`, `spotify_developer_app`, `python_install_macos`, `python_install_linux`. |
| GET | `/api/onboarding/status`, `POST /api/onboarding/complete` | First-run onboarding gate. |
| GET | `/api/onboarding/progress` | Drives the **Getting Started** floating checklist — auto-derived flags for `keys_saved`, `spotify_connected`, `profile_created`, `playlist_generated`, plus `feedback_count` / `feedback_target` / `feedback_done`. |

### Cancellation

Each `/api/run` request is assigned a `run_id`. The server stores a `threading.Event` per run in `_runs`. The generation loop checks the event (a) before each iteration and (b) immediately after each blocking `call_gpt()`. `/api/cancel` with `finalize:false` yields a `cancelled` event and leaves Spotify untouched. `finalize:true` breaks out, caps verified tracks at the target size, and yields a normal `result` event with `was_cancelled:true`.

### Backend helpers

`app.py` uses a handful of private helpers to keep route functions small: `safe_text(data, key)` (text extraction with sanitisation + length caps), `call_gpt_json()` (single-shot JSON completion with error mapping), `_parse_profile_sections()` (body → structured dict), `_load_help_html()` (language-aware), `_persist_setting()` (dotenv write), `collect_forbidden_artists()` / `_compute_exhausted_artists()` (build deny blocks fed to GPT).

### Performance

- **flask-compress** — automatic gzip / brotli for text responses.
- **Cache-Control** — static CSS/JS/images carry `public, max-age=300` (5 min) to 86400 (1 day) depending on path.
- **Threaded Flask** — `app.run(threaded=True)` so SSE streams don't block other requests.
- **mtime-based profile cache** — `profile.py` skips JSON reads when the file's mtime hasn't changed.
- **5-minute model list cache** — `/api/settings/models`.

---

## Frontend

Vanilla JS modules + Jinja partials. No bundler, no framework.

**Layout:** `base.html` hosts the provider sections (OpenAI / Spotify) and a floating **Getting Started** checklist card (`#gettingStartedCard`) that reflects `/api/onboarding/progress`. Items auto-check as state changes; each row has a **Jump** action that expands and scrolls to the relevant section.

**Settings → Display size:** a radiogroup in the Settings modal writes `--ui-scale` on `:root` (three options: Small / Default / Large). All font-size tokens (`--fs-2xs` … `--fs-2xl`) multiply by this variable so the entire UI scales consistently.

**Preview player:** opens a three-zone bottom-sheet overlay.
1. Player (centered) — `#sdkPlayer` (Web Playback SDK with 👍 / 👎 quick buttons that submit immediately) on Premium + Widevine/FairPlay runtimes; iframe fallback (`#spotifyPreviewIframe`, ~30 s previews) otherwise. A header toggle stores autoplay preference in `localStorage.spv_preview_autoplay`.
2. Action buttons — **Feedback** (opens the reason panel) and **Delete**.
3. Sliding feedback panel — artist/track/reason inputs + dual submit (`#previewFbSubmitLike` / `#previewFbSubmitDislike`).

SDK lifecycle lives in `frontend/static/js/modules/spotify-sdk.js`; the route layer is `core/src/playlist.py::get_spotify_access_token()` / `get_spotify_session_info()`.

**Quickstart tour:** `frontend/static/js/modules/quickstart-tour.js` renders a 3-step provider-scoped storyboard (OpenAI: Setup → Profile → Repeat; Spotify: Setup → Generate → Refine). Does **not** auto-open — users launch it from ☰ → 🚀 Quick Start. Dismiss preference is per-provider (`spotyvibe-quickstart-openai-dismissed`, `spotyvibe-quickstart-spotify-dismissed`).

**Help page:** landing view shows 5 task-oriented tiles (set up keys, build profile, generate, refine, troubleshoot). A sidebar TOC is also available; clicking a tile jumps into the relevant help section.

**i18n:** every user-facing string uses `data-i18n="key"` or `i18n('key','fallback')`. `en.json`, `de.json`, and `jp.json` must stay in sync — `core/tests/test_i18n_parity.py` enforces this.

**Empty states:** Refine Playlist and Band/Song Analysis render tip cards when empty, so first-time users aren't looking at a blank panel.

**Audio filter grid:** rebuilt with per-row CSS named grid areas so each filter row lays out independently on narrow viewports without flex wrapping.

**Onboarding:** 4-page swipeable flow (intro, language, credentials, connect). CSS uses container-size queries to fluidly scale the card on short viewports.

### Theme system

| Theme | Implementation | Body class |
|---|---|---|
| Equalizer | Canvas — 56 spring-physics bars with simulated beats | `.theme-equalizer` |
| Pulse | Canvas — ring pool + emitters + ambient haze + bass-drop bursts | `.theme-pulse` |

Preference stored in `localStorage['spotyvibe-theme']`. Renderers registered in `theme-switcher.js`. A `prefers-reduced-motion` media query disables all CSS animations and all canvas loops.

---

## Security

- `sanitize_text()` / `sanitize_profile()` strip null bytes and control chars from every user input.
- `validate_profile_schema()` whitelists top-level keys and enforces field-length caps.
- Flask `MAX_CONTENT_LENGTH = 1 MB`; profile import allows 10 MB.
- System prompts mark user-provided profile data as untrusted to harden against prompt injection.
- Spotify search strings are sanitised before building `track:"..." artist:"..."` queries.

---

## Spotify Web API (February 2026 changes)

See [../SKILL.md](../SKILL.md) for the full reference. Summary:

- Use `sp.playlist_items()` — `playlist_tracks()` was removed.
- Each playlist item's inner key is `"item"`, not `"track"`. SpotyVibe uses `entry.get("item") or entry.get("track")` and a `fields=items(item(...))` parameter.
- `GET /me/playlists` renamed the summary field from `"tracks"` to `"items"` — code falls back to either.
- Playlist creation uses `current_user_playlist_create()` (`POST /v1/me/playlists`).
- Search `limit` max is 10; SpotyVibe uses `limit=1`.
- `popularity`, `followers`, `audio_features` endpoints are gone (the obsolete `spotify_metadata.py` helper module that wrapped them was removed 2026-04-30).

On 403 during playlist writes, `add_to_playlist()` calls `disconnect_spotify()` so the UI shows the reconnect banner.

---

## Distribution

| Target | Artifact | Build |
|---|---|---|
| Windows | `spotyvibe.exe` (PyInstaller one-folder) or `spotyvibe_onefile.exe` | `bash build-tools/build_exe.sh --package` |
| macOS / Linux | `spotyvibe-*.whl` (`hatchling` backend, `py3-none-any`) | `pip install build && python -m build --wheel` |

All artifacts attach to each [GitHub Release](../../releases). CI workflow: `.github/workflows/ci.yml`.

### Windows desktop wrapper

`desktop_launcher.py` opens a native window via **pywebview** (WebView2 runtime on Windows 10/11 — a patched Windows is required; Legacy Edge/MSHTML falls back to a broken render). Closing the window terminates the process. Credentials live in the OS keychain; settings in `%LOCALAPPDATA%\spotyvibe\settings.conf`.

### Python wheel (macOS / Linux)

- `hatchling` force-includes `app.py`, `config.py`, `core/src/`, `frontend/`, `prompts/`, `data/`, `documentation/`.
- `spotyvibe.cli:main()` reserves port 5000 (Spotify's redirect URI is hard-coded), delays 1.5 s, then opens the default browser and runs Flask.
- One `.whl` tagged `py3-none-any` serves both platforms.

### RAG candidate-pool feature

The suggestion pipeline can inject a pre-ranked pool of ~20 artists retrieved from a local MusicBrainz-derived corpus into the LLM prompt. This converts the model's job from *recall* (naming fitting artists from parametric memory — where small local models hallucinate and `gpt-*-mini` defaults to popular names) into *ranking* (picking from a supplied shortlist). The detailed design rationale lives in §"RAG design reference" further down; this section is the operational summary.

**Module layout** ([core/src/rag/](../core/src/rag/)):

| File | Role |
|---|---|
| `corpus.py` | `RagCorpus` dataclass — loads `artists.jsonl.gz` into in-memory rows + inverted tag index + TF-IDF idf vector. Slimmed schema (only `mbid`, `name`, `begin_year`, `tags`, `tag_weights`, `listener_popularity` — `sort_name`/`country`/`end_year` and the unused `by_mbid`/`by_name_normalised` indexes were dropped in 2026-04 — see §"RAG design reference" → Per-artist schema). ~150 MB resident for 350K artists, ~210 MB for 500K. |
| `retrieval.py` | `score_artists` (flat) + **`score_artists_stratified` (default)** — TF-IDF over artist-tag postings with bigram/hyphen compound boost (×3) and a popularity re-rank penalty. Stratified mode runs the retriever once per profile facet (`must_have`, `soft_preferences`, `primary_reference`, `tags`) with per-facet quotas so eclectic profiles don't get one strong facet starving the others. Returns up to `RAG_POOL_SIZE` rows (default 60). |
| `prompt.py` | Formats retrieved rows as the `CANDIDATE_POOL` prompt block appended to the suggestions user-message. |
| `distribution.py` | Manifest fetch, update check, streaming sha256-verified download. Pure stdlib `urllib`. |

**Runtime wiring** — [app.py](../app.py) loads the corpus once at startup when `RAG_ENABLED` is true *and* the file exists (missing corpus is a silent no-op); [core/src/suggestions.py](../core/src/suggestions.py) appends the candidate-pool block to the user prompt per batch, with the user's confirmed anchors + the batch deny-list feeding the retriever's filter. Toggling the setting in the UI hot-swaps the corpus handle without a restart.

**RAG bypass on `emerging_only=True`** — when the user picks the "Brand new bands" exploration notch, RAG is **skipped**. The MusicBrainz dump is republished quarterly at most and cannot contain artists who debuted in the last 6 months, so injecting the pool would contradict the system constraint. The post-Spotify `filter_emerging_artists` (album `release_date` check) remains the factual verification step. See `core/src/suggestions.py::build_messages` and `documentation/spotyvibe_with_rag/` vs `_without_rag/` eval logs for the data behind the decision.

**Configuration** ([config.py](../config.py)):

| Constant | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | persisted in `settings.conf`; `DEFAULT_RAG_ENABLED = True` when unset and corpus present | Master toggle; UI-exposed in Settings → Candidate pool (RAG). Disabling persists explicit `false` so the new default doesn't silently re-enable. |
| `RAG_CORPUS_PATH` | `<app_dir>/rag_corpus/artists.jsonl.gz` (under the user's app dir, e.g. `%LOCALAPPDATA%/spotyvibe/`) | Corpus location. Survives across PyInstaller-EXE launches. |
| `RAG_POOL_SIZE` | `60` | Candidates injected per batch. Bumped from 20 in 2026-04 after the eval log showed only ~19% of GPT picks came from a 20-slot pool — i.e. the pool was too narrow to anchor for eclectic profiles. Tuned to 60 (down from a brief stint at 100) once the stratified split per facet started carrying its weight. See `spotyvibe-decisions-2026-04-21.md`. |
| `RAG_POPULARITY_PENALTY` | `0.4` | Anti-popularity-bias re-rank coefficient (0 = pure TF-IDF, 1 = strong obscurity bias). |
| `RAG_STRATIFIED` | `True` | When true, use `score_artists_stratified` so each facet of the profile (must_have, soft_preferences, primary_reference, tags) gets a guaranteed quota of the pool. |
| `RAG_FACET_WEIGHTS` | `{must_have: 0.50, soft_preferences: 0.25, primary_reference: 0.15, tags: 0.10}` | Per-facet share of `RAG_POOL_SIZE`. Remainder fills from a flat pass. |
| `RAG_MANIFEST_URL` | `https://storage.googleapis.com/spotivibe-rag-corpus/manifest.json` | Override via env var for staging. Points to the public GCS bucket populated by the weekly Cloud Run Job. |

**Prompt grows under RAG** — with RAG on, each LLM call carries an extra ~700 tokens (the 60-slot pool). The full conversation typically lands at 4–6 k tokens (system + profile + history + pool + JSON output) on cloud models. `BATCH_SIZE = 10` is unchanged regardless of the RAG state.

> **⚠ RAG limitations on small local LLMs.** A RAG-enabled prompt can run 4–6 k tokens. If you point SpotyVibe at a local model with a hard 4 k or 8 k context window the pool may be truncated and quality drops sharply. Mitigations:
>
> - **Disable RAG** in Settings → Candidate pool. The model falls back to its parametric music knowledge (lower hallucination resistance, but the prompt drops to ~3 k tokens).
> - **Lower `RAG_POOL_SIZE`** (e.g. 40 or 20) — see the trade-off table in §"RAG design reference" → Pool size sweet-spot data.
> - **Use a 16 k+ context model** (most cloud APIs and any `*-128k` local model). This is the recommended path — RAG was designed against GPT-4-class models with 32 k+ contexts.
>
> Self-hosting a smaller open-weight model on Cloud Run **as a drop-in OpenAI replacement** was evaluated and rejected (April 2026): NVIDIA L4 GPU on Cloud Run runs a few dollars a month at current volume, but Gemma/Llama 4-bit ≪ GPT-4 for creative/nuanced music reasoning, and sporadic use triggers 15–30 s cold starts. Cost is comparable; quality is the disqualifier. Use OpenAI / a hosted GPT-4-class model for the suggestion engine and reserve local LLMs for users who explicitly accept the quality trade-off.

### RAG corpus — Cloud Run automated pipeline

The corpus (`artists.jsonl.gz`, ~10 MB) is **not** bundled with the app. It is built and published automatically by a **Google Cloud Run Job** that runs weekly, independent of app releases.

**Infrastructure** (see [`documentation/guides/cloud-run-rag-setup.md`](guides/cloud-run-rag-setup.md) for the full setup guide):

| Component | Details |
|---|---|
| **GCP Project** | `spotivibe-rag` |
| **GCS Bucket** | `spotivibe-rag-corpus` (us-central1, public read via `allUsers/objectViewer`) |
| **Cloud Run Job** | `spotivibe-rag-builder` — 1 vCPU, 4 GiB RAM, 24 h timeout, max-retries 1 |
| **Cloud Scheduler** | `spotivibe-rag-weekly` — monthly, 1st at 23:00 Europe/Vienna (`0 23 1 * *`) |
| **Service Account** | `spotivibe-rag-builder@spotivibe-rag.iam.gserviceaccount.com` |

**Pipeline** — the Cloud Run Job executes `build-tools/cloud_run_publish.py`, which:

1. Runs `refresh_rag_corpus.py` — downloads the latest MusicBrainz JSON dump (~3 GB), **streams** directly from the compressed `.tar.xz` archives (no 33 GB extraction to disk), and invokes `build_rag_corpus.py` to produce the corpus.
2. **(Optional, currently disabled)** Runs `enrich_with_spotify.py` if `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` are set and `DISABLE_SPOTIFY_ENRICHMENT` is unset. Disabled since 2026-05-04: Spotify's `genres` field returns empty for all artists post-Feb-2026. Code retained for future re-enablement.
3. **(Phase B, 2026-05)** Runs `enrich_with_lastfm.py` if `LASTFM_API_KEY` is set — looks up each MB artist on Last.fm via MBID and attaches `lastfm_listeners`, `lastfm_playcount`, and `lastfm_tags` (weighted community tags, min-weight cutoff ≥ 30). Rate-limited to ~5.5 req/s. Estimated wall-clock for all ~174k artists: ~17 h (within the 24 h timeout). Distinct exit codes: 43 (rate-limit → `halt.flag`) / 44 (auth-error → loud fail). See `build-tools/lastfm_enrichment/client.py`.
4. Computes SHA-256 of the resulting `artists.jsonl.gz`.
5. Uploads `artists.jsonl.gz` + `manifest.json` to the public GCS bucket.
6. Wipes the ephemeral working directory.

**Bucket contents** — always exactly two objects:

| Asset | Purpose |
|---|---|
| `artists.jsonl.gz` | Top 350,000 artists by Option A popularity proxy (release count + tag total), filtered to acts with `begin_year >= 1960`. One NDJSON row per artist. |
| `manifest.json` | `{corpus_version, built_at, sha256, size_bytes, corpus_url}`. Clients fetch this once per startup to decide whether to prompt for an update. |

**Manual rebuild** (if the weekly Job is insufficient or you need an ad-hoc refresh):

```bash
# Option 1: Trigger the Cloud Run Job manually.
gcloud run jobs execute spotivibe-rag-builder --region=us-central1

# Option 2: Run locally and publish to GCS (requires gcloud auth + gsutil).
python build-tools/refresh_rag_corpus.py --top-n 350000
# Then upload manually:
gcloud storage cp data/rag_corpus/artists.jsonl.gz gs://spotivibe-rag-corpus/
```

**Cost**: $0/month on the GCP always-free tier. The Job uses ~29 vCPU-hours/month (of 50 free) at 1 vCPU and ~14.5 GiB-hours/month (of 100 free) at 4 GiB RAM. See `cloud-run-rag-setup.md` § 9 for the full cost breakdown.

**Client-side update flow** — implemented in [core/src/rag/distribution.py](../core/src/rag/distribution.py) and wired from [app.py](../app.py):

1. `_check_rag_corpus_update()` runs once at startup (5-second timeout, silent on failure).
2. Result is cached in-process and exposed via `/api/settings` as `rag_update` (`{status: current | update_available | missing_corpus | offline, remote: {...}, local_version: "…"}`).
3. The Settings modal renders a banner when status is `update_available` or `missing_corpus`. Clicking **Download now** POSTs to `/api/rag/download-corpus`, which streams to `artists.jsonl.gz.part`, sha256-verifies against the manifest, atomically renames into place, writes the `artists.meta.json` sidecar, and hot-swaps the in-memory `RagCorpus` handle.
4. `RAG_MANIFEST_URL` is overridable via env var for testing against a staging URL.

**Cadence** — the Cloud Run Job runs monthly (1st of each month at 23:00 Vienna time) via Cloud Scheduler. `MIN_REBUILD_DAYS=25` prevents premature rebuilds. The corpus refreshes automatically from the latest MusicBrainz dump. No manual intervention is needed unless the pipeline fails (check Cloud Run console → Jobs → Executions).

### Maintaining the RAG feature

Day-to-day upkeep of the RAG pipeline breaks into five buckets:

1. **Corpus refresh (automated)** — the weekly Cloud Run Job handles this. Monitor via:
   - `gcloud run jobs executions list --job=spotivibe-rag-builder --region=us-central1 --limit=5`
   - GCS bucket: `gcloud storage ls --long gs://spotivibe-rag-corpus/`
   - Public manifest: `curl -s https://storage.googleapis.com/spotivibe-rag-corpus/manifest.json`
   - If the Job fails, check logs in the Cloud Run console or trigger a manual re-run.
2. **Cloud Run Job maintenance** — if the build scripts change, rebuild and push the Docker image:
   ```bash
   cd <repo-root>
   gcloud builds submit --config=build-tools/cloud-run-job/cloudbuild.yaml .
   ```
   The next scheduled (or manual) execution picks up the new image automatically.
3. **Tag alias map** ([data/rag_corpus/tag_aliases.json](../data/rag_corpus/tag_aliases.json)) — the curated keyword→tag lookup that feeds query expansion. Extend additively when you see a profile term (e.g. a new subgenre, a non-English mood word) failing to match MusicBrainz tags. No rebuild required; the map is read by the retriever at startup. After editing, rebuild the Docker image (step 2) so the Cloud Run Job includes the updated aliases.
4. **Retrieval tuning** — placeholder knobs that should be revisited after real-user A/B data accumulates:
   - `RAG_POPULARITY_PENALTY` (too obscure → lower; too mainstream → raise).
   - `RAG_POOL_SIZE` (persistent hallucinations → try 40; feels too directive → try 10).
   - `_COMPOUND_BOOST` in `retrieval.py` (bigram boost factor).
5. **Tests** — [core/tests/test_rag_corpus.py](../core/tests/test_rag_corpus.py), `test_rag_retrieval.py`, `test_rag_prompt.py`, `test_rag_distribution.py`. Fixtures use tiny hand-crafted gzipped JSONL; no real corpus is checked in. Run as part of `pytest core/tests/`.

**Known limitations to track:**

- Option A popularity proxy (release count + tag total) over-rates long-dead classical composers. Acceptable because tag matching dominates selection — flag for re-evaluation only if users complain.
- Alias map is English-centric; German/Japanese profile vocabulary degrades to unigram matching until aliases are added.
- No embedding fallback; profiles naming vibes with no MusicBrainz tag coverage silently produce weaker pools. The `score_artists()` interface is the seam for a future embedding-based v2.

### RAG design reference

This subsection captures the formulas, memory budgets, and design-rationale answers that earlier lived in `documentation/guides/rag-implementation.md` (deleted 2026-04-25 after consolidation). Code comments throughout `core/src/rag/` point here.

#### Per-artist schema

| Field | Source | Used for |
|---|---|---|
| `mbid` (UUID) | MusicBrainz `artist.id` | Stable primary key |
| `name` | MusicBrainz `artist.name` | Prompt injection + Spotify search |
| `begin_year` | MusicBrainz `artist.begin_date_year` | Era matching |
| `tags` (list) | MusicBrainz `artist_tag` joined on tag id | Genre / mood matching — main retrieval signal |
| `tag_weights` (list of ints) | MusicBrainz `artist_tag.count` | Tag relevance ranking |
| `listener_popularity` (0–1) | Derived: release count + tag total proxy (Option A) | Anti-popularity-bias re-rank (fallback when Last.fm data absent) |
| `spotify_id`, `spotify_genres` | Phase 2 enrichment via Spotify Client Credentials | Optional: extra tag vocabulary (currently disabled — Spotify genres empty post-Feb 2026) |
| `lastfm_listeners` | Phase B enrichment via Last.fm `artist.getInfo` | Primary popularity signal — log10-scaled to 0–1 in `_lastfm_popularity()` |
| `lastfm_playcount` | Phase B enrichment via Last.fm `artist.getInfo` | Stored for future use; not currently consumed at runtime |
| `lastfm_tags` | Phase B enrichment via Last.fm `artist.getTopTags` | High-signal weighted tags (0–100), indexed alongside MB tags + Spotify genres |
| `lastfm_tag_weights` | Phase B enrichment via Last.fm `artist.getTopTags` | Per-tag weight matching `lastfm_tags` order |

Slimming history (2026-04): `sort_name`, `country`, `end_year` and the in-memory `by_mbid` / `by_name_normalised` indexes were dropped because they were loaded but never read. Net: ~25–30% resident memory reduction. JSONL parser silently ignores extra fields, so older corpora still load.

#### Corpus size rationale

| Top-N cut | Disk (gzipped) | Resident | Recall | Decision |
|---:|---:|---:|---|---|
| 100,000 | ~5 MB | ~80 MB | Misses regional / niche acts for eclectic tastes | Too small |
| 350,000 | ~25–35 MB | ~150–200 MB | Covers virtually every artist a real user will encounter | **Default** |
| 500,000+ | ~40–55 MB | ~210–280 MB | No measurable recall gain; hurts cold start | Avoid |

Pre-1960 artists are filtered (`MIN_ARTIST_BEGIN_YEAR = 1960`) at both build time and runtime — historical/classical acts dominate tag-weighted rankings but don't fit modern music discovery. Onboarding panel + Settings tooltip surface this constraint.

#### Retrieval scoring formula

Given the user's `profile`, `primary_reference`, and the batch's `deny_list`:

```
query_tags = profile.must_have_tags
           + profile.soft_preferences (lower weight)
           + extract_tags(primary_reference.analysis)

score(artist) = sum(tag_idf[t] * tag_weight[artist, t] * query_weight[t]
                    for t in query_tags if t in artist.tags)

final_score   = score(artist) * (1 - RAG_POPULARITY_PENALTY * popularity_normalised)
```

`tag_idf` uses smoothed IDF: `log((N+1)/(df+1)) + 1`. Bigrams and hyphenated compounds get a `_COMPOUND_BOOST = 3.0` multiplier — discovered empirically because "dream pop" is far more diagnostic than "pop". Tag extraction from free-text profile hints uses [data/rag_corpus/tag_aliases.json](../data/rag_corpus/tag_aliases.json), a hand-curated keyword→tag lookup (~200 entries covering common synonyms like "electronic" → `electronica`).

#### Stratified retrieval

`score_artists_stratified` runs the retriever once per profile facet (`must_have`, `soft_preferences`, `primary_reference`, `tags`) with per-facet quotas, dedupes across facets, fills the remainder from a flat pass, and falls back to the flat scorer if every facet is empty. Quotas defined in `RAG_FACET_WEIGHTS` (must_have 50%, soft 25%, reference 15%, tags 10%) — tuned for the 60-slot default but works at any pool size.

Rationale: a single TF-IDF pass over a heavily-weighted `must_have` facet starves softer signals on eclectic profiles. Stratified guarantees per-facet coverage.

#### Pool size sweet-spot data

Eval data (Apr 2026, 4 playlists × 30 tracks on the "Rock" profile):

| `RAG_POOL_SIZE` | Pool adherence | Hallucination rate | Notes |
|---:|---:|---:|---|
| 20 | 19% | 5.5% | Pool too narrow to anchor an eclectic profile — model picks off-pool 81% of the time |
| 60 | ~38% | ~5% | Better adherence, prompt grows ~600 tok |
| **100** | **~50%** | **~5%** | Eval benchmark value; further width adds prompt cost without measurable gain |
| 200 | ~55% | ~5% | Hits 8K context for some local LLMs |

The 2026-04-21 decision report set `≥ 40% in_candidate_pool` as the target metric; the 100-slot default reaches it.

#### Sparse retrieval over embeddings — design choice

TF-IDF + tag matching chosen over sentence-transformers embeddings because:

1. **Offline-first discipline.** Tag TF-IDF has zero runtime ML dependencies; embeddings pull in `sentence-transformers` or ONNX Runtime (~90 MB model + dep tree).
2. **Tag data is already structured.** MusicBrainz tags are human-curated. Running embeddings over already-categorised text gives diminishing returns.
3. **Workload is short-tail filtering, not fuzzy similarity.** The profile already names specific genres/moods; tag matching is a strong signal.
4. **Debuggability.** TF-IDF scores are inspectable by reading the query; embedding scores are opaque.

`score_artists()` is the replacement seam if "profile mentions a vibe with no exact tag match" becomes a measured failure mode.

#### Hallucination measurement — pandas guide

The eval log (`%LOCALAPPDATA%/spotyvibe/eval.jsonl` on Windows; `~/.local/share/spotyvibe/eval.jsonl` on Linux) writes one row per AI-suggested track when `DEBUG_MODE=true`. Schema is documented under "Eval-log telemetry" below.

Capture protocol for a clean A/B:
1. Reset the eval log (delete or rename).
2. Enable `DEBUG_MODE` in Settings.
3. Run N playlists with RAG off (Settings → Candidate pool (RAG) → off). Vary nothing else.
4. Run N playlists with RAG on. Same profile, same playlist size.
5. Disable `DEBUG_MODE` when done.

Headline analysis (drop a 30-row sample into Jupyter):

```python
import pandas as pd
from pathlib import Path

LOG = Path.home() / ".local/share/spotyvibe/eval.jsonl"  # or %LOCALAPPDATA% on Windows
df = pd.read_json(LOG, lines=True)

# Hallucination rate: tracks Spotify could not find
print(df.groupby("rag_enabled")["found_on_spotify"].apply(lambda s: 1 - s.mean()))

# Pool effectiveness (RAG-on only)
rag_on = df[df["rag_enabled"]]
print("Pool adherence:", rag_on["in_candidate_pool"].mean())
print("Found-rate by pool membership:")
print(rag_on.groupby("in_candidate_pool")["found_on_spotify"].mean())

# Repeated hallucinations — high-signal cases
hallucinations = (df.loc[~df["found_on_spotify"], ["model", "rag_enabled", "artist", "track"]]
                    .value_counts(["artist", "track", "model", "rag_enabled"])
                    .reset_index(name="count").sort_values("count", ascending=False))
hallucinations.head(20)
```

Decision rules:

| Observation | Action |
|---|---|
| RAG-on hallucination rate ≥ 30% lower than RAG-off | Confirms RAG value; keep `DEFAULT_RAG_ENABLED = True` |
| `in_candidate_pool` mean < 0.4 | Try `RAG_POOL_SIZE = 200` *or* tighten the candidate-pool prompt language |
| `in_candidate_pool` mean > 0.9 *and* hallucinations still high | The pool itself is wrong — extend `tag_aliases.json` |
| Out-of-pool found-rate ≈ in-pool found-rate | Pool not adding ranking signal — revisit `RAG_POPULARITY_PENALTY` |
| Repeated identical hallucinations across runs of the same profile | Add to the profile's `avoid` list, or add the *correct* artist as an alias if it's a misremember |

Caveats: `found_on_spotify=False` is not a perfect hallucination signal — Spotify catalog gaps, regional restrictions (`market="from_token"`), and minor title typos all count as misses. Cross-check the worst-offender list before drawing conclusions.

#### Token budget for the candidate pool

The `CANDIDATE_POOL` block in [core/src/rag/prompt.py](../core/src/rag/prompt.py) holds itself to **≤ 250 input tokens for a 20-artist pool** (~12 tokens per row: name + 2-3 tags). At the current 100-slot default, the budget scales linearly to ~1,200 tokens — accounted for in the per-call cost analysis (see §RAG candidate-pool feature above and [result-improvement.md](../result-improvement.md) Phase 0).

Format is intentionally terse (no per-row index prefix, tags inline in parentheses) since the index was never read by GPT and the `— tags:` prose was redundant given the parenthetical convention.

#### KV-cache friendliness

The `CANDIDATE_POOL` block is placed **after** the stable system prompt + profile but **before** the deny-list and feedback. Rationale: profile is stable across a single playlist run, so everything before the pool stays cached on llama.cpp's `--cache-reuse` and on OpenAI's prompt cache. The pool itself changes per batch (deny-list grows, re-ranking shifts), so cache resets there and onward — already the case with the current deny-list.

---

## Eval-log telemetry (`core/src/eval_log.py`)

When `DEBUG_MODE=true`, every generation run appends JSONL rows to `eval.jsonl` (in the user's app dir). Two row kinds, written to the same file:

| Row kind | Written by | One row per | Purpose |
|---|---|---|---|
| `kind: "track"` | `log_batch_outcome()` | each AI-suggested track | Hallucination + pool-hit measurement (per-track). Original 2026-04 schema. |
| `kind: "batch_summary"` | `log_batch_summary()` | each LLM call | **Quality-impact analysis of Option A / Option C trims** (added 2026-04-22). Carries prompt-component char counts, OpenAI `usage` (when present), and the `gpt_returned → after_filter → spotify_found → in_pool` funnel. |

Both row types share `run_id`, `batch_num`, `profile_hash` and **`config_signature`** — the last is a short SHA1 over `{rag_enabled, rag_pool_size, rag_stratified, effective_batch_size, extra}` so rows generated under the same configuration can be bucketed without diffing timestamps. The `extra` dict carries trim flags (`compact_json`, `slim_pool_format`, `feedback_trim_v2`, `strip_dup_profile_fields`) so a future change can be A/B-bucketed simply by flipping a flag.

**Plumbing**:

- `core/src/suggestions.py::build_messages` populates `_LAST_PROMPT_COMPONENTS` (per-component char counts) alongside the existing `_LAST_RAG_POOL_NAMES`. Both are exposed via `get_last_prompt_components()` and `get_last_rag_pool_names()`.
- `core/src/suggestions.py::call_gpt` attaches OpenAI's `usage` block (`prompt_tokens` / `completion_tokens` / `total_tokens`) to the result dict under `_usage`. Local LLM providers that omit `usage` produce `_usage: None` — callers detect "provider omitted" vs "we forgot to plumb it" by key presence.
- `app.py::run_pipeline` pops `_usage` immediately after `call_gpt`, computes the funnel counts before/after `filter_duplicate_suggestions` + Spotify verification, then writes one `track` row per suggestion plus one `batch_summary` row per LLM call.

**Cost**: zero when `DEBUG_MODE` is off (every writer short-circuits at the first line). When on, write volume is ~1 KB per track + ~500 B per batch — negligible for offline-analysis workloads.

**Analysis pattern** (pandas):

```python
import json, pandas as pd
rows = [json.loads(l) for l in open("eval.jsonl", encoding="utf-8")]
df = pd.DataFrame(rows)

tracks = df[df["kind"] == "track"]
batches = df[df["kind"] == "batch_summary"]

# Spotify-found rate per config signature.
print(tracks.groupby("config_signature")["found_on_spotify"].mean())

# Funnel collapse rate per config (how many of the LLM's tracks survive dedup + Spotify).
batches["funnel_pass"] = batches["spotify_found_count"] / batches["gpt_returned_count"]
print(batches.groupby("config_signature")[
    ["gpt_returned_count", "after_filter_count", "spotify_found_count", "in_pool_count", "funnel_pass"]
].mean())

# Prompt-size impact of the trims (compare config_signatures before vs after).
prompt_sizes = batches["prompt_components"].apply(pd.Series)
print(prompt_sizes.groupby(batches["config_signature"]).mean())
```

**Tests**: `core/tests/test_eval_log.py` (17 tests) and `core/tests/test_suggestions.py::TestPromptTelemetryCapture` (4 tests).

---

## Per-run perf log (`core/src/perf_log.py`)

M3 (2026-05-07). One sqlite row per playlist generation, written from
the `/api/run` finally block before `trace.finalize_trace()` clears the
in-memory metrics. Lets a longitudinal trend ("did latency drift over
N weeks?") be answered with one SQL query without re-running the eval
harness.

**Path**: `<APP_DIR>/perf_log.sqlite`. Created on first write.

**Schema** (`run_perf` table):

| Column | Type | Notes |
|---|---|---|
| `run_id` | TEXT PRIMARY KEY | UUID; deduplicates on retry. |
| `ts_utc` | TEXT NOT NULL | ISO-8601 insert time. |
| `model` | TEXT | Selected model at `/api/run` time. |
| `stage_metrics` | TEXT NOT NULL | JSON dump of `{stage: {duration_s, calls, tokens_in, tokens_out}}`. |
| `tracks_found` | INTEGER NOT NULL | Verified tracks at finalisation. |
| `tracks_target` | INTEGER NOT NULL | What the user requested. |
| `exhausted` | INTEGER NOT NULL | 1 when GPT-exhaustion guard fired. |
| `error` | TEXT | Truncated message when the run raised, else NULL. |
| `schema_version` | INTEGER NOT NULL | Bumped on incompatible changes. |

**Always-on metrics**: `core/src/trace.py` keeps a lightweight
`_METRICS` accumulator that is populated regardless of `DEBUG_MODE`;
the heavy trace bundle (`stages` payloads, disk write) still requires
`DEBUG_MODE=true`. `trace.current_stage_metrics()` returns a deep copy
for the perf-log writer.

**Cost**: ~one `INSERT` per generation (≈ 1 ms). Failures are logged
+ swallowed so the perf log is never load-bearing.

**Tests**: `core/tests/test_perf_log.py` (12 tests) plus
`TestAlwaysOnMetrics` in `core/tests/test_trace.py` (6 tests).

---

## SSE error classification (`core/src/errors.py`)

U2 (2026-05-07). `TranslatableError` and `as_response_payload()` now
carry an `error_class` field with values `"transient"` or `"permanent"`.
The frontend SSE handler renders transient failures with ⏳ + a soft
status level (the user just retries) and permanent failures with ❌.

**Classification entry points**:

- `OpenAIRateLimitError` and `OpenAITimeoutError` (in
  `core/src/openai_http.py`) carry class-level `error_class = "transient"`
  and `key = "error.transient.openai_rate_limited" / "openai_slow"`.
- Spotipy's `SpotifyException` is a third-party type; `app.py`
  `_classify_unknown_exception()` inspects `http_status` (429 / 502 /
  503 / 504) and injects the transient class + i18n key.
- Anything else → defaults to `permanent`.

**i18n keys** (en/de/jp): `error.transient.openai_rate_limited`,
`error.transient.openai_slow`, `error.transient.spotify_rate_limited`,
`error.transient.spotify_unavailable`.

**Tests**: `TestErrorClass` in `core/tests/test_errors.py` (6 tests)
and `TestSseErrorClassification` in `core/tests/test_app.py` (7 tests).

---

## Tests

```bash
python -m pytest core/tests/ -v              # ~780 core tests, ~15s
bash build-tools/run_frontend_tests.sh       # Playwright, 3 parallel groups
bash build-tools/run_tests.sh                # all tests, 4 groups
bash build-tools/run_tests_podman.sh         # CI parity
```

Screenshot tests are excluded via the `screenshots` pytest marker — run only on explicit refresh.

External APIs (OpenAI, Spotify) are mocked throughout; no test ever hits the network.

---

## Data Flow: Generation

```
User clicks Generate
      ▼
 Load active profile (mtime-cached)  ◄── profiles/<uuid>.json
      ▼
 build_messages()  ──────► OpenAI-compatible API  (configured model)
      ▼                     returns N suggestions
 filter_duplicate_suggestions()   (fuzzy dedup vs history + dislikes)
      ▼
 search_tracks()  ──────► Spotify Web API  (10 parallel workers)
      ▼
 Enrich with genres + release_year
      ▼
 Enough? ── no ──► Retry (MAX_CONSECUTIVE_EMPTY_BATCHES cap, 20-call ceiling)
      ▼ yes
 add_to_playlist()  ──────► Spotify Web API
      ▼
 save_run()  ──────► run_history.json (cap 5)
      ▼
 SSE `result` event → browser renders cards + playlist link
```

---

## Documentation Cleanup Log

| Date | Commit | Action |
|---|---|---|
| 2026-05-04 | `a212e55` | Consolidated and deleted 6 working documents (see below). Relevant technical content merged into this manual; open tasks merged into `next-steps.md`. |

**Files deleted in the 2026-05-04 cleanup:**

| File | Lines | Content | Disposition |
|---|---|---|---|
| `result-improvement.md` | 1410 | Phase 0–6 implementation journal (quality & cost rework history) | Architecture captured here; open items in `next-steps.md` |
| `cost-speed-research.md` | 597 | 26-lever cost/speed audit (2026-04-29) | Shipped levers documented here; open levers in `next-steps.md` |
| `corpus_analysis.md` | 907 | Pre-enrichment corpus diagnosis + vocab-mismatch findings | Superseded by Phase B Last.fm enrichment; residual items in `next-steps.md` |
| `context/claudeAnalyse.md` | 278 | One-time production failure analysis (F1–F9 findings) | All findings implemented (Phases 2.0–2.6); analysis is historical |
| `documentation/rag_enrichment_plan.md` | 265 | Multi-source enrichment plan (Phases A–E) | Phase A+B done; C–E tracked in `next-steps.md`; Cloud Run details here |
| `TODO.md` | 317 | Deferred code-review items register | All completed or merged into `next-steps.md` |

All deleted files are recoverable via `git show <commit>:path/to/file`. Use the commit hash above to inspect any file's content at the point of deletion.

