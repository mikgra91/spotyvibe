# SpotyVibe User Guide

Welcome to **SpotyVibe** — your AI-powered music discovery assistant.  
This guide explains how to use the **SpotyVibe interface** to set up your preferences, connect Spotify, generate playlists, and refine recommendations over time.

---

## Table of Contents

- [Getting Started](#getting-started)
  - [Overview](#overview)
  - [Before You Start](#before-you-start)
  - [Understanding the Main Screen](#understanding-the-main-screen)
- [Account Setup](#account-setup)
  - [Open the Menu](#open-the-menu)
  - [Enter Your Credentials](#enter-your-credentials)
  - [Connect Your Spotify Account](#connect-your-spotify-account)
- [User Preferences](#user-preferences)
  - [Settings](#settings)
  - [Language](#language)
  - [Theme](#theme)
- [Music Profile](#music-profile)
  - [Create Your Music Profile](#create-your-music-profile)
    - [Select or Create a Profile](#select-or-create-a-profile)
    - [Edit Your Profile](#edit-your-profile)
    - [Describe Your Vibe](#describe-your-vibe)
    - [Core Description](#core-description)
    - [Must Have](#must-have)
    - [Soft Preferences](#soft-preferences)
    - [Avoid](#avoid)
    - [Save or AI Profile Update](#save-or-ai-profile-update)
  - [Import, Export, Reset, and Delete Your Profile](#import-export-reset-and-delete-your-profile)
  - [Updating Your Taste Over Time](#updating-your-taste-over-time)
- [Discovery & Analysis](#discovery--analysis)
  - [Band/Song Analysis](#bandsong-analysis)
- [Playlist Generation](#playlist-generation)
  - [Choose a Playlist Mode](#choose-a-playlist-mode)
  - [Use Audio Filters](#use-audio-filters)
  - [Start Generation](#start-generation)
  - [Stop Early or Use Current Tracks](#stop-early-or-use-current-tracks)
- [Track Review & Feedback](#track-review--feedback)
  - [Preview a Track](#preview-a-track)
  - [Open Spotify Links](#open-spotify-links)
  - [Like a Track](#like-a-track)
  - [Dislike a Track](#dislike-a-track)
  - [Remove a Track](#remove-a-track)
- [Refine Playlist](#refine-playlist)
  - [Select and Load a Playlist](#select-and-load-a-playlist)
  - [Review Tracks](#review-tracks)
  - [Like a Track (Refine)](#like-a-track-refine)
  - [Dislike a Track (Refine)](#dislike-a-track-refine)
  - [Dismiss a Track](#dismiss-a-track)
- [Song List & Run History](#song-list--run-history)
  - [Persistent Song List](#persistent-song-list)
  - [Run History](#run-history)
- [Mobile Usage](#mobile-usage)
- [Troubleshooting & Tips](#troubleshooting--tips)
  - [Troubleshooting](#troubleshooting)
  - [Final Tips](#final-tips)

---

## Getting Started

### Overview

SpotyVibe helps you discover music based on your personal taste.  
You describe what you like, connect your Spotify account, and let the app generate playlist suggestions tailored to you.

The more feedback you give, the better the recommendations become.

> **Screenshot placeholder:** Main home screen / dashboard

---

### Before You Start

To use SpotyVibe, make sure you have:

- A **Spotify Premium** account
- Your **OpenAI API Key**
- Your **Spotify Client ID**
- Your **Spotify Client Secret**

You will enter these in the app during setup.

> **Screenshot placeholder:** Credentials screen

---

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

> **Screenshot placeholder:** Header with menu, language, and theme controls

---

## Account Setup

### Open the Menu

Click the **☰ menu icon** (hamburger menu) in the top-right corner to open the menu.

From here, you can access:

- **Credentials**
- **Settings**
- **Disconnect Spotify** (if already connected)

> **Screenshot placeholder:** Burger menu open

---

### Enter Your Credentials

Open **Credentials** and enter:

- **OpenAI API Key**
- **Spotify Client ID**
- **Spotify Client Secret**

Click **Save** when finished. Your API keys are stored securely in a separate credentials file — app preferences (model, playlist size, etc.) are stored in a separate settings file.

If the information is correct, you can proceed to connect Spotify.

> **Screenshot placeholder:** Credentials form filled in

---

### Connect Your Spotify Account

After saving your credentials, SpotyVibe will prompt you to connect Spotify.

Click **Connect to Spotify** and complete the sign-in flow.

Once connected:

- The connection banner disappears
- You can start generating playlists
- SpotyVibe can create and manage playlists for you

If your session expires later, simply reconnect.

> **Screenshot placeholder:** Connect to Spotify banner

---

## User Preferences

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

> **Screenshot placeholder:** Settings panel

---

### Language

Use the **language picker** at the top of the page to switch the interface language.

This changes text such as:

- Buttons
- Labels
- Messages
- Menus

> **Screenshot placeholder:** Language selector

---

### Theme

SpotyVibe includes multiple visual themes.

Use the **theme switcher** near the top of the page to select your preferred look.

Themes change the visual style of the interface but do not affect playlist results.

> **Screenshot placeholder:** Theme switcher

---

## Music Profile

### Create Your Music Profile

Before SpotyVibe can generate good recommendations, you need to teach it your taste.

In the **OpenAI** section, look at the **Music Profile** header. You will see a **profile dropdown** that lets you manage multiple profiles.

#### Select or Create a Profile

1. Click **+ Create new Profile** below the dropdown.
2. Type a name — for example "Workout", "Chill", or "Discovery" — and press **Enter** or click **✓**.
3. The new profile is automatically selected and ready to edit.

You can create as many profiles as you want. Each profile is completely independent — great for different moods, activities, or family members.

To switch profiles, select a different one from the dropdown. To delete the current profile, expand the editor and click the 🗑 **Delete** button.

> **Screenshot placeholder:** Profile selector dropdown with create input

---

#### Edit Your Profile

Click **Edit profile** or click anywhere on the **Music Profile** header to expand the editor.

You will see several sections that help describe your ideal music.

> **Screenshot placeholder:** Music Profile editor open

---

#### Describe Your Vibe

This is the quickest way to tell SpotyVibe what you are looking for.

Write in everyday language — like chatting with a friend — what kind of music you want. For example:

- "I love energetic rock with theatrical vocals like Queen. Surprise me with something new but keep it high-energy and melodic!"
- "More jazz influence, less electronic. Think Snarky Puppy meets Radiohead."
- "Make my profile darker and heavier, but keep the melodies."

When you use **AI Profile Update**, SpotyVibe translates your words into a structured profile automatically. After the update completes, the field is **cleared automatically** — your input has been incorporated into the structured profile sections, so the one-time instruction is no longer needed.

If you fill in this field, the **Core Description** below becomes optional — the AI will generate one for you.

> **Screenshot placeholder:** Describe Your Vibe field

---

#### Core Description

This is the most important part of your profile.

Describe the kind of music you want using your own words, such as:

- genre
- mood
- energy
- atmosphere
- reference artists
- instruments
- vocals

This field should clearly explain your overall taste.

> **Screenshot placeholder:** Core Description field

---

#### Must Have

Use this section for qualities that every recommendation should have.

Examples:

- strong melodies
- emotional vocals
- energetic drums
- atmospheric guitar work

Enter one preference per line.

> **Screenshot placeholder:** Must Have section

---

#### Soft Preferences

Use this section for qualities that are welcome, but not required.

Examples:

- slight progressive elements
- warm production
- occasional synth textures

Enter one preference per line.

> **Screenshot placeholder:** Soft Preferences section

---

#### Avoid

Use this section for sounds or traits you do **not** want.

Examples:

- overly electronic production
- slow ballads
- harsh vocals
- repetitive choruses

Enter one item per line.

> **Screenshot placeholder:** Avoid section

---

#### Save or AI Profile Update

After editing your profile, you can choose one of two actions:

- **Save**  
  Stores your profile as written. Works even if fields are empty.

- **AI Profile Update**  
  Lets SpotyVibe refine and organize your input for you. Requires either a Core Description or a Vibe message — a yellow warning appears if both are empty.

Use **Save** for quick edits.  
Use **AI Profile Update** when you want the app to help improve the profile.

> **Screenshot placeholder:** Save and AI Profile Update buttons

---

### Import, Export, Reset, and Delete Your Profile

When the profile editor is open, profile management buttons appear below the **Last trained** status line in the section header:

- **Import**  
  Load a saved profile file into the current profile.

- **Export**  
  Download your current profile as a JSON file.

- **Reset to history**  
  Restore the previous version of your profile (one-step undo).

- **Delete**  
  Permanently remove the current profile and its history. This cannot be undone. If other profiles exist, the first one is automatically selected.

This is useful if you want to back up your profile, move it to another device, clean up unused profiles, or undo a recent change.

> **Screenshot placeholder:** Import / Export / Reset / Delete controls

---

### Updating Your Taste Over Time

Your taste may change, and SpotyVibe is designed to evolve with you.

To update your preferences:

1. Go back to the **OpenAI** section
2. Click **Edit profile**
3. Update your description or preference lists
4. Save or run **AI Profile Update**
5. Generate again

The more accurately your profile reflects your current taste, the better your future playlists will be.

> **Screenshot placeholder:** Editing an existing profile

---

## Discovery & Analysis

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

> **Screenshot placeholder:** Band/Song Analysis panel

---

## Playlist Generation

Once your profile is ready and Spotify is connected, go to the **Spotify** section and click **Show** on the **Discover Music** header (or click anywhere on the header) to expand it.

This is where SpotyVibe creates playlist suggestions based on your taste. The section is collapsed by default to keep the page compact.

> **Screenshot placeholder:** Discover Music section expanded

---

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

> **Screenshot placeholder:** Playlist mode selector

---

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

> **Screenshot placeholder:** Audio Filters sub-panel inside Discover Music

> **Screenshot placeholder:** Band/Song Analysis with ⇒ Filter buttons

---

### Start Generation

Click **Generate & Create Playlist** to begin.

A loading spinner appears below the button inside the Discover Music section. Progress messages are displayed underneath the spinner as SpotyVibe works:

1. Generate song suggestions
2. Check them on Spotify
3. Build the playlist
4. Show the results inside the section (below a divider)
5. Provide a link to open the playlist in Spotify

> **Screenshot placeholder:** Generation in progress with inline spinner

---

### Stop Early or Use Current Tracks

During generation, two helpful options may appear:

- **Cancel**  
  Stops the current generation without applying changes

- **Use X tracks now**  
  Stops generation and creates the playlist using the tracks already found

This is useful if you already like the results and do not want to wait longer.

> **Screenshot placeholder:** Cancel and Use X Tracks Now buttons

---

## Track Review & Feedback

After generation, SpotyVibe displays the suggested tracks **inside the Discover Music section**, below the Generate button, separated by a divider. A completion banner and playlist link appear first, followed by the track cards. Track cards glow green on hover.

Each card may show:

- Track name
- Artist
- Album artwork
- Reason for recommendation
- Action buttons

You can review each song and decide what to do next.

> **Screenshot placeholder:** Track cards after generation

---

### Preview a Track

Click the album art on a song card to open the preview overlay at the bottom of the screen.

The preview uses a three-zone layout:

1. **Spotify player** — the embedded player (centered, wide)
2. **Action tabs** — a vertical column of file-cabinet register-tab buttons (👍 👎 ✕) to the right of the player
3. **Feedback form** — slides in to fill the remaining space when you click 👍 or 👎

Clicking the same tab again closes the feedback form. The ✕ button dismisses the track immediately without opening a form. Active tabs glow green (like) or red (dislike).

Use the ‹ and › arrows to navigate between tracks without closing the overlay.

> **Note:** The embedded Spotify player provides **~30-second previews**. Full-length playback is not available because the embed runs in an isolated iframe that cannot access your Spotify session due to browser third-party cookie restrictions. To listen to the full track, click the Spotify icon inside the player or use the Spotify links on the song card.

> **Screenshot placeholder:** Preview player open

---

### Open Spotify Links

Each song card includes quick links to open content in Spotify, such as:

- the track
- the artist
- the album

Use these links to explore music in more detail.

> **Screenshot placeholder:** Spotify quick links on a song card

---

### Like a Track

Click **Like** if a track matches your taste.

You can optionally add a short reason before submitting.

Liking tracks helps SpotyVibe learn what works well for you.

Examples of reasons:

- perfect mood
- great vocals
- strong melody
- exactly the sound I want

> **Screenshot placeholder:** Like feedback form

---

### Dislike a Track

Click **Dislike** if a track does not fit.

You can optionally add a reason to explain why.

Examples:

- too slow
- wrong atmosphere
- too electronic
- weak chorus

This helps SpotyVibe avoid similar tracks in future runs.

> **Screenshot placeholder:** Dislike feedback form

---

### Remove a Track

Click **Remove** to take a song out of the list without recording it as like or dislike.

Use this for tracks you feel neutral about.

> **Screenshot placeholder:** Remove button on song card

---

## Refine Playlist

The **Refine Playlist** section lets you load an existing Spotify playlist and review its tracks one by one. You can like, dislike, or dismiss each track to refine your taste profile and clean up the playlist at the same time.

This is useful when you want to:

- Go through a playlist you created earlier and give retroactive feedback
- Clean up a playlist by removing tracks that no longer fit
- Teach SpotyVibe more about your taste based on real listening experience

To open it, click **Show** on the **🔄 Refine Playlist** header (or click anywhere on the header) inside the Spotify section.

> **Screenshot placeholder:** Refine Playlist section expanded

---

### Select and Load a Playlist

1. Expand the **Refine Playlist** section — your Spotify playlists load automatically into the dropdown
2. Select a playlist from the **dropdown**
3. Click **🔄 Load Playlist**

A loading spinner appears below the button while SpotyVibe fetches the tracks. Once loaded, the tracks appear inside the section, below the button, separated by a divider. Track cards look similar to the Discover suggestion list.

> **Screenshot placeholder:** Playlist dropdown with playlists loaded

---

### Review Tracks

Each track card shows:

- Album artwork (click to preview)
- Artist and track name
- Spotify links (track, artist, album)
- Action buttons: **👍 Like**, **👎 Dislike**, **✕ Dismiss**

You can also click the album art to open the Spotify preview player. When previewing from the Refine list, the prev/next navigation operates within the review track list.

> **Screenshot placeholder:** Review track cards

---

### Like a Track (Refine)

Click **👍 Like** to record positive feedback for a track.

A feedback form opens where you can optionally edit the artist, track name, and add a reason.

After submitting, the track animates out of the review list. The track **stays in the Spotify playlist** — only your taste profile is updated.

> **Screenshot placeholder:** Like feedback form in Refine section

---

### Dislike a Track (Refine)

Click **👎 Dislike** to record negative feedback.

A feedback form opens where you can optionally edit the artist, track name, and add a reason.

After submitting, the track is:

1. **Recorded as a dislike** in your taste profile
2. **Removed from the Spotify playlist**

The card animates out of the review list.

> **Screenshot placeholder:** Dislike feedback form in Refine section

---

### Dismiss a Track

Click **✕ (Dismiss)** to remove a track from the Spotify playlist **without** recording any taste profile feedback.

Use this for tracks you feel neutral about but want to remove from the playlist.

The card animates out of the review list.

> **Screenshot placeholder:** Dismiss button on review track card

---

## Song List & Run History

### Run History

SpotyVibe keeps the **last 5** playlist generation runs in the **History** section, located inside the Spotify panel below Refine Playlist. Click **Show history** or click anywhere on the section header to expand it.

For each run you can see:

- when the run happened
- how many tracks were added
- a link to the playlist (if it still exists on Spotify)

**Click any history entry** to expand it and reveal the full list of tracks (Artist — Track) that were added during that run. Click again to collapse.

Older runs beyond the most recent 5 are automatically removed to keep the list concise.

> **Screenshot placeholder:** Run History section with expanded entry

---

### Persistent Song List

Your generated song list is saved inside the Discover Music section and restored when you reload the page — you never lose your track cards between sessions.

This means:

- You can revisit previous suggestions
- You do not lose the list when returning to the app
- You can keep reviewing songs over time

If the list becomes too full, remove some tracks before generating more.

> **Screenshot placeholder:** Song list with saved tracks

---

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

> **Screenshot placeholder:** Mobile view of the home screen

---

## Troubleshooting & Tips

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

> **Screenshot placeholder:** Example warning or error message

---

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