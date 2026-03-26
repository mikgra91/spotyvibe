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

> **Important:** When creating your Spotify app in the Developer Dashboard, you must add `http://127.0.0.1:5000/callback` as a **Redirect URI** in the app settings. Without this, Spotify authentication will not work.

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

You should see the SpotyVibe interface.

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

### 3. Connect Your Spotify Account

After saving your credentials, a banner will appear asking you to **Connect to Spotify**. Click the link — a small popup window will open where you log in to Spotify and grant permission. Once authorised, the popup closes automatically and the banner disappears.

#### Disconnecting / Reconnecting

If your Spotify session expires or you need to re-authenticate, open the **⚙️ gear menu** and click **🔌 Disconnect Spotify**. This clears the cached token and the "Connect to Spotify" banner will reappear so you can log in again.

> **Tip:** If you see a `403 Forbidden` error during playlist generation, the app will automatically disconnect for you. Simply click **Connect to Spotify** in the warning banner to reconnect.

### 4. Train Your Taste Profile

Before generating suggestions, you need to tell the AI what kind of music you like. The UI is divided into two clearly labelled sections:

- **Step 1 — Taste Profile:** Teach the AI your preferences.
- **Step 2 — Generate Playlist:** Create a Spotify playlist from your profile.

To train your profile:

1. In the **Step 1** section, click **Edit profile**.
2. Write a description of your music taste in your own words. For example:
   - *"I love high-energy rock with big melodies, think Queen meets Muse. I hate slow ballads and anything too electronic."*
   - *"I'm into indie folk with acoustic guitars, warm vocals, and storytelling lyrics. Nothing too loud or aggressive."*
3. Click **Send to AI**.

The AI will analyse your description and build a structured taste profile. You can update it anytime — each update merges with what the AI already knows.

---

## Generating a Playlist

Once your profile is trained and Spotify is connected, go to the **Step 2 — Generate Playlist** section:

1. Click **▶ Generate & Create Playlist**.
2. Watch the progress updates as the AI works:
   - It asks GPT for 30 track suggestions based on your taste.
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

## Reviewing Suggestions

Each suggested track shows the **artist**, **track name**, and a short **reason** explaining why the AI picked it.

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

Every time you click **Generate & Create Playlist**, the AI produces a fresh batch of 30 suggestions. It never repeats tracks from previous runs — your history is remembered automatically.

The more feedback you give, the better the suggestions become.

---

## Updating Your Taste Profile

Your taste may evolve over time. You can update your profile at any point:

1. Click **Edit profile** in the Train Taste Profile section.
2. Write what has changed (e.g., *"I'm getting more into prog rock lately"* or *"Stop suggesting anything with screaming vocals"*).
3. Click **Send to AI**.

The AI merges your new input with the existing profile — nothing is lost. Your feedback history and past suggestions are always preserved.

> **Tip — Profile consistency matters:** If you explicitly reject an artist (via 👎 Dislike), make sure the same artist is not still listed as a confirmed favourite. Contradictions in the profile confuse the AI and cause bad suggestions. If you notice the AI keeps repeating things you've rejected, open the Train Taste Profile section and add a clear sentence like *"I strongly dislike [Artist] — never suggest them."*

---

## Debug Mode

If the AI's suggestions don't seem to match your preferences, you can enable **Debug Mode** to inspect the exact prompts being sent and the responses received:

1. Open **⚙️ gear menu → ⚙️ Settings**.
2. Check **"Log GPT requests & responses to debug file"**.
3. Click **Save**.

Now every GPT interaction (profile training and playlist generation) is logged to `%LOCALAPPDATA%\spotyvibe\debug.log`. Each entry includes a timestamp, the full messages sent to GPT, and the raw response.

You can open this file with any text editor to review and optimise the prompts in the `prompts/` directory.

> **Tip:** Disable debug mode when you're done — the log file can grow large over repeated runs.

---

## Where Are My Data Files?

All your personal data is stored outside the project in your system's app data folder:

| File | Location | Purpose |
|---|---|---|
| Credentials | `%LOCALAPPDATA%\spotyvibe\.credentials` | Your API keys and settings (never in the project folder). |
| Taste profile | `%LOCALAPPDATA%\spotyvibe\personalized_music_profile.json` | Your trained taste profile + history. |
| Spotify token | `%LOCALAPPDATA%\spotyvibe\.spotify-cache` | Cached Spotify authentication token. |
| Debug log | `%LOCALAPPDATA%\spotyvibe\debug.log` | GPT request/response log (only when debug mode is enabled). |

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
| **Spotify auth fails with "INVALID_CLIENT"** | Double-check your Client ID and Secret. Make sure `http://127.0.0.1:5000/callback` is listed as a Redirect URI in your Spotify Developer Dashboard. |
| **"403 Forbidden" during generation** | Your Spotify session has expired or permissions were revoked. The app disconnects automatically — click **Connect to Spotify** in the warning banner to reconnect. You can also manually disconnect via ⚙️ → 🔌 Disconnect Spotify. |
| **"OpenAI API key is not configured"** | Open ⚙️ → Credentials and enter your OpenAI API Key. |
| **GPT kept suggesting the same songs and stopped early** | This is the automatic loop-protection kicking in. After 3 consecutive batches where every suggestion was already in your history, the app stops and creates the playlist with whatever tracks were found. Click **▶ Use X tracks now** before that point, or update your taste profile with new preferences and re-run. |
| **"GPT could not generate any new tracks"** | Your history is very large and GPT can no longer find tracks outside it. Try describing new styles or genres in the Train Taste Profile section to expand the suggestion space. |
| **Most tracks "not found on Spotify"** | This can happen if the AI suggests very obscure tracks. Run the generation again — each attempt produces different results. |
| **"python-dotenv could not parse statement"** | Your credentials file is corrupted. Open ⚙️ → Credentials and re-save your keys. The app now prevents this from recurring. |
| **App won't start** | Make sure you ran `pip install -r requirements.txt` and are using Python 3.10+. |

