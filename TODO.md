# TODO

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

## Bugs

- [x] **Import/Export visibility**: Import and Export are visible even if the user did not press “Edit profile”.

- [x] **Import/Export alignment**: Import and Export buttons are not left-aligned under the “Last trained” label; they currently appear directly under the “Edit profile” button.

## 🧩 Audio Filters – Layout Overflow Issue

**Problem:** UI elements do not fit properly inside the container.

### TODO
- [ ] Inspect container constraints (padding, margin, width)
- [ ] Replace fixed widths with responsive layout (`flex` or `grid`)
- [ ] Ensure labels (Energy, Valence, etc.) have consistent width
- [ ] Align min/max input fields horizontally
- [ ] Add wrapping (`flex-wrap` or grid) to prevent overflow
- [ ] Ensure inputs scale properly on smaller screens
- [ ] Standardize spacing between rows and inputs
- [ ] Test responsiveness across multiple screen sizes
- [ ] (Optional) Refactor into 2-column grid:
  - Label | Min/Max inputs


---

## 👤 Hide Profile – Button Placement

**Problem:** "Hide profile" button is incorrectly placed below Import/Export/Reset.

### TODO
- [ ] Move "Hide profile" button above Import / Export / Reset row
- [ ] Adjust layout hierarchy:
  - Hide Profile
  - Import / Export / Reset
- [ ] Ensure consistent spacing after repositioning
- [ ] Verify responsive behavior (no awkward wrapping)
- [ ] (Optional) Style as secondary/destructive action


---

## 🔍 Song Analysis – Input Layout

**Problem:** Input fields are inconsistent and incorrectly arranged.

### Desired Layout
- Row 1: Artist input + Track input
- Row 2: Analyse button (full width)

### TODO
- [ ] Refactor container to use `flex` or `grid`
- [ ] Place both input fields in a single row
- [ ] Ensure equal width distribution (50/50 or proportional)
- [ ] Move "Analyse" button to a new row below inputs
- [ ] Make button full-width or properly centered
- [ ] Standardize input height and styling
- [ ] Fix padding and placeholder alignment
- [ ] Add responsive fallback:
  - Stack inputs vertically on small screens
- [ ] Ensure consistent spacing between elements


---

## ⚙️ Backend – Client `proxies` Error

**Error:** `Client.__init__() got an unexpected keyword argument 'proxies'`

### TODO
- [ ] Identify which client throws the error (requests, httpx, API client, etc.)
- [ ] Locate where `proxies` argument is passed
- [ ] Verify library version and supported parameters
- [ ] Fix implementation:
  - Remove unsupported `proxies` argument OR
  - Pass proxies using correct method (library-specific)
- [ ] Add validation before passing config to client
- [ ] Add logging for debugging incorrect parameters
- [ ] Test with:
  - Proxy enabled
  - Proxy disabled
- [ ] (Optional) Add environment-based proxy configuration


---

## 🚀 Onboarding – Reappears on App Start

**Problem:** Onboarding flow is not persisted correctly.

### TODO
- [ ] Identify persistence method (local storage, AsyncStorage, DB, etc.)
- [ ] Ensure onboarding completion flag is saved (`onboardingCompleted = true`)
- [ ] Load flag before rendering initial screen
- [ ] Prevent race conditions during app startup
- [ ] Ensure onboarding only renders if flag is false
- [ ] Add fallback handling if state fails to load
- [ ] Test scenarios:
  - First-time user
  - Returning user
  - App restart
  - App update
- [ ] (Optional) Add manual reset option for onboarding


---

## ✅ QA Checklist

- [ ] UI layouts responsive across devices
- [ ] No overflow or alignment issues
- [ ] Buttons positioned logically
- [ ] Backend client initializes without errors
- [ ] Onboarding behaves correctly
- [ ] End-to-end flow works (Profile → Analysis → Playlist)