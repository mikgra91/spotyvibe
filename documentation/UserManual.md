# User Manual

Setup and usage guide for **SpotyVibe** — your AI-powered Spotify playlist generator.

---

## Prerequisites

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **Spotify Premium account** — required; Spotify's Web API needs Premium to create playlists.
- **Internet connection.**
- API keys:

| Key | Get it from |
|---|---|
| OpenAI API key | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Spotify Client ID + Secret | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) |

> When registering the Spotify app, add the redirect URI:
> - `http://127.0.0.1:5000/callback`

> **💰 Cost:** The OpenAI API is paid. `gpt-5.4-mini` is affordable; larger models cost significantly more. See [OpenAI Pricing](https://platform.openai.com/docs/pricing). SpotyVibe can also be pointed at free local runtimes (Ollama, LM Studio) — see [Custom AI Provider](#custom-ai-provider).

---

## Install & Run

### Windows

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.

### macOS / Linux

1. Install Python 3.10+ (`brew install python@3.12` / `sudo apt install python3 python3-pip`).
2. Download `spotyvibe-*.whl` from the latest [GitHub Release](https://github.com/mikgra91/spotyvibe/releases).
3. Run:
   ```bash
   pip install spotyvibe-*.whl
   spotyvibe
   ```

Press **Ctrl+C** to stop.

> **macOS port 5000:** AirPlay Receiver uses this port. If SpotyVibe fails to start, disable it: **System Settings → General → AirDrop & Handoff → AirPlay Receiver**.

### Windows executable (optional)

```bash
bash build-tools/build_exe.sh --package    # dist/spotyvibe/spotyvibe.exe
bash build-tools/build_exe.sh --full       # dist/spotyvibe_onefile.exe
```

The executable opens a native window — no external browser. Credentials stay in the OS keychain.

---

## First-Time Setup

When you open SpotyVibe, a **Getting Started** card appears on the home page with a 5-item checklist (enter keys → connect Spotify → build profile → generate a playlist → give feedback). Each item auto-checks as you complete it, and the **Jump** button scrolls to the relevant section.

### 1. Enter API keys

☰ → **🔑 Credentials**. Paste your OpenAI API key, Spotify Client ID, and Secret. Keys are stored in the OS keychain (Windows Credential Manager / macOS Keychain).

### 2. Pick a model

☰ → **⚙️ Settings**. Default is `gpt-5.4-mini`. Other options: `gpt-5.4`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`.

The Settings modal also exposes:

- **Playlist Size** — 5–30 tracks (default: 10).
- **New Artist %** — 1–100 (default: 30). Higher = more aggressive exploration.
- **ChatGPT Language** — language the AI uses in its replies (independent of the UI language).
- **Display size** — Small / Default / Large. Scales the whole UI.
- **Debug mode** — desktop only; logs GPT requests to `%LOCALAPPDATA%\spotyvibe\debug.log`.

### 3. Choose UI language

Language picker in the header: **English**, **Deutsch**, or **日本語**. Persists in your browser.

### 4. Choose a theme

Below the title: **Equalizer** (default — frequency bars) or **Pulse** (concentric rings). Saved to browser localStorage.

### 5. Connect Spotify

After saving credentials, click **Connect to Spotify** in the banner. A popup handles the OAuth handshake. Disconnect any time via ☰ → **🔌 Disconnect Spotify**.

> If you see `403 Forbidden` during generation, the app auto-disconnects. Just click **Connect to Spotify** to reconnect.

### 6. Build a music profile

The UI has two provider sections:

- **OpenAI** — profile editor, AI profile update, Band/Song Analysis.
- **Spotify** — Discover Music, Refine Playlist, History.

Each section header is clickable to expand/collapse.

In **Music Profile**, pick or create a profile from the dropdown (`+ Create new Profile`). Profiles are independent JSON files — great for different moods or family members.

Click **Edit profile** to open four accordion sections:

- **💬 Describe Your Vibe** — free-text; the AI routes statements to the correct section automatically.
- **🎵 Core Description** — foundation: genre, mood, reference artists.
- **✅ Must Have** — hard requirements (one per line).
- **💡 Soft Preferences** — nice-to-haves.
- **🚫 Avoid** — disqualifiers.

Then either:

- **Save** — stores your input as-is. Works even with empty fields.
- **AI Profile Update** — GPT analyses and refines your input. Requires Core Description or Vibe text.

The **Profile Strength** meter (visible while editing) shows five dimensions plus a % score and highlights what to improve next. Green glow at ≥ 60%.

#### Import / Export / Reset

Appear under **Edit profile** mode:

- **⬆ Import** — replace active profile from a JSON file (10 MB cap; old profile auto-backed up).
- **⬇ Export** — download active profile as `spotyvibe_profile.json`.
- **↩ Reset to history** — one-step undo (swaps with the backup).
- **🗑 Delete** — permanent removal of the profile + history.

---

## Quick Start Tour (optional)

☰ → **🚀 Quick Start** opens a 3-step storyboard walkthrough scoped to the active provider section (OpenAI or Spotify). Each step has a short description, a key-actions checklist, and an animated mockup. Dismiss preference is per-provider.

---

## Generating a Playlist

Expand **Discover Music** in the Spotify section.

### Quick vs Advanced mode

- **Quick** (default) — playlist size slider, exploration slider, Generate button.
- **Advanced** — all controls: playlist mode, emerging artists, audio filters, new artist %, preset picker.

### Exploration slider

5 notches, each with a preset (playlist size, new-artist %, emerging toggle, temperature):

| Notch | Label | New artist % | Emerging | Temp |
|---|---|---|---|---|
| 1 | Familiar | 10 | no | 0.5 |
| 2 | Mostly known | 25 | no | 0.7 |
| 3 | Balanced | 50 | no | 0.8 |
| 4 | Mostly new | 70 | no | 0.9 |
| 5 | Adventurous | 90 | yes | 1.0 |

Hand-editing a field in Advanced mode to an off-preset value shows a **Custom** state with a dashed thumb.

### Presets

The preset dropdown ships with **Safe picks**, **Balanced**, and **Deep discovery**. Save your own via "💾 Save current as preset…". Manage (rename, delete, reorder, import, export) via ☰ → **🎛 Manage presets**.

### Playlist mode

| Mode | Behaviour |
|---|---|
| Default | Reuses or creates the "SpotyVibe Playlist" |
| Create new | Always creates a new playlist |
| Append | Adds to an existing playlist |
| Replace | Clears an existing playlist first |

Custom names accept `{date}` and `{style}` tokens.

### Audio filters (Advanced)

Collapsible sub-panel. Set min/max for **energy**, **valence**, **tempo**, **danceability**, **acousticness**. A live hint renders as you type (e.g. "↳ Energetic to Intense"). Filters are injected into the GPT prompt, not post-filtered. **✕ Clear all** resets everything.

The fastest way to set filters is from a **Band/Song Analysis** result — each feature row has a **⇒ Filter** button (±10 %, ±15 BPM for tempo), and **⇒ Use All as Filters** applies all at once.

### Emerging artists only

Checkbox. When on:

- GPT is told to only suggest artists that debuted in the last 6 months.
- Tracks are also validated against Spotify release dates post-search.
- The final playlist may contain **fewer** tracks than requested (only emerging artists survive).

### Running the generation

Click **▶ Generate & Create Playlist**. A spinner appears in-section with live progress messages. When done, the tracks render below with album art, reason text, and Spotify links — and are added to the playlist.

### Stopping early

- **⛔ Cancel** — abort and discard. No playlist changes.
- **▶ Use X tracks now** — stop now and create the playlist with whatever has been verified. Label updates live.

---

## Reviewing Suggestions

Each track card shows album art, artist, title, reason, quick links (🎵 track, 🎤 artist, 💿 album), and glows green on hover. Clicking the album art opens the preview overlay.

**Preview overlay** — three zones:

1. **Player** (centered) — Web Playback SDK on Premium + Widevine/FairPlay-capable devices (full-track playback with 👍 / 👎 quick buttons next to the transport). Iframe fallback (~30 s clips) otherwise. An **autoplay** toggle remembers your choice.
2. **Action buttons** — 💬 **Feedback** or 🗑 **Delete**.
3. **Feedback panel** — artist, track, reason + dual submit (👍 Like / 👎 Dislike).

### 💬 Feedback

- **👍 Like** — adds the track to your liked list, marks the artist as confirmed. Track stays in the playlist.
- **👎 Dislike** — records a negative signal **and** removes the track from the Spotify playlist.

> **Tip:** Clear the *Track* field and leave only the artist to reject the entire artist.

### 🗑 Delete

Removes from the Spotify playlist without touching your taste profile. Use for tracks you're neutral about.

### Persistent song list

Tracks persist across page reloads (capped at 100). A counter shows the current total. Like/Dislike/Delete permanently remove from the saved list. If the list is full, generation is blocked until you make room.

---

## Refine Playlist

Load any of your Spotify playlists and review tracks one by one.

1. Expand **🔄 Refine Playlist**.
2. Pick a playlist and click **🔄 Load Playlist**.
3. For each track: 💬 Feedback (Like keeps, Dislike removes + records), 🗑 Delete (removes without feedback), or click the album art for the same preview player.

Useful for cleaning up old playlists and teaching SpotyVibe retroactively.

---

## Run History

Collapsible **History** panel below Discover Music. Records the last 5 runs with date, track count, and playlist link. Click a row to expand the full track list. Refreshes automatically when a new run completes while open.

---

## Band/Song Analysis

Inside the OpenAI section. Enter an artist (+ optional track) and click **Analyze**. Returns genre, style tags, characteristics, GPT-estimated audio features (energy, valence, danceability, etc.), and copy-paste profile suggestions. Use the **⇒ Filter** buttons to populate audio filters directly.

---

## Explainable Recommendations

Each suggested track shows 1–2 rationale chips: `matches '<trait>'`, `similar to <Artist>`, `released YYYY`, `discovery pick`, `matches energy/tempo`.

## Taste Dashboard

Collapsible **Your taste at a glance** below the profile editor. Shows three charts once you have ≥ 10 unique tracks in history:

- **Top genres** — donut chart (Spotify artist data).
- **Energy × valence** — scatter plot (GPT estimates — noted below the chart).
- **Decades** — bar chart (Spotify album data).

## Seed Profile from Playlist

Create a taste profile directly from an existing Spotify playlist: profile editor → **Seed from playlist** (also available during onboarding). SpotyVibe analyses artists, genres, and audio features to draft a profile; review and save.

## Cost Estimator

Live cost estimate in the Settings modal and under the Generate button. Approximates token counts and looks up pricing from the shipped price table. Models without pricing data show "estimate unavailable".

## Voice Input (desktop only)

🎤 **Speak** button inside "Describe Your Vibe". Uses the browser's Web Speech API — no audio leaves your device.

## Custom AI Provider

Settings → **Provider**:

| Provider | API key | Notes |
|---|---|---|
| OpenAI | yes | Default |
| Ollama (local) | no | Runs on your machine; free |
| LM Studio (local) | no | Runs on your machine; free |
| Groq | yes | Cloud, fast inference |
| OpenRouter | yes | Multi-model proxy |
| Custom | depends | Any OpenAI-compatible `/v1` URL |

**🔁 Fetch models** populates the model dropdown from the provider's `/v1/models`. If that fails, click ✎ to type a model name manually.

---

## Mobile

Works in any mobile browser. Tablets get smaller headings and padding; phones stack controls vertically, open modals as bottom sheets, and enforce a 44 px minimum touch target.

---

## Data Files

All persistent data lives outside the project:

| File | Location | Purpose |
|---|---|---|
| Credentials | OS keychain (fallback: `%LOCALAPPDATA%\spotyvibe\.credentials`) | API keys |
| Settings | `%LOCALAPPDATA%\spotyvibe\settings.conf` | Prefs (model, size, language, debug, etc.) |
| Profiles | `%LOCALAPPDATA%\spotyvibe\profiles\<uuid>.json` | Each profile + `.history.json` backup |
| Spotify token | `%LOCALAPPDATA%\spotyvibe\.spotify-cache` | Cached OAuth token |
| Run history | `%LOCALAPPDATA%\spotyvibe\run_history.json` | Last 5 runs |
| Debug log | `%LOCALAPPDATA%\spotyvibe\debug.log` | Desktop only, when debug mode is on |

Reinstall or update without losing anything.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Spotify credentials missing" | ☰ → Credentials; enter Client ID and Secret. |
| "Please train your taste profile first" | Use the OpenAI section to describe your taste before generating. |
| Spotify auth fails with "INVALID_CLIENT" | Check Client ID/Secret and the redirect URIs in your Spotify Developer Dashboard. |
| 403 Forbidden during generation | Session expired / permissions revoked. Click **Connect to Spotify** to reconnect. |
| "OpenAI API key is not configured" | ☰ → Credentials; enter your OpenAI key. |
| GPT keeps repeating songs and stops early | Loop protection kicked in (3 all-filtered batches). Use **▶ Use X tracks now** earlier, or expand your profile with new styles. |
| "GPT could not generate any new tracks" | History too large. Add new styles or genres to the profile. |
| Most tracks "not found on Spotify" | GPT suggested obscure tracks. Try again — each run is different. |
| "python-dotenv could not parse statement" | Credentials file corrupt. Re-save via ☰ → Credentials. |
| Audio filters remove all tracks | Ranges are too narrow. Widen or clear them. |
| App won't start | Ensure `pip install -r requirements.txt` and Python 3.10+. |
