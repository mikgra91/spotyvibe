═══════════════════════════════════════════════════════════════
  SpotyVibe — macOS Installation Guide
═══════════════════════════════════════════════════════════════

  AI-powered music discovery: personalised Spotify playlists
  based on your taste, powered by OpenAI.

───────────────────────────────────────────────────────────────
  PREREQUISITES
───────────────────────────────────────────────────────────────

  1. Python 3.10 or newer
     • Recommended: install via Homebrew
         brew install python@3.12
     • Or download from: https://www.python.org/downloads/

  2. A Spotify Premium account

  3. API keys (free to obtain):
     • OpenAI API Key  → https://platform.openai.com/api-keys
     • Spotify Client ID & Secret → https://developer.spotify.com/dashboard
       (Create an app and add this redirect URI:
        http://127.0.0.1:5000/callback)

───────────────────────────────────────────────────────────────
  HOW TO START
───────────────────────────────────────────────────────────────

  Double-click  SpotyVibe.command  in Finder.

  On the first launch:
    • A Terminal window opens
    • A virtual environment is created automatically
    • Dependencies are installed
    • The server starts and your browser opens to
      http://127.0.0.1:5000

  On subsequent launches:
    • Starts in seconds (no reinstall)

  To stop: press Ctrl+C in the Terminal window.

───────────────────────────────────────────────────────────────
  FIRST-LAUNCH: GATEKEEPER WARNING
───────────────────────────────────────────────────────────────

  macOS Gatekeeper may block the script on first use.

  To fix this (only needed once):
    1. Right-click SpotyVibe.command in Finder
    2. Select "Open" from the context menu
    3. Click "Open" in the confirmation dialog

  If you see "app is damaged", run this in Terminal:
    xattr -cr /path/to/SpotyVibe-macOS/SpotyVibe.command

───────────────────────────────────────────────────────────────
  PORT 5000 CONFLICT (AirPlay Receiver)
───────────────────────────────────────────────────────────────

  macOS AirPlay Receiver uses port 5000 by default.
  If you see a "port in use" error:

    System Settings → General → AirDrop & Handoff
    → AirPlay Receiver → Off

───────────────────────────────────────────────────────────────
  WHAT'S IN THIS FOLDER
───────────────────────────────────────────────────────────────

  SpotyVibe.command     ← Double-click this to start
  build-tools/start.sh  ← Main launcher (called automatically)
  app.py                ← Flask web server
  config.py             ← Configuration & credential management
  requirements-core.txt ← Python dependencies (installed automatically)
  core/src/             ← Backend logic
  frontend/             ← HTML, CSS, JS, translations
  prompts/              ← AI prompt templates
  data/                 ← Profile template

  Credentials are stored in your macOS Keychain — never in
  plain text files inside this folder.

───────────────────────────────────────────────────────────────
  TROUBLESHOOTING
───────────────────────────────────────────────────────────────

  "Python not found"
    → Install Python 3.10+ via Homebrew: brew install python@3.12

  "Port 5000 already in use"
    → Disable AirPlay Receiver (see above) or stop the other
      process using: lsof -i :5000

  "pip install failed"
    → Make sure you have an internet connection.
      The first launch downloads Python packages.

  Browser did not open?
    → Open manually: http://127.0.0.1:5000

───────────────────────────────────────────────────────────────
  MORE INFORMATION
───────────────────────────────────────────────────────────────

  Full documentation: https://github.com/mikgra91/spotyvibe

  Enjoy discovering your next favourite music with SpotyVibe!

