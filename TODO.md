# TODO — SpotyVibe

## Features

### Discover New / Emerging Artists Only
Checkbox that restricts suggestions to artists who are new or emerged in the last ~6 months.

**Spotify API research (Apr 2026):**
- No dedicated "new artists" endpoint exists on Spotify.
- `GET /browse/new-releases`, `GET /artists/{id}/related-artists`, and `popularity` field were all **removed** in the Feb 2026 API changes.
- `GET /recommendations` — unconfirmed availability, not currently used.
- **What still works:** Spotify search `year:YYYY` filter, and `release_date` on album objects.

**Approach — GPT-first with Spotify release-date validation:**
1. **UI:** Add a checkbox "Only new / emerging artists" in the Generate section (near audio filters or playlist mode).
2. **GPT prompt:** When active, inject an additional hard constraint into the system prompt: *"Only suggest tracks by artists whose debut release is within the last 6 months."* (The diversity hints in `suggestions.py` already have a similar pattern — line ~382.)
3. **Over-request strategy:** GPT requests `user_count + 20` tracks (instead of the normal `+5` buffer) because many suggestions will be filtered out by the release-date check. This avoids expensive retry loops.
   - Normal mode: `effective_batch = user_count + 5` (current default).
   - New artists mode: `effective_batch = user_count + 20`.
4. **Spotify validation:** After GPT suggests tracks and they are searched on Spotify, check the album `release_date`. Reject tracks where the artist's earliest album predates the cutoff window.
5. **Result count:** Show all tracks that survive the filter — this may be more or fewer than `user_count`. No truncation to `user_count`.
6. **Fallback:** If too many suggestions get rejected by the date check, retry GPT with a wider window or a prompt nudge.

**Sub-task — UX wording for variable result count:**
- [ ] Design and implement user-facing messaging when the new-artists filter is active. The user should understand why they may see more or fewer tracks than they requested (e.g., "Showing 14 of 30 checked tracks — only tracks by recently emerged artists are included.").
- [ ] Affected files: i18n keys, `pipeline.js` (result display logic), possibly `playlist_review.html` or track list rendering.

**Files to change:**
- `frontend/templates/generate_section.html` — checkbox UI
- `frontend/static/i18n/en.json` + `de.json` — i18n keys
- `frontend/static/js/modules/pipeline.js` — pass flag to backend
- `app.py` — accept and forward the flag
- `core/src/suggestions.py` — modify `build_messages()` to inject the constraint + adjust `effective_batch_size`
- `prompts/system_prompt.txt` (+ model-specific variants) — optional: add conditional block
- `core/src/playlist.py` — after search, check album `release_date` and filter; return all survivors

### Tab Groups Instead of Scrollbar
- [ ] Replace the current vertical scroll-based section navigation with a tabbed UI (tab groups).
- [ ] Each major section (Profile, Generate, Review, Analysis, History) becomes a tab.
- [ ] Eliminates the need for the scroll-based jump bubble and long-page scrolling.

## UX / UI Improvements

### Default Theme — Without Movement
- [ ] Provide a static/calm default theme that has no background animations or particle movement.
- [ ] Users who want motion can opt into an animated theme explicitly.

### Move Theme Picker to the Bottom
- [ ] Relocate the theme picker/switcher to the bottom of the page (or into a less prominent position).
- [ ] Currently it feels like a primary UI component; it should be secondary/cosmetic.

### Pagination in Quickstart — Remove on Top
- [ ] Remove the top pagination in the quickstart guide; keep only the bottom pagination.
- [ ] Simplifies the quickstart layout.

### Move Feedback/Retry to a Different Help Container After Profile Creation
- [ ] Once the user has created a music profile, relocate the feedback/retry controls into a separate help or utility container.
- [ ] Avoids cluttering the main workflow area post-profile-creation.

## i18n / Wording

### "Musik entdecken", "Playlist verfeinern" — German UI Shows English Text
- [ ] The German translation (`de.json`) incorrectly uses the English word "Show" instead of the German "Anzeigen" for these labels.
- [ ] Find and fix affected keys in `de.json` so the German UI reads "Anzeigen" (or another proper German verb).
- [ ] Verify `en.json` counterparts are correct.

## Data / History

### Reset History = Reset Last Change
- [ ] The "Reset History" action should undo only the last change (single-step undo) rather than wiping the entire history.
- [ ] Rename or clarify the button label to match the new behavior (e.g., "Undo Last Change").
