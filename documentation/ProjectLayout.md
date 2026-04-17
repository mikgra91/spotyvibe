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
│   ├── localised_docs.py          # Language-aware Markdown resolver (Wave 5)
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
│   ├── taste_dashboard.html       # Taste dashboard charts panel
│   ├── theme_switcher.html, settings_gear.html, toast.html
│   └── modals/                    # credentials, help, quickstart, settings,
│       │                          #   privacy, setup_guide_overlay
│       ├── privacy_modal.html     # "What gets sent where?" data-flow table
│       ├── setup_guide_overlay.html # Full-screen setup guide detail overlay
│       └── preset_manager_modal.html # Preset manager sub-screen
├── frontend/static/favicon.ico    # Browser favicon
├── frontend/static/css/           # Modular CSS (no bundler)
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
│   ├── playlist_seed.css          # Playlist seed modal + draft banner
│   ├── rationale_chips.css        # Rationale chip styling
│   ├── taste_dashboard.css        # Taste dashboard charts
│   ├── tips.css                   # Feature discovery tip toasts
│   ├── provider.css               # Provider dropdown + credential rows
│   ├── cost_estimate.css          # Cost-estimate card + footnote
│   ├── voice.css                  # Microphone button states
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
│   ├── playlist_seed.js           # Playlist-seeded profile flow
│   ├── rationale.js               # Rationale chip rendering
│   ├── taste_dashboard.js         # SVG taste visualisation dashboard
│   ├── tips.js                    # Feature discovery tip toasts
│   ├── provider.js                # Custom LLM endpoint management
│   ├── cost_estimate.js           # Token & cost estimator widget
│   ├── voice.js                   # Web Speech API voice input
│   └── theme-switcher.js, theme-equalizer.js, theme-pulse.js,
│       theme-spectrum.js, theme-starfield.js
├── frontend/static/i18n/          # en.json + de.json + jp.json
├── frontend/tests/                # Playwright tests
│   ├── test_frontend.py           # Main frontend integration tests
│   └── test_profile_integration.py # Profile switch/create/delete state reset tests
├── prompts/                       # AI prompt templates
├── android/                       # Chaquopy APK
├── build-tools/                   # build_exe.sh, build_apk.sh, build_dist.sh, start.sh
├── documentation/                 # UserManual, TechnicalManual, help.en.md, help.de.md
│   ├── guides/                    # Setup guide markdown (openai, spotify)
│   └── assets/guides/             # Guide screenshot placeholders
├── spotyvibe/                     # Python package (wheel entry point)
│   ├── __init__.py, __main__.py
│   └── cli.py                     # Console entry point (spotyvibe command)
└── data/                          # music_profile.json template
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
