# Project Layout

> Read this file on demand when you need a full directory map.
> Do not inline it into conversations. For day-to-day work, the tables
> in `CLAUDE.md` ("Where to Change What") are sufficient.

## Directory Tree

```
spotyvibe/
├── app.py                         # Flask server — all routes
├── config.py                      # Config & credential mgmt
├── version.py                     # Version string
├── desktop_launcher.py            # PyInstaller EXE entry
├── requirements.txt               # Full dev/build dependencies (Windows + testing)
├── requirements-core.txt          # Runtime-only dependencies (macOS/Linux launcher)
├── pyproject.toml                 # Python wheel build config (hatchling)
├── start.sh                       # macOS/Linux launcher wrapper (thin → build-tools/start.sh)
├── SpotyVibe.command              # macOS Finder launcher wrapper (thin → build-tools/start.sh)
├── spotyvibe.spec                 # PyInstaller spec (folder build)
├── spotyvibe_onefile.spec         # PyInstaller spec (single-file build)
├── pytest.ini                     # Excludes screenshot tests (-m "not screenshots")
├── README.md                      # Developer overview
├── CLAUDE.md, AGENTS.md           # Project-level AI agent rules
├── RULES.md, SKILL.md             # On-demand convention + Spotify-API references
├── result-improvement.md          # Phase status dashboard + retro
├── core/src/                      # Backend logic (Python)
│   ├── openai_http.py             # OpenAI HTTP client (no SDK; local-LLM-friendly)
│   ├── profile.py                 # Taste-profile I/O + GPT training
│   ├── suggestions.py             # GPT suggestion engine + dedup (3-stage pipeline)
│   ├── playlist.py                # Spotify playlist CRUD & OAuth
│   ├── feedback.py                # Like/dislike recording
│   ├── history.py                 # Run history persistence
│   ├── analysis.py                # Band/artist analysis
│   ├── taste.py                   # Taste aggregation for dashboard
│   ├── localised_docs.py          # Language-aware Markdown resolver (en/de/jp fallback)
│   ├── eval_log.py                # Per-batch / per-run eval telemetry rows
│   ├── utils.py                   # Shared utilities
│   └── rag/                       # Retrieval-augmented generation pool
│       ├── corpus.py              # RAG corpus loader
│       ├── retrieval.py           # Artist scoring + selection
│       ├── prompt.py              # Candidate-pool block formatting
│       └── distribution.py        # Cloud-Run / HTTP corpus distribution
├── core/tests/                    # Unit tests — one per core module
│   ├── test_i18n_parity.py        # Asserts en/de/jp.json key sets match
│   └── …                          # ~620 tests (~3s)
├── frontend/templates/            # Jinja2 HTML
│   ├── base.html                  # Main layout (loads all partials)
│   ├── macros.html                # Shared Jinja macros
│   ├── onboarding.html            # 4-page setup wizard (Welcome → Language → Credentials → Connect)
│   ├── train_profile.html         # Music profile editor
│   ├── generate_section.html      # Playlist generation controls
│   ├── playlist_review.html       # Track review UI
│   ├── band_analysis.html         # Artist deep-dive
│   ├── run_history.html           # Past runs
│   ├── preview_overlay.html       # Audio preview overlay
│   ├── taste_dashboard.html       # Taste dashboard charts panel
│   ├── theme_switcher.html, settings_gear.html, toast.html
│   └── modals/
│       ├── credentials_modal.html # API keys entry
│       ├── settings_modal.html    # Model, playlist size, language, display size, debug
│       ├── help_modal.html        # In-app help viewer
│       ├── quickstart_modal.html  # Provider-scoped Quick Start storyboard
│       ├── privacy_modal.html     # "What gets sent where?" data-flow table
│       ├── playlist_seed_modal.html # Playlist-seeded profile picker
│       ├── preset_manager_modal.html # Preset CRUD sub-screen
│       └── setup_guide_overlay.html # Full-screen setup guide detail overlay
├── frontend/static/favicon.ico    # Browser favicon
├── frontend/static/css/           # Modular CSS (no bundler)
│   └── …                          # See `documentation/TechnicalManual.md` § "Frontend"
├── frontend/static/js/modules/    # JS feature modules (vanilla ES modules)
│   ├── core: state.js, dom.js, ui.js, tabs.js, modals.js, i18n.js, warnings.js
│   ├── auth: auth.js, provider.js, provider-pills.js
│   ├── feature: profile.js, pipeline.js, playlist-mode.js, review.js,
│   │           feedback.js, feedback-api.js, preview.js, tracklist.js,
│   │           history.js, analysis.js, audio-filters.js, completeness.js,
│   │           exploration.js, presets.js, quick_advanced.js, playlist_seed.js,
│   │           rationale.js, taste_dashboard.js, tips.js, cost_estimate.js,
│   │           voice.js, getting-started.js, ui-scale.js, spotify-sdk.js,
│   │           rag_update_prompt.js
│   ├── onboarding: onboarding.js, setup_guide.js, quickstart-demo.js, quickstart-tour.js
│   └── theme: theme-switcher.js, theme-equalizer.js, theme-pulse.js,
│              theme-spectrum.js, theme-starfield.js, theme-calm.js
├── frontend/static/i18n/          # en.json + de.json + jp.json (key sets must match)
├── frontend/tests/                # Playwright tests (~233; 3 parallel groups)
│   ├── conftest.py, helpers.py, helpers_integration.py
│   ├── test_page_load.py, test_navigation.py, test_modals.py
│   ├── test_profile.py, test_generation.py, test_edge_cases.py,
│   │   test_onboarding.py, test_profile_integration.py
│   ├── test_wf_*.py               # 7 workflow files
│   └── test_documentation_screenshots.py  # gated by `screenshots` marker — never run automatically
├── prompts/                       # AI prompt templates (3-stage pipeline)
│   ├── system_prompt.txt, prompt_template.txt   # legacy / fallback
│   ├── avoid_check_system.txt                   # Stage 2
│   ├── track_select_system.txt, track_select_system_local.txt,
│   │   track_select_user.txt                    # Stage 3
│   ├── analysis_prompt.txt                      # Band/song analysis
│   ├── profile_seed_from_playlist.txt
│   └── profile_training_prompt.txt
├── build-tools/                   # build_exe.sh, build_dist.sh, run_tests*.sh, start.sh, …
├── build_assets/                  # spotyvibe.ico (PyInstaller icon)
├── documentation/                 # User & technical docs
│   ├── UserManual.md, TechnicalManual.md, ProjectLayout.md
│   ├── ModelRecommendations.md, MCPServers.md
│   ├── help.en.md, help.de.md, help.jp.md      # in-app help (must stay in sync)
│   ├── guides/                    # Setup guide markdown (openai, spotify)
│   ├── prompts/                   # Documentation prompts
│   └── assets/                    # Screenshots & guide assets
├── evaluation/                    # Quality / cost / latency eval harness
│   ├── run_evaluation.py, harness.py, scenario.py, reporting.py,
│   ├── README.md, settings.ini.example
│   └── results/, sandbox/
├── spotyvibe/                     # Python package (wheel entry point)
│   ├── __init__.py, __main__.py
│   └── cli.py                     # Console entry point (`spotyvibe` command)
└── data/                          # music_profile.json template + RAG corpus
    └── rag_corpus/                # Pre-built corpus shards
```

## Architecture

- **Single-page Flask app** — `base.html` includes partials; JS modules handle SPA behavior.
- **No build step** — vanilla JS (ES modules), modular CSS, no bundler.
- **Spotify isolation** — all API calls in `core/src/playlist.py`.
- **OpenAI isolation** — all calls via `core/src/openai_http.py` (raw HTTP).
- **macOS/Linux packaging** — `pyproject.toml` + hatchling builds a `.whl`; `spotyvibe/cli.py` is the entry point.

## Maintenance

Before creating a commit that adds, removes, or renames files/dirs, run:

```bash
tree -L 3 -I "node_modules|__pycache__|.git|venv|dist|build|css-review" --dirsfirst
```

and update the tree above accordingly.
