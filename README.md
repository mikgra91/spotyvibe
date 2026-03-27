# SpotyVibe 🎵

An AI-powered music discovery tool that creates personalised Spotify playlists based on your taste.

---

## What Is This?

SpotyVibe uses **artificial intelligence** to learn what kind of music you enjoy and then generates a playlist of 30 tracks tailored to your preferences. The tracks are automatically added to a private Spotify playlist that you can listen to right away.

The interface features a premium dark aesthetic with frosted dark-glass panels and luminous green accents — designed for an immersive, high-end music discovery experience. A **theme switcher** at the top of the page lets you choose between two animated background styles:

- **Equalizer** — animated frequency-spectrum bars with spring physics and beat simulation (the default)
- **Pulse** — expanding concentric rings with floating particles and bass-drop effects

Your theme preference is saved in the browser and restored on next visit.

The more you use it, the smarter it gets — every time you like or dislike a suggestion, the AI refines its understanding of your taste and delivers better recommendations next time.

## How It Works

1. **Describe your taste** — Fill in structured sections (core description, must-haves, soft preferences, things to avoid) so the AI understands exactly what you want.
2. **Generate a playlist** — The AI creates 30 personalised track suggestions, each shown with its Spotify album cover, and adds them to your Spotify playlist.
3. **Give feedback** — Like tracks you enjoy, dislike ones you don't. The AI learns from every interaction.
4. **Repeat** — Each run produces fresh recommendations that get more accurate over time.

## Features

- **AI-powered suggestions** with configurable OpenAI model selection.
- **Structured taste profile** — accordion-style editor with separate sections for core description, must-haves, soft preferences, and things to avoid. Existing profile data is pre-filled for easy editing. Save changes directly or use **AI Profile Update** to let GPT refine your input.
- **Album artwork** displayed alongside each suggested track.
- **Spotify integration** — auto-creates and manages a private playlist.
- **Cancel generation** — stop an in-progress playlist generation at any time with the ⛔ Cancel button.
- **Use tracks now** — if GPT gets stuck repeating songs, use the "▶ Use X tracks now" button to create the playlist immediately with however many tracks have already been verified.
- **Automatic loop protection** — if GPT ignores the exclusion list for 3 consecutive batches, the loop stops automatically and creates the playlist with whatever was found. Each retry sends an explicit warning listing the exact tracks GPT suggested that were already known.
- **New Artist % setting** — configurable percentage (1–100, default 30%) of each batch that must come from artists not yet in your history, pushing GPT to explore new territory.
- **Hardened GPT prompt** — Bear Ghost is set as the explicit primary style reference; a "Hard Negative Rules" section disqualifies generic or predictable tracks; GPT emits a self-validation block to force it to check its own output before finalising.
- **Debug mode** — logs all GPT communication to a file for prompt analysis and tuning.
- **Mobile responsive** — the UI automatically adapts to tablet and phone screens with touch-friendly controls and bottom-sheet modals, no app install required.
- **Android APK ready** — project includes Chaquopy-based Android scaffolding for building a self-contained APK that bundles the full Flask app, Python runtime, and all dependencies. The Android build pins Android Gradle Plugin 8.2.2, Kotlin 1.9.22, Chaquopy 15.0.1, compile/target SDK 34, and Python 3.10 with pinned pip dependencies. Spotify OAuth works seamlessly on Android via direct navigation (popups are not supported in WebView). Emulator testing is supported via the `x86_64` ABI filter.

## Quick Start

1. Install Python 3.10+ and run `pip install -r requirements.txt`.
2. Start the app with `python app.py` and open <http://127.0.0.1:5000>.
3. Enter your API keys (OpenAI + Spotify) via **⚙️ → Credentials**.
4. Connect your Spotify account and start generating playlists!

---

## Documentation

| Document | Description |
|---|---|
| **[User Manual](UserManual.md)** | Step-by-step setup guide and usage instructions for end users. |
| **[Technical Manual](TechnicalManual.md)** | Architecture overview, component interactions, and developer reference. |

---

## License

This project is for personal use and educational purposes.
