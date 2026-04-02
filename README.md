# SpotyVibe 🎵

An AI-powered music discovery tool that creates personalised Spotify playlists based on your taste.

---

## What Is This?

SpotyVibe uses **artificial intelligence** to learn what kind of music you enjoy and then generates a playlist of tracks tailored to your preferences (**playlist size is configurable**; default: 10). The tracks are automatically added to a private Spotify playlist that you can listen to right away.


The interface features a premium dark aesthetic with frosted dark-glass panels and luminous green accents — designed for an immersive, high-end music discovery experience. A **theme switcher** at the top of the page lets you choose between two animated background styles:

- **Equalizer** — animated frequency-spectrum bars with spring physics and beat simulation (the default)
- **Pulse** — expanding concentric rings with floating particles and bass-drop effects

Your theme preference is saved in the browser and restored on next visit.

The more you use it, the smarter it gets — every time you like or dislike a suggestion, the AI refines its understanding of your taste and delivers better recommendations next time.

## How It Works

1. **Describe your taste** — Fill in structured sections (core description, must-haves, soft preferences, things to avoid) so the AI understands exactly what you want.
2. **Generate a playlist** — The AI creates a personalised set of track suggestions (based on your configured playlist size), each shown with its Spotify album cover, and adds them to your Spotify playlist.

3. **Give feedback** — Like tracks you enjoy, dislike ones you don't. The AI learns from every interaction.
4. **Repeat** — Each run produces fresh recommendations that get more accurate over time.

## Features

- **AI-powered suggestions** with configurable OpenAI model selection (GPT-5.4, GPT-5.4-mini, GPT-4.1, GPT-4.1-mini, GPT-4.1-nano).
- **Structured taste profile** — accordion-style editor with separate sections for core description, must-haves, soft preferences, and things to avoid. Existing profile data is pre-filled for easy editing. Save changes directly or use **AI Profile Update** to let GPT refine your input.
- **Profile import/export** — import a full profile JSON (the current profile is automatically backed up to the history file) or export your current active profile as a JSON download. Import/Export/Reset controls appear below the "Last trained" status line when the profile editor is open.
- **Reset to history** — revert your Music Profile to the previous saved version (one-step undo).
- **Collapsible UI sections** — every major component (Music Profile, Band/Song Analysis, Audio Filters, Discover Music, Refine Playlist, History) is collapsible/expandable. Each section header includes a short description and the entire header area is clickable to toggle.

- **Album artwork** displayed alongside each suggested track.
- **Spotify integration** — auto-creates and manages a private playlist.
- **Cancel generation** — stop an in-progress playlist generation at any time with the ⛔ Cancel button.
- **Use tracks now** — if GPT gets stuck repeating songs, use the "▶ Use X tracks now" button to create the playlist immediately with however many tracks have already been verified.
- **Automatic loop protection** — if GPT ignores the exclusion list for 3 consecutive batches, the loop stops automatically and creates the playlist with whatever was found. Each retry sends an explicit warning listing the exact tracks GPT suggested that were already known.
- **New Artist % setting** — configurable percentage (1–100, default 30%) of each batch that must come from artists not yet in your history, pushing GPT to explore new territory.
- **Model-specific GPT prompts** — each model family gets a tailored system prompt optimised for its strengths (e.g., candidate-pool reasoning for GPT-5.4, step-by-step validation for GPT-4.1). A consolidated JSON deny list ensures exclusion accuracy across all models.
- **Band/Song Analysis** — AI-powered analysis of any band or song, returning genre, style, characteristics, GPT-estimated audio features (energy, danceability, etc.), and copy-paste profile suggestions (`core/analysis.py`).
- **Internationalization (i18n)** — full English and German UI with a language picker in the header; translations in `static/i18n/en.json` and `de.json`. A separate **ChatGPT Language** setting controls the language used for GPT communication.
- **GPT Audio Feature Constraints** — optional audio filters (energy, valence, tempo, danceability, acousticness) in the OpenAI section are injected directly into the GPT prompt, guiding the AI to suggest tracks matching the desired mood and feel.
- **Feedback Reasons in prompts** — recent like/dislike reasons are summarized and sent to GPT so it can learn *why* you liked or disliked a track, not just which ones.
- **Multiple Playlists / Playlist Naming** — create new, append, or replace playlists with custom name templates supporting `{date}` and `{style}` tokens.
- **Refine Playlist** — load an existing Spotify playlist and review tracks one-by-one with like, dislike, or dismiss actions to refine your taste profile and clean up the playlist.
- **Inline loading spinners** — both playlist generation and playlist loading show a centered spinner with live progress messages inside the section, keeping the UI clean and focused.
- **Run History** — the last 5 generation runs are saved (`core/history.py`); each entry shows date/time, track count, and a playlist link. Expand any entry to see the full list of tracks added.
- **Previews and Richer Track Cards** — album art, inline Spotify preview playback, and direct links to track, artist, and album on Spotify. Track cards glow green on hover. The preview player uses a three-zone bottom-bar layout: Spotify player (centered), file-cabinet register-tab action buttons (👍 👎 ✕), and a sliding feedback form that expands to the right screen edge.
- **Hard Cost Guardrails** — max 20 GPT calls per run, max 3 consecutive empty batches, and field-level character limits to prevent runaway usage.
- **Better SSE Resilience** — run state is persisted by `run_id`; a recovery endpoint lets the client reconnect after a network drop.
- **Cached Model List** — `/api/settings/models` is cached with a 5-minute TTL to reduce API calls.
- **Security hardening** — profile import validation, server-side request size limits, character sanitization, prompt injection hardening, Android WebView download restriction, and Spotify search query sanitization.
- **Debug mode (desktop only)** — logs all GPT communication to a file for prompt analysis and tuning (not available in the Android APK).
- **Mobile responsive** — the UI automatically adapts to tablet and phone screens with touch-friendly controls and bottom-sheet modals, no app install required.
- **Android APK ready** — project includes Chaquopy-based Android scaffolding for building a self-contained APK that bundles the full Flask app, Python runtime, and all dependencies. The Android build pins Android Gradle Plugin 8.2.2, Kotlin 1.9.22, Chaquopy 15.0.1, compile/target SDK 34, and Python 3.10 with pinned pip dependencies. Spotify OAuth works seamlessly on Android via deep-link callback (`spotyvibe://callback`); add this URI alongside `http://127.0.0.1:5000/callback` in your Spotify Developer Dashboard. Emulator testing is supported via the `x86_64` ABI filter.
- **Android Onboarding Flow** — multi-page swipeable onboarding for first-time Android users covering intro, credentials, and Spotify connection.
- **Android Packaging Polish** — share/import flows, external Spotify links, and improved OAuth deep linking.
- **Testing & CI** — pytest suite with GitHub Actions CI on push and PR (`.github/workflows/ci.yml`).

## Project Structure (key paths)

| Path | Purpose |
|---|---|
| `app.py` | Flask application entry point |
| `core/analysis.py` | Band/song analysis logic |
| `core/history.py` | Run history tracking |
| `prompts/analysis_prompt.txt` | GPT prompt template for band/song analysis |
| `static/i18n/en.json`, `de.json` | UI translation files |
| `.github/workflows/ci.yml` | GitHub Actions CI pipeline |
| `tests/` | pytest test suite |

## Quick Start

1. Install Python 3.10+ and run `pip install -r requirements.txt`.
2. Start the app with `python app.py` and open <http://127.0.0.1:5000>.
3. Enter your API keys (OpenAI + Spotify) via **⚙️ → Credentials**.
4. Connect your Spotify account and start generating playlists!

---

## Build a Windows executable (PyInstaller)

SpotyVibe includes a desktop-only PyInstaller setup which builds a **one-folder** Windows executable.

```bash
pip install -r requirements.txt
python build_assets/make_ico.py
python -m pytest tests/ -v


# One-folder build
pyinstaller --noconfirm --clean spotyvibe.spec

# (Optional) one-file build
pyinstaller --noconfirm --clean spotyvibe_onefile.spec

# Or use the helper script:
#   ./build-tools/build_exe.sh --package
#   ./build-tools/build_exe.sh --full
```


Output:
- One-folder: `dist/spotyvibe/spotyvibe.exe`
- One-file: `dist/spotyvibe_onefile.exe`


Notes:
- The executable runs the same local server at `http://127.0.0.1:5000`.
- On launch, the desktop executable auto-opens your default browser to the UI.
- Credentials are **not** bundled; they remain in `%LOCALAPPDATA%\spotyvibe\.credentials`.
- The one-file build has a slower cold start (it extracts bundled files on launch).



---


## Documentation

| Document | Description |
|---|---|
| **[User Manual](documentation/UserManual.md)** | Step-by-step setup guide and usage instructions for end users. |
| **[Technical Manual](documentation/TechnicalManual.md)** | Architecture overview, component interactions, and developer reference. |

---

## License

This project is for personal use and educational purposes.
