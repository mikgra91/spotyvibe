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
python -m pytest tests/ -v
```

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
│   └── feedback.py         # Like/dislike recording
├── prompts/                # AI prompt templates
├── data/                   # Template data
├── frontend/
│   ├── templates/          # Flask templates (base.html + partials)
│   └── static/             # CSS, JS, and other static assets
├── context/                # Generated context summaries (do not hand-edit)
└── tests/
```

---

## Rules

### Task Planning
- For large tasks (multiple files, new features, cross-cutting concerns): inform the user, present a plan with files/order/summary, and **wait for confirmation** before implementing.
- Break large tasks into sub-agents, one scoped piece per agent.

### Spotify API
- Consult [`SKILL.md`](SKILL.md) for endpoint reference, Feb 2026 breaking changes, OAuth requirements, and spotipy mappings.
- Never use deprecated endpoints. Verify against the [Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) before adding new calls.

### Agent Procedures & Context Files
- Follow the git commit/push procedure in [`SKILL.md`](SKILL.md).
- Context files in `context/` are generated summaries — regenerate them when their source files change, in the same commit.

### Documentation
Every feature change must be reflected in all three:
1. `README.md` — general overview
2. `documentation/help.md` — end-user usage and troubleshooting (served via `/api/help`)
3. `documentation/TechnicalManual.md` — architecture, API, data flow

### Code Style
- Meaningful names, comments only where the "why" isn't obvious.
- Follow existing conventions; check for duplicate logic before adding new code.
- Only remove an import after verifying no usages remain.
- After new features, create/update unit tests.

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
- Run `python -m pytest tests/ -v` before completing any code or styling change.
- Skip for documentation-only changes.
- Mock all external API calls (OpenAI, Spotify).

---

## Context & Token Efficiency

- Prefer high-signal, relevant context over large context. Remove irrelevant content before summarizing.
- Read only required sections/lines of files; summarize after reading; don't re-read the same file twice.
- Keep reasoning short. Don't restate full plans every step — only update what changed.
- Prefer fewer, more complete tool calls. Don't re-send identical results.
- Place critical information at the beginning or end of context, not the middle.
- Stop once the task is complete — avoid unnecessary exploration.
