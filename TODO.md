# TODO — SpotyVibe Open Issues

Codebase analysis performed on 2026-04-06.

---

## ~~1. Refine Playlist shows track count in dropdown~~ ✅

- **Type:** UI bug
- **Severity:** Low
- **Location:**
  - `frontend/static/js/modules/review.js` → `populateReviewPlaylistPicker()` (line ~237)
- **Problem:** The Refine Playlist dropdown renders each option as `${pl.name} (${pl.track_count} tracks)`, while the Discover section dropdown (`playlist-mode.js` → `loadDiscoverPicker()`) renders only `pl.name`. The track count in the Refine dropdown is redundant visual noise.
- **Fix:** Remove the `(${pl.track_count} tracks)` suffix from the `populateReviewPlaylistPicker()` option text to match the Discover picker style:
  ```js
  // Before
  `<option value="${pl.id}">${pl.name} (${pl.track_count} tracks)</option>`
  // After
  `<option value="${pl.id}">${pl.name}</option>`
  ```
- **Files to change:** `frontend/static/js/modules/review.js`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/js/modules/review.js`** — In `populateReviewPlaylistPicker()` (line ~239), change the template literal from:
   ```js
   `<option value="${pl.id}">${pl.name} (${pl.track_count} tracks)</option>`
   ```
   to:
   ```js
   `<option value="${pl.id}">${pl.name}</option>`
   ```
2. **Run tests:** `python -m pytest frontend/tests/ -v` — verify no visual regression tests fail.

### Estimated scope
1 line change in 1 file. ~5 minutes.

</details>

---

## 2. Reload function to re-fetch Spotify playlists

- **Type:** Feature request
- **Severity:** Medium
- **Location:**
  - `frontend/static/js/modules/playlist-mode.js` → `loadDiscoverPicker()`, `refreshDiscoverPlaylistPicker()`
  - `frontend/static/js/modules/review.js` → `populateReviewPlaylistPicker()`
  - `frontend/static/js/modules/state.js` → `cachedPlaylists`, `invalidateCachedPlaylists()`
  - `frontend/templates/playlist_review.html`
  - `frontend/templates/generate_section.html`
- **Problem:** Both playlist dropdowns (Discover and Refine) cache the playlist list in `State.cachedPlaylists`. Once loaded, there is no user-accessible button to force a re-fetch from Spotify. If the user creates or modifies playlists externally (e.g., in the Spotify app), the dropdowns remain stale until a page reload.
- **Fix:** Add a refresh/reload button (e.g., ↻ icon) next to each playlist dropdown. On click, call `State.invalidateCachedPlaylists()` and then re-invoke the respective picker loader. The backend `GET /api/playlists` already returns fresh data — it is purely a frontend cache issue.
- **Files to change:** `frontend/templates/playlist_review.html`, `frontend/templates/generate_section.html`, `frontend/static/js/modules/review.js`, `frontend/static/js/modules/playlist-mode.js`, `frontend/static/css/styles.css` (refresh button style), `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Add i18n keys** — Add `"playlist_refresh_aria"` (e.g., "Refresh playlist list") to `frontend/static/i18n/en.json` and `de.json`.
2. **Edit `frontend/templates/generate_section.html`** — Add a refresh button (↻ icon) next to the `#playlistPickerRow` `<select>`. Use a `<button>` with `class="playlist-refresh-btn"`, `aria-label` bound to the i18n key, and `onclick="PlaylistMode.refreshDiscoverPlaylistPicker()"`.
3. **Edit `frontend/templates/playlist_review.html`** — Add the same refresh button next to `#reviewPlaylistPicker`. Wire `onclick` to a new exported function `refreshReviewPlaylistPicker()` in `review.js`.
4. **Edit `frontend/static/js/modules/review.js`** — Add and export `refreshReviewPlaylistPicker()`:
   ```js
   export async function refreshReviewPlaylistPicker() {
       State.invalidateCachedPlaylists();
       await populateReviewPlaylistPicker();
   }
   ```
5. **Edit `frontend/static/css/styles.css`** — Add `.playlist-refresh-btn` style: inline-flex, subtle icon, hover highlight, `min-height: 36px` for mobile touch target. Place it inline beside the picker `<select>`.
6. **Run tests.**

### Estimated scope
5 files, ~30 lines added. ~30 minutes.

</details>

---

## ~~3. EXE does not keep language settings after closing~~ ✅

- **Type:** Bug
- **Severity:** High
- **Location:**
  - `frontend/static/js/modules/i18n.js` → `switchLanguage()`, `initI18n()`
  - `desktop_launcher.py` → `_get_storage_path()`, webview configuration
- **Problem:** The UI language is persisted in `localStorage` (`svLang` key). In the desktop EXE (pywebview), WebView2 storage should be retained via the `storage_path` parameter (`%LOCALAPPDATA%\spotyvibe\webview_data`). However, the language setting is lost after closing the app, suggesting the WebView2 profile data is not actually being preserved across sessions or localStorage is cleared.
- **Root cause candidates:**
  1. The `storage_path` might not be applied correctly, or pywebview might not flush WebView2 profile data before the window closes.
  2. The `frameless=True` mode may affect how `storage_path` is handled.
  3. A potential workaround: persist the language setting server-side (like GPT language in `settings.conf`) and restore it on page load, bypassing localStorage reliance.
- **Recommended fix:** Save the UI language to the backend (`settings.conf`) alongside the GPT language. On page load, have the server inject the saved language via a template variable or API call, rather than relying solely on localStorage.
- **Files to change:** `config.py` (add `UI_LANGUAGE` setting), `app.py` (expose/save it), `frontend/static/js/modules/i18n.js` (read from server on init), `frontend/templates/base.html` (optional: inject as template var)

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `config.py`** — Add `UI_LANGUAGE` to `SETTINGS_KEYS` list (line ~134). Add helper functions:
   ```python
   def get_ui_language():
       return os.getenv("UI_LANGUAGE", "")

   def set_ui_language(lang: str):
       ensure_env()
       set_key(str(SETTINGS_FILE), "UI_LANGUAGE", lang)
       os.environ["UI_LANGUAGE"] = lang
   ```
   Include `"ui_language"` in `get_settings()` return dict.
2. **Edit `app.py`** — In the `POST /api/settings` endpoint, handle `ui_language` key by calling `set_ui_language()`. In `GET /api/settings`, include `ui_language` in the response.
3. **Edit `frontend/static/js/modules/i18n.js`** — In `switchLanguage()`, also POST the UI language to `/api/settings` with key `ui_language`. In `initI18n()`, fetch `/api/settings` to read `ui_language` from server-side and use it as the source of truth instead of `localStorage` alone. Fallback chain: server setting → localStorage → browser language.
4. **Run tests** — update `core/tests/test_config.py` to verify `UI_LANGUAGE` round-trips correctly.

### Estimated scope
4 files, ~40 lines. ~45 minutes.

</details>

---

## ~~4. Duplicate profile creation should be prevented (UI-side)~~ ✅

- **Type:** Bug / UX improvement
- **Severity:** Medium
- **Location:**
  - `core/src/profile.py` → `create_profile()` (line ~528)
  - `app.py` → `create_profile_endpoint()` (line ~804)
  - `frontend/static/js/modules/profile.js` → `createNewProfile()` (line ~222)
- **Problem:** The **backend** already prevents duplicate profile names (case-insensitive check in `create_profile()`) and returns a 400 error. The **frontend** `createNewProfile()` also handles the error response and displays it. So duplicate prevention is already implemented end-to-end.
- **Possible residual issue:** The error message from the backend (`A profile named "X" already exists.`) may not be translated for the German UI. The error is returned as a plain English string and displayed verbatim.
- **Fix:** Either (a) add an i18n key for the duplicate error message and translate it in `de.json`, or (b) perform a client-side pre-check against the loaded profile list before sending the API request.
- **Files to change:** `frontend/static/js/modules/profile.js`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Add i18n keys** — Add `"profile_duplicate_error"` key to `en.json` (`"A profile named \"{name}\" already exists."`) and `de.json` (`"Ein Profil mit dem Namen \"{name}\" existiert bereits."`).
2. **Edit `frontend/static/js/modules/profile.js`** — In `createNewProfile()`, when the backend returns a 400 with a duplicate error, check if the message matches the duplicate pattern and substitute the i18n key. Use `i18n('profile_duplicate_error', resp.error).replace('{name}', profileName)`.
3. **Run tests.**

### Estimated scope
3 files, ~10 lines. ~20 minutes.

</details>

---

## ~~5. Enter key does not trigger Band/Song Analysis~~ ✅

- **Type:** Bug
- **Severity:** Low
- **Location:**
  - `frontend/templates/band_analysis.html` (lines ~15–18) — input fields `#analysisArtist` and `#analysisTrack`
  - `frontend/static/js/modules/analysis.js` → `runAnalysis()`
- **Problem:** The analysis input fields (`analysisArtist`, `analysisTrack`) do not have `onkeydown` handlers for Enter. The user must click the "Analyse" button. Other inputs in the app (e.g., profile create) already support Enter-to-submit.
- **Fix:** Add `onkeydown="if(event.key==='Enter'){event.preventDefault();runAnalysis()}"` to both input elements in `band_analysis.html`.
- **Files to change:** `frontend/templates/band_analysis.html`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/templates/band_analysis.html`** — Add `onkeydown="if(event.key==='Enter'){event.preventDefault();runAnalysis()}"` to both `#analysisArtist` and `#analysisTrack` input elements.
2. **Accessibility:** Ensure the `onkeydown` handler is also added as an attribute so screen readers and keyboard users benefit equally.
3. **Run tests.**

### Estimated scope
1 file, 2 line changes. ~5 minutes.

</details>

---

## 6. Multiple texts missing German translation

- **Type:** i18n / Localization
- **Severity:** Medium
- **Location:**
  - `frontend/static/i18n/en.json` vs `frontend/static/i18n/de.json`
  - Various JS modules with hardcoded English strings
- **Problem:** Several user-facing texts are hardcoded in English in JS files and are not routed through the i18n system. Examples include:
  - **review.js:** `'Please select a playlist first.'`, `'👎 Disliked & removed: ...'`, `'👍 Liked: ...'`
  - **profile.js:** `'Failed to switch profile.'`, `'Network error: ...'`, `'Delete failed.'`, `'Import failed: file is larger than 10MB.'`, `'Invalid JSON file.'`, `'Import failed: ...'`, `'Profile imported. Previous profile saved to history.'`, `'OpenAI API key is required. Open ⚙️ Settings.'`
  - **audio-filters.js:** `'All audio filters cleared.'`, filter hint descriptions (e.g., `'Calm, ambient'`, `'Energetic'`, `'Dark, melancholic'`)
  - **analysis.js:** `'Artist name is required.'`, `'Analysing…'`, analysis result labels
  - **generate_section.html:** `'Generate AI-powered playlists...'` subtitle, `'Playlist name (supports {date}, {style})'` placeholder, audio filter hint text
  - **playlist_review.html:** `'Select a playlist…'` placeholder
  - **band_analysis.html:** subtitle text `'Get an AI-powered breakdown of any artist or track...'`
  - Various `data-i18n` keys may exist in `en.json` but still use English fallback text in templates
- **Fix:** Audit all JS `showToast()`, `showAlert()`, `textContent =` assignments, and HTML hardcoded strings. Add i18n keys for each, add German translations to `de.json`, and replace hardcoded text with `i18n('key', 'fallback')` calls.
- **Files to change:** `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`, `frontend/static/js/modules/review.js`, `frontend/static/js/modules/profile.js`, `frontend/static/js/modules/audio-filters.js`, `frontend/static/js/modules/analysis.js`, `frontend/templates/generate_section.html`, `frontend/templates/band_analysis.html`, `frontend/templates/playlist_review.html`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Audit phase** — Grep all JS modules for `showToast(`, `showAlert(`, `showConfirm(`, `textContent =`, and hardcoded string literals in template HTML files. Build a comprehensive list of untranslated strings.
2. **Add i18n keys to `en.json`** — For each hardcoded string, create a descriptive key (e.g., `"review_select_playlist_first"`, `"review_liked"`, `"review_disliked_removed"`, `"profile_switch_failed"`, `"profile_network_error"`, `"profile_delete_failed"`, `"profile_import_too_large"`, `"profile_invalid_json"`, `"profile_import_failed"`, `"profile_import_success"`, `"profile_openai_key_required"`, `"audio_filters_cleared"`, `"analysis_artist_required"`, `"analysis_running"`).
3. **Add German translations to `de.json`** — Provide German text for every new key.
4. **Edit JS modules** — Replace each hardcoded string with `i18n('key', 'English fallback')`. Files: `review.js`, `profile.js`, `audio-filters.js`, `analysis.js`.
5. **Edit HTML templates** — For hardcoded text in `generate_section.html`, `band_analysis.html`, `playlist_review.html`, add `data-i18n` attributes and add corresponding keys to both JSON files.
6. **Run tests.**

### Estimated scope
~9 files, ~100+ line changes. This is a **big task** — delegate distinct file groups to sub-agents. ~2–3 hours.

</details>

---

## 7. Audio filters need better evaluation pattern

- **Type:** Feature improvement
- **Severity:** Medium
- **Location:**
  - `frontend/static/js/modules/audio-filters.js` → `HINT_RANGES`, `applyAnalysisFilter()`, `applyAllAnalysisFilters()`
  - `core/src/suggestions.py` → `_format_audio_filters()`
- **Problem:** The current audio filter system uses simple min/max numeric ranges with fixed ±10% (or ±15 BPM for tempo) offsets when applying analysis values. The `HINT_RANGES` descriptors are coarse (4 buckets per feature). The evaluation pattern could be improved for more nuanced filtering.
- **Possible improvements:**
  1. **Finer-grained hint ranges** — More descriptive buckets (e.g., 6–8 levels instead of 4) for more precise feedback.
  2. **Adaptive offset** — Instead of a fixed ±10%, scale the range based on the feature's typical distribution (e.g., narrow for acousticness, wider for energy).
  3. **Preset patterns** — Allow users to select named presets (e.g., "Chill", "Workout", "Focus") that pre-fill all filter ranges at once.
  4. **Range sliders** — Replace number inputs with dual-thumb range sliders for a more intuitive UX.
  5. **GPT prompt integration** — Improve how `_format_audio_filters()` communicates constraints to GPT, perhaps with descriptive language instead of raw numbers.
- **Files to change:** `frontend/static/js/modules/audio-filters.js`, `frontend/templates/generate_section.html`, `frontend/static/css/styles.css`, `core/src/suggestions.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Refine hint ranges** — In `audio-filters.js`, expand `HINT_RANGES` from 4 buckets to 6–8 per feature for more descriptive feedback (e.g., split "Energetic" into "Moderate energy" and "High energy").
2. **Adaptive offset** — Replace fixed ±10% with per-feature offsets:
   - `acousticness`: ±0.08 (narrow — values tend to cluster)
   - `energy`, `valence`: ±0.12 (medium spread)
   - `tempo`: ±12 BPM
   - `danceability`: ±0.10
3. **Preset patterns** — Add a preset dropdown (`<select id="audioFilterPreset">`) above the filter grid with options: "None", "Chill", "Workout", "Focus", "Party". Each preset maps to a predefined set of filter values. Apply via a new `applyPreset(name)` function.
4. **i18n** — Add i18n keys for preset names and new hint labels.
5. **GPT prompt** — In `suggestions.py` → `_format_audio_filters()`, generate descriptive language alongside numbers (e.g., "Energy: 0.7–0.9 (high energy)").
6. **Run tests.**

### Estimated scope
4 files, ~150 lines. ~2 hours. Consider splitting into sub-tasks: (a) hint ranges + offsets, (b) presets, (c) prompt integration.

</details>

---

## ~~8. Empty/unnamed profiles shown in the list~~ ✅

- **Type:** Bug
- **Severity:** Medium
- **Location:**
  - `core/src/profile.py` → `ensure_profile()` (line ~79), `list_profiles()` (line ~503)
  - `data/music_profile.json` — template has `"name": ""`
- **Problem:** When `ensure_profile()` creates a profile file from the template, the template's `"name"` field is empty (`""`). If an active profile ID is set but the profile was never formally created via `create_profile()` (e.g., on first launch or after a migration), a profile with an empty name ends up on disk. `list_profiles()` returns it, and the UI shows it in the dropdown (as `p.name || p.id` — falling back to UUID).
- **Fix:** Filter out nameless profiles in `list_profiles()` so they are treated as internal/temporary:
  ```python
  # In list_profiles(), skip profiles without a name
  name = data.get("name", "")
  if not name:
      continue
  ```
  Alternatively, `ensure_profile()` could be modified to not create a file unless a name is set, but this may break other flows.
- **Files to change:** `core/src/profile.py`, `core/tests/test_profile.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/profile.py`** — In `list_profiles()` (line ~517), after `data = json.load(f)`, add:
   ```python
   name = data.get("name", "")
   if not name:
       continue
   ```
   This skips profiles with empty or missing names.
2. **Update `core/tests/test_profile.py`** — Add a test that creates a profile file with `"name": ""` and verifies `list_profiles()` excludes it.
3. **Run tests.**

### Estimated scope
1 file + 1 test file, ~10 lines. ~15 minutes.

</details>

---

## ~~9. Bug when changing profile mid-session~~ ✅

- **Type:** Bug
- **Severity:** High
- **Location:**
  - `frontend/static/js/modules/profile.js` → `switchProfile()` (line ~182)
  - `app.py` → `activate_profile_endpoint()`, various endpoints reading active profile
  - `core/src/profile.py` → `activate_profile()`, `load_profile()`
  - `frontend/static/js/modules/state.js` — song list, suggestions, cached playlists
- **Problem:** Switching the active profile mid-session updates the backend (`settings.conf`) and refreshes the profile form UI, but does **not** clear or reset client-side state that may belong to the previous profile:
  - **Song list** (`State.suggestions`) still contains tracks from the old profile's generation run.
  - **Feedback** submitted after switching may target the newly active profile's JSON file, but the track context (source profile) is stale.
  - **Audio filters** may still be set from an analysis done in the old profile context.
  - **Run history** may show runs from the previous profile.
  - **Cached playlists** — not profile-specific, but the Discover picker's selected playlist may have been chosen for the old profile.
- **Fix:** On profile switch, clear or reload all session-dependent state:
  1. Clear `State.suggestions` and re-render the discover track list.
  2. Clear the review track list.
  3. Optionally reset audio filters.
  4. Reload run history for the new profile (if history is profile-scoped).
  5. Add a server-side endpoint (or extend the activate response) that returns the new profile's associated state.
- **Files to change:** `frontend/static/js/modules/profile.js`, `frontend/static/js/modules/state.js`, `frontend/static/js/modules/tracklist.js`, `frontend/static/js/modules/review.js`, possibly `app.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/js/modules/profile.js`** — In `switchProfile()`, after the successful backend call, invoke a new `resetSessionState()` function.
2. **Edit `frontend/static/js/modules/state.js`** — Add and export `resetSessionState()`:
   ```js
   export function resetSessionState() {
       suggestions = [];
       reviewTracks = [];
       cachedPlaylists = null;
       openFormIndex = null;
       openFormAction = null;
       currentRunId = null;
       partialTrackCount = 0;
   }
   ```
3. **Edit `frontend/static/js/modules/profile.js`** — After calling `State.resetSessionState()`, also:
   - Call `renderTracks()` from `tracklist.js` to clear the discover track list UI.
   - Call `renderReviewTracks([])` or equivalent to clear the refine track list.
   - Optionally call `clearAllAudioFilters()` from `audio-filters.js`.
   - Reload run history if visible.
4. **Run tests.**

### Estimated scope
3 files, ~30 lines. ~45 minutes.

</details>

---

## ~~10. `charmap` codec error with emoji characters~~ ✅

- **Type:** Bug
- **Severity:** High
- **Location:**
  - `core/src/feedback.py` → `like_track()` (line ~54), `dislike_track()` (line ~99) — `print()` statements with 👍/👎 emojis
- **Problem:** On Windows, `print()` uses the console's default encoding (typically `cp1252` / `charmap`), which cannot encode Unicode emoji like 👍 (`\U0001f44d`) and 👎 (`\U0001f44e`). When running as a PyInstaller EXE (where stdout may not be a proper UTF-8 terminal), this raises:
  ```
  UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f44e' in position 0
  ```
- **Fix options:**
  1. **Remove emojis from print statements** — Replace `👍`/`👎` with plain text like `[LIKED]`/`[DISLIKED]`.
  2. **Set stdout encoding** — Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at startup in `desktop_launcher.py` or `app.py`.
  3. **Wrap prints** — Use a helper that catches `UnicodeEncodeError` and falls back to ASCII.
- **Recommended:** Option 1 is simplest and most robust. These print statements are debug/log output and do not need emojis.
- **Files to change:** `core/src/feedback.py` (primary), optionally `desktop_launcher.py` or `app.py` for a global fix

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/feedback.py`** — Replace emoji characters in `print()` statements:
   - Line ~55: `print(f"👍 Liked: ...")` → `print(f"[LIKED] {artist} - {track}" + ...)`
   - Line ~57: `print(f"👍 Liked artist: ...")` → `print(f"[LIKED] Artist: {artist}" + ...)`
   - Line ~100: `print(f"👎 Disliked: ...")` → `print(f"[DISLIKED] {artist} - {track} ({reason})")`
   - Line ~102: `print(f"👎 Excluded artist: ...")` → `print(f"[EXCLUDED] Artist: {artist} ({reason})")`
2. **Run tests.**

### Note
This issue is fully subsumed by TODO #23 (replace `print()` with `logging`). If #23 is implemented first, this becomes a no-op. Implement this only if #23 is deferred.

### Estimated scope
1 file, 4 line changes. ~5 minutes.

</details>

---

## 11. Delete button in playlist dropdowns

- **Type:** Feature request
- **Severity:** Medium
- **Location:**
  - `frontend/static/js/modules/playlist-mode.js` → `loadDiscoverPicker()` (line ~11)
  - `frontend/static/js/modules/review.js` → `populateReviewPlaylistPicker()` (line ~220)
  - `frontend/templates/generate_section.html` → `#playlistPickerRow` (line ~27)
  - `frontend/templates/playlist_review.html` → `#reviewPlaylistPicker` (line ~15)
  - `core/src/playlist.py` → new `delete_playlist()` function
  - `app.py` → new `DELETE /api/playlist/<playlist_id>` endpoint
- **Problem:** Both playlist dropdowns (Discover section's Append/Replace picker and Refine Playlist picker) render a plain `<select>` element. There is no way to delete a playlist without leaving SpotyVibe and opening Spotify. Users who accumulate many generated playlists cannot clean up directly from the app.
- **Desired behaviour:**
  1. Each playlist entry in **both** dropdowns shows a **delete icon** (🗑 / ✕) on the right side.
  2. Clicking the delete icon opens a **confirmation prompt** (using the existing `showConfirm()` dialog from `frontend/static/js/modules/ui.js`) with the message: *"Are you sure? This will permanently remove the playlist «{name}» from your Spotify account!"*
  3. If the user **confirms**, the playlist is deleted via the Spotify API and the dropdown re-renders without it.
  4. If the user **declines**, nothing happens — the playlist remains untouched.
- **Implementation details:**
  - **Backend — new function in `core/src/playlist.py`:**
    ```python
    def delete_playlist(playlist_id):
        """Unfollow (delete) a Spotify playlist by ID."""
        sp = get_spotify_client()
        sp.current_user_unfollow_playlist(playlist_id)
    ```
    Spotify does not have a true "delete" — `current_user_unfollow_playlist()` is the correct spotipy method. For playlists the user owns, unfollowing effectively deletes them.
  - **Backend — new endpoint in `app.py`:**
    ```python
    @app.route("/api/playlist/<playlist_id>", methods=["DELETE"])
    def delete_playlist_endpoint(playlist_id):
        try:
            delete_playlist(playlist_id)
            return jsonify(ok=True)
        except Exception as e:
            return jsonify(error=str(e)), 500
    ```
  - **Frontend — replace `<select>` with a custom dropdown list:** A native `<select>` element does not support inline buttons per option. The picker must be converted to a **custom dropdown** (e.g., a `<div>` with `role="listbox"` and individual `<div role="option">` items). Each item renders the playlist name on the left and a delete icon button on the right. The custom dropdown must:
    - Replicate native select keyboard behaviour (arrow keys, Enter to select, Escape to close).
    - Support `aria-expanded`, `aria-activedescendant`, `role="listbox"` / `role="option"` for accessibility.
    - Use the same visual styling as the current `.playlist-picker-select`.
    - Be reusable across both Discover and Refine sections (extract a shared component or utility function).
  - **Frontend — delete flow (JS):**
    1. Click delete icon → call `showConfirm('Are you sure? This will permanently remove the playlist "NAME" from your Spotify account!')`.
    2. On confirm → `fetch('/api/playlist/' + id, { method: 'DELETE' })`.
    3. On success → `State.invalidateCachedPlaylists()`, re-render both pickers, show success toast.
    4. On decline → no-op.
  - **i18n:** Add keys for the confirmation message, delete button aria-label, and success/error toasts to `en.json` and `de.json`.
  - **CSS:** Style the delete icon (small, subtle, red on hover) and the custom dropdown container.
- **Files to change:** `core/src/playlist.py`, `app.py`, `frontend/static/js/modules/playlist-mode.js`, `frontend/static/js/modules/review.js`, `frontend/templates/generate_section.html`, `frontend/templates/playlist_review.html`, `frontend/static/css/styles.css`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`, `core/tests/test_playlist.py`, `core/tests/test_app.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Backend — `core/src/playlist.py`** — Add `delete_playlist(playlist_id)` function:
   ```python
   def delete_playlist(playlist_id):
       sp = get_spotify_client()
       sp.current_user_unfollow_playlist(playlist_id)
   ```
2. **Backend — `app.py`** — Add `DELETE /api/playlist/<playlist_id>` endpoint that calls `delete_playlist()`, returns `jsonify(ok=True)` on success or `jsonify(error=str(e)), 500` on failure.
3. **Frontend — Custom dropdown component** — Replace native `<select>` in both pickers with a custom dropdown `<div>` structure:
   - Container: `<div class="custom-playlist-picker" role="listbox" aria-expanded="false">`
   - Trigger button: shows selected playlist name, toggles dropdown open/closed.
   - Items: `<div role="option">` with playlist name on left, delete icon `<button>` on right.
   - Keyboard: Arrow keys navigate, Enter selects, Escape closes, Delete on focused item triggers delete flow.
   - Extract as a reusable function `createPlaylistPicker(containerId, onSelect, onDelete)` in a new module `frontend/static/js/modules/playlist-picker.js`.
4. **Frontend — Delete flow** — On delete icon click: `showConfirm(i18n('playlist_delete_confirm', '...'))` → on confirm: `fetch('/api/playlist/' + id, { method: 'DELETE' })` → on success: `State.invalidateCachedPlaylists()`, re-render both pickers, show success toast.
5. **CSS** — Add styles for `.custom-playlist-picker`, `.playlist-option`, `.playlist-delete-btn` (small, subtle, red on hover).
6. **i18n** — Add keys: `playlist_delete_confirm`, `playlist_delete_success`, `playlist_delete_error`, `playlist_delete_aria`.
7. **Tests** — Add test for `delete_playlist()` in `core/tests/test_playlist.py` (mock `sp.current_user_unfollow_playlist`). Add endpoint test in `core/tests/test_app.py`.
8. **Run tests.**

### Estimated scope
~11 files, ~200+ lines. This is a **big task** — split into sub-agents: (a) backend endpoint + tests, (b) custom dropdown component, (c) delete flow integration + i18n. ~3–4 hours.

</details>

---

## ~~12. Jump bubble overlaps interactive elements on mobile~~ ✅

- **Type:** UI bug / Mobile UX
- **Severity:** High
- **Location:**
  - `frontend/static/css/styles.css` → `.section-jump-bubble` (line ~3824), phone breakpoint (line ~2398)
  - `frontend/static/js/modules/jump-bubble.js` → `initJumpBubble()`, `update()`
  - `frontend/templates/base.html` → `#sectionJumpBubble` button (line ~62)
- **Problem:** The jump bubble is a 56×56px fixed-position button pinned to the **bottom-right corner** on mobile (`right: 16px; bottom: 20px`). On phone-sized screens this position overlaps with:
  1. **Track action buttons** (Like / Dislike / Remove) on song cards — the track list renders below the Generate/Refine sections and the bottom card's action buttons sit right where the bubble is.
  2. **Toast notifications** — toasts are positioned at `bottom: 1rem` and stretch `left: 1rem; right: 1rem` on phones. An active toast and the bubble occupy the same vertical band.
  3. **"Use X tracks now" / Cancel buttons** during generation — these stack vertically full-width at `≤480px` and the bottom button can be partially hidden behind the bubble.
  4. **Audio filter inputs** — when the filter panel is expanded and the user scrolls so it sits at the bottom, the last filter row's inputs can be covered.
  5. On the **Android APK** (Chaquopy WebView), the bubble has no way to be dismissed and permanently covers part of the UI — there is no desktop-like "just move the window" workaround.
- **Fix:** **Hide the jump bubble entirely on mobile.** On small screens the page is a single vertical scroll — the two provider sections (OpenAI, Spotify) follow each other naturally and a jump shortcut provides minimal value compared to the real estate it consumes. The simplest approach:
  ```css
  /* In the ≤ 480px breakpoint */
  .section-jump-bubble {
      display: none !important;
  }
  ```
  Alternatively, if the bubble should be kept on tablets (`≤768px`), restrict `display: none` to `≤480px` only. The JS in `jump-bubble.js` already handles the `.hidden` class gracefully, so no JS changes are needed — CSS alone is sufficient.
- **Files to change:** `frontend/static/css/styles.css`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/css/styles.css`** — In the `≤480px` media query breakpoint, add:
   ```css
   .section-jump-bubble {
       display: none !important;
   }
   ```
2. **No JS changes needed** — `jump-bubble.js` already handles the `.hidden` class gracefully.
3. **Run tests.**

### Estimated scope
1 file, 3 lines. ~5 minutes.

</details>

---

## ~~13. Toast notification overlaps jump bubble and bottom buttons on mobile~~ ✅

- **Type:** UI bug / Mobile UX
- **Severity:** Medium
- **Location:**
  - `frontend/static/css/styles.css` → `.toast` (line ~1594), phone breakpoint (line ~2213, 2460)
  - `frontend/templates/toast.html`
- **Problem:** On the `≤480px` breakpoint, toasts are positioned `bottom: max(1rem, env(safe-area-inset-bottom))` and span the full width (`left: 1rem; right: 1rem`). This causes visual overlap with:
  1. The **jump bubble** (if not hidden per TODO #12) — both sit in the bottom-right corner at the same z-level band.
  2. **Full-width action buttons** (Generate, Cancel, Use X Tracks) that stack vertically — a toast appearing during generation covers part of the cancel/use-now button row.
  3. The **settings dropdown** on phone — it slides up from the bottom (`position: fixed; bottom: 0`) and occupies up to 60vh. If a toast fires while the menu is open, they overlap.
- **Fix:** Move toasts to the **top** of the viewport on mobile to avoid conflicting with bottom-anchored UI (buttons, bubble, bottom-sheet menus). This matches the Android notification pattern where alerts appear at the top:
  ```css
  @media (max-width: 480px) {
      .toast {
          bottom: auto;
          top: 1rem;
          top: max(1rem, env(safe-area-inset-top));
          left: 1rem;
          right: 1rem;
          transform: translateY(-80px);  /* slide in from above */
      }
      .toast.show {
          transform: translateY(0);
      }
  }
  ```
  This avoids fighting for the same bottom edge as the settings sheet, bubble, and action buttons.
- **Files to change:** `frontend/static/css/styles.css`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/css/styles.css`** — In the `≤480px` breakpoint, override the `.toast` position to top:
   ```css
   @media (max-width: 480px) {
       .toast {
           bottom: auto;
           top: max(1rem, env(safe-area-inset-top));
           left: 1rem;
           right: 1rem;
           transform: translateY(-80px);
       }
       .toast.show {
           transform: translateY(0);
       }
   }
   ```
2. **Verify** that the toast slide-in animation direction reverses correctly (slides down from above instead of up from below).
3. **Run tests.**

### Estimated scope
1 file, ~10 lines. ~15 minutes.

</details>

---

## ~~14. Preview overlay feedback panel overflows on small phones~~ ✅

- **Type:** UI bug / Mobile UX
- **Severity:** Medium
- **Location:**
  - `frontend/static/css/styles.css` → preview overlay phone breakpoint (line ~2311)
  - `frontend/templates/preview_overlay.html`
- **Problem:** On phones (`≤480px`), the preview overlay stacks vertically: player → action tabs → feedback panel. When the feedback form slides in (artist, track, reason fields + two buttons), the total height of all three zones **exceeds `100dvh`** on shorter devices (e.g., older 5" Android phones, phones with a large nav-bar). The feedback form is pushed partially off-screen below the viewport and cannot be scrolled to because the overlay has no overflow scrolling on its content.
  - The `preview-layout` uses `max-height: 100dvh` but the panel itself (`.preview-feedback-panel`) has no `overflow-y: auto`, so the form fields and submit button can be unreachable.
  - The Spotify embed iframe alone is ~190px, the title/counter ~40px, the tab strip ~76px, and the feedback form ~230px — totalling ~536px. On a 640px-tall viewport with safe-area insets, the submit button is clipped.
- **Fix:**
  1. Add `overflow-y: auto` to `.preview-layout` or `.preview-feedback-panel` in the `≤480px` breakpoint so the content can be scrolled.
  2. Consider reducing the iframe `height` attribute from `190` to `152` on mobile (Spotify supports a compact embed height of 152px).
  3. Alternatively, collapse the player (hide the iframe) when the feedback form is open, similar to how a mobile keyboard pushes content up.
- **Files to change:** `frontend/static/css/styles.css`, possibly `frontend/static/js/modules/preview.js` (for dynamic iframe height)

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/css/styles.css`** — In the `≤480px` breakpoint for the preview overlay:
   - Add `overflow-y: auto` to `.preview-layout` to enable scrolling when content exceeds viewport.
   - Optionally reduce the Spotify embed iframe height: add a rule `.preview-layout iframe { height: 152px; }` for compact mode.
2. **Verify** on a 640px-tall viewport that the feedback form fields and submit button are fully reachable via scroll.
3. **Run tests.**

### Estimated scope
1 file, ~5 lines. ~15 minutes.

</details>

---

## ~~15. Audio filter hint text truncated / overflows on narrow phones~~ ✅

- **Type:** UI bug / Mobile UX
- **Severity:** Low
- **Location:**
  - `frontend/static/css/styles.css` → `.audio-filter-hint-text` (line ~3112), phone breakpoint (line ~2284)
  - `frontend/templates/generate_section.html` → audio filter grid
- **Problem:** At `≤480px`, the audio filter grid switches to `grid-template-columns: 1fr 1fr` (two columns: min and max inputs). The label spans both columns and the hint text (`↳ Energetic to Intense`) also spans both via `grid-column: 1 / -1`. However:
  1. The hint text has `white-space: nowrap` and `min-width: 100px` — on a 320px-wide device with padding, long hints like `"↳ Calm, ambient to Dark, melancholic"` can overflow the grid and cause horizontal scrolling on the entire page.
  2. The "⇒ Filter" buttons in analysis results (`.af-use-btn`) are tiny touch targets (`padding: 2px 8px`, no `min-height`) — well below the 44px touch target recommended for mobile. They are difficult to tap accurately.
  3. The "✕ Clear all" button in the filter header has the same small-target problem.
- **Fix:**
  1. Remove `white-space: nowrap` from `.audio-filter-hint-text` in the `≤480px` breakpoint, or set `overflow: hidden; text-overflow: ellipsis` to prevent page-level horizontal scroll.
  2. Add `min-height: 36px` and `padding: 6px 12px` to `.af-use-btn` in the mobile breakpoint for touch-friendly targets.
  3. Add `min-height: 36px` to `.audio-filter-clear-btn` in the mobile breakpoint.
- **Files to change:** `frontend/static/css/styles.css`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/css/styles.css`** — In the `≤480px` breakpoint:
   - Override `.audio-filter-hint-text` to remove `white-space: nowrap` and add `overflow: hidden; text-overflow: ellipsis; word-break: break-word;`.
   - Add `min-height: 36px; padding: 6px 12px;` to `.af-use-btn` for touch-friendly targets.
   - Add `min-height: 36px;` to `.audio-filter-clear-btn`.
2. **Run tests.**

### Estimated scope
1 file, ~10 lines. ~10 minutes.

</details>

---

## ~~16. Section help (?) icon too small for touch on mobile~~ ✅

- **Type:** Accessibility / Mobile UX
- **Severity:** Medium
- **Location:**
  - `frontend/static/css/styles.css` → `.section-help-icon` (line ~1361)
  - Templates: `train_profile.html`, `band_analysis.html`, `generate_section.html`, `playlist_review.html`, `run_history.html`
- **Problem:** The `?` section help icons are `20×20px` with no extra touch padding. The WCAG / Android minimum touch target size is `44×44px` (48dp recommended by Material Design). On phones, these icons are:
  1. Extremely difficult to tap — they sit inline within the section `<h2>` title text and are only 20px circles. Users often accidentally tap the section header (toggling expand/collapse) instead of the help icon.
  2. The `top: -4px` relative offset shifts the icon upward, further reducing its effective touch area and misaligning it with the baseline of the heading text on mobile.
  3. Each icon uses `event.stopPropagation()` to prevent header click-through, but on touch the imprecise hit area means the `stopPropagation` never fires and the header toggle activates instead.
- **Fix:** Increase the touch target on mobile without changing the visual size. The standard technique is an invisible padding area:
  ```css
  @media (max-width: 480px) {
      .section-help-icon {
          /* Enlarge touch target to 44×44 without changing visual size */
          position: relative;
          width: 20px;
          height: 20px;
      }
      .section-help-icon::after {
          content: '';
          position: absolute;
          top: -12px;
          left: -12px;
          right: -12px;
          bottom: -12px;
      }
  }
  ```
  Alternatively, simply increase the icon's visible size to `28×28px` and add `padding: 4px` on mobile, which also improves visibility.
- **Files to change:** `frontend/static/css/styles.css`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `frontend/static/css/styles.css`** — In the `≤480px` breakpoint, enlarge the touch target using an invisible pseudo-element:
   ```css
   @media (max-width: 480px) {
       .section-help-icon {
           position: relative;
       }
       .section-help-icon::after {
           content: '';
           position: absolute;
           top: -12px;
           left: -12px;
           right: -12px;
           bottom: -12px;
       }
   }
   ```
2. **Run tests.**

### Estimated scope
1 file, ~12 lines. ~10 minutes.

</details>

---

## ~~17. Path traversal via unvalidated profile ID~~ ✅

- **Type:** Security bug
- **Severity:** Critical
- **Source:** Core code review §2.1
- **Location:**
  - `config.py` → `get_active_profile_path()` (line ~375)
  - `core/src/profile.py` → `delete_profile()` (line ~571), `activate_profile()` (line ~594)
- **Problem:** Profile IDs are used directly in file paths (`PROFILES_DIR / f"{pid}.json"`) without validation. While `create_profile()` generates UUIDs, `activate_profile()` and `delete_profile()` accept an externally-supplied `profile_id` from the API endpoint. A malicious value like `../../.credentials` would resolve to a path outside `PROFILES_DIR`, potentially allowing reading or deleting arbitrary files.
- **Fix:**
  1. Validate that `profile_id` matches a UUID pattern (`^[a-f0-9-]{36}$`) before constructing any file path.
  2. After constructing the path, verify `resolved_path.parent == PROFILES_DIR.resolve()` as a defence-in-depth check.
  3. Apply validation in both `config.py` (`get_active_profile_path()`) and `profile.py` (`delete_profile()`, `activate_profile()`).
- **Files to change:** `config.py`, `core/src/profile.py`, `core/tests/test_profile.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Add a validation helper in `config.py`** — Create a `validate_profile_id(profile_id)` function:
   ```python
   import re as _re
   _UUID_PATTERN = _re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')

   def validate_profile_id(profile_id):
       """Validate that a profile ID is a well-formed UUID.
       Raises ValueError if the ID doesn't match the UUID pattern.
       """
       if not profile_id or not _UUID_PATTERN.match(profile_id):
           raise ValueError(f"Invalid profile ID: {profile_id!r}")
   ```
2. **Edit `config.py` → `get_active_profile_path()` and `get_active_history_path()`** — Call `validate_profile_id(pid)` before constructing the path. If `pid` is empty, return `None` as before (don't validate empty).
3. **Edit `core/src/profile.py` → `delete_profile()`** (line ~568) — Call `validate_profile_id(profile_id)` at the top, before constructing `profile_path`.
4. **Edit `core/src/profile.py` → `activate_profile()`** (line ~591) — Call `validate_profile_id(profile_id)` at the top.
5. **Defence-in-depth** — After constructing any profile path, add an assertion:
   ```python
   resolved = profile_path.resolve()
   if resolved.parent != PROFILES_DIR.resolve():
       raise ValueError("Profile path escapes the profiles directory.")
   ```
6. **Update tests** — In `core/tests/test_profile.py`, add tests:
   - `test_delete_profile_rejects_traversal`: call `delete_profile("../../.credentials")` → expect `ValueError`.
   - `test_activate_profile_rejects_traversal`: call `activate_profile("../../.credentials")` → expect `ValueError`.
   - `test_validate_profile_id_valid`: verify a valid UUID passes.
   - `test_validate_profile_id_invalid`: verify `..`, `../../x`, non-UUID strings all raise `ValueError`.
7. **Run tests.**

### Estimated scope
2 files + 1 test file, ~35 lines. ~30 minutes.

</details>

---

## 18. Credential storage with OS keychain (keyring library)

- **Type:** Security improvement
- **Severity:** Medium
- **Source:** Core code review §2.2
- **Location:**
  - `config.py` — credential read/write functions, `.credentials` file handling
- **Problem:** API keys (OpenAI, Spotify client ID/secret) are stored in a plain-text dotenv file at `%LOCALAPPDATA%\spotyvibe\.credentials`. Any process running as the same user can read these.
- **Fix:** Use the `keyring` library to store credentials in the OS keychain instead of plain-text files. Requirements:
  1. Must also work on **Android** (Chaquopy) — investigate `keyring` backend availability or provide a graceful fallback to the current file-based approach on platforms without keychain support.
  2. Users must still be able to **update credentials through the application UI** (Settings modal).
  3. Migration path: on first launch after the change, read existing `.credentials` values, store them in the keychain, and optionally remove the plain-text file.
- **Files to change:** `config.py`, `requirements.txt`, `android/app/build.gradle` (pip pins), `core/tests/test_config.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Research phase** — Investigate `keyring` library:
   - On Windows: uses Windows Credential Locker (built-in). ✅
   - On Android/Chaquopy: `keyring` has no backend. Need a fallback. → Use `keyring` with a try/except import; fall back to the current dotenv file on Android.
   - API: `keyring.set_password(service, key, value)`, `keyring.get_password(service, key)`.
2. **Add `keyring` to `requirements.txt`** — Add `keyring>=25.0`.
3. **Do NOT add `keyring` to Android pip pins** — Instead, implement a runtime check in `config.py`.
4. **Edit `config.py`** — Create a credential abstraction layer:
   ```python
   _USE_KEYRING = False
   try:
       import keyring
       if not IS_ANDROID:
           _USE_KEYRING = True
   except ImportError:
       pass

   SERVICE_NAME = "spotyvibe"

   def _read_credential(key):
       if _USE_KEYRING:
           val = keyring.get_password(SERVICE_NAME, key)
           if val is not None:
               return val
       # Fallback: read from .credentials file
       return dotenv_values(str(CREDENTIALS_FILE)).get(key, "")

   def _write_credential(key, value):
       if _USE_KEYRING:
           if value:
               keyring.set_password(SERVICE_NAME, key, value)
           else:
               try: keyring.delete_password(SERVICE_NAME, key)
               except keyring.errors.PasswordDeleteError: pass
       # Always also write to .credentials for backward compatibility
       set_key(str(CREDENTIALS_FILE), key, value)
   ```
5. **Edit `save_credentials()`** — Use `_write_credential()` for each key instead of direct `set_key()`.
6. **Edit `load_config()`** — After `load_dotenv()`, override `os.environ` with keyring values for each `CREDENTIAL_KEYS` entry.
7. **Migration** — In `load_config()`, on first run with keyring available: read existing `.credentials` values, store them in keyring, optionally log that migration occurred.
8. **Ensure UI still works** — `save_credentials()` and `get_credentials()` continue to work through the application's Settings modal. No frontend changes needed.
9. **Update tests** — Mock `keyring` in `core/tests/test_config.py`. Test both keyring-available and keyring-unavailable paths.
10. **Run tests.**

### Estimated scope
2 files + 1 test file, ~60 lines. ~1–2 hours.

### Risks
- `keyring` on Linux may require `secretstorage` + D-Bus, which may not be available in CI. → Use `keyring.backends.null.Keyring` or mock in tests.
- Ensure the `.credentials` file fallback always works so no user loses access.

</details>

---

## ~~19. `debug_log()` creates directory for wrong file~~ ✅

- **Type:** Bug
- **Severity:** High
- **Source:** Core code review §1.1
- **Location:**
  - `core/src/utils.py` → `debug_log()` (line ~67)
- **Problem:** The function creates the parent directory of `DEBUG_LOG_FILE` but then writes to `PROMPT_LOG_FILE`. If the two paths ever diverge (e.g. different subdirectories), this would silently fail.
- **Fix:** Use `PROMPT_LOG_FILE.parent.mkdir(...)` to match the actual write target, or extract a single `ensure_log_dir()` helper that both log functions share.
- **Files to change:** `core/src/utils.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/utils.py`** — In `debug_log()` (line ~67), change:
   ```python
   DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
   ```
   to:
   ```python
   PROMPT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
   ```
   This matches the actual write target (`PROMPT_LOG_FILE`).
2. **Run tests.**

### Estimated scope
1 file, 1 line change. ~5 minutes.

</details>

---

## ~~20. `swap_profile_with_history()` not thread-safe~~ ✅

- **Type:** Bug
- **Severity:** High
- **Source:** Core code review §1.2
- **Location:**
  - `core/src/profile.py` → `swap_profile_with_history()` (lines ~119–145)
- **Problem:** The function performs a three-step file rename (profile → tmp, history → profile, tmp → history) **without** holding `_profile_lock`. Concurrent requests (e.g. feedback submission) could read a partially-swapped state or get a `FileNotFoundError`.
- **Fix:** Wrap the entire swap sequence in `with _profile_lock:`.
- **Files to change:** `core/src/profile.py`, `core/tests/test_profile.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/profile.py`** — Wrap the entire body of `swap_profile_with_history()` (lines ~128–145) in `with _profile_lock:`. The function currently calls `ensure_profile()` and `load_profile()` which each acquire the lock independently — these must now use internal unlocked variants to avoid deadlock.
2. **Create unlocked internal helpers** — Extract `_ensure_profile_unlocked()` and `_load_profile_unlocked()` that do the file I/O without acquiring `_profile_lock`. The public `ensure_profile()` and `load_profile()` call these inside `with _profile_lock:`.
3. **Rewrite `swap_profile_with_history()`:**
   ```python
   def swap_profile_with_history():
       profile_path, history_path = _require_active_profile()
       with _profile_lock:
           _ensure_profile_unlocked()
           if not history_path.exists():
               raise ValueError("No history profile exists yet.")
           profile_path.parent.mkdir(parents=True, exist_ok=True)
           tmp = profile_path.parent / (profile_path.name + ".swap.tmp")
           if tmp.exists():
               tmp.unlink()
           profile_path.rename(tmp)
           history_path.rename(profile_path)
           tmp.rename(history_path)
           with open(profile_path, "r", encoding="utf-8") as f:
               return json.load(f)
   ```
4. **Update tests** — Verify swap is atomic under concurrent access.
5. **Run tests.**

### Estimated scope
1 file, ~30 lines refactored. ~30 minutes.

### Note
This is closely related to TODO #25 (lock granularity). Consider implementing both together.

</details>

---

## ~~21. `save_profile_sections()` skips input sanitisation~~ ✅

- **Type:** Bug
- **Severity:** Medium
- **Source:** Core code review §1.3
- **Location:**
  - `core/src/profile.py` → `save_profile_sections()` (line ~349)
- **Problem:** `save_profile_sections()` directly stores user-provided text into the profile without calling `sanitize_text()`. All other save paths (`import_profile_dict`, `train_profile`) sanitise input. This path allows control characters, null bytes, or oversized content.
- **Fix:** Apply `sanitize_text()` to each section value and enforce `MAX_CORE_DESCRIPTION_LEN` / `MAX_PROFILE_SECTION_LEN` limits.
- **Files to change:** `core/src/profile.py`, `core/tests/test_profile.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/profile.py`** — In `save_profile_sections()` (line ~347), add sanitisation after reading `sections`:
   ```python
   from .utils import sanitize_text
   from config import MAX_CORE_DESCRIPTION_LEN, MAX_PROFILE_SECTION_LEN

   vibe = sanitize_text(sections.get("vibe_description", ""))[:MAX_PROFILE_SECTION_LEN]
   core = sanitize_text(sections.get("core_description", ""))[:MAX_CORE_DESCRIPTION_LEN]
   profile["preferences"]["vibe_description"] = vibe
   profile["preferences"]["core_description"] = core
   ```
   Also sanitise each line in the list fields (`must_have`, `soft_preferences`, `avoid`):
   ```python
   profile["preferences"]["must_have"] = [
       sanitize_text(line.strip())[:MAX_PROFILE_SECTION_LEN]
       for line in sections.get("must_have", "").splitlines()
       if line.strip()
   ]
   ```
   Repeat for `soft_preferences` and `avoid`.
2. **Note:** `sanitize_text` is already imported via `from .utils import ...` at the top of the file. Verify the import exists; if not, add it.
3. **Update tests** — In `core/tests/test_profile.py`, add `test_save_profile_sections_sanitizes_input` that passes control characters and verifies they are stripped.
4. **Run tests.**

### Estimated scope
1 file + 1 test file, ~20 lines. ~20 minutes.

</details>

---

## ~~22. `add_to_playlist()` fragile `None` guard on return~~ ✅

- **Type:** Bug
- **Severity:** Medium
- **Source:** Core code review §1.5
- **Location:**
  - `core/src/playlist.py` → `add_to_playlist()` (line ~501)
- **Problem:** After the try/except block, the code unconditionally accesses `playlist["external_urls"]` and `playlist["id"]`. If `playlist` is `None` due to an unexpected code path, this crashes. The logic is currently prevented by flow, but it is fragile.
- **Fix:** Add a guard before the return: `if not playlist: raise RuntimeError("No playlist resolved")`.
- **Files to change:** `core/src/playlist.py`, `core/tests/test_playlist.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/playlist.py`** — Before the return statement at line ~501, add:
   ```python
   if not playlist:
       raise RuntimeError("No playlist resolved — unexpected state in add_to_playlist().")
   ```
2. **Update tests** — In `core/tests/test_playlist.py`, add a test that verifies the RuntimeError is raised if `playlist` somehow ends up as `None` (mock the internal calls to simulate the edge case).
3. **Run tests.**

### Estimated scope
1 file + 1 test file, ~5 lines. ~10 minutes.

</details>

---

## ~~23. Replace `print()` with Python `logging` module~~ ✅

- **Type:** Logging / Operational
- **Severity:** High
- **Source:** Core code review §4.1, §4.2, §4.3
- **Location:** All core modules (`playlist.py`, `suggestions.py`, `feedback.py`, `profile.py`, `utils.py`, etc.)
- **Problem:**
  1. The entire codebase uses bare `print()` for diagnostic output. In EXE deployments, `stdout` may not exist or may use `cp1252`, causing `UnicodeEncodeError`. On Android/Chaquopy, `print()` output is lost entirely.
  2. `debug_log()` and `app_log()` are gated behind `get_debug_mode()` — in normal use, **zero diagnostic information** is recorded.
  3. Log files (`PROMPT_LOG_FILE`) have no size limit or rotation — extended debug use can accumulate hundreds of MB.
- **Fix:**
  1. Replace all `print()` calls with `logging` using appropriate levels (`logger.info()`, `logger.warning()`, `logger.debug()`).
  2. Configure a `RotatingFileHandler` in `config.py` or `app.py` with `errors='replace'` to prevent encoding crashes.
  3. Introduce baseline logging that always records critical events (API errors, profile saves, playlist operations) regardless of debug mode. Reserve `debug_log()` for verbose GPT prompt/response dumps.
  4. Add log rotation or size checks to `debug_log()`.
- **Files to change:** All core modules, `config.py`, `app.py`, `desktop_launcher.py`
- **Note:** This also resolves TODO #10 (`charmap` codec emoji error), since `logging` with `errors='replace'` handles emoji safely.

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Configure logging in `app.py`** — At the top of `app.py` (before Flask app creation), set up the logging infrastructure:
   ```python
   import logging
   from logging.handlers import RotatingFileHandler
   from config import DEBUG_LOG_FILE, get_debug_mode

   def setup_logging():
       log_dir = DEBUG_LOG_FILE.parent
       log_dir.mkdir(parents=True, exist_ok=True)
       
       # Root logger — always captures WARNING+
       root = logging.getLogger()
       root.setLevel(logging.DEBUG)
       
       # File handler — always active, rotates at 5MB, keeps 3 backups
       fh = RotatingFileHandler(
           str(DEBUG_LOG_FILE), maxBytes=5*1024*1024, backupCount=3,
           encoding='utf-8', errors='replace'
       )
       fh.setLevel(logging.INFO)
       fh.setFormatter(logging.Formatter(
           '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
           datefmt='%Y-%m-%d %H:%M:%S'
       ))
       root.addHandler(fh)
       
       # Console handler — for development
       ch = logging.StreamHandler()
       ch.setLevel(logging.DEBUG if get_debug_mode() else logging.WARNING)
       ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
       root.addHandler(ch)
   ```
   Call `setup_logging()` after `load_config()`.
2. **Edit each core module** — Replace `print()` calls with logger calls. Each module gets its own logger:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
   Mapping:
   - `print(f"Removed from playlist: ...")` → `logger.info("Removed from playlist: %s - %s", artist, track)`
   - `print(f"Not found on Spotify: ...")` → `logger.warning("Not found on Spotify: %s", result_data)`
   - `print(f"Spotify search error for ...")` → `logger.error("Spotify search error for %s: %s", label, e)`
   - `print(f"Filtered (rejected/disliked artist): ...")` → `logger.debug("Filtered (rejected): %s", artist)`
   - `print(f"👍 Liked: ...")` → `logger.info("[LIKED] %s - %s", artist, track)`
   - `print(f"👎 Disliked: ...")` → `logger.info("[DISLIKED] %s - %s (%s)", artist, track, reason)`
   
   Files to edit: `playlist.py`, `suggestions.py`, `feedback.py`, `profile.py`, `utils.py`, `history.py`, `analysis.py`, `spotify_metadata.py`.
3. **Update `debug_log()` in `utils.py`** — Keep for verbose GPT prompt/response dumps, but add rotation:
   ```python
   PROMPT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
   # Size check — rotate if > 50MB
   if PROMPT_LOG_FILE.exists() and PROMPT_LOG_FILE.stat().st_size > 50 * 1024 * 1024:
       rotated = PROMPT_LOG_FILE.with_suffix('.log.1')
       if rotated.exists():
           rotated.unlink()
       PROMPT_LOG_FILE.rename(rotated)
   ```
4. **Update `app_log()` in `utils.py`** — Remove the `get_debug_mode()` gate for baseline events. Use `logger.info()` instead of manual file writes.
5. **Update `desktop_launcher.py`** — Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` as a safety net for any remaining stdout usage.
6. **Run tests.**

### Estimated scope
~10 files, ~100+ line changes. This is a **big task** — split into sub-agents: (a) logging setup in `app.py` + `utils.py`, (b) `playlist.py` + `feedback.py` migration, (c) `suggestions.py` + remaining modules. ~2–3 hours.

### Note
Resolves TODO #10 (`charmap` codec emoji error) as a side effect.

</details>

---

## ~~24. Silent exception swallowing in multiple locations~~ ✅

- **Type:** Bug / Logging
- **Severity:** Medium
- **Source:** Core code review §4.4
- **Location:**
  - `core/src/playlist.py` → `get_spotify_auth_status()` (line ~148), `handle_spotify_callback()` (lines ~178–180), `disconnect_spotify()` (lines ~163–165)
  - `core/src/history.py` → `_load_history()` (line ~24)
  - `core/src/utils.py` → `clear_debug_log()` (line ~77)
- **Problem:** Exceptions are either discarded entirely or printed to stdout (where they may be lost). This makes debugging production issues extremely difficult.
- **Fix:** Log caught exceptions at `WARNING` or `ERROR` level. For user-facing functions, propagate a meaningful error message.
- **Files to change:** `core/src/playlist.py`, `core/src/history.py`, `core/src/utils.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Prerequisite:** TODO #23 (logging module) should ideally be done first. If not, use `print()` as an interim measure.
2. **Edit `core/src/playlist.py`:**
   - `get_spotify_auth_status()` (line ~148): Change `except Exception:` to `except Exception as e:` and add `logger.warning("Spotify auth check failed: %s", e)`.
   - `handle_spotify_callback()` (lines ~178–180): Add `logger.error("Spotify callback error: %s", e)`.
   - `disconnect_spotify()` (lines ~163–165): Add `logger.error("Error removing Spotify cache: %s", e)`.
3. **Edit `core/src/history.py`:**
   - `_load_history()` (line ~24): Add `logger.warning("Failed to load run history: %s", e)` in the except block (currently silently swallows `JSONDecodeError` and `OSError`).
4. **Edit `core/src/utils.py`:**
   - `clear_debug_log()` (line ~77): Add `logger.warning("Failed to delete log file %s: %s", f, e)` in the except block.
5. **Run tests.**

### Estimated scope
3 files, ~10 lines. ~15 minutes (assumes logging is already set up per TODO #23).

### Dependency
Implement after TODO #23. If #23 is deferred, use `print(f"WARNING: ...", file=sys.stderr)` as a temporary measure.

</details>

---

## ~~25. Profile lock granularity allows lost updates~~ ✅

- **Type:** Code quality / Bug
- **Severity:** Medium
- **Source:** Core code review §5.1
- **Location:**
  - `core/src/profile.py` → `load_profile()`, `save_profile()`, `train_profile()`
  - `core/src/feedback.py` → `like_track()`, `dislike_track()`
- **Problem:** `load_profile()` and `save_profile()` each acquire `_profile_lock` independently. Functions like `train_profile()` call `load_profile()` (acquires → releases), do processing, then call `save_profile()` (acquires → releases). Between load and save, another thread could modify the profile, causing a lost-update bug.
- **Fix:** Provide a context-manager API for the profile lock, or use a higher-level read-modify-write function that holds the lock for the entire cycle.
- **Files to change:** `core/src/profile.py`, `core/src/feedback.py`, `core/tests/test_profile.py`, `core/tests/test_feedback.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/profile.py`** — Create a context-manager API for the profile lock:
   ```python
   from contextlib import contextmanager

   @contextmanager
   def profile_transaction():
       """Hold _profile_lock for the entire read-modify-write cycle.
       
       Usage:
           with profile_transaction() as (load_fn, save_fn):
               data = load_fn()
               data["field"] = "value"
               save_fn(data)
       """
       with _profile_lock:
           def _load():
               profile_path, _ = _require_active_profile()
               _ensure_profile_unlocked()
               with open(profile_path, "r", encoding="utf-8") as f:
                   return json.load(f)
           
           def _save(profile):
               profile_path, history_path = _require_active_profile()
               if profile_path.exists():
                   shutil.copy2(str(profile_path), str(history_path))
               with open(profile_path, "w", encoding="utf-8") as f:
                   json.dump(profile, f, indent=2)
           
           yield _load, _save
   ```
2. **Refactor `train_profile()`** — Use `profile_transaction()`:
   ```python
   def train_profile(sections):
       with profile_transaction() as (load_fn, save_fn):
           profile = load_fn()
           # ... GPT call, processing ...
           save_fn(updated_profile)
       return updated_profile
   ```
   **Caveat:** The GPT API call is inside the lock, which blocks concurrent profile access during training (~5–15s). This is acceptable for a single-user app. If it becomes a problem, the lock can be released during the API call and re-acquired before save, with a compare-and-swap check.
3. **Edit `core/src/feedback.py`** — Use `profile_transaction()` in `like_track()` and `dislike_track()`:
   ```python
   def like_track(artist, track=None, reason=None):
       artist = sanitize_text(artist or "")
       track = sanitize_text(track) if track else None
       reason = sanitize_text(reason) if reason else None
       with profile_transaction() as (load_fn, save_fn):
           profile = load_fn()
           # ... modifications ...
           save_fn(profile)
   ```
4. **Keep backward compatibility** — `load_profile()` and `save_profile()` continue to work as before for read-only or simple-write use cases.
5. **Update tests** — Add a test that calls `save_run()` from two threads and verifies no data is lost.
6. **Run tests.**

### Estimated scope
2 files + 2 test files, ~50 lines. ~1 hour.

### Note
Closely related to TODO #20 (swap thread safety). Implement together.

</details>

---

## ~~26. `normalize_history()` mutates input dict in-place~~ ✅

- **Type:** Code quality
- **Severity:** Low
- **Source:** Core code review §5.2
- **Location:**
  - `core/src/suggestions.py` → `normalize_history()` (line ~129)
- **Problem:** `normalize_history()` modifies the profile dict it receives in-place, which can cause subtle bugs if the caller doesn't expect mutation. The function also returns the mutated dict, creating ambiguity.
- **Fix:** Work on a **deep copy** of the input dict instead of mutating in-place.
- **Files to change:** `core/src/suggestions.py`, `core/tests/test_suggestions.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/suggestions.py`** — In `normalize_history()` (line ~129), work on a deep copy:
   ```python
   import copy

   def normalize_history(profile):
       profile = copy.deepcopy(profile)
       _migrate_suggested_tracks(profile)
       # ... rest of dedup logic unchanged ...
       return profile
   ```
2. **Verify callers** — Check all callers of `normalize_history()` and ensure they use the return value (not the original input). Grep for `normalize_history(` in the codebase. The main caller is in `build_prompt_messages()` — verify it uses `profile = normalize_history(profile)`.
3. **Update tests** — In `core/tests/test_suggestions.py`, add a test that verifies the original dict is not mutated:
   ```python
   def test_normalize_history_does_not_mutate_input():
       original = {"history": {"suggested_tracks": [...], "suggested_artists": [...]}}
       original_copy = copy.deepcopy(original)
       normalize_history(original)
       assert original == original_copy
   ```
4. **Run tests.**

### Estimated scope
1 file + 1 test file, ~10 lines. ~15 minutes.

</details>

---

## ~~27. Remove dead code: `list_models()` in `openai_http.py`~~ ✅

- **Type:** Dead code
- **Severity:** Low
- **Source:** Core code review §3.1
- **Location:**
  - `core/src/openai_http.py` → `list_models()` (lines ~207–217)
- **Problem:** The function is never called anywhere in the codebase. The model list is maintained as a hardcoded allowlist in `config.py`.
- **Fix:** Remove `list_models()` and update the module docstring to only list `POST /v1/chat/completions`.
- **Files to change:** `core/src/openai_http.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Verify no usages** — Grep the entire codebase for `list_models`:
   ```bash
   git grep 'list_models' -- '*.py'
   ```
   Expected: only the definition in `openai_http.py` and possibly the module docstring.
2. **Edit `core/src/openai_http.py`** — Delete the `list_models()` function (lines ~207–217).
3. **Update the module docstring** (lines ~1–8) — Remove `GET /v1/models` from the list of used endpoints. Keep only `POST /v1/chat/completions`.
4. **Run tests.**

### Estimated scope
1 file, ~15 lines removed. ~5 minutes.

</details>

---

## ~~28. Remove dead code: legacy string-format track handling~~ ✅

- **Type:** Dead code
- **Severity:** Low
- **Source:** Core code review §3.3
- **Location:**
  - `core/src/suggestions.py` → `_migrate_suggested_tracks()` (lines ~89–126), `_build_deny_set_json()` (lines ~207–228), `filter_duplicate_suggestions()` (lines ~605–621)
- **Problem:** Multiple functions retain code paths for handling legacy string-format entries in `suggested_tracks` (pre-migration format). After migration has run once, all entries are dicts — the `isinstance(entry, str)` branches are effectively dead.
- **Fix:** Remove the string-handling branches and simplify. Add a migration version stamp to track this. Low priority — the code is harmless and defensive.
- **Files to change:** `core/src/suggestions.py`, `core/tests/test_suggestions.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/suggestions.py`** — Remove the `isinstance(entry, str)` branches:
   - In `_migrate_suggested_tracks()` (lines ~89–126): Keep the function but simplify — if all entries are dicts, return early. Remove the string-to-dict conversion logic and the `known_artists` longest-match parsing.
   - In `normalize_history()` (lines ~154–159): Remove the `else: a, t = "", str(item).lower().strip()` branch.
   - In `_build_deny_set_json()` (lines ~207–228): Remove the `else:` branch that handles legacy strings. Remove the `known_artists` variable used only for legacy parsing.
   - In `filter_duplicate_suggestions()` (lines ~605–621): Remove the `else:` branch in the artist track counting loop. Remove the `known_artists` variable.
2. **Simplify `_migrate_suggested_tracks()`** — It can become a no-op guard:
   ```python
   def _migrate_suggested_tracks(profile):
       """Legacy migration — now a no-op safety check."""
       tracks = profile.get("history", {}).get("suggested_tracks", [])
       if all(isinstance(t, dict) for t in tracks):
           return profile
       # If any non-dict entries remain, convert them (defensive)
       profile["history"]["suggested_tracks"] = [
           t if isinstance(t, dict) else {"artist": "", "track": str(t).lower().strip()}
           for t in tracks
       ]
       return profile
   ```
3. **Update tests** — Remove or update tests that explicitly test string-format track handling.
4. **Run tests.**

### Estimated scope
1 file + 1 test file, ~40 lines removed/simplified. ~30 minutes.

</details>

---

## ~~29. `history.py` — no concurrency protection~~ ✅

- **Type:** Code quality
- **Severity:** Low
- **Source:** Core code review §5.4
- **Location:**
  - `core/src/history.py` → `save_run()`, `_load_history()`, `_save_history()`
- **Problem:** `save_run()` calls `_load_history()` + `_save_history()` without any lock. If two generation runs complete simultaneously, one's history entry could be lost.
- **Fix:** Add a threading lock (like `_profile_lock` in `profile.py`), or serialize history writes through the Flask request thread.
- **Files to change:** `core/src/history.py`, `core/tests/test_history.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/history.py`** — Add a threading lock:
   ```python
   import threading
   _history_lock = threading.Lock()
   ```
2. **Wrap `save_run()`** in the lock:
   ```python
   def save_run(run_id, playlist_id, playlist_url, tracks):
       with _history_lock:
           history = _load_history()
           # ... existing logic ...
           _save_history(history)
   ```
3. **Wrap `load_runs()`** in the lock (read lock for consistency):
   ```python
   def load_runs():
       with _history_lock:
           return list(reversed(_load_history()))
   ```
4. **Update tests** — Add a test that calls `save_run()` from two threads and verifies no data is lost.
5. **Run tests.**

### Estimated scope
1 file + 1 test file, ~10 lines. ~15 minutes.

</details>

---

## ~~30. Diversity hints ignore `gpt_language` setting~~ ✅

- **Type:** Bug
- **Severity:** Low
- **Source:** Core code review §1.4
- **Location:**
  - `core/src/suggestions.py` → diversity hints (lines ~387–395)
- **Problem:** The `diversity_hints` list is always in English regardless of the `gpt_language` setting. This is inconsistent with the rest of the prompt pipeline which substitutes `{gpt_language}`.
- **Fix:** Either template these with `gpt_language` or add a comment justifying the English-only choice (e.g. "GPT instruction language is always English; output language is controlled separately").
- **Files to change:** `core/src/suggestions.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Decision: Add a justification comment** — The diversity hints are GPT *instructions* (telling the model what to do), not GPT *output* (what the model says to the user). GPT instruction language is conventionally English regardless of output language. Adding a comment is the simplest and most correct fix.
2. **Edit `core/src/suggestions.py`** — Above the `diversity_hints` list (line ~387), add:
   ```python
   # Diversity hints are instruction-language (always English) — they tell GPT
   # what kind of artists to explore. The output language is controlled
   # separately via {gpt_language} in the prompt template.
   ```
3. **Run tests.**

### Estimated scope
1 file, 3-line comment. ~5 minutes.

</details>

---

## ~~31. Inconsistent `sanitize_text` pattern in `feedback.py`~~ ✅

- **Type:** Bug
- **Severity:** Low
- **Source:** Core code review §1.6
- **Location:**
  - `core/src/feedback.py` → `like_track()` / `dislike_track()` (lines ~40–41)
- **Problem:** The ternary pattern `sanitize_text(track or "") if track else track` is confusing and inconsistent with the `artist` line which always calls `sanitize_text(artist or "")`.
- **Fix:** Simplify to `track = sanitize_text(track) if track else None` or `track = sanitize_text(track or "") or None`.
- **Files to change:** `core/src/feedback.py`

<details><summary><strong>📋 Development Plan</strong></summary>

### Steps
1. **Edit `core/src/feedback.py`** — In `like_track()` (lines ~39–41), simplify:
   ```python
   # Before:
   artist = sanitize_text(artist or "")
   track = sanitize_text(track or "") if track else track
   reason = sanitize_text(reason or "") if reason else reason

   # After:
   artist = sanitize_text(artist or "")
   track = sanitize_text(track) if track else None
   reason = sanitize_text(reason) if reason else None
   ```
2. **Apply same fix in `dislike_track()`** (lines ~77–79):
   ```python
   # Before:
   artist = sanitize_text(artist or "")
   track = sanitize_text(track or "") if track else track
   reason = sanitize_text(reason or "user feedback")

   # After:
   artist = sanitize_text(artist or "")
   track = sanitize_text(track) if track else None
   reason = sanitize_text(reason or "user feedback")
   ```
3. **Run tests.**

### Estimated scope
1 file, ~4 line changes. ~5 minutes.

</details>

---

## Summary

| # | Issue | Severity | Type |
|---|-------|----------|------|
| 1 | Track count in Refine dropdown | Low | UI bug |
| 2 | No reload button for playlist dropdowns | Medium | Feature |
| 3 | EXE loses language setting on close | High | Bug |
| 4 | Duplicate profile name (UI feedback) | Medium | UX |
| 5 | Enter key in Band/Song Analysis | Low | Bug |
| 6 | Missing German translations | Medium | i18n |
| 7 | Audio filter evaluation pattern | Medium | Feature |
| 8 | Empty/unnamed profiles in list | Medium | Bug |
| 9 | Profile switch mid-session state | High | Bug |
| 10 | `charmap` codec emoji error | High | Bug |
| 11 | Delete button in playlist dropdowns | Medium | Feature |
| 12 | Jump bubble overlaps elements on mobile | High | Mobile UX |
| 13 | Toast overlaps bottom UI on mobile | Medium | Mobile UX |
| 14 | Preview feedback panel overflows on small phones | Medium | Mobile UX |
| 15 | Audio filter hints overflow / small touch targets | Low | Mobile UX |
| 16 | Section help icon too small for touch | Medium | Mobile a11y |
| 17 | Path traversal via unvalidated profile ID | Critical | Security |
| 18 | Credential storage with OS keychain | Medium | Security |
| 19 | `debug_log()` creates directory for wrong file | High | Bug |
| 20 | `swap_profile_with_history()` not thread-safe | High | Bug |
| 21 | `save_profile_sections()` skips input sanitisation | Medium | Bug |
| 22 | `add_to_playlist()` fragile `None` guard on return | Medium | Bug |
| 23 | Replace `print()` with Python `logging` module | High | Logging |
| 24 | Silent exception swallowing in multiple locations | Medium | Bug |
| 25 | Profile lock granularity allows lost updates | Medium | Code quality |
| 26 | `normalize_history()` mutates input dict in-place | Low | Code quality |
| 27 | Remove dead code: `list_models()` in `openai_http.py` | Low | Dead code |
| 28 | Remove dead code: legacy string-format track handling | Low | Dead code |
| 29 | `history.py` — no concurrency protection | Low | Code quality |
| 30 | Diversity hints ignore `gpt_language` setting | Low | Bug |
| 31 | Inconsistent `sanitize_text` pattern in `feedback.py` | Low | Bug |
