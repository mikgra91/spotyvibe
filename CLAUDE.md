# CLAUDE.md — SpotyVibe

AI-powered music discovery: Flask + OpenAI + Spotify Web API.
Read `SKILL.md` before any Spotify API change. Read `RULES.md` for a11y and detailed conventions.

## Build & Run

```bash
python app.py                                        # http://127.0.0.1:5000
python -m pytest core/tests/ frontend/tests/ -v      # run tests (required before completing code changes)
bash build-tools/build_exe.sh                        # PyInstaller Windows EXE
bash build-tools/build_apk.sh debug                  # Chaquopy Android APK
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
| Styling | `frontend/static/css/styles.css` (single file, ~5000 lines) |
| JS feature logic | `frontend/static/js/modules/<feature>.js` |
| App entry / module wiring | `frontend/static/js/main.js` |
| Translations | `frontend/static/i18n/en.json` + `de.json` (must stay in sync) |
| AI prompts | `prompts/*.txt` |
| Desktop EXE wrapper | `desktop_launcher.py` |
| Version | `version.py` |

## Rules — Must Follow

1. **i18n** — All user-facing text uses `data-i18n="key"` in HTML or `i18n('key','fallback')` in JS. Never hardcode strings. Always add keys to both `en.json` and `de.json`.
2. **Spotify** — Use `sp.playlist_items()` not `playlist_tracks()`. Search `limit` max is 10. Inner key is `"item"` not `"track"` (Feb 2026 change). See `SKILL.md` for full reference.
3. **Android** — No Rust-extension packages. No `openai` SDK. `pydantic` must be <2.0 if used. Test with `build_apk.sh debug`.
4. **Tests** — Run pytest before completing any code/styling change. Mock all external APIs. Skip for docs-only changes.
5. **Documentation** — Feature changes must update: `README.md`, `documentation/UserManual.md`, `documentation/help.md` (served at `/api/help`), `documentation/TechnicalManual.md`.
6. **Git** — No destructive commands (`restore`, `checkout --`, `reset`, `clean`). Sentence-case commit subjects, no trailing period.
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
├── requirements.txt
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
│   └── utils.py                   # Shared utilities
├── core/tests/                    # Unit tests — one per core module
├── frontend/templates/            # Jinja2 HTML
│   ├── base.html                  # Main layout (loads all partials)
│   ├── onboarding.html            # First-run setup (standalone, own i18n)
│   ├── train_profile.html         # Music profile editor
│   ├── generate_section.html      # Playlist generation controls
│   ├── playlist_review.html       # Track review UI
│   ├── band_analysis.html         # Artist deep-dive
│   ├── run_history.html           # Past runs
│   ├── preview_overlay.html       # Audio preview overlay
│   ├── theme_switcher.html, settings_gear.html, toast.html
│   └── modals/                    # credentials, help, quickstart, settings
├── frontend/static/js/modules/   # JS feature modules
│   ├── state.js                   # Central app state
│   ├── ui.js, auth.js, profile.js, pipeline.js, playlist-mode.js
│   ├── review.js, feedback.js, preview.js, tracklist.js
│   ├── history.js, analysis.js, audio-filters.js
│   ├── modals.js, i18n.js, warnings.js, provider-pills.js
│   ├── quickstart-demo.js, quickstart-tour.js, jump-bubble.js
│   └── theme-switcher.js, theme-equalizer.js, theme-pulse.js,
│       theme-spectrum.js, theme-starfield.js
├── frontend/static/i18n/          # en.json + de.json
├── frontend/tests/                # Playwright tests
├── prompts/                       # AI prompt templates
├── android/                       # Chaquopy APK (see rule 3)
├── build-tools/                   # build_exe.sh, build_apk.sh
├── documentation/                 # UserManual, TechnicalManual, help.md
└── data/                          # music_profile.json template
```

## Architecture

- **Single-page Flask app** — `base.html` includes partials; JS modules handle SPA behavior.
- **No build step** — vanilla JS (ES modules), single CSS file.
- **Spotify isolation** — all API calls in `core/src/playlist.py`.
- **OpenAI isolation** — all calls via `core/src/openai_http.py` (raw HTTP).

## On Commit

Before creating a commit: run `tree -L 3 -I "node_modules|__pycache__|.git|venv|dist|build|css-review" --dirsfirst` and update the Project Tree section above if files/dirs were added, removed, or renamed.
