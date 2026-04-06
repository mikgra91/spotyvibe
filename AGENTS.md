# AGENTS.md

Project-level instructions for AI coding agents working on this codebase.
See [`SKILL.md`](SKILL.md) for operational procedures (git workflow, context file maintenance, Spotify API reference).

---

## Project Overview

**SpotyVibe** is an AI-powered music discovery tool that creates personalised Spotify playlists via Flask + OpenAI + Spotify Web API.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Web framework | Flask ≥3.0 |
| AI | OpenAI API (direct HTTP via `core/openai_http.py`, no SDK) |
| Spotify | Spotipy ≥2.23 |
| Credentials | python-dotenv ≥1.0 |
| Frontend | Vanilla HTML/CSS/JS (single-page, no framework) |
| Tests | pytest ≥7.0 |

## Build & Run

```bash
pip install -r requirements.txt
python app.py          # http://127.0.0.1:5000
python -m pytest core/tests/ frontend/tests/ -v
```

Playwright's Chromium browser is auto-installed on the first frontend test run (via `frontend/tests/conftest.py`). No manual `playwright install` step is needed.

Credentials (OpenAI key, Spotify Client ID/Secret) are configured via the UI and stored in `%LOCALAPPDATA%\spotyvibe\.credentials`.
Spotify app must have `http://127.0.0.1:5000/callback` as a Redirect URI.

## Android (Chaquopy) Constraints

The Android APK uses Chaquopy. Pip pins in `android/app/build.gradle` intentionally differ from `requirements.txt` — avoid packages with native/Rust extensions.

- **Do not re-add `openai`** — replaced by `core/openai_http.py` to eliminate `jiter`/`pydantic-core` (Rust) deps
- **`pydantic` must be `<2.0`** if re-added — v2 depends on `pydantic-core` (Rust)
- After changing Android pip pins, run `./build-tools/build_apk.sh debug` to validate

## Project Structure

```
spotyvibe/
├── app.py                  # Flask web server — all HTTP endpoints
├── config.py               # Configuration & credential management
├── requirements.txt
├── core/
│   ├── openai_http.py      # Direct HTTP client for OpenAI API (no SDK)
│   ├── utils.py            # Shared utilities
│   ├── profile.py          # Taste profile I/O and GPT-based training
│   ├── suggestions.py      # GPT suggestion engine and deduplication
│   ├── playlist.py         # Spotify playlist management and OAuth
│   ├── feedback.py         # Like/dislike recording
│   └── tests/              # Unit tests for core modules
├── prompts/                # AI prompt templates
├── data/                   # Template data
├── frontend/
│   ├── templates/          # Flask templates (base.html + partials)
│   ├── static/             # CSS, JS, and other static assets
│   └── tests/              # Frontend (Playwright) tests
```

---

## Rules

### Task Planning
- For large tasks (multiple files, new features, cross-cutting concerns): inform the user, present a plan with files/order/summary, and **wait for confirmation** before implementing.
- Break large tasks into sub-agents, one scoped piece per agent.

### Spotify API
- **Primary reference:** [`SKILL.md`](SKILL.md) — contains the full endpoint table, Feb 2026 breaking changes, OAuth flow, field filtering syntax, and spotipy method mappings. Read it before making any Spotify-related code change.
- Never use deprecated endpoints. Verify against the [Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) before adding new calls.
- **Key Feb 2026 gotchas:**
  - Playlist item inner key is `"item"`, not `"track"`. Use the defensive pattern: `entry.get("item") or entry.get("track")`.
  - Playlist summary field on `GET /me/playlists` is `"items"`, not `"tracks"`. Use: `pl.get("items") or pl.get("tracks")`.
  - `fields` parameter must match the new key names — e.g. `items(item(uri,name,...))` not `items(track(...))`. Mismatched filters return empty objects silently (no error).
  - Search `limit` max is 10 (down from 50). Always pass `limit` explicitly.
  - Use `sp.playlist_items()`, never `sp.playlist_tracks()`.
  - Use `sp.current_user_playlist_create()`, never `sp.user_playlist_create()`.
- **All Spotify interactions** live in `core/src/playlist.py`. Do not scatter Spotify API calls across other modules.

### Agent Procedures
- Follow the git commit/push procedure in [`SKILL.md`](SKILL.md).

### Documentation
Every feature change must be reflected in all four:
1. `README.md` — general overview
2. `documentation/UserManual.md` — detailed end-user manual (comprehensive walkthrough of all features)
3. `documentation/help.md` — in-app user guide served via `/api/help` (see below)
4. `documentation/TechnicalManual.md` — architecture, API, data flow

#### `documentation/help.md` — In-App Help
- **Served at runtime** by the `/api/help` endpoint, rendered as HTML inside the Help modal.
- **Audience:** end users interacting with the SpotyVibe UI.
- **Scope:** step-by-step usage guide covering first-time setup (credentials, settings, Spotify connection), music profile creation (core description, must-have, soft preferences, avoid), playlist generation (modes, audio filters, cancel/use-now), track review (preview, like, dislike, remove), song list persistence, run history, undo, mobile usage, and troubleshooting.
- **Format:** Markdown with `> **Screenshot placeholder:**` markers for future screenshots. Keep sections self-contained and scannable — users jump directly to a section via the table of contents.
- When adding a new user-facing feature, add a corresponding section to `help.md` with clear instructions and a screenshot placeholder.

### Code Style
- Meaningful names, comments only where the "why" isn't obvious.
- Follow existing conventions; check for duplicate logic before adding new code.
- Only remove an import after verifying no usages remain.
- After new features, create/update unit tests.

### Internationalization (i18n)
All user-facing text in the frontend **must** use the i18n system — **never** hardcode strings directly in HTML templates or JavaScript modules.

- **Language files** are at `frontend/static/i18n/en.json` (English) and `frontend/static/i18n/de.json` (German). Both files must always have the same set of keys.
- **HTML templates:** Use `data-i18n="key"` for visible text content, `data-i18n-placeholder="key"` for input placeholders, and `data-i18n-title="key"` for title/tooltip attributes. The English text in the HTML serves as a fallback; the i18n system overwrites it on page load.
- **JavaScript modules:** Import `{ i18n } from './i18n.js'` and use `i18n('key', 'Fallback text')` for any user-visible string (toasts, alerts, status messages, dynamically built HTML labels, button text, etc.).
- **Onboarding page** (`onboarding.html`): Uses its own lightweight `obI18n()` / `obApplyLang()` functions (no ES module imports). Follow the same `data-i18n` attribute pattern for static text and `obI18n()` for dynamic JS strings.
- **Adding new strings:** When adding any new user-facing text, always:
  1. Add the key + English value to `en.json`.
  2. Add the key + German translation to `de.json`.
  3. Use `data-i18n` in HTML or `i18n()` in JS — never leave a raw string.
- **Key naming convention:** Use dot-separated namespaces matching the feature area (e.g., `profile.title`, `feedback.like`, `pipeline.cancelled`, `ob.skip`).

### Accessibility (a11y)
Every frontend change **must** consider visually impaired and assistive-technology users:
- **ARIA attributes** — All interactive elements must have descriptive `aria-label` or `aria-labelledby`. Use `aria-expanded`, `aria-controls`, `aria-modal`, `aria-live`, and `role` attributes where applicable.
- **Focus management** — Modals and overlays must trap focus and restore it on close. Ensure a logical tab order; never leave focus on hidden or removed elements.
- **Keyboard navigation** — Every action reachable by mouse/touch must also be reachable via keyboard (`Tab`, `Enter`, `Space`, `Escape`). Add `onkeydown` handlers alongside `onclick` for custom controls.
- **Screen-reader text** — Use `.sr-only` for text that should be announced but not visible. Decorative icons must have `aria-hidden="true"`.
- **Color & contrast** — Never convey information by color alone; pair color indicators with text or icons. Maintain WCAG AA contrast ratios (≥ 4.5:1 for text, ≥ 3:1 for large text/UI components).
- **Semantic HTML** — Prefer `<button>`, `<a>`, `<nav>`, `<main>`, `<section>`, `<label>` over generic `<div>`/`<span>` for interactive or structural elements.
- **`prefers-reduced-motion`** — Respect the user's motion preference; disable or simplify animations when this media query matches.
- **Skip link** — The existing "Skip to main content" link must remain functional.
- **Testing** — When adding new UI components, manually verify with a screen reader (TalkBack on Android, NVDA or Narrator on Windows) or at minimum check the DOM for correct ARIA tree structure.

### Git
- **No destructive commands**: no `git restore`, `git checkout -- <path>`, `git reset`, `git clean`. On unexpected state, inspect and ask the user.
- **Commit message style** — sentence-case subject, no trailing period; bullet body for multi-file changes describing what changed and why:
  ```
  Add profile import/export and tighten Android WebView security

  - Add profile import/export endpoints and UI controls
  - Enforce server-side import size limits
  ```

### Credentials & Security
- Never hardcode API keys or secrets.
- Never commit `.credentials`, `.spotify-cache`, or `personalized_music_profile.json`.

### Tests
- Run `python -m pytest core/tests/ frontend/tests/ -v` before completing any code or styling change.
- Skip for documentation-only changes.
- Mock all external API calls (OpenAI, Spotify).
- Playwright Chromium is auto-installed by `frontend/tests/conftest.py` on the first run — no manual step needed after `pip install -r requirements.txt`.
- **Screenshot tests** (`frontend/tests/test_documentation_screenshots.py`) are marked `@pytest.mark.screenshots` and excluded from routine runs via `pytest.ini` (`-m "not screenshots"`). Run them manually when documentation screenshots need refreshing:
  ```bash
  python -m pytest frontend/tests/test_documentation_screenshots.py -v -m screenshots
  ```

---

## Context & Token Efficiency

- Prefer high-signal, relevant context over large context. Remove irrelevant content before summarizing.
- Read only required sections/lines of files; summarize after reading; don't re-read the same file twice.
- Keep reasoning short. Don't restate full plans every step — only update what changed.
- Prefer fewer, more complete tool calls. Don't re-send identical results.
- Place critical information at the beginning or end of context, not the middle.
- Stop once the task is complete — avoid unnecessary exploration.
