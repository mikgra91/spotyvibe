# UX Improvement Plan

Consolidated implementation plan. Decisions locked in after feedback round.

---

## 1. Onboarding language selector hidden in Windows app ✅ DONE

**Root cause:** [onboarding.css:34-39](frontend/static/css/onboarding.css#L34-L39)
— `.ob-lang-toggle` uses `position: fixed; top: 16px; right: 24px;`. The
packaged app's 64 px titlebar ([desktop_launcher.py:200](desktop_launcher.py#L200))
covers the top strip.

**Fix:**
```css
.ob-lang-toggle { top: calc(var(--titlebar-h, 0px) + 16px); }
```
`--titlebar-h` is zero in a browser and ~64 px in the app. No JS change.

---

## 2. Notifications/toast hidden behind titlebar ✅ DONE

**Decision locked:** keep titlebar size; make the rest of the app
respect the space it takes.

**Plan:**
- Introduce global token `--safe-top: calc(var(--titlebar-h, 0px) + 12px)`
  in `base.css`.
- Audit every `position: fixed; top:` rule across CSS; replace literal
  pixel offsets with `--safe-top` (or `calc(var(--titlebar-h, 0px) + N)`).
- Known suspects: toast, tip toasts, alerts, completeness card, modal
  overlays, preview overlay.
- Do **not** shrink titlebar.

---

## 3. Centered green "Send" button under "Describe your vibe" ✅ DONE

**Current:** [train_profile.html:154-157](frontend/templates/train_profile.html#L154-L157)
has two action buttons at the bottom of the form, after all accordions.
Users writing only in the Vibe textarea never see them.

**Plan:**
- Add a primary CTA *inside* the Vibe accordion body, below the textarea,
  centered. Uses existing `.btn-run` (green).
- Calls `sendTrainProfile()` (same handler as the bottom button).
- Keep the bottom buttons for users who scroll.

**Decision locked — label:** "Let AI build my profile".
New i18n key: `profile.vibe_cta` in en/de/jp.

---

## 4. Like/dislike in preview not discoverable — superseded by §6 redesign

The original plan (text-labels + first-open pulse on the 👍/👎/✕ tab
trio) is replaced by the §6 button restructure. The three-tab UI goes
away entirely. Discoverability is carried by:

- **Quick 👍/👎 in the new SDK player panel** (§8a) — always visible,
  large, green/red, no form.
- **Feedback / Delete buttons** replacing the tab cluster (§6) —
  explicit labels, no icon ambiguity.

First-open pulse concept is repurposed: on the first preview per
session, pulse the *player's* quick 👍/👎 once with an auto-dismissing
tip ("Rate while it plays"). Reuses `tips.js`. i18n key:
`preview.rate_hint`.

---

## 5. Audio filters UI — "broken / loose collection" ✅ DONE

**Root cause confirmed from screenshot.** [sections.css:821-828](frontend/static/css/sections.css#L821-L828)
defines a 4-column grid, and `.audio-filter-row { display: contents; }`
flattens each row's children into the grid. But each row has **6**
children: `label`, `input min`, `input max`, `hint-text`, `inline-hint`,
`learn-more` (from [generate_section.html:67-74](frontend/templates/generate_section.html#L67-L74)).
With 4 grid columns, 6 children per row → children spill into the next
metric's row, producing the scrambled layout in the screenshot.

**Fix:**
- Drop `display: contents` from `.audio-filter-row`.
- Each row becomes its own grid (label + min + max + hint-text on one
  line; inline-hint + learn-more on a second line spanning the row).
- Grid template:
  ```css
  .audio-filter-row {
      display: grid;
      grid-template-columns: 160px 1fr 1fr minmax(100px, auto);
      grid-template-areas:
          "label min  max  hint"
          "desc  desc desc desc";
      gap: var(--sp-1) var(--sp-2);
      align-items: center;
      padding: var(--sp-2) 0;
      border-bottom: 1px solid var(--border-subtle);
  }
  .audio-filter-row > label         { grid-area: label; }
  .audio-filter-row > input:first-of-type { grid-area: min; }
  .audio-filter-row > input:last-of-type  { grid-area: max; }
  .audio-filter-row .audio-filter-hint-text { grid-area: hint; }
  .audio-filter-row .inline-hint    { grid-area: desc; margin: 0; }
  .audio-filter-row .learn-more     { grid-area: desc; justify-self: end; }
  ```
- Header row (Min | Max | Clear all) keeps current 4-column grid, aligned
  to the same tracks.
- Responsive: below 600 px collapse to single column (label / min / max
  stacked), `inline-hint` under.

---

## 6. Quick like/dislike — button restructure (replaces double-click scheme)

**Why the change:** the originally-locked "click once to submit, click
again within 1.5 s to open the form" pattern is unsafe because Dislike
triggers playlist removal ([preview.js:241-251](frontend/static/js/modules/preview.js#L241-L251)).
A destructive action cannot share a click with a form-opener. Replaced
with an explicit two-surface design:

### Two surfaces for feedback

**Surface 1 — Quick actions inside the SDK player panel (§8a):**
- Large 👍 (green) and 👎 (red) buttons next to the transport controls.
- Submit immediately with empty reason. No form, no confirmation dialog.
- Behavior:
  - **Like:** POST feedback (`action=like`, `reason=null`), advance to
    next preview track, keep the song in the Spotify playlist. Toast:
    "👍 Liked: {track}".
  - **Dislike:** POST feedback (`action=dislike`, `reason=null`), POST
    `/api/remove` to strip from Spotify playlist, advance to next
    preview track. Toast: "👎 Disliked & removed: {track}".

**Surface 2 — Per-track Feedback + Delete buttons (replaces the
👍/👎/🗑 trio on track rows and in the preview chrome outside the
player):**
- **Feedback** button — opens the existing reason panel. Polarity is
  *not* chosen by which button was clicked; instead, the panel shows a
  textarea plus two submit buttons at the bottom:
  - Green **Like** on the left.
  - Red **Dislike** on the right.
  Clicking one submits with the entered reason (or empty). Dislike
  still removes from the Spotify playlist + advances; Like just records
  and advances. Same side-effects as Surface 1, plus the reason text.
- **Delete** button (🗑) — unchanged behavior: remove from the Spotify
  playlist without recording feedback. Current
  [previewDismiss](frontend/static/js/modules/preview.js) path.

### Rationale

- Immediate-action affordance is reserved for the player, where the
  user is actively listening and the polarity is unambiguous.
- Per-row surface defaults to the deliberate path (form) because the
  user is scanning, not listening — quick mis-clicks there have higher
  regret cost.
- No timing window, no hidden second-click behavior. Every click has
  one meaning.

### Files

- [frontend/templates/preview_overlay.html](frontend/templates/preview_overlay.html)
  — replace the `previewTabLike`/`previewTabDislike`/dismiss tab row
  with **Feedback** + **Delete** buttons. Add quick 👍/👎 inside the
  new player panel (defined in §8a).
- [frontend/static/js/modules/preview.js](frontend/static/js/modules/preview.js)
  — remove `togglePreviewFeedbackForm(action)` tab logic; new
  `openFeedbackPanel()` (no polarity arg) and two submit handlers
  `submitLikeWithReason()` / `submitDislikeWithReason()`. Quick-action
  handlers `quickLike()` / `quickDislike()` wired to the player panel.
- [frontend/static/js/modules/feedback.js](frontend/static/js/modules/feedback.js)
  — if track rows use the same pattern, mirror the Feedback/Delete
  restructure here.
- [frontend/static/css/preview.css](frontend/static/css/preview.css) —
  styles for the two submit buttons (green/red) at the bottom of the
  reason panel; styles for the player's quick 👍/👎.
- i18n (en/de/jp): `feedback.open_panel` ("Feedback"),
  `feedback.submit_like` ("Like"), `feedback.submit_dislike`
  ("Dislike"), `feedback.quick_liked_toast`,
  `feedback.quick_disliked_toast`, `preview.rate_hint` (from §4).
  Remove obsolete `feedback.quick_toast_hint`.

**Backend:** no change. `/api/feedback` already accepts `reason=null`
and the separate `/api/remove` call is unchanged.

**Dependency:** this ships with §8a (the new player panel is where
Surface 1 lives). §4 and §6 and §8a are one coupled deliverable.

---

## 7. Delete icon instead of ✕ ✅ DONE

**Decision locked:** reuse existing 🗑 (used by `.playlist-delete-btn`).

**Files:**
- [feedback.js:52](frontend/static/js/modules/feedback.js#L52) — swap
  `✕` → `🗑`.
- [preview_overlay.html:37-39](frontend/templates/preview_overlay.html#L37-L39)
  — swap preview remove button.
- [quickstart-demo.js](frontend/static/js/modules/quickstart-demo.js) —
  update demo track cards (multiple occurrences).
- `frontend/static/i18n/{en,de,jp}.json` — update
  `quickstart.step4_desc`, `step5_desc`, `step4_action5`, `step5_action5`
  to reference the trash icon instead of `✕`.
- Keep `.af-clear-all` as `✕` — it's a "clear all" action, not a delete.

Rename aria-label to something like `feedback.delete_from_playlist`.

---

## 8. Preview player

### 8a. Premium full playback — decision locked: Web Playback SDK, full replacement

**Why not the iframe:** the `open.spotify.com/embed/track/…` iframe relies on
first-party `open.spotify.com` cookies to detect Premium. In packaged
WebViews (WebView2 / WKWebView / WebKitGTK / Android WebView) the cookie
jar is app-isolated — the user has never logged into Spotify there — and
third-party cookie partitioning by top-level site blocks the iframe even
after in-app login. The mechanism is structural, not a cache-bust issue.

**Audience note:** Spotify Free accounts cannot create or modify
playlists via the Web API, so the entire app is Premium-only in
practice. Free-user fallbacks below exist only for degraded runtimes
(e.g. Linux without Widevine), not for a Free-user product path.

**Approach — Web Playback SDK, full UI replacement:**

Load `https://sdk.scdn.co/spotify-player.js` in the top frame, authenticate
it with our existing OAuth token (same flow as playlist CRUD, plus the
`streaming` scope), and render a custom player panel inside
[preview_overlay.html](frontend/templates/preview_overlay.html). The
Spotify iframe is removed for Premium users on supported runtimes.

**Scope:** add `streaming` to the Spotify OAuth scopes in
[core/src/playlist.py](core/src/playlist.py). Existing users will see a
one-time re-consent prompt on next login — acceptable.

**Runtime matrix (Widevine/EME availability):**

| Runtime | SDK playback | Fallback |
|---|---|---|
| WebView2 (Win EXE) | ✅ Widevine bundled with Edge Chromium | — |
| WKWebView (macOS) | ✅ FairPlay via WebKit | — |
| Android WebView (APK) | ✅ Widevine via Android system | — |
| WebKitGTK (Linux wheel) | ⚠️ Widevine CDM rarely installed | iframe embed (30 s) |
| Desktop browsers | ✅ on Chrome/Edge; ✅ Firefox with Widevine; Safari uses FairPlay | iframe embed |

Detection: attempt SDK init; on `initialization_error` or
`account_error`, fall back to the current iframe embed and show a toast
("Full-track playback unavailable on this device — preview only").

**Player UI (custom panel replacing the iframe):**

- Album art (left, ~120 px square) — from `current_track.album.images[0]`.
- Title + artist (stacked, right of art).
- Transport row: prev · play/pause · next (reuse existing preview nav handlers; next/prev still drive `loadTrackByIndex`, not SDK `nextTrack()`, so order follows our suggestion list, not Spotify queue).
- Quick-feedback row (§6 Surface 1): large 👍 (green) · 👎 (red), submit-on-click with empty reason. Dislike also removes from Spotify playlist + advances. Visible in both SDK and iframe fallback modes so the UX is consistent.
- Scrubber: `<input type="range">` bound to `position` / `duration` from `player_state_changed`. Click-to-seek via `player.seek(ms)`.
- Time labels: `m:ss / m:ss`.
- Volume: omit for v1 — desktop OS volume is sufficient; adds UI surface for little gain.

Style lives in [frontend/static/css/preview.css](frontend/static/css/preview.css);
reuse existing `--accent-green`, `--bg-panel`, `--fs-*` tokens. No new
CSS file.

**State flow:**

1. On login success (or app load if token cached), call
   `/api/me` — already exists in playlist.py — and expose `is_premium`
   to the frontend (window bootstrap or a new `/api/session` endpoint).
2. [preview.js](frontend/static/js/modules/preview.js) decides per-open:
   - `is_premium && sdk_available` → render custom panel, connect SDK,
     `player.play({ uris: ['spotify:track:<id>'] })`.
   - otherwise → current iframe embed (unchanged path).
3. Autoplay toggle (8b) still applies: when SDK player reports
   `position === duration` via `player_state_changed`, call our existing
   `nextPreview()` if autoplay is on.
4. Like/Dislike/Remove handlers (items 4, 6, 7) operate on the current
   track metadata regardless of player mode — no change needed.

**Token delivery to the SDK:** SDK calls a `getOAuthToken(cb)` callback
whenever it needs a fresh token. Wire it to a new endpoint
`GET /api/spotify/token` that returns the current access token (refreshed
if needed via existing playlist.py refresh logic). Never embed the token
in HTML.

**Files touched:**

- [core/src/playlist.py](core/src/playlist.py) — add `streaming` scope;
  expose `is_premium` on the session/me response; add token-fetch helper
  for the new endpoint.
- [app.py](app.py) — new `/api/session` (returns `{is_premium}`) and
  `/api/spotify/token` (returns current access token).
- [frontend/static/js/modules/preview.js](frontend/static/js/modules/preview.js)
  — branch on `is_premium`; SDK init + player-state wiring; fallback to
  iframe on SDK error.
- New [frontend/static/js/modules/spotify-sdk.js](frontend/static/js/modules/spotify-sdk.js)
  — SDK loader, `Spotify.Player` lifecycle, `getOAuthToken` callback,
  event → app state bridge. Isolated so preview.js stays readable.
- [frontend/templates/preview_overlay.html](frontend/templates/preview_overlay.html)
  — add the custom player panel markup (hidden by default; shown when
  SDK path is active).
- [frontend/static/css/preview.css](frontend/static/css/preview.css) —
  styles for the custom panel.
- [frontend/static/i18n/en.json](frontend/static/i18n/en.json) + `de.json`
  + `jp.json` — new keys: `preview.sdk_unavailable`, `preview.loading`,
  `preview.play`, `preview.pause`.
- Tests: mock `window.Spotify` in frontend tests; verify branch selection
  on `is_premium` + SDK availability. Core tests cover the new endpoints.

**Out of scope:** volume control, shuffle, queue visualization,
cross-device transfer, lyrics. Add later if asked.

### 8b. Autoplay toggle ✅ DONE

- [preview.js:71](frontend/static/js/modules/preview.js#L71) already
  passes `autoplay=true`.
- Add a checkbox under the iframe: `☑ Autoplay next track`. Default on.
- Persist in `localStorage` (`spv_preview_autoplay`).
- When unchecked, update iframe `src` without DOM replacement so the
  user retains the play button.
- i18n key: `preview.autoplay`.

---

## 9. Onboarding overflows on 13" Windows screens + global UI scale option

**Reported issue:** on a 13" laptop the packaged Windows app forces
constant scrolling through the onboarding wizard. Users should see each
step "as one picture," not a scroll column.

**Diagnosis (root causes in current CSS):**
- [onboarding.css:5-11](frontend/static/css/onboarding.css#L5-L11) —
  `.ob-wrap` is `100vh - titlebar-h` tall, but the content inside each
  `.ob-page` is not vertically budgeted, so it overflows.
- [onboarding.css:90-98](frontend/static/css/onboarding.css#L90-L98),
  [onboarding.css:100-106](frontend/static/css/onboarding.css#L100-L106)
  — fixed pixel / rem values for icon (`2.8rem`), title (`1.75rem`),
  subtitle max-width (`360px`) don't respond to viewport *height*.
- [onboarding.css:66-76](frontend/static/css/onboarding.css#L66-L76) —
  `--ob-card-padding: 32px 24px` (defined in [base.css:61-62](frontend/static/css/base.css#L61-L62))
  is fixed; 32 px top + 32 px bottom eats ~8 % of a 720-px viewport.
- [onboarding.css:458-467](frontend/static/css/onboarding.css#L458-L467)
  — `.ob-seed-card { min-height: 180px }` × 3-col grid on Step 6 alone
  contributes ~180 px of vertical space.
- Typical 13" laptop: 1280×800 native, minus Windows taskbar (~48 px),
  minus browser/WebView chrome, minus our 64-px titlebar → effective
  viewport height **~620–680 CSS px**. Current onboarding is designed
  for ≥ 800 px.

### Research — design patterns (2026)

Four complementary techniques turned up in recent guides; cheapest to
most invasive:

**(a) Fluid typography with `clamp()`** — scales sizes continuously
between min/max based on viewport, no media query thresholds. Standard
recommendation in [MDN / BrowserStack responsive-sizing guides](https://www.browserstack.com/guide/responsive-css-size).
Fits SpotyVibe's existing token system — `--fs-*` and `--ob-icon`
become `clamp(min, preferred, max)` expressions keyed off `vh`.

**(b) Short-viewport media queries** — `@media (max-height: 720px)`
overrides for vertical padding, icon size, grid row heights. Precedent:
every major SaaS onboarding (Stripe, Notion, Linear) ships a compact
variant at short heights. Minimal risk because it's additive.

**(c) Container queries** — `@container (max-height: …)` lets a
component adapt to its own box rather than the viewport. 95 %+ browser
coverage as of 2026 per [LogRocket](https://blog.logrocket.com/container-queries-2026/).
Overkill for a full-screen wizard (the card already fills the
viewport), but useful later for seed cards / summary rows.

**(d) User-configurable UI scale** — "small / medium / large" or a
slider. WCAG 1.4.4 already requires content to survive 200 % text
zoom ([a11y-collective](https://www.a11y-collective.com/blog/accessible-ux-design/)),
but a discoverable in-app toggle is standard in Slack, VS Code,
Figma, and Windows Settings. Implementation pattern: a CSS custom
property (`--ui-scale`) on `:root` multiplied into `--fs-*` and
`--sp-*` via `calc()`, persisted to `localStorage`.

### Decision — recommended plan

**Phase 1 — fix the 13" report (no new UI surface):** ✅ DONE
1. Introduce a viewport-aware `--ob-scale` token defined as
   `clamp(0.82, calc(100vh / 880), 1)` on `.ob-wrap`. Multiplies into
   the onboarding-only size tokens below. Equals `1` on ≥ 880 px, floors
   at `0.82` on very short screens.
2. Convert onboarding-specific magnitudes to scaled variants:
   ```css
   .ob-wrap {
       --ob-icon-fs: calc(2.8rem * var(--ob-scale));
       --ob-title-fs: calc(1.75rem * var(--ob-scale));
       --ob-card-pad-y: calc(24px * var(--ob-scale));
       --ob-gap: calc(var(--sp-3) * var(--ob-scale));
       --ob-seed-min-h: calc(180px * var(--ob-scale));
   }
   .ob-icon { font-size: var(--ob-icon-fs); }
   .ob-title { font-size: var(--ob-title-fs); }
   .ob-card { padding: var(--ob-card-pad-y) 24px; }
   .ob-seed-card { min-height: var(--ob-seed-min-h); }
   ```
3. Add a short-viewport guard for items that don't scale well via
   `calc()` (e.g. 2-column fallback for the 3-col seed grid at Step 6):
   ```css
   @media (max-height: 680px) {
       .ob-seed-grid { grid-template-columns: repeat(2, 1fr); }
       .ob-feature { margin-bottom: var(--sp-2); }
       .ob-subtitle { margin-bottom: var(--sp-2); }
   }
   ```
4. Remove `justify-content: center` on `.ob-page` at short heights so
   content starts from the top (already scrolls if it must, but stops
   floating below the viewport when it barely fits).

Expected impact: Step 6 (densest step — 3 seed cards @ 180 px each)
drops from ~820 px intrinsic height to ~690 px on a 620 px viewport,
still needs a few scroll pixels but no longer "constant scrolling."
Other steps fit without scroll.

**Phase 2 — global UI scale preference (separate commit, opt-in):**
5. Add a single setting in the Settings modal: radio group
   **Compact / Normal / Large** (0.9 / 1.0 / 1.1). Do *not* ship as
   a slider — three discrete presets are easier to label, test, and
   translate.
6. Implementation:
   - Write `--ui-scale` on `:root` from JS on load.
   - Extend `base.css` font-size tokens to `--fs-md: calc(0.9rem * var(--ui-scale, 1))`
     etc. Do NOT apply to `--sp-*` by default — scaling both space *and*
     text together feels like browser zoom and conflicts with the Phase
     1 `--ob-scale`. Text-only scaling aligns with WCAG 1.4.4.
   - Persist in `localStorage` (`spv_ui_scale`).
   - i18n: `settings.ui_scale.label`, `settings.ui_scale.compact`,
     `settings.ui_scale.normal`, `settings.ui_scale.large`.
7. Do not couple to onboarding `--ob-scale`. The two systems solve
   different problems (viewport-fit vs. user preference) and should
   compose multiplicatively only if the user explicitly asks for that
   later.

**Why not just rely on browser/Ctrl-+ zoom?**
- WebView2 in the packaged desktop app doesn't expose Ctrl-+ consistently.
- Users don't discover it.
- Browser zoom scales *everything* including layout breakpoints, which
  can trigger mobile layouts unintentionally.

**Out of scope for this round:** container queries (Phase 1 fluid
tokens already solve the onboarding case); dynamic density mode
coupled to window size (adds state, test matrix, and edge cases for
resize mid-wizard).

### Files touched

Phase 1 only:
- [frontend/static/css/onboarding.css](frontend/static/css/onboarding.css)
  — add `--ob-scale`, rewrite ~8 size rules, add `@media (max-height)`
  block.
- No JS change, no new i18n keys.

Phase 2 (deferred):
- `frontend/static/css/base.css` — wrap `--fs-*` tokens in `calc(* var(--ui-scale, 1))`.
- `frontend/templates/settings_modal.html` or equivalent — add radio group.
- `frontend/static/js/modules/settings.js` (or wherever) — read/write
  `localStorage` + apply to `document.documentElement.style`.
- `frontend/static/i18n/{en,de,jp}.json` — 4 new keys.

---

## Implementation order (cheap wins first)

1. **Safe-top offset** (items 1, 2) — new `--safe-top` token, replace
   literal top offsets.
2. **Trash icon swap** (item 7) — `✕` → 🗑 in feedback + preview + demo;
   sync i18n strings.
3. **Vibe CTA button** (item 3) — "Let AI build my profile" inside the
   accordion, centered.
4. **Audio filters rebuild** (item 5) — drop `display: contents`, grid
   per row with named areas.
5. **Preview + player overhaul** (items 4, 6, 8 — one coupled commit
   set): autoplay toggle (8b, done), Web Playback SDK player panel (8a),
   quick 👍/👎 inside the player, Feedback + Delete button restructure
   on track rows, first-open rate hint via `tips.js`.
6. **Onboarding fluid scaling** (item 9, Phase 1) — CSS-only, no new
   UI surface, fixes the 13" report.
7. **Global UI scale preference** (item 9, Phase 2) — Settings modal
   radio + `--ui-scale` token, opt-in.

Each step is one commit with en/de/jp i18n sync where applicable. Tests
(pytest + frontend Playwright) run per commit.
