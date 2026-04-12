# Wave 2 — Quick wins: inline explanations, completeness meter, Quick/Advanced split, exploration slider, presets

> **Reader.** This document is written for Claude Sonnet 4.6 to implement. It assumes no memory of prior conversations. It is self-contained.
>
> **Prerequisite.** Wave 1 (`wave1_foundation.md`) must be merged first. The reworked onboarding, language relocation, privacy modal, and setup-guide overlay are assumed to exist by the time you start Wave 2.
>
> **Source of truth for *why*.** [`../design.md`](../design.md) § B.2, § C.3, § D.1, § D.2, § D.4.
>
> **Working directory.** `c:\git\spotyvibe`. All paths below are relative to the repo root.
>
> **Conventions.** Vanilla ES modules, no bundler, no framework. Jinja2 templates. Modular CSS. i18n via `data-i18n="key"` + runtime `i18n(key, fallback)`. All user-facing text lives in `frontend/static/i18n/en.json` and `de.json` — never hardcoded. See [`../CLAUDE.md`](../CLAUDE.md).
>
> **What this wave is.** Five "quick win" UX upgrades that land together because they touch the same surfaces (Generate panel, profile editor, Settings modal) and share patterns (inline hints, collapsible "Learn more", the new control-group layout).
>
> **What this wave is NOT.** No playlist seed (Wave 3, C.1). No explainable chips (Wave 3, D.3). No visualisation (Wave 3, F.1). No feature-tip toasts (Wave 3, B.1). No custom LLM endpoints (Wave 4, E.1). No cost estimator (Wave 4, E.2). No voice input (Wave 4, C.2). If you're about to add a chart, a toast, or a provider picker — stop.

---

## 1. Scope map

| Ref | Name | Summary |
|-----|------|---------|
| B.2 | Inline explanations replacing hover tooltips | Convert every hover `data-tooltip`/`.tooltip-trigger` in the Generate panel and Settings modal to an always-visible hint line under the label. Add a collapsible "Learn more ▸" for controls whose explanation needs more than a sentence. Add an `(optional)` badge to genuinely non-critical controls. |
| C.3 | Profile completeness meter | Live 0–100 % strength meter on the profile editor, visible only while < 60 %. Four contributing dimensions with tick marks; one rule-based suggestion line. Updates on input (debounced). |
| D.1 | Quick vs Advanced mode split | Tabbed split at the top of the Generate panel. Quick mode exposes size + exploration slider + Generate. Advanced mode exposes everything today's Generate panel has plus the exploration slider and the preset picker. |
| D.2 | Exploration vs Accuracy slider | 5-notch composite slider appearing in both modes. Sets new-artist %, emerging-only, temperature. In Advanced, it drives the individual knobs visibly; hand-editing any knob switches the slider to a dotted "custom" indicator. |
| D.4 | Named generation presets | Preset system for generation settings (not for taste profiles — those already exist). 3 built-in presets ship: Safe picks, Balanced, Deep discovery. User presets stack on top of a divider; built-in below, immutable, clone-to-edit. Preset manager sub-screen in the gear menu for rename/delete/reorder. Import/export JSON. |

---

## 2. Files to create, modify, delete

### Create

| Path | Purpose |
|------|---------|
| `frontend/static/css/completeness.css` | Profile completeness meter styling. |
| `frontend/static/css/exploration_slider.css` | 5-notch composite slider. |
| `frontend/static/css/presets.css` | Preset dropdown, preset manager modal. |
| `frontend/static/js/modules/completeness.js` | Completeness-score calculator, meter DOM updater. |
| `frontend/static/js/modules/exploration.js` | Slider state → underlying knobs mapping and reverse detection. |
| `frontend/static/js/modules/presets.js` | Preset CRUD, built-in catalogue, import/export, dropdown rendering. |
| `frontend/static/js/modules/quick_advanced.js` | Generate-panel mode toggle + control sync between modes. |
| `frontend/templates/modals/preset_manager_modal.html` | Preset manager sub-screen. |
| `implementation/wave2_quick_wins.md` | **This file.** |

### Modify

| Path | What changes |
|------|--------------|
| `frontend/templates/generate_section.html` | Add mode toggle header, Quick/Advanced body containers, exploration slider, preset picker row, `(optional)` badges, inline hints + learn-more under every control. |
| `frontend/templates/train_profile.html` | Add completeness meter placeholder element and mount point. |
| `frontend/templates/modals/settings_modal.html` | Replace `.tooltip-trigger` spans with inline hint lines. Add `Learn more ▸` for Playlist Size and New Artist %. Add `(optional)` badge to Debug Mode. |
| `frontend/templates/base.html` | Include `preset_manager_modal.html`. |
| `frontend/templates/settings_gear.html` | Add "Manage presets" menu item. |
| `frontend/static/css/base.css` | Add tokens for the exploration slider + completeness bar (see § 3). |
| `frontend/static/css/forms.css` | Add a shared `.inline-hint` class for the new always-visible hint lines. Add `.learn-more` collapsible. Add `.optional-badge`. |
| `frontend/static/css/sections.css` | Add Quick/Advanced mode-toggle styles. |
| `frontend/static/js/main.js` | Wire the new modules (`completeness.js`, `exploration.js`, `presets.js`, `quick_advanced.js`) into bootstrap. |
| `frontend/static/js/modules/pipeline.js` (if it exists; otherwise wherever the generation request is built) | Send `temperature` in the generation payload. Derive it from the exploration slider state. |
| `frontend/static/js/modules/audio-filters.js` | Remove the `data-tooltip` conversion — the filter labels now display inline hints rendered from the template. The per-field "live hint" (`af-*-hint`) stays. |
| `frontend/static/i18n/en.json` | Add every key listed in § 11. |
| `frontend/static/i18n/de.json` | Same keys with German strings. |
| `app.py` | Accept `temperature` in the generation-request payload. Nothing else. |
| `core/src/openai_http.py` (or wherever `temperature` is forwarded to the API) | Pass `temperature` when present in the request. |
| `frontend/tests/test_documentation_screenshots.py` | New captures for Quick mode, Advanced mode, exploration slider states, preset dropdown, preset manager, completeness meter. See § 12. |
| `frontend/tests/test_frontend.py` | New smoke tests for preset CRUD, mode switching, exploration slider, completeness calculation. See § 13. |

### Delete

Nothing. All Wave 1 surfaces remain.

### What is **not** removed

- `data-tooltip` attribute support in `ui.js` (the global tooltip machinery). It still powers icon-only buttons elsewhere (track likes, refresh buttons). We're removing *hover-only tooltips on primary controls*, not the tooltip infrastructure.
- The hover tooltips on track-action buttons (👍 Like, 👎 Dislike, ✕ Remove, Spotify link icons). Those are icon-only affordances — tooltips are the right UI there.

---

## 3. Shared patterns (read first)

### 3.1 The `.inline-hint` pattern (replaces hover tooltips on primary controls)

Every control that used to rely on a `?` tooltip now renders:

```html
<div class="form-row">
  <label for="settings-playlist-size">
    <span data-i18n="settings.playlist_size_label">Playlist Size</span>
    <span class="optional-badge hidden" data-i18n="common.optional">(optional)</span>
  </label>
  <input id="settings-playlist-size" type="number" min="10" max="30" step="5">
  <p class="inline-hint" data-i18n="settings.playlist_size_hint">How many tracks GPT will suggest in one run. Max 30.</p>
  <details class="learn-more">
    <summary data-i18n="common.learn_more">Learn more</summary>
    <div class="learn-more-body" data-i18n="settings.playlist_size_learn_more">
      SpotyVibe fetches tracks in blocks of 10 per GPT request. Higher totals mean more requests, longer waits, and higher cost. 30 is the practical ceiling — beyond that GPT starts repeating itself across blocks.
    </div>
  </details>
</div>
```

**CSS specs** (add to `forms.css`):

- `.inline-hint` — `font-size: 0.82rem; color: var(--text-muted); margin: 4px 0 0; line-height: 1.4;`
- `.learn-more` — `margin-top: 6px; font-size: 0.82rem;`
- `.learn-more > summary` — `color: var(--primary); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; list-style: none; padding: 2px 0;` Hover: `text-decoration: underline;` Remove default disclosure triangle: `.learn-more > summary::-webkit-details-marker { display: none; } .learn-more > summary::marker { content: ""; }` Insert chevron: `.learn-more > summary::before { content: "▸"; display: inline-block; transition: transform 150ms ease; } .learn-more[open] > summary::before { transform: rotate(90deg); }`
- `.learn-more-body` — `margin-top: 8px; padding: 10px 12px; background: var(--bg-input); border-radius: var(--radius-sm); color: var(--text-secondary); line-height: 1.45;`
- `.optional-badge` — `display: inline-block; margin-left: 6px; padding: 2px 8px; font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); background: var(--bg-input); border-radius: var(--radius-pill); vertical-align: middle;`

### 3.2 New design tokens (append to `base.css` `:root`)

```
--slider-track-h: 4px;
--slider-thumb-size: 18px;
--meter-bar-h: 8px;
--meter-ok: var(--warning);        /* 30-60% yellow */
--meter-strong: var(--success);    /* ≥60% green */
--meter-weak: var(--error);        /* <30% red */
```

### 3.3 Preset data schema

A preset is a JSON object:

```json
{
  "id": "user_1730145012345",
  "name": "Morning coffee",
  "builtin": false,
  "version": 1,
  "settings": {
    "size": 20,
    "exploration_notch": 2,
    "new_artist_pct": 25,
    "emerging_only": false,
    "temperature": 0.7,
    "audio_filters": {
      "energy": { "min": null, "max": 60 },
      "valence": { "min": 40, "max": null },
      "tempo": { "min": null, "max": null },
      "danceability": { "min": null, "max": null },
      "acousticness": { "min": null, "max": null }
    },
    "model_override": null
  }
}
```

**Fields:**
- `id` — `"builtin_safe_picks"` / `"builtin_balanced"` / `"builtin_deep_discovery"` for built-ins, `"user_" + Date.now()` for user-created.
- `name` — display string. User-editable for user presets only.
- `builtin` — immutable flag. Built-in presets have `true`; user presets `false`.
- `version` — schema version, starts at `1`. Bump + migrate on breaking changes.
- `exploration_notch` — `1..5` or `"custom"` (string literal) when underlying values have been hand-edited.
- `new_artist_pct` — `0..100`. Derived from notch unless custom.
- `emerging_only` — boolean.
- `temperature` — `0.0..2.0`. Derived from notch unless custom.
- `audio_filters` — same structure as today's `audio_filters` on generate payloads. `null` means "unspecified".
- `model_override` — model id string or `null` (use global default).

**Storage.** User presets live in `localStorage` under key `sv.presets.user` as a JSON array. Built-in presets are defined in `presets.js` and never stored. All preset ids start with `builtin_` or `user_` — that prefix is the sole distinguisher for deletion/rename/clone behaviour.

### 3.4 Built-in preset catalogue

Define exactly three built-ins in `presets.js`:

```js
export const BUILTIN_PRESETS = [
  {
    id: 'builtin_safe_picks',
    name: 'Safe picks',        // i18n key: preset.builtin_safe_picks
    builtin: true,
    version: 1,
    settings: {
      size: 20,
      exploration_notch: 1,
      new_artist_pct: 10,
      emerging_only: false,
      temperature: 0.5,
      audio_filters: EMPTY_FILTERS,
      model_override: null,
    },
  },
  {
    id: 'builtin_balanced',
    name: 'Balanced',           // i18n key: preset.builtin_balanced
    builtin: true,
    version: 1,
    settings: {
      size: 25,
      exploration_notch: 3,
      new_artist_pct: 50,
      emerging_only: false,
      temperature: 0.8,
      audio_filters: EMPTY_FILTERS,
      model_override: null,
    },
  },
  {
    id: 'builtin_deep_discovery',
    name: 'Deep discovery',     // i18n key: preset.builtin_deep_discovery
    builtin: true,
    version: 1,
    settings: {
      size: 30,
      exploration_notch: 5,
      new_artist_pct: 90,
      emerging_only: true,
      temperature: 1.0,
      audio_filters: EMPTY_FILTERS,
      model_override: null,
    },
  },
];
```

Render the `name` field through `i18n('preset.builtin_safe_picks', preset.name)` so localisation can override the default English.

---

## 4. B.2 — Inline explanations replacing hover tooltips

### 4.1 Controls to migrate (exhaustive list)

| Location | Control | Current mechanism | New mechanism |
|----------|---------|------------------|---------------|
| `generate_section.html` | Audio filter: Energy | `data-tooltip` on `.af-label-tip` | Inline hint below label + Learn more |
| `generate_section.html` | Audio filter: Valence | `data-tooltip` | Inline hint + Learn more |
| `generate_section.html` | Audio filter: Tempo | `data-tooltip` | Inline hint + Learn more |
| `generate_section.html` | Audio filter: Danceability | `data-tooltip` | Inline hint + Learn more |
| `generate_section.html` | Audio filter: Acousticness | `data-tooltip` | Inline hint + Learn more |
| `generate_section.html` | Emerging-artists checkbox | Already has inline hint — keep | No change except move inside Advanced mode |
| `settings_modal.html` | Playlist Size | `.tooltip-trigger` "?" span | Inline hint + Learn more |
| `settings_modal.html` | New Artist % | `.tooltip-trigger` "?" span | Inline hint + Learn more |
| `settings_modal.html` | Used Model | none | Add inline hint + Learn more |
| `settings_modal.html` | Debug Mode | none | Add `(optional)` badge + inline hint |

### 4.2 `(optional)` badge — where to apply

Apply the badge **only** to controls that can be left at defaults with zero quality loss:

- Audio filters (section header, already has "(optional)" — keep existing; restyle with the new `.optional-badge` class for consistency).
- Emerging-artists checkbox.
- Debug Mode.

Do **not** apply to: Playlist Size, New Artist %, Used Model, Exploration slider. Those are primary controls with sensible defaults but meaningful behaviour.

### 4.3 Exact inline-hint copy per control

All strings go through i18n — keys listed in § 11. English short hint + "Learn more" long text:

| Control | Short hint (always visible) | Learn more (collapsed) |
|---------|-----------------------------|------------------------|
| Energy | How intense and active the track feels. | Higher values push GPT toward loud, fast, driving tracks. Lower values favour calm, ambient music. Leave empty to let any value through. |
| Valence | Musical positiveness — happy vs sad. | Valence is Spotify's 0–100 measurement of emotional tone. High = cheerful, euphoric; low = sad, angry, dark. |
| Tempo | Speed in beats per minute (BPM). | Typical ranges: slow ballads 60–80, mid-tempo pop 90–110, dance 120–140, fast rock/electronic 140–180. |
| Danceability | How suitable a track is for dancing. | Based on tempo stability, rhythm regularity, and beat strength. Not the same as "upbeat" — a steady ambient groove can score high. |
| Acousticness | Acoustic vs electronic. | High = unplugged, live instruments, folk. Low = synths, heavy production, electronic. |
| Emerging artists | Restrict to artists who debuted in the last 6 months. | A strong bias toward discovery. Skips well-known acts entirely. Works best in combination with a high exploration setting. |
| Playlist Size | How many tracks to generate (max 30). | Max capped at 30 — beyond that GPT starts repeating itself across 10-track fetch blocks, and review fatigue sets in. If you want a longer session, run twice with different presets. |
| New Artist % | Minimum share of suggestions from artists you haven't listened to yet. | Higher pushes exploration; lower keeps things familiar. The exploration slider above drives this — edit here to override. |
| Used Model | Which OpenAI model produces your suggestions. | Higher-tier models cost more per run. For music suggestions the difference is noticeable but not dramatic; gpt-4o-mini is a sensible default. |
| Debug Mode | Log every GPT request and response to a local file. | For developers and bug reports. Never affects behaviour. The log file stays on your device — see the Privacy modal. |

### 4.4 Example screen fragment — Settings modal, Playlist Size row

**Before:**

```html
<label for="settings-playlist-size" class="modal-label-with-tooltip">
  Playlist Size
  <span class="tooltip-trigger" data-tooltip="Tracks are fetched in blocks of 10…">?</span>
</label>
<input id="settings-playlist-size" type="number" min="10" step="10" …>
<div class="cred-status" id="status-settings-playlist-size"></div>
```

**After:**

```html
<div class="form-row">
  <label for="settings-playlist-size" data-i18n="settings.playlist_size_label">Playlist Size</label>
  <input id="settings-playlist-size" type="number" min="10" max="30" step="5">
  <p class="inline-hint" data-i18n="settings.playlist_size_hint">How many tracks to generate (max 30).</p>
  <details class="learn-more">
    <summary data-i18n="common.learn_more">Learn more</summary>
    <div class="learn-more-body" data-i18n="settings.playlist_size_learn_more">
      Max capped at 30 — beyond that GPT starts repeating itself across 10-track fetch blocks, and review fatigue sets in. If you want a longer session, run twice with different presets.
    </div>
  </details>
  <div class="cred-status" id="status-settings-playlist-size"></div>
</div>
```

Notice the `max="30"`. This enforces the Wave-2 hard cap (see design.md D.1). The input also needs a browser-side validator: on blur, clamp to `[10, 30]`. Implement in `quick_advanced.js` or a new tiny shared clamp helper.

---

## 5. C.3 — Profile completeness meter

### 5.1 Mount point

In `train_profile.html`, insert a new block *between* the `#accProfiles` accordion and the `#accVibeDesc` accordion:

```html
<div id="profileCompletenessCard" class="completeness-card hidden" role="status" aria-live="polite">
  <div class="completeness-header">
    <span class="completeness-title" data-i18n="profile.strength">Profile Strength</span>
    <span class="completeness-score" id="completenessScore">0%</span>
  </div>
  <div class="completeness-bar">
    <div class="completeness-bar-fill" id="completenessBarFill" style="width: 0%"></div>
  </div>
  <ul class="completeness-ticks" id="completenessTicks">
    <!-- rendered dynamically by completeness.js -->
  </ul>
  <p class="completeness-suggestion" id="completenessSuggestion"></p>
</div>
```

### 5.2 Visibility

- Hidden by default (`hidden` class).
- Compute score on:
  1. Profile editor accordion opening.
  2. Every `input`/`change` on the 5 textareas (debounced 250 ms).
  3. After `POST /api/profile` succeeds (AI Profile Update or Save without AI).
- Visible iff score < 60. If the score crosses 60, add an `is-complete` transient class for 2 seconds (light green flash) and then hide.

### 5.3 Score dimensions

```
Core Description  40%
  Strong: ≥ 80 characters AND ≥ 1 genre/mood word
  Partial: 20–79 characters OR < 1 mood word
  Empty: 0 characters

Must Have         25%
  Strong: ≥ 2 non-empty lines
  Partial: 1 line
  Empty: 0 lines

Soft Preferences  15%
  Strong: ≥ 1 non-empty line
  Empty: 0 lines

Avoid             10%
  Strong: ≥ 1 non-empty line
  Empty: 0 lines

User-edited       10%
  Strong: any field has been touched since load
  Empty: pristine prefill
```

**Mood/genre word set** (English; reuse for German since these are usually English loanwords in practice): `rock, pop, jazz, hiphop, hip-hop, rap, indie, electronic, classical, metal, folk, country, ambient, techno, house, soul, funk, blues, punk, upbeat, chill, energetic, melancholic, happy, sad, dreamy, aggressive, calm, theatrical, atmospheric, driving`. Case-insensitive substring match.

Each dimension yields a value of `1.0` (strong), `0.5` (partial if present in the rubric), or `0.0` (empty). The weighted sum produces a 0–100 % score.

### 5.4 Tick list render

Each dimension is a row in `<ul id="completenessTicks">`:

```html
<li class="completeness-tick strong">
  <span class="tick-icon">✓</span>
  <span class="tick-label" data-i18n="profile.core_description">Core Description</span>
  <span class="tick-value">150 chars</span>
</li>
```

State classes: `.strong` (green ✓), `.partial` (yellow ◐), `.empty` (grey ○). `tick-value` is a short summary string rendered client-side.

### 5.5 Suggestion line

Rule-based (not GPT). Priority order — show the first matching:

1. If Core Description is empty: "Add a few sentences describing your ideal sound — that's the foundation."
2. If Must Have is empty: "List 2–3 non-negotiable traits — things every suggestion must have."
3. If Soft Preferences is empty: "Add a soft preference for variety."
4. If Avoid is empty: "Add at least one thing to avoid — it sharpens the profile."
5. If Core Description is partial (< 80 chars): "Expand your core description — a sentence or two more helps GPT."
6. Else (≥ 60 %): empty — the card is about to hide anyway.

i18n keys: `profile.suggest_core_empty`, `profile.suggest_must_empty`, etc. (§ 11).

### 5.6 Meter bar styling

- `.completeness-card` — `background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; margin: 12px 0 18px;`
- `.completeness-header` — `display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;`
- `.completeness-title` — `font-size: 0.92rem; font-weight: 600; color: var(--text-primary);`
- `.completeness-score` — `font-size: 1.1rem; font-weight: 700; font-variant-numeric: tabular-nums;`
- `.completeness-bar` — `height: var(--meter-bar-h); background: var(--border); border-radius: var(--radius-pill); overflow: hidden;`
- `.completeness-bar-fill` — `height: 100%; transition: width 250ms ease, background 250ms ease;`
- Score < 30: fill background = `--meter-weak`; text colour matches.
- Score 30–59: `--meter-ok`.
- Score ≥ 60: `--meter-strong`.
- `.completeness-ticks` — `list-style: none; padding: 0; margin: 12px 0 0;`
- `.completeness-tick` — `display: flex; gap: 10px; align-items: center; padding: 4px 0; font-size: 0.85rem;`
- `.tick-icon` — `width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; flex-shrink: 0;`. `.strong .tick-icon` = green bg 0.12 alpha. `.partial .tick-icon` = yellow. `.empty .tick-icon` = grey with a thin border.
- `.completeness-suggestion` — `margin-top: 10px; font-size: 0.82rem; color: var(--text-secondary); font-style: italic;`

---

## 6. D.1 — Quick vs Advanced mode split

### 6.1 Generate panel layout (new)

The expanded Generate section gets a new sub-structure:

```
.generate-section
├── .train-header (unchanged — collapsible bar with "🎧 Discover Music")
└── .train-body
    │
    ├── .gen-mode-tabs                      ← NEW, pill toggle
    │   ├── button.gen-mode-btn.active data-mode="quick"
    │   └── button.gen-mode-btn        data-mode="advanced"
    │
    ├── .gen-mode-body.gen-mode-body--quick    ← visible by default
    │   ├── .gen-size-row
    │   │   ├── label "Playlist size"
    │   │   ├── input[type=range min=10 max=30 step=5]
    │   │   ├── .gen-size-value (live readout, e.g. "25 tracks")
    │   │   ├── p.inline-hint
    │   │   └── details.learn-more
    │   ├── .exploration-row                ← the new slider (see § 7)
    │   └── .run-section                     ← existing Generate button
    │
    └── .gen-mode-body.gen-mode-body--advanced.hidden
        ├── .preset-row                      ← NEW, see § 9
        ├── .gen-size-row                    ← duplicate structure; value kept in sync
        ├── .exploration-row                 ← same instance? or mirrored? — see § 7.3
        ├── .playlist-mode-row               ← existing; MOVED here
        ├── .emerging-artists-row            ← existing; MOVED here
        ├── .audio-filter-subpanel           ← existing; MOVED here
        ├── .new-artist-pct-row              ← NEW, pulled down from Settings modal for Advanced exposure
        ├── .dep-chips-row                   ← existing "depOpenai / depSpotify"
        └── .run-section                     ← existing Generate button
```

The `.run-section` appears in **both** modes (there is one Generate button per mode, each wired to the same `runPipeline()`). If that duplication is ugly, keep a single `.run-section` outside both `.gen-mode-body` elements — but then the Quick mode layout needs a placeholder at the bottom. Implementer's choice; the duplicate is simpler.

### 6.2 Mode toggle UI

**`.gen-mode-tabs`** (a pill-shaped segmented control at the top of the body):

- `display: inline-flex; background: var(--bg-input); padding: 4px; border-radius: var(--radius-pill); border: 1px solid var(--border); margin-bottom: 18px;`
- Each `.gen-mode-btn` — `border: none; background: transparent; color: var(--text-secondary); font-size: 0.88rem; font-weight: 600; padding: 8px 18px; border-radius: var(--radius-pill); cursor: pointer; transition: background 150ms, color 150ms;`
- Active state: `background: var(--primary); color: var(--btn-cta-text);`
- Hover (inactive): `color: var(--text-primary);`

**Width behaviour:** the tab row is `inline-flex`, so it auto-sizes. It is left-aligned in the body.

### 6.3 Mode persistence

- `localStorage` key: `sv.gen_mode` = `"quick"` or `"advanced"`.
- Default on first run: `"quick"`.
- Switching mode writes to `localStorage` and toggles visibility of the two `.gen-mode-body` elements.
- The mode toggle does **not** reset any field value. Fields shared between modes (size, exploration slider) stay in sync — see § 7.3.

### 6.4 `runPipeline()` integration

Whichever mode is active, `runPipeline()` reads the current values from the *active* `.gen-mode-body`. Implementation: every field carries both a `#id` and a shared `.gen-*` class. The pipeline reads from the active mode's elements only (query `.gen-mode-body:not(.hidden) .gen-field-size input` etc.).

### 6.5 Copy

- Quick tab label: `gen.mode_quick` → "Quick"
- Advanced tab label: `gen.mode_advanced` → "Advanced"
- Size label (both modes): `gen.size_label` → "Playlist size"
- Size readout suffix: `gen.size_suffix` → "tracks"

---

## 7. D.2 — Exploration vs Accuracy slider

### 7.1 Slider markup

```html
<div class="exploration-row">
  <div class="exploration-header">
    <label for="explorationSlider" class="exploration-label" data-i18n="gen.exploration_label">Exploration vs Accuracy</label>
    <span class="exploration-value" id="explorationValueLabel" data-i18n="gen.exploration_notch_3">Balanced</span>
  </div>
  <div class="exploration-slider-wrap">
    <input
      type="range"
      id="explorationSlider"
      class="exploration-slider"
      min="1" max="5" step="1" value="3"
      aria-label="Exploration slider"
    >
    <div class="exploration-ticks" aria-hidden="true">
      <span class="tick"></span><span class="tick"></span><span class="tick"></span><span class="tick"></span><span class="tick"></span>
    </div>
    <div class="exploration-edge-labels" aria-hidden="true">
      <span data-i18n="gen.exploration_left">Familiar</span>
      <span data-i18n="gen.exploration_right">Adventurous</span>
    </div>
  </div>
  <p class="inline-hint" id="explorationHint" data-i18n="gen.exploration_hint_3">Balanced — roughly half new artists, moderate novelty.</p>
</div>
```

### 7.2 Notch → underlying values mapping (client-side only; `exploration.js`)

```js
export const EXPLORATION_NOTCHES = {
  1: { label: 'gen.exploration_notch_1', hint: 'gen.exploration_hint_1', new_artist_pct: 10, emerging_only: false, temperature: 0.5 },
  2: { label: 'gen.exploration_notch_2', hint: 'gen.exploration_hint_2', new_artist_pct: 25, emerging_only: false, temperature: 0.7 },
  3: { label: 'gen.exploration_notch_3', hint: 'gen.exploration_hint_3', new_artist_pct: 50, emerging_only: false, temperature: 0.8 },
  4: { label: 'gen.exploration_notch_4', hint: 'gen.exploration_hint_4', new_artist_pct: 70, emerging_only: false, temperature: 0.9 },
  5: { label: 'gen.exploration_notch_5', hint: 'gen.exploration_hint_5', new_artist_pct: 90, emerging_only: true,  temperature: 1.0 },
};
```

When the slider changes:
1. Read new notch.
2. Update `explorationValueLabel` and `explorationHint` text via i18n.
3. Write the notch's `new_artist_pct` into `#settings-new-artist-pct` (settings modal) and any Advanced-mode field that displays it.
4. Write `emerging_only` into `#emergingArtistsCheckbox`.
5. Stash the notch into `localStorage` (`sv.exploration_notch`).
6. Temperature is in-memory only — picked up at generation time.

### 7.3 Bidirectional sync (Advanced hand-editing → "custom" indicator)

In Advanced mode, the user can edit `new_artist_pct` and `emerging_only` individually. When either changes to a value not matching **any** notch's mapping exactly:

- Slider thumb is rendered in a "between-notches" position (half-step between the two closest notches; see § 7.4).
- `explorationValueLabel` shows `gen.exploration_custom` → "Custom".
- `explorationHint` shows `gen.exploration_hint_custom` → "Custom mix — edit the slider to jump back to a preset."
- Slider thumb gets a `--custom` CSS modifier: dotted border instead of solid.

Clicking the slider (moving to any notch) exits custom state and re-applies the notch's mapping overwrites.

### 7.4 Slider visual styling

- `.exploration-slider-wrap` — `position: relative; padding: 6px 0 28px;` (room for edge labels below).
- `.exploration-slider` (native `input[type=range]` styled cross-browser):
  - Track: `background: var(--border); height: var(--slider-track-h); border-radius: 2px;`
  - Filled portion (left of thumb) uses a gradient overlay; implementation trick: a second `div.exploration-slider-fill` positioned absolutely inside `.exploration-slider-wrap` with `width: calc(((value - 1) / 4) * 100%)` — updated on `input` events. Background `linear-gradient(90deg, var(--primary), var(--accent-teal))`.
  - Thumb: `appearance: none; width: var(--slider-thumb-size); height: var(--slider-thumb-size); background: var(--primary); border: 2px solid var(--bg-card); border-radius: 50%; box-shadow: 0 2px 8px var(--glow-green); cursor: pointer;`
  - Thumb custom state: `.exploration-slider--custom::-webkit-slider-thumb { border-style: dashed; background: var(--bg-elevated); }` — plus Firefox equivalent.
- `.exploration-ticks` — absolute row of 5 short dashes positioned above the track at `1, 25, 50, 75, 100%`.
- `.exploration-edge-labels` — `position: absolute; bottom: 0; left: 0; right: 0; display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;`
- `.exploration-value` — `font-size: 0.88rem; color: var(--primary); font-weight: 600;`

### 7.5 Keyboard

The native `<input type="range">` already supports arrow keys. No extra code.

### 7.6 Both-mode instance

The slider exists in Quick and in Advanced — use **two** DOM instances but one state owner (`exploration.js`). When the notch changes in one instance, `exploration.js` updates the other. Avoid rendering only in the visible mode to prevent a flicker on mode switch.

---

## 8. D.4 — Named generation presets

### 8.1 Preset dropdown (visible in Advanced mode only)

Mount: `.preset-row` at the top of `.gen-mode-body--advanced`.

```html
<div class="preset-row">
  <label for="presetDropdown" class="preset-label" data-i18n="preset.label">Preset</label>
  <div class="preset-dropdown-wrap">
    <button
      class="preset-dropdown-trigger"
      id="presetDropdownTrigger"
      onclick="togglePresetDropdown()"
      aria-haspopup="listbox"
      aria-expanded="false"
    >
      <span class="preset-dropdown-name" id="presetDropdownName">Balanced (built-in)</span>
      <span class="preset-dropdown-chevron" aria-hidden="true">▾</span>
    </button>
    <ul class="preset-dropdown-list hidden" id="presetDropdownList" role="listbox">
      <!-- populated dynamically; see § 8.2 -->
    </ul>
  </div>
  <button class="preset-save-btn" onclick="openSaveAsPresetDialog()" data-i18n="preset.save_current">💾 Save current as preset…</button>
</div>
```

### 8.2 Dropdown list structure

```
[ Balanced (built-in) ▾ ]
  ┌────────────────────────────────┐
  │ Your presets                   │  ← section header, muted, uppercase, 0.72rem
  │                                │
  │   Morning coffee         ✓ [⋯] │  ← checkmark = active; [⋯] opens per-item menu
  │   Workout mix              [⋯] │
  │   Deep dive                [⋯] │
  │                                │
  │ ─────────────────────────      │  ← divider (1px var(--border))
  │                                │
  │ Built-in                       │  ← section header
  │                                │
  │   Safe picks          [clone]  │
  │   Balanced            [clone]  │
  │   Deep discovery      [clone]  │
  │                                │
  │ ─────────────────────────      │
  │                                │
  │   [💾 Save current as preset…] │
  │   [⚙ Manage presets…]          │
  └────────────────────────────────┘
```

**Render rules:**

- If the user has **zero** user presets: suppress the "Your presets" header and its divider. Dropdown opens directly to the "Built-in" section.
- Active preset (the one currently applied to the form) gets a `✓` on the right of its row. Only one preset can be active at a time. If the user hand-edits a field, the active flag is cleared and the trigger label shows `gen.preset_custom_unsaved` → "Custom (unsaved)".
- `[⋯]` on user rows opens a tiny inline menu: Rename, Delete, Export. Implement as a sub-popover, anchored to the row. Keep it simple — a fixed-position small card with three `<button>`s.
- `[clone]` on built-in rows creates a new user preset copying the built-in's settings with name `"{builtin_name} (copy)"`. It is immediately selected. No confirmation.

**Styling:**

- `.preset-dropdown-list` — `position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-card); z-index: 100; padding: 6px 0; max-height: 400px; overflow-y: auto; margin-top: 6px;`
- `.preset-section-header` — `padding: 6px 12px; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted);`
- `.preset-item` — `display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer;` Hover: `background: var(--bg-elevated);`
- `.preset-item--active` — `color: var(--primary);`
- `.preset-item-name` — `flex: 1;`
- `.preset-item-action` — text-muted, icon button on hover becomes primary.

### 8.3 "Save current as preset" dialog

Use a minimal modal — not a full page. Reuse `.modal-overlay` styles from existing modals.

```html
<div class="modal-overlay" id="savePresetModal" role="dialog" aria-modal="true" aria-labelledby="savePresetTitle" onclick="if(event.target===this)closeModal('savePresetModal')">
  <div class="modal" style="max-width: 420px;">
    <h2 id="savePresetTitle" data-i18n="preset.save_title">Save preset</h2>
    <div class="form-row">
      <label for="savePresetInput" data-i18n="preset.name_label">Name</label>
      <input id="savePresetInput" type="text" maxlength="40" data-i18n-placeholder="preset.name_placeholder" placeholder="e.g. Workout mix">
      <p class="inline-hint" data-i18n="preset.name_hint">Stored on your device only.</p>
    </div>
    <div class="modal-actions">
      <button class="btn btn-save" onclick="confirmSaveAsPreset()" data-i18n="btn.save">Save</button>
      <button class="btn btn-cancel" onclick="closeModal('savePresetModal')" data-i18n="btn.cancel">Cancel</button>
    </div>
  </div>
</div>
```

### 8.4 Preset manager modal

File: `frontend/templates/modals/preset_manager_modal.html`. Included from `base.html`.

```html
<div class="modal-overlay" id="presetManagerModal" role="dialog" aria-modal="true" aria-labelledby="presetManagerTitle" onclick="if(event.target===this)closeModal('presetManagerModal')">
  <div class="modal" style="max-width: 560px;">
    <h2 id="presetManagerTitle" data-i18n="preset.manager_title">Manage presets</h2>
    <p class="inline-hint" data-i18n="preset.manager_subtitle">Drag to reorder your own presets. Built-in presets are fixed.</p>

    <ul class="preset-manager-list" id="presetManagerUserList">
      <!-- user rows: drag-handle, name (editable on click), export, delete -->
    </ul>

    <h3 class="preset-manager-section" data-i18n="preset.builtin_header">Built-in</h3>
    <ul class="preset-manager-list" id="presetManagerBuiltinList">
      <!-- builtin rows: name (readonly), clone button -->
    </ul>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="importPresetFile()" data-i18n="preset.import">⬆ Import preset…</button>
      <input id="presetImportInput" type="file" accept="application/json,.json" style="display:none;">
      <button class="btn btn-cancel" onclick="closeModal('presetManagerModal')" data-i18n="btn.close">Close</button>
    </div>
  </div>
</div>
```

- Drag-handle uses HTML5 DnD or a small `Sortable`-style minimal implementation. Keep it vanilla — a 15-line pointerdown/pointermove/pointerup listener is enough.
- Renaming: click the name turns the row into `<input>`, blur or Enter saves, Esc cancels.
- Exporting: `Blob([JSON.stringify(preset, null, 2)], { type: 'application/json' })` → temporary `<a href=objectURL download=...>`.
- Deleting: inline `✕` button with a small confirmation tooltip ("Delete? [Yes] [No]") — no browser `confirm()`.
- Importing: file picker → parse JSON → validate shape (id, name, settings object with expected keys) → assign a new `user_` id (don't trust imported ids, to avoid clobbering existing presets) → append to user list.

### 8.5 Gear menu integration

`settings_gear.html` — add one more item to `#settingsDropdown`, right under "Settings":

```html
<button role="menuitem" onclick="openModal('presetManagerModal'); closeSettingsMenu();"><span aria-hidden="true">🎛</span> <span data-i18n="nav.manage_presets">Manage presets</span></button>
```

---

## 9. Backend — minimal changes

### 9.1 Accept `temperature` in the generation endpoint

Find the route that starts a generation (likely `/api/generate` or similar in `app.py`). The current payload probably includes `new_artist_pct`, `emerging_only`, `audio_filters`. Add `temperature`:

- Accept a float between `0.0` and `2.0`. Clamp server-side. Reject values outside that range with 400.
- If `temperature` is absent from the payload, use the current implicit default (whatever `openai_http.py` uses today).

### 9.2 Forward `temperature` to OpenAI

In `core/src/openai_http.py` (or wherever completions are called), pass the `temperature` field through to the OpenAI request body. No fallback in this layer; the caller is responsible for providing a value.

### 9.3 Everything else

No new endpoints, no new storage, no migration. Presets are entirely client-side; the backend never sees them.

---

## 10. Wiring — `main.js` bootstrap additions

After the existing module initialisations, add (pseudocode):

```js
import * as Completeness from './modules/completeness.js';
import * as Exploration from './modules/exploration.js';
import * as Presets from './modules/presets.js';
import * as QuickAdvanced from './modules/quick_advanced.js';

window.addEventListener('DOMContentLoaded', () => {
    QuickAdvanced.init();       // restore mode from localStorage, wire toggle
    Exploration.init();         // wire both slider instances, bidirectional sync
    Presets.init();             // load user presets from localStorage, render dropdown
    Completeness.init();        // wire observer on profile editor fields
});
```

Order matters: `QuickAdvanced.init()` before `Exploration.init()` because the slider lives inside the mode bodies and needs the mode to be resolved first.

---

## 11. i18n keys

Append to `en.json` and `de.json`. Existing keys that are reused (emerging-artists hint, etc.) are **not** listed.

```
# Common
common.learn_more              = "Learn more"                            / "Mehr erfahren"
common.optional                = "(optional)"                            / "(optional)"

# Generate panel — modes
gen.mode_quick                 = "Quick"                                 / "Schnell"
gen.mode_advanced              = "Advanced"                              / "Erweitert"
gen.size_label                 = "Playlist size"                         / "Playlist-Größe"
gen.size_suffix                = "tracks"                                / "Tracks"

# Exploration slider
gen.exploration_label          = "Exploration vs Accuracy"               / "Erkundung vs. Treue"
gen.exploration_left           = "Familiar"                              / "Vertraut"
gen.exploration_right          = "Adventurous"                           / "Abenteuerlustig"
gen.exploration_notch_1        = "Familiar"                              / "Vertraut"
gen.exploration_notch_2        = "Mostly known"                          / "Meist bekannt"
gen.exploration_notch_3        = "Balanced"                              / "Ausgewogen"
gen.exploration_notch_4        = "Mostly new"                            / "Meist neu"
gen.exploration_notch_5        = "Adventurous"                           / "Abenteuerlustig"
gen.exploration_custom         = "Custom"                                / "Eigene Einstellung"
gen.exploration_hint_1         = "Familiar — bias toward artists you already know." / "Vertraut — Fokus auf Künstler, die du kennst."
gen.exploration_hint_2         = "Mostly known — a few new artists mixed in." / "Meist bekannt — ein paar neue Künstler dabei."
gen.exploration_hint_3         = "Balanced — roughly half new artists, moderate novelty." / "Ausgewogen — etwa zur Hälfte neue Künstler, moderate Vielfalt."
gen.exploration_hint_4         = "Mostly new — discovery-led, some familiar anchors." / "Meist neu — Entdeckungsmodus mit vertrauten Ankern."
gen.exploration_hint_5         = "Adventurous — emerging artists only, high novelty."    / "Abenteuerlustig — nur neu aufkommende Künstler, hohe Vielfalt."
gen.exploration_hint_custom    = "Custom mix — move the slider to jump back to a preset." / "Eigene Mischung — bewege den Regler, um zu einer Voreinstellung zurückzukehren."

# Audio filter inline hints
af.energy_hint                 = "How intense and active the track feels." / "Wie intensiv und aktiv der Track wirkt."
af.energy_learn_more           = "Higher values push GPT toward loud, fast, driving tracks. Lower values favour calm, ambient music. Leave empty to let any value through." / "Höhere Werte steuern GPT zu lauten, schnellen, treibenden Tracks. Niedrigere Werte bevorzugen ruhige, ambiente Musik. Leer lassen = beliebig."
af.valence_hint                = "Musical positiveness — happy vs sad."   / "Musikalische Stimmung — fröhlich vs. traurig."
af.valence_learn_more          = "Valence is Spotify's 0–100 measurement of emotional tone. High = cheerful, euphoric; low = sad, angry, dark." / "Valence ist Spotifys 0–100-Wert für emotionale Färbung. Hoch = fröhlich, euphorisch; niedrig = traurig, düster."
af.tempo_hint                  = "Speed in beats per minute (BPM)."      / "Geschwindigkeit in Schlägen pro Minute (BPM)."
af.tempo_learn_more            = "Typical ranges: slow ballads 60–80, mid-tempo pop 90–110, dance 120–140, fast rock/electronic 140–180." / "Typische Bereiche: Balladen 60–80, Mid-Tempo-Pop 90–110, Dance 120–140, schneller Rock/Elektronik 140–180."
af.danceability_hint           = "How suitable a track is for dancing."  / "Wie gut sich der Track zum Tanzen eignet."
af.danceability_learn_more     = "Based on tempo stability, rhythm regularity, and beat strength. Not the same as \"upbeat\" — a steady ambient groove can score high." / "Basiert auf Tempo-Stabilität, Rhythmus und Beat-Stärke. Nicht dasselbe wie \"gute Laune\" — ein ruhiger Groove kann hoch punkten."
af.acousticness_hint           = "Acoustic vs electronic."               / "Akustisch vs. elektronisch."
af.acousticness_learn_more     = "High = unplugged, live instruments, folk. Low = synths, heavy production, electronic." / "Hoch = unplugged, echte Instrumente, Folk. Niedrig = Synths, Elektronik, hohe Produktion."

# Settings modal
settings.playlist_size_label   = "Playlist Size"                         / "Playlist-Größe"
settings.playlist_size_hint    = "How many tracks to generate (max 30)." / "Wie viele Tracks generiert werden (max. 30)."
settings.playlist_size_learn_more = "Max capped at 30 — beyond that GPT starts repeating itself across 10-track fetch blocks, and review fatigue sets in. If you want a longer session, run twice with different presets." / "Maximal 30 — darüber hinaus wiederholt sich GPT zwischen 10er-Blöcken und die Bewertung wird anstrengend. Für längere Sessions: zweimal mit unterschiedlichen Presets laufen lassen."
settings.new_artist_pct_label  = "New Artist %"                          / "Neue Künstler %"
settings.new_artist_pct_hint   = "Minimum share of suggestions from artists you haven't listened to yet." / "Mindestanteil der Vorschläge von Künstlern, die du noch nicht gehört hast."
settings.new_artist_pct_learn_more = "Higher pushes exploration; lower keeps things familiar. The exploration slider above drives this — edit here to override." / "Höher = mehr Erkundung, niedriger = vertrauter. Der Erkundungs-Regler oben steuert diesen Wert — hier überschreiben."
settings.model_label           = "Used Model"                            / "Verwendetes Modell"
settings.model_hint            = "Which OpenAI model produces your suggestions." / "Welches OpenAI-Modell deine Vorschläge erzeugt."
settings.model_learn_more      = "Higher-tier models cost more per run. For music suggestions the difference is noticeable but not dramatic; gpt-4o-mini is a sensible default." / "Leistungsstärkere Modelle kosten mehr pro Lauf. Für Musikvorschläge ist der Unterschied hörbar, aber nicht dramatisch; gpt-4o-mini ist ein sinnvoller Standard."
settings.debug_hint            = "Log every GPT request and response to a local file." / "Protokolliert jede GPT-Anfrage und -Antwort in eine lokale Datei."
settings.debug_learn_more      = "For developers and bug reports. Never affects behaviour. The log file stays on your device — see the Privacy modal." / "Für Entwickler und Fehlerberichte. Beeinflusst das Verhalten nie. Die Logdatei bleibt auf deinem Gerät — siehe Datenschutz-Dialog."

# Profile completeness
profile.strength               = "Profile Strength"                      / "Profil-Stärke"
profile.core_description       = "Core Description"                      / "Kern-Beschreibung"
profile.must_have              = "Must Have"                             / "Pflicht"
profile.soft_preferences       = "Soft Preferences"                      / "Soft-Präferenzen"
profile.avoid                  = "Avoid"                                 / "Vermeiden"
profile.touched                = "Edited"                                / "Bearbeitet"
profile.suggest_core_empty     = "Add a few sentences describing your ideal sound — that's the foundation." / "Füge ein paar Sätze zu deinem Wunsch-Sound hinzu — das ist die Grundlage."
profile.suggest_must_empty     = "List 2–3 non-negotiable traits — things every suggestion must have." / "Nenne 2–3 Muss-Eigenschaften — was jeder Vorschlag haben muss."
profile.suggest_soft_empty     = "Add a soft preference for variety."    / "Füge eine Soft-Präferenz für mehr Abwechslung hinzu."
profile.suggest_avoid_empty    = "Add at least one thing to avoid — it sharpens the profile." / "Füge mindestens einen Vermeide-Punkt hinzu — das schärft das Profil."
profile.suggest_core_partial   = "Expand your core description — a sentence or two more helps GPT." / "Erweitere deine Kern-Beschreibung — ein oder zwei Sätze mehr helfen GPT."

# Presets
preset.label                   = "Preset"                                / "Voreinstellung"
preset.builtin_suffix          = "(built-in)"                            / "(mitgeliefert)"
preset.your_presets            = "Your presets"                          / "Deine Voreinstellungen"
preset.builtin_header          = "Built-in"                              / "Mitgeliefert"
preset.save_current            = "💾 Save current as preset…"            / "💾 Aktuelle Einstellungen speichern…"
preset.save_title              = "Save preset"                           / "Voreinstellung speichern"
preset.name_label              = "Name"                                  / "Name"
preset.name_placeholder        = "e.g. Workout mix"                      / "z. B. Workout-Mix"
preset.name_hint               = "Stored on your device only."           / "Nur auf deinem Gerät gespeichert."
preset.manager_title           = "Manage presets"                        / "Voreinstellungen verwalten"
preset.manager_subtitle        = "Drag to reorder your own presets. Built-in presets are fixed." / "Ziehe, um deine eigenen Voreinstellungen umzusortieren. Mitgelieferte sind fest."
preset.clone                   = "Clone"                                 / "Duplizieren"
preset.delete                  = "Delete"                                / "Löschen"
preset.rename                  = "Rename"                                / "Umbenennen"
preset.export                  = "Export"                                / "Exportieren"
preset.import                  = "⬆ Import preset…"                      / "⬆ Voreinstellung importieren…"
preset.import_failed           = "Import failed."                        / "Import fehlgeschlagen."
preset.custom_unsaved          = "Custom (unsaved)"                      / "Eigene (nicht gespeichert)"
preset.builtin_safe_picks      = "Safe picks"                            / "Sichere Wahl"
preset.builtin_balanced        = "Balanced"                              / "Ausgewogen"
preset.builtin_deep_discovery  = "Deep discovery"                        / "Tiefe Entdeckung"
preset.using                   = "Using preset: {name}"                  / "Voreinstellung: {name}"
preset.clone_copy_suffix       = "(copy)"                                / "(Kopie)"

# Gear menu
nav.manage_presets             = "Manage presets"                        / "Voreinstellungen verwalten"
```

---

## 12. Screenshot tests — updates to `test_documentation_screenshots.py`

Append after Wave 1's onboarding/privacy tests. Numbers continue from `55_rerun_setup_menu_item` (highest used after Wave 1). Use `56–68` for Wave 2.

```python
# -- Wave 2: Quick wins ------------------------------------------------

def test_56_generate_quick_mode(self, page: Page, screenshot_url):
    """Screenshot: Generate panel in Quick mode with exploration slider."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(400)
    page.evaluate("localStorage.setItem('sv.gen_mode', 'quick')")
    page.reload()
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(400)
    _shot_element(page, "56_generate_quick_mode", "#generateSection")

def test_57_generate_advanced_mode(self, page: Page, screenshot_url):
    """Screenshot: Generate panel in Advanced mode with all controls visible."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(300)
    _shot_element(page, "57_generate_advanced_mode", "#generateSection")

def test_58_exploration_slider_adventurous(self, page: Page, screenshot_url):
    """Screenshot: Exploration slider at notch 5 (Adventurous)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.evaluate("document.getElementById('explorationSlider').value = 5; document.getElementById('explorationSlider').dispatchEvent(new Event('input'));")
    page.wait_for_timeout(200)
    _shot_element(page, "58_exploration_slider_adventurous", ".exploration-row")

def test_59_exploration_slider_custom(self, page: Page, screenshot_url):
    """Screenshot: Slider in 'Custom' state after Advanced-mode override."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(200)
    # Slider is at 3 (Balanced → 50%); change new-artist % to 33 to force custom.
    page.locator("#settings-new-artist-pct, input[name='new-artist-pct']").first.fill("33")
    page.locator("body").click()  # blur
    page.wait_for_timeout(300)
    _shot_element(page, "59_exploration_slider_custom", ".exploration-row")

def test_60_preset_dropdown_open(self, page: Page, screenshot_url):
    """Screenshot: Preset dropdown expanded in Advanced mode with user + built-in sections."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        const userPresets = [
            { id: 'user_1', name: 'Morning coffee', builtin: false, version: 1, settings: {} },
            { id: 'user_2', name: 'Workout mix',    builtin: false, version: 1, settings: {} },
        ];
        localStorage.setItem('sv.presets.user', JSON.stringify(userPresets));
    }""")
    page.reload()
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(200)
    page.locator("#presetDropdownTrigger").click()
    page.wait_for_timeout(200)
    _shot_element(page, "60_preset_dropdown_open", ".preset-row")

def test_61_preset_dropdown_empty_user(self, page: Page, screenshot_url):
    """Screenshot: Preset dropdown when user has zero custom presets."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.removeItem('sv.presets.user')")
    page.reload()
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(200)
    page.locator("#presetDropdownTrigger").click()
    page.wait_for_timeout(200)
    _shot_element(page, "61_preset_dropdown_empty_user", ".preset-row")

def test_62_save_preset_dialog(self, page: Page, screenshot_url):
    """Screenshot: 'Save current as preset' dialog."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(200)
    page.locator(".preset-save-btn").click()
    page.wait_for_timeout(300)
    _shot_element(page, "62_save_preset_dialog", "#savePresetModal .modal")

def test_63_preset_manager(self, page: Page, screenshot_url):
    """Screenshot: Manage presets modal with user + built-in rows."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        const userPresets = [
            { id: 'user_1', name: 'Morning coffee', builtin: false, version: 1, settings: {} },
            { id: 'user_2', name: 'Workout mix',    builtin: false, version: 1, settings: {} },
        ];
        localStorage.setItem('sv.presets.user', JSON.stringify(userPresets));
    }""")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Manage presets')").click()
    page.wait_for_timeout(300)
    _shot_element(page, "63_preset_manager", "#presetManagerModal .modal")

def test_64_completeness_meter_weak(self, page: Page, screenshot_url):
    """Screenshot: Completeness meter at low score (red) on an empty profile."""
    # Override profile state to empty for this one test
    page.goto(screenshot_url + "?mock_empty_profile=1")  # optional: fixture support
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(400)
    page.evaluate("""() => {
        document.getElementById('trainCoreDesc').value = '';
        document.getElementById('trainMustHave').value = '';
        document.getElementById('trainSoftPrefs').value = '';
        document.getElementById('trainAvoid').value = '';
        ['trainCoreDesc','trainMustHave','trainSoftPrefs','trainAvoid'].forEach(id => {
            document.getElementById(id).dispatchEvent(new Event('input'));
        });
    }""")
    page.wait_for_timeout(400)
    _shot_element(page, "64_completeness_meter_weak", "#profileCompletenessCard")

def test_65_completeness_meter_medium(self, page: Page, screenshot_url):
    """Screenshot: Completeness meter at ~45% (yellow)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(400)
    page.evaluate("""() => {
        document.getElementById('trainCoreDesc').value = 'Upbeat melodic rock.';
        document.getElementById('trainMustHave').value = 'high energy';
        document.getElementById('trainSoftPrefs').value = '';
        document.getElementById('trainAvoid').value = '';
        ['trainCoreDesc','trainMustHave','trainSoftPrefs','trainAvoid'].forEach(id => {
            document.getElementById(id).dispatchEvent(new Event('input'));
        });
    }""")
    page.wait_for_timeout(400)
    _shot_element(page, "65_completeness_meter_medium", "#profileCompletenessCard")

def test_66_audio_filter_inline_hints(self, page: Page, screenshot_url):
    """Screenshot: Audio filter panel showing inline hints + Learn more expandable open on one filter."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.wait_for_timeout(200)
    page.locator(".audio-filter-toggle").click()
    page.wait_for_timeout(200)
    # Expand Learn more on Energy
    page.locator(".audio-filter-row:has-text('Energy') .learn-more > summary").click()
    page.wait_for_timeout(200)
    _shot_element(page, "66_audio_filter_inline_hints", "#audioFiltersSection")

def test_67_settings_modal_inline_hints(self, page: Page, screenshot_url):
    """Screenshot: Settings modal with new inline hints + Learn more expandables."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    _shot_element(page, "67_settings_modal_inline_hints", "#settingsModal .modal")

def test_68_gen_mode_tabs_isolated(self, page: Page, screenshot_url):
    """Screenshot: The Quick / Advanced tab row as its own element shot."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    _shot_element(page, "68_gen_mode_tabs", ".gen-mode-tabs")
```

---

## 13. Smoke tests — additions to `test_frontend.py`

```python
def test_quick_advanced_mode_persists(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    # Switch to Spotify tab + open Generate
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    assert page.evaluate("localStorage.getItem('sv.gen_mode')") == "advanced"
    page.reload()
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    assert page.locator(".gen-mode-btn[data-mode='advanced']").get_attribute("class").__contains__("active")

def test_exploration_slider_updates_underlying_fields(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    # Move slider to 1 (Familiar). Expect new_artist_pct to become 10.
    page.evaluate("""() => {
        const s = document.getElementById('explorationSlider');
        s.value = 1;
        s.dispatchEvent(new Event('input'));
    }""")
    pct = page.evaluate("document.querySelector('.gen-field-new-artist-pct input, #settings-new-artist-pct').value")
    assert int(pct) == 10
    emerging = page.evaluate("document.getElementById('emergingArtistsCheckbox').checked")
    assert emerging is False

def test_exploration_slider_custom_on_hand_edit(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    # Hand-edit new-artist-% to a value not matching any notch
    page.evaluate("""() => {
        const el = document.querySelector('.gen-field-new-artist-pct input, #settings-new-artist-pct');
        el.value = 33;
        el.dispatchEvent(new Event('input'));
        el.dispatchEvent(new Event('change'));
    }""")
    label = page.locator("#explorationValueLabel").text_content()
    assert "Custom" in label or "Eigene" in label

def test_preset_save_and_reload(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.removeItem('sv.presets.user')")
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.locator(".preset-save-btn").click()
    page.locator("#savePresetInput").fill("Test preset")
    page.locator("#savePresetModal .btn-save").click()
    # Reload, expect the preset to still be present
    page.reload()
    page.wait_for_load_state("networkidle")
    stored = page.evaluate("JSON.parse(localStorage.getItem('sv.presets.user') || '[]')")
    assert any(p["name"] == "Test preset" for p in stored)

def test_completeness_hides_at_high_score(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    # Fill fields strongly
    page.locator("#trainCoreDesc").fill("Upbeat melodic rock with strong hooks, theatrical vocals, and constant momentum — think Queen meets Bear Ghost.")
    page.locator("#trainMustHave").fill("high energy\nstrong memorable melodies\nvocals")
    page.locator("#trainSoftPrefs").fill("prog influence")
    page.locator("#trainAvoid").fill("electronic/synth-heavy")
    # Trigger input events
    for sel in ["#trainCoreDesc", "#trainMustHave", "#trainSoftPrefs", "#trainAvoid"]:
        page.evaluate(f"document.querySelector('{sel}').dispatchEvent(new Event('input'))")
    page.wait_for_timeout(400)
    assert page.locator("#profileCompletenessCard").is_hidden()

def test_tooltip_removed_from_audio_filters(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    page.locator(".audio-filter-toggle").click()
    # The hover tooltip attribute should be gone
    energy_label = page.locator(".audio-filter-row:has-text('Energy') label")
    assert energy_label.get_attribute("data-tooltip") is None
    # An inline hint line should exist
    assert page.locator(".audio-filter-row:has-text('Energy') .inline-hint").is_visible()
```

---

## 14. Acceptance checklist

- [ ] No `data-tooltip` attributes remain on primary controls in `generate_section.html`, `settings_modal.html`. Grep: `grep -rn 'data-tooltip' frontend/templates/ | grep -v track- | grep -v refresh | grep -v playlist-refresh | grep -v playlist-delete` should be empty.
- [ ] Every control listed in § 4.1 has an `.inline-hint` with a translated short description.
- [ ] Every control in § 4.1 has a `<details class="learn-more">` with longer body (except emerging-artists checkbox, which is already concise — confirm with the inline-hint copy table in § 4.3).
- [ ] `(optional)` badge rendered on: audio-filters section header, emerging-artists checkbox, Debug Mode.
- [ ] Profile completeness meter appears when score < 60, hides ≥ 60, updates on every keystroke (debounced 250 ms).
- [ ] Completeness meter reflects all five dimensions with correct weights (sum = 100).
- [ ] Suggestion line follows the priority in § 5.5 and is empty when score ≥ 60.
- [ ] Generate panel shows Quick/Advanced tab toggle when expanded.
- [ ] Quick mode shows only: size slider, exploration slider, Generate button. Nothing else.
- [ ] Advanced mode shows all previous Generate-panel controls **plus** preset dropdown, exploration slider, and the new-artist-% slider (moved here from Settings modal for visibility — the Settings modal field also still exists).
- [ ] Mode persists across reloads via `localStorage`.
- [ ] Size slider min = 10, max = 30, step = 5. Value displays next to the slider (e.g. "25 tracks"). This is the **hard cap** agreed in design.md D.1.
- [ ] Exploration slider has exactly 5 notches. Moving it updates: new-artist-% input, emerging-artists checkbox, and the in-memory `temperature` value.
- [ ] Hand-editing new-artist-% or emerging-artists to a value that doesn't match any notch switches the slider to "Custom" state (dashed thumb, "Custom" label).
- [ ] Moving the slider out of "Custom" state re-applies the notch mapping to the underlying fields.
- [ ] Preset dropdown opens in Advanced mode. User presets on top with `[⋯]` menu; built-in below a divider with `[clone]` affordance.
- [ ] Zero-user-presets state: "Your presets" section hidden; dropdown opens to Built-in directly.
- [ ] Clicking `[clone]` on a built-in creates a user preset with name suffix `(copy)` and immediately selects it.
- [ ] Built-in presets cannot be renamed, deleted, reordered, or overwritten. Preset manager does not surface those actions for built-ins.
- [ ] "Save current as preset" dialog creates a preset and persists to `localStorage`.
- [ ] Preset Import accepts valid JSON and rejects malformed input with a toast (`preset.import_failed`).
- [ ] Preset Export emits a JSON file whose shape matches § 3.3.
- [ ] Active preset label appears above the Generate button: `Using preset: Morning coffee`. Hand-editing switches to `Custom (unsaved)`.
- [ ] Backend accepts `temperature` in the generation payload and forwards it to OpenAI.
- [ ] Settings modal size control clamps to `[10, 30]` on blur (matches the Generate-panel cap).
- [ ] All 13 new screenshot tests (§ 12) pass under `-m screenshots`.
- [ ] All 6 new smoke tests (§ 13) pass under the regular pytest run.
- [ ] No existing test regresses — run the full `python -m pytest core/tests/ frontend/tests/ -v`.
- [ ] i18n coverage: no hardcoded English in new templates, JS modules, or Python responses. Grep for known strings ("Playlist size", "Learn more", "Preset") in new code outside `en.json`.
- [ ] Responsive: at 390×844 (iPhone 13), tab row remains inline; preset dropdown is full-width; slider thumb is ≥ 44 px touch target (scale via transform on `::-webkit-slider-thumb`).

---

## 15. Review checklist before merging

- [ ] `version.py` bumped.
- [ ] `documentation/UserManual.md` updated: short paragraph on Quick vs Advanced + presets + completeness meter.
- [ ] `documentation/TechnicalManual.md` updated: note the `temperature` field in generation payloads.
- [ ] `documentation/help.md` updated: sections for presets and exploration slider. Reuse learn-more copy from § 4.3 where it fits.
- [ ] No Wave-3/4/5 surfaces started — no playlist-seed plumbing, no chip-based explanations, no visualisation stubs, no custom-endpoint fields.
- [ ] New entries added to the project-tree section of `CLAUDE.md`.
- [ ] All new/changed text exists in both `en.json` and `de.json`.

---

## 16. Reference — surfaces you will touch in Wave 2

| File | Action |
|------|--------|
| `app.py` | Modify — accept `temperature` on the generation route |
| `core/src/openai_http.py` | Modify — forward `temperature` |
| `frontend/templates/generate_section.html` | Rewrite body — add tabs, two mode bodies, slider, preset row, inline hints |
| `frontend/templates/train_profile.html` | Modify — completeness card mount |
| `frontend/templates/modals/settings_modal.html` | Modify — inline hints, `(optional)` badge, max=30 clamp |
| `frontend/templates/modals/preset_manager_modal.html` | Create |
| `frontend/templates/base.html` | Modify — include preset manager modal |
| `frontend/templates/settings_gear.html` | Modify — add "Manage presets" menu item |
| `frontend/static/css/base.css` | Modify — new tokens |
| `frontend/static/css/forms.css` | Modify — `.inline-hint`, `.learn-more`, `.optional-badge` |
| `frontend/static/css/sections.css` | Modify — `.gen-mode-tabs`, `.gen-mode-body` |
| `frontend/static/css/completeness.css` | Create |
| `frontend/static/css/exploration_slider.css` | Create |
| `frontend/static/css/presets.css` | Create |
| `frontend/static/js/modules/completeness.js` | Create |
| `frontend/static/js/modules/exploration.js` | Create |
| `frontend/static/js/modules/presets.js` | Create |
| `frontend/static/js/modules/quick_advanced.js` | Create |
| `frontend/static/js/modules/pipeline.js` (or the current runPipeline owner) | Modify — include `temperature` in payload |
| `frontend/static/js/modules/audio-filters.js` | Modify — remove hover tooltip conversion |
| `frontend/static/js/main.js` | Modify — bootstrap new modules |
| `frontend/static/i18n/en.json` | Modify — add § 11 keys |
| `frontend/static/i18n/de.json` | Modify — add § 11 keys |
| `frontend/tests/test_documentation_screenshots.py` | Modify — add tests 56–68 |
| `frontend/tests/test_frontend.py` | Modify — add 6 smoke tests |

---

## 17. Opening contract for the implementer

You have full autonomy within Wave 2 scope. Do **not** implement anything outside it. When you believe Wave 2 is done, stop and say "Wave 2 complete — please review". Do not commit, do not push, do not start on Wave 3 — the user opens the next implementation file when ready.
