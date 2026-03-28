# TODO

## Features

- [x] **Add “Reset to history” button for Music Profile**.
  - Adds a UI action to restore the previous profile.
  - Implementation should *swap* `personalized_music_profile.json` and `personalized_music_profile.history.json` (current becomes history, history becomes current).
  - Should handle the case where the history file does not exist.

- [x] **Disable / remove Debug Log on Android**.
  - The “Debug Mode” setting and the `DELETE /api/settings/debug-log` UI affordance should only be available on Desktop.
  - Android APK should not expose prompt logging controls in Settings.

- [ ] **Add “Band/Song Analysis” section under Music Profile**.
  - UI: a new section where users can input:
    - band names, or
    - band + song names
  - Backend: send the input to the configured OpenAI model and return an analysis describing:
    - genre/style classification,
    - key musical characteristics (energy, instrumentation, vocals, production, structure),
    - “how to describe this sound” suggestions the user can paste into their profile.
  - Output should be structured (JSON) so the UI can render it cleanly.

- [ ] **Add Spotify “audio feature” constraints (optional filters)**.
  - Optional post-verification filtering using Spotify audio features (tempo/energy/valence/etc.).
  - UI could start simple (e.g., “avoid slow songs”, “energy 0.6–1.0”) and expand later.

- [ ] **Use feedback reasons more directly**.
  - Summarise recent like/dislike reasons into a short “recent feedback” block sent to GPT (capped for token safety).
  - Optionally provide a toggle to bias the next run toward recent likes vs exploration.

- [ ] **Multiple playlists / playlist naming**.
  - Support “create new playlist”, “append to existing”, and/or “replace playlist” modes.
  - Allow custom playlist name templates (e.g., date/time, style tag).

- [ ] **Run history and rollback**.
  - Save run metadata (timestamp, playlist ID/URL, tracks added) to local storage.
  - Add “undo last run” (remove tracks added by the last run).

- [ ] **Previews and richer track cards**.
  - Add Spotify preview playback when `preview_url` is available.
  - Add quick links to track/album/artist in Spotify.

## Security

- [x] **Add file size limit** for profile import.
  - Add a maximum request size and enforce it server-side for `POST /api/profile/import`.
  - Consider client-side early checks as a UX improvement (but do not rely on them).

- [ ] **Sanitise & validate imported JSON**.
  - Parse and validate the JSON structure rigorously.
  - Map imported content onto the internal profile schema (template-based), rejecting unknown or dangerous fields.
  - Ensure types match expected shapes (dict vs list vs string) to prevent prompt-injection-like content from being stored in unexpected places.

- [ ] **Add server-side request size limits for all user-input endpoints** (not just import).
  - Enforce size limits on `POST /api/train-profile`, `POST /api/save-profile`, `POST /api/feedback` (and any future endpoints).
  - Add field-level limits (max chars per field, max list lengths) to prevent runaway OpenAI prompt sizes and cost surprises.

- [ ] **Strip/control unsafe characters from user-provided text**.
  - Remove null bytes and control characters.
  - Normalize whitespace.
  - Apply consistently to manual profile edits, feedback, and imported profile fields.

- [ ] **Harden prompts against prompt injection by treating the profile as untrusted data**.
  - Update prompts / message assembly to explicitly instruct the model to ignore any instructions embedded inside profile fields.

- [ ] **Restrict Android WebView downloads to trusted localhost endpoints**.
  - In `MainActivity.kt`, only allow downloads from `http://127.0.0.1:5000` (ideally only `/api/profile/export`).

- [x] **Escape/normalize Spotify search query inputs**.
  - Prevent malformed Spotify search queries by escaping or removing quotes in user-provided artist/track strings before building `track:"..." artist:"..."` queries.

## Reliability & Cost

- [ ] **Hard cost guardrails**.
  - Add max GPT calls / retries per run.
  - Add field-level limits to prevent accidental huge prompts.
  - Optionally show rough cost estimates in debug mode.

- [ ] **Better SSE resilience**.
  - Optionally persist run state by `run_id` so the UI can recover after refresh.
  - Add clearer end states for disconnects/timeouts.

- [ ] **Cache model list (minor but nice)**.
  - Cache `/api/settings/models` responses for a short TTL to reduce OpenAI API calls.

## Android

- [ ] **Android packaging polish (targeted)**.
  - Improve share/import flows for exported profiles.
  - Consider “open in external browser” for Spotify links.

## Testing & CI

- [ ] **Testing & CI upgrades (keeps changes safe)**.
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
