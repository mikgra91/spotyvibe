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
| `GPT_HISTORY_LIMIT` | 200 | Max history entries sent to GPT (bounds token usage). |
| `EXHAUSTED_ARTIST_THRESHOLD` | 4 | Artists with ≥ this many tracks in history are marked `[EXHAUSTED]` in the exclusion block. |
| `MAX_CONSECUTIVE_EMPTY_BATCHES` | 3 | Breaks the loop after N all-filtered retries. |
| `MAX_GPT_CALLS_PER_RUN` | 20 | Hard ceiling per generation run. |
| `DEFAULT_OPENAI_MODEL` | `gpt-5.4-mini` | Fallback model. |
| `PROFILE_IMPORT_MAX_BYTES` | 10 MB | Per-request cap for profile import. |
| `GENERAL_REQUEST_MAX_BYTES` | 1 MB | Flask `MAX_CONTENT_LENGTH` for all other endpoints. |

**Credential keys (keyring):** `OPENAI_API_KEY`, `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`.

**Settings keys (`settings.conf`):**
`OPENAI_MODEL`, `DEBUG_MODE`, `PLAYLIST_SIZE`, `NEW_ARTIST_PERCENTAGE`, `GPT_LANGUAGE`, `ONBOARDING_COMPLETED`, `ACTIVE_PROFILE_ID`, `UI_LANGUAGE`, `LLM_BASE_URL`, `PROVIDER_PRESET`.

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

`app.py` uses a handful of private helpers to keep route functions small: `safe_text(data, key)` (text extraction with sanitisation + length caps), `call_gpt_json()` (single-shot JSON completion with error mapping), `_parse_profile_sections()` (body → structured dict), `_load_help_html()` (language-aware), `_persist_setting()` (dotenv write), `_collect_forbidden_artists()` / `_compute_exhausted_artists()` (build deny blocks fed to GPT).

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
- `popularity`, `followers`, `audio_features` endpoints are gone — `core/src/spotify_metadata.py` is retained but no longer exposed.

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

The suggestion pipeline can inject a pre-ranked pool of ~20 artists retrieved from a local MusicBrainz-derived corpus into the LLM prompt. This converts the model's job from *recall* (naming fitting artists from parametric memory — where small local models hallucinate and `gpt-*-mini` defaults to popular names) into *ranking* (picking from a supplied shortlist). The full design rationale lives in [guides/rag-implementation.md](guides/rag-implementation.md); this section is the operational summary.

**Module layout** ([core/src/rag/](../core/src/rag/)):

| File | Role |
|---|---|
| `corpus.py` | `RagCorpus` dataclass — loads `artists.jsonl.gz` into in-memory rows + inverted tag index + TF-IDF idf vector. ~80 MB resident for 100K artists. |
| `retrieval.py` | `score_artists(profile, deny_list)` — TF-IDF over artist-tag postings with a bigram/hyphen compound boost (×3) and a popularity re-rank penalty. Returns top `RAG_POOL_SIZE` rows. |
| `prompt.py` | Formats retrieved rows as the `CANDIDATE_POOL` prompt block appended to the suggestions user-message. |
| `distribution.py` | Manifest fetch, update check, streaming sha256-verified download. Pure stdlib `urllib`. |

**Runtime wiring** — [app.py](../app.py) loads the corpus once at startup when `RAG_ENABLED` is true *and* the file exists (missing corpus is a silent no-op); [core/src/suggestions.py](../core/src/suggestions.py) appends the candidate-pool block to the user prompt per batch, with the user's confirmed anchors + the batch deny-list feeding the retriever's filter. Toggling the setting in the UI hot-swaps the corpus handle without a restart.

**Configuration** ([config.py](../config.py)):

| Constant | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | persisted in `settings.conf`; `DEFAULT_RAG_ENABLED = True` when unset and corpus present | Master toggle; UI-exposed in Settings → Candidate pool (RAG). Disabling persists explicit `false` so the new default doesn't silently re-enable. |
| `RAG_CORPUS_PATH` | `data/rag_corpus/artists.jsonl.gz` | Corpus location. |
| `RAG_POOL_SIZE` | `20` | Candidates injected per batch. |
| `RAG_POPULARITY_PENALTY` | `0.4` | Anti-popularity-bias re-rank coefficient (0 = pure TF-IDF, 1 = strong obscurity bias). |
| `RAG_MANIFEST_URL` | GitHub release URL | Override via env var for staging. |

### RAG corpus (separate release channel)

The corpus (`artists.jsonl.gz`, ~7 MB) is **not** bundled with the app artifacts above. It ships on its own rolling GitHub Release tagged `rag-corpus-latest`, independent of the versioned app releases, so the corpus can be refreshed without cutting a new app build.

**Release contents** — the `rag-corpus-latest` tag always holds exactly two assets:

| Asset | Purpose |
|---|---|
| `artists.jsonl.gz` | Top 100,000 artists by Option A popularity proxy (release count + tag total). One NDJSON row per artist. |
| `manifest.json` | `{corpus_version, built_at, sha256, size_bytes, corpus_url}`. Clients fetch this once per startup to decide whether to prompt for an update. |

**Producing a new release** (requires authenticated `gh` CLI):

```bash
# 1. Rebuild the corpus from a fresh MusicBrainz dump.
python build-tools/refresh_rag_corpus.py           # fetch+extract+build in one step
#    (or, if you already have the dump extracted:
#     python build-tools/build_rag_corpus.py --source /path/to/mbdump/ ...)

# 2. Publish — uploads both assets with --clobber, replacing the previous pair.
python build-tools/publish_rag_corpus.py           # version derived from mtime (UTC date)
python build-tools/publish_rag_corpus.py --version 2026-04-19   # or pin explicitly
python build-tools/publish_rag_corpus.py --dry-run             # print manifest, skip upload
```

`publish_rag_corpus.py` does three things: computes sha256 of the corpus, writes `manifest.json` pointing at the asset URL under the `rag-corpus-latest` tag, and calls `gh release upload … --clobber` (creating the release on first run). The rolling tag means download URLs stay stable — clients never need to learn a new release name.

**Client-side update flow** — implemented in [core/src/rag/distribution.py](../core/src/rag/distribution.py) and wired from [app.py](../app.py):

1. `_check_rag_corpus_update()` runs once at startup (5-second timeout, silent on failure).
2. Result is cached in-process and exposed via `/api/settings` as `rag_update` (`{status: current | update_available | missing_corpus | offline, remote: {...}, local_version: "…"}`).
3. The Settings modal renders a banner when status is `update_available` or `missing_corpus`. Clicking **Download now** POSTs to `/api/rag/download-corpus`, which streams to `artists.jsonl.gz.part`, sha256-verifies against the manifest, atomically renames into place, writes the `artists.meta.json` sidecar, and hot-swaps the in-memory `RagCorpus` handle.
4. `RAG_MANIFEST_URL` is overridable via env var for testing against a staging URL.

**Cadence** — there is no scheduled refresh. Rebuild and republish when MusicBrainz's monthly dumps warrant it, or when tag/alias curation changes meaningfully alter retrieval quality.

### Maintaining the RAG feature

Day-to-day upkeep of the RAG pipeline breaks into four buckets:

1. **Corpus refresh** — roughly quarterly, or when users report stale / missing artists:
   - `python build-tools/refresh_rag_corpus.py` (fetches the latest MusicBrainz dump, extracts, rebuilds). Intermediate downloads cache under `build-tools/.rag-cache/`; pass `--cleanup` to wipe after success.
   - `python build-tools/publish_rag_corpus.py` to upload + rewrite the `rag-corpus-latest` release. All existing clients pick up the update on their next startup via the manifest check.
2. **Tag alias map** ([data/rag_corpus/tag_aliases.json](../data/rag_corpus/tag_aliases.json)) — the curated keyword→tag lookup that feeds query expansion. Extend additively when you see a profile term (e.g. a new subgenre, a non-English mood word) failing to match MusicBrainz tags. No rebuild required; the map is read by the retriever at startup.
3. **Retrieval tuning** — placeholder knobs that should be revisited after real-user A/B data accumulates:
   - `RAG_POPULARITY_PENALTY` (too obscure → lower; too mainstream → raise).
   - `RAG_POOL_SIZE` (persistent hallucinations → try 40; feels too directive → try 10).
   - `_COMPOUND_BOOST` in `retrieval.py` (bigram boost factor).
4. **Tests** — [core/tests/test_rag_corpus.py](../core/tests/test_rag_corpus.py), `test_rag_retrieval.py`, `test_rag_prompt.py`, `test_rag_distribution.py`. Fixtures use tiny hand-crafted gzipped JSONL; no real corpus is checked in. Run as part of `pytest core/tests/`.

**Known limitations to track:**

- Option A popularity proxy (release count + tag total) over-rates long-dead classical composers. Acceptable because tag matching dominates selection — flag for re-evaluation only if users complain.
- Alias map is English-centric; German/Japanese profile vocabulary degrades to unigram matching until aliases are added.
- No embedding fallback; profiles naming vibes with no MusicBrainz tag coverage silently produce weaker pools. The `score_artists()` interface is the seam for a future embedding-based v2.

---

## Tests

```bash
python -m pytest core/tests/ -v              # ~458 core tests, ~3s
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
