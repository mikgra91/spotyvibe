# CLAUDE.md — SpotyVibe

> ## 🔴🔴🔴 ABSOLUTE RULE — READ BEFORE ANYTHING ELSE
>
> **NEVER run `git commit`, `git push`, or any command that creates commits or pushes to a remote.**
>
> The ONLY exception: the user's **current message** contains the **EXACT, LITERAL, CASE-SENSITIVE STRING `CP ALLOWED`** as a standalone, top-level instruction. No other phrase grants permission — not "commit and push", not "go ahead", not "yes", not any natural-language equivalent. **`CP ALLOWED` or nothing.**
>
> - One occurrence of `CP ALLOWED` = ONE git operation. Permission revoked the instant it completes.
> - Editing, fixing, planning, or reviewing code is **NEVER** implicit permission to commit.
> - When in doubt: **do NOT commit. Ask the user.**
> - There are **zero exceptions** to this rule. It has been violated 9 times. Each violation caused real damage.

AI-powered music discovery: Flask + OpenAI + Spotify Web API.

**Load on demand:**
- [`documentation/api/spotify.md`](documentation/api/spotify.md) — Spotify Web API conventions and known breaking changes (read before any Spotify API change).
- [`documentation/conventions.md`](documentation/conventions.md) — Full a11y checklist + i18n details.
- [`documentation/MCPServers.md`](documentation/MCPServers.md) — Optional MCP server setup (Spotify, GitHub, Playwright, MDN).
- [`documentation/TechnicalManual.md`](documentation/TechnicalManual.md) — Architecture, modules, data flow.
- [`documentation/guides/cloud-run-rag-setup.md`](documentation/guides/cloud-run-rag-setup.md) — GCP-side RAG corpus pipeline.

## Build & Run

```bash
python app.py                                        # http://127.0.0.1:5000
bash build-tools/run_tests.sh                        # core + frontend tests in parallel
bash build-tools/build_exe.sh                        # PyInstaller Windows EXE
pip install build && python -m build --wheel         # Python wheel for macOS/Linux
```

### Running Tests

| Command | Runs |
|---|---|
| `python -m pytest core/tests/ -v` | Core unit tests (~620 tests, ~3s) |
| `bash build-tools/run_frontend_tests.sh` | Frontend tests in 3 parallel groups (~233 tests) |
| `bash build-tools/run_tests.sh` | Core + frontend in parallel (4 groups) |
| `bash build-tools/run_tests.sh core` \| `frontend` | Scope to one side |
| `bash build-tools/run_tests_podman.sh` | All tests in Podman containers (CI) |

**⚠️ `test_documentation_screenshots.py` is NEVER run automatically** — excluded via the `screenshots` marker. Run only when the user explicitly requests a screenshot refresh.

`tree` is available in git bash — use it for directory exploration. CI-simulation recipe + parallel-monitor snippet live in `documentation/TechnicalManual.md`.

## Where to Change What

| Task | Files |
|---|---|
| API endpoint / route | `app.py` |
| Config / credentials | `config.py` |
| Spotify OAuth or playlist CRUD | `core/src/playlist.py` (ALL Spotify calls live here) |
| OpenAI / GPT calls | `core/src/openai_http.py` (direct HTTP, no SDK) |
| Music profile logic | `core/src/profile.py` |
| Suggestion engine | `core/src/suggestions.py` |
| RAG corpus & retrieval | `core/src/rag/` (corpus, retrieval, prompt, distribution) |
| Like/dislike | `core/src/feedback.py` |
| Run history | `core/src/history.py` |
| Artist analysis | `core/src/analysis.py` |
| Page layout / HTML structure | `frontend/templates/base.html` + partials |
| Styling | `frontend/static/css/` (modular, no bundler) |
| JS feature logic | `frontend/static/js/modules/<feature>.js` |
| App entry / module wiring | `frontend/static/js/main.js` |
| Translations | `frontend/static/i18n/en.json` + `de.json` + `jp.json` (must stay in sync) |
| AI prompts | `prompts/*.txt` |
| Desktop EXE wrapper | `desktop_launcher.py` |
| macOS/Linux launcher | `build-tools/start.sh`, `SpotyVibe.command`, `start.sh` |
| Version | `version.py` |

## Rules — Must Follow

1. **i18n** — All user-facing text uses `data-i18n="key"` in HTML or `i18n('key','fallback')` in JS. Never hardcode strings. Keys must exist in `en.json`, `de.json`, and `jp.json`.
2. **Spotify** — Use `sp.playlist_items()` not `playlist_tracks()`. Search `limit` max is 10. Inner key is `"item"` not `"track"` (Feb 2026 change). See [`documentation/api/spotify.md`](documentation/api/spotify.md) for full reference.
3. **Tests** —
   - Run pytest before completing any code/styling change. Mock all external APIs. Skip for docs-only changes.
   - **Scope rule:** fix test failures that are (a) caused by your current change, OR (b) in code paths you are actively touching. For unrelated pre-existing failures, **report them to the user and ask whether to fix now or defer** — do not silently expand the task. A 5-line change should not turn into a 12-file refactor without explicit confirmation.
4. **Documentation** — Feature changes must update: `README.md`, `documentation/UserManual.md`, `documentation/help.en.md` + `documentation/help.de.md` + `documentation/help.jp.md` (keep in sync), `documentation/TechnicalManual.md`.
5. **Git** —
   - No destructive commands (`restore`, `checkout --`, `reset`, `clean`).
   - **Do not use `git stash` / `git stash pop` inside an assistant session** — pop re-injects every restored file's contents into the conversation as "intentional changes" system reminders, consuming tens of thousands of tokens. If work must be parked, commit to a scratch branch instead, or ask the user.
   - Sentence-case commit subjects, no trailing period.
   - **🔴 NEVER run `git commit` or `git push` unless the user's current message contains the exact string `CP ALLOWED`. No other phrase grants permission. Permission is one-time only — once the operation completes, permission is revoked.**
6. **Security** — Never hardcode API keys. Never commit `.credentials`, `.spotify-cache`, or `personalized_music_profile.json`.
7. **Large tasks** — Present a plan with files/order/summary and wait for confirmation before implementing.
8. **No code style enforcement** — Rely on linters/formatters, not AI judgment. Only follow existing conventions.
9. **a11y** — See [`documentation/conventions.md`](documentation/conventions.md) for full checklist. Minimum: ARIA labels on interactive elements, keyboard navigation, focus management in modals.

## Context Discipline

Context is the budget for a session. Blow it and the session ends mid-task. Rules:

- **Batch reads.** If you know you'll touch N related files, read them in one parallel tool block, not iteratively.
- **Don't re-read files.** The harness tracks file state after Edit/Write — re-reading to "verify" is waste.
- **Prefer Grep over Read for discovery.** Read only the specific lines you'll edit.
- **Don't run pytest more than needed.** One baseline run, one confirmation run. Not five debug loops. Use `-k <pattern>` to narrow scope during iteration.
- **Avoid `git stash`** (see rule 6). Pop re-injects file contents.
- **Delegate to subagents only when genuinely useful** — they re-derive context, which is often more expensive than inline work on tasks the parent already understands.
- **When context gets tight, tell the user.** Offer to `/compact` or checkpoint-and-resume, rather than silently degrading.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
