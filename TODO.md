# TODO — SpotyVibe

---

## Features

---

### 1. Discover New / Emerging Artists Only

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

<details>
<summary><strong>Implementation Plan (7 steps, ordered)</strong></summary>

#### Step 1 — i18n keys
Add keys to both `en.json` and `de.json`. Place them near the existing audio-filter keys (around line 59–107 in `en.json`).
New keys needed:
- `"generate.emerging_only"` — checkbox label (EN: "Only new / emerging artists", DE: "Nur neue / aufstrebende Künstler")
- `"generate.emerging_only_hint"` — explanation text (EN: "Only suggest tracks by artists who debuted in the last 6 months.", DE: "Nur Tracks von Künstlern vorschlagen, die in den letzten 6 Monaten debütiert haben.")
- `"pipeline.emerging_filter_result"` — result message (EN: "Showing {shown} of {checked} checked tracks — only tracks by recently emerged artists are included.", DE: "Zeige {shown} von {checked} geprüften Tracks — nur Tracks von kürzlich aufgetauchten Künstlern sind enthalten.")

**Files:** `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`

#### Step 2 — Checkbox UI
Add a checkbox **after the audio filters section** (after line 90 in `generate_section.html`). Follow the existing pattern of the audio filter toggle (lines 42–90) but simpler — a single checkbox row, not a collapsible panel.

HTML structure:
```html
<div class="emerging-artists-row" id="emergingArtistsRow">
    <label class="emerging-artists-label">
        <input type="checkbox" id="emergingArtistsCheckbox">
        <span data-i18n="generate.emerging_only">Only new / emerging artists</span>
    </label>
    <span class="emerging-artists-hint" data-i18n="generate.emerging_only_hint">...</span>
</div>
```

Add minimal CSS in `frontend/static/css/forms.css` (where other checkbox styles live).

**Files:** `frontend/templates/generate_section.html` (after line 90), `frontend/static/css/forms.css`

#### Step 3 — Frontend: pass flag to backend
In `frontend/static/js/modules/pipeline.js`, read the checkbox state and include it in the request payload.

**Where to change:** `pipeline.js` lines 97–99 — after `getAudioFilters()`, add:
```js
const emergingOnly = document.getElementById('emergingArtistsCheckbox')?.checked || false;
if (emergingOnly) playlistPayload.emerging_only = true;
```

The payload already gets spread into the POST body at line 124: `JSON.stringify({ run_id: runId, ...payload })`.

**File:** `frontend/static/js/modules/pipeline.js` (lines 97–99)

#### Step 4 — Backend route: accept and forward the flag
In `app.py`, extract `emerging_only` from the request body and pass it through the generation pipeline.

**Where to change:** `app.py` line 308 — after `audio_filters = body.get("audio_filters") or {}`, add:
```python
emerging_only = bool(body.get("emerging_only"))
```

Then pass `emerging_only` to `build_messages()` at lines 396–404 and to the post-search filter logic.

**File:** `app.py` (lines 300–312 for extraction, lines 396–404 for forwarding)

#### Step 5 — GPT prompt: inject constraint + adjust batch size
In `core/src/suggestions.py`, modify `build_messages()` (lines 302–334):

1. **Add parameter:** `emerging_only=False` to the function signature (line 302).
2. **Adjust batch size:** At line 320, when `emerging_only` is True, use `+20` instead of `+5`:
   ```python
   buffer = 20 if emerging_only else 5
   effective_batch_size = batch_size + buffer
   ```
3. **Inject prompt constraint:** After the system prompt placeholder substitution (lines 331–334), append a hard constraint when `emerging_only` is True:
   ```python
   if emerging_only:
       constraint = "\n8. ONLY suggest tracks by artists whose debut release is within the last 6 months. Prefer unknown, underground, or recently debuted artists."
       system_prompt = system_prompt.replace("Maximum 2 tracks per artist per batch.", "Maximum 2 tracks per artist per batch." + constraint)
   ```

**File:** `core/src/suggestions.py` (lines 302–334)

#### Step 6 — Spotify validation: filter by release_date
In `core/src/playlist.py`, after `search_tracks()` returns found tracks (line 251–336), add a post-filter function.

The `release_date` field is already available on found tracks via `_normalize_track()` in `spotify_metadata.py` line 303: `"release_date": album.get("release_date")`.

Add a new function `filter_emerging_artists(tracks, cutoff_months=6)` that:
1. Parses `release_date` (format: `"YYYY-MM-DD"` or `"YYYY"`) from each track.
2. Rejects tracks where the release date predates `now - cutoff_months`.
3. Returns `(survivors, rejected)`.

Call this filter in `app.py` after search results come back, only when `emerging_only` is True. Do NOT truncate survivors to `user_count` — return all that pass.

**Files:** `core/src/playlist.py` (new function, after line 336), `app.py` (after search_tracks call)

#### Step 7 — Result display with variable count message
In `pipeline.js`, when `emerging_only` is active, display the `pipeline.emerging_filter_result` i18n message showing how many tracks survived filtering.

**Where to change:** The SSE event handler in `pipeline.js` (around lines 120–161) where stream events are processed. Add a status message after the final batch.

**File:** `frontend/static/js/modules/pipeline.js`

</details>

**Sub-task — UX wording for variable result count:**
- [ ] Design and implement user-facing messaging when the new-artists filter is active. The user should understand why they may see more or fewer tracks than they requested (e.g., "Showing 14 of 30 checked tracks — only tracks by recently emerged artists are included.").
- [ ] Affected files: i18n keys, `pipeline.js` (result display logic), possibly `playlist_review.html` or track list rendering.

**Definition of Done:**
- [ ] Checkbox visible in Generate section, below audio filters
- [ ] Checking the box sends `emerging_only: true` in the POST `/api/run` payload
- [ ] `build_messages()` injects hard constraint 8 into GPT system prompt when flag is active
- [ ] Batch size uses `+20` buffer instead of `+5` when flag is active
- [ ] After Spotify search, tracks are filtered by `release_date` (reject if artist's album predates 6-month window)
- [ ] Surviving tracks are returned without truncation to `user_count`
- [ ] UI shows a status message explaining why result count differs from requested count
- [ ] i18n keys in both `en.json` and `de.json`
- [ ] `data-i18n` attribute on all new user-facing text
- [ ] Tests pass (`python -m pytest core/tests/ frontend/tests/ -v`)
- [ ] Documentation updated: `README.md`, `UserManual.md`, `help.md`, `TechnicalManual.md`

---

### 2. Tab Groups Instead of Scrollbar

Replace the current vertical scroll-based section navigation with a tabbed UI (tab groups). Each major section (Profile, Generate, Review, Analysis, History) becomes a tab.

<details>
<summary><strong>Implementation Plan (5 steps, ordered)</strong></summary>

#### Step 1 — Tab bar HTML
In `frontend/templates/base.html`, replace the section jump bubble (line 73–74: `<button class="section-jump-bubble" id="sectionJumpBubble">`) with a horizontal tab bar. Place it inside the `<header>` or immediately after it.

Each tab corresponds to an existing section:
- Profile → `#trainSection` (defined in `train_profile.html`)
- Generate → `#generateSection` (defined in `generate_section.html`)
- Review → `#reviewSection` (defined in `playlist_review.html`)
- Analysis → `#analysisSection` (defined in `band_analysis.html`)
- History → `#historySection` (defined in `run_history.html`)

Use `role="tablist"` on the container, `role="tab"` on each tab button, and `role="tabpanel"` on each section. Add `aria-selected`, `aria-controls`, and `tabindex` attributes for accessibility.

**File:** `frontend/templates/base.html` (replace lines 73–74, add tab bar)

#### Step 2 — Tab switching JS module
Create or repurpose `frontend/static/js/modules/jump-bubble.js` (currently 97 lines handling the scroll bubble). Replace its content with tab-switching logic:

1. On tab click: hide all section `<div>`s (add `hidden` class), show the target section, update `aria-selected` on all tabs.
2. On page load: activate the Profile tab by default (or the last-active tab from `localStorage`).
3. Remove the scroll-based intersection observer and jump bubble logic (lines 14–97).
4. Export `initTabs()` instead of `initJumpBubble()`.

Update `frontend/static/js/main.js` line 18 and 198 to import and call `initTabs()` instead of `initJumpBubble()`.

**Files:** `frontend/static/js/modules/jump-bubble.js` (full rewrite), `frontend/static/js/main.js` (lines 18, 198)

#### Step 3 — Section visibility changes
Each section currently auto-expands via its own toggle function. With tabs, sections are shown/hidden at the section level, not the body level. Remove or adapt the outer show/hide behavior:

- The sections are currently **all rendered** and stacked vertically. With tabs, only the active section's container is visible.
- The inner "Show/Hide" toggle buttons on each section header (`toggleTrainBody` in `profile.js:463`, `toggleGenerateBody` in `pipeline.js:12`, `toggleReviewBody` in `review.js:7`, `toggleAnalysisBody` in `analysis.js:4`, `toggleHistoryBody` in `history.js:5`) should remain — they control the section **body** accordion within the visible tab.

**Files:** No changes to toggle functions. Only the outer section `<div>` visibility is managed by tabs.

#### Step 4 — CSS for tab bar
Add tab bar styles in `frontend/static/css/layout.css`. Remove jump bubble styles from `frontend/static/css/components.css` (lines 559–618).

Tab bar design: horizontal, sticky below header, glass-panel aesthetic matching existing UI. Active tab gets a bottom border or highlight. Use existing CSS variables from `base.css`.

**Files:** `frontend/static/css/layout.css`, `frontend/static/css/components.css` (remove lines 559–618), `frontend/static/css/responsive.css` (add mobile tab styles)

#### Step 5 — i18n for tab labels
Add i18n keys for each tab label. The section titles already exist (`"profile.title"`, `"generate.title"`, `"review.title"`, `"analysis.title"`, `"history.title"`). Reuse them on the tab buttons with `data-i18n`.

**Files:** No new i18n keys needed — reuse existing section title keys.

</details>

**Definition of Done:**
- [ ] Horizontal tab bar visible below header with 5 tabs (Profile, Generate, Review, Analysis, History)
- [ ] Clicking a tab shows only that section, hides all others
- [ ] Active tab is visually distinct (highlight/underline)
- [ ] Inner "Show/Hide" body toggles still work within each tab
- [ ] Jump bubble removed from HTML, JS, and CSS
- [ ] Tab bar is keyboard-navigable (arrow keys between tabs, Enter/Space to activate)
- [ ] `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected` attributes present
- [ ] Tab labels use existing i18n keys (`data-i18n`)
- [ ] Responsive: tabs stack or scroll horizontally on mobile
- [ ] Active tab persists via `localStorage` across page reloads
- [ ] Tests pass

---

## UX / UI Improvements

---

### 3. Default Theme — Without Movement ✅

Provide a static/calm default theme that has no background animations or particle movement. Users who want motion can opt into an animated theme explicitly.

<details>
<summary><strong>Implementation Plan (3 steps)</strong></summary>

#### Step 1 — Add a "calm" theme renderer
Create `frontend/static/js/modules/theme-calm.js`. Register it in `THEME_RENDERERS` (defined in `theme-switcher.js` line 8). The renderer should paint a **static** background (e.g., a subtle gradient or solid color on the canvas) and return a no-op animation function — no `requestAnimationFrame` loop.

Follow the pattern of existing theme files (e.g., `theme-equalizer.js` lines 3–7):
```js
import { THEME_RENDERERS } from './theme-switcher.js';
THEME_RENDERERS.calm = (canvas) => {
    const ctx = canvas.getContext('2d');
    // Draw a static gradient once
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
    grad.addColorStop(0, '#1a1a2e');
    grad.addColorStop(1, '#16213e');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return () => {}; // no-op animation frame
};
```

Also add the canvas element to `THEME_BACKGROUNDS` in `theme-switcher.js` line 1–6.

**Files:** `frontend/static/js/modules/theme-calm.js` (new), `frontend/static/js/modules/theme-switcher.js` (lines 1–8)

#### Step 2 — Set "calm" as default
In `frontend/static/js/main.js` line 169, change the fallback from `'equalizer'` to `'calm'`:
```js
switchTheme(_pendingTheme || 'calm');
```

Import the new theme module as a side-effect import alongside the others (lines 19–22).

**Files:** `frontend/static/js/main.js` (lines 19–22 and 169)

#### Step 3 — Add theme to switcher UI
In `frontend/templates/theme_switcher.html` (lines 1–11), add a button for the calm theme. Follow the existing button pattern. Use a suitable icon or label.

Add i18n keys: `"theme.calm"` (EN: "Calm", DE: "Ruhig").

**Files:** `frontend/templates/theme_switcher.html`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`

</details>

**Definition of Done:**
- [x] New "calm" theme exists with a static background (no animation loop, no `requestAnimationFrame`)
- [x] "calm" is the default theme for first-time visitors (no `localStorage` theme saved)
- [x] Existing animated themes (equalizer, pulse, spectrum, starfield) still work and can be selected
- [x] Theme switcher UI includes the calm theme option
- [x] i18n keys for theme name in both `en.json` and `de.json`
- [x] Users who previously chose a theme keep their choice (localStorage respected)
- [x] Tests pass

---

### 4. Move Theme Picker to the Bottom ✅

Relocate the theme picker/switcher from the header to the bottom of the page. It should feel secondary/cosmetic, not like a primary UI component.

<details>
<summary><strong>Implementation Plan (2 steps)</strong></summary>

#### Step 1 — Move the include
In `frontend/templates/base.html` line 34, the theme switcher is included inside `<header>`:
```html
{% include "theme_switcher.html" %}
```
Move this include to **after all section includes** (after the History section), just before the closing content area. Place it inside a `<footer>` or a `<div class="page-footer">` wrapper.

**File:** `frontend/templates/base.html` (move line 34 to after all sections)

#### Step 2 — Adjust CSS positioning
In `frontend/static/css/components.css` lines 502–548, the `.style-switcher` has `margin-bottom: 1.6rem`. Update positioning to align it at the bottom:
- Remove any header-specific spacing.
- Add `margin-top: 2rem` and center it.
- In `frontend/static/css/responsive.css`, verify mobile positioning still works (check lines 388–419 for existing responsive rules).

**Files:** `frontend/static/css/components.css` (lines 502–548), `frontend/static/css/responsive.css`

</details>

**Definition of Done:**
- [x] Theme picker renders below all main sections, not in the header
- [x] Visually secondary — smaller or more subdued than main UI elements
- [x] Still fully functional (clicking themes switches them)
- [x] Responsive layout works on mobile
- [x] Tests pass

---

### 5. Pagination in Quickstart — Remove on Top ✅ (already resolved — only bottom pagination exists)

Remove the top pagination in the quickstart guide; keep only the bottom pagination.

<details>
<summary><strong>Implementation Plan</strong></summary>

**Context:** In `frontend/templates/modals/quickstart_modal.html`, the pagination is at lines 295–305 inside the footer. The exploration found pagination exists only at the bottom (`.qs-pagination` at line 295). If there IS a top pagination element, it may be dynamically generated.

Check `frontend/static/js/modules/quickstart-tour.js` lines 111–127 for dot indicator rendering — the JS may clone or duplicate pagination into a top container.

**Action:** Search for any top pagination container (class or ID with "top" + "pagination") in the quickstart HTML and JS. If found, remove the top one. If pagination is only at the bottom already, this task may be resolved — verify visually.

**Files:** `frontend/templates/modals/quickstart_modal.html`, `frontend/static/js/modules/quickstart-tour.js` (lines 62–127)

</details>

**Definition of Done:**
- [x] Quickstart modal shows pagination controls only at the bottom
- [x] No duplicate pagination at the top of the quickstart modal
- [x] Bottom pagination still works (dots, back/next buttons)
- [x] Tests pass

---

### 6. Move Feedback/Retry to a Different Help Container After Profile Creation

Once the user has created a music profile, relocate the feedback/retry controls into a separate help or utility container. Avoids cluttering the main workflow area post-profile-creation.

<details>
<summary><strong>Implementation Plan</strong></summary>

**Current state:**
- Preview feedback panel: `frontend/templates/preview_overlay.html` lines 42–63 (`.preview-feedback-panel` with form inputs, slides in from right).
- Inline track feedback forms: `frontend/templates/generate_section.html` lines 165–189 (per-track Like/Dislike/Remove buttons and feedback form).
- Profile reset/retry: `frontend/static/js/modules/profile.js` lines 672–696 (`resetProfileToHistory()` — POSTs to `/api/profile/reset-to-history`).
- Reset button in profile menu: `frontend/templates/train_profile.html` line 38.

**Action:** After profile is trained (check `is_profile_trained()` state), move the retry/reset controls from the profile section header into a dedicated utility panel. This could be a collapsible "Profile Tools" row below the profile section, or inside the settings gear menu (`settings_gear.html`).

**Files:** `frontend/templates/train_profile.html` (line 38), `frontend/static/js/modules/profile.js` (lines 672–696), potentially `frontend/templates/settings_gear.html`

</details>

**Definition of Done:**
- [ ] Feedback/retry controls are not visible in the main profile section header after profile creation
- [ ] Controls are accessible from a secondary location (utility panel or settings)
- [ ] Controls still function identically (reset-to-history, retry)
- [ ] Before profile creation, controls remain in their original position (or are hidden entirely)
- [ ] Tests pass

---

## i18n / Wording

---

### 7. "Musik entdecken", "Playlist verfeinern" — Section Toggle Buttons Show English "Show" in German UI ✅

**Root cause:** The toggle buttons in `generate_section.html` line 8 and `playlist_review.html` line 9 are missing the `data-i18n="btn.show"` attribute. The other section toggles (`train_profile.html` line 13, `band_analysis.html` line 9, `run_history.html` line 9) DO have `data-i18n="btn.show"` and work correctly. The German translation itself is correct: `de.json` line 48 has `"btn.show": "Anzeigen"`.

The JS toggle functions (`toggleGenerateBody` at `pipeline.js:17`, `toggleReviewBody` at `review.js:12`) correctly call `i18n('btn.show', 'Show')` on toggle — but the **initial render** before any toggle shows the hardcoded English fallback because `data-i18n` is missing.

<details>
<summary><strong>Implementation Plan (1 step)</strong></summary>

Add `data-i18n="btn.show"` to the two buttons that are missing it:

**File 1 — `frontend/templates/generate_section.html` line 8:**
Change:
```html
<button class="btn-train" id="generateToggleBtn" onclick="event.stopPropagation(); toggleGenerateBody()" aria-expanded="false" aria-controls="generateBody">Show</button>
```
To:
```html
<button class="btn-train" id="generateToggleBtn" onclick="event.stopPropagation(); toggleGenerateBody()" data-i18n="btn.show" aria-expanded="false" aria-controls="generateBody">Show</button>
```

**File 2 — `frontend/templates/playlist_review.html` line 9:**
Change:
```html
<button class="btn-train" id="reviewToggleBtn" onclick="event.stopPropagation(); toggleReviewBody()" aria-expanded="false" aria-controls="reviewBody">Show</button>
```
To:
```html
<button class="btn-train" id="reviewToggleBtn" onclick="event.stopPropagation(); toggleReviewBody()" data-i18n="btn.show" aria-expanded="false" aria-controls="reviewBody">Show</button>
```

</details>

**Definition of Done:**
- [x] `generate_section.html` line 8 toggle button has `data-i18n="btn.show"`
- [x] `playlist_review.html` line 9 toggle button has `data-i18n="btn.show"`
- [x] German UI shows "Anzeigen" (not "Show") on initial page load for all five section toggles
- [x] English UI is unchanged (still shows "Show")
- [x] Tests pass

---

## Data / History

---

### 8. Reset History = Reset Last Change (Single-Step Undo) ✅ (label fix only — behavior unchanged)

The "Reset History" action should undo only the last change (single-step undo) rather than wiping the entire history. Rename the button label to match the new behavior.

**Important clarification:** This refers to the **profile** reset, not the run history. The current behavior (`POST /api/profile/reset-to-history`) swaps the active profile with a single `.history.json` backup — it is already a one-step revert. The issue is that the **button label** says "Reset" which implies a full wipe, and there is no multi-level undo.

<details>
<summary><strong>Implementation Plan (3 steps)</strong></summary>

#### Step 1 — Clarify the button label
In `frontend/templates/train_profile.html` line 38, the reset menu item uses `data-i18n="profile.menu_reset"`. Update the i18n values:

- `en.json`: Change `"profile.menu_reset"` from "Reset profile" to "Undo last change"
- `de.json`: Change `"profile.menu_reset"` from current value to "Letzte Änderung rückgängig"
- Also update `"profile.reset_confirm"` confirmation text to reflect "undo last change" wording.

**Context for existing keys:** `de.json` lines 143–145 contain the reset confirmation/success/failure messages.

**Files:** `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`

#### Step 2 — (Optional) Multi-level undo
Currently `core/src/history.py` (69 lines total) does NOT manage profile history — it manages **run** history. Profile history is a separate `.history.json` file managed by `core/src/profile.py`.

To support true multi-level undo, `profile.py` would need to maintain a stack of previous profile states instead of a single backup. This is a larger change. Evaluate whether the label fix alone is sufficient.

**Files:** `core/src/profile.py` (if multi-level undo is desired)

#### Step 3 — Backend route behavior (if changing)
The current endpoint `POST /api/profile/reset-to-history` in `app.py` lines 976–979 swaps active profile with `.history.json`. If multi-level undo is added, this route would need to pop from a history stack instead.

**File:** `app.py` (lines 976–979)

</details>

**Definition of Done:**
- [x] Button label reads "Undo last change" (EN) / "Letzte Änderung rückgängig" (DE) instead of "Reset profile"
- [x] Confirmation dialog text updated to match new wording
- [x] Behavior unchanged (still swaps with `.history.json` backup) unless multi-level undo is implemented
- [x] Tests pass
- [x] Documentation updated if behavior changes
