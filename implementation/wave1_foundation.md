# Wave 1 — Foundation: Onboarding rework, language relocation, honest privacy, setup guides

> **Reader.** This document is written for Claude Sonnet 4.6 to implement. It assumes no memory of prior conversations. It is self-contained.
>
> **Source of truth.** The *why* and *UX rationale* are in [`../design.md`](../design.md) § A.1, A.2, A.3, A.4. This document is the *how*.
>
> **Working directory.** `c:\git\spotyvibe`. All paths below are relative to the repo root unless absolute.
>
> **Conventions.** Vanilla ES modules, no bundler, no framework. Jinja2 templates. Modular CSS. i18n via `data-i18n="key"` attributes + `i18n(key, fallback)` runtime. All user-facing text must live in `frontend/static/i18n/en.json` and `de.json` — never hardcoded. See [`../CLAUDE.md`](../CLAUDE.md) for the project's non-negotiable rules (Git safety, i18n, Spotify API constraints, etc.).
>
> **What this wave is.** The reworked onboarding flow as a 7-step wizard, re-runnable from the gear menu; language selector moved into a persistent header above every wizard step; privacy copy corrected; two setup guides (OpenAI, Spotify) with inline-expandable hints and full-screen detail overlays.
>
> **What this wave is NOT.** No playlist-seed-from-Spotify (that is Wave 3, C.1). No voice input (Wave 4, C.2). No profile-completeness meter (Wave 2, C.3). No Quick/Advanced split (Wave 2, D.1). No cost estimator (Wave 4, E.2). No feature tips (Wave 3, B.1). Tell yourself "skeleton, not features" when in doubt.

---

## 1. Scope map

Wave 1 delivers four design.md items simultaneously because they share the same surfaces:

| Ref | Name | Summary |
|-----|------|---------|
| A.1 | Language selector relocation | Remove the dedicated language onboarding page. Put a persistent `EN \| DE` pill in the top-right of the onboarding shell, visible on every step. Main-app language selector in `settings_gear.html` **stays where it is** (user confirmed: "after onboarding leave the language selector where it is currently"). |
| A.4 | Honest privacy messaging | Replace "keys stored locally on your device" short copy with a layered statement (short summary + detail modal with a data-flow table). Applied in onboarding step 1 **and** as a new link in the help page. |
| A.2 | Reworked onboarding / setup wizard | 7 linear steps with back/skip/next. The wizard is re-runnable from the burger menu. All previously onboardable settings live here; every step has a `Skip for now` that does not block the user. |
| A.3 | Inline + overlay setup guides | Each credential-entry step has a three-tier guidance: (1) always-visible one-line hint, (2) inline expandable `How do I get this?` with 3–5 bullets, (3) "Read full guide" button opens a full-screen overlay with numbered steps and screenshots. **Wave 1 ships G1 (OpenAI) and G2 (Spotify) only.** G3/G4 (Python install guides) are deferred. |

### Explicit out-of-scope for Wave 1

- Step 5 (Seed your taste) card 1 "From a Spotify playlist" is rendered but **disabled** with a "Coming soon" badge. The Playwright test should only assert the card is visible and disabled.
- Step 6 (Model & budget) contains **only** the model picker. The cost estimate panel shows a placeholder line "Cost estimate available in a future update" — do not build tokenization.
- No new feature-discovery toasts, no completeness meter, no exploration slider, no presets.
- No guides G3 (macOS) / G4 (Linux). Skeleton support only.
- Do not migrate the gear-menu Credentials modal or Settings modal away yet — they remain, with a small "Re-run setup" entry in the burger menu to open the wizard. In future waves the settings modal shrinks as fields move into the wizard; here, keep duplication.

---

## 2. Files to create, modify, delete

### Create

| Path | Purpose |
|------|---------|
| `frontend/templates/modals/privacy_modal.html` | "What gets sent where?" modal, full data-flow table. Included from `base.html` AND linked from `onboarding.html`. |
| `frontend/static/css/onboarding.css` | All onboarding-shell + wizard styles. Move the current `<style>` block out of `onboarding.html` into this file and expand. |
| `frontend/static/css/setup_guide.css` | Styles for the detail-overlay stepper and the privacy modal's data table. |
| `frontend/static/js/modules/onboarding.js` | ES-module owner of wizard state, navigation, and language-toggle wiring. Replaces the inline `<script>` block currently in `onboarding.html`. |
| `frontend/static/js/modules/setup_guide.js` | Owner of detail-overlay open/close, copy-to-clipboard, keyboard (Esc). Also powers the inline-expandable rows. |
| `documentation/guides/openai_api_key.en.md` | G1 content — numbered steps, references to screenshot assets. |
| `documentation/guides/spotify_developer_app.en.md` | G2 content. |
| `documentation/assets/guides/openai/*.png` | G1 step screenshots (placeholder images — see § 9 for naming). |
| `documentation/assets/guides/spotify/*.png` | G2 step screenshots. |
| `implementation/wave1_foundation.md` | **This file** (already exists by the time you read this). |

### Modify

| Path | What changes |
|------|--------------|
| `frontend/templates/onboarding.html` | Full rewrite to the 7-step skeleton. Move inline CSS into `onboarding.css` and inline JS into `onboarding.js`. |
| `frontend/templates/settings_gear.html` | Add a new burger-menu entry `<button>` "Re-run setup" that opens the wizard (via `/onboarding?replay=1`). |
| `frontend/templates/base.html` | Include `privacy_modal.html`. No other structural changes. |
| `app.py` | Add query-param support for `/onboarding?replay=1` so the route does **not** auto-redirect to `/` even when `is_onboarding_completed()` returns `True`. Add a new helper/endpoint `GET /api/help/guide/<slug>` (returns the raw markdown of a guide, localised if available — English-only for Wave 1). |
| `frontend/static/i18n/en.json` | Add every key listed in § 11. |
| `frontend/static/i18n/de.json` | Same keys with German translations (see § 11 for suggested strings). |
| `frontend/static/css/base.css` | Add three new tokens used by the wizard (see § 3.2). |
| `documentation/help.md` | Add a "Privacy — what leaves your device" section with the data table. Linked from the new privacy modal. |
| `frontend/tests/test_documentation_screenshots.py` | Update onboarding screenshot captures — see § 12. The existing `_goto_onboarding_page` helper + `24_onboarding_credentials.png` filename must remain working (help.md links to it; repoint the filename to the new Step 2 output). |

### Delete

None. All previous functionality is either preserved or repoints to the wizard.

---

## 3. Design tokens and shell — shared across every wizard step

### 3.1 Page chrome

```
viewport (100vh × 100vw)
│
├── background                        ← same dark radial gradient as main app
│
├── language selector .ob-lang-toggle ← fixed, top:16px, right:24px, z-index 50
│
└── .ob-wrap                          ← flex center, full viewport minus titlebar
    │
    └── .ob-card                      ← 480px max-width, centered, radius-lg
        │
        ├── .ob-step-indicator        ← row of 7 pills, top margin 0
        ├── .ob-icon                  ← 3.5rem emoji, centered, margin-top 20px
        ├── .ob-title                 ← 2rem/800, centered, margin-top 12px
        ├── .ob-subtitle              ← 1rem, text-secondary, max-width 360px
        ├── .ob-body                  ← step-specific content, flex column, gap 16px
        └── .ob-nav                   ← sticky bottom row, margin-top 28px
```

### 3.2 New CSS tokens (append to `base.css` `:root`)

```
--ob-card-max-width: 480px;
--ob-card-padding: 32px 24px;
--ob-step-gap: 16px;
```

These are additive only. Do not modify existing tokens.

### 3.3 `.ob-lang-toggle` — persistent language pill

- Fixed position, `top: 16px; right: 24px;` desktop. On viewports ≤ 640px: `top: 12px; right: 16px;`.
- z-index `50` (below modals at 200, above content).
- Markup mirrors the existing `.lang-toggle` in `settings_gear.html` so users get a consistent look:

```html
<div class="lang-toggle ob-lang-toggle" role="group" aria-label="Language">
    <button class="lang-toggle-btn active" data-lang="en" onclick="obSwitchLang('en')" aria-label="English">EN</button>
    <span class="lang-toggle-sep" aria-hidden="true">|</span>
    <button class="lang-toggle-btn" data-lang="de" onclick="obSwitchLang('de')" aria-label="Deutsch">DE</button>
</div>
```

- Style rules override only the positioning; re-use `.lang-toggle*` classes for visual consistency.
- `obSwitchLang(lang)` (in `onboarding.js`) performs: (1) write `svLang` to localStorage, (2) `POST /api/settings { ui_language, gpt_language }`, (3) reload translation JSON, (4) re-render all `[data-i18n]`, `[data-i18n-placeholder]`, `[data-i18n-title]` elements.

### 3.4 `.ob-step-indicator` — 7-step pill row

```
┌─┐ ┌─┐ ┌───┐ · · · ·
 1   2    3    4 5 6 7  (example: step 3 active, 1–2 complete, 4–7 future)
```

Per pill state:

| State | Shape | Size | Color |
|-------|-------|------|-------|
| complete (behind current) | short rounded rect | `16px × 8px`, `border-radius: 4px` | `rgba(30,215,96,0.4)` (`--primary` at 0.4 alpha) |
| current | long rounded rect | `24px × 8px`, `border-radius: 4px` | `var(--primary)` solid |
| future | dot | `8px × 8px`, `border-radius: 50%` | `var(--border)` background |

- Gap between pills: `8px`.
- The row is horizontally centered, `display: flex`, `justify-content: center`.
- Transition `width 200ms ease, background 200ms ease` on every pill so state changes animate.

### 3.5 `.ob-nav` — bottom row

Flex row, `justify-content: space-between`, `width: 100%`.

- **Left slot** — secondary/ghost button. On step 1 it is "Skip" (aria-label "Skip onboarding"). On steps 2–7 it is "← Back" (aria-label "Previous step").
- **Middle slot (steps 2–6 only)** — tertiary text link "Skip for now", muted color. Absent on step 1 (Skip already present) and step 7 (no skipping at the end).
- **Right slot** — primary CTA pill. Label per step: step 1 "Get started →", steps 2–6 "Next →", step 7 "Open SpotyVibe →". Step 7's CTA is full-width and 56px tall (overrides the normal slot); place it in a second row below the Back button, not in the flex row.

Button styles already exist in the app:
- Primary CTA: same as `.onboarding-continue-btn` (reuse).
- Back / Skip ghost: same as `.ob-btn-skip` (reuse).
- "Skip for now" middle link: reuse `.ob-btn-skip` with an additional `.ob-btn-skip--inline` modifier that adds 0.85rem font, underline on hover.

### 3.6 Motion

- Between-step transition: same sliding container as today (`.ob-pages` horizontal flex with `transform: translateX(-Npx)` and `transition: transform 400ms cubic-bezier(0.4,0,0.2,1)`). Keep the current implementation.
- Respect `prefers-reduced-motion`: reduce to `transition: none`. Add `@media (prefers-reduced-motion: reduce)` rule.

### 3.7 Keyboard

- `Esc` closes any open setup-guide overlay or privacy modal. It does **not** dismiss the wizard.
- `Enter` while focus is on a text input advances to the next step *only if* the step's CTA is currently enabled. Otherwise no-op.
- `Tab` order per step: language selector → step indicator is skipped (not focusable) → step content in DOM order → nav row (Back → Skip for now → Next).
- Touch swipe (left/right) navigation **remains** per today's behavior (already in `onboarding.html` init).

---

## 4. Step-by-step screen specifications

All steps use the shell from § 3. Only the `.ob-body` content differs. DOM structure: the wizard is a single `.ob-wrap` with 7 `.ob-page` children, all in the DOM at once, sliding via translateX (unchanged from today).

### Step 1 — Welcome

**Body markup structure:**

```
.ob-body
├── .ob-feature-list                    ← unordered row list, max-width 360px, centered
│   ├── .ob-feature                     ← 🎯 + title + description
│   ├── .ob-feature                     ← 🎧
│   └── .ob-feature                     ← 🔁
│
└── .ob-privacy-panel                   ← NEW, faint green tinted card
    ├── .ob-privacy-icon                ← 🔒
    ├── .ob-privacy-text                ← short privacy sentence
    └── .ob-privacy-link                ← "What gets sent where? →"
```

**Copy (i18n keys listed in § 11):**

- Icon: 🎵
- Title: `ob.step1_title` → "Welcome to SpotyVibe"
- Subtitle: `ob.subtitle` (existing key, reuse) → "AI-powered music discovery. Describe your taste, get the perfect playlist."
- Feature 1: `ob.feature_playlists` + `ob.feature_playlists_desc` (existing keys).
- Feature 2: `ob.feature_spotify` + `ob.feature_spotify_desc`.
- Feature 3: `ob.feature_refine` + `ob.feature_refine_desc`.
- Privacy panel text: `ob.privacy_short` → "Your keys and taste profile stay on your device. When you generate a playlist, your taste is sent to OpenAI (to get suggestions) and track titles go to Spotify (to verify and save them). Nothing else is tracked."
- Privacy link: `ob.privacy_details_link` → "What gets sent where? →"

**Privacy panel exact styling:**

- `background: rgba(30,215,96,0.05);`
- `border: 1px solid rgba(30,215,96,0.2);`
- `border-radius: var(--radius-md);`
- `padding: 14px 16px;`
- `display: flex; gap: 12px; align-items: flex-start;`
- `.ob-privacy-icon` — `font-size: 1.2rem; flex-shrink: 0; margin-top: 2px;`
- `.ob-privacy-text` — `font-size: 0.86rem; color: var(--text-secondary); line-height: 1.4;`
- `.ob-privacy-link` — `display: inline-block; margin-top: 8px; color: var(--primary); font-size: 0.85rem; font-weight: 500; text-decoration: none;` Hover: `text-decoration: underline;`
- Click on the link opens `#privacyModal` (see § 6).

**Nav:** Left "Skip" (exits onboarding: `POST /api/onboarding/complete`, redirect `/`). Right "Get started →" (advance to step 2).

---

### Step 2 — OpenAI API key

**Body markup structure:**

```
.ob-body
└── .ob-cred-section
    ├── .ob-cred-row
    │   ├── label.ob-cred-label          ← "OPENAI API KEY" uppercase
    │   ├── .ob-cred-set-row.hidden      ← "✓ API key — OK" + edit pencil (when already set)
    │   ├── .ob-cred-input-wrap
    │   │   └── input#ob-openai-key type="password" placeholder="sk-…"
    │   └── .ob-cred-hint                ← one-line muted hint
    │
    └── .ob-cred-guide                   ← NEW, the three-tier guidance
        ├── button.ob-cred-guide-toggle  ← "▸ How do I get this?"
        └── .ob-cred-guide-body.hidden
            ├── ol.ob-cred-guide-bullets ← 3 numbered short bullets
            └── button.ob-cred-guide-readmore ← "📖 Read full guide"
```

**Copy:**

- Icon: 🔑
- Title: `ob.step2_title` → "Add your OpenAI key"
- Subtitle: `ob.step2_subtitle` → "SpotyVibe uses OpenAI to generate suggestions. You'll need an API key."
- Label: `ob.openai_key_label` (existing key, reuse) → "OpenAI API Key"
- Hint: `ob.openai_key_hint` → "Paste this from your OpenAI dashboard."
- Guide toggle: `ob.howto_openai` → "How do I get this?"
- Guide bullets: `ob.openai_step1`, `ob.openai_step2`, `ob.openai_step3` — see § 11.
- Read full guide button: `ob.read_full_guide` → "Read full guide"
- Already-set success label: `ob.key_ok` (existing key, reuse) → "API Key — OK"
- Edit pencil aria-label: `ob.edit` (existing).

**"How do I get this?" interaction:**

- Initially collapsed. Click on `.ob-cred-guide-toggle` toggles `.hidden` on `.ob-cred-guide-body`.
- Chevron character `▸` rotates 90° when expanded. Implementation: `.ob-cred-guide-toggle[aria-expanded="true"] .ob-cred-guide-chevron { transform: rotate(90deg); }`
- Toggle exposes `aria-expanded="true|false"` and `aria-controls="ob-openai-guide-body"`.
- Expanded state smooth-animates with `max-height` transition (use a generous `400px` max; content is short).

**"Read full guide" interaction:**

- Clicks call `openSetupGuide('openai')` (defined in `setup_guide.js`) which loads `/api/help/guide/openai_api_key` and shows the `#setupGuideOverlay` (described in § 5).

**Input behavior:**

- On input, `onObCredentialInput()` updates the CTA enabled state. The CTA is enabled if the input has non-empty trimmed content OR if the success row is showing (key already set).
- On "Next →" click: if the input has content, save via `POST /api/settings/credentials` before advancing. If already-set, just advance.

**Skip-for-now behavior:**

- Advance without saving. Do not clear the input if user typed something (they may go back).

**Nav:** Left "← Back". Middle "Skip for now". Right "Next →" (disabled until either input has content or key is already set).

---

### Step 3 — Spotify developer app

**Body markup structure:**

Two credential rows stacked, each identical to step 2's pattern, for Client ID and Client Secret:

```
.ob-body
└── .ob-cred-section
    ├── .ob-cred-row  (id)
    │   ├── label     ← "SPOTIFY CLIENT ID"
    │   ├── .ob-cred-set-row.hidden
    │   ├── .ob-cred-input-wrap
    │   │   └── input#ob-spotify-id type="text" placeholder="Enter client ID…"
    │   └── .ob-cred-hint
    │
    ├── .ob-cred-row  (secret)
    │   ├── label     ← "SPOTIFY CLIENT SECRET"
    │   ├── .ob-cred-set-row.hidden
    │   ├── .ob-cred-input-wrap
    │   │   └── input#ob-spotify-secret type="password" placeholder="Enter client secret…"
    │   └── .ob-cred-hint
    │
    └── .ob-cred-guide                  ← ONE guide covering both fields, not two
        ├── button.ob-cred-guide-toggle ← "▸ How do I get these?"
        └── .ob-cred-guide-body.hidden
            ├── ol.ob-cred-guide-bullets
            │   ├── li "Go to developer.spotify.com/dashboard"
            │   ├── li 'Click "Create app"'
            │   ├── li with inline redirect URI
            │   │   └── .ob-redirect-uri-row  ← monospace pill + 📋 Copy button
            │   └── li "Copy the Client ID and Client Secret."
            └── button.ob-cred-guide-readmore ← "Read full guide"
```

**Copy:**

- Icon: 🎧
- Title: `ob.step3_title` → "Connect a Spotify app"
- Subtitle: `ob.step3_subtitle` → "SpotyVibe talks to Spotify through your own free developer app. It takes about 2 minutes."
- Client ID label: `ob.spotify_id_label` (existing).
- Client ID hint: `ob.spotify_id_hint` → "You'll paste this after creating your app on Spotify's dashboard."
- Client Secret label: `ob.spotify_secret_label` (existing).
- Client Secret hint: `ob.spotify_secret_hint` → "The secret shown right next to your Client ID."
- Guide toggle: `ob.howto_spotify` → "How do I get these?"
- Guide bullet text: `ob.spotify_step1`…`ob.spotify_step4` — see § 11.
- Redirect URI literal (not translated): `http://127.0.0.1:5000/callback`
- Copy button label: `ob.copy` → "Copy"
- Copy success toast: `ob.copied` → "Copied"

**Redirect URI block styling:**

- Flex row, `background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; margin: 8px 0;`
- Left side: `<code>` with `font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 0.82rem; color: var(--text-primary);`
- Right side: `<button class="btn-copy">` with `📋 Copy` — on click, `navigator.clipboard.writeText('http://127.0.0.1:5000/callback')`, then swap button text to `✓ Copied` for 1500ms. Toast is optional; the label swap is sufficient.

**Input behaviors:**

- Same as step 2, but now there are two inputs. Next is enabled when both inputs have content OR both are already-set, OR one is set and the other has content.
- Save on Next: call `POST /api/settings/credentials` with the non-empty values before advancing.

**Nav:** Left "← Back". Middle "Skip for now". Right "Next →".

---

### Step 4 — Connect Spotify

**Body markup structure:**

```
.ob-body
├── button#ob-spotify-btn.ob-action-btn  ← 56px tall, full-width (existing ob-action-btn styling)
│                                           Label: "🔌 Sign in with Spotify" or swap on connect
├── #ob-spotify-status                   ← status line (existing pattern)
│
└── .ob-info-chip                        ← rounded info box
    ├── span.ob-info-icon 🔒
    └── span.ob-info-text
```

**Copy:**

- Icon: 🎶
- Title: `ob.step4_title` → "Connect your Spotify account"
- Subtitle: `ob.step4_subtitle` → "Sign in once so SpotyVibe can save playlists into your library."
- Button, not connected: `ob.connect_btn` (existing) → "🔌 Sign in with Spotify"
- Button, connected: `ob.disconnect_btn` (existing) → "🔌 Disconnect from Spotify"
- Status, connected: `ob.spotify_connected` (existing) → "✓ Spotify connected!"
- Info chip text: `ob.spotify_info` → "Spotify Premium is required for full functionality. The app opens in a browser window and returns here when you're signed in."

**Info chip styling:**

- `background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px 14px;`
- `display: flex; gap: 10px; align-items: flex-start;`
- `.ob-info-icon` — `font-size: 1.05rem; flex-shrink: 0; margin-top: 2px;`
- `.ob-info-text` — `font-size: 0.83rem; color: var(--text-muted); line-height: 1.45;`

**Interaction:** `toggleObSpotify()` behavior is preserved from current `onboarding.html` — opens `/api/spotify/auth` in a popup or same-tab for webview UA, listens for `spotify-auth-complete` postMessage. This code already works; port it unchanged to `onboarding.js`.

**Nav:** Left "← Back". Middle "Skip for now". Right "Next →".

---

### Step 5 — Seed your taste

> Wave 1 delivers the UI shell with 3 options. Card 1 (Spotify playlist seed) is disabled and labeled "Coming soon". Card 2 (Import profile) works — it reuses today's `importProfile()` logic. Card 3 (Start from scratch) is a no-op that advances to step 6.

**Body markup structure:**

```
.ob-body
├── .ob-seed-grid                         ← 3 cards side-by-side on ≥640px, stacked on mobile
│   ├── .ob-seed-card.ob-seed-card--disabled  ← Spotify playlist seed, Coming soon
│   │   ├── .ob-seed-icon     🎵
│   │   ├── .ob-seed-title    "From a Spotify playlist"
│   │   ├── .ob-seed-desc     …
│   │   ├── .ob-seed-badge    "Coming soon"
│   │   └── (no button)
│   ├── .ob-seed-card                      ← Import profile
│   │   ├── .ob-seed-icon     📥
│   │   ├── .ob-seed-title    "Import a profile"
│   │   ├── .ob-seed-desc     …
│   │   └── button.ob-seed-action onclick="obImportProfile()"  "Pick file…"
│   └── .ob-seed-card                      ← Start from scratch
│       ├── .ob-seed-icon     ✍
│       ├── .ob-seed-title    "Start from scratch"
│       ├── .ob-seed-desc     …
│       └── button.ob-seed-action onclick="obGoPage(5)"  "I'll do it in the app"
│
├── #ob-import-status                      ← empty status line below grid (existing)
└── input#ob-import-input type="file" ...  ← hidden, preserved from today
```

**Card layout CSS:**

- `.ob-seed-grid` — `display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;`
- Media query `@media (max-width: 640px) { .ob-seed-grid { grid-template-columns: 1fr; } }`
- `.ob-seed-card` — `background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 16px; display: flex; flex-direction: column; min-height: 180px;`
- `.ob-seed-icon` — `font-size: 1.8rem; margin-bottom: 10px;`
- `.ob-seed-title` — `font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;`
- `.ob-seed-desc` — `font-size: 0.83rem; color: var(--text-secondary); line-height: 1.4; flex-grow: 1;`
- `.ob-seed-action` — pinned to bottom, primary-accent subtle: `background: transparent; border: 1px solid var(--primary); color: var(--primary); padding: 8px 14px; border-radius: var(--radius-pill); font-size: 0.85rem; font-weight: 600; cursor: pointer; align-self: flex-start; margin-top: 12px;` Hover: `background: rgba(30,215,96,0.08);`
- `.ob-seed-card--disabled` — `opacity: 0.55;` The card does not get `.ob-seed-action`; it gets `.ob-seed-badge`.
- `.ob-seed-badge` — `display: inline-block; align-self: flex-start; margin-top: 12px; background: var(--bg-input); color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; padding: 4px 10px; border-radius: var(--radius-pill);`

**Copy:**

- Icon: 🎯
- Title: `ob.step5_title` → "Teach SpotyVibe your taste"
- Subtitle: `ob.step5_subtitle` → "Pick the quickest way in. You can always refine your profile later."
- Card 1 title: `ob.seed_playlist_title` → "From a Spotify playlist"
- Card 1 desc: `ob.seed_playlist_desc` → "Point us at a playlist you already love — SpotyVibe drafts a profile from it you can tweak."
- Card 1 badge: `ob.coming_soon` → "Coming soon"
- Card 2 title: `ob.seed_import_title` → "Import a profile"
- Card 2 desc: `ob.seed_import_desc` → "Got a SpotyVibe profile JSON from a friend or a previous install? Load it here."
- Card 2 button: `ob.seed_import_btn` → "Pick file…"
- Card 3 title: `ob.seed_scratch_title` → "Start from scratch"
- Card 3 desc: `ob.seed_scratch_desc` → "Describe your taste in a sentence or two. You'll edit the full profile in the app next."
- Card 3 button: `ob.seed_scratch_btn` → "I'll do it in the app"

**Behavior:**

- `obImportProfile()` ports the existing `importProfile()` from today's `onboarding.html` unchanged.
- Clicking card 3's button just calls `obGoPage(5)` (advance to step 6). No state change.
- Clicking anywhere on the disabled card is a no-op. Add `aria-disabled="true"` and prevent the button within from existing at all.

**Nav:** Left "← Back". Middle "Skip" (not "Skip for now" — this step's content is optional by nature; wording matches step 1). Right "Next →".

---

### Step 6 — Pick a model

> Wave 1: model picker + a placeholder line where the cost estimate will go in Wave 4.

**Body markup structure:**

```
.ob-body
├── .ob-model-picker
│   ├── label      "PICK YOUR MODEL"
│   ├── select#ob-model-select       ← populated from /api/settings on load
│   └── .ob-model-hint               ← muted one-line explaining trade-off
│
└── .ob-cost-placeholder             ← rounded elevated card
    ├── span.ob-cost-icon 💰
    └── span.ob-cost-text            ← "Per-generation cost estimates coming in a future update."
```

**Copy:**

- Icon: 💰
- Title: `ob.step6_title` → "Pick a model"
- Subtitle: `ob.step6_subtitle` → "Different models cost different amounts per playlist. Pick one that matches your budget."
- Label: `ob.model_label` → "PICK YOUR MODEL"
- Hint: `ob.model_hint` → "You can change this anytime from the gear menu."
- Cost placeholder: `ob.cost_placeholder` → "Per-generation cost estimates coming in a future update."

**Dropdown population:**

- On step 6 activation, `obLoadModels()` calls `GET /api/settings` and reads `available_models` + current `settings.model`. Populate the `<select>` like the gear-menu settings modal does (see `settings_modal.html`).

**Saving:**

- On "Next →", if the selection differs from the stored value, `POST /api/settings { model: <id> }` before advancing.

**Nav:** Left "← Back". Middle "Skip for now". Right "Next →".

---

### Step 7 — Ready

> Summary checklist + single full-width CTA to exit the wizard and open the app.

**Body markup structure:**

```
.ob-body
├── .ob-summary-card                      ← elevated rounded card
│   ├── .ob-summary-row id=sum-openai
│   │   ├── .ob-summary-status            ← ✓ circle (green) or ⚠ circle (amber)
│   │   ├── .ob-summary-text
│   │   │   ├── .ob-summary-label         ← "OpenAI key"
│   │   │   └── .ob-summary-sub           ← "Set" / "Not set — add one to generate playlists"
│   │   └── button.ob-summary-edit        ← "Edit" → jumps back to step 2
│   ├── .ob-summary-row id=sum-spotify-cred
│   ├── .ob-summary-row id=sum-spotify-conn
│   ├── .ob-summary-row id=sum-profile
│   └── .ob-summary-row id=sum-model
│
├── .ob-skipped-warning.hidden            ← appears only if any row is amber
│
└── button#ob-finish-btn.ob-action-btn    ← full-width, 56px tall (existing ob-action-btn sized up)
    "Open SpotyVibe →"
```

**Circle status badge:**

- `.ob-summary-status` is a 28px × 28px circle. `display: flex; align-items: center; justify-content: center; border-radius: 50%; flex-shrink: 0;`
- Done: `background: rgba(34,197,94,0.12); color: var(--success);` content `✓`.
- Skipped: `background: rgba(245,158,11,0.12); color: var(--warning);` content `⚠`.

**Row layout:**

- `.ob-summary-row` — `display: flex; gap: 12px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border);`. Last row has `border-bottom: none;`.
- `.ob-summary-text` — `flex: 1;`
- `.ob-summary-label` — `font-size: 0.92rem; font-weight: 600; color: var(--text-primary);`
- `.ob-summary-sub` — `font-size: 0.8rem; color: var(--text-secondary); margin-top: 2px;`
- `.ob-summary-edit` — text button, `color: var(--primary); font-size: 0.82rem; background: none; border: none; cursor: pointer;` — hover underline.

**Row content derivation (on step 7 activation, one async function `obBuildSummary()`):**

1. `sum-openai`: done if credentials prefill shows OPENAI_API_KEY `is_set: true`.
2. `sum-spotify-cred`: done if both SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET `is_set: true`.
3. `sum-spotify-conn`: done if `/api/spotify/status` returns `authenticated`.
4. `sum-profile`: done if `/api/profile/status` returns `trained: true` OR a profile was imported during this session. **Wave 1 heuristic**: simple — check `/api/profile/status`; if `trained === true`, done. Otherwise skipped.
5. `sum-model`: done if a model is selected. Always true in practice (there is always a default).

**Skipped warning:**

- `.ob-skipped-warning` appears if any row is skipped. Copy: `ob.skipped_warning` → "Some things aren't set. You can still use the app, but a warning will stay in the header until they're done."
- Styling: same as `.ob-info-chip` but with amber tint: `background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.25);` Icon ⚠.

**Copy:**

- Icon: ✅
- Title: `ob.step7_title` → "You're ready to go"
- Subtitle: `ob.step7_subtitle` → "Here's what's set up. You can change any of this later from the gear menu."
- Row labels: `ob.sum_openai`, `ob.sum_spotify_cred`, `ob.sum_spotify_conn`, `ob.sum_profile`, `ob.sum_model`. See § 11.
- Finish button: `ob.finish_btn` → "Open SpotyVibe →"

**Nav:** Left "← Back". **No middle "Skip for now", no right CTA in the standard nav row.** The big Open SpotyVibe button is the terminal action. Place it directly below `.ob-skipped-warning` (or directly below `.ob-summary-card` if no warning), outside the standard `.ob-nav`. The `.ob-nav` on this step contains only the Back button, left-aligned.

**Finish behavior:**

- Call `POST /api/onboarding/complete` (already exists).
- Redirect to `/`.

---

## 5. Setup guide detail overlay (G1 and G2 only)

### 5.1 DOM inclusion

Add to `base.html` alongside other modals, **and** include the same markup in `onboarding.html`. To avoid duplication, put the markup in a partial `frontend/templates/modals/setup_guide_overlay.html` and include it from both.

### 5.2 Structure

```
#setupGuideOverlay.setup-guide-overlay (role=dialog aria-modal=true)
├── button#setupGuideClose (fixed top:24px right:24px) "✕"
└── .setup-guide-scroll
    └── .setup-guide-card
        ├── .setup-guide-pill           ← small "SETUP GUIDE" label
        ├── h2.setup-guide-title        ← varies per guide
        ├── p.setup-guide-subtitle      ← varies per guide
        ├── ol.setup-guide-steps        ← rendered from guide markdown
        │   └── li.setup-guide-step
        │       ├── .setup-guide-step-num
        │       └── .setup-guide-step-body
        │           ├── h3.setup-guide-step-title
        │           ├── p.setup-guide-step-desc
        │           ├── img.setup-guide-step-img (optional)
        │           └── .setup-guide-step-copy (optional, monospace pill + copy btn)
        └── button.setup-guide-done     ← "I'm done — back to setup" primary pill, full-width
```

### 5.3 Styling

- Overlay: `position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(6px); z-index: 200;`
- Close button: 40px circular, `background: var(--bg-elevated); color: var(--text-primary); border: none; border-radius: 50%; z-index: 250;`
- Card: `max-width: 720px; margin: 48px auto; background: var(--bg-card); border-radius: var(--radius-lg); box-shadow: var(--shadow-card); padding: 32px;`
- Pill label: `display: inline-block; background: var(--primary); color: var(--btn-cta-text); padding: 4px 12px; border-radius: var(--radius-pill); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;`
- Title: `font-size: 1.8rem; font-weight: 700; margin: 10px 0 8px;`
- Subtitle: `font-size: 1rem; color: var(--text-secondary); margin-bottom: 24px;`
- Step: `display: flex; gap: 16px; align-items: flex-start; margin-bottom: 28px;`
- Step number: `width: 32px; height: 32px; border-radius: 50%; background: var(--bg-elevated); color: var(--primary); display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0;`
- Step image: `width: 100%; border-radius: var(--radius-sm); border: 1px solid var(--border); margin-top: 12px; display: block;`

### 5.4 Guide loader contract

`setup_guide.js` exports `openSetupGuide(slug)`. Behavior:

1. Show `#setupGuideOverlay`, block page scroll (`body.style.overflow = 'hidden'`).
2. `fetch('/api/help/guide/' + slug)` — new Flask endpoint (see § 10). Expect JSON: `{ title, subtitle, steps: [{ title, description, image?, copy? }] }`.
3. Render into the overlay DOM.
4. Attach copy buttons to any step that has `copy` (e.g. the Spotify redirect URI).
5. Close triggers: `✕` button, `Esc` key, "I'm done" button, click outside the card.

### 5.5 Guide content files

Create `documentation/guides/openai_api_key.en.md` and `documentation/guides/spotify_developer_app.en.md`. Use a simple frontmatter + numbered-step format the Python endpoint parses:

```yaml
---
title: Get your OpenAI API key
subtitle: A free developer account, then one click to create a key.
---

## Step 1 — Sign up or sign in
Go to [platform.openai.com](https://platform.openai.com) and log in (or create an account if you don't have one yet — signup takes about a minute).
![Sign in to OpenAI](/docs/guides/openai/step1_signin.png)

## Step 2 — Open the API keys page
In the left sidebar, click **API keys**. You may need to verify your phone number first — this is OpenAI's anti-abuse check, not a SpotyVibe requirement.
![API keys in the sidebar](/docs/guides/openai/step2_sidebar.png)

## Step 3 — Create a new key
Click **Create new secret key**, give it any name (e.g. `SpotyVibe`), and click Create. Copy the key immediately — OpenAI will not show it again.
![Create new key](/docs/guides/openai/step3_create.png)
```

The endpoint in § 10 parses the `---` frontmatter, splits on `## Step N — …`, and extracts an optional image reference. For the Spotify guide, add a special copy-block:

```markdown
## Step 3 — Set the Redirect URI
Paste this exact URL into the **Redirect URIs** field:

```copy
http://127.0.0.1:5000/callback
```
```

The ```copy`` fenced block tells the parser to render a copy-pill below the step. Keep the parser simple — regex is fine.

**Screenshot assets:** place placeholders at `documentation/assets/guides/openai/step1_signin.png`, `step2_sidebar.png`, `step3_create.png` and equivalent paths under `spotify/`. They can be 1-pixel transparent PNGs for Wave 1 — the implementer replaces them by manual capture. Add a note to the README of `documentation/assets/guides/` explaining this.

---

## 6. Privacy modal

### 6.1 File

`frontend/templates/modals/privacy_modal.html`. Include from `base.html` after the existing help modal include.

### 6.2 Structure

```
#privacyModal.modal-overlay (role=dialog aria-modal=true aria-labelledby=privacyModalTitle)
└── .modal
    ├── h2#privacyModalTitle 🔒 "What gets sent where?"
    ├── p.privacy-summary                 ← same short copy as onboarding's .ob-privacy-text
    ├── table.privacy-table
    │   ├── thead
    │   │   └── tr  Data | Stored on device | Sent to OpenAI | Sent to Spotify
    │   └── tbody (5 rows — see § 6.4)
    ├── p.privacy-footnote                ← muted one-line "Applies to the default SpotyVibe setup. Custom LLM endpoints may route data differently."
    └── .modal-actions
        └── button.btn.btn-cancel onclick=closeModal('privacyModal')  "Close"
```

### 6.3 Table styling

- `width: 100%; border-collapse: collapse; font-size: 0.85rem; margin: 16px 0;`
- Header cells: `background: var(--bg-elevated); color: var(--text-primary); font-weight: 600; padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border);`
- Body cells: `padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text-secondary);`
- Checkmark/dash: ✓ in `--primary`, — in `--text-muted`. Center-align those three columns.

### 6.4 Table rows

| Data | On device | To OpenAI | To Spotify |
|------|-----------|-----------|------------|
| `priv.row_keys` API keys | ✓ | — | — |
| `priv.row_profile` Taste profile (text) | ✓ | ✓ (per generation) | — |
| `priv.row_feedback` Track likes / dislikes | ✓ | ✓ (per generation) | — |
| `priv.row_titles` Suggested track titles | ✓ | — | ✓ (search / add) |
| `priv.row_library` Listening history | — | — | ✓ (read once) |

### 6.5 Open / close

- Open: called from `.ob-privacy-link` click (`openPrivacyModal()`) AND from a new link added to `help.md` rendering (see § 8).
- Close: existing `closeModal()` helper handles Esc + outside click + button click.

---

## 7. Gear-menu "Re-run setup" entry

### 7.1 `settings_gear.html` modification

Insert a new menu item in the `#settingsDropdown` between "Settings" and "Spotify toggle":

```html
<button role="menuitem" onclick="rerunSetup()"><span aria-hidden="true">🪄</span> <span data-i18n="nav.rerun_setup">Re-run setup</span></button>
```

### 7.2 `rerunSetup()` implementation

In an appropriate JS module (likely `modals.js` or a new small helper), define:

```js
function rerunSetup() {
    window.location.href = '/onboarding?replay=1';
}
```

### 7.3 Backend

`app.py` currently has a route for `/onboarding` that renders the template. It may also have redirection logic to `/` when `is_onboarding_completed()` returns true.

- If a redirect-on-completed check exists, gate it with `if request.args.get('replay') != '1':`.
- The frontend `(async function () { ... })()` init block in `onboarding.html` also checks status and redirects — update it: `if (data.completed && !new URLSearchParams(location.search).get('replay')) { window.location.href = '/'; }`.

---

## 8. Privacy section in help.md

Append a new section to `documentation/help.md` (location: near the top, after the intro, before "Getting Started"):

```markdown
## Privacy — what leaves your device

SpotyVibe keeps your keys and taste profile on your device. When you generate a playlist, your taste is sent to OpenAI (to get suggestions) and track titles are sent to Spotify (to verify and save them). Nothing else is tracked.

[See the full data-flow table →](#privacy-table){.open-privacy-modal}

<a id="privacy-table"></a>

| Data | On device | To OpenAI | To Spotify |
|------|-----------|-----------|------------|
| API keys | ✓ | — | — |
| Taste profile (text) | ✓ | ✓ (per generation) | — |
| Track likes / dislikes | ✓ | ✓ (per generation) | — |
| Suggested track titles | ✓ | — | ✓ (search / add) |
| Listening history | — | — | ✓ (read once) |

Applies to the default SpotyVibe setup. Custom LLM endpoints may route data differently.
```

The `.open-privacy-modal` marker is a hint for a minor enhancement: in `help.js` or equivalent, attach click handlers to any link with that class to open the modal instead of scrolling. Low priority — the inline table is the main deliverable.

---

## 9. Documentation asset placeholders

Create `documentation/assets/guides/README.md`:

```markdown
# Setup guide screenshots

These images are served by the in-app setup guides (reachable from the onboarding wizard and the help modal). They are manually captured from the live OpenAI and Spotify developer dashboards.

| Guide | Steps | Files |
|-------|-------|-------|
| OpenAI API key (G1) | 3 | `openai/step1_signin.png`, `openai/step2_sidebar.png`, `openai/step3_create.png` |
| Spotify developer app (G2) | 4 | `spotify/step1_dashboard.png`, `spotify/step2_create.png`, `spotify/step3_redirect.png`, `spotify/step4_secret.png` |

When a Spotify or OpenAI dashboard redesign renders a screenshot stale, replace the file in-place (same filename). Do not rename — the guide markdown under `documentation/guides/*.md` references these paths.
```

For Wave 1, commit 1×1 transparent PNG placeholders at all referenced paths so the guide overlay does not 404. Mark them with a TODO in the README (above).

---

## 10. Backend — Flask changes in `app.py`

### 10.1 `/onboarding` — gate redirect on `?replay=1`

Find the existing `/onboarding` route. If it has a "redirect-if-completed" check, update as shown. If it does not (the frontend does the check itself), ensure the frontend check honors `?replay=1` (§ 7.3).

### 10.2 `GET /api/help/guide/<slug>` — new endpoint

- Read `documentation/guides/<slug>.<lang>.md` where `<lang>` is the session's UI language, falling back to `.en.md`.
- Parse YAML frontmatter (`title`, `subtitle`).
- Parse body: split on `^## Step \d+ —\s*(.+)$` headings into steps. For each step, extract the paragraph(s) until the next `## Step` or EOF.
- Extract first `![alt](path)` as the step's `image` field.
- Extract first ```` ```copy ```` fenced block as the step's `copy` field.
- Return JSON: `{ title, subtitle, steps: [{ title, description, image?, copy? }] }`.

Slug whitelist: `openai_api_key`, `spotify_developer_app`. Reject others with 404.

Use `re` only — no new dependencies. Frontmatter can be parsed with a tiny hand-rolled split on `---` lines, no PyYAML.

### 10.3 Do not delete existing credential endpoints

`POST /api/settings/credentials`, `GET /api/settings/credentials`, `POST /api/settings`, `GET /api/settings`, `POST /api/onboarding/complete`, `GET /api/onboarding/status`, `POST /api/profile/import`, `/api/spotify/auth`, `/api/spotify/status`, `/api/spotify/disconnect`, `GET /api/profile/status` — all preserved, all called by the wizard.

---

## 11. i18n keys (add to `en.json` and `de.json`)

Keep existing keys unchanged. Append the following. The German strings below are suggestions; the implementer may improve them but every key MUST exist in both files.

```
# Wizard nav
ob.back             = "← Back"           / "← Zurück"
ob.skip_for_now     = "Skip for now"     / "Später erledigen"
ob.get_started      = "Get started →"    / "Loslegen →"

# Step 1
ob.step1_title                 = "Welcome to SpotyVibe"                 / "Willkommen bei SpotyVibe"
ob.privacy_short               = "Your keys and taste profile stay on your device. When you generate a playlist, your taste is sent to OpenAI (to get suggestions) and track titles go to Spotify (to verify and save them). Nothing else is tracked." / "Deine Schlüssel und dein Geschmacksprofil bleiben auf deinem Gerät. Wenn du eine Playlist erstellst, wird dein Profil an OpenAI (für Vorschläge) und werden Songtitel an Spotify (zum Prüfen und Speichern) gesendet. Mehr wird nicht übertragen."
ob.privacy_details_link        = "What gets sent where? →"              / "Was wird wohin gesendet? →"

# Step 2
ob.step2_title                 = "Add your OpenAI key"                  / "OpenAI-Schlüssel hinzufügen"
ob.step2_subtitle              = "SpotyVibe uses OpenAI to generate suggestions. You'll need an API key." / "SpotyVibe verwendet OpenAI für Vorschläge. Du brauchst dafür einen API-Schlüssel."
ob.openai_key_hint             = "Paste this from your OpenAI dashboard." / "Diesen Wert findest du in deinem OpenAI-Dashboard."
ob.howto_openai                = "How do I get this?"                   / "Wie komme ich daran?"
ob.openai_step1                = "Go to platform.openai.com/api-keys"   / "Öffne platform.openai.com/api-keys"
ob.openai_step2                = "Click \"Create new secret key\""      / "Klicke auf \"Create new secret key\""
ob.openai_step3                = "Copy it (you won't see it again)"     / "Kopiere ihn (du siehst ihn nur einmal)"
ob.read_full_guide             = "Read full guide"                       / "Vollständige Anleitung"

# Step 3
ob.step3_title                 = "Connect a Spotify app"                / "Spotify-App verbinden"
ob.step3_subtitle              = "SpotyVibe talks to Spotify through your own free developer app. It takes about 2 minutes." / "SpotyVibe spricht mit Spotify über deine eigene kostenlose Developer-App. Das dauert etwa 2 Minuten."
ob.spotify_id_hint             = "You'll paste this after creating your app on Spotify's dashboard." / "Den Wert bekommst du, nachdem du deine App im Spotify-Dashboard erstellt hast."
ob.spotify_secret_hint         = "The secret shown right next to your Client ID." / "Das Secret, das direkt neben der Client-ID angezeigt wird."
ob.howto_spotify               = "How do I get these?"                  / "Wie komme ich daran?"
ob.spotify_step1               = "Go to developer.spotify.com/dashboard" / "Öffne developer.spotify.com/dashboard"
ob.spotify_step2               = "Click \"Create app\". Any name, any description." / "Klicke auf \"Create app\". Name und Beschreibung frei wählbar."
ob.spotify_step3               = "Set the Redirect URI to exactly:"     / "Trage als Redirect URI exakt ein:"
ob.spotify_step4               = "Copy the Client ID and Client Secret." / "Kopiere Client ID und Client Secret."
ob.copy                        = "Copy"                                  / "Kopieren"
ob.copied                      = "✓ Copied"                              / "✓ Kopiert"

# Step 4
ob.step4_title                 = "Connect your Spotify account"         / "Spotify-Konto verbinden"
ob.step4_subtitle              = "Sign in once so SpotyVibe can save playlists into your library." / "Melde dich einmal an, damit SpotyVibe Playlists in deine Bibliothek speichern kann."
ob.spotify_info                = "Spotify Premium is required for full functionality. The app opens in a browser window and returns here when you're signed in." / "Für volle Funktionalität ist Spotify Premium nötig. Die Anmeldung erfolgt in einem Browserfenster und kehrt danach hierher zurück."

# Step 5
ob.step5_title                 = "Teach SpotyVibe your taste"           / "SpotyVibe deinen Geschmack beibringen"
ob.step5_subtitle              = "Pick the quickest way in. You can always refine your profile later." / "Wähle den schnellsten Einstieg. Das Profil kannst du später jederzeit verfeinern."
ob.seed_playlist_title         = "From a Spotify playlist"              / "Aus einer Spotify-Playlist"
ob.seed_playlist_desc          = "Point us at a playlist you already love — SpotyVibe drafts a profile from it you can tweak." / "Wähle eine Playlist, die du magst — SpotyVibe erstellt daraus ein Profil, das du anpassen kannst."
ob.coming_soon                 = "Coming soon"                          / "Bald verfügbar"
ob.seed_import_title           = "Import a profile"                     / "Profil importieren"
ob.seed_import_desc            = "Got a SpotyVibe profile JSON from a friend or a previous install? Load it here." / "Hast du ein SpotyVibe-Profil-JSON von einem Freund oder einer früheren Installation? Hier hochladen."
ob.seed_import_btn             = "Pick file…"                           / "Datei wählen…"
ob.seed_scratch_title          = "Start from scratch"                   / "Von null beginnen"
ob.seed_scratch_desc           = "Describe your taste in a sentence or two. You'll edit the full profile in the app next." / "Beschreibe deinen Geschmack in ein, zwei Sätzen. Das vollständige Profil pflegst du danach in der App."
ob.seed_scratch_btn            = "I'll do it in the app"                / "Erledige ich in der App"

# Step 6
ob.step6_title                 = "Pick a model"                         / "Modell wählen"
ob.step6_subtitle              = "Different models cost different amounts per playlist. Pick one that matches your budget." / "Verschiedene Modelle kosten pro Playlist unterschiedlich viel. Wähle eines, das zu deinem Budget passt."
ob.model_label                 = "PICK YOUR MODEL"                      / "MODELL AUSWÄHLEN"
ob.model_hint                  = "You can change this anytime from the gear menu." / "Du kannst das Modell jederzeit im Zahnrad-Menü wechseln."
ob.cost_placeholder            = "Per-generation cost estimates coming in a future update." / "Kostenabschätzungen pro Generierung folgen in einem zukünftigen Update."

# Step 7
ob.step7_title                 = "You're ready to go"                   / "Du kannst loslegen"
ob.step7_subtitle              = "Here's what's set up. You can change any of this later from the gear menu." / "Das ist eingerichtet. Du kannst alles später im Zahnrad-Menü ändern."
ob.sum_openai                  = "OpenAI key"                           / "OpenAI-Schlüssel"
ob.sum_spotify_cred            = "Spotify developer app"                / "Spotify Developer-App"
ob.sum_spotify_conn            = "Spotify account"                      / "Spotify-Konto"
ob.sum_profile                 = "Taste profile"                        / "Geschmacksprofil"
ob.sum_model                   = "Model"                                / "Modell"
ob.sum_set                     = "Set"                                  / "Eingerichtet"
ob.sum_not_set                 = "Not set"                              / "Nicht eingerichtet"
ob.sum_connected_as            = "Connected as {user}"                  / "Angemeldet als {user}"
ob.sum_edit                    = "Edit"                                 / "Bearbeiten"
ob.skipped_warning             = "Some things aren't set. You can still use the app, but a warning will stay in the header until they're done." / "Einiges ist noch nicht eingerichtet. Du kannst die App trotzdem nutzen; eine Warnung bleibt im Header, bis alles fertig ist."
ob.finish_btn                  = "Open SpotyVibe →"                     / "SpotyVibe öffnen →"

# Gear menu
nav.rerun_setup                = "Re-run setup"                         / "Einrichtung erneut starten"

# Privacy modal
priv.title                     = "What gets sent where?"                / "Was wird wohin gesendet?"
priv.col_data                  = "Data"                                 / "Daten"
priv.col_device                = "On device"                            / "Auf dem Gerät"
priv.col_openai                = "To OpenAI"                            / "An OpenAI"
priv.col_spotify               = "To Spotify"                           / "An Spotify"
priv.row_keys                  = "API keys"                             / "API-Schlüssel"
priv.row_profile               = "Taste profile (text)"                 / "Geschmacksprofil (Text)"
priv.row_feedback              = "Track likes / dislikes"               / "Song-Bewertungen"
priv.row_titles                = "Suggested track titles"               / "Vorgeschlagene Songtitel"
priv.row_library               = "Listening history"                    / "Hörverlauf"
priv.per_generation            = "per generation"                       / "pro Generierung"
priv.search_add                = "search / add"                         / "Suchen / Hinzufügen"
priv.read_once                 = "read once"                            / "einmal gelesen"
priv.footnote                  = "Applies to the default SpotyVibe setup. Custom LLM endpoints may route data differently." / "Gilt für die Standard-Einrichtung von SpotyVibe. Eigene LLM-Endpunkte können Daten anders verarbeiten."
priv.close                     = "Close"                                / "Schließen"
```

Keys that already exist in `en.json` and are reused above: `ob.subtitle`, `ob.feature_*`, `ob.openai_key_label`, `ob.spotify_id_label`, `ob.spotify_secret_label`, `ob.key_ok`, `ob.id_ok`, `ob.secret_ok`, `ob.edit`, `ob.connect_btn`, `ob.disconnect_btn`, `ob.spotify_connected`, `ob.cred_saved`, `ob.cred_error`, `ob.network_error`, `ob.opening_spotify`, `ob.nothing_to_save`, `ob.save_credentials`, `ob.profile_imported`, `ob.import_failed`, `ob.close`. Do not duplicate.

---

## 12. Screenshot tests — updates to `test_documentation_screenshots.py`

The new wizard has 7 steps, not 4. The existing `_goto_onboarding_page(page_index)` helper relied on indices 0–3. Update it as follows.

### 12.1 Rewrite `_goto_onboarding_page`

```python
def _goto_onboarding_page(self, page: Page, screenshot_url: str, page_index: int):
    """Open /onboarding?replay=1 and advance to the given 0-based step index.

    page_index 0 = Welcome, 1 = OpenAI key, 2 = Spotify cred,
    3 = Connect Spotify, 4 = Seed taste, 5 = Model, 6 = Ready.
    """
    def handle_status(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"completed": False}),
        )
    page.route("**/api/onboarding/status", handle_status)
    page.goto(screenshot_url + "/onboarding?replay=1")
    page.wait_for_load_state("networkidle")
    for i in range(page_index):
        # Each step's CTA may be "Get started →", "Next →", or a step-terminal CTA.
        # Click the visible CTA inside the currently-active page.
        page.locator(".ob-page.active .ob-cta-next, .ob-page.active .ob-cta-start").first.click()
        page.wait_for_timeout(500)
    page.wait_for_timeout(200)
```

Note: the CSS classes `.ob-page.active`, `.ob-cta-next`, `.ob-cta-start` are conventions for the new wizard; use them consistently in `onboarding.html` so the test can rely on them.

### 12.2 Keep existing file `24_onboarding_credentials.png` pointing to the new Step 2 (OpenAI key)

`help.md` line 92 references `24_onboarding_credentials.png`. After the rewrite, "credentials" maps to Step 2 (OpenAI) most closely. Keep:

```python
def test_24_onboarding_credentials(self, page: Page, screenshot_url):
    """Screenshot: Onboarding step 2 — OpenAI API key (kept at this filename
    because documentation/help.md links to it)."""
    self._goto_onboarding_page(page, screenshot_url, page_index=1)
    _shot(page, "24_onboarding_credentials")
```

### 12.3 Replace the three existing `test_45/46/47` onboarding tests with full 7-step capture

Delete the current `test_45_onboarding_intro`, `test_46_onboarding_language`, `test_47_onboarding_connect_import`. Replace with the following eleven tests (seven steps + overlays + privacy modal + re-run flow):

```python
def test_45_onboarding_step1_welcome(self, page, screenshot_url):
    self._goto_onboarding_page(page, screenshot_url, page_index=0)
    _shot(page, "45_onboarding_step1_welcome")

def test_46_onboarding_step2_openai(self, page, screenshot_url):
    # Covered by test_24; keep a separate _step2 capture only if the framing
    # helps documentation. Re-point this test number to the Spotify step.
    self._goto_onboarding_page(page, screenshot_url, page_index=2)
    _shot(page, "46_onboarding_step3_spotify_cred")

def test_47_onboarding_step4_connect(self, page, screenshot_url):
    self._goto_onboarding_page(page, screenshot_url, page_index=3)
    _shot(page, "47_onboarding_step4_connect")

def test_48_onboarding_step5_seed(self, page, screenshot_url):
    self._goto_onboarding_page(page, screenshot_url, page_index=4)
    _shot(page, "48_onboarding_step5_seed")

def test_49_onboarding_step6_model(self, page, screenshot_url):
    self._goto_onboarding_page(page, screenshot_url, page_index=5)
    _shot(page, "49_onboarding_step6_model")

def test_50_onboarding_step7_ready(self, page, screenshot_url):
    self._goto_onboarding_page(page, screenshot_url, page_index=6)
    _shot(page, "50_onboarding_step7_ready")

def test_51_onboarding_howto_openai_expanded(self, page, screenshot_url):
    """Step 2 with the 'How do I get this?' accordion expanded."""
    self._goto_onboarding_page(page, screenshot_url, page_index=1)
    page.locator(".ob-cred-guide-toggle").click()
    page.wait_for_timeout(250)
    _shot(page, "51_onboarding_howto_openai_expanded")

def test_52_setup_guide_openai_overlay(self, page, screenshot_url):
    """The full-screen OpenAI setup guide overlay."""
    self._goto_onboarding_page(page, screenshot_url, page_index=1)
    page.locator(".ob-cred-guide-toggle").click()
    page.wait_for_timeout(250)
    page.locator(".ob-cred-guide-readmore").click()
    page.wait_for_timeout(400)
    _shot(page, "52_setup_guide_openai")

def test_53_setup_guide_spotify_overlay(self, page, screenshot_url):
    """The full-screen Spotify setup guide overlay."""
    self._goto_onboarding_page(page, screenshot_url, page_index=2)
    page.locator(".ob-cred-guide-toggle").click()
    page.wait_for_timeout(250)
    page.locator(".ob-cred-guide-readmore").click()
    page.wait_for_timeout(400)
    _shot(page, "53_setup_guide_spotify")

def test_54_privacy_modal(self, page, screenshot_url):
    """Privacy 'What gets sent where?' modal, opened from onboarding step 1."""
    self._goto_onboarding_page(page, screenshot_url, page_index=0)
    page.locator(".ob-privacy-link").click()
    page.wait_for_timeout(300)
    _shot_element(page, "54_privacy_modal", "#privacyModal .modal")

def test_55_rerun_setup_menu_item(self, page, screenshot_url):
    """The gear-menu burger with 'Re-run setup' visible."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(300)
    _shot_element(page, "55_rerun_setup_menu_item", ".header-controls")
```

Update the section header comment above these tests to reflect the new flow.

---

## 13. Smoke tests — new Playwright tests

Add to `frontend/tests/test_frontend.py` (not the screenshot file). These run under normal `pytest` and must pass on every change.

```python
def test_wizard_walks_7_steps(page, base_url):
    """Smoke: open wizard via replay, click Next through all steps, finish."""
    page.goto(base_url + "/onboarding?replay=1")
    page.wait_for_load_state("networkidle")

    # Step 1 → "Get started →"
    page.locator(".ob-cta-start").click()
    page.wait_for_timeout(300)

    # Steps 2–6 → "Skip for now" to avoid credential input
    for _ in range(5):
        page.locator(".ob-page.active .ob-cta-skip-inline").click()
        page.wait_for_timeout(300)

    # Step 7 → "Open SpotyVibe →"
    page.locator("#ob-finish-btn").click()
    page.wait_for_url(base_url + "/", timeout=5000)

def test_wizard_howto_accordion_toggles(page, base_url):
    page.goto(base_url + "/onboarding?replay=1")
    page.locator(".ob-cta-start").click()
    page.wait_for_timeout(300)
    toggle = page.locator(".ob-cred-guide-toggle")
    body = page.locator(".ob-cred-guide-body")
    assert body.is_hidden()
    toggle.click()
    assert body.is_visible()
    toggle.click()
    assert body.is_hidden()

def test_privacy_modal_opens_and_closes(page, base_url):
    page.goto(base_url + "/onboarding?replay=1")
    page.wait_for_load_state("networkidle")
    page.locator(".ob-privacy-link").click()
    page.wait_for_selector("#privacyModal:not(.hidden)")
    page.keyboard.press("Escape")
    page.wait_for_selector("#privacyModal.hidden")

def test_language_toggle_persists_across_steps(page, base_url):
    page.goto(base_url + "/onboarding?replay=1")
    page.wait_for_load_state("networkidle")
    page.locator(".ob-lang-toggle button[data-lang='de']").click()
    page.wait_for_timeout(400)
    # Advance to next step
    page.locator(".ob-cta-start").click()
    page.wait_for_timeout(400)
    # Assert German is still active
    assert page.locator(".ob-lang-toggle button[data-lang='de']").get_attribute("class").__contains__("active")
```

If `base_url` fixture does not exist in `test_frontend.py`, follow the existing pattern in that file for starting a test server; do not copy from `test_documentation_screenshots.py` (those tests run under `-m screenshots` only).

---

## 14. Acceptance checklist

Before considering Wave 1 done, verify each box:

- [ ] `/onboarding` (cold install) renders the new 7-step wizard.
- [ ] `/onboarding?replay=1` renders the wizard even when `is_onboarding_completed()` is true.
- [ ] Burger menu shows a "Re-run setup" entry; clicking it navigates to `/onboarding?replay=1`.
- [ ] Language pill visible top-right on every step; toggling updates all `[data-i18n]` immediately and persists across step navigation.
- [ ] There is no dedicated "Language" step any more.
- [ ] Step indicator shows 7 pills; completed/current/future states render per § 3.4.
- [ ] All CTAs translate. All step titles translate. All guide bullets translate.
- [ ] Step 1 privacy panel is present; clicking "What gets sent where? →" opens `#privacyModal`.
- [ ] Privacy modal renders the 5-row data-flow table. Esc closes it.
- [ ] Step 2: `How do I get this?` expandable reveals 3 bullets and a "Read full guide" button. Collapsing works. Keyboard accessible (`aria-expanded`).
- [ ] Step 3: `How do I get these?` expandable has 4 bullets, including the redirect-URI copy pill. Clicking the copy button writes the URI to the clipboard and swaps label to `✓ Copied` for 1500 ms.
- [ ] Steps 2 and 3 detail overlays (G1, G2) open, render frontmatter-derived title/subtitle, and display the correct number of steps. "I'm done" button closes them.
- [ ] Step 4: Sign-in flow works as before; status line updates correctly.
- [ ] Step 5: 3 cards render side-by-side on ≥640px, stacked on <640px. Card 1 is visually disabled with a "Coming soon" badge. Card 2 opens the file picker and successfully imports a valid JSON. Card 3 advances to step 6.
- [ ] Step 6: Model dropdown populated from `/api/settings`; changing and clicking Next saves the model.
- [ ] Step 7: Summary rows reflect the actual backend state; amber warning banner shows iff any row is skipped; "Open SpotyVibe →" calls `/api/onboarding/complete` and redirects to `/`.
- [ ] All four smoke tests in § 13 pass under `python -m pytest frontend/tests/test_frontend.py -v`.
- [ ] All twelve screenshot tests in § 12 pass under `python -m pytest frontend/tests/test_documentation_screenshots.py -m screenshots -v -k "onboarding or setup_guide or privacy or rerun"`.
- [ ] `help.md` contains the new "Privacy" section; the existing `24_onboarding_credentials.png` link still resolves.
- [ ] No existing test regresses. Run `python -m pytest core/tests/ frontend/tests/ -v` before declaring done.
- [ ] `[data-i18n]` coverage: grep for new literal strings in `onboarding.html`, `privacy_modal.html`, `setup_guide_overlay.html`. Any English copy outside `i18n` keys is a bug.
- [ ] Responsive: at 390×844 (iPhone 13), the wizard's card is full-width minus 24px side padding; step indicator is visible; CTA remains tappable (≥44px target).
- [ ] `prefers-reduced-motion`: transitions collapse to instant.

---

## 15. Review checklist before merging

- [ ] `documentation/UserManual.md` and `documentation/TechnicalManual.md` updated to mention the wizard re-run entry point (rule 5 in CLAUDE.md).
- [ ] `version.py` bumped (per conventions in CLAUDE.md).
- [ ] Project tree section in `CLAUDE.md` updated if files were added under `frontend/templates/modals/` or `documentation/guides/`.
- [ ] No hardcoded English strings in any new template, JS module, or Python response.
- [ ] No secrets committed (check that the setup-guide markdown examples use placeholder keys, not real ones).
- [ ] Wave 2 surfaces are **not** partially wired here — if you find yourself adding a "profile completeness" calculation, stop.

---

## 16. Reference — surfaces you will touch in Wave 1

| File | Action |
|------|--------|
| `app.py` | Modify — `/onboarding` replay gate; new `/api/help/guide/<slug>` |
| `frontend/templates/base.html` | Modify — include privacy modal |
| `frontend/templates/onboarding.html` | Rewrite |
| `frontend/templates/settings_gear.html` | Modify — add "Re-run setup" item |
| `frontend/templates/modals/privacy_modal.html` | Create |
| `frontend/templates/modals/setup_guide_overlay.html` | Create |
| `frontend/static/css/base.css` | Modify — 3 new tokens |
| `frontend/static/css/onboarding.css` | Create |
| `frontend/static/css/setup_guide.css` | Create |
| `frontend/static/js/modules/onboarding.js` | Create |
| `frontend/static/js/modules/setup_guide.js` | Create |
| `frontend/static/i18n/en.json` | Modify — add keys from § 11 |
| `frontend/static/i18n/de.json` | Modify — add keys from § 11 |
| `documentation/help.md` | Modify — add Privacy section |
| `documentation/guides/openai_api_key.en.md` | Create |
| `documentation/guides/spotify_developer_app.en.md` | Create |
| `documentation/assets/guides/README.md` | Create |
| `documentation/assets/guides/openai/*.png` | Create — placeholder PNGs |
| `documentation/assets/guides/spotify/*.png` | Create — placeholder PNGs |
| `frontend/tests/test_documentation_screenshots.py` | Modify — new tests |
| `frontend/tests/test_frontend.py` | Modify — add 4 smoke tests |

---

## 17. Opening contract for the implementer

You have full autonomy within this Wave 1 scope. Do **not** implement anything outside it. When you believe Wave 1 is done, stop and say "Wave 1 complete — please review". Do not commit, do not push, do not start on Wave 2 — the user will open the next implementation file when ready.
