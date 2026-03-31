# User Manual

Welcome to **SpotyVibe** — your personal AI music discovery assistant.
This guide walks you through setting up the app and using all of its features.

---

## Prerequisites

Before you start, make sure you have:

- **Python 3.10 or newer** installed on your computer. You can download it from [python.org](https://www.python.org/downloads/).
- A **Spotify Premium account** (required — Spotify's developer API requires Premium to create and modify playlists).
- An **internet connection** (the app communicates with OpenAI and Spotify online).

You will also need two sets of API keys (free to obtain):

| Key | Where to get it |
|---|---|
| **OpenAI API Key** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — sign up and create a new API key. |
| **Spotify Client ID & Secret** | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) — create a new app to get your Client ID and Client Secret. |

> **Important:** When creating your Spotify app in the Developer Dashboard, you must add the following **Redirect URIs** in the app settings:
> - `http://127.0.0.1:5000/callback` — required for the **desktop** app
> - `spotyvibe://callback` — required for the **Android APK**
>
> Without the matching URI for your platform, Spotify authentication will fail with "redirect_uri: No matching configuration".

> **💰 Cost note:** The OpenAI API is a **paid service**. Each playlist generation and profile training uses API credits. The default model (`gpt-4.1-mini`) is very affordable, but larger models cost significantly more. See [OpenAI Pricing](https://platform.openai.com/docs/pricing) for details.

---

## Installation

1. **Download** or clone the project to your computer.

2. **Open a terminal** (Command Prompt, PowerShell, or Git Bash) and navigate to the `spotyvibe` folder:
   ```
   cd path/to/spotyvibe
   ```

3. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

That's it — the app is ready to use.

---

## Starting the App

Run the following command in the `spotyvibe` folder:

```
python app.py
```

Then open your browser and go to: **http://127.0.0.1:5000**

You should see the SpotyVibe interface — a premium dark cinematic layout with a vignette-edged stage, animated background visuals, floating frosted dark-glass panels, and luminous green accents.

> **Accessibility note:** If you have reduced-motion preferences enabled in your operating system, all animations and transitions are automatically disabled.

---

## Building a Windows executable (optional)

If you want to run SpotyVibe without installing Python, you can build a Windows executable using PyInstaller.

```bash
pip install -r requirements.txt
python build_assets/make_ico.py


# One-folder build (recommended)
pyinstaller --noconfirm --clean spotyvibe.spec

# (Optional) one-file build
pyinstaller --noconfirm --clean spotyvibe_onefile.spec

# Or use the helper script:
#   ./build-tools/build_exe.sh --package
#   ./build-tools/build_exe.sh --full
```


Then run either:
- One-folder: `dist/spotyvibe/spotyvibe.exe`
- One-file: `dist/spotyvibe_onefile.exe`


The executable starts the server and auto-opens your default browser to **http://127.0.0.1:5000**.

> **One-file note:** The one-file build may start more slowly on first launch because it extracts bundled files to a temporary directory.


> **Note:** Your credentials are still stored outside the app bundle at `%LOCALAPPDATA%\spotyvibe\.credentials`.



---

## First-Time Setup


### 1. Enter Your API Keys

Click the **⚙️ gear icon** in the top-right corner and select **🔑 Credentials**.

Enter the three values:

- **OpenAI API Key** — your key from OpenAI.
- **Spotify Client ID** — from your Spotify Developer app.
- **Spotify Client Secret** — from your Spotify Developer app.

Click **Save**. Your credentials are stored securely outside the project folder and are never committed to version control.

> **💰 Cost note:** SpotyVibe uses the OpenAI API, which is a **paid service**. Each generation run and each profile training call costs money. Check [OpenAI Pricing](https://platform.openai.com/docs/pricing) for details.

### 2. Choose an AI Model

Open the **⚙️ gear menu** and select **⚙️ Settings**.

The **Used Model** dropdown lists all available models from your OpenAI account. The default is `gpt-4.1-mini`.

You can switch to a different model at any time. More capable models (e.g., `gpt-4.1`, `gpt-4o`) may produce better recommendations but cost more per request.

> **⚠️ Cost warning:** Different models have very different prices — for example, `gpt-4.1` can cost 10× more per request than `gpt-4.1-mini`. Check [OpenAI Pricing](https://platform.openai.com/docs/pricing) to understand the costs before switching models.

**Playlist Size** — controls how many tracks are generated per run (minimum 10, default 10).

**New Artist %** — sets the minimum percentage of suggestions per batch that must come from artists *not yet in your history* (range: 1–100, default: 30). For example, with 30% and a batch size of 10, GPT is required to include at least 3 tracks from artists it has never suggested before.

- **Higher values** (e.g., 60–80%) push GPT to explore new territory aggressively. Useful early on when your history is small.
- **Lower values** (e.g., 10–20%) let GPT revisit artists it knows you like more often. Useful once you have a rich history and want deeper cuts from proven artists.

**ChatGPT Language** — a dropdown that sets the language the AI uses when communicating with you (English / Deutsch). This controls GPT's response language for suggestions, profile analysis, and feedback — for example, track recommendation reasons will appear in the chosen language. This setting is independent of the UI language selected in the page header.

### 3. Choose Your Language

At the top of the page header you will find a **language picker**. SpotyVibe currently supports:

- **English**
- **Deutsch** (German)

Selecting a language changes all UI labels, buttons, and messages. Your choice is saved in the browser (localStorage) and persists across visits — you do not need to select it again.

> **Note:** This setting controls the **user-interface language only**. It is independent of the ChatGPT Language setting in the Settings panel (see step 2 above), which controls the language the AI uses in its responses.

### 4. Choose a Visual Theme

At the top of the page, below the SpotyVibe title, you'll find a **Theme** switcher with two options:

| Theme | Description |
|---|---|
| **Equalizer** | The default — animated frequency-spectrum bars that bounce with spring physics and simulated beats. |
| **Pulse** | Expanding concentric rings with floating particles and occasional bass-drop bursts. |

Click any theme button to switch instantly. Your choice is saved in the browser (localStorage) and restored automatically on your next visit.

### 5. Connect Your Spotify Account

After saving your credentials, a banner will appear asking you to **Connect to Spotify**. Click the link — a small popup window will open where you log in to Spotify and grant permission. Once authorised, the popup closes automatically and the banner disappears.

> **Android note:** On the Android APK, the Spotify login opens as a direct page navigation instead of a popup (Android WebView does not support popups to external URLs). After you grant permission in the system browser, the app returns to the home page automatically.

#### Disconnecting / Reconnecting

If your Spotify session expires or you need to re-authenticate, open the **⚙️ gear menu** and click **🔌 Disconnect Spotify**. This clears the cached token and the "Connect to Spotify" banner will reappear so you can log in again.

> **Tip:** If you see a `403 Forbidden` error during playlist generation, the app will automatically disconnect for you. Simply click **Connect to Spotify** in the warning banner to reconnect.

### 6. Set Up Your Music Profile

Before generating suggestions, you need to tell the AI what kind of music you like. The UI is divided into two clearly labelled sections:

- **Step 1 — Taste Profile:** Teach the AI your preferences.
- **Step 2 — Generate Playlist:** Create a Spotify playlist from your profile.

To set up your profile:

1. In the **Step 1** section, click **Edit profile**.
2. The editor opens with four collapsible accordion sections. Fill in the ones relevant to you:

   - **🎵 Core Description** *(required)* — Describe your ideal sound in your own words: genre, mood, energy, reference artists. This is the foundation of your profile and must be provided.
   - **✅ Must Have** — Non-negotiable traits every suggestion must have (one per line). These are hard requirements — a track missing any one is rejected. Example: *"strong melodies"*, *"vocals/singing"*.
   - **💡 Soft Preferences** — Nice-to-have traits that improve a suggestion but aren't required (one per line). Example: *"slight prog influence"*.
   - **🚫 Avoid** — Traits that immediately disqualify a track (one per line). Example: *"electronic/synth-heavy production"*, *"slow or mid-tempo songs"*.

3. Choose how to save your changes:
   - Click **Save** to store your preferences directly as-is.
   - Click **AI Profile Update** to send your input to GPT, which will analyse and refine it into a structured taste profile.

If you already have a profile, the fields are **pre-filled** with your existing preferences so you can see and edit what the AI currently knows.

### Import / Export / Reset your profile

When you expand the **Music Profile** editor (via **Edit profile**), extra profile file actions appear under the **Last trained** label:

- **⬆ Import** — Select a JSON profile file and import it into SpotyVibe.
  - On Android, this opens the system file picker.
  - Import **replaces your entire current profile file**.
  - Before replacing it, SpotyVibe automatically backs up your existing profile to the history file (`personalized_music_profile.history.json`).
  - **Size limit:** Imported files must be **10MB or smaller**.

- **⬇ Export** — Downloads your current active profile as `spotyvibe_profile.json`.
  - On Android, the file is saved to your device's **Downloads**.

- **↩ Reset to history** — Reverts your profile to the previous saved version (one-step undo).
  - This **swaps** the current profile and the history file.
  - If no history exists yet, SpotyVibe will show an error.

> **Tip:** The exported file is always in the correct format to re-import later.


> **Note:** The Core Description field is required. If you clear it and try to submit, the app will highlight the field and ask you to fill it in.


The AI Profile Update merges with what the AI already knows — your feedback history and past suggestions are always preserved. The direct Save option is useful when you just want to make a quick edit without waiting for AI processing.

---

## Generating a Playlist

Once your profile is trained and Spotify is connected, go to the **Step 2 — Generate Playlist** section.

### Playlist Mode

Before generating, choose a **playlist mode** from the selector:

| Mode | Behaviour |
|---|---|
| **Default** | Uses the standard "SpotyVibe Playlist". If it already exists, new tracks are appended. |
| **Create new** | Always creates a brand-new playlist. You can enter a custom name. |
| **Append** | Adds tracks to an existing playlist you pick from a dropdown. |
| **Replace** | Clears all tracks in the chosen existing playlist and adds the new tracks. |

Custom playlist names support **tokens** that are replaced automatically:

- `{date}` — replaced with the current date (e.g. `2026-03-29`).
- `{style}` — replaced with a short style tag derived from your profile.

For example, a name template of `SpotyVibe {style} {date}` might produce `SpotyVibe Prog-Rock 2026-03-29`.

### Audio Feature Filters

Below the playlist mode selector you will find a collapsible **Audio Filters** section. These optional filters let you constrain the generated playlist by Spotify audio features:

- **Energy** — how intense / energetic the track feels (0–100)
- **Valence** — how happy / positive the track sounds (0–100)
- **Tempo** — beats per minute (BPM)
- **Danceability** — how suitable the track is for dancing (0–100)
- **Acousticness** — how acoustic (vs. electronic) the track is (0–100)

Each filter has a **min** and **max** slider. Tracks that fall outside your ranges are removed after Spotify verification — the AI still suggests them, but they are filtered out before being added to the playlist.

Leave a filter's sliders at their default positions (empty) to skip that filter entirely. If all filters are empty, no filtering is applied.

> **Tip:** If you find that filters are removing too many tracks, widen the ranges or disable some filters to let more tracks through.

### Running a Generation

1. Click **▶ Generate & Create Playlist**.
2. Watch the progress updates as the AI works:
   - It asks GPT for track suggestions based on your taste until it reaches your configured **Playlist Size** (default: 10).
   - It verifies each track exists on Spotify.
   - If some tracks aren't found, it automatically retries with new suggestions.

3. When finished, the suggested tracks appear in a list — each shown with its **album cover artwork** — and are added to a private Spotify playlist called **"SpotyVibe Playlist"**.
4. A link to the playlist is shown — click it to open it in Spotify.

---

## Stopping a Generation Early

Sometimes GPT gets stuck suggesting the same songs over and over, or you simply have enough tracks and don't want to wait for the full playlist. Two buttons appear during generation to help with this:

### ⛔ Cancel

Click **⛔ Cancel** at any time to immediately stop the generation. No playlist changes are made — any tracks verified so far are discarded and the Spotify playlist is left unchanged.

Use this when you want to start over with fresh settings or a refined profile.

### ▶ Use X tracks now

As each batch of tracks is verified, a **▶ Use X tracks now** button appears next to the Cancel button (where X is the current count of verified tracks). Clicking this button:

1. Stops the generation immediately.
2. Creates the Spotify playlist with however many tracks have been verified so far — even if the number is less than your configured playlist size.
3. Displays the tracks in the list and shows a link to the finished playlist.

Use this when the AI has found some good tracks but has started repeating suggestions — you can grab what's already good and skip waiting for the rest.

> **Tip:** If you configured a playlist size of 30 but GPT starts looping after 12 tracks, click **▶ Use 12 tracks now** to instantly create a playlist with those 12 tracks.

---

## Run History and Undo

Below the generation area you will find a collapsible **Run History** section. It records every playlist generation you perform, showing:

- **Date and time** of the run
- **Track count** — how many tracks were added
- **Playlist link** — click to open the playlist in Spotify

At the top of the history list is an **Undo last run** button. Clicking it removes all tracks that were added by the most recent generation run from the corresponding Spotify playlist. This is useful if a run produced poor results and you want to revert quickly without manually deleting tracks.

> **Note:** Undo only affects the most recent run. If the playlist has been deleted on Spotify, or if the run history is empty, the undo operation will fail with an explanatory message.

> **Tip:** If the history panel is open when a new generation completes, the list refreshes automatically — no need to close and reopen it.

---

## Reviewing Suggestions

Each suggested track shows the **artist**, **track name**, and a short **reason** explaining why the AI picked it. Tracks are displayed as rich cards with the following details:

- **Album artwork** — the album cover is shown on each track card.
- **Preview** — every track shows a **Preview** button. Clicking it opens a bottom-sheet overlay with the embedded Spotify player so you can listen right in the app. Click the **✕** in the overlay or tap the dark backdrop to close it.
- **Quick links** — icon links open the track (🎵), artist (🎤), and album (💿) pages on Spotify so you can explore further.

### Persistent Song List

The song list is **saved automatically** after each generation and restored when you reload the page — you never lose your track cards between sessions. A counter below the Generate button shows how many songs are currently in the list (max 100).

- When you **like, dislike, or remove** a track it is permanently deleted from the saved list.
- If the list has too many songs to fit another batch, generation is **blocked** with a warning. Review and remove some songs first to make room.

> **Tip:** The persistent list acts as a running record of everything SpotyVibe has generated for you, so the AI can continue building on it across multiple sessions without repeating suggestions.

You have three options for each track:

### 👍 Like

Click the **👍 Like** button to open the feedback form. The artist and track are pre-filled. You can optionally add a **reason** (e.g., *"perfect energy and melody"*). Click **Submit Like** to save.

- The track is recorded as a positive signal.
- The artist is added to your confirmed favourites.
- Future suggestions will lean towards similar music.

### 👎 Dislike

Click the **👎 Dislike** button. The feedback form opens with the same fields. Add a reason if you want (e.g., *"too slow"*, *"boring melody"*). Click **Submit Dislike** to save.

- The track is recorded as a negative signal and removed from your Spotify playlist.
- The AI will avoid suggesting similar tracks in the future.

> **Tip:** Clear the *Track* field and only leave the artist name to dislike an **entire artist**. The artist will be fully excluded from future suggestions.

### ✕ Remove

Click the **✕** button to dismiss a track from the list and remove it from the Spotify playlist — without recording any feedback. Use this for tracks you're neutral about but don't want in the playlist.

---

## Running Again

Every time you click **Generate & Create Playlist**, the AI produces a fresh batch of suggestions sized to your configured **Playlist Size**. It never repeats tracks from previous runs — your history is remembered automatically.


The more feedback you give, the better the suggestions become.

---

## Updating Your Music Profile

Your taste may evolve over time. You can update your profile at any point:

1. Click **Edit profile** in the Music Profile section.
2. The accordion sections open pre-filled with your current profile data. Edit any section — for example, add new items to **Must Have**, remove entries from **Avoid**, or rewrite the **Core Description**.
3. Choose how to save:
   - Click **Save** to store your edits directly.
   - Click **AI Profile Update** to have GPT analyse and merge your changes.

Both options preserve your feedback history and past suggestions — nothing is lost.

### Band/Song Analysis

Inside the **Step 1** section you will find a collapsible **Band/Song Analysis** panel. This tool lets you research any artist or track before adding it to your profile:

1. Enter an **artist name** and, optionally, a **track name**.
2. Click **Analyze**.
3. The AI returns detailed information about the music: genre, style tags, and characteristics such as energy, instrumentation, vocals, production, and structure.
4. Below the analysis you will see **Profile Suggestions** — short phrases you can paste directly into your taste profile fields. Each suggestion has a **copy-to-clipboard** button so you can copy the text with one click and paste it into the Core Description, Must Have, Soft Preferences, or Avoid fields.

This is useful when you want to describe a sound but aren't sure of the right terminology — let the AI analyse a reference track and borrow its vocabulary.

> **Tip — Profile consistency matters:** If you explicitly reject an artist (via 👎 Dislike), make sure the same artist is not still listed as a confirmed favourite. Contradictions in the profile confuse the AI and cause bad suggestions. If you notice the AI keeps repeating things you've rejected, open the Music Profile section and add a clear sentence like *"I strongly dislike [Artist] — never suggest them."*

---

## Debug Mode (Desktop only)

If the AI's suggestions don't seem to match your preferences, you can enable **Debug Mode** (desktop only) to inspect the exact prompts being sent and the responses received:


1. Open **⚙️ gear menu → ⚙️ Settings**.
2. Check **"Log GPT requests & responses to debug file"**.
3. Click **Save**.

Now every GPT interaction (profile training and playlist generation) is logged to a `debug.log` file. The exact path is shown in the Settings panel (e.g. `%LOCALAPPDATA%\spotyvibe\debug.log` on Windows). Each log entry includes a timestamp, the full messages sent to GPT, and the raw response.

> **Android note:** Debug Mode is intentionally not available in the Android APK.


You can open this file with any text editor to review and optimise the prompts in the `prompts/` directory.

> **Tip:** Disable debug mode when you're done — the log file can grow large over repeated runs.

---

## Using SpotyVibe on Mobile

SpotyVibe works on phones and tablets — just open the same `http://127.0.0.1:5000` URL in your mobile browser. The interface automatically adapts to your screen size:

- **Tablets** — the layout narrows to fit the screen, with slightly smaller headings and buttons.
- **Phones** — buttons and forms stack vertically for easy one-handed use. Modals slide up from the bottom of the screen as full-width sheets. All buttons and interactive elements have a minimum 44px touch target for comfortable tapping.

No special action is needed — there is nothing to install or configure. If your desktop and mobile device are on the same network, open the app URL from your phone and it just works.

> **Tip:** Toast notifications appear full-width on phones so they're easy to read. Tooltips reposition themselves to stay visible on small screens.

---

## Building the Android APK

SpotyVibe can be packaged as a standalone Android app. The `android/` directory contains the full build scaffolding.

**Prerequisites:**

- **Android Studio** with Android SDK API 34 installed
- **JDK 17** (bundled with Android Studio or installed separately)
- **Android SDK** — install via Android Studio's SDK Manager

The Android project pins Android Gradle Plugin 8.2.2, Kotlin 1.9.22, and Chaquopy 15.0.1, so use a current Android Studio release that supports those versions.

**Building:**

```bash
# Run from the repo root
./build-tools/build_apk.sh debug
```



The build script copies the Python sources into the Android project and runs a Gradle build. The resulting APK bundles the complete SpotyVibe app — Flask server, Python runtime, and all pip dependencies — so no external Python installation is needed on the device.

The APK targets `arm64-v8a` devices by default. For **emulator testing**, the build also includes `x86_64` support — remove it from `android/app/build.gradle` before creating a release build to reduce APK size. The app module pins Python 3.10, Flask 3.x, OpenAI 1.x, Spotipy 2.x, python-dotenv 1.x, and Markdown 3.x so APK builds stay consistent.

After installing, the app starts Flask in the background and loads the UI in a WebView. All features work identically to the desktop version, with one difference: Spotify authentication uses direct navigation instead of a popup window (see the note in [Connect Your Spotify Account](#5-connect-your-spotify-account) above).

### Onboarding Flow (Android)

The first time you launch the Android APK, a **3-page swipeable onboarding** screen appears:

1. **Page 1 — Welcome** — an introduction to SpotyVibe with feature highlights.
2. **Page 2 — Credentials** — enter your OpenAI API key and Spotify Client ID / Secret directly during setup.
3. **Page 3 — Connect & Import** — connect your Spotify account and import an existing taste profile if you have one.

Each page has **Skip**, **Next**, and **Close** buttons so you can navigate or dismiss the onboarding at any time. Once completed (or skipped), the onboarding is remembered and will not appear again on subsequent launches.

---

## Where Are My Data Files?

All your personal data is stored outside the project in your system's app data folder:

| File | Location | Purpose |
|---|---|---|
| Credentials | `%LOCALAPPDATA%\spotyvibe\.credentials` | Your API keys and settings (never in the project folder). |
| Taste profile | `%LOCALAPPDATA%\spotyvibe\personalized_music_profile.json` | Your trained taste profile + history. |
| Spotify token | `%LOCALAPPDATA%\spotyvibe\.spotify-cache` | Cached Spotify authentication token. |
| Debug log | `%LOCALAPPDATA%\spotyvibe\debug.log` | GPT request/response log (desktop only, only when debug mode is enabled). |
| Run history | `%LOCALAPPDATA%\spotyvibe\run_history.json` | Past generation run metadata (used for undo). |

This means you can safely update or reinstall the app without losing your profile or credentials.

---

## Command-Line Usage

While the web interface is the recommended way to use SpotyVibe, the app also supports command-line usage:

### Generate a playlist (CLI)

```bash
python -m core.playlist
```

### Get suggestions only (no playlist)

```bash
python -m core.suggestions
```

### Record feedback from the command line

```bash
# Like a track
python -m core.feedback like "Artist Name" --track "Song Name" --reason "why you like it"

# Dislike a track
python -m core.feedback dislike "Artist Name" --track "Song Name" --reason "why you dislike it"

# Exclude an entire artist
python -m core.feedback dislike "Artist Name" --reason "why"
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **"Spotify credentials missing"** | Open ⚙️ → Credentials and enter your Spotify Client ID and Secret. |
| **"Please train your taste profile first"** | Use the Train Taste Profile section to describe your music taste before generating. |
| **Spotify auth fails with "INVALID_CLIENT"** | Double-check your Client ID and Secret. Make sure the correct Redirect URI is listed in your Spotify Developer Dashboard (see Prerequisites above). |
| **Android: "redirect_uri: No matching configuration"** | Add `spotyvibe://callback` as a Redirect URI in your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). This URI is required for the Android APK — without it, Spotify rejects the login request. |
| **"403 Forbidden" during generation** | Your Spotify session has expired or permissions were revoked. The app disconnects automatically — click **Connect to Spotify** in the warning banner to reconnect. You can also manually disconnect via ⚙️ → 🔌 Disconnect Spotify. |
| **"OpenAI API key is not configured"** | Open ⚙️ → Credentials and enter your OpenAI API Key. |
| **GPT kept suggesting the same songs and stopped early** | This is the automatic loop-protection kicking in. After 3 consecutive batches where every suggestion was already in your history, the app stops and creates the playlist with whatever tracks were found. Click **▶ Use X tracks now** before that point, or update your taste profile with new preferences and re-run. |
| **"GPT could not generate any new tracks"** | Your history is very large and GPT can no longer find tracks outside it. Try describing new styles or genres in the Train Taste Profile section to expand the suggestion space. |
| **Most tracks "not found on Spotify"** | This can happen if the AI suggests very obscure tracks. Run the generation again — each attempt produces different results. |
| **"python-dotenv could not parse statement"** | Your credentials file is corrupted. Open ⚙️ → Credentials and re-save your keys. The app now prevents this from recurring. |
| **Undo last run fails** | The run history may be empty (no previous runs recorded) or the target playlist was deleted on Spotify. Generate a new playlist first, or check that the playlist still exists in your Spotify account. |
| **Audio filters remove all tracks** | Your filter ranges are too narrow and every suggested track falls outside them. Widen the min/max sliders or disable some filters entirely by resetting them to their default positions. |
| **App won't start** | Make sure you ran `pip install -r requirements.txt` and are using Python 3.10+. |

