# AGENTS.md

Project-level instructions for AI coding agents working on this codebase.

---

## Project Overview

**SpotyVibe** is an AI-powered music discovery tool that creates personalised Spotify playlists. It is a Python web application built with Flask, using the OpenAI API for music suggestions and the Spotify Web API for playlist management.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Web framework | Flask ≥3.0 |
| AI | OpenAI API (openai ≥1.0) |
| Spotify integration | Spotipy ≥2.23 (Spotify Web API wrapper) |
| Credential storage | python-dotenv ≥1.0 |
| Frontend | Vanilla HTML / CSS / JavaScript (single-page, no framework) |
| Tests | pytest ≥7.0 |

---

## Build & Run

```bash
# Install dependencies
cd spotyvibe
pip install -r requirements.txt

# Start the app
python app.py
# Open http://127.0.0.1:5000

# Run tests
python -m pytest tests/ -v
```

**Required credentials** (configured at runtime via the UI, stored in `%LOCALAPPDATA%\spotyvibe\.credentials`):
- OpenAI API Key
- Spotify Client ID & Client Secret

The Spotify app must have `http://127.0.0.1:5000/callback` listed as a Redirect URI in the Spotify Developer Dashboard.

---

## Project Structure

```
spotyvibe/
├── app.py                  # Flask web server — all HTTP endpoints
├── config.py               # Centralised configuration & credential management
├── requirements.txt        # Python dependencies
├── core/                   # Business logic modules
│   ├── utils.py            # Shared utilities (OpenAI client, helpers)
│   ├── profile.py          # Taste profile I/O and GPT-based training
│   ├── suggestions.py      # GPT suggestion engine and deduplication
│   ├── playlist.py         # Spotify playlist management and OAuth
│   └── feedback.py         # Like/dislike recording
├── prompts/                # AI prompt templates (editable without code changes)
├── data/                   # Template data (empty profile seed)
├── static/                 # Static assets served by Flask
│   └── css/
│       └── styles.css      # Main stylesheet
├── templates/              # Flask templates (index.html — single-page UI)
└── tests/                  # pytest unit tests
```

---

## Rules

### Task Planning

- **If a task is big, always plan first.** Do not start implementing a large change without a plan.
- If you assess a task as big (e.g. multiple files, new features, cross-cutting concerns), **inform the user** that the task is large and that you will create a plan before writing any code.
- Present the plan to the user — including the list of files to change, the order of changes, and a summary of each step — and **wait for the user to confirm** before proceeding with implementation.
- **Big tasks should be broken down and executed in sub-agents.** Each sub-agent handles one well-scoped piece of the plan (e.g. one module, one test file, one documentation update). This keeps changes focused, reviewable, and easier to roll back.

### Spotify API

- **Always use the current Spotify Web API endpoints.** Do not use deprecated or removed endpoints. Before making Spotify API changes, verify the endpoint is supported by checking the [Spotify Web API Reference](https://developer.spotify.com/documentation/web-api).
- Playlist creation must use `POST /v1/me/playlists` (via `spotipy.Spotify.current_user_playlist_create()`), not the removed `POST /v1/users/{user_id}/playlists`.
- Prefer `current_user_*` spotipy methods over the older `user_*` variants wherever available.

### Documentation

- **Every feature change must be documented in all three places:**
  1. **`README.md`** — general overview of the feature for first-time visitors.
  2. **`UserManual.md`** — end-user explanation: what the feature does, how to use it, and relevant troubleshooting.
  3. **`TechnicalManual.md`** — technical details: architecture, API endpoints, data flow, and implementation notes.
- Do not skip any of the three. If a change affects the UI, backend, or external API behaviour, all three documents must be updated in the same changeset.

### Code Style

- Write clear, readable code with meaningful names.
- Add comments only where the "why" is not obvious.
- Follow existing project conventions — do not rename things for external consistency.
- Check for duplicate logic before adding new code; extract shared logic into helpers.
- Only remove an import after verifying no usages remain in the entire file.
- after new features always create/update the existing unit tests

### Git Safety

- **Do not run destructive git commands** such as `git restore`, `git checkout -- <path>`, `git reset`, or `git clean`.
- If the working tree contains unexpected changes, use non-destructive inspection (`git status`, diffs) and ask the user how to proceed.


### Credentials & Security

- Never hardcode API keys or secrets in source code.
- All credentials are stored in `%LOCALAPPDATA%\spotyvibe\.credentials` (dotenv format), outside the project directory.
- Never commit the `.credentials` file, `.spotify-cache`, or `personalized_music_profile.json`.

### Tests

- Run `python -m pytest tests/ -v` before completing any code or styling change (Python files, HTML templates, CSS).
- **Do not run tests for documentation-only changes** (e.g. updates to `README.md`, `UserManual.md`, `TechnicalManual.md`, or `AGENTS.md`).
- External API calls (OpenAI, Spotify) must be mocked in tests.

