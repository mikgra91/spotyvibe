# SpotyVibe — Fix plan (2026-04-13)

> **Source.** User bug batch collected 2026-04-13 with screenshots in `C:\Users\micha\Desktop\Bugs\13042026\`. All architectural decisions in this plan were confirmed by the user in chat.
>
> **Scope.** Polish + correctness fixes across the 5-wave implementation. No new features. Every item is a bug or an already-agreed small design refinement.
>
> **Conventions.** Same as [`CLAUDE.md`](CLAUDE.md). i18n via `data-i18n` / `i18n()`. Vanilla ES modules. No new dependencies. Changes may span frontend, backend, and docs — kept in the same batch when they share a surface.
>
> **Out of scope.** Anything not in this plan. No new features. No provider SDKs beyond OpenAI-compatible. No cost-tracking history. No DE setup-guide screenshot translations.

---

## Execution batches

Work in the order below. Each batch is self-contained and committable. Stop and check with the user between batches unless explicitly asked to continue.

| Batch | Theme | Items |
|-------|-------|-------|
| 1 | Onboarding correctness (showstopper) | A.1 A.2 A.3 A.4 B.1 B.2 B.4 B.5 |
| 2 | Main-app polish | C.2 C.4 E.1 F.2 I K |
| 3 | Architecture refinements | C.3 D.1 F.1 G H J |
| 4 | Investigation-heavy | C.1 D.3 |

Batch 1 blocks a new user from completing onboarding and must land first.

---

## A. Onboarding blockers

### A.1 — Setup-guide detail views show green rectangles

- **Cause.** Wave-1 placeholder PNGs under `documentation/assets/guides/*/` are solid-colour image files rendered at `width: 100%`.
- **Fix.** Replace every placeholder file with a single reusable 800×450 "📸 Screenshot coming soon" asset (dashed outline + caption). Document in `documentation/assets/guides/README.md` that these are placeholders pending manual capture.
- **Files.** `documentation/assets/guides/openai/*.png`, `spotify/*.png`, `python-macos/*.png`, `python-linux/*.png`.

### A.2 — Onboarding card exceeds viewport height

- **Cause.** `.ob-wrap` uses `min-height: 100vh` without capping inner card height. Long steps (especially step 1 with features + privacy panel) force page scroll.
- **Fix.** Restructure the shell as a flex column that fits `100vh - titlebar` without scrolling. Only `.ob-body` scrolls when content genuinely overflows (narrow viewports on step 5). Reduce step-1 density: feature icons 1.3 rem down from 1.6; trim privacy panel to 2 lines with "More →".
  ```
  .ob-wrap        height: calc(100vh - var(--titlebar-h));
                  display: flex; flex-direction: column; overflow: hidden;
  .ob-card        flex: 1; display: flex; flex-direction: column; overflow: hidden;
  .ob-body        flex: 1; overflow-y: auto;
  .ob-nav         flex-shrink: 0;
  ```
- **Files.** `frontend/static/css/onboarding.css`, `frontend/templates/onboarding.html`.

### A.3 — Language selector missing

- **Cause.** `.ob-lang-toggle` either not rendered or styled off-screen. Screenshots show only a stub text label.
- **Fix.** Verify the template includes the EN|DE pill, positioned `position: fixed; top: 16px; right: 24px; z-index: 50`. Confirm `obSwitchLang()` wired. Add focus-visible outline for keyboard users.
- **Files.** `frontend/templates/onboarding.html`, `frontend/static/css/onboarding.css`, `frontend/static/js/modules/onboarding.js`.

### A.4 — Spotify OAuth leaves the desktop app

- **Cause.** `onboarding.js` calls `window.open('/api/spotify/auth', ...)` which pywebview cannot honour; the OS browser receives the callback instead of the app.
- **Fix.** Gate on `window.pywebview.api.open_spotify_auth` presence:
  ```js
  if (window.pywebview?.api?.open_spotify_auth) {
      window.pywebview.api.open_spotify_auth();
  } else {
      window.open('/api/spotify/auth', 'spotifyAuth', 'width=480,height=640');
  }
  ```
  Apply the same guard to any other Spotify-connect entry point in the main app (check `frontend/static/js/modules/auth.js`).
- **Files.** `frontend/static/js/modules/onboarding.js`, `frontend/static/js/modules/auth.js`.

---

## B. Provider + model workflow rework

### B-meta — Workflow analysis

**Current (broken):** Step 2 "Add your OpenAI key" (provider hardcoded) → Step 6 "Pick a model" with provider choice buried behind "Use a different provider…" expandable.

**Proposed:** Provider choice moves to Step 2. Step 6 becomes purely model selection + cost estimate.

```
Step 2:  "Choose your AI provider"
  - Provider dropdown (styled; OpenAI preselected)
  - API key field (label + hint swap per provider)
  - Base URL field (only when Custom)
  - Inline "How do I get this?" expandable (per-provider bullets)
  - Read-full-guide link (only where a guide exists)

Step 6:  "Pick a model"
  - Subtitle: "You chose {Provider}. Pick a model."
  - Model dropdown populated from /api/llm/fetch_models at step activation
  - Loading spinner while fetching; free-text fallback if fetch fails
  - Cost estimate widget below
```

### B.1 — Provider dropdown uses native `<select>`

- **Fix.** Replace with the app's custom dropdown pattern (same as `profileCustomDropdown`).
- **Files.** `frontend/templates/onboarding.html`, `frontend/templates/modals/settings_modal.html`, `frontend/static/css/provider.css`.

### B.2 — Models don't load; cost estimate unavailable

- **Fix chain.**
  1. On Step 6 activation, call `fetchProviderModels()` if the dropdown is empty; show a spinner.
  2. After success, preselect the first id (or the last-used).
  3. Cost estimate auto-refreshes via existing model-change listener.
  4. On failure, show retry inline error + free-text fallback.
- **Files.** `frontend/static/js/modules/onboarding.js`, `frontend/static/js/modules/provider.js`.

### B.3 — Provider hidden behind expandable *(resolved by B-meta)*

### B.4 — Merge Step-2 key with provider choice

- **Fix.** Restructure Step 2 in `onboarding.html`: provider dropdown above the key input; bind `onProviderChange()`; delete the provider expandable from Step 6. Rename Step 2 title: `ob.step2_title` = "Choose your AI provider" / "KI-Anbieter wählen". Step 6 title unchanged; subtitle updated.
- **Files.** `frontend/templates/onboarding.html`, `frontend/static/js/modules/onboarding.js`, `frontend/static/js/modules/provider.js`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`.

### B.5 — Ready overview falsely reports Model as "Set"

- **Cause.** Overview reads `/api/settings` which returns persisted defaults. A fresh install has a default model even if the user skipped Step 6.
- **Fix.** Track in-session changes:
  ```js
  const obTouched = {
      openai_key: false, spotify_cred: false, spotify_conn: false,
      profile: false, model: false,
  };
  ```
  Each step's save handler flips its flag. Overview rows show:
  - **Touched this session** → green ✓ + value
  - **Untouched but previously set** (re-run) → green ✓ + "(from previous setup)"
  - **Untouched and not previously set** → amber ⚠ + "Not set"
  When `?replay=1`, prefill flags as false so re-run users don't see unwarranted amber.
- **Files.** `frontend/static/js/modules/onboarding.js`, `frontend/templates/onboarding.html`.

---

## C. Main-app polish

### C.1 — Quickstart demo autoplay broken

- **Needs investigation.** Likely `qsDemoToggle()` or the auto-advance `setInterval` in `quickstart-demo.js` is not firing. Instrument and verify.
- **Files.** `frontend/static/js/modules/quickstart-demo.js`.

### C.2 — Audio filters no spacing

- **Cause.** `.audio-filter-subpanel` has no top margin.
- **Fix.** Add `margin-top: 16px` (standard component gap). Apply uniformly to all Generate-body subpanels so spacing is consistent.
- **Files.** `frontend/static/css/sections.css`.

### C.3 — Remove duplicate settings from Settings modal

- **Decision (confirmed).** Remove `playlist_size` and `new_artist_pct` from the Settings modal. No migration needed — no user base to protect.
- **Fix.**
  - Delete the two `.form-row` blocks from `settings_modal.html`.
  - Update `Balanced` built-in preset values in `presets.js` to match backend-shipped defaults (`playlist_size=30`, `new_artist_pct=30` per `config.py`).
  - Keep `get_playlist_size()` / `get_new_artist_percentage()` backend accessors — still used as API fallbacks when no preset is active.
  - Drop the now-orphan i18n keys: `settings.playlist_size_*`, `settings.new_artist_pct_*`.
- **Files.** `frontend/templates/modals/settings_modal.html`, `frontend/static/js/modules/presets.js`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json`.

### C.4 — Container horizontal width +10%

- **Fix.** Update `.container` to `max-width: min(1600px, 90vw)` (up from current fixed-ish cap). Verify readability at 1920×1080 and 1366×768.
- **Files.** `frontend/static/css/layout.css`.

---

## D. Seed-from-playlist

### D.1 — Promote seed action out of `⋯` menu

- **Decision (confirmed).** Two cards side-by-side in the Profiles area, replacing the single `+ Create new Profile` CTA. Remove from `⋯` menu.
- **UI.**
  ```
  ┌─ + New profile ─────┐  ┌─ 🎵 From playlist ──────┐
  │ Blank, edit it      │  │ Draft from a Spotify    │
  │ yourself            │  │ playlist you like       │
  └─────────────────────┘  └─────────────────────────┘
  ```
  `+ New profile` = primary (stronger visual), zero-prerequisite. `🎵 From playlist` = secondary but same size, disabled with "Connect Spotify first" helper when Spotify is not connected.
- **State handling.** After picking a playlist, if a profile is currently active, existing "Replace vs Create new" prompt remains.
- **Responsive.** Cards stack vertically below 540 px.
- **Files.** `frontend/templates/train_profile.html`, `frontend/static/js/modules/profile.js`, `frontend/static/js/modules/playlist_seed.js`, `frontend/static/css/sections.css`.

### D.2 — X button wrong position *(resolved inside D.1 refactor)*

- **Fix.** Replace `#playlistSeedModal`'s custom close affordance with the app's standard `.modal-close-btn` (top-right absolute). Match `#credentialsModal` / `#settingsModal`.
- **Files.** `frontend/templates/modals/playlist_seed_modal.html`, `frontend/static/css/playlist_seed.css`.

### D.3 — "No playlists found" after new profile

- **Needs investigation.** Hypotheses: module-level cache not reset on profile change; server endpoint bug; stale spotipy auth. Reproduce → trace → fix. Add "Retry" affordance on empty state.
- **Files.** `frontend/static/js/modules/playlist_seed.js`, possibly `core/src/playlist.py`.

---

## E. Taste dashboard

### E.1 — Not expandable / empty / wrong spacing

- **Fix.**
  1. Verify accordion toggle wiring in `taste_dashboard.js`; use the shared `toggleAccordion()` if not already.
  2. Empty state (`tracks_considered < 10`) renders the existing `dashboard.empty_body` copy — confirm it actually shows.
  3. Add `margin-top: <standard>` to the section for uniform spacing.
- **Files.** `frontend/static/js/modules/taste_dashboard.js`, `frontend/static/css/taste_dashboard.css`, `frontend/templates/taste_dashboard.html`.

---

## F. Profile management

### F.1 — Profile Strength shows stale content after reset

- **Cause.** Reset/Undo actions hit the server but don't clear the DOM textareas; completeness reads live DOM.
- **Fix.** After any reset action, re-fetch profile, programmatically clear textareas, and dispatch `input` events so the completeness listener re-reads:
  ```js
  await fetch('/api/profile/reset', { method: 'POST' });
  await loadProfileIntoForm();
  ['trainVibeDesc','trainCoreDesc','trainMustHave','trainSoftPrefs','trainAvoid']
      .forEach(id => document.getElementById(id).dispatchEvent(new Event('input')));
  ```
- **Files.** `frontend/static/js/modules/profile.js`.

### F.2 — Profile dropdown / burger menu overlap

- **Fix.** Add mutual-exclusion close: when `⋯` opens, call `closeProfileDropdown()`; when profile dropdown opens, call `closeProfileMenu()`. Add click-outside listener closing both. Consider extracting to `frontend/static/js/modules/popovers.js` if more such pairs appear.
- **Files.** `frontend/static/js/modules/profile.js`.

---

## G. Profile editor — flatten structure

- **Decision (confirmed).** Profiles is not an accordion any more; it's a persistent card. The 5 text sub-accordions move to the top level of `#trainSection`.
- **Target layout.**
  ```
  🎯 Music Profile                              [Show/Hide]
     Define your musical taste — genres, moods, must-haves.

  ┌─── Profiles ─────────────────────────────────────────┐
  │  [ Rock                       ▾ ]             [⋯]    │
  │                                                        │
  │  [+ New profile]      [🎵 From playlist]              │
  └────────────────────────────────────────────────────────┘

  [ Profile Strength · 50% ·              ▸ ]
  ████████████░░░░░░░░░░░░░░░░

  ─── Describe Your Vibe          ▾ ───
  ─── Core Description            ▾ ───
  ─── Must Have                   ▾ ───
  ─── Soft Preferences            ▾ ───
  ─── Avoid                       ▾ ───

  [AI Profile Update]   [Save without AI]
  ```
- **Rationale.** Profiles is meta (which profile?); the 5 text sections are content. Same accordion level conflates hierarchy. Flattening — rather than nesting — avoids two-level indentation while preserving the clear mental separation.
- **Files.** `frontend/templates/train_profile.html`, `frontend/static/css/sections.css`.

---

## H. Profile Strength collapsible

- **Fix.** Header (title + percentage + bar) always visible; tick rows + suggestion move behind a chevron toggle. Default: collapsed. Remember state in `localStorage` key `sv.completeness_expanded`.
- **Files.** `frontend/static/js/modules/completeness.js`, `frontend/static/css/completeness.css`, `frontend/templates/train_profile.html`.

---

## I. Generate button + cost estimate layout

- **Fix.** Stack the cost footnote **below** the Generate button (centred), removing the beside-the-button placement that visually fought with "Using preset: Balanced" above.
  ```
                Using preset: Balanced
   ┌──────────────────────────────────────────┐
   │     ▶  Generate & Create Playlist         │
   └──────────────────────────────────────────┘
              💰 ≈ $0.02 · gpt-5.4 · est.
  ```
- **Files.** `frontend/static/css/sections.css`.

---

## J. Cost estimate inline popover

- **Fix.** Replace the "details" link on the Generate-panel footnote with an inline popover that renders the full 6-row cost-estimate card anchored above the footnote. Trigger: click on the whole footnote. Dismiss: click-outside, `Esc`, re-click the trigger.
- **Implementation.** Extract the cost-card DOM into a reusable fragment in `cost_estimate.js` (small `mountCostCard(container)` helper). Reused in both the Settings modal and the new popover — no duplicate HTML.
- **Files.** `frontend/static/js/modules/cost_estimate.js`, `frontend/static/css/cost_estimate.css`, `frontend/templates/generate_section.html`.

---

## K. Burger menu grouping

- **Fix.** Add two section headers to `#settingsDropdown` with a separator between them:
  ```
  CONFIGURATION
  ──────────────
  🔑  Credentials
  ⚙️  Settings
  🎛  Manage presets
  🔌  Disconnect Spotify
  ──────────────
  HELP & GUIDANCE
  ──────────────
  ❓  Help
  🚀  Quick Start
  🪄  Re-run setup
  🔄  Reset tips
  ```
- **Rationale.**
  - **Configuration** = persistent-state actions (keys, model, presets, account session).
  - **Help & Guidance** = things invoked to learn or be re-taught. "Re-run setup" lives here because it's a guided tour, not a settings dialog.
- **Visual spec.**
  - Section headers: uppercase, `0.72rem`, `letter-spacing: 0.06em`, `color: var(--text-muted)`, `font-weight: 600`, padding `10px 14px 4px`. `role="presentation"`.
  - Separator: `1px solid var(--border)`, `margin: 8px 0`.
- **Optional icon cleanup.** `🪄` for Re-run setup (instead of ✨), `🔄` for Reset tips (distinct from `🔁`).
- **Files.** `frontend/templates/settings_gear.html`, `frontend/static/css/components.css`, `frontend/static/i18n/en.json`, `frontend/static/i18n/de.json` (add `nav.group_configuration`, `nav.group_help`).

---

## Architectural decisions recorded

1. **C.3** — Settings modal loses `playlist_size` and `new_artist_pct`. Backend-shipped defaults become the `Balanced` built-in preset's values. No migration — no user base.
2. **D.1** — Seed-from-playlist becomes a first-class action: two side-by-side cards (`+ New profile` / `🎵 From playlist`) in the Profiles card. Removed from `⋯` menu. Existing "Replace vs Create new" confirmation preserved for in-flight seed applied to an existing profile.
3. **G** — Flatten profile editor. Profiles card is persistent (not an accordion); the 5 text sub-accordions sit at the top level of Music Profile.
4. **K** — Burger menu sections: **Configuration** (persistent state) vs **Help & Guidance** (tours / learning / recovery). Re-run setup in the second group because it's a guided tour.

---

## Closing contract for the implementer

- Commit each batch separately. Don't commit mid-batch.
- After each batch, run `python -m pytest core/tests/ frontend/tests/ -v` and the relevant screenshot tests. Fix any regression before moving on.
- Bump `version.py` once after all four batches land.
- i18n: every new user-facing string must exist in both `en.json` and `de.json`.
- Never commit or push without explicit user instruction in the current message — see [`CLAUDE.md`](CLAUDE.md) rule 6.
