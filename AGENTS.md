# AGENTS.md

> ## 🔴🔴🔴 ABSOLUTE RULE — READ BEFORE ANYTHING ELSE
>
> **NEVER run `git commit`, `git push`, or any command that creates commits or pushes to a remote.**
>
> The ONLY exception: the user has **explicitly told you** to commit/push **in the current message** (e.g., "commit this", "perform a segmented commit and push"). Even then, permission covers **that one operation only** — once done, permission is revoked.
>
> - Editing, fixing, planning, or reviewing code is **NEVER** implicit permission to commit.
> - When in doubt: **do NOT commit. Ask the user.**
> - There are **zero exceptions** to this rule.

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

## MCP Servers (recommended for AI agents)

If your AI tooling supports MCP (Model Context Protocol), the following servers are recommended for this project. Setup instructions are in `CLAUDE.md` → "Optional MCP Servers". Configuration is per-developer (`settings.local.json`, not committed).

| Server | Purpose |
|---|---|
| **Spotify** (`marcelmarais/spotify-mcp-server`) | Live Spotify API exploration, verify response shapes, test search queries |
| **GitHub** (`github/github-mcp-server`) | Monitor CI/CD workflows, inspect check failures, review PRs |
| **Playwright** (`microsoft/playwright-mcp`) | Browser automation for UI testing and debugging |
| **MDN** (`mdn/mcp`) | Live CSS/JS/Web API reference with browser compatibility data |

## Key Constraints

1. All Spotify API calls in `core/src/playlist.py` only.
2. All OpenAI calls through `core/src/openai_http.py` only.
3. All user-facing text must use i18n (`en.json` + `de.json`).
4. Run `python -m pytest core/tests/ frontend/tests/ -v` before completing changes.
5. Feature changes require updates to all 4 documentation files (see `RULES.md`).
6. No destructive git commands. No hardcoded secrets. **🔴 NEVER run `git commit` or `git push` unless the user has explicitly instructed you to in the current message. Permission is one-time only — once the operation completes, permission is revoked.**
7. Android: no Rust-extension packages, no `openai` SDK, `pydantic` <2.0.
8. Spotify OAuth redirect: `http://127.0.0.1:5000/callback`.
9. **🔴 Pre-existing test failures are NOT to be ignored.** When running the test suite (rule 4), **all** failures must be investigated and fixed — not just those caused by changes made in the current session. A test that was already broken before you started is still a bug. Report it, diagnose it, and fix it. Never dismiss a failure with "this wasn't caused by my changes" or silently skip it.
