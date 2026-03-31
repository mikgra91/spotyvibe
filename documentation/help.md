# SpotyVibe User Guide

Welcome to **SpotyVibe** — your AI-powered music discovery assistant.  
This guide explains how to use the **SpotyVibe interface** to set up your preferences, connect Spotify, generate playlists, and refine recommendations over time.

---

## Table of Contents

- [Overview](#overview)
- [Before You Start](#before-you-start)
- [Getting Started](#getting-started)
- [Understanding the Main Screen](#understanding-the-main-screen)
- [First-Time Setup](#first-time-setup)
  - [Open the Menu](#open-the-menu)
  - [Enter Your Credentials](#enter-your-credentials)
  - [Choose Your Settings](#choose-your-settings)
  - [Choose Language](#choose-language)
  - [Choose Theme](#choose-theme)
  - [Connect Your Spotify Account](#connect-your-spotify-account)
- [Create Your Music Profile](#create-your-music-profile)
  - [Core Description](#core-description)
  - [Must Have](#must-have)
  - [Soft Preferences](#soft-preferences)
  - [Avoid](#avoid)
  - [Save or AI Profile Update](#save-or-ai-profile-update)
- [Import, Export, and Reset Your Profile](#import-export-and-reset-your-profile)
- [Use Band/Song Analysis](#use-bandsong-analysis)
- [Generate a Playlist](#generate-a-playlist)
  - [Choose a Playlist Mode](#choose-a-playlist-mode)
  - [Use Audio Filters](#use-audio-filters)
  - [Start Generation](#start-generation)
  - [Stop Early or Use Current Tracks](#stop-early-or-use-current-tracks)
- [Review and Manage Suggested Tracks](#review-and-manage-suggested-tracks)
  - [Preview a Track](#preview-a-track)
  - [Open Spotify Links](#open-spotify-links)
  - [Like a Track](#like-a-track)
  - [Dislike a Track](#dislike-a-track)
  - [Remove a Track](#remove-a-track)
- [Song List and Run History](#song-list-and-run-history)
  - [Persistent Song List](#persistent-song-list)
  - [Run History](#run-history)
  - [Undo Last Run](#undo-last-run)
- [Updating Your Taste Over Time](#updating-your-taste-over-time)
- [Using SpotyVibe on Mobile](#using-spotyvibe-on-mobile)
- [Troubleshooting](#troubleshooting)

---

## Overview

SpotyVibe helps you discover music based on your personal taste.  
You describe what you like, connect your Spotify account, and let the app generate playlist suggestions tailored to you.

The more feedback you give, the better the recommendations become.

> **Screenshot placeholder:** Main home screen / dashboard

---

## Before You Start

To use SpotyVibe, make sure you have:

- A **Spotify Premium** account
- Your **OpenAI API Key**
- Your **Spotify Client ID**
- Your **Spotify Client Secret**

You will enter these in the app during setup.

> **Screenshot placeholder:** Credentials screen

---

## Getting Started

When you open SpotyVibe, you will see the main interface with two provider sections:

- **OpenAI** — Taste profile editor, AI profile updates, and AI Band/Song Analysis.
- **Spotify** — Spotify Metadata Analysis, playlist generation, audio filters, and run history.

Status pills at the top of each section show whether your credentials are configured and connected.

Before generating playlists, complete your setup and create your music profile.

---

## Understanding the Main Screen

The main screen is designed around a simple flow:

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

## First-Time Setup

### Open the Menu

Click the **gear icon** in the top-right corner to open the menu.

From here, you can access:

- **Credentials**
- **Settings**
- **Disconnect Spotify** (if already connected)

> **Screenshot placeholder:** Gear menu open

---

### Enter Your Credentials

Open **Credentials** and enter:

- **OpenAI API Key**
- **Spotify Client ID**
- **Spotify Client Secret**

Click **Save** when finished.

If the information is correct, you can proceed to connect Spotify.

> **Screenshot placeholder:** Credentials form filled in

---

### Choose Your Settings

Open **Settings** to customize how SpotyVibe works for you.

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

### Choose Language

Use the **language picker** at the top of the page to switch the interface language.

This changes text such as:

- Buttons
- Labels
- Messages
- Menus

> **Screenshot placeholder:** Language selector

---

### Choose Theme

SpotyVibe includes multiple visual themes.

Use the **theme switcher** near the top of the page to select your preferred look.

Themes change the visual style of the interface but do not affect playlist results.

> **Screenshot placeholder:** Theme switcher

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

## Create Your Music Profile

Before SpotyVibe can generate good recommendations, you need to teach it your taste.

In the **OpenAI** section, click **Edit profile**.

You will see several sections that help describe your ideal music.

> **Screenshot placeholder:** Music Profile editor open

---

### Core Description

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

### Must Have

Use this section for qualities that every recommendation should have.

Examples:

- strong melodies
- emotional vocals
- energetic drums
- atmospheric guitar work

Enter one preference per line.

> **Screenshot placeholder:** Must Have section

---

### Soft Preferences

Use this section for qualities that are welcome, but not required.

Examples:

- slight progressive elements
- warm production
- occasional synth textures

Enter one preference per line.

> **Screenshot placeholder:** Soft Preferences section

---

### Avoid

Use this section for sounds or traits you do **not** want.

Examples:

- overly electronic production
- slow ballads
- harsh vocals
- repetitive choruses

Enter one item per line.

> **Screenshot placeholder:** Avoid section

---

### Save or AI Profile Update

After editing your profile, you can choose one of two actions:

- **Save**  
  Stores your profile as written

- **AI Profile Update**  
  Lets SpotyVibe refine and organize your input for you

Use **Save** for quick edits.  
Use **AI Profile Update** when you want the app to help improve the profile.

> **Screenshot placeholder:** Save and AI Profile Update buttons

---

## Import, Export, and Reset Your Profile

Inside the profile editor, SpotyVibe also gives you profile management tools:

- **Import**  
  Load a saved profile file

- **Export**  
  Download your current profile

- **Reset to history**  
  Restore the previous version of your profile

This is useful if you want to back up your profile, move it to another device, or undo a recent change.

> **Screenshot placeholder:** Import / Export / Reset controls

---

## Use Band/Song Analysis

In the **OpenAI** section, you can open the **AI Band/Song Analysis** section.

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

## Generate a Playlist

Once your profile is ready and Spotify is connected, go to the **Spotify** section and use the **Generate Playlist** area.

This is where SpotyVibe creates playlist suggestions based on your taste.

> **Screenshot placeholder:** Generate Playlist section

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

The **Audio Filters** section lets you narrow down the mood and feel of the playlist.

Available filters may include:

- **Energy**
- **Valence**
- **Tempo**
- **Danceability**
- **Acousticness**

Use these when you want more control over the final sound.

Examples:

- Higher energy for workout music
- Lower valence for darker moods
- More acousticness for organic sound

If you are unsure, leave the filters unchanged.

> **Screenshot placeholder:** Audio Filters section expanded

---

### Start Generation

Click **Generate & Create Playlist** to begin.

SpotyVibe will:

1. Generate song suggestions
2. Check them
3. Build the playlist
4. Show the results in the app
5. Provide a link to open the playlist in Spotify

During generation, you will see progress updates.

> **Screenshot placeholder:** Generation in progress

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

## Review and Manage Suggested Tracks

After generation, SpotyVibe displays the suggested tracks as cards.

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

Use the **Preview** button on a song card to listen inside the app.

A player opens in an overlay so you can quickly sample the song without leaving SpotyVibe.

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

## Song List and Run History

### Persistent Song List

Your generated song list is kept in the app so you can return to it later.

This means:

- You can revisit previous suggestions
- You do not lose the list when returning to the app
- You can keep reviewing songs over time

If the list becomes too full, remove some tracks before generating more.

> **Screenshot placeholder:** Song list with saved tracks

---

### Run History

SpotyVibe keeps a history of playlist generation runs.

In the **Run History** section, you can review:

- when a run happened
- how many tracks were added
- the playlist link

This helps you keep track of previous sessions.

> **Screenshot placeholder:** Run History section

---

### Undo Last Run

If the most recent playlist run did not turn out well, use **Undo last run**.

This removes the tracks from the latest run from the related playlist.

Use this when you want to quickly reverse the last result.

> **Screenshot placeholder:** Undo Last Run button

---

## Updating Your Taste Over Time

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

## Using SpotyVibe on Mobile

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

## Troubleshooting

### I cannot generate a playlist
Make sure you have:

- entered all required credentials
- connected your Spotify account
- completed your music profile

### Spotify connection does not work
Try disconnecting and connecting Spotify again from the menu.

### The recommendations are not matching my taste
Update your music profile with clearer descriptions and more specific likes/dislikes.

### The app keeps suggesting similar songs
Use more detailed profile edits, increase interest in new artists, and give direct feedback on tracks you do or do not like.

### Too few tracks are being added
Widen your audio filters or try again with fewer restrictions.

> **Screenshot placeholder:** Example warning or error message

---

## Final Tips

To get the best results from SpotyVibe:

- Be specific in your music profile
- Give feedback often
- Update your profile when your taste changes
- Use audio filters only when you want tighter control
- Use run history and undo when experimenting

The app improves as you interact with it, so regular feedback leads to better discoveries.

---

Enjoy discovering your next favorite music with **SpotyVibe**.