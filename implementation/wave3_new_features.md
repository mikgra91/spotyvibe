# Wave 3 — New features: playlist-seeded profiles, explainable chips, taste visualisation, feature-discovery tips

> **Reader.** This document is written for Claude Sonnet 4.6 to implement. It assumes no memory of prior conversations. It is self-contained.
>
> **Prerequisites.** Waves 1 and 2 (`wave1_foundation.md`, `wave2_quick_wins.md`) must be merged first. Wave 3 enables the "Coming soon" card wired up in Wave 1 (onboarding step 5, card 1) and piggybacks on the preset dropdown shape from Wave 2 for the new tip styling.
>
> **Source of truth for *why*.** [`../design.md`](../design.md) § C.1, § D.3, § F.1, § B.1.
>
> **Working directory.** `c:\git\spotyvibe`. All paths below are relative to the repo root.
>
> **Conventions.** Vanilla ES modules, no bundler. Jinja2 templates. Modular CSS. i18n via `data-i18n` + `i18n(key, fallback)`. All user-facing text lives in `frontend/static/i18n/en.json` and `de.json`. See [`../CLAUDE.md`](../CLAUDE.md). Spotify API: per rule 2 in CLAUDE.md, use `sp.playlist_items()` not `playlist_tracks()`, search `limit` max 10, response inner key is `"item"` not `"track"`.
>
> **What this wave is.** Four substantive features that add real capability (not just polish). Together they change how users build and understand their profile, why they accept suggestions, and how they discover the rest of the app.
>
> **What this wave is NOT.** No custom LLM endpoint (Wave 4, E.1). No cost estimator (Wave 4, E.2). No voice input (Wave 4, C.2). No help i18n (Wave 5). If you're about to add a base-URL field, a token counter, or a microphone button — stop.

---

## 1. Scope map

| Ref | Name | Summary |
|-----|------|---------|
| C.1 | Seed profile from Spotify playlist | Enable Wave-1's "Coming soon" card on onboarding step 5. Add a "Seed from playlist" button on the profile editor. Flow: pick a playlist → backend fetches tracks + artist genres + audio features → GPT drafts a profile → user lands in the profile editor with fields pre-filled and a "Generated from: {playlist}" banner → user edits and saves via the existing flow. **Single-playlist only**; multi-playlist blending is deferred. |
| D.3 | Explainable recommendations (structured chips) | Replace free-form `track.reason` prose with 1–2 bounded rationale chips per suggestion, chosen from a fixed vocabulary (`profile_match`, `artist_match`, `recency`, `novelty`, `audio_match`). Chips appear directly under the track title. GPT returns them as structured JSON. Run history serialises and re-renders them. |
| F.1 | Taste visualisation dashboard | A collapsible 3-panel dashboard on the profile page showing: top-genre donut, energy × valence scatter, release-decade bar chart. Data aggregated server-side from run history + Spotify metadata. Renders only when ≥ 10 tracks are available; shows a friendly empty state otherwise. Custom SVG, no chart library. |
| B.1 | In-context feature discovery toasts | Event-triggered, non-modal tips appearing via the existing toast surface, at most one per session, seen-state tracked in `localStorage`. Fixed catalogue of 5 tips. Burger-menu item "Reset tips" re-enables them for users who want a tour. |

---

## 2. Files to create, modify, delete

### Create

| Path | Purpose |
|------|---------|
| `frontend/templates/modals/playlist_seed_modal.html` | Picker: user's Spotify playlists + multi-step flow (pick → confirm → draft in editor). |
| `frontend/templates/taste_dashboard.html` | Dashboard partial, included from the OpenAI provider section. |
| `frontend/static/css/playlist_seed.css` | Picker modal + draft banner styling. |
| `frontend/static/css/rationale_chips.css` | Chip styling for track rows. |
| `frontend/static/css/taste_dashboard.css` | Dashboard grid + chart styles. |
| `frontend/static/css/tips.css` | Toast variant styling for tips (builds on existing toast.html). |
| `frontend/static/js/modules/playlist_seed.js` | Client flow: fetch user playlists, POST seed request, apply draft to editor, banner state. |
| `frontend/static/js/modules/rationale.js` | Chip rendering + fallback + i18n composition. |
| `frontend/static/js/modules/taste_dashboard.js` | Fetch `/api/taste/aggregate`, render SVGs, collapse/expand. |
| `frontend/static/js/modules/tips.js` | Trigger registry, `maybeTrigger(id, ctx)`, seen-state, queue. |
| `documentation/prompts/rationale_chips_examples.md` | Few-shot examples shipped alongside the prompt (referenced by `prompts/*.txt` additions). |
| `implementation/wave3_new_features.md` | **This file.** |

### Modify

| Path | What changes |
|------|--------------|
| `frontend/templates/onboarding.html` | Enable step-5 card 1 (remove `--disabled`, remove "Coming soon" badge, wire click to `openPlaylistSeedPicker('onboarding')`). Add banner display after draft applied. |
| `frontend/templates/train_profile.html` | Add "🎵 Seed from playlist" button in the profile menu (`⋯` dropdown). Add the draft banner element above `.accordion-panel#accVibeDesc`. Include the taste-dashboard partial below the profile editor body. |
| `frontend/templates/base.html` | Include `playlist_seed_modal.html`. |
| `frontend/templates/generate_section.html` | Remove the inline `{% if track.reason %}<div class="track-reason">…</div>{% endif %}` server-side render. Chips render client-side from the track's `rationale` field (see § 5). Keep the Jinja `track.reason` plumbing as a **fallback** for legacy run-history entries that pre-date Wave 3 — rendered as a single chip. |
| `frontend/templates/run_history.html` | Same — re-render chips for historical tracks using the stored `rationale` array (or `reason` fallback). |
| `frontend/templates/settings_gear.html` | Add "Reset tips" menu item below "Manage presets". |
| `frontend/static/js/modules/tracklist.js` | Replace `.track-reason` `<div>` rendering with a chip row. Delegate to `rationale.js`. |
| `frontend/static/js/modules/pipeline.js` (or the current runPipeline owner) | After a successful generation, call `Tips.maybeTrigger('first_generation_complete')` and `Tips.maybeTrigger('five_generations', { count })`. |
| `frontend/static/js/modules/feedback.js` | After each dislike, increment an in-memory per-run counter; if ≥ 2, call `Tips.maybeTrigger('disliked_2_plus')`. |
| `frontend/static/js/modules/history.js` | On first view of the history tab (per session), call `Tips.maybeTrigger('first_history_view')`. |
| `frontend/static/js/modules/audio-filters.js` | On first expand of the audio-filter subpanel, call `Tips.maybeTrigger('first_filter_open')`. |
| `frontend/static/js/modules/profile.js` | Add "Seed from playlist" entry point; hook the draft banner; apply the draft to fields. |
| `frontend/static/js/main.js` | Bootstrap `tips.js`, `taste_dashboard.js`, `playlist_seed.js`, `rationale.js`. |
| `core/src/playlist.py` | Add `fetch_user_playlists()` (list of `{id, name, owner, track_count, cover_url}`), `fetch_playlist_items_for_seed(id)` (returns tracks with artist ids and basic metadata). **All Spotify API calls must remain inside this module** (rule per CLAUDE.md). |
| `core/src/spotify_metadata.py` | Add `fetch_audio_features_batch(track_ids)` (bounded to 100 per Spotify batch size) and `fetch_artists_genres(artist_ids)`. Reuse existing helpers if present. |
| `core/src/profile.py` | Add `draft_profile_from_playlist(playlist_payload)` — calls GPT to synthesise `core_description`, `must_have`, `soft_preferences`, `avoid` (always empty). Returns a profile dict matching the existing shape. |
| `core/src/suggestions.py` | Update response parser to accept `rationale: [{type, arg?}, ...]` arrays. If the model returns a legacy `reason` string, keep it as a `legacy` chip type. |
| `core/src/history.py` | Persist `rationale` with each track entry. Bump a `schema_version` on stored runs to `2` so old runs keep their `reason` string intact while new runs store `rationale`. Migration: on read, normalise old runs by moving `reason` → `rationale: [{type: 'legacy', arg: reason}]` on the fly, without rewriting the file. |
| `prompts/suggestions.txt` (or whichever prompt produces track suggestions) | Add a `rationale` block spec. Include 2 few-shot examples. |
| `prompts/profile_seed_from_playlist.txt` | **Create** — new prompt for drafting a profile from playlist data. |
| `app.py` | Add endpoints: `GET /api/spotify/playlists_for_seed`, `POST /api/profile/seed_from_playlist`, `GET /api/taste/aggregate`. |
| `frontend/static/i18n/en.json` | Add every key listed in § 12. |
| `frontend/static/i18n/de.json` | Same keys with German strings. |
| `frontend/tests/test_documentation_screenshots.py` | New captures: playlist picker, draft banner, chip variants, dashboard, tip toast, reset-tips menu. § 13. |
| `frontend/tests/test_frontend.py` | New smoke tests. § 14. |
| `core/tests/test_profile.py` and `core/tests/test_suggestions.py` | Add unit tests for `draft_profile_from_playlist` and rationale parsing. |

### Delete

Nothing. Every Wave-1/Wave-2 surface stays.

---

## 3. Shared patterns (read first)

### 3.1 The rationale chip — reusable component

The chip from § 5 is used under each track row. It is **not** re-used elsewhere in Wave 3. Keep the styles in `rationale_chips.css` scoped to `.rationale-chip`.

### 3.2 Toast variant for tips

The existing `frontend/templates/toast.html` handles reactive success/error messages. Tips re-use the same DOM element with a `--tip` class modifier, an icon, and a text-link affordance. Do not build a parallel toast stack.

### 3.3 Draft banner (used by C.1)

A horizontal banner rendered *above* the profile editor accordion stack when a draft is pending confirmation. Reuse the `.ob-info-chip` visual style from Wave 1 but with an additional "Discard draft" action on the right.

### 3.4 Dashboard chart grid (used by F.1 only)

3-column grid on ≥ 960 px, stacked on smaller viewports. Each chart is its own self-contained SVG — no shared axis or data bus.

### 3.5 Tip registry

`tips.js` owns a single catalogue object keyed by event id. Triggering an unknown id is a silent no-op. Each registered tip defines:

```js
{
  id: 'first_generation_complete',
  label_i18n: 'tip.first_generation',
  body_i18n: 'tip.first_generation_body',
  link_i18n: 'tip.first_generation_link',
  linkAction: () => { /* navigate or open a section */ },
  once: true,                  // seen once ever; false for re-entrant tips (none in Wave 3)
}
```

---

## 4. C.1 — Seed profile from a Spotify playlist

### 4.1 Flow (end-to-end)

1. User opens the picker:
   - From **onboarding step 5 card 1** (click on card or its button).
   - From **profile editor `⋯` menu** → "Seed from playlist".
2. Modal appears: `GET /api/spotify/playlists_for_seed` populates a scrollable list.
3. User picks exactly one playlist. A "Use this playlist" primary button enables.
4. If an existing (non-empty) profile is active: show an inline confirmation *inside the modal* — "This will replace your current profile's fields. The original is not deleted automatically — export it first if you want to keep it." Two buttons: "Continue" (primary) / "Cancel".
5. On "Use this playlist" (or "Continue" after the confirmation), show a full-width loader inside the modal with the copy "Drafting your profile… this may take up to 30 seconds." Disable the list.
6. Client calls `POST /api/profile/seed_from_playlist` `{ playlist_id }`. Backend:
   - Fetches tracks via `sp.playlist_items()` (rule: `playlist_items`, inner key `item` not `track`).
   - Extracts artist ids, fetches artist genres + audio features.
   - Sends an LLM prompt (new prompt `prompts/profile_seed_from_playlist.txt`) with an anonymised summary of the playlist: top genres, top 5 artists, energy/valence/tempo medians, common moods inferred from audio features.
   - Returns a profile dict with: `core_description` (GPT prose), `must_have` (top 3 artists as "similar to X" entries), `soft_preferences` (top 3 genres), `avoid: []`, and a `_draft` metadata block with `{ playlist_id, playlist_name, track_count, drafted_at }`.
7. Client closes the modal, opens the profile editor (expands `#trainToggleBtn` if collapsed), populates fields with the draft values, and shows the **draft banner** (§ 4.4).
8. User reviews / edits. Clicking "AI Profile Update" or "Save without AI" commits via the existing save flow. A small hidden field carries the `_draft` metadata through so the profile gets a `seeded_from` record — useful for later analytics but never shown in the UI.
9. Clicking "Discard draft" in the banner reloads the pristine profile (existing `/api/profile` GET) and hides the banner.

### 4.2 Playlist picker modal (DOM)

File: `frontend/templates/modals/playlist_seed_modal.html`. Included from `base.html`.

```
#playlistSeedModal.modal-overlay
└── .modal.playlist-seed-modal (max-width: 540px; min-height: 480px;)
    ├── header
    │   ├── h2 🎵 "Seed from a Spotify playlist"
    │   └── button.modal-close (top-right)
    │
    ├── p.playlist-seed-subtitle
    │
    ├── .playlist-search-row
    │   └── input#playlistSeedSearch (type=search, placeholder)
    │
    ├── ul.playlist-seed-list (scrollable, max-height: 360px)
    │   └── li.playlist-seed-item * N
    │       ├── img.playlist-seed-cover (48×48)
    │       ├── .playlist-seed-text
    │       │   ├── .playlist-seed-name
    │       │   └── .playlist-seed-meta (track count + owner)
    │       └── .playlist-seed-check (radio-visual ○ / ●)
    │
    ├── .playlist-seed-replace-warn.hidden
    │   └── (inline warning before Continue, see § 4.1 step 4)
    │
    ├── .playlist-seed-loader.hidden
    │   ├── .spinner.spinner--lg
    │   └── p "Drafting your profile…"
    │
    └── .modal-actions
        ├── button.btn.btn-cancel
        └── button.btn.btn-save#playlistSeedConfirmBtn (disabled until selection)
```

### 4.3 Styling specs

- `.playlist-seed-item` — `display: flex; gap: 12px; align-items: center; padding: 10px 12px; border-radius: var(--radius-sm); cursor: pointer; transition: background 120ms;` Hover: `background: var(--bg-elevated);` Selected: `background: rgba(30,215,96,0.08); outline: 1px solid rgba(30,215,96,0.35);`
- `.playlist-seed-cover` — `width: 48px; height: 48px; border-radius: var(--radius-sm); object-fit: cover; flex-shrink: 0;`
- `.playlist-seed-name` — `font-size: 0.92rem; font-weight: 600; color: var(--text-primary);`
- `.playlist-seed-meta` — `font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;`
- `.playlist-seed-check` — `width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--border); flex-shrink: 0;` Selected: `border-color: var(--primary); background: radial-gradient(circle, var(--primary) 40%, transparent 42%);`
- `.playlist-seed-list` — `list-style: none; padding: 0; margin: 12px 0 0; max-height: 360px; overflow-y: auto;`
- `.playlist-seed-replace-warn` — same visual as `.ob-info-chip` from Wave 1 but with amber tint: `background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.25); margin: 12px 0;`
- `.playlist-seed-loader` — `display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 40px 20px;`

### 4.4 Draft banner (profile editor)

Insert between `#accProfiles` and `#profileCompletenessCard` (the Wave-2 meter) or right above `#accVibeDesc` if completeness card is absent:

```html
<div id="profileDraftBanner" class="profile-draft-banner hidden" role="status">
  <span class="profile-draft-icon" aria-hidden="true">✨</span>
  <div class="profile-draft-text">
    <div class="profile-draft-title" data-i18n="profile.draft_title">Drafted from your playlist</div>
    <div class="profile-draft-sub" id="profileDraftSub"><!-- e.g. "Generated from 'Road Trip Mix' — review and save below." --></div>
  </div>
  <button class="profile-draft-discard" onclick="discardProfileDraft()" data-i18n="profile.draft_discard">Discard draft</button>
</div>
```

Styling (same elevated info-chip pattern):

- `background: rgba(30,215,96,0.05); border: 1px solid rgba(30,215,96,0.2); border-radius: var(--radius-md); padding: 12px 14px; display: flex; gap: 12px; align-items: center; margin: 12px 0;`
- `.profile-draft-title` — `font-size: 0.92rem; font-weight: 600; color: var(--text-primary);`
- `.profile-draft-sub` — `font-size: 0.82rem; color: var(--text-secondary); margin-top: 2px;`
- `.profile-draft-discard` — text-link style, `color: var(--primary); background: none; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 600; flex-shrink: 0;`

Banner shows until the user either saves (any save action) or discards. On successful save, hide the banner and also hide via success toast "Profile updated from playlist".

### 4.5 Onboarding card 1 wiring

In `onboarding.html` step 5, remove the `--disabled` modifier and "Coming soon" badge from card 1. Wire:

```html
<button class="ob-seed-action" onclick="openPlaylistSeedPicker('onboarding')">Choose playlist →</button>
```

**Condition:** card is only enabled if Spotify is connected (step 4 completed). If not, show a helper subtitle "Connect Spotify on step 4 to enable this" and keep it visually muted (`opacity: 0.55`). `playlist_seed.js` watches the Spotify auth status to update the card's enabled state in real time when the user returns to step 5.

After the onboarding user confirms a draft, advance the wizard directly to step 6 (Pick a model) **and** show a subtle toast "Profile drafted — edit it later from the app." The draft itself is applied once the user lands on the main app; the onboarding does not render the full profile editor inline. Implementation: stash the draft in `sessionStorage` under key `sv.draft_profile` and retrieve it in `main.js` bootstrap on the next navigation; if present, open the profile editor and show the banner.

### 4.6 Endpoints

**`GET /api/spotify/playlists_for_seed`**

Response:

```json
{
  "playlists": [
    { "id": "37i9dQZF1DXcBWIGoYBM5M", "name": "Road Trip Mix", "owner": "Jane", "track_count": 25, "cover_url": "https://i.scdn.co/image/..." },
    ...
  ]
}
```

- Returns up to 50 playlists. Honour pagination only if needed — Wave 3 caps at the first page.
- Requires Spotify auth. 401 if not authenticated with a stable error shape the client already handles for other Spotify endpoints.

**`POST /api/profile/seed_from_playlist`**

Request body: `{ "playlist_id": "..." }`

Response:

```json
{
  "draft": {
    "core_description": "...",
    "must_have": ["similar to Foo Fighters", "driving guitar", "memorable hooks"],
    "soft_preferences": ["indie rock", "alt rock", "post-rock"],
    "avoid": [],
    "vibe_description": ""
  },
  "meta": {
    "playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
    "playlist_name": "Road Trip Mix",
    "track_count": 25,
    "top_genres": ["indie rock", "alt rock", "post-rock"],
    "top_artists": ["Foo Fighters", "Arctic Monkeys", "Muse"],
    "drafted_at": "2026-04-18T12:30:00Z"
  }
}
```

- Backend budgets tokens: send a summary of the playlist (top 15 tracks + median audio features + top artists + top genres), not the full 100+ track list. This keeps the prompt well under budget.
- On GPT error: return HTTP 502 with `{ error: "draft_failed", detail: ... }`. Client shows the existing error-toast pattern.
- Timeout: 30 seconds hard cap on the GPT call.

**`GET /api/profile/draft_restore`** (**optional, only if needed** — the `sessionStorage` hand-off covers onboarding → main app)

Skip unless sessionStorage turns out to be unreliable across the Spotify auth redirect.

---

## 5. D.3 — Explainable recommendations (structured chips)

### 5.1 Chip vocabulary (fixed)

| Chip type | Typical trigger | Label template (i18n) | Examples |
|-----------|-----------------|-----------------------|----------|
| `profile_match` | Track aligns with a profile tag, core description word, or must-have | `explain.profile_match` → "matches '{arg}'" | matches 'indie rock', matches 'theatrical vocals' |
| `artist_match` | Track's artist relates to a liked artist or one in history | `explain.artist_match` → "similar to {arg}" | similar to Muse, same label as Foo Fighters |
| `recency` | Release in last 12 months, or matches emerging-artist filter | `explain.recency` → "{arg}" | released 2026, emerging artist |
| `novelty` | Intentional discovery pick, not a safe bet | `explain.novelty` → "{arg}" | discovery pick, new artist |
| `audio_match` | Track falls within an active audio filter range | `explain.audio_match` → "matches {arg}" | matches energy 70–90%, matches tempo 120 BPM |
| `legacy` | Fallback for pre-Wave-3 history entries | `explain.legacy` → "{arg}" | (passes through the original reason text) |
| `fallback` | No rationale returned; shown as a muted chip | `explain.fallback` → "profile match" | (no arg) |

`arg` is ≤ 40 characters after client-side truncation. GPT is instructed to respect this cap; the client enforces it defensively.

### 5.2 Response schema per track

```json
{
  "artist": "Muse",
  "title": "Hysteria",
  "rationale": [
    { "type": "profile_match", "arg": "theatrical rock" },
    { "type": "artist_match",  "arg": "Queen" }
  ]
}
```

- Exactly 1 or 2 entries.
- `type` must be one of the known set; unknown types are dropped client-side.
- `arg` is optional only for `novelty` (the type alone is self-explanatory) — every other type must have `arg`.

### 5.3 Prompt changes

Append to the suggestions prompt (existing file under `prompts/`):

```
After each track, include a "rationale" array with 1–2 entries justifying the
pick. Each entry has:
  - type: one of ["profile_match", "artist_match", "recency", "novelty", "audio_match"]
  - arg:  a short string (≤ 40 characters), required except for "novelty"

Use this exact shape:
  "rationale": [
    { "type": "profile_match", "arg": "indie rock" },
    { "type": "artist_match",  "arg": "Foo Fighters" }
  ]

Do not write full sentences. Do not repeat the profile. Do not use any type
other than the ones listed. If you cannot justify a pick with these types,
omit the track entirely.

Examples: (see prompts/rationale_chips_examples.md for 2 worked examples)
```

Also commit `documentation/prompts/rationale_chips_examples.md` containing:

```
# Rationale chip — few-shot examples

## Example 1
Track: "Hysteria" — Muse
User profile core: theatrical rock, strong bass, high energy
User history: many Queen tracks, 3 Foo Fighters tracks

Output:
{
  "artist": "Muse",
  "title": "Hysteria",
  "rationale": [
    { "type": "profile_match", "arg": "theatrical rock" },
    { "type": "artist_match",  "arg": "Queen" }
  ]
}

## Example 2
Track: "Running Up That Hill" — Kate Bush (2022 remaster)
User profile: melodic, cinematic, haunting vocals
Filters active: energy 60-90%

Output:
{
  "artist": "Kate Bush",
  "title": "Running Up That Hill",
  "rationale": [
    { "type": "profile_match", "arg": "haunting vocals" },
    { "type": "audio_match",   "arg": "energy 60-90%" }
  ]
}
```

### 5.4 Parser (`core/src/suggestions.py`)

- When parsing GPT output per track:
  - Read `rationale` if present.
  - Drop entries whose `type` isn't in the allowed list.
  - Truncate `arg` to 40 characters.
  - Cap array length to 2.
  - If the resulting array is empty AND a `reason` string is present (old-style fallback), convert to `[{type: "legacy", arg: reason}]`.
  - If both are missing, assign `[{type: "fallback"}]`. The client renders this as a muted chip.

### 5.5 UI rendering (`rationale.js`)

The module exports `renderRationale(container, rationale, options)` where:
- `container` is the `<div>` immediately below the track title (replace the old `.track-reason`).
- `rationale` is the array returned above.
- `options = { max: 2, mutedFallback: true }`.

Each chip:

```html
<span class="rationale-chip rationale-chip--{type}">
  <span class="rationale-chip-dot" aria-hidden="true"></span>
  <span class="rationale-chip-label">matches 'theatrical rock'</span>
</span>
```

The label is composed via i18n:

```js
const template = i18n('explain.' + type, defaultTemplateByType[type]);
const label = template.replace('{arg}', truncate(arg || '', 40));
```

### 5.6 Styling

- `.rationale-chip` — `display: inline-flex; align-items: center; gap: 6px; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-pill); padding: 3px 10px; font-size: 0.72rem; color: var(--text-secondary); margin-right: 6px;`
- Chip dot — `width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;`
- Chip colour mapping via per-type classes:

| Class | Dot colour |
|-------|------------|
| `.rationale-chip--profile_match` | `var(--primary)` |
| `.rationale-chip--artist_match` | `var(--accent-teal)` |
| `.rationale-chip--recency` | `var(--accent-cyan)` |
| `.rationale-chip--novelty` | `var(--accent-purple)` |
| `.rationale-chip--audio_match` | `var(--accent-pink)` |
| `.rationale-chip--legacy` | `var(--text-muted)` |
| `.rationale-chip--fallback` | `var(--border)` (no glow, extra-muted label) |

Fallback chip label colour: `color: var(--text-muted); font-style: italic;`

### 5.7 Track-card markup change

Before (in `generate_section.html` within the track loop):

```html
{% if track.reason %}<div class="track-reason">{{ track.reason|e }}</div>{% endif %}
```

After:

```html
<div class="track-rationale" data-track-rationale="{{ track.rationale|tojson|forceescape if track.rationale else '' }}"></div>
```

`rationale.js` finds every `.track-rationale[data-track-rationale]` on render and fills it. For server-side already-rendered tracks (run-history view), this runs once on page load.

### 5.8 Run history persistence

`core/src/history.py` — on write, serialise each track with:

```json
{
  "artist": "...",
  "title":  "...",
  "rationale": [ { "type": "...", "arg": "..." }, ... ]
}
```

On read, if `schema_version < 2` or `rationale` is missing:

```python
if 'rationale' not in track and track.get('reason'):
    track['rationale'] = [{'type': 'legacy', 'arg': track['reason']}]
```

Do **not** rewrite the stored file — the transform is read-only. When a new run is written, write with `schema_version: 2` and no `reason` field.

---

## 6. F.1 — Taste visualisation dashboard

### 6.1 Mount

New partial `frontend/templates/taste_dashboard.html`, included in `base.html` **inside** the OpenAI provider section, below `{% include "train_profile.html" %}` and above `{% include "band_analysis.html" %}`. Wrap it in an accordion-style collapsible card matching the existing `.accordion-panel` pattern so the user can hide it.

```
.taste-dashboard-section.accordion-panel
├── .accordion-header (role=button, toggles)
│   ├── h3 📊 "Your taste at a glance"
│   └── .accordion-chevron
│
└── .accordion-body
    └── .accordion-body-inner
        ├── p.acc-hint "Aggregated from your recent playlists and history."
        ├── .dashboard-grid (grid-template-columns: repeat(3, 1fr) on ≥960px)
        │   ├── .dashboard-card.dashboard-card--genres
        │   ├── .dashboard-card.dashboard-card--scatter
        │   └── .dashboard-card.dashboard-card--decades
        │
        └── .dashboard-empty.hidden
            └── (empty-state for < 10 tracks)
```

### 6.2 Data pipeline

`taste_dashboard.js`:

1. On accordion expansion (or initial page load if the accordion is remembered open), `fetch('/api/taste/aggregate')`.
2. If `tracks_considered < 10`, show the empty state, hide the grid, exit.
3. Else render all three charts.

**`GET /api/taste/aggregate`** response:

```json
{
  "tracks_considered": 87,
  "runs_considered": 12,
  "top_genres": [
    { "genre": "indie rock", "count": 34 },
    { "genre": "alt rock",   "count": 22 },
    { "genre": "post-rock",  "count": 14 },
    { "genre": "dream pop",  "count": 10 },
    { "genre": "shoegaze",   "count": 7 },
    { "genre": "folk rock",  "count": 5 },
    { "genre": "grunge",     "count": 3 },
    { "genre": "britpop",    "count": 3 }
  ],
  "energy_valence": [
    { "energy": 0.85, "valence": 0.62, "artist": "Muse", "title": "Hysteria" },
    ...
  ],
  "decades": [
    { "decade": "1960s", "count": 2 },
    { "decade": "1970s", "count": 8 },
    { "decade": "1980s", "count": 12 },
    { "decade": "1990s", "count": 21 },
    { "decade": "2000s", "count": 25 },
    { "decade": "2010s", "count": 15 },
    { "decade": "2020s", "count": 4 }
  ]
}
```

**Aggregation rules (backend):**

- Tracks are drawn from all stored runs; dedup by `(artist, title)` case-insensitively.
- `top_genres`: count artist genres across deduped tracks; keep top 8.
- `energy_valence`: include up to 100 tracks with both audio features available. Drop tracks without audio features.
- `decades`: bucket by `release_year // 10 * 10`.

Where Spotify audio features or release years are missing, skip the track for that dataset only.

### 6.3 Chart 1 — Top-genre donut

Custom SVG. 200 × 200 viewBox. 8 wedges. Slice colours cycle through `--primary`, `--accent-teal`, `--accent-cyan`, `--accent-purple`, `--accent-pink`, `--accent-violet`, `#1ed760` (primary duplicate for slot 7), `var(--text-muted)`.

- Wedge path: standard SVG arc.
- Centre hole: 40 % of outer radius.
- Legend: vertical list below the SVG, rendered as rows with a `.legend-swatch` (8px square) + genre name + count.

Hover:
- `pointermove` over a wedge raises it by 4 px (translate outward from centre) and shows a tooltip `<div class="dashboard-tooltip">` with the exact genre + count. Position tooltip near cursor.

Accessibility:
- Wrap in a `<figure>` with a `<figcaption class="sr-only">` describing the top 3 genres as a sentence.
- Each wedge has `role="button"` and `aria-label="indie rock, 34 tracks"`.

### 6.4 Chart 2 — Energy × valence scatter

- SVG 260 × 220 viewBox.
- X-axis: valence 0–1 (sad → happy). Y-axis: energy 0–1 (calm → intense).
- Axes: 1 px `var(--border)` lines, short tick marks at 0, 0.5, 1.
- Axis labels: "Sad" / "Happy" under X, "Calm" / "Intense" rotated -90° on Y.
- Dots: `<circle>` with r=4, fill `var(--primary)` at 0.6 opacity, stroke `var(--primary)` at 0.9.
- Hover: raise opacity to 1, show tooltip with artist + title.
- Performance note: at 100 dots, naive SVG is fine — no canvas optimisation needed.

### 6.5 Chart 3 — Decade bar

- SVG 260 × 180.
- One bar per decade present in data. X axis labelled by decade.
- Bar width: `(chartWidth - (n-1)*gap) / n`.
- Bar height: proportional to max count in dataset.
- Fill: `var(--primary)` with 0.85 opacity, rounded top corners (use `<rect rx="2" ry="2">`).
- Hover: darken + tooltip "2010s — 15 tracks".

### 6.6 Empty state

- `<p>` "Generate a few playlists to see your taste profile."
- Small faded icon (📊) above.
- Centred, padding 40 px.

### 6.7 CSS grid + card styling

- `.dashboard-grid` — `display: grid; gap: 14px; grid-template-columns: 1fr;` Media `≥ 960px`: `grid-template-columns: repeat(3, 1fr);`
- `.dashboard-card` — `background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 18px; min-height: 300px; display: flex; flex-direction: column;`
- `.dashboard-card h4` — `margin: 0 0 14px; font-size: 0.95rem; font-weight: 700; color: var(--text-primary);`
- `.dashboard-tooltip` — `position: fixed; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 10px; font-size: 0.8rem; pointer-events: none; box-shadow: var(--shadow-elevated); z-index: 400;`

### 6.8 Accordion expand state

Persist open/closed in `localStorage` under `sv.dashboard_open`. Default: open.

---

## 7. B.1 — In-context feature discovery tips

### 7.1 Tip catalogue (fixed for Wave 3)

| id | When fires | Tip copy | Link target |
|----|-----------|----------|-------------|
| `first_generation_complete` | `pipeline.js` calls after a successful first generation in this install | "Tip: Try **Band / Song Analysis** to understand why you liked a track." | Switch to OpenAI tab + scroll to analysis section, open it. |
| `disliked_2_plus` | `feedback.js` after second dislike in one session | "Tip: **Refine Existing Playlist** lets you curate any Spotify playlist to train your taste." | Switch to Spotify tab, expand the review section. |
| `first_history_view` | `history.js` on first view of the history tab (per install) | "Tip: **Export your profile** to back it up or share it." | Open profile ⋯ menu → Export. |
| `first_filter_open` | `audio-filters.js` on first expand of the filter subpanel (per install) | "Tip: Filters are optional — leave them empty to let GPT pick freely." | Scrolls to the filter header (no sub-action beyond highlight). |
| `five_generations` | `pipeline.js` when cumulative generation count crosses 5 | "Tip: Save your current settings as a **preset** to reuse them." | Switch to Spotify tab, open Generate panel, open preset dropdown. |

### 7.2 Seen-state storage

`localStorage` key: `sv.tips.seen` = JSON array of tip ids.

- On trigger: check `id in seen`. If yes, skip. Else render + append id.
- Reset via the new "Reset tips" menu item (§ 7.5) — clears the array.

### 7.3 Queue + session gate

- At most one tip per session. A module-level `sessionTipShown = false` prevents re-entry.
- If multiple triggers fire in the same session, the first wins; the rest roll over to the next session naturally because they remain unseen.
- `sessionTipShown` is an in-memory variable, not persisted — reloading the page is a "new session" from the tip's perspective.

### 7.4 UI — tip toast

Extend `frontend/templates/toast.html` or render inline in `tips.js`. The tip toast differs visually from the default toast:

- Border-left accent: `border-left: 3px solid var(--primary);` (instead of the usual no-border toast).
- Icon: 💡 (emoji) at the start, 1.15 rem.
- Copy: two lines — title (bold, primary-text colour) + body (secondary-text).
- Link affordance: an inline button text-link, primary colour, underlined on hover. Click performs the registered action and dismisses the tip.
- Dismiss: `✕` on the right.
- Auto-dismiss: 12 seconds. Countdown not visible. Paused while cursor hovers.
- Slide-in from top-right corner, 14 px offset from the edge.

```html
<div class="toast toast--tip" role="status" aria-live="polite">
  <span class="toast-tip-icon">💡</span>
  <div class="toast-tip-text">
    <div class="toast-tip-title">Tip: Try Band / Song Analysis</div>
    <div class="toast-tip-body">Understand why you liked a track.</div>
    <button class="toast-tip-link">Open Band Analysis →</button>
  </div>
  <button class="toast-tip-close" aria-label="Dismiss">✕</button>
</div>
```

Styling:

- `.toast--tip` — `background: var(--bg-card); border: 1px solid var(--border); border-left: 3px solid var(--primary); border-radius: var(--radius-md); box-shadow: var(--shadow-elevated); padding: 12px 14px; max-width: 360px; display: flex; gap: 10px; align-items: flex-start;`
- `.toast-tip-title` — `font-size: 0.88rem; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;`
- `.toast-tip-body` — `font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px;`
- `.toast-tip-link` — `background: none; border: none; color: var(--primary); font-size: 0.82rem; font-weight: 600; cursor: pointer; padding: 0;` Hover: underline.
- `.toast-tip-close` — text-muted, 1rem `✕`. Hover → `var(--text-primary)`.

### 7.5 "Reset tips" menu item

In `settings_gear.html`, add after "Manage presets" (Wave 2):

```html
<button role="menuitem" onclick="resetTipsSeen()"><span aria-hidden="true">🔄</span> <span data-i18n="nav.reset_tips">Reset tips</span></button>
```

`resetTipsSeen()` — simple JS: `localStorage.removeItem('sv.tips.seen'); showToast(i18n('tip.reset_done', 'Tips reset — you\'ll see them again as you use the app.'));`

### 7.6 Trigger wiring

Where to call `Tips.maybeTrigger(id, ctx?)`:

- `pipeline.js`, on successful generation completion:
  - `Tips.maybeTrigger('first_generation_complete')` — unconditional; tips module handles seen-check.
  - After incrementing a generation-count in `localStorage` (`sv.gen_count`), if new count crosses 5, `Tips.maybeTrigger('five_generations')`.
- `feedback.js`, after each dislike:
  - Keep a `window._svSessionDislikes` counter. After increment, if `>= 2`, `Tips.maybeTrigger('disliked_2_plus')`.
- `history.js`, on tab show:
  - Track a per-install flag `sv.history_viewed`. If not set, trigger + set.
- `audio-filters.js`, on first subpanel expand:
  - Track `sv.filters_opened`. If not set, trigger + set.

These per-install flags live alongside `sv.tips.seen` but are independent — the tip module only checks `sv.tips.seen`, the trigger sites check whatever makes sense for the trigger itself.

---

## 8. Backend — new routes

### 8.1 `GET /api/spotify/playlists_for_seed`

```python
@app.route('/api/spotify/playlists_for_seed', methods=['GET'])
def api_playlists_for_seed():
    if not is_spotify_authenticated():
        return jsonify({'error': 'not_authenticated'}), 401
    playlists = fetch_user_playlists(limit=50)  # first page, 50 items
    return jsonify({'playlists': playlists})
```

`fetch_user_playlists()` lives in `core/src/playlist.py`. Uses `sp.current_user_playlists(limit=50)`.

### 8.2 `POST /api/profile/seed_from_playlist`

```python
@app.route('/api/profile/seed_from_playlist', methods=['POST'])
def api_seed_from_playlist():
    data = request.get_json(silent=True) or {}
    pid = data.get('playlist_id')
    if not pid:
        return jsonify({'error': 'missing_playlist_id'}), 400
    if not is_spotify_authenticated():
        return jsonify({'error': 'not_authenticated'}), 401

    summary = fetch_playlist_items_for_seed(pid)
    # summary: { name, owner, track_count, tracks: [...] }

    try:
        draft = draft_profile_from_playlist(summary)
    except Exception as e:
        logger.exception('seed draft failed')
        return jsonify({'error': 'draft_failed', 'detail': str(e)}), 502

    meta = {
        'playlist_id': pid,
        'playlist_name': summary['name'],
        'track_count': summary['track_count'],
        'top_genres': summary['top_genres'][:5],
        'top_artists': summary['top_artists'][:5],
        'drafted_at': datetime.utcnow().isoformat() + 'Z',
    }
    return jsonify({'draft': draft, 'meta': meta})
```

Never persist the draft here — only return it. Saving is always explicit via the user's action in the editor.

### 8.3 `GET /api/taste/aggregate`

```python
@app.route('/api/taste/aggregate', methods=['GET'])
def api_taste_aggregate():
    runs = load_runs()
    aggregated = aggregate_taste(runs)  # in core/src/analysis.py or new core/src/taste.py
    return jsonify(aggregated)
```

`aggregate_taste(runs)` returns the shape in § 6.2. Pure function; no Spotify calls at aggregation time (metadata must already be in the stored runs). If audio features are missing from older runs, the scatter chart degrades gracefully (fewer points).

---

## 9. Prompt additions

### 9.1 `prompts/suggestions.txt` — rationale section

Append the text from § 5.3 to the existing prompt. Keep the few-shot examples in a separate file (`documentation/prompts/rationale_chips_examples.md`) and include by reference in the prompt render pipeline if the project uses a prompt-templating layer; otherwise paste the two examples inline at the bottom of the prompt file.

### 9.2 `prompts/profile_seed_from_playlist.txt` — new prompt

Outline (fill in English tone, keep it concise — the prompt should be ≤ 800 tokens):

```
You are drafting a SpotyVibe taste profile from a Spotify playlist the user already likes.

Given the following playlist summary, produce a profile JSON with these exact keys:
- core_description: 2–3 sentence prose in the first person ("I love …") describing the sonic qualities of the playlist.
- must_have: array of up to 3 short strings, each a trait the user seems to require (e.g. "driving guitar", "strong melody", "similar to <artist>").
- soft_preferences: array of up to 3 short strings, softer preferences inferred from genre/mood.
- avoid: empty array.

Playlist summary:
  Name:        {name}
  Track count: {count}
  Top artists: {top_artists_list}
  Top genres:  {top_genres_list}
  Median energy: {energy}
  Median valence: {valence}
  Median tempo: {tempo}
  Moods detected (derived): {moods}

Return strict JSON. No trailing commentary.
```

---

## 10. Unit-test notes for `core/`

- `core/tests/test_profile.py` — test `draft_profile_from_playlist()` with a mocked OpenAI response. Validate returned dict has the 5 keys, `avoid` is always `[]`, `must_have` length ≤ 3.
- `core/tests/test_suggestions.py` — test the parser with:
  - a well-formed `rationale` array → passes through.
  - `rationale` with an unknown `type` → that entry is dropped; others kept.
  - `rationale` > 2 entries → capped to 2.
  - `rationale` missing, `reason` present → legacy entry synthesised.
  - `rationale` missing, `reason` missing → fallback entry synthesised.
  - `arg` longer than 40 chars → truncated.
- `core/tests/test_history.py` (create if absent) — test that a run written post-Wave-3 reads back identically, and a run written pre-Wave-3 (only `reason` stored) reads back with a `legacy` rationale synthesised on the fly.
- `core/tests/test_taste.py` (create if absent) — test `aggregate_taste()` with a synthetic run list that produces the shape in § 6.2.

All unit tests must run as part of `python -m pytest core/tests/` with no external API calls.

---

## 11. Wiring — `main.js` bootstrap additions

Order matters. Add after Wave-2 bootstraps:

```js
import * as Tips            from './modules/tips.js';
import * as Rationale       from './modules/rationale.js';
import * as TasteDashboard  from './modules/taste_dashboard.js';
import * as PlaylistSeed    from './modules/playlist_seed.js';

window.addEventListener('DOMContentLoaded', () => {
    Tips.init();                 // registers the 5-tip catalogue
    Rationale.init();            // renders chips on any track row present at load
    TasteDashboard.init();       // binds the accordion, fetches on open
    PlaylistSeed.init();         // binds the picker modal, onboarding card, profile menu item
    // Apply any pending draft stashed during onboarding
    PlaylistSeed.applyPendingDraftIfAny();
});
```

---

## 12. i18n keys

Append to `en.json` and `de.json`. Existing keys are reused where sensible.

```
# Playlist seed (C.1)
seed.modal_title                = "Seed from a Spotify playlist"         / "Aus einer Spotify-Playlist erzeugen"
seed.modal_subtitle             = "Pick one of your playlists — SpotyVibe drafts a profile you can tweak." / "Wähle eine deiner Playlists — SpotyVibe erstellt daraus ein Profil, das du anpassen kannst."
seed.search_placeholder         = "Search your playlists…"               / "Playlists durchsuchen…"
seed.track_count                = "{count} tracks"                       / "{count} Tracks"
seed.owner                      = "by {owner}"                           / "von {owner}"
seed.use_playlist               = "Use this playlist"                    / "Diese Playlist verwenden"
seed.drafting                   = "Drafting your profile… this may take up to 30 seconds." / "Profil wird erstellt… kann bis zu 30 Sekunden dauern."
seed.replace_warning            = "This will replace your current profile's fields. The original is not deleted automatically — export it first if you want to keep it." / "Deine aktuellen Profilfelder werden ersetzt. Das Original wird nicht automatisch gelöscht — exportiere es vorher, wenn du es behalten willst."
seed.continue                   = "Continue"                             / "Weiter"
seed.failed                     = "Couldn't draft a profile from this playlist. Please try a different one." / "Aus dieser Playlist konnte kein Profil erstellt werden. Bitte versuche eine andere."
seed.connect_spotify_first      = "Connect Spotify on step 4 to enable this" / "Spotify in Schritt 4 verbinden, um dies zu aktivieren"

# Profile draft banner
profile.draft_title             = "Drafted from your playlist"           / "Aus Playlist erzeugt"
profile.draft_sub_tpl           = "Generated from \"{name}\" — review and save below." / "Erzeugt aus „{name}" — unten prüfen und speichern."
profile.draft_discard           = "Discard draft"                        / "Entwurf verwerfen"
profile.draft_saved             = "Profile updated from playlist"        / "Profil aus Playlist aktualisiert"

# Profile ⋯ menu
profile.menu_seed_playlist      = "Seed from playlist"                   / "Aus Playlist erzeugen"

# Explainable chips (D.3)
explain.profile_match           = "matches '{arg}'"                      / "passt zu „{arg}"
explain.artist_match            = "similar to {arg}"                     / "ähnlich zu {arg}"
explain.recency                 = "{arg}"                                / "{arg}"
explain.novelty                 = "{arg}"                                / "{arg}"
explain.audio_match             = "matches {arg}"                        / "passt zu {arg}"
explain.legacy                  = "{arg}"                                / "{arg}"
explain.fallback                = "profile match"                        / "passt zum Profil"
explain.recency_released        = "released {year}"                      / "erschienen {year}"
explain.recency_emerging        = "emerging artist"                      / "aufsteigender Künstler"
explain.novelty_discovery       = "discovery pick"                       / "Entdeckung"
explain.novelty_new_artist      = "new artist"                           / "neuer Künstler"

# Taste dashboard (F.1)
dashboard.title                 = "Your taste at a glance"               / "Dein Geschmack auf einen Blick"
dashboard.subtitle              = "Aggregated from your recent playlists and history." / "Aggregiert aus deinen Playlists und deinem Verlauf."
dashboard.card_genres           = "Top genres"                           / "Top-Genres"
dashboard.card_scatter          = "Energy × valence"                     / "Energie × Valence"
dashboard.card_decades          = "Decades"                              / "Jahrzehnte"
dashboard.scatter_sad           = "Sad"                                  / "Traurig"
dashboard.scatter_happy         = "Happy"                                / "Fröhlich"
dashboard.scatter_calm          = "Calm"                                 / "Ruhig"
dashboard.scatter_intense       = "Intense"                              / "Intensiv"
dashboard.scatter_tooltip       = "{artist} — {title}"                   / "{artist} — {title}"
dashboard.decades_tooltip       = "{decade} — {count} tracks"            / "{decade} — {count} Tracks"
dashboard.empty_title           = "Not enough data yet"                  / "Noch zu wenig Daten"
dashboard.empty_body            = "Generate a few playlists to see your taste profile." / "Erzeuge ein paar Playlists, um dein Geschmacksprofil zu sehen."
dashboard.tracks_counted        = "Based on {count} tracks"              / "Basiert auf {count} Tracks"

# Tips (B.1)
tip.first_generation            = "Try Band / Song Analysis"             / "Band-/Song-Analyse ausprobieren"
tip.first_generation_body       = "Understand why you liked a track — paste one and let GPT break it down." / "Verstehe, warum dir ein Track gefällt — füge einen ein und lass ihn von GPT analysieren."
tip.first_generation_link       = "Open Band Analysis →"                 / "Band-Analyse öffnen →"
tip.disliked_2                  = "Refine an existing playlist"          / "Bestehende Playlist verfeinern"
tip.disliked_2_body             = "Curate any Spotify playlist to train your taste — like/dislike without generating." / "Trainiere deinen Geschmack anhand einer existierenden Spotify-Playlist — bewerten ohne zu generieren."
tip.disliked_2_link             = "Open Refine Playlist →"               / "Playlist verfeinern öffnen →"
tip.first_history               = "Export your profile"                  / "Profil exportieren"
tip.first_history_body          = "Back it up or share it — ⋯ menu on the profile." / "Sichere es oder teile es — ⋯-Menü am Profil."
tip.first_history_link          = "Open profile menu →"                  / "Profilmenü öffnen →"
tip.first_filter                = "Filters are optional"                 / "Filter sind optional"
tip.first_filter_body           = "Leave them empty to let GPT pick freely — they only narrow the field." / "Leer lassen, damit GPT frei wählt — Filter schränken nur ein."
tip.first_filter_link           = "Got it"                               / "Alles klar"
tip.five_generations            = "Save this setup as a preset"          / "Diese Einstellung als Voreinstellung speichern"
tip.five_generations_body       = "You've found a combination that works — save it so you can reuse it." / "Du hast eine funktionierende Kombination gefunden — speichere sie zur Wiederverwendung."
tip.five_generations_link       = "Save preset →"                        / "Voreinstellung speichern →"
tip.reset_done                  = "Tips reset — you'll see them again as you use the app." / "Tipps zurückgesetzt — du siehst sie wieder bei der Nutzung."

# Gear menu
nav.reset_tips                  = "Reset tips"                           / "Tipps zurücksetzen"
```

---

## 13. Screenshot tests — additions to `test_documentation_screenshots.py`

Numbers 69–80. Append below Wave 2's 56–68.

```python
# -- Wave 3: New features ---------------------------------------------

def test_69_playlist_seed_modal(self, page: Page, screenshot_url):
    """Screenshot: playlist-seed picker modal (from profile menu)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator("#profileMenuTrigger").click()
    page.wait_for_timeout(200)
    page.locator("#profileMenuSeedPlaylist").click()
    page.wait_for_timeout(400)
    # Inject mock playlist list
    page.evaluate("""() => {
        const list = document.getElementById('playlistSeedList');
        list.innerHTML = '';
        const samples = [
            { id: 'a', name: 'Road Trip Mix', owner: 'Jane', track_count: 25, cover_url: '' },
            { id: 'b', name: 'Weekend Vibes', owner: 'Jane', track_count: 40, cover_url: '' },
            { id: 'c', name: 'Focus Flow',    owner: 'Jane', track_count: 30, cover_url: '' },
        ];
        samples.forEach(p => {
            const li = document.createElement('li');
            li.className = 'playlist-seed-item';
            li.innerHTML = `<div class="playlist-seed-cover"></div><div class="playlist-seed-text"><div class="playlist-seed-name">${p.name}</div><div class="playlist-seed-meta">${p.track_count} tracks · by ${p.owner}</div></div><div class="playlist-seed-check"></div>`;
            list.appendChild(li);
        });
    }""")
    page.wait_for_timeout(200)
    _shot_element(page, "69_playlist_seed_modal", "#playlistSeedModal .modal")

def test_70_playlist_seed_drafting(self, page: Page, screenshot_url):
    """Screenshot: picker modal in drafting state with spinner."""
    # Reuse setup from 69, then select + click Use this playlist
    # … (see implementation pattern from Wave-2 preset tests)
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(300)
    page.locator("#profileMenuTrigger").click()
    page.locator("#profileMenuSeedPlaylist").click()
    page.wait_for_timeout(300)
    page.evaluate("document.querySelector('.playlist-seed-loader').classList.remove('hidden')")
    page.evaluate("document.getElementById('playlistSeedList').classList.add('hidden')")
    _shot_element(page, "70_playlist_seed_drafting", "#playlistSeedModal .modal")

def test_71_profile_draft_banner(self, page: Page, screenshot_url):
    """Screenshot: draft banner on the profile editor after a seed."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        const b = document.getElementById('profileDraftBanner');
        b.classList.remove('hidden');
        document.getElementById('profileDraftSub').textContent = 'Generated from "Road Trip Mix" — review and save below.';
    }""")
    page.wait_for_timeout(200)
    _shot_element(page, "71_profile_draft_banner", "#trainSection")

def test_72_rationale_chips_default(self, page: Page, screenshot_url):
    """Screenshot: track card with default chip pair (profile_match + artist_match)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.evaluate(_INJECT_TRACKS_JS % json.dumps([{
        **_FAKE_SONGLIST[0],
        "rationale": [
            {"type": "profile_match", "arg": "theatrical rock"},
            {"type": "artist_match",  "arg": "Queen"},
        ],
    }]))
    page.wait_for_timeout(400)
    _shot_element(page, "72_rationale_chips_default", "#track-0")

def test_73_rationale_chips_fallback(self, page: Page, screenshot_url):
    """Screenshot: track card with fallback chip (no rationale returned)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    page.evaluate(_INJECT_TRACKS_JS % json.dumps([{
        **_FAKE_SONGLIST[0],
        "rationale": [{"type": "fallback"}],
    }]))
    page.wait_for_timeout(400)
    _shot_element(page, "73_rationale_chips_fallback", "#track-0")

def test_74_rationale_chips_all_types(self, page: Page, screenshot_url):
    """Screenshot: multiple rows showcasing each chip type."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(300)
    tracks = [
        {**_FAKE_SONGLIST[0], "rationale": [{"type":"profile_match","arg":"indie rock"}]},
        {**_FAKE_SONGLIST[1], "rationale": [{"type":"artist_match","arg":"Foo Fighters"}]},
        {**_FAKE_SONGLIST[2], "rationale": [{"type":"recency","arg":"released 2025"}]},
    ]
    page.evaluate(_INJECT_TRACKS_JS % json.dumps(tracks))
    page.wait_for_timeout(400)
    _shot_element(page, "74_rationale_chips_all_types", "#discoverTrackArea")

def test_75_taste_dashboard(self, page: Page, screenshot_url):
    """Screenshot: taste dashboard with all three charts populated."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    # Mock the endpoint response
    page.route("**/api/taste/aggregate", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "tracks_considered": 87,
            "runs_considered": 12,
            "top_genres": [
                {"genre": "indie rock", "count": 34},
                {"genre": "alt rock",   "count": 22},
                {"genre": "post-rock",  "count": 14},
                {"genre": "dream pop",  "count": 10},
                {"genre": "shoegaze",   "count": 7},
                {"genre": "folk rock",  "count": 5},
            ],
            "energy_valence": [
                {"energy": 0.85, "valence": 0.62, "artist": "Muse",    "title": "Hysteria"},
                {"energy": 0.40, "valence": 0.30, "artist": "Radiohead","title": "No Surprises"},
                {"energy": 0.75, "valence": 0.80, "artist": "Queen",   "title": "Don't Stop Me Now"},
            ] * 10,
            "decades": [
                {"decade": "1970s", "count": 8},
                {"decade": "1990s", "count": 21},
                {"decade": "2000s", "count": 25},
                {"decade": "2010s", "count": 15},
            ],
        }),
    ))
    page.reload()
    page.wait_for_load_state("networkidle")
    page.locator(".taste-dashboard-section .accordion-header").click()
    page.wait_for_timeout(500)
    _shot_element(page, "75_taste_dashboard", ".taste-dashboard-section")

def test_76_taste_dashboard_empty(self, page: Page, screenshot_url):
    """Screenshot: dashboard empty state (< 10 tracks)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.route("**/api/taste/aggregate", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"tracks_considered": 3, "runs_considered": 1,
                         "top_genres": [], "energy_valence": [], "decades": []}),
    ))
    page.reload()
    page.wait_for_load_state("networkidle")
    page.locator(".taste-dashboard-section .accordion-header").click()
    page.wait_for_timeout(300)
    _shot_element(page, "76_taste_dashboard_empty", ".taste-dashboard-section")

def test_77_tip_toast_first_generation(self, page: Page, screenshot_url):
    """Screenshot: tip toast (first generation complete)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/tips.js').then(Tips => {
            Tips.showTipById('first_generation_complete');
        });
    }""")
    page.wait_for_timeout(500)
    _shot_element(page, "77_tip_toast_first_generation", ".toast--tip")

def test_78_tip_toast_disliked(self, page: Page, screenshot_url):
    """Screenshot: tip toast (disliked 2+ tracks)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/tips.js').then(Tips => {
            Tips.showTipById('disliked_2_plus');
        });
    }""")
    page.wait_for_timeout(500)
    _shot_element(page, "78_tip_toast_disliked", ".toast--tip")

def test_79_reset_tips_menu(self, page: Page, screenshot_url):
    """Screenshot: burger menu with 'Reset tips' entry visible."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(300)
    _shot_element(page, "79_reset_tips_menu", ".header-controls")

def test_80_onboarding_step5_card1_enabled(self, page: Page, screenshot_url):
    """Screenshot: onboarding step 5 with card 1 enabled (Wave-3 state)."""
    # Pre-condition: Spotify is connected in the mocked state
    self._goto_onboarding_page(page, screenshot_url, page_index=4)
    _shot(page, "80_onboarding_step5_card1_enabled")
```

Note: `_goto_onboarding_page` is the helper added in Wave 1.

---

## 14. Smoke tests — additions to `test_frontend.py`

```python
def test_playlist_seed_happy_path(page, base_url):
    """End-to-end: pick playlist → endpoint returns draft → fields populated → banner visible."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    # Mock endpoints
    page.route("**/api/spotify/playlists_for_seed", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"playlists": [
            {"id": "pl1", "name": "Road Trip Mix", "owner": "Jane", "track_count": 25, "cover_url": ""},
        ]}),
    ))
    page.route("**/api/profile/seed_from_playlist", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "draft": {
                "core_description": "Upbeat melodic rock.",
                "must_have": ["driving guitar"],
                "soft_preferences": ["indie rock"],
                "avoid": [],
                "vibe_description": "",
            },
            "meta": {"playlist_id": "pl1", "playlist_name": "Road Trip Mix", "track_count": 25,
                     "top_genres": [], "top_artists": [], "drafted_at": "2026-01-01T00:00:00Z"},
        }),
    ))
    page.locator("#trainToggleBtn").click()
    page.locator("#profileMenuTrigger").click()
    page.locator("#profileMenuSeedPlaylist").click()
    page.wait_for_selector("#playlistSeedModal:not(.hidden)")
    page.locator(".playlist-seed-item").first.click()
    page.locator("#playlistSeedConfirmBtn").click()
    page.wait_for_selector("#profileDraftBanner:not(.hidden)", timeout=5000)
    assert "Upbeat melodic rock." in page.locator("#trainCoreDesc").input_value()

def test_rationale_chips_render_from_data_attr(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#tab-spotify").click()
    page.locator("#generateToggleBtn").click()
    page.evaluate("""() => {
        const wrap = document.getElementById('discoverTrackArea');
        wrap.classList.remove('hidden');
        const list = document.getElementById('trackList');
        list.innerHTML = `
          <li id="track-0" class="track-item">
            <div class="track-header"><div class="track-info">
              <div class="track-name">Muse — Hysteria</div>
              <div class="track-rationale" data-track-rationale='[{"type":"profile_match","arg":"theatrical rock"},{"type":"artist_match","arg":"Queen"}]'></div>
            </div></div>
          </li>`;
        import('/static/js/modules/rationale.js').then(M => M.renderAll());
    }""")
    page.wait_for_timeout(300)
    chips = page.locator("#track-0 .rationale-chip")
    assert chips.count() == 2
    assert "theatrical rock" in chips.nth(0).text_content()
    assert "Queen" in chips.nth(1).text_content()

def test_tip_shows_once_then_seen(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.removeItem('sv.tips.seen')")
    page.evaluate("""() => {
        import('/static/js/modules/tips.js').then(Tips => {
            Tips.maybeTrigger('first_filter_open');
        });
    }""")
    page.wait_for_selector(".toast--tip", timeout=2000)
    # Dismiss
    page.locator(".toast-tip-close").click()
    page.wait_for_timeout(300)
    # Trigger again — should not reappear
    page.evaluate("""() => {
        import('/static/js/modules/tips.js').then(Tips => {
            Tips.maybeTrigger('first_filter_open');
        });
    }""")
    page.wait_for_timeout(500)
    assert page.locator(".toast--tip").count() == 0

def test_tip_session_gate(page, base_url):
    """Only one tip per session even if two triggers fire."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.removeItem('sv.tips.seen')")
    page.evaluate("""() => {
        import('/static/js/modules/tips.js').then(Tips => {
            Tips.maybeTrigger('first_filter_open');
            Tips.maybeTrigger('disliked_2_plus');
        });
    }""")
    page.wait_for_timeout(600)
    assert page.locator(".toast--tip").count() == 1

def test_taste_dashboard_empty_state(page, base_url):
    page.route("**/api/taste/aggregate", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"tracks_considered": 3, "runs_considered": 1,
                         "top_genres": [], "energy_valence": [], "decades": []}),
    ))
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".taste-dashboard-section .accordion-header").click()
    page.wait_for_selector(".dashboard-empty:not(.hidden)", timeout=3000)

def test_reset_tips_clears_seen(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.setItem('sv.tips.seen', JSON.stringify(['first_filter_open']))")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Reset tips')").click()
    page.wait_for_timeout(300)
    seen = page.evaluate("localStorage.getItem('sv.tips.seen')")
    assert seen is None
```

---

## 15. Acceptance checklist

- [ ] Onboarding step 5 card 1 is enabled when Spotify is connected; disabled with helper copy otherwise.
- [ ] Picker modal opens from onboarding card 1 and from profile editor `⋯` menu. Both paths work.
- [ ] Picker shows up to 50 user playlists with cover, name, track count, owner.
- [ ] Selecting a playlist enables the "Use this playlist" CTA.
- [ ] Existing non-empty profile shows the replace warning inside the picker before drafting.
- [ ] Drafting state: list hidden, loader visible; 30s cap; error toast on failure.
- [ ] Successful draft opens profile editor, fills fields, shows draft banner.
- [ ] "Discard draft" reloads the original profile; banner disappears.
- [ ] Save via "AI Profile Update" or "Save without AI" dismisses the banner and shows a success toast.
- [ ] Onboarding path stashes the draft in `sessionStorage` and applies it on next page load via `applyPendingDraftIfAny()`.
- [ ] Every new track from a Wave-3 generation has `rationale` populated (1–2 entries).
- [ ] Track rows render 1–2 chips — not prose, not `.track-reason` divs.
- [ ] Legacy run-history entries render as a single `legacy` chip.
- [ ] Missing/empty rationale renders a single muted `fallback` chip.
- [ ] Chip types unknown to the client are silently dropped.
- [ ] `arg` longer than 40 chars is truncated in-place.
- [ ] Chips colour-code per type (see § 5.6). Colour mapping matches design.
- [ ] Run history persists `rationale` and `schema_version: 2` for new runs.
- [ ] Parser unit tests pass (§ 10 bullets).
- [ ] Taste dashboard renders below the profile editor body.
- [ ] Dashboard accordion state persists in `localStorage` under `sv.dashboard_open`.
- [ ] `/api/taste/aggregate` returns the shape in § 6.2; dashboard renders all three charts when `tracks_considered >= 10`, else empty state.
- [ ] Donut, scatter, and bar SVGs are hand-rolled (no chart library dependency).
- [ ] Hover tooltip appears on donut wedges, scatter dots, and decade bars, with correct labels.
- [ ] Tips module registers the 5-tip catalogue and triggers correctly from each of the 5 call sites.
- [ ] A triggered tip appears as a `.toast--tip`, slides in top-right, auto-dismisses after 12 seconds unless hovered.
- [ ] Clicking the tip's inline link runs the registered `linkAction` and dismisses the toast.
- [ ] At most one tip per session, regardless of how many triggers fire.
- [ ] Seen state persists in `sv.tips.seen`; a seen tip does not re-appear.
- [ ] "Reset tips" menu item wipes `sv.tips.seen` and shows a confirmation toast.
- [ ] All 12 new screenshot tests (§ 13) pass under `-m screenshots`.
- [ ] All 6 new smoke tests (§ 14) pass under regular pytest.
- [ ] Core unit tests (§ 10) pass under `python -m pytest core/tests/`.
- [ ] No existing test regresses — run `python -m pytest core/tests/ frontend/tests/ -v`.
- [ ] No hardcoded English in any new template, JS module, or Python response — verified by grep.
- [ ] Responsive: at 390×844, dashboard grid stacks vertically; picker modal is full-width with scrollable list; chips wrap under the track title without horizontal overflow.

---

## 16. Review checklist before merging

- [ ] `version.py` bumped.
- [ ] `documentation/UserManual.md` updated: section on playlist seed, chips explanation, dashboard, tip system.
- [ ] `documentation/TechnicalManual.md` updated: rationale schema, run-history schema_version bump, `/api/taste/aggregate` endpoint, `/api/profile/seed_from_playlist` endpoint.
- [ ] `documentation/help.md` updated: user-facing explanations for the dashboard, chips, tip system, and playlist seeding.
- [ ] No Wave-4 surfaces started — no base-URL field on the model picker, no token counter, no microphone button.
- [ ] Project-tree section of `CLAUDE.md` updated with new partials and JS modules.
- [ ] All new strings exist in both `en.json` and `de.json`.
- [ ] No secrets in any prompt example files or few-shot examples.

---

## 17. Reference — surfaces you will touch in Wave 3

| File | Action |
|------|--------|
| `app.py` | Modify — 3 new endpoints (playlists_for_seed, seed_from_playlist, taste/aggregate) |
| `core/src/playlist.py` | Modify — `fetch_user_playlists()`, `fetch_playlist_items_for_seed()` |
| `core/src/spotify_metadata.py` | Modify — batch audio features + artist genres helpers |
| `core/src/profile.py` | Modify — `draft_profile_from_playlist()` |
| `core/src/suggestions.py` | Modify — rationale parser |
| `core/src/history.py` | Modify — persist rationale, schema_version migration on read |
| `core/src/taste.py` (or `analysis.py`) | Create / modify — `aggregate_taste()` |
| `prompts/suggestions.txt` | Modify — rationale section + examples |
| `prompts/profile_seed_from_playlist.txt` | Create |
| `documentation/prompts/rationale_chips_examples.md` | Create |
| `frontend/templates/onboarding.html` | Modify — enable step-5 card 1 |
| `frontend/templates/train_profile.html` | Modify — draft banner mount, ⋯-menu item, include dashboard |
| `frontend/templates/generate_section.html` | Modify — swap `.track-reason` for `.track-rationale` |
| `frontend/templates/run_history.html` | Modify — same chip render for historical tracks |
| `frontend/templates/settings_gear.html` | Modify — "Reset tips" menu item |
| `frontend/templates/base.html` | Modify — include playlist-seed modal |
| `frontend/templates/modals/playlist_seed_modal.html` | Create |
| `frontend/templates/taste_dashboard.html` | Create |
| `frontend/static/css/playlist_seed.css` | Create |
| `frontend/static/css/rationale_chips.css` | Create |
| `frontend/static/css/taste_dashboard.css` | Create |
| `frontend/static/css/tips.css` | Create |
| `frontend/static/js/modules/playlist_seed.js` | Create |
| `frontend/static/js/modules/rationale.js` | Create |
| `frontend/static/js/modules/taste_dashboard.js` | Create |
| `frontend/static/js/modules/tips.js` | Create |
| `frontend/static/js/modules/tracklist.js` | Modify — chip rendering |
| `frontend/static/js/modules/pipeline.js` | Modify — tip triggers |
| `frontend/static/js/modules/feedback.js` | Modify — dislike counter → tip trigger |
| `frontend/static/js/modules/history.js` | Modify — first-view tip trigger |
| `frontend/static/js/modules/audio-filters.js` | Modify — first-open tip trigger |
| `frontend/static/js/modules/profile.js` | Modify — draft-banner integration |
| `frontend/static/js/modules/onboarding.js` (Wave 1) | Modify — wire step-5 card 1 |
| `frontend/static/js/main.js` | Modify — bootstrap new modules |
| `frontend/static/i18n/en.json` | Modify — § 12 keys |
| `frontend/static/i18n/de.json` | Modify — § 12 keys |
| `frontend/tests/test_documentation_screenshots.py` | Modify — 12 new tests |
| `frontend/tests/test_frontend.py` | Modify — 6 new smoke tests |
| `core/tests/test_profile.py` | Modify — `draft_profile_from_playlist` |
| `core/tests/test_suggestions.py` | Modify — rationale parser |
| `core/tests/test_history.py` | Create / modify — schema migration |
| `core/tests/test_taste.py` | Create |

---

## 18. Opening contract for the implementer

You have full autonomy within Wave 3 scope. Do **not** implement anything outside it. When you believe Wave 3 is done, stop and say "Wave 3 complete — please review". Do not commit, do not push, do not start on Wave 4 — the user opens the next implementation file when ready.
