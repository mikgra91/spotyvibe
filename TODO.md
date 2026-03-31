# TODO

---

## 🧩 JS Extraction & Modularization

### Context
The script block from `templates/index.html` (lines 358–2203) was not extracted during the HTML modularization phase. `frontend/templates/base.html` already references `static/js/main.js`. This task extracts and splits the JS into component-aligned ES modules under `frontend/static/js/`.

### Steps

- [x] Read `templates/index.html` lines 358–2203 (full script block) to capture all JS before deleting the file
- [x] Create `frontend/static/js/modules/` directory and extract the following modules:
  - [x] `modules/state.js` — global state variables (`suggestions`, `openFormIndex`, `spotifyAuthStatus`, etc.)
  - [x] `modules/auth.js` — credential & Spotify auth checks, `connectSpotify`, `toggleSpotifyConnection`
  - [x] `modules/warnings.js` — `renderComponentWarnings`
  - [x] `modules/profile.js` — taste profile accordion, `toggleAccordion`, `prefillTrainFields`, `toggleTrainBody`, `startImportProfile`, `exportProfile`, `submitProfile`, `sendTrainProfile`, `saveProfileDirect`
  - [x] `modules/history.js` — `toggleHistoryBody`, `loadHistory`, `undoLastRun`
  - [x] `modules/analysis.js` — `toggleAnalysisBody`, `runAnalysis`, `renderAnalysisResult`, `copySuggestion`
  - [x] `modules/pipeline.js` — `runPipeline`, SSE streaming, `handleStreamEvent`, `setGenerating`, `cancelGeneration`, `resumeRun`, `useCurrentTracks`, `showSseDisconnectBanner`, `generateUUID`, `updateUseTracksButton`, `canGenerate`
  - [x] `modules/audio-filters.js` — `toggleAudioFilters`, `getAudioFilters`
  - [x] `modules/playlist-mode.js` — `getPlaylistMode`, `onPlaylistModeChange`, `getPlaylistModePayload`
  - [x] `modules/tracklist.js` — `renderTracks`
  - [x] `modules/preview.js` — `openPreviewOverlay`, `closePreviewOverlay`
  - [x] `modules/feedback.js` — `toggleFeedback`, `closeFeedback`, `submitFeedback`, `removeTrack`, `animateRemove`
  - [x] `modules/ui.js` — `showStatus`, `showPlaylistLink`, `hidePlaylistLink`, `esc`, `attr`, `sanitizeHtml`, `escHtml`, `toggleSettingsMenu`, `showToast`
  - [x] `modules/modals.js` — `openCredentials`, `saveCredentials`, `clearCredential`, `saveSettings`, `openHelp`, `closeModal`
  - [x] `modules/theme-switcher.js` — `switchTheme`, `THEME_BACKGROUNDS`, `THEME_RENDERERS`
  - [x] `modules/theme-equalizer.js` — Equalizer canvas renderer
  - [x] `modules/theme-pulse.js` — Pulse canvas renderer (sourced from `96fc34d` — working copy was truncated)
  - [x] `modules/i18n.js` — `switchLanguage`, `applyLanguage`, `i18n`, `initI18n`
- [x] Create `frontend/static/js/main.js` — entry point: imports all modules, wires up DOMContentLoaded init and global function assignments
- [x] Update `frontend/templates/base.html` script tag: add `type="module"` to the `main.js` `<script>` tag
- [ ] Delete `templates/index.html` (source file is now fully superseded by `frontend/templates/`)
- [ ] Update memory: mark JS extraction as complete

---

## Features

- [x] **Add “Reset to history” button for Music Profile**.
  - Adds a UI action to restore the previous profile.
  - Implementation should *swap* `personalized_music_profile.json` and `personalized_music_profile.history.json` (current becomes history, history becomes current).
  - Should handle the case where the history file does not exist.

- [x] **Disable / remove Debug Log on Android**.
  - The “Debug Mode” setting and the `DELETE /api/settings/debug-log` UI affordance should only be available on Desktop.
  - Android APK should not expose prompt logging controls in Settings.

- [x] **Add “Band/Song Analysis” section under Music Profile**.
  - UI: a new section where users can input:
    - band names, or
    - band + song names
  - Backend: send the input to the configured OpenAI model and return an analysis describing:
    - genre/style classification,
    - key musical characteristics (energy, instrumentation, vocals, production, structure),
    - “how to describe this sound” suggestions the user can paste into their profile.
  - Output should be structured (JSON) so the UI can render it cleanly.

- [x] **Switch for german language**
  - provide translation files for en and de
  - implement a option under the Menu to switch language
  - implement language picker for android application

- [x] **read and reply language for ChatGpt prompt**
  - provide an option under Settings to set the ChatGPT communication language
  - based on this language, chatgpt should handle the prompt as if it where german. 

# ✅ Android Onboarding Flow – Task List

## 🚀 Onboarding Trigger & State
- [x] Detect first app launch after installation
- [x] Automatically show onboarding flow on first launch
- [x] Persist onboarding completion state (e.g., SharedPreferences)
- [x] Prevent onboarding from showing again after completion or skip

---

## 📱 Navigation & UX Structure
- [x] Implement multi-page onboarding (horizontal swipe)
- [x] Enable swipe gesture navigation between pages
- [x] Add "Skip" button (bottom-left) on all pages
- [x] Add "Next" button (bottom-right) on all pages except last
- [x] Replace "Next" with "Close" button on final page
- [x] Ensure "Skip" and "Close" both exit onboarding and mark it as complete
- [x] Navigate user to main app screen after exit

---

## 🧾 Page 1 – Introduction
- [x] Display app logo
- [x] Display app name
- [x] Add short description/tagline
- [x] Ensure clean and simple layout for quick understanding

---

## 🔐 Page 2 – Credentials Setup
- [x] Explain required credentials (e.g., OpenAI API key, Spotify account)
- [x] Describe why credentials are needed
- [x] Add "Set Credentials" link/button at bottom
- [x] Open credential input screen/modal on click
- [x] Allow user to input and save credentials
- [x] Validate credential input (basic validation)

---

## 🎵 Page 3 – Spotify & Preferences
- [x] Add "Connect to Spotify" button
- [x] Trigger Spotify authentication flow
- [x] Handle successful Spotify connection state
- [x] Add "Import Preference Profile" button
- [x] Allow user to import or define preference profile
- [x] Provide feedback on successful import/setup

---

## 🔄 Integration with App Flow
- [x] Redirect new users to onboarding instead of main screen
- [x] Ensure onboarding is part of app startup flow (not standalone route only)
- [x] Remove or refactor existing static `/onboarding` page
- [x] Ensure onboarding actions (credentials, Spotify) update app state

---

## 🧪 QA & Edge Cases
- [x] Test onboarding appears only on first launch
- [x] Test "Skip" exits correctly from all pages
- [x] Test "Close" exits correctly on final page
- [x] Test swipe navigation works smoothly
- [x] Test credential input persistence
- [x] Test Spotify connection flow (success + failure cases)
- [x] Test onboarding state persistence across app restarts

- [x] **Add Spotify “audio feature” constraints (optional filters)**.
  - Optional post-verification filtering using Spotify audio features (tempo/energy/valence/etc.).
  - UI could start simple (e.g., “avoid slow songs”, “energy 0.6–1.0”) and expand later.

- [x] **Use feedback reasons more directly**.
  - Summarise recent like/dislike reasons into a short “recent feedback” block sent to GPT (capped for token safety).
  - Optionally provide a toggle to bias the next run toward recent likes vs exploration.

- [x] **Multiple playlists / playlist naming**.
  - Support “create new playlist”, “append to existing”, and/or “replace playlist” modes.
  - Allow custom playlist name templates (e.g., date/time, style tag).

- [x] **Run history and rollback**.
  - Save run metadata (timestamp, playlist ID/URL, tracks added) to local storage.
  - Add “undo last run” (remove tracks added by the last run).

- [x] **Previews and richer track cards**.
  - Add Spotify preview playback when `preview_url` is available.
  - Add quick links to track/album/artist in Spotify.
  - [x] **Show History – Auto-Update on New Generation**: history panel refreshes automatically when a new playlist is generated.
  - [x] **Persistent Song Feedback List**: song list persists across sessions (max 100 songs); generation blocked when list is too full; liked/disliked/removed tracks permanently deleted; counter shown in UI.
  - [x] **30-Second Song Preview via Spotify Embed**: replaced deprecated `preview_url` audio element with Spotify embed overlay (bottom-sheet), available for every track via "Preview" button.

## Security

- [x] **Add file size limit** for profile import.
  - Add a maximum request size and enforce it server-side for `POST /api/profile/import`.
  - Consider client-side early checks as a UX improvement (but do not rely on them).

- [x] **Sanitise & validate imported JSON**.
  - Parse and validate the JSON structure rigorously.
  - Map imported content onto the internal profile schema (template-based), rejecting unknown or dangerous fields.
  - Ensure types match expected shapes (dict vs list vs string) to prevent prompt-injection-like content from being stored in unexpected places.

- [x] **Add server-side request size limits for all user-input endpoints** (not just import).
  - Enforce size limits on `POST /api/train-profile`, `POST /api/save-profile`, `POST /api/feedback` (and any future endpoints).
  - Add field-level limits (max chars per field, max list lengths) to prevent runaway OpenAI prompt sizes and cost surprises.

- [x] **Strip/control unsafe characters from user-provided text**.
  - Remove null bytes and control characters.
  - Normalize whitespace.
  - Apply consistently to manual profile edits, feedback, and imported profile fields.

- [x] **Harden prompts against prompt injection by treating the profile as untrusted data**.
  - Update prompts / message assembly to explicitly instruct the model to ignore any instructions embedded inside profile fields.

- [x] **Restrict Android WebView downloads to trusted localhost endpoints**.
  - In `MainActivity.kt`, only allow downloads from `http://127.0.0.1:5000` (ideally only `/api/profile/export`).

- [x] **Escape/normalize Spotify search query inputs**.
  - Prevent malformed Spotify search queries by escaping or removing quotes in user-provided artist/track strings before building `track:"..." artist:"..."` queries.

## Reliability & Cost

- [x] **Hard cost guardrails**.
  - Add max GPT calls / retries per run.
  - Add field-level limits to prevent accidental huge prompts.
  - Optionally show rough cost estimates in debug mode.

- [x] **Better SSE resilience**.
  - Optionally persist run state by `run_id` so the UI can recover after refresh.
  - Add clearer end states for disconnects/timeouts.

- [x] **Cache model list (minor but nice)**.
  - Cache `/api/settings/models` responses for a short TTL to reduce OpenAI API calls.

## Android

- [x] **Android packaging polish (targeted)**.
  - Improve share/import flows for exported profiles.
  - Consider “open in external browser” for Spotify links.

## Testing & CI

- [x] **Testing & CI upgrades (keeps changes safe)**.
  - Add unit tests for import validation/sanitization.
  - Add tests for playlist creation modes and run rollback.
  - Add lightweight CI to run `pytest` on pushes/PRs.

## Documentation

- [x] **Fix documentation/behavior inconsistencies (quick wins)**.
  - Align docs with configurable playlist size (default 10) and batch size behaviour.
  - Avoid hard-coding “30 tracks” in user-facing docs where the value is configurable.

## Prompt Improvement (GPT Suggestion Quality)

### Phase 1 — Quick Wins
- [x] Add rejected/disliked artist filter to `filter_duplicate_suggestions()` (`core/suggestions.py`)
- [x] Add Unicode normalization (`NFKD`) to `_normalize_key()` (`core/suggestions.py`)
- [x] Remove `validation` field from output schema (`prompts/system_prompt.txt`)
- [x] Fresh retry prompts with ephemeral deny set — no prose warnings, no mention of previous attempt (`core/suggestions.py`)
- [x] Temperature escalation on retries: 0.7 → 0.5 → 0.3 (`core/suggestions.py`, `app.py`)
- [x] Code-side enforcement: max 2 tracks per artist per batch (`core/suggestions.py`)

### Phase 2 — Prompt Restructure
- [x] Consolidate system prompt — eliminate repeated/conflicting rules (`prompts/system_prompt.txt`)
- [x] Structured JSON deny sets (`DENY_LIST`) as single source of truth (`core/suggestions.py`)
- [x] Strip `artists.rejected` and `feedback.disliked_artists` from profile JSON sent to GPT (`core/suggestions.py`)
- [x] Over-request by +3 (`batch_size + 3`), playlist-only model output, code-side metadata derivation (`core/suggestions.py`, `app.py`)
- [x] Place `DENY_LIST` before profile in user message (`prompts/prompt_template.txt`)
- [x] Diversity hints on retries when history > 50 tracks (`core/suggestions.py`)

### Phase 3 — Structural
- [x] Store tracks as `{"artist": ..., "track": ...}` dicts in history instead of concatenated strings (requires profile migration) (`core/suggestions.py`, `core/profile.py`)
- [x] Two-pass generation for large histories (>150 tracks) (`core/suggestions.py`, `app.py`)
- [x] Per-model prompt tuning (if switching between gpt-4.1-mini and gpt-4.1) (`prompts/`, `core/suggestions.py`)

---

## Bugs

- [x] **Import/Export visibility**: Import and Export are visible even if the user did not press “Edit profile”.

- [x] **Import/Export alignment**: Import and Export buttons are not left-aligned under the “Last trained” label; they currently appear directly under the “Edit profile” button.

## 🧩 Audio Filters – Layout Overflow Issue

**Problem:** UI elements do not fit properly inside the container.

**Analysis:** Root cause is `grid-template-columns: 140px 1fr 1fr` with `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` on labels. "Danceability (0–1)" and "Acousticness (0–1)" get clipped. Each `.audio-filter-row` defines its own grid so label columns are independently sized (inconsistent widths across rows).

**Fix:** Flatten to a single parent grid on `.audio-filter-grid` with `display: contents` on each `.audio-filter-row` so all labels share one column track (`max-content`). Update mobile breakpoint accordingly.

### TODO
- [x] Inspect container constraints (padding, margin, width)
- [x] Replace fixed widths with responsive layout (`flex` or `grid`)
- [x] Ensure labels (Energy, Valence, etc.) have consistent width
- [x] Align min/max input fields horizontally
- [x] Add wrapping (`flex-wrap` or grid) to prevent overflow
- [x] Ensure inputs scale properly on smaller screens
- [x] Standardize spacing between rows and inputs
- [x] Test responsiveness across multiple screen sizes
- [x] (Optional) Refactor into 2-column grid:
  - Label | Min/Max inputs


---

## 👤 Hide Profile – Button Placement

**Problem:** "Hide profile" button is incorrectly placed below Import/Export/Reset.

**Analysis:** DOM order in `train-header-actions` is already correct — `btn-train` (Edit/Hide profile) appears before `profile-io-row` (Import/Export/Reset) in both HTML and visual order (`flex-direction: column`). Layout is correct. Spacing/gap cleanup needed.

### TODO
- [x] Move "Hide profile" button above Import / Export / Reset row
- [x] Adjust layout hierarchy:
  - Hide Profile
  - Import / Export / Reset
- [x] Ensure consistent spacing after repositioning
- [x] Verify responsive behavior (no awkward wrapping)
- [ ] (Optional) Style as secondary/destructive action


---

## 🔍 Song Analysis – Input Layout

**Problem:** Input fields are inconsistent and incorrectly arranged.

**Analysis:** The flex+column container with a two-input row and full-width button is already implemented correctly in HTML/CSS. The UX issue is that the header toggle button and the submit button both say "Analyse" — creating two identical buttons when the body is open. Fix: make the toggle label dynamic ("Open Analysis" / "Close Analysis").

### Desired Layout
- Row 1: Artist input + Track input
- Row 2: Analyse button (full width)

### TODO
- [x] Refactor container to use `flex` or `grid`
- [x] Place both input fields in a single row
- [x] Ensure equal width distribution (50/50 or proportional)
- [x] Move "Analyse" button to a new row below inputs
- [x] Make button full-width or properly centered
- [x] Standardize input height and styling
- [x] Fix padding and placeholder alignment (fix duplicate "Analyse" toggle label)
- [x] Add responsive fallback:
  - Stack inputs vertically on small screens
- [x] Ensure consistent spacing between elements


---

## ⚙️ Backend – Client `proxies` Error

~~**Error:** `Client.__init__() got an unexpected keyword argument 'proxies'`~~

**Resolved** — The `openai` SDK was removed and replaced with `core/openai_http.py` (stdlib `urllib.request`). The error was caused by the SDK's internal `httpx` client receiving an unsupported `proxies` keyword argument in newer `httpx` versions. Since there is no longer any SDK client being instantiated, this error cannot occur.

- [x] ~~Identify which client throws the error~~ (was openai SDK → httpx)
- [x] ~~Fix implementation~~ (removed the SDK entirely)
- [x] ~~Test~~ (covered by test_openai_http.py)


---

## 🚀 Onboarding – Reappears on App Start

**Problem:** Onboarding flow is not persisted correctly.

**Analysis:** Persistence is via `ONBOARDING_COMPLETED` key in `.credentials` dotenv file (Flask/Python side). The Flask `/` route renders `index.html` with **no redirect** to `/onboarding` even for first-time users. `showWebView()` in `MainActivity.kt` loads `FLASK_URL` (main app) unconditionally with an incorrect comment "Server handles onboarding redirect". Fix: add server-side redirect in the `/` route + Android SharedPreferences as fallback.

### TODO
- [x] Identify persistence method (`ONBOARDING_COMPLETED` in `.credentials` dotenv via `config.py`)
- [x] Ensure onboarding completion flag is saved (`onboardingCompleted = true`)
- [x] Load flag before rendering initial screen (Flask `/` redirect + Android SharedPreferences)
- [x] Prevent race conditions during app startup (SharedPreferences read before WebView load)
- [x] Ensure onboarding only renders if flag is false
- [x] Add fallback handling if state fails to load (Flask redirect is server-side fallback)
- [ ] Test scenarios:
  - First-time user
  - Returning user
  - App restart
  - App update
- [ ] (Optional) Add manual reset option for onboarding


---

## ✅ QA Checklist

- [x] UI layouts responsive across devices
- [x] No overflow or alignment issues
- [x] Buttons positioned logically
- [x] Backend client initializes without errors
- [x] Onboarding behaves correctly
- [ ] End-to-end flow works (Profile → Analysis → Playlist)

#### TODO (tests currently skipped due to failures)
These tests were skipped (commented out via `@pytest.mark.skip`) after the first failing run, per repo rule.

**Root cause identified and fixed:**
- **Primary cause**: `templates/index.html` was truncated mid-file inside the Pulse renderer (`/* bur` at line 2205). The missing ~185 lines included the rest of the Pulse renderer draw loop, `switchTheme(_pendingTheme || 'equalizer')` init call, `showToast()`, i18n functions, and `</script></body></html>`. This caused a JS `SyntaxError` that silently broke all interactive JS. Restored from commit `96fc34d`.
- **Secondary cause**: `openCredentials()` added `.open` to the modal *after* `await fetch()`, causing a timing race in Playwright. Fixed to open modal immediately and populate status async.
- All 16 `@pytest.mark.skip` decorators removed; tests re-enabled.

- [x] Fix and re-enable: `tests/test_frontend.py::TestThemeSwitcher::test_switch_to_pulse[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestThemeSwitcher::test_theme_persists_via_localstorage[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestSettingsGearMenu::test_dropdown_closes_on_outside_click[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestCredentialsModal::test_opens_from_gear_menu[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestCredentialsModal::test_shows_three_fields[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestCredentialsModal::test_shows_credential_status[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestCredentialsModal::test_closes_on_cancel[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestCredentialsModal::test_closes_on_overlay_click[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestHelpModal::test_loads_help_content[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestHelpModal::test_help_contains_key_sections[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestGenerationPipeline::test_generation_flow_with_mocked_sse[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestGenerationPipeline::test_cancel_button_shows_during_generation[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestFeedbackButtons::test_feedback_form_prefills_artist_and_track[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestFeedbackButtons::test_submit_like_sends_feedback[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestFeedbackButtons::test_remove_button_removes_track[chromium]`
- [x] Fix and re-enable: `tests/test_frontend.py::TestToastNotifications::test_toast_appears_on_feedback[chromium]`
