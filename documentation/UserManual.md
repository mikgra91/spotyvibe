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
| **OpenRouter API key** (recommended default) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| OpenAI API key (alternative) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Spotify Client ID + Secret | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) |

> SpotyVibe ships with **OpenRouter + DeepSeek V4 Flash** as the default provider/model. Switched 2026-05-14 after extensive eval: best quality-per-$ measured. OpenAI is still supported — switch via Settings → Provider.

> When registering the Spotify app, add the redirect URI:
> - `http://127.0.0.1:5000/callback`

> **💰 Cost:**
> - **DeepSeek V4 Flash via OpenRouter (paid)** — ~$0.015 per playlist; deposit €5-10 on [openrouter.ai/credits](https://openrouter.ai/credits) lasts ~330-660 playlists.
> - **DeepSeek V4 Flash :free** — pick `deepseek/deepseek-v4-flash:free` in the model dropdown for **zero-cost** usage. Capped at 200 requests/day aggregate per OpenRouter account (≈ 40-65 SpotyVibe playlists/day, then resets at midnight UTC).
> - **OpenAI gpt-5.4-mini** — ~$0.05/playlist. See [OpenAI Pricing](https://platform.openai.com/docs/pricing).
> - **Free local runtimes** (Ollama, LM Studio) — zero cost; quality varies. See [Custom AI Provider](#custom-ai-provider).

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

☰ → **🔑 Credentials**. Paste your **OpenRouter API key** (or OpenAI key if you switched providers), Spotify Client ID, and Secret. Keys are stored in the OS keychain (Windows Credential Manager / macOS Keychain).

> The credential field is labelled `OPENAI_API_KEY` for historical reasons but accepts any provider's bearer token — what matters is the active `PROVIDER_PRESET` and `LLM_BASE_URL`.

### 2. Pick a model

☰ → **⚙️ Settings**. Default is `deepseek/deepseek-v4-flash` (OpenRouter). To run for free, switch the model to `deepseek/deepseek-v4-flash:free`. To switch to OpenAI, change **Provider** to `openai` — the dropdown then offers `gpt-5.4-mini`, `gpt-5.4`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`.

The mode-strategy switch (Fast / Best / Auto / Custom) was removed on 2026-05-14: the DeepSeek default matches gpt-5.4's quality at 1/10 the cost, eliminating the trade-off the picker used to manage. Pick a model — that's it.

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

The header carries a small **Spotify status pill** with a coloured dot — green when connected, red when disconnected, grey while the status is still being checked. The pill refreshes automatically when you switch back to the tab and click-toggles connect/disconnect like the menu item.

> If you see `403 Forbidden` during generation, the app auto-disconnects. Just click **Connect to Spotify** to reconnect.

### 6. Build a music profile

The UI has two provider sections:

- **OpenAI** — profile editor, AI profile update, Band/Song Analysis.
- **Spotify** — Discover Tracks, Discover Artists, Refine Playlist, History.

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

Expand **Discover Tracks** in the Spotify section.

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

When you hand-edit the **New Artist %** field to a value that no longer matches the active preset, a small **CUSTOM** badge appears next to the input. The active preset itself is untouched — save the deviation as a new preset (or update the existing one) to make it persistent.

### Artist coverage

SpotyVibe's offline artist corpus (the optional **Candidate pool (RAG)** in Settings) only includes acts that started in the **1960s or later**. Pre-1960s music is intentionally excluded — the share of typical SpotyVibe listening before 1960 is negligible and dropping it keeps the index lean. The same note appears as a tooltip (ⓘ) next to the toggle in Settings.

### Local LLMs and the candidate pool (RAG)

If you point SpotyVibe at a **local LLM** (Ollama, LM Studio, …) with a small context window (4 k or 8 k tokens), keep these limits in mind:

- The candidate pool adds ~700 tokens to every prompt. With a 60-slot pool, profile, history and JSON output the conversation typically lands at **4–6 k tokens**.
- If your local model truncates the prompt, **disable RAG** (Settings → Candidate pool), lower `RAG_POOL_SIZE`, or switch to a 16 k+ context model. The RAG feature was designed for hosted GPT-4-class models; smaller open-weight models also tend to ignore the pool more often, so the quality uplift may not justify the extra tokens.

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

## Discover Artists

The **Discover Artists** section sits between Discover Tracks and Refine Playlist. It finds **new artists** matching your taste profile, each with a few representative tracks — artist-level discovery rather than a track playlist.

Two controls:

- **Artists size** — how many new artists to discover (1–10).
- **Exploration vs Accuracy** — *Familiar* favours close matches; *Adventurous* surfaces obscure, under-the-radar artists.

Every pick is **new**: artists already confirmed or previously suggested in your profile are excluded. SpotyVibe retrieves a wide candidate pool from the music corpus, then a single AI pass selects the final list — each artist shown with a one-line reason, genre tags, and a few tracks.

Tracks are verified on Spotify; found tracks are linked, missing ones marked *not on Spotify*. **Apply to Playlist** adds the verified tracks to a playlist (create / append / replace — same modal as Discover Tracks); **Clear** discards the list.

---

## Refine Playlist

Load any of your Spotify playlists and review tracks one by one.

1. Expand **🔄 Refine Playlist**.
2. Pick a playlist and click **🔄 Load Playlist**.
3. For each track: 💬 Feedback (Like keeps, Dislike removes + records), 🗑 Delete (removes without feedback), or click the album art for the same preview player.

Useful for cleaning up old playlists and teaching SpotyVibe retroactively.

---

## Run History

Collapsible **History** panel below Discover Tracks. Records the last 5 runs with date, track count, and playlist link. Click a row to expand the full track list. Refreshes automatically when a new run completes while open.

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
| "Couldn't find more matching tracks" | Loop protection kicked in (3 all-filtered batches). Try a smaller playlist size, adjust the exploration slider, or add new styles to the profile. |
| ⏳ Spotify rate-limited / Model slow | Transient upstream throttle — wait a moment, then retry. The pipeline already retried internally before surfacing this. |
| Most tracks "not found on Spotify" | GPT suggested obscure tracks. Try again — each run is different. |
| "python-dotenv could not parse statement" | Credentials file corrupt. Re-save via ☰ → Credentials. |
| Audio filters remove all tracks | Ranges are too narrow. Widen or clear them. |
| App won't start | Ensure `pip install -r requirements.txt` and Python 3.10+. |
