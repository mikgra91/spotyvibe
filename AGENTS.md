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
- **Consult [`SKILL.md`](SKILL.md) for a full summary of endpoints used by SpotyVibe, the February 2026 breaking changes, OAuth redirect URI requirements, and spotipy method mappings.**
- Playlist creation must use `POST /v1/me/playlists` (via `spotipy.Spotify.current_user_playlist_create()`), not the removed `POST /v1/users/{user_id}/playlists`.
- Playlist track reads/writes must use `GET/POST /playlists/{id}/items` (via `sp.playlist_items()` / `sp.playlist_add_items()`). The old `/tracks` endpoints were removed in February 2026.
- Prefer `current_user_*` spotipy methods over the older `user_*` variants wherever available.
- Search `limit` must be ≤ 10 (Spotify reduced the maximum in February 2026).

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

### Git Commit Message Style

Follow the existing repository commit message style:

- **Subject line:** short, sentence-case summary (no trailing period). Keep it descriptive (avoid placeholder commits like `"y"`).
- **Body (recommended for multi-file changes):** blank line after the subject, then a bullet list using `- `.
- Bullets should describe **what changed and why**, not just file names.

Example:

```
Add profile import/export and tighten Android WebView security

- Add profile import/export endpoints and UI controls
- Enforce server-side import size limits
- Restrict Android WebView downloads to trusted localhost endpoints
- Update docs and tests for new behavior
```


### Credentials & Security


- Never hardcode API keys or secrets in source code.
- All credentials are stored in `%LOCALAPPDATA%\spotyvibe\.credentials` (dotenv format), outside the project directory.
- Never commit the `.credentials` file, `.spotify-cache`, or `personalized_music_profile.json`.

### Tests

- Run `python -m pytest tests/ -v` before completing any code or styling change (Python files, HTML templates, CSS).
- **Do not run tests for documentation-only changes** (e.g. updates to `README.md`, `UserManual.md`, `TechnicalManual.md`, or `AGENTS.md`).
- External API calls (OpenAI, Spotify) must be mocked in tests.

# Token & Context Optimization Rules (Claude Code)

## 1. Core Principle
- Optimize for **tokens per successful task**, not per message.
- Minimize tokens **without reducing correctness**.
- Every token must provide value.
- Prefer clarity over extreme brevity if it prevents retries.

---

## 2. Context Budget Management

### 2.1 Soft Context Limit (CRITICAL)
- Do NOT exceed **60–70% of the model's max context window**.
- Behavior:
  - <50% → normal operation
  - 50–70% → begin compaction
  - >70% → aggressive compaction required
  - >85% → critical, must reduce immediately

---

### 2.2 Mandatory Compaction Thresholds
- <300 tokens → never compact  
- 300–800 tokens → avoid compaction  
- 800–1,500 tokens → compact if reused  
- >1,500 tokens → compact if reused once  
- >3,000 tokens → compaction REQUIRED  

---

### 2.3 Context Reuse Rule
- If context will be reused ≥2 times → prefer summarization.
- Avoid re-sending large raw context multiple times.

---

## 3. Context Quality (More Important than Size)

### 3.1 Context Dilution Rule
- More context can reduce accuracy.
- Always prefer **high-signal, relevant context** over large context.

---

### 3.2 Relevance Filtering (MANDATORY)
- Remove irrelevant content BEFORE summarizing.
- Never compress irrelevant information — delete it.

---

### 3.3 Information Density Rule
- Preserve:
  - constraints
  - numbers
  - code
  - key facts
- Remove:
  - filler text
  - explanations
  - redundancy

---

## 4. Context Structure (CRITICAL — Research-Based)

### 4.1 Position-Aware Ordering
- Place most important information at:
  1. Beginning
  2. End
- Avoid placing critical information in the middle of long context.

---

### 4.2 Lost-in-the-Middle Mitigation
- Extract key facts and move them to the top.
- Keep important constraints near the end when relevant.

---

## 5. Compression Strategy

### 5.1 Hierarchical Compression (REQUIRED)
- Never summarize large context in one step.
- Use:
  1. Split into chunks
  2. Summarize each chunk
  3. Merge summaries

---

### 5.2 Compression Ratios
- General tasks → 30–60%
- Code / technical → 50–80%
- High precision → 70–90%
- Avoid compression below 30% unless necessary

---

### 5.3 Anti-Recompression Rule
- NEVER summarize already summarized content.
- Always summarize from the original source if available.
- If only a summary exists → treat it as final.

---

## 6. Agent Loop Optimization

### 6.1 Minimize Reasoning Tokens
- Keep reasoning short and structured.
- Avoid verbose chain-of-thought.

---

### 6.2 Avoid Re-Planning
- Do NOT restate full plans every step.
- Only update what changed.

---

### 6.3 Early Convergence
- Stop once the task is complete.
- Avoid unnecessary exploration.

---

## 7. Tool Usage Optimization

### 7.1 Minimize Tool Calls
- Prefer fewer, more complete tool calls.
- Combine operations when possible.

---

### 7.2 Reduce Tool Payload
- Send only required parameters.
- Avoid sending full files unless necessary.

---

### 7.3 Avoid Duplication
- Do not re-send identical tool results.
- Store and reference instead.

---

## 8. File & Code Context Management

### 8.1 Partial Reads Only
- Read only:
  - relevant sections
  - specific lines
  - required symbols

---

### 8.2 Summarize Large Files
- Summarize after reading.
- Discard raw content once summarized.

---

### 8.3 Avoid Duplicate Context
- Do not include the same code multiple times.
- Reference instead of repeating.

---

## 9. Multi-Step Task Optimization

### 9.1 Merge Steps
- Combine compatible operations.

---

### 9.2 Avoid Backtracking
- Validate before acting.

---

### 9.3 Cache Results
- Reuse intermediate results.

---

## 10. Anti-Patterns (Avoid)

- Re-reading the same file multiple times
- Repeating full plans every step
- Sending full file contents unnecessarily
- Keeping outdated context
- Verbose reasoning traces
- Excessive tool calls
- Large unfiltered retrieval results

---

## 11. Heuristics

- If it can be removed → remove it
- If it repeats → deduplicate it
- If it grows → summarize it
- If it’s irrelevant → delete it
- If output is long → constrain it

---

## 12. Tradeoff Rule

- Use more tokens only if it:
  - prevents retries
  - improves correctness
  - reduces total steps