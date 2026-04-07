# AGENTS.md

Project-level instructions for AI coding agents working on this codebase.
Claude users: all instructions are in `CLAUDE.md`. This file exists for non-Claude agents.

See `CLAUDE.md` for project structure, architecture, and rules.
See `SKILL.md` for Spotify Web API reference.
See `RULES.md` for detailed a11y, i18n, and documentation conventions.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Web framework | Flask ≥3.0 |
| AI | OpenAI API (direct HTTP via `core/src/openai_http.py`, no SDK) |
| Spotify | Spotipy ≥2.23 |
| Credentials | python-dotenv ≥1.0, OS keychain (Windows Credential Manager) |
| Frontend | Vanilla HTML/CSS/JS (single-page, no framework, no build step) |
| Tests | pytest ≥7.0, Playwright (frontend) |
| Desktop | PyInstaller + webview |
| Android | Chaquopy (no Rust-extension packages) |

## Key Constraints

1. All Spotify API calls in `core/src/playlist.py` only.
2. All OpenAI calls through `core/src/openai_http.py` only.
3. All user-facing text must use i18n (`en.json` + `de.json`).
4. Run `python -m pytest core/tests/ frontend/tests/ -v` before completing changes.
5. Feature changes require updates to all 4 documentation files (see `RULES.md`).
6. No destructive git commands. No hardcoded secrets.
7. Android: no Rust-extension packages, no `openai` SDK, `pydantic` <2.0.
8. Spotify OAuth redirect: `http://127.0.0.1:5000/callback`.
