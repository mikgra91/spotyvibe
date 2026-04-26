# SpotyVibe User Guide

Welcome to **SpotyVibe** — your AI-powered music discovery assistant.  
This guide explains how to use the **SpotyVibe interface** to set up your preferences, connect Spotify, generate playlists, and refine recommendations over time.

---

## Pick a topic

<div class="help-tiles">
  <a class="help-tile" href="#account-setup">
    <span class="help-tile-title">1. Set up your keys</span>
    <span class="help-tile-desc">Save your OpenAI and Spotify credentials and connect Spotify.</span>
  </a>
  <a class="help-tile" href="#music-profile">
    <span class="help-tile-title">2. Build a music profile</span>
    <span class="help-tile-desc">Describe your taste so the AI can suggest tracks you'll love.</span>
  </a>
  <a class="help-tile" href="#playlist-generation">
    <span class="help-tile-title">3. Generate playlists</span>
    <span class="help-tile-desc">Pick a mode, tweak filters, and create a new playlist.</span>
  </a>
  <a class="help-tile" href="#refine-playlist">
    <span class="help-tile-title">4. Refine and review</span>
    <span class="help-tile-desc">Like, dislike, and dismiss tracks to sharpen your profile.</span>
  </a>
  <a class="help-tile" href="#troubleshooting--tips">
    <span class="help-tile-title">5. Troubleshooting</span>
    <span class="help-tile-desc">Common issues and final tips.</span>
  </a>
</div>

**Reference**

<ul class="help-reference-list">
  <li><a href="#privacy--what-leaves-your-device">Privacy</a></li>
  <li><a href="#getting-started">Getting Started</a></li>
  <li><a href="#user-preferences">User Preferences</a></li>
  <li><a href="#discovery--analysis">Band/Song Analysis</a></li>
  <li><a href="#track-review--feedback">Track Review &amp; Feedback</a></li>
  <li><a href="#taste-dashboard">Taste Dashboard</a></li>
  <li><a href="#song-list--run-history">Song List &amp; Run History</a></li>
  <li><a href="#mobile-usage">Mobile Usage</a></li>
</ul>

---

<a id="privacy--what-leaves-your-device"></a>
## Privacy — What Leaves Your Device

SpotyVibe keeps your keys and taste profile on your device. When you generate a playlist, your taste is sent to OpenAI (to get suggestions) and track titles are sent to Spotify (to verify and save them). Nothing else is tracked.

| Data | On device | To OpenAI | To Spotify |
|------|-----------|-----------|------------|
| API keys | ✓ | — | — |
| Taste profile (text) | ✓ | ✓ (per generation) | — |
| Track likes / dislikes | ✓ | ✓ (per generation) | — |
| Suggested track titles | ✓ | — | ✓ (search / add) |
| Listening history | — | — | ✓ (read once) |

Applies to the default SpotyVibe setup. Custom LLM endpoints may route data differently.

---

<a id="getting-started"></a>
## Getting Started

<a id="overview"></a>
### Overview

SpotyVibe helps you discover music based on your personal taste.  
You describe what you like, connect your Spotify account, and let the app generate playlist suggestions tailored to you.

The more feedback you give, the better the recommendations become.

SpotyVibe runs on **Windows**, **macOS**, and **Linux**. On Windows, it runs as a native desktop app (PyInstaller executable). On macOS and Linux, install the Python package (`pip install spotyvibe-*.whl`) and run `spotyvibe` — it starts the server and opens your browser automatically.

![Main home screen](/docs/screenshots/01_main_home_screen.png)

---

<a id="before-you-start"></a>
### Before You Start

To use SpotyVibe, make sure you have:

- A **Spotify Premium** account
- Your **OpenAI API Key**
- Your **Spotify Client ID**
- Your **Spotify Client Secret**

You will enter these in the app during setup.

![Credentials screen](/docs/screenshots/24_onboarding_credentials.png)

---

<a id="understanding-the-main-screen"></a>
### Understanding the Main Screen

When you open SpotyVibe, you will see the main interface with two provider sections:

- **OpenAI** — Taste profile editor, AI profile updates, and AI Band/Song Analysis.
- **Spotify** — Playlist generation, playlist refinement, and run history.

Status pills at the top of each section show whether your credentials are configured and connected.

Each major component is **collapsible/expandable**. You can click the section header (anywhere in the title area) or the toggle button to expand or collapse it. A short description below each title explains what the component does.

Each section header also has a small **?** help icon. Click it to open this guide scrolled directly to the relevant section.

The main screen is organised into collapsible components grouped under two provider sections:

**OpenAI Section:**
- **🎯 Music Profile** — Define your musical taste — genres, moods, must-haves, and things to avoid.
- **🔍 Band/Song Analysis** — Get an AI-powered breakdown of any artist or track with ready-to-paste profile suggestions.

**Spotify Section:**
- **🎧 Discover Music** — Generate AI-powered playlists and save them directly to your Spotify account. Includes an optional **Audio Filters** sub-panel to constrain suggestions by mood and feel. *(Collapsed by default.)*
- **🔄 Refine Playlist** — Load an existing playlist and give track-by-track feedback to refine your taste profile. *(Collapsed by default.)*
- **🕓 History** — View past generation runs.

The overall flow is:

1. Open the menu and complete your setup
2. Create or refine your music profile
3. Generate a playlist
4. Review songs and provide feedback
5. Repeat to improve future recommendations

At the top of the page, you can also access:

- The **menu**
- The **language selector**
- The **theme selector**

![Header with menu, language, and theme controls](/docs/screenshots/02_header_controls.png)

---

<a id="quick-start-guide"></a>
### Quick Start Guide

When you open SpotyVibe for the first time, a **Quick Start Guide** appears automatically for the active provider section. The guide is split into two provider-scoped variants:

- **🤖 OpenAI Quick Start** — Setup, Build Your Profile, Repeat & Improve.
- **🎵 Spotify Quick Start** — Setup, Generate a Playlist, Review & Feedback, Refine Existing Playlists, Repeat & Improve.

Each variant only shows steps relevant to its provider and has its own "Don't show again" preference.

**Using the guide:**

- The **Contents** page lists only the steps for the active provider. Click any entry to jump directly to that step.
- Each step has a text description, a **Key Actions** checklist, and an **interactive demo** that shows exactly what to click in the app.
- The demos auto-play — use **▶/⏸** to pause, or **‹ / ›** to step through manually.
- Use the **numbered dots** or **Back / Next** buttons at the bottom to navigate between steps.
- On the last step, **Next** becomes **Get Started** and closes the guide.

**Dismissing and reopening:**

- Check **"Don't show again"** on any page to stop that provider's guide from showing on future visits.
- When you switch to the other provider for the first time in a session, its guide auto-shows if not dismissed.
- To reopen it at any time, click **☰ → 🚀 Quick Start** (opens the guide for the currently active provider).

![Quick Start guide contents page](/docs/screenshots/26_quickstart_toc.png)

---

<a id="account-setup"></a>
## Account Setup

<a id="open-the-menu"></a>
### Open the Menu

Click the **☰ menu icon** (hamburger menu) in the top-right corner to open the menu.

From here, you can access:

- **Credentials**
- **Settings**
- **Disconnect Spotify** (if already connected)

![Burger menu open](/docs/screenshots/03_burger_menu_open.png)

---

<a id="enter-your-credentials"></a>
### Enter Your Credentials

Open **Credentials** and enter:

- **OpenAI API Key**
- **Spotify Client ID**
- **Spotify Client Secret**

Click **Save** when finished. Your API keys are stored securely in your operating system's keychain (e.g. Windows Credential Manager) — they are never saved as plain text. App preferences (model, playlist size, etc.) are stored in a separate settings file.

If the information is correct, you can proceed to connect Spotify.

![Credentials form](/docs/screenshots/04_credentials_modal.png)

---

<a id="connect-your-spotify-account"></a>
### Connect Your Spotify Account

After saving your credentials, SpotyVibe will prompt you to connect Spotify.

Click **Connect to Spotify** and complete the sign-in flow.

Once connected:

- The connection banner disappears
- You can start generating playlists
- SpotyVibe can create and manage playlists for you

If your session expires later, simply reconnect.

![Connect to Spotify banner](/docs/screenshots/27_connect_spotify_banner.png)

---

<a id="user-preferences"></a>
## User Preferences

<a id="settings"></a>
### Settings

Open **Settings** from the menu to customize how SpotyVibe works for you.

Available settings include:

- **Used Model**  
  Choose which AI model SpotyVibe uses.

- **Playlist Size**  
  Set how many tracks SpotyVibe should aim to generate.

- **New Artist %**  
  Control how strongly SpotyVibe favors artists you have not seen before.

- **ChatGPT Language**  
  Select the language used in AI-generated explanations and profile updates.

Click **Save** after making changes.

![Settings panel](/docs/screenshots/05_settings_modal.png)

---

<a id="language"></a>
### Language

Use the **language picker** at the top of the page to switch the interface language.

This changes text such as:

- Buttons
- Labels
- Messages
- Menus

![Language selector](/docs/screenshots/06_language_selector.png)

---

<a id="theme"></a>
### Theme

SpotyVibe includes multiple visual themes.

Use the **theme switcher** near the top of the page to select your preferred look.

Themes change the visual style of the interface but do not affect playlist results.

![Theme switcher](/docs/screenshots/07_theme_switcher.png)

---

<a id="music-profile"></a>
## Music Profile

<a id="create-your-music-profile"></a>
### Create Your Music Profile

Before SpotyVibe can generate good recommendations, you need to teach it your taste.

In the **OpenAI** section, click **Edit profile** or click anywhere on the **Music Profile** header to expand the profile editor.

The editor is organized into **collapsible accordion panels**. Click any panel header to expand or collapse it. The first panel — **Profiles** — is where you manage your profiles.

![Music Profile editor with accordion panels](/docs/screenshots/08_profile_editor_open.png)

---

<a id="select-or-create-a-profile"></a>
#### Select or Create a Profile

The **👤 Profiles** accordion is the first panel in the editor. It contains a dropdown and a create button.

1. Click **+ Create new Profile** below the dropdown.
2. Type a name — for example "Workout", "Chill", or "Discovery" — and press **Enter** or click **✓**. Names can be up to 40 characters.
3. The new profile is automatically selected and ready to edit.

You can create as many profiles as you want. Each profile is completely independent — great for different moods, activities, or family members.

To switch profiles, select a different one from the dropdown. Your form fields update automatically when you switch.

![Profiles accordion with dropdown and create input](/docs/screenshots/09_profiles_accordion.png)

---

<a id="profile-status"></a>
#### Profile Status

Below the section header you will see a status line:

- **✓ Last trained: [date/time]** — The profile has been saved or AI-updated at least once. This shows when the last save happened, not how good the profile is.
- **⚠ Not yet trained** — The profile has never been saved. Describe your taste and save it to get started.

![Profile status indicators](/docs/screenshots/10_profile_status.png)

---

<a id="describe-your-vibe"></a>
#### Describe Your Vibe

The **💬 Describe Your Vibe** accordion is the quickest way to tell SpotyVibe what you are looking for.

Write in everyday language — like chatting with a friend — what kind of music you want. For example:

- "I love energetic rock with theatrical vocals like Queen. Surprise me with something new but keep it high-energy and melodic!"
- "More jazz influence, less electronic. Think Snarky Puppy meets Radiohead."
- "Make my profile darker and heavier, but keep the melodies."

**Smart classification:** When you use **AI Profile Update**, SpotyVibe does not just store your text — it **automatically classifies** each part of your message and routes it to the correct profile section. The AI recognizes natural trigger phrases:

| What you write | Where it goes |
|---|---|
| "must have heavy bass", "needs strong vocals" | → **Must Have** |
| "no autotune", "avoid slow songs", "without synths" | → **Avoid** |
| "would be nice to have jazz influence", "ideally some prog elements" | → **Soft Preferences** |
| General taste descriptions, genre/mood/energy | → **Core Description** |

This means you can write everything in one place and let the AI sort it out. After the update completes, the field is **cleared automatically** — your input has been incorporated into the structured profile sections, so the one-time instruction is no longer needed.

If you fill in this field, the **Core Description** below becomes optional — the AI will generate one for you.

![Describe Your Vibe field with example text](/docs/screenshots/11_vibe_description.png)

---

<a id="core-description"></a>
#### Core Description

The **🎵 Core Description** accordion is the foundation of your profile.

Describe the kind of music you want using your own words, such as:

- genre
- mood
- energy
- atmosphere
- reference artists
- instruments
- vocals

This field should clearly explain your overall taste.

![Core Description field](/docs/screenshots/12_core_description.png)

---

<a id="must-have"></a>
#### Must Have

The **✅ Must Have** accordion is for non-negotiable traits that every recommendation **must** have. A track missing any of these is rejected.

Examples:

- strong melodies
- emotional vocals
- energetic drums
- atmospheric guitar work

Enter one preference per line.

![Must Have section](/docs/screenshots/13_must_have.png)

---

<a id="soft-preferences"></a>
#### Soft Preferences

The **💡 Soft Preferences** accordion is for qualities that are welcome but not required — nice-to-haves that improve a suggestion.

Examples:

- slight progressive elements
- warm production
- occasional synth textures

Enter one preference per line.

![Soft Preferences section](/docs/screenshots/14_soft_preferences.png)

---

<a id="avoid"></a>
#### Avoid

The **🚫 Avoid** accordion is for absolute dealbreakers — sounds or traits you do **not** want.

Examples:

- overly electronic production
- slow ballads
- harsh vocals
- repetitive choruses

Enter one item per line.

![Avoid section](/docs/screenshots/15_avoid.png)

---

<a id="save-or-ai-profile-update"></a>
#### Save or AI Profile Update

After editing your profile, two action buttons appear at the bottom of the editor:

- **Save** (right side)  
  Stores your profile exactly as written. No AI processing, no API call, instant. Works even if fields are empty. Does **not** require an OpenAI API key.

- **AI Profile Update** (left side)  
  Sends your input to GPT, which refines, organizes, and structures your profile. The AI automatically classifies your Vibe Description (see above), extracts reference artists, generates internal taste rules, and improves the wording of each section. Requires an OpenAI API key and uses a small number of tokens. A yellow warning appears if both Core Description and Vibe Description are empty.

**When to use which:**

| | Save | AI Profile Update |
|---|---|---|
| Speed | Instant | A few seconds |
| API key required | No | Yes (OpenAI) |
| Token cost | None | Small |
| Refines wording | No — saves as-is | Yes — improves structure |
| Classifies Vibe text | No | Yes — routes to correct sections |
| Best for | Quick edits, minor tweaks | First-time setup, major changes |

A loading spinner with rotating status messages appears during AI Profile Update.

![Save and AI Profile Update buttons](/docs/screenshots/16_save_buttons.png)

---

<a id="what-the-ai-does-behind-the-scenes"></a>
#### What the AI Does Behind the Scenes

When you run **AI Profile Update**, GPT does more than just save your text. It also populates several internal fields that you never edit directly but that significantly improve playlist generation:

- **Goal & primary reference** — A one-sentence summary and dominant style benchmark derived from your core description.
- **Confirmed / moderate / rejected artists** — Artist names extracted from your descriptions, categorized by how well they match your taste.
- **Taste rules** — A priority order for judging tracks (e.g. "melody > energy > style") and an ordered list of absolute dealbreakers from your Avoid section.

These fields are invisible in the UI but are included in every playlist generation prompt, helping GPT make more accurate suggestions. You do not need to manage them — they update automatically each time you run AI Profile Update.

---

<a id="import-export-reset-and-delete-your-profile"></a>
### Import, Export, Reset, and Delete Your Profile

The **Profiles** accordion header contains a **⋯** (three-dot) menu button next to the collapse chevron. Click it to open a dropdown with the following actions:

- **Upload profile**  
  Load a saved profile JSON file into the current profile. A confirmation dialog appears first. Your previous profile is automatically backed up to a history file before the import overwrites it. Unknown fields in the imported file are silently stripped; missing fields are filled from the default template.

- **Export profile**  
  Download your current profile as a `spotyvibe_profile.json` file (full JSON including all AI-generated internal fields).

- **Reset profile**  
  Restore the previous version of your profile (one-step undo). This loads the automatic backup that was created before the last save, AI update, or import.

- **Delete profile**  
  Permanently remove the current profile and its history. A confirmation dialog appears first. This cannot be undone. If other profiles exist, the first one is automatically selected.

**Disabled items:** When no profile is selected, **Export**, **Reset**, and **Delete** are grayed out because they require an active profile. **Upload** is always available — it creates or replaces the active profile.

This is useful if you want to back up your profile, move it to another device, clean up unused profiles, or undo a recent change.

![Import / Export / Reset / Delete controls](/docs/screenshots/17_profile_io_controls.png)

---

<a id="updating-your-taste-over-time"></a>
### Updating Your Taste Over Time

Your taste may change, and SpotyVibe is designed to evolve with you.

To update your preferences:

1. Go back to the **OpenAI** section
2. Click **Edit profile**
3. Update your description or preference lists — or just type what changed in the **Describe Your Vibe** field
4. Save or run **AI Profile Update**
5. Generate again

The more accurately your profile reflects your current taste, the better your future playlists will be. For small adjustments, use the Vibe field — for example, "more acoustic, less electronic" — and let the AI merge it into your existing profile.

![Editing an existing profile](/docs/screenshots/28_editing_existing_profile.png)

---

<a id="discovery--analysis"></a>
## Discovery & Analysis

<a id="bandsong-analysis"></a>
### Band/Song Analysis

In the **OpenAI** section, click **Open Analysis** or click anywhere on the **Band/Song Analysis** header to expand it.

This feature helps you analyze an artist or song and turn that into profile language.

How to use it:

1. Enter an **artist name**
2. Optionally enter a **track name**
3. Click **Analyze**
4. Review the results
5. Copy useful suggestions into your music profile

This is especially helpful if you know what you like, but are not sure how to describe it.

![Band/Song Analysis panel](/docs/screenshots/18_analysis_panel.png)

---

<a id="playlist-generation"></a>
## Playlist Generation

Once your profile is ready and Spotify is connected, go to the **Spotify** section and click **Show** on the **Discover Music** header (or click anywhere on the header) to expand it.

This is where SpotyVibe creates playlist suggestions based on your taste. The section is collapsed by default to keep the page compact.

![Discover Music section expanded](/docs/screenshots/19_discover_section.png)

---

<a id="choose-a-playlist-mode"></a>
### Choose a Playlist Mode

Before generating, choose how SpotyVibe should handle the playlist.

Common options include:

- **Default**  
  Uses the standard SpotyVibe playlist

- **Create new**  
  Creates a brand-new playlist

- **Append**  
  Adds tracks to an existing playlist

- **Replace**  
  Clears an existing playlist and fills it with new tracks

If you create a new playlist, you can usually enter a custom playlist name.

![Playlist mode selector](/docs/screenshots/20_playlist_mode_selector.png)

---

### Quick vs Advanced Mode

The Generate panel has two modes, accessible via the pill toggle at the top:

- **Quick** — Shows only playlist size, the exploration slider, and the Generate button. Best for everyday use.
- **Advanced** — Shows all controls: preset picker, playlist mode, emerging artists, audio filters, new artist %, and the exploration slider.

Your mode selection is saved and restored on reload.

---

### Exploration Slider

The **Exploration vs Accuracy** slider is a 5-notch control that adjusts how adventurous your suggestions will be:

1. **Familiar** — Bias toward artists you already know (10% new, temperature 0.5).
2. **Mostly known** — A few new artists mixed in (25% new, temperature 0.7).
3. **Balanced** — Roughly half new artists, moderate novelty (50% new, temperature 0.8).
4. **Mostly new** — Discovery-led, some familiar anchors (70% new, temperature 0.9).
5. **Adventurous** — Emerging artists only, high novelty (90% new, temperature 1.0).

In Advanced mode, if you hand-edit the "New Artist %" or emerging artists checkbox to values that don't match any notch, the slider enters a **Custom** state. Moving it back to any notch re-applies the preset values.

---

### Generation Presets

In Advanced mode, a **Preset** dropdown at the top lets you save and recall complete generation configurations:

- **Built-in presets:** Safe picks, Balanced, Deep discovery. Cannot be edited, but can be cloned.
- **User presets:** Appear above the built-ins. Save via "💾 Save current as preset…".
- **Manage presets:** Open via ☰ Menu → 🎛 Manage presets. Rename, delete, reorder, import, or export.
- Presets are stored locally on your device in the browser's localStorage.
- **CUSTOM badge:** Hand-editing the **New Artist %** field to a value other than the active preset's value shows a small **CUSTOM** badge next to the input. Save it as a new preset (or update the existing one) to make the change permanent.

> **Artist coverage note:** SpotyVibe's offline artist corpus (the optional **Candidate pool (RAG)** in Settings) only includes acts that started in the **1960s or later**. Pre-1960s music is intentionally excluded — its share of typical SpotyVibe listening is small and dropping it keeps the index lean. The same note appears as a tooltip (ⓘ) next to the toggle in Settings.

> **Local LLM note:** With RAG enabled the prompt grows to ~6–9 k tokens. SpotyVibe automatically halves the per-call batch (5 instead of 10) so the conversation fits most local-model context windows, which means roughly twice as many "Batch N…" progress lines per run. If you use a small-context local model (4 k or 8 k tokens) and quality drops, disable RAG in Settings or switch to a 16 k+ context model — RAG was designed for hosted GPT-4-class models.

---

<a id="use-audio-filters"></a>
### Use Audio Filters

Inside the **Discover Music** section, click the **🎚 Audio Filters (optional)** bar to expand the filter panel. These optional filters guide GPT to suggest tracks matching your desired mood and feel.

Available filters:

- **Energy** — how intense / energetic the track feels (0–1)
- **Valence** — how happy / positive the track sounds (0–1)
- **Tempo** — beats per minute (BPM)
- **Danceability** — how suitable the track is for dancing (0–1)
- **Acousticness** — how acoustic (vs. electronic) the track is (0–1)

Each filter has a **min** and **max** input. As you type, a human-readable hint appears to the right (e.g. "↳ Energetic to Intense") so you can see what the numbers mean at a glance.

**Clear All:** Click **✕ Clear all** in the top-right of the filter panel to reset every filter at once.

#### Using Band/Song Analysis to Set Filters

The easiest way to fill in audio filters is via the **Band/Song Analysis** feature:

1. Open **Band/Song Analysis** and analyse a reference track.
2. In the results, each audio feature row (Energy, Valence, etc.) has a **⇒ Filter** button.
3. Click **⇒ Filter** on any feature — it automatically sets a sensible min/max range (±10%, or ±15 BPM for tempo) in the Discover Music filter panel.
4. Or click **⇒ Use All as Filters** to apply all features at once.
5. The Discover section and filter panel open automatically when you apply a filter.

This bridges the gap between analysis and generation — no more memorising numbers.

![Audio Filters sub-panel inside Discover Music](/docs/screenshots/21_audio_filters.png)

![Band/Song Analysis with Filter buttons](/docs/screenshots/18_analysis_panel.png)

---

<a id="emerging-artists-only"></a>
### Emerging Artists Only

Between the playlist name/mode controls and the Audio Filters panel, there is an **"Only new / emerging artists"** checkbox.

When checked:

- The AI is instructed to **only suggest tracks by artists who debuted in the last 6 months**.
- After Spotify verification, tracks are filtered by their album **release date** — anything older than 6 months is removed.
- To compensate for the heavier filtering, the AI requests more candidates per batch.
- The final playlist may have **fewer tracks** than your configured size. A status message explains the result (e.g. "Showing 14 of 30 checked tracks — only tracks by recently emerged artists are included.").

Leave the checkbox unchecked for normal generation behaviour.

---

<a id="start-generation"></a>
### Start Generation

Click **Generate & Create Playlist** to begin.

A loading spinner appears below the button inside the Discover Music section. Progress messages are displayed underneath the spinner as SpotyVibe works:

1. Generate song suggestions
2. Check them on Spotify
3. Build the playlist
4. Show the results inside the section (below a divider)
5. Provide a link to open the playlist in Spotify

![Generation in progress with inline spinner](/docs/screenshots/29_generation_spinner.png)

---

<a id="stop-early-or-use-current-tracks"></a>
### Stop Early or Use Current Tracks

During generation, two helpful options may appear:

- **Cancel**  
  Stops the current generation without applying changes

- **Use X tracks now**  
  Stops generation and creates the playlist using the tracks already found

This is useful if you already like the results and do not want to wait longer.

![Cancel and Use X Tracks Now buttons](/docs/screenshots/30_cancel_use_tracks.png)

---

<a id="track-review--feedback"></a>
## Track Review & Feedback

After generation, SpotyVibe displays the suggested tracks **inside the Discover Music section**, below the Generate button, separated by a divider. A completion banner and playlist link appear first, followed by the track cards. Track cards glow green on hover.

Each card may show:

- Track name
- Artist
- Album artwork
- Reason for recommendation
- Action buttons

You can review each song and decide what to do next.

![Track cards after generation](/docs/screenshots/31_track_cards.png)

---

<a id="preview-a-track"></a>
### Preview a Track

Click the album art on a song card to open the preview overlay at the bottom of the screen.

The preview uses a three-zone layout:

1. **Player** — the track player (centered, wide). On Spotify Premium and supported runtimes, SpotyVibe uses the Spotify Web Playback SDK for full-length playback and surfaces 👍 / 👎 quick buttons directly next to the transport controls. Otherwise, the embedded Spotify iframe provides ~30-second previews.
2. **Action buttons** — a **Feedback** button (opens the reason panel) and a **Delete** button (removes the track from the Spotify playlist without recording feedback), to the right of the player.
3. **Feedback panel** — slides in when you click **Feedback**. The panel shows the track details plus an optional reason field, and two submit buttons at the bottom: **👍 Like** (green) and **👎 Dislike** (red). Pick your polarity when you submit, not when you open the panel.

The quick 👍 / 👎 in the player submit immediately with no reason — useful while the song is playing. Dislike additionally removes the track from the Spotify playlist and advances to the next preview.

Use the ‹ and › arrows to navigate between tracks without closing the overlay.

> **First time previewing a track?** The player's 👍 / 👎 pulse briefly and a tip explains the quick-rating workflow. The hint only shows on the first open per device.

![Preview player open](/docs/screenshots/32_preview_player.png)

---

<a id="open-spotify-links"></a>
### Open Spotify Links

Each song card includes quick links to open content in Spotify, such as:

- the track
- the artist
- the album

Use these links to explore music in more detail.

![Spotify quick links on a song card](/docs/screenshots/33_spotify_quick_links.png)

---

<a id="like-a-track"></a>
### Like a Track

Click **Like** if a track matches your taste.

You can optionally add a short reason before submitting.

Liking tracks helps SpotyVibe learn what works well for you.

Examples of reasons:

- perfect mood
- great vocals
- strong melody
- exactly the sound I want

![Like feedback form](/docs/screenshots/34_like_feedback_form.png)

---

<a id="dislike-a-track"></a>
### Dislike a Track

Click **Dislike** if a track does not fit.

You can optionally add a reason to explain why.

Examples:

- too slow
- wrong atmosphere
- too electronic
- weak chorus

This helps SpotyVibe avoid similar tracks in future runs.

![Dislike feedback form](/docs/screenshots/35_dislike_feedback_form.png)

#### Dislike a whole artist

If you submit a Dislike with the **Track** field left empty, SpotyVibe asks for confirmation: *"Remove ALL songs by '<artist>' from this playlist and never suggest them again?"* Clicking OK removes every track by that artist from the active playlist (not just the visible one) and remembers the artist-level dislike, so they will not be suggested again. Cancel does nothing.

---

<a id="remove-a-track"></a>
### Remove a Track

Click **Remove** to take a song out of the list without recording it as like or dislike.

Use this for tracks you feel neutral about.

![Remove button on song card](/docs/screenshots/36_remove_button.png)

---

<a id="refine-playlist"></a>
## Refine Playlist

The **Refine Playlist** section lets you load an existing Spotify playlist and review its tracks one by one. You can like, dislike, or dismiss each track to refine your taste profile and clean up the playlist at the same time.

This is useful when you want to:

- Go through a playlist you created earlier and give retroactive feedback
- Clean up a playlist by removing tracks that no longer fit
- Teach SpotyVibe more about your taste based on real listening experience

To open it, click **Show** on the **🔄 Refine Playlist** header (or click anywhere on the header) inside the Spotify section.

![Refine Playlist section expanded](/docs/screenshots/22_refine_playlist_section.png)

---

<a id="select-and-load-a-playlist"></a>
### Select and Load a Playlist

1. Expand the **Refine Playlist** section — your Spotify playlists load automatically into the dropdown
2. Select a playlist from the **dropdown**
3. Click **🔄 Load Playlist**

A loading spinner appears below the button while SpotyVibe fetches the tracks. Once loaded, the tracks appear inside the section, below the button, separated by a divider. Track cards look similar to the Discover suggestion list.

![Playlist dropdown with playlists loaded](/docs/screenshots/37_playlist_dropdown.png)

---

<a id="review-tracks"></a>
### Review Tracks

Each track card shows:

- Album artwork (click to preview)
- Artist and track name
- Spotify links (track, artist, album)
- Action buttons: **💬 Feedback** (opens the reason panel) and **🗑 Delete** (removes from the Spotify playlist without recording feedback)

You can also click the album art to open the Spotify preview player. When previewing from the Refine list, the prev/next navigation operates within the review track list.

![Review track cards](/docs/screenshots/38_review_track_cards.png)

---

<a id="like-a-track-refine"></a>
### Like a Track (Refine)

Click **💬 Feedback** on the track card and then click **👍 Like** at the bottom of the panel. You can optionally edit the artist, track name, and add a reason before submitting.

After submitting, the track animates out of the review list. The track **stays in the Spotify playlist** — only your taste profile is updated.

![Like feedback form in Refine section](/docs/screenshots/39_review_like_form.png)

---

<a id="dislike-a-track-refine"></a>
### Dislike a Track (Refine)

Click **💬 Feedback** on the track card and then click **👎 Dislike** at the bottom of the panel. You can optionally edit the artist, track name, and add a reason before submitting.

After submitting, the track is:

1. **Recorded as a dislike** in your taste profile
2. **Removed from the Spotify playlist**

The card animates out of the review list.

![Dislike feedback form in Refine section](/docs/screenshots/40_review_dislike_form.png)

---

<a id="dismiss-a-track"></a>
### Delete a Track

Click **🗑 Delete** to remove a track from the Spotify playlist **without** recording any taste profile feedback.

Use this for tracks you feel neutral about but want to remove from the playlist.

The card animates out of the review list.

![Dismiss button on review track card](/docs/screenshots/41_review_dismiss_button.png)

---

<a id="taste-dashboard"></a>
## Taste Dashboard

Below the Music Profile editor, the **"Your taste at a glance"** section shows interactive charts that visualise your listening patterns. The data is aggregated automatically from your playlist generation history.

<a id="opening-the-dashboard"></a>
### Opening the Dashboard

Click **Show** (or click the section header) to expand the dashboard panel. If you have not generated enough playlists yet, you will see a **"Not enough data yet"** placeholder instead of charts. Charts appear once you have at least **10 unique tracks** across your generation runs.

<a id="charts"></a>
### Charts

The dashboard displays three chart types:

- **Top Genres** — A donut chart showing your most frequent genres, derived from Spotify artist metadata. Hover over a slice to see the genre name and track count.
- **Energy × Valence** — A scatter plot mapping the mood of your tracks. The horizontal axis represents valence (sad → happy) and the vertical axis represents energy (calm → intense). Hover over a dot to see the artist and track title. A footnote reminds you that energy and valence values are AI estimates, not exact measurements.
- **Decades** — A bar chart showing the release decades of your tracks, derived from Spotify album data.

<a id="sentiment-sections"></a>
### Sentiment Sections

If you have given feedback on tracks (likes/dislikes), the dashboard splits into up to three sub-sections:

- **All tracks** — The main view aggregating every track from your runs.
- **Liked tracks** — Charts based only on tracks you liked (👍).
- **Disliked tracks** — Charts based only on tracks you disliked (👎).

The liked and disliked sections only appear when there is enough data to display.

<a id="profile-isolation"></a>
### Profile Isolation

Each profile has its own independent dashboard data. When you **switch profiles** or **create a new profile**, the dashboard is fully reset:

- All charts are cleared immediately.
- The empty-state placeholder is shown.
- If the dashboard panel is currently expanded, fresh data is fetched automatically for the newly active profile.

This means you will never see stale charts from a previous profile. A brand-new profile always starts with the "Not enough data yet" message until you generate playlists under that profile.

---

<a id="song-list--run-history"></a>
## Song List & Run History

<a id="run-history"></a>
### Run History

SpotyVibe keeps the **last 5** playlist generation runs in the **History** section, located inside the Spotify panel below Refine Playlist. Click **Show history** or click anywhere on the section header to expand it.

For each run you can see:

- when the run happened
- how many tracks were added
- a link to the playlist (if it still exists on Spotify)

**Click any history entry** to expand it and reveal the full list of tracks (Artist — Track) that were added during that run. Click again to collapse.

Older runs beyond the most recent 5 are automatically removed to keep the list concise.

![Run History section with expanded entry](/docs/screenshots/23_run_history.png)

---

<a id="persistent-song-list"></a>
### Persistent Song List

Your generated song list is saved inside the Discover Music section and restored when you reload the page — you never lose your track cards between sessions.

This means:

- You can revisit previous suggestions
- You do not lose the list when returning to the app
- You can keep reviewing songs over time

If the list becomes too full, remove some tracks before generating more.

![Song list with saved tracks](/docs/screenshots/42_history_song_list.png)

---

<a id="mobile-usage"></a>
## Mobile Usage

SpotyVibe also works well on phones and tablets.

On mobile devices:

- panels stack vertically
- buttons are easy to tap
- dialogs and forms adapt to smaller screens

You can use the same main flow:

1. Complete setup
2. Connect Spotify
3. Build your profile
4. Generate playlists
5. Review songs and provide feedback

![Mobile view of the home screen](/docs/screenshots/43_mobile_view.png)

---

<a id="troubleshooting--tips"></a>
## Troubleshooting & Tips

<a id="troubleshooting"></a>
### Troubleshooting

**I cannot generate a playlist**  
Make sure you have:

- entered all required credentials
- connected your Spotify account
- completed your music profile

**Spotify connection does not work**  
Try disconnecting and connecting Spotify again from the menu.

**The recommendations are not matching my taste**  
Update your music profile with clearer descriptions and more specific likes/dislikes.

**The app keeps suggesting similar songs**  
Use more detailed profile edits, increase interest in new artists, and give direct feedback on tracks you do or do not like.

**Too few tracks are being added**  
Widen your audio filters or try again with fewer restrictions.

![Example warning or error message](/docs/screenshots/44_warning_message.png)

---

<a id="final-tips"></a>
### Final Tips

To get the best results from SpotyVibe:

- Be specific in your music profile
- Give feedback often
- Update your profile when your taste changes
- Use audio filters only when you want tighter control
- Use run history to review past generations

The app improves as you interact with it, so regular feedback leads to better discoveries.

---

Enjoy discovering your next favorite music with **SpotyVibe**.
