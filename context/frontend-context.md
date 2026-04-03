# Frontend Context Summary

Generated: 2026-04-03

---

## Architecture

Single-page vanilla HTML/CSS/JavaScript application served by Flask via Jinja2 templates. No frontend framework — uses ES modules for code organization. The entry point is `frontend/static/js/main.js`, which imports all feature modules, exposes functions to `window` for `onclick=` handlers in HTML, and runs initialization on `DOMContentLoaded`.

Templates are Jinja2 partials composed via `{% include %}` directives in `base.html`. The CSS is a single 2500-line stylesheet (`frontend/static/css/styles.css`) implementing a premium dark glass design system. Internationalization is handled client-side via JSON translation files.

---

## File Map

### Templates (`frontend/templates/`)

| Template | Purpose |
|---|---|
| `base.html` | Root layout. Includes all partials, loads fonts (Inter), CSS, and `main.js` as ES module. Defines the two provider sections (OpenAI, Spotify) and the overall page skeleton. |
| `onboarding.html` | Standalone 3-page swipeable welcome flow: intro, credentials entry, Spotify connect + profile import. Has its own inline `<style>` block. Rendered at `/` when onboarding is not completed. |
| `train_profile.html` | Music Profile editor partial. Five accordion panels: Describe Your Vibe, Core Description (required unless vibe is set), Must Have, Soft Preferences, Avoid. Profile import/export/reset buttons. Two save paths: direct Save and AI Profile Update. |
| `band_analysis.html` | AI band/song analysis partial. Artist + track inputs, Analyse button, results area rendered by JS. |
| `generate_section.html` | Playlist generation partial. Playlist mode radio buttons (default/create/append/replace), playlist name input or picker, dependency status chips, Generate + Cancel + "Use X tracks now" buttons. |
| `tracklist.html` | Track list partial. Server-rendered initial list + JS-rendered updates. Each track has cover image, Spotify/artist/album links, Like/Dislike/Remove buttons, expandable feedback form. Song list counter. |
| `run_history.html` | Run history partial. Collapsible list of past runs with dates, track counts, playlist links. Undo button for latest run. |
| `preview_overlay.html` | Spotify embed iframe overlay for track preview. Bottom-sheet pattern. |
| `toast.html` | Toast notification element (fixed bottom-center). |
| `settings_gear.html` | Header controls: EN/DE language toggle pills + burger menu with dropdown (Credentials, Settings, Connect/Disconnect Spotify, Help). |
| `theme_switcher.html` | Theme pill buttons: Equalizer and Pulse. |
| `spotify_metadata.html` | Spotify metadata lookup form (deprecated — UI exists but no backend endpoint is exposed). Artist/track inputs + market region selector. |
| `modals/credentials_modal.html` | Credentials modal. Three fields: OpenAI API Key, Spotify Client ID, Spotify Client Secret. Each has set/unset status indicator and clear button. |
| `modals/settings_modal.html` | Settings modal. Model dropdown (lazy-loaded from `/api/settings/models`), Playlist Size, New Artist %, GPT Language, Debug Mode (desktop only). Cost warning link. Loading spinner overlay. |
| `modals/help_modal.html` | Help modal. Content loaded from `/api/help` endpoint, sanitized and rendered as HTML. Close button outside the modal frame. |

### JavaScript Modules (`frontend/static/js/modules/`)

| Module | Key Exports | Responsibility |
|---|---|---|
| `state.js` | `suggestions`, `spotifyAuthStatus`, `openaiKeySet`, `profileTrained`, `selectedModel`, `gptLanguage`, `isGenerating`, `partialTrackCount`, `currentRunId`, `currentAbortController`, `helpLoaded`, etc. + setters | Central mutable state store. All UI state lives here. No persistence — reset on page reload. |
| `auth.js` | `checkCredentialStatus()`, `checkSpotifyAuth()`, `connectSpotify()`, `toggleSpotifyConnection()`, `fetchSettingsState()` | Fetches credential/auth/settings status from backend, updates state. Spotify auth uses popup (desktop) or redirect (Android WebView detected via `/; wv\)/` user-agent pattern). |
| `warnings.js` | `renderComponentWarnings()` | Reads state and shows/hides inline warning banners for missing OpenAI key, missing Spotify credentials, or unauthenticated Spotify. Disables Generate and Train buttons accordingly. |
| `profile.js` | `toggleAccordion()`, `prefillTrainFields()`, `updateTrainToggleLabel()`, `toggleTrainBody()`, `startImportProfile()`, `exportProfile()`, `submitProfile()`, `sendTrainProfile()`, `saveProfileDirect()`, `resetProfileToHistory()`, `bindProfileImportInput()`, `checkProfileStatus()` | Profile editor logic. Prefills fields from `GET /api/profile/data`. Two save paths: direct save (`POST /api/save-profile`) and AI training (`POST /api/train-profile`). Core description required unless vibe description is filled. Import via file input, export via download link. |
| `analysis.js` | `toggleAnalysisBody()`, `runAnalysis()`, `renderAnalysisResult(data)`, `copySuggestion(idx)` | Sends `POST /api/analyze`, renders structured result card with genre tags, characteristics table, GPT-estimated audio feature bars (percentage bar visualization), and copyable profile suggestions. |
| `pipeline.js` | `toggleGenerateBody()`, `runPipeline()`, `setGenerating()`, `updateUseTracksButton()`, `generateUUID()`, `handleStreamEvent()`, `showSseDisconnectBanner()`, `resumeRun()`, `cancelGeneration()`, `useCurrentTracks()`, `canGenerate()` | Core generation pipeline. Pre-checks credentials/auth/profile state. Sends `POST /api/run` with playlist mode + audio filters, reads SSE stream via ReadableStream API. Handles event types: `progress`, `batch_verified`, `result`, `cancelled`, `error`. Cancel sends `POST /api/cancel` with `finalize: false` + AbortController. "Use X tracks now" sends `finalize: true` without aborting the reader. SSE disconnect shows resume banner. |
| `audio-filters.js` | `toggleAudioFilters()`, `getAudioFilters()` | Reads audio filter number inputs (energy, valence, tempo, danceability, acousticness), returns a filter dict `{feature: {min, max}}` or `null` if no filters set. |
| `playlist-mode.js` | `getPlaylistMode()`, `onPlaylistModeChange()`, `getPlaylistModePayload()` | Reads radio button selection. Shows/hides playlist name input (for "create") or playlist picker dropdown (for "append"/"replace"). Lazy-loads user playlists from `GET /api/playlists` on first expand. Returns `{playlist_mode, playlist_name?, playlist_id?}`. |
| `tracklist.js` | `renderTracks()` | Clears and rebuilds `#trackList` from `State.suggestions`. Each track gets: album cover, preview button (if preview_url), Spotify/artist/album links, Like/Dislike/Remove buttons, expandable feedback form. All output is XSS-escaped via `esc()` and `attr()`. Updates song list counter. |
| `preview.js` | `togglePreview(idx)`, `openPreviewOverlay(url, title)`, `closePreviewOverlay()` | Audio preview playback via `<audio>` elements. Only one preview plays at a time. Preview overlay uses Spotify embed iframe. |
| `feedback.js` | `toggleFeedback(idx, action)`, `closeFeedback(idx)`, `submitFeedback(idx)`, `removeTrack(idx)`, `animateRemove(idx)` | Per-track feedback forms. Submit sends `POST /api/feedback` with action/artist/track/reason. Remove sends `POST /api/remove`. Both animate the track out (opacity + translateX transition, then DOM removal). Also sends `DELETE /api/songlist/track` to remove from persistent song list. |
| `ui.js` | `showStatus()`, `showStatusHtml()`, `showPlaylistLink()`, `hidePlaylistLink()`, `esc()`, `attr()`, `sanitizeHtml()`, `escHtml()`, `toggleSettingsMenu()`, `showToast()` | Core UI utilities. `esc()` uses textContent/innerHTML for safe text escaping. `attr()` escapes for HTML attributes. `sanitizeHtml()` is a DOM-based allowlist sanitizer (strips disallowed tags/attributes, blocks `javascript:` hrefs). Toast auto-hides after configurable duration. |
| `modals.js` | `openCredentials()`, `saveCredentials()`, `clearCredential()`, `saveSettings()`, `openSettings()`, `openHelp()`, `openSectionHelp()`, `closeSectionHelp()`, `closeModal()` | All modal open/close logic. Credentials: fetches current status, saves non-empty fields. Settings: fetches current values, lazy-loads model list from `/api/settings/models`, saves all changed fields. Help: fetches from `/api/help`, sanitizes HTML, caches after first load. Section help: fetches from `/api/help/section/{anchor}`. |
| `theme-switcher.js` | `switchTheme(name)`, `THEME_BACKGROUNDS`, `THEME_RENDERERS` | Theme switching orchestrator. Sets `body.className` to `theme-{name}`, replaces canvas in `#themeBackground`, starts renderer's `requestAnimationFrame` loop, stops previous loop via returned cleanup function. Handles window resize. Persists to `localStorage` key `spotyvibe-theme`. |
| `theme-equalizer.js` | (side-effect: registers `THEME_RENDERERS.equalizer`) | 56-bar spring-physics equalizer canvas animation. Bars have gradient colors (green→teal→blue→purple→pink), rounded tops, per-bar glow, wave-based target heights with beat simulation (random center+spread bursts). Spring constant 0.08, damping 0.78. |
| `theme-pulse.js` | (side-effect: registers `THEME_RENDERERS.pulse`) | Ring pulse canvas animation. 5 emitters, 120-slot ring pool, 60 floating particles. Features: breathing ambient glow, bass-drop bursts (2–3 emitters × 3–6 rings), soft/crisp ring variants, vignette overlay. Color palette: green, teal, blue, purple, violet, pink. |
| `i18n.js` | `switchLanguage(lang)`, `applyLanguage(lang)`, `i18n(key, fallback)`, `_i18nStrings`, `initI18n()` | Client-side i18n. Loads `/static/i18n/{lang}.json`, applies to elements via `data-i18n` (textContent), `data-i18n-placeholder`, `data-i18n-title` attributes. Saved in `localStorage` key `svLang`. Auto-detects browser language on first visit (German → 'de', else 'en'). |
| `spotify-metadata.js` | `renderProviderPills()` | Renders status pills in both provider section headers: OpenAI (key status, profile status, model, language) and Spotify (connection status). Also renders dependency chips (green/amber dots) in the generate section. |

### Stylesheet (`frontend/static/css/styles.css`)

**2513 lines.** Single stylesheet implementing a premium dark glass design system.

#### Design Tokens (CSS Custom Properties)

| Category | Key Variables |
|---|---|
| Backgrounds | `--bg-main: #050608`, `--bg-deep: #0b0f14`, `--bg-card: #151b22`, `--bg-elevated: #1b212a`, `--bg-input: #0f1318` |
| Text | `--text-primary: #f4f7fb`, `--text-secondary: #b5bfd0`, `--text-muted: #6B7280` |
| Primary | `--primary: #1ed760`, `--primary-hover: #24f06b`, `--primary-dark: #11b84c` |
| Accents | `--accent-teal: #19d3c5`, `--accent-cyan: #4ca8ff`, `--accent-purple: #8c3dff`, `--accent-violet: #b14dff`, `--accent-pink: #ff4db8` |
| Semantic | `--success: #22C55E`, `--error: #EF4444`, `--warning: #F59E0B` |
| Glow | `--glow-green`, `--glow-teal`, `--glow-purple` (partial-opacity rgba values) |
| Borders | `--border: rgba(255,255,255,0.07)` |
| Radius | `--radius-sm: 12px`, `--radius-md: 18px`, `--radius-lg: 24px`, `--radius-pill: 999px` |
| Glass | `--glass-bg` (linear-gradient 85–90% opacity), `--glass-blur: blur(16px)`, `--glass-border` |
| Shadows | `--shadow-card` (multi-layer + inset highlight), `--shadow-elevated`, `--shadow-card-hover` |
| Focus | `--focus-glow` (3px green ring + 20px halo) |
| Transition | `--transition: 200ms ease` |

#### Visual Design System

- **Background:** Layered radial gradients (green glow top, purple glow bottom) over near-black base. `body::after` vignette (inset box-shadow).
- **Glass panels:** Semi-transparent gradient backgrounds with `backdrop-filter: blur(16px)`. Used for all cards, sections, modals, dropdowns, toasts, status messages.
- **Typography:** Inter font (400–800 weight). Title: 2.8rem/800 with dual-layer green text-shadow glow. Section labels: `--accent-pink` uppercase.
- **Buttons:** Primary CTA — green gradient with inset highlight and triple-layer glow shadow, pill-shaped (18px 40px). On hover: scale 1.02× + intensified glow. Secondary: dark glass with subtle borders. Cancel: red. Use tracks: green outline.
- **Inputs:** Dark background (`--bg-input`), 3px focus ring with glow halo.
- **Custom scrollbar:** 6px thin, dark, cross-browser (WebKit + Firefox).
- **Accessibility:** `prefers-reduced-motion` disables all animations/transitions. `:focus-visible` shows 2px green outline.

#### Component Styles

| Component | Key CSS Classes | Notes |
|---|---|---|
| Provider sections | `.provider-section`, `.provider-openai`, `.provider-spotify` | Outer wrapper cards with colored borders |
| Status pills | `.status-pill`, `.status-pill--ok/warn/err` | Colored dot + text, pill-shaped |
| Dependency chips | `.dep-chip`, `.dep-dot--ok/warn/unknown` | Small indicators in generate section |
| Section panels | `.train-section`, `.generate-section`, `.analysis-section`, `.history-section` | Shared glass panel (radius-lg, padding 32px 28px) |
| Collapsible sections | `.train-header` (flex, clickable), `.train-body.hidden` | Toggle via `.hidden` class |
| Accordion panels | `.accordion-panel`, `.accordion-panel.open` | CSS `max-height` transition for expand/collapse |
| Track items | `.track-item` | Glass panel with cover, info, actions. Hover: translateY(-2px) |
| Feedback forms | `.feedback-form`, `.feedback-form.open` | `display: none` → `display: block` |
| Modals | `.modal-overlay.open`, `.modal` | Backdrop blur, centered. On phone: bottom-sheet pattern |
| Help modal | `.help-modal-wrapper`, `.help-modal`, `.help-content` | Markdown rendering styles for h1–h4, lists, tables, code, blockquotes |
| Section help | `.section-help-wrapper`, `.section-help-popup`, `.section-help-icon` | "?" button opens focused help popup |
| Toast | `.toast.show` | Fixed bottom-center, slide-up animation |
| Settings dropdown | `.settings-dropdown.open` | Absolute positioned below burger |
| Language toggle | `.lang-toggle`, `.lang-toggle-btn.active` | Active button gets green background |
| Theme switcher | `.style-switcher-btn.active` | Active button gets green border/shadow |
| Audio filters | `.audio-filter-grid`, `.audio-filter-row` | CSS grid with `display: contents` rows |
| Analysis result | `.analysis-card`, `.analysis-tag`, `.analysis-ch-table` | Result card with tags, characteristics table |
| Audio feature bars | `.af-grid`, `.af-row`, `.af-bar-track`, `.af-bar-fill` | Horizontal bar chart visualization |
| Playlist mode | `.playlist-mode-row`, `.playlist-mode-option` | Radio buttons + conditional name/picker rows |
| Preview overlay | `.spotify-preview-overlay`, `.spotify-preview-panel` | Bottom sheet with iframe embed |
| Onboarding | `.onboarding-body`, `.onboarding-card`, `.onboarding-continue-btn` | Standalone page with different body class |
| Component warnings | `.component-warn` | Amber background, warning text |
| Buttons | `.btn-run`, `.btn-run-cancel`, `.btn-use-tracks`, `.btn-train`, `.btn-profile-io`, `.btn-preview` | Various button styles |

#### Responsive Breakpoints

| Breakpoint | Target | Key Changes |
|---|---|---|
| `≤ 768px` | Tablet | Reduced padding, smaller headings, wrapping track actions, smaller modals |
| `≤ 480px` | Phone | Minimal padding, vertical button stacking, full-width bottom-sheet modals, 44px min touch targets, stacked train header/actions, collapsed audio filter grid |
| `≤ 600px` | Small screens | Provider section padding reduced, stacked provider header, narrower meta-grid |

### i18n Files (`frontend/static/i18n/`)

| File | Language | Keys |
|---|---|---|
| `en.json` | English | 98 lines, ~70 translation keys |
| `de.json` | German | 98 lines, same key set |

Key namespaces: `nav.*`, `app.*`, `section.*`, `profile.*`, `btn.*`, `analysis.*`, `settings.*`, `history.*`, `feedback.*`, `msg.*`, `provider.*`, `pill.*`, `audio_filters.*`, `warn.*`, `help.*`.

---

## Page Layout Structure

```
body.theme-{equalizer|pulse}
├── .background#themeBackground
│   └── canvas (theme-specific animation)
├── .container (max-width: 960px, centered)
│   ├── .header-controls (absolute top-right)
│   │   ├── .lang-toggle (EN | DE)
│   │   └── .burger-wrapper
│   │       ├── button.burger-btn (3 lines)
│   │       └── .settings-dropdown (Credentials/Settings/Spotify/Help)
│   ├── h1 "SpotyVibe"
│   ├── p.subtitle
│   ├── .style-switcher (Equalizer | Pulse)
│   │
│   ├── section.provider-section.provider-openai
│   │   ├── .provider-header (badge + subtitle + #openaiStatusPills)
│   │   ├── .train-section (Music Profile)
│   │   │   ├── .train-header (title + status + toggle btn + import/export/reset)
│   │   │   ├── #trainWarn (warning banner)
│   │   │   └── .train-body (5 accordion panels + Save/AI Update/Cancel buttons)
│   │   ├── .analysis-section#analysisSection (Band/Song Analysis)
│   │   │   ├── .train-header
│   │   │   └── .train-body (artist/track inputs + Analyse btn + result area)
│   │   └── .analysis-section#audioFiltersSection (Audio Filters)
│   │       ├── .train-header
│   │       └── .train-body (5 filter rows: energy, valence, tempo, danceability, acousticness)
│   │
│   ├── section.provider-section.provider-spotify
│   │   ├── .provider-header (badge + subtitle + #spotifyStatusPills)
│   │   ├── .generate-section (Playlist Creation)
│   │   │   ├── .train-header
│   │   │   └── .train-body
│   │   │       ├── .playlist-mode-row (radio + name input / playlist picker)
│   │   │       ├── .generate-deps-row (OpenAI + Spotify dependency chips)
│   │   │       ├── .run-section (#runBtn + #cancelBtn + #useTracksBtn)
│   │   │       └── #runWarn (warning banner)
│   │   └── .history-section (Run History)
│   │       ├── .train-header (+ Undo button)
│   │       └── .train-body → #historyList
│   │
│   ├── #statusBox (generation progress/result messages)
│   ├── #playlistLinkBox (playlist URL after generation)
│   ├── .songlist-counter-row (#songlistCounter "X / 100 songs")
│   ├── ul#trackList (track items with Like/Dislike/Remove + feedback forms)
│   ├── #spotifyPreviewOverlay (Spotify embed iframe bottom sheet)
│   ├── #toast (notification)
│   ├── #credentialsModal
│   ├── #settingsModal
│   ├── #helpModal
│   └── #sectionHelpOverlay (focused single-section help popup)
│
└── body::after (vignette overlay, z-index 9999)
```

---

## Theme System

Two canvas-based background themes, switchable at runtime via pill buttons.

| Theme | Canvas ID | Renderer | Visual Description |
|---|---|---|---|
| **Equalizer** | `equalizerCanvas` | `theme-equalizer.js` | 56 bars with spring-physics animation, gradient colors (green→purple), rounded tops, per-bar glow, beat bursts. 3-layer wave target function. |
| **Pulse** | `pulseCanvas` | `theme-pulse.js` | 5 emitters spawning expanding rings (120-slot pool), 60 floating particles, breathing ambient glow, bass-drop burst events. Soft/crisp ring variants. |

**Switching flow:**
1. `switchTheme(name)` stops current animation loop via cleanup function
2. Sets `body.className = 'theme-{name}'`
3. Replaces `#themeBackground` innerHTML with new `<canvas>`
4. Starts new `requestAnimationFrame` loop via `THEME_RENDERERS[name](canvas)`
5. Attaches resize handler, wraps cleanup to also remove handler
6. Updates active pill button styling
7. Persists to `localStorage` key `spotyvibe-theme`

---

## Interaction Patterns

### Section Expand/Collapse
All major sections use a common pattern: `.train-header` (clickable) toggles `.hidden` class on `.train-body`. Toggle buttons update their label text. The entire header background is clickable; buttons inside use `event.stopPropagation()`.

### Accordion Panels (Profile Editor)
Profile editor sections use `.accordion-panel` with `.open` class toggle. Expansion is animated via CSS `max-height` transition (0 → 500px). Chevron rotates 180° on open.

### Modal System
Modals use `.modal-overlay` with `.open` class for visibility. Overlay click-to-close via `onclick="if(event.target===this)closeModal('id')"`. Backdrop has `blur(6px)`. On phones (≤480px), modals become bottom sheets (`align-items: flex-end`, top border-radius only).

### SSE Pipeline
Generation uses `POST /api/run` returning `text/event-stream`. The client reads via `ReadableStream` API with manual `\n\n` boundary parsing. Events: `progress` (status update), `batch_verified` (updates "Use X tracks now" button), `result` (final playlist), `cancelled`, `error`. Cancel uses `AbortController.abort()`. SSE disconnect shows a resume banner with run ID.

### Feedback
Per-track expandable forms with like/dislike action preselection. Submit sends artist/track/reason to `POST /api/feedback`. On success, track animates out (opacity 0 + translateX 40px, then DOM removal after 300ms). Remove tracks send `POST /api/remove` and also delete from song list.

### Profile Save
Two paths:
1. **Direct Save** (`saveProfileDirect`) → `POST /api/save-profile` — no AI processing
2. **AI Profile Update** (`sendTrainProfile`) → `POST /api/train-profile` — sends through GPT

Both validate that either vibe description or core description is non-empty. After success, body collapses and status updates.

### Spotify Auth
Desktop: `window.open()` popup to `/api/spotify/auth`. On auth completion, popup posts `'spotify-auth-complete'` message to opener.
Android (WebView detected via `/; wv\)/`): Direct `window.location.href` redirect to `/api/spotify/auth`.

### Toast Notifications
`showToast(message, type, duration)` — shows fixed bottom-center notification. Auto-hides after `duration` (default 3000ms). Types: `success`, `error`, `info`.

---

## State Management

All UI state lives in `state.js` as module-level `let` variables with setter functions. Key state:

| Variable | Type | Purpose |
|---|---|---|
| `suggestions` | Array | Current track list after generation |
| `openFormIndex` / `openFormAction` | number/string | Currently open feedback form |
| `spotifyAuthStatus` | string | `'unknown'`, `'authenticated'`, `'not_authenticated'`, `'not_configured'` |
| `openaiKeySet` | boolean | Whether OpenAI API key is configured |
| `profileTrained` | boolean | Whether taste profile has been trained |
| `selectedModel` | string | Currently configured OpenAI model |
| `gptLanguage` | string | Configured GPT response language |
| `isGenerating` | boolean | Whether generation pipeline is active |
| `partialTrackCount` | number | Verified tracks so far (for "Use X now" button) |
| `currentRunId` | string | UUID of current generation run |
| `currentAbortController` | AbortController | For SSE cancellation |
| `helpLoaded` | boolean | Help content cache flag |
| `historyBodyOpen` | boolean | Whether run history section is expanded |

---

## API Communication

All backend communication uses the Fetch API. Endpoints called from frontend:

| Endpoint | Method | Called From | Purpose |
|---|---|---|---|
| `/api/settings/credentials` | GET | `auth.js`, `modals.js` | Check credential status |
| `/api/settings/credentials` | POST | `modals.js` | Save/clear credentials |
| `/api/spotify/status` | GET | `auth.js` | Check Spotify auth state |
| `/api/spotify/auth` | GET | `auth.js` | Initiate Spotify OAuth |
| `/api/spotify/disconnect` | POST | `auth.js` | Clear Spotify token |
| `/api/settings` | GET/POST | `auth.js`, `modals.js` | Read/write settings |
| `/api/settings/models` | GET | `modals.js` | List available OpenAI models |
| `/api/profile/status` | GET | `profile.js` | Check if trained + last_updated |
| `/api/profile/data` | GET | `profile.js` | Get full profile for prefilling |
| `/api/profile/export` | GET | `profile.js` | Download profile JSON |
| `/api/profile/import` | POST | `profile.js` | Import profile JSON |
| `/api/profile/reset-to-history` | POST | `profile.js` | Swap profile with backup |
| `/api/train-profile` | POST | `profile.js` | AI-assisted profile training |
| `/api/save-profile` | POST | `profile.js` | Direct profile save |
| `/api/analyze` | POST | `analysis.js` | Band/song AI analysis |
| `/api/run` | POST | `pipeline.js` | Start generation (SSE stream) |
| `/api/cancel` | POST | `pipeline.js` | Cancel/finalize generation |
| `/api/run/{id}/status` | GET | `pipeline.js` | Check run state for SSE recovery |
| `/api/feedback` | POST | `feedback.js` | Submit like/dislike |
| `/api/remove` | POST | `feedback.js` | Remove track from playlist |
| `/api/songlist/track` | DELETE | `feedback.js` | Remove from song list |
| `/api/playlists` | GET | `playlist-mode.js` | List user's Spotify playlists |
| `/api/runs` | GET | `history.js` | Load run history |
| `/api/runs/undo` | POST | `history.js` | Undo last run |
| `/api/help` | GET | `modals.js` | Load help content |
| `/api/help/section/{anchor}` | GET | `modals.js` | Load section-specific help |
| `/api/onboarding/status` | GET | (server-side) | Check onboarding completion |
| `/api/onboarding/complete` | POST | `onboarding.html` | Mark onboarding done |
| `/static/i18n/{lang}.json` | GET | `i18n.js` | Load translation strings |

---

## Security Measures (Frontend)

- **XSS prevention:** `esc()` uses `textContent`/`innerHTML` round-trip for safe text escaping. `attr()` escapes all HTML-special characters for attribute contexts. `sanitizeHtml()` is a DOM-based allowlist sanitizer (strips disallowed tags/attributes, blocks `javascript:` URLs).
- **Input validation:** Core description required check (client-side). File size check on profile import (10MB max before upload). Maxlength attributes on text inputs (200 chars).
- **Content Security:** Help content from `/api/help` is passed through `sanitizeHtml()` before DOM insertion. Allowed tags: heading, paragraph, list, link, code, table, blockquote, image, etc. Allowed attributes limited per tag.
