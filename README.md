# SpotyVibe 🎵

AI-powered music discovery. Describe what you like — SpotyVibe asks an LLM for fitting tracks, verifies each on Spotify, and drops them into a private playlist. Every like or dislike sharpens the next run.

---

## How it works

1. **Describe your taste** — core description, must-haves, soft preferences, things to avoid.
2. **Generate** — the AI picks tracks; SpotyVibe adds them to your playlist.
3. **Rate** — 👍 / 👎 from the preview player or each track card.
4. **Repeat** — each run gets better as the profile grows.

---

## Features

- **Configurable LLM** — default is **Gemini 3.1 Flash Lite via OpenRouter** (cheapest/fastest of the recommended models). Switch to gpt-5.4-mini, Claude Haiku 4.5, Ollama, LM Studio, or any OpenAI-compatible endpoint from Settings → Provider.
- **Structured taste profile** with multi-profile support, import/export, one-step undo, and an AI-seed-from-playlist option.
- **Exploration slider** (5 notches) that adjusts playlist size, new-artist %, emerging-artists toggle, and temperature in one pull. Advanced mode exposes every knob individually.
- **Audio feature filters** (energy, valence, tempo, danceability, acousticness) injected into the GPT prompt. Populate them in one click from a Band/Song Analysis result.
- **Emerging artists only** — restrict suggestions to artists who debuted in the last 6 months.
- **Filter AI-generated music** (opt-in) — drop tracks by artists on a community-maintained blocklist of AI-generated acts, matched on Spotify artist ID. Blocklist data from [`CennoxX/spotify-ai-blocker`](https://github.com/CennoxX/spotify-ai-blocker) (MIT).
- **Preview player** — Spotify Web Playback SDK on Premium (full tracks, 👍 / 👎 quick buttons, autoplay toggle) with an iframe fallback (~30 s clips).
- **Feedback-aware prompts** — recent like/dislike reasons are summarised and fed back to GPT.
- **Rationale chips** on every suggestion: `matches '<trait>'`, `similar to <Artist>`, `released YYYY`, `discovery pick`, `matches energy/tempo`.
- **Taste dashboard** — genre donut, energy × valence scatter, decade bar, once you have ≥ 10 unique tracks.
- **Discover Artists** — surface new artists matching your taste (1–10 at a time), each with a few representative tracks; apply the Spotify-verified ones straight to a playlist.
- **Refine Playlist** — load any existing Spotify playlist and curate it track by track.
- **Run history** — last 5 runs with expandable track lists.
- **Getting Started checklist** — a floating home-page card that auto-checks setup steps as you complete them.
- **i18n** — English, Deutsch, 日本語 (UI and AI response language are independent settings).
- **Display size** — three-step UI scale (Small / Default / Large).
- **Two animated themes** — Equalizer (default) or Pulse. `prefers-reduced-motion` disables both.
- **Mobile-responsive**, PyInstaller EXE, and Python wheel distributions.
- **Tests & CI** — pytest + Playwright, running in parallel on every push.

---

## Install & Run

| Platform | Command |
|---|---|
| Windows | `pip install -r requirements.txt && python app.py` |
| macOS / Linux | `pip install spotyvibe-*.whl && spotyvibe` |

Open <http://127.0.0.1:5000> (desktop opens automatically).

> **Prerequisites:** Python 3.10+, Spotify Premium, and API keys from:
> - **[OpenRouter](https://openrouter.ai/keys)** (default — GPT-5.4-mini route) OR [OpenAI](https://platform.openai.com/api-keys) (alternative)
> - **[Spotify Developer](https://developer.spotify.com/dashboard)** (always required)
>
> Register the redirect URI on the Spotify app: `http://127.0.0.1:5000/callback`.

> **macOS port 5000:** AirPlay Receiver uses this port by default. Disable it in **System Settings → General → AirDrop & Handoff** if SpotyVibe can't bind.

> **💰 Cost:** Gemini 3.1 Flash Lite via OpenRouter costs roughly ~$0.015–0.02 per playlist; `gpt-5.4-mini` ~$0.04 and Claude Haiku 4.5 ~$0.08. Free local providers (Ollama, LM Studio) are supported via Settings → Provider. See [`evaluation/model-performance-result.md`](evaluation/model-performance-result.md) for the full verdict.

---

## Build from source

```bash
bash build-tools/build_exe.sh --package    # Windows EXE (one-folder)
pip install build && python -m build --wheel   # macOS/Linux wheel
```

Artifacts attach to each [GitHub Release](../../releases).

---

## Documentation

| Document | Description |
|---|---|
| [User Manual](documentation/UserManual.md) | End-user setup and usage |
| [Technical Manual](documentation/TechnicalManual.md) | Architecture and developer reference |

---

## License

Personal / educational use.
