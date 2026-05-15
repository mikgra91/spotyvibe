# Setup guide screenshots

These images are served by the in-app setup guides (reachable from the onboarding wizard and the help modal). They are manually captured from the live OpenAI and Spotify developer dashboards.

| Guide | Steps | Files |
|-------|-------|-------|
| **OpenRouter API key (G0 — new default)** | 4 | `openrouter/step1_signin.png`, `openrouter/step2_keys.png`, `openrouter/step3_create.png`, `openrouter/step4_credits.png` |
| OpenAI API key (G1) | 3 | `openai/step1_signin.png`, `openai/step2_sidebar.png`, `openai/step3_create.png` |
| Spotify developer app (G2) | 4 | `spotify/step1_dashboard.png`, `spotify/step2_create.png`, `spotify/step3_redirect.png`, `spotify/step4_secret.png` |
| Python install — macOS (G3) | 4 | `python-macos/step1_homebrew.png`, `python-macos/step2_install.png`, `python-macos/step3_verify.png`, `python-macos/step4_venv.png` |
| Python install — Linux (G4) | 3 | `python-linux/step1_update.png`, `python-linux/step2_install.png`, `python-linux/step3_verify.png` |

When a Spotify or OpenAI dashboard redesign renders a screenshot stale, replace the file in-place (same filename). Do not rename — the guide markdown under `documentation/guides/*.md` references these paths.

> **Filename convention for translations:** Each guide has an English source (`<slug>.en.md`) and optional translations (`<slug>.de.md`, etc.). The `localised_docs.py` resolver tries `<slug>.<lang>.md` first, then falls back to `<slug>.en.md`.

> **Placeholders:** Every file is currently an 800×450 dark PNG with a dashed outline — a visual "📸 Screenshot coming soon" marker. Replace each one in-place with an actual dashboard screenshot when available. Do not rename files — the guide markdown references these exact paths.

