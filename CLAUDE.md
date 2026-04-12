# CLAUDE.md — SpotyVibe

> ## 🔴🔴🔴 ABSOLUTE RULE — READ BEFORE ANYTHING ELSE
>
> **NEVER run `git commit`, `git push`, or any command that creates commits or pushes to a remote.**
>
> The ONLY exception: the user has **explicitly told you** to commit/push **in the current message** (e.g., "commit this", "perform a segmented commit and push"). Even then, permission covers **that one operation only** — once done, permission is revoked.
>
> - Editing, fixing, planning, or reviewing code is **NEVER** implicit permission to commit.
> - When in doubt: **do NOT commit. Ask the user.**
> - There are **zero exceptions** to this rule.

AI-powered music discovery: Flask + OpenAI + Spotify Web API.
Read `SKILL.md` before any Spotify API change. Read `RULES.md` for a11y and detailed conventions.

## Build & Run

```bash
python app.py                                        # http://127.0.0.1:5000
python -m pytest core/tests/ frontend/tests/ -v      # run tests (required before completing code changes)
bash build-tools/build_exe.sh                        # PyInstaller Windows EXE
bash build-tools/build_apk.sh debug                  # Chaquopy Android APK
pip install build && python -m build --wheel         # Python wheel for macOS/Linux
# macOS/Linux end-user: pip install spotyvibe-*.whl && spotyvibe
# Dev: bash build-tools/start.sh
```

`tree` is available in git bash — use it for directory exploration.

## Where to Change What

| Task | Files |
|---|---|
| API endpoint / route | `app.py` |
| Config / credentials | `config.py` |
| Spotify OAuth or playlist CRUD | `core/src/playlist.py` (ALL Spotify calls live here — nowhere else) |
| OpenAI / GPT calls | `core/src/openai_http.py` (direct HTTP, no SDK) |
| Music profile logic | `core/src/profile.py` |
| Suggestion engine | `core/src/suggestions.py` |
| Like/dislike | `core/src/feedback.py` |
| Run history | `core/src/history.py` |
| Artist analysis | `core/src/analysis.py` |
| Page layout / HTML structure | `frontend/templates/base.html` + partials |
| Styling | `frontend/static/css/` (11 modular files: base → layout → buttons → forms → components → tracks → modals → quickstart → sections → preview → responsive) |
| JS feature logic | `frontend/static/js/modules/<feature>.js` |
| App entry / module wiring | `frontend/static/js/main.js` |
| Translations | `frontend/static/i18n/en.json` + `de.json` (must stay in sync) |
| AI prompts | `prompts/*.txt` |
| Desktop EXE wrapper | `desktop_launcher.py` |
| macOS/Linux launcher | `build-tools/start.sh`, `SpotyVibe.command`, `start.sh` |
| macOS/Linux packaging | `pyproject.toml`, `spotyvibe/cli.py` |
| Version | `version.py` |

## Rules — Must Follow

1. **i18n** — All user-facing text uses `data-i18n="key"` in HTML or `i18n('key','fallback')` in JS. Never hardcode strings. Always add keys to both `en.json` and `de.json`.
2. **Spotify** — Use `sp.playlist_items()` not `playlist_tracks()`. Search `limit` max is 10. Inner key is `"item"` not `"track"` (Feb 2026 change). See `SKILL.md` for full reference.
3. **Android** — No Rust-extension packages. No `openai` SDK. `pydantic` must be <2.0 if used. Test with `build_apk.sh debug`.
4. **Tests** — Run pytest before completing any code/styling change. Mock all external APIs. Skip for docs-only changes.
5. **Documentation** — Feature changes must update: `README.md`, `documentation/UserManual.md`, `documentation/help.md` (served at `/api/help`), `documentation/TechnicalManual.md`.
6. **Git** — No destructive commands (`restore`, `checkout --`, `reset`, `clean`). Sentence-case commit subjects, no trailing period. **🔴 NEVER run `git commit` or `git push` unless the user has explicitly instructed you to in the current message. A one-time instruction (e.g., "perform a segmented commit") grants permission for that operation only — once completed, permission is revoked. Planning, reviewing, fixing, or editing code is NEVER implicit permission to commit.**
7. **Security** — Never hardcode API keys. Never commit `.credentials`, `.spotify-cache`, or `personalized_music_profile.json`.
8. **Large tasks** — Present a plan with files/order/summary and wait for confirmation before implementing.
9. **No code style enforcement** — Rely on linters/formatters, not AI judgment. Only follow existing conventions.
10. **a11y** — See `RULES.md` for full accessibility checklist. Minimum: ARIA labels on interactive elements, keyboard navigation, focus management in modals.

## Project Tree

```
spotyvibe/
├── app.py                         # Flask server — all routes
├── config.py                      # Config & credential mgmt
├── version.py                     # Version string
├── desktop_launcher.py            # PyInstaller EXE entry
├── spotyvibe_bootstrap.py         # Desktop bootstrap/updater
├── requirements.txt               # Full dev/build dependencies (Windows + testing)
├── requirements-core.txt          # Runtime-only dependencies (macOS/Linux launcher)
├── pyproject.toml                 # Python wheel build config (hatchling)
├── start.sh                       # macOS/Linux launcher wrapper (thin → build-tools/start.sh)
├── SpotyVibe.command              # macOS Finder launcher wrapper (thin → build-tools/start.sh)
├── .gitattributes                 # LF line endings for .sh/.command files
├── pytest.ini                     # Excludes screenshot tests (-m "not screenshots")
├── core/src/                      # Backend logic (Python)
│   ├── openai_http.py             # OpenAI HTTP client (no SDK)
│   ├── profile.py                 # Taste-profile I/O + GPT training
│   ├── suggestions.py             # GPT suggestion engine + dedup
│   ├── playlist.py                # Spotify playlist CRUD & OAuth
│   ├── feedback.py                # Like/dislike recording
│   ├── history.py                 # Run history persistence
│   ├── analysis.py                # Band/artist analysis
│   ├── spotify_metadata.py        # Spotify metadata enrichment
│   ├── taste.py                   # Taste aggregation for dashboard (Wave 3)
│   └── utils.py                   # Shared utilities
├── core/tests/                    # Unit tests — one per core module
├── frontend/templates/            # Jinja2 HTML
│   ├── base.html                  # Main layout (loads all partials)
│   ├── onboarding.html            # 7-step setup wizard (standalone, own i18n)
│   ├── train_profile.html         # Music profile editor
│   ├── generate_section.html      # Playlist generation controls
│   ├── playlist_review.html       # Track review UI
│   ├── band_analysis.html         # Artist deep-dive
│   ├── run_history.html           # Past runs
│   ├── preview_overlay.html       # Audio preview overlay
│   ├── theme_switcher.html, settings_gear.html, toast.html
│   └── modals/                    # credentials, help, quickstart, settings,
│       │                          #   privacy, setup_guide_overlay
│       ├── privacy_modal.html     # "What gets sent where?" data-flow table
│       ├── setup_guide_overlay.html # Full-screen setup guide detail overlay
│       └── preset_manager_modal.html # Preset manager sub-screen
├── frontend/static/favicon.ico    # Browser favicon
├── frontend/static/css/           # Modular CSS (13 files, no bundler)
│   ├── base.css                   # Design tokens, reset, body, scrollbar
│   ├── layout.css                 # Container, typography, sr-only, focus
│   ├── buttons.css                # All .btn-* variants
│   ├── forms.css                  # Form rows, inputs, selects, checkboxes
│   ├── components.css             # Glass panels, toast, tooltip, spinner, accordion
│   ├── tracks.css                 # Track list, items, covers, feedback
│   ├── modals.css                 # Modal overlay, help modal, lightbox
│   ├── quickstart.css             # Quickstart guide (qs-*/qd-* prefixes)
│   ├── sections.css               # Profile, analysis, providers, metadata
│   ├── preview.css                # Spotify preview overlay
│   ├── onboarding.css             # Onboarding wizard shell + step styles
│   ├── setup_guide.css            # Setup guide overlay + privacy table styles
│   ├── completeness.css           # Profile completeness meter styling
│   ├── exploration_slider.css     # 5-notch exploration slider
│   ├── presets.css                # Preset dropdown + manager modal
│   ├── playlist_seed.css          # Playlist seed modal + draft banner (Wave 3)
│   ├── rationale_chips.css        # Rationale chip styling (Wave 3)
│   ├── taste_dashboard.css        # Taste dashboard charts (Wave 3)
│   ├── tips.css                   # Feature discovery tip toasts (Wave 3)
│   ├── provider.css               # Provider dropdown + credential rows (Wave 4)
│   ├── cost_estimate.css          # Cost-estimate card + footnote (Wave 4)
│   ├── voice.css                  # Microphone button states (Wave 4)
│   └── responsive.css             # All @media queries
├── frontend/static/js/modules/   # JS feature modules
│   ├── state.js                   # Central app state
│   ├── ui.js, auth.js, profile.js, pipeline.js, playlist-mode.js
│   ├── review.js, feedback.js, preview.js, tracklist.js
│   ├── history.js, analysis.js, audio-filters.js
│   ├── modals.js, i18n.js, warnings.js, provider-pills.js
│   ├── quickstart-demo.js, quickstart-tour.js, tabs.js
│   ├── onboarding.js              # Wizard state, navigation, language toggle
│   ├── setup_guide.js             # Detail overlay open/close, copy, keyboard
│   ├── completeness.js            # Profile completeness meter calculator
│   ├── exploration.js             # Exploration slider state + bidirectional sync
│   ├── presets.js                 # Preset CRUD, built-in catalogue, import/export
│   ├── quick_advanced.js          # Generate-panel mode toggle + control sync
│   ├── playlist_seed.js           # Playlist-seeded profile flow (Wave 3)
│   ├── rationale.js               # Rationale chip rendering (Wave 3)
│   ├── taste_dashboard.js         # SVG taste visualisation dashboard (Wave 3)
│   ├── tips.js                    # Feature discovery tip toasts (Wave 3)
│   ├── provider.js                # Custom LLM endpoint management (Wave 4)
│   ├── cost_estimate.js           # Token & cost estimator widget (Wave 4)
│   ├── voice.js                   # Web Speech API voice input (Wave 4)
│   └── theme-switcher.js, theme-equalizer.js, theme-pulse.js,
│       theme-spectrum.js, theme-starfield.js
├── frontend/static/i18n/          # en.json + de.json
├── frontend/tests/                # Playwright tests
├── prompts/                       # AI prompt templates
├── android/                       # Chaquopy APK (see rule 3)
├── build-tools/                   # build_exe.sh, build_apk.sh, build_dist.sh, start.sh (launcher)
├── documentation/                 # UserManual, TechnicalManual, help.md
│   ├── guides/                    # Setup guide markdown (openai, spotify)
│   └── assets/guides/             # Guide screenshot placeholders (openai/, spotify/)
├── spotyvibe/                     # Python package (wheel entry point)
│   ├── __init__.py, __main__.py
│   └── cli.py                     # Console entry point (spotyvibe command)
└── data/                          # music_profile.json template
```

## Architecture

- **Single-page Flask app** — `base.html` includes partials; JS modules handle SPA behavior.
- **No build step** — vanilla JS (ES modules), modular CSS (13 files, no bundler).
- **Spotify isolation** — all API calls in `core/src/playlist.py`.
- **OpenAI isolation** — all calls via `core/src/openai_http.py` (raw HTTP).
- **macOS/Linux packaging** — `pyproject.toml` + hatchling builds a `.whl`; `spotyvibe/cli.py` is the entry point.

## Optional MCP Servers (per-developer)

MCP server configs live in each developer's `settings.local.json` (not committed). Below are recommended servers for this project.

### Spotify MCP (`marcelmarais/spotify-mcp-server`)

Provides 30+ Spotify Web API tools (search, playlist CRUD, playback, queue, devices). Useful for live API exploration, verifying response shapes after API changes, and testing search queries without running the app.

**Setup:**
```bash
cd ~/.claude/mcp-servers
git clone https://github.com/marcelmarais/spotify-mcp-server.git
cd spotify-mcp-server
npm install && npm run build
```
Then create a Spotify app at https://developer.spotify.com/dashboard with redirect URI `http://127.0.0.1:8888/callback`, and run `npm run auth` to complete OAuth. Add to your `settings.local.json`:
```json
{
  "mcpServers": {
    "spotify": {
      "command": "node",
      "args": ["<HOME>/.claude/mcp-servers/spotify-mcp-server/build/index.js"]
    }
  }
}
```

**When to use:** Verify Spotify API behavior, test search queries, inspect playlist structures, debug field names after API changes. Consult `SKILL.md` alongside MCP results for known breaking changes.

### GitHub MCP (`github/github-mcp-server`)

Official GitHub MCP server. Monitor CI/CD workflow runs (`release.yml`, `beta.yml`), inspect check failures, review PRs, and manage issues directly from Claude.

**Setup (requires Docker or Podman):**
```json
{
  "mcpServers": {
    "github": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_PAT>"
      }
    }
  }
}
```
Create a PAT at https://github.com/settings/personal-access-tokens/new with `repo` and `read:org` scopes. Substitute `docker` for `podman` if using Docker Desktop. On Windows, use the full path to the Podman executable if it's not in PATH.

**When to use:** Monitor CI/CD builds, review PRs, trace test failures to commits, manage issues.

### Playwright MCP (`microsoft/playwright-mcp`)

Browser automation via accessibility snapshots (not screenshots). Run Playwright tests, debug frontend behavior, and verify UI changes in a real browser.

**Setup (no build needed):**
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

**When to use:** Test UI changes in a live browser, debug DOM/accessibility issues, verify responsive layout behavior.

### MDN MCP (`mdn/mcp`)

Live MDN Web Docs access — current CSS, JavaScript, and Web API references with browser compatibility data. No stale knowledge cutoff.

**Setup (remote, no install):**
```json
{
  "mcpServers": {
    "mdn": {
      "type": "url",
      "url": "https://mcp.mdn.mozilla.net/sse"
    }
  }
}
```

**When to use:** Look up vanilla JS APIs, CSS properties, browser compatibility. Especially useful for this project's no-framework, no-bundler frontend stack.

## On Commit

Before creating a commit: run `tree -L 3 -I "node_modules|__pycache__|.git|venv|dist|build|css-review" --dirsfirst` and update the Project Tree section above if files/dirs were added, removed, or renamed.
