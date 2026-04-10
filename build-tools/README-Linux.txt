═══════════════════════════════════════════════════════════════
  SpotyVibe — Linux Installation Guide
═══════════════════════════════════════════════════════════════

  AI-powered music discovery: personalised Spotify playlists
  based on your taste, powered by OpenAI.

───────────────────────────────────────────────────────────────
  PREREQUISITES
───────────────────────────────────────────────────────────────

  1. Python 3.10 or newer with the venv module

     Debian / Ubuntu:
         sudo apt install python3 python3-venv

     Fedora:
         sudo dnf install python3

     Arch:
         sudo pacman -S python

  2. A Spotify Premium account

  3. API keys (free to obtain):
     • OpenAI API Key  → https://platform.openai.com/api-keys
     • Spotify Client ID & Secret → https://developer.spotify.com/dashboard
       (Create an app and add this redirect URI:
        http://127.0.0.1:5000/callback)

───────────────────────────────────────────────────────────────
  HOW TO START
───────────────────────────────────────────────────────────────

  Open a terminal in this folder and run:

      ./start.sh

  Or, if you get "Permission denied":

      bash start.sh

  On the first launch:
    • A virtual environment (.venv/) is created automatically
    • Dependencies are installed
    • The server starts and your browser opens to
      http://127.0.0.1:5000

  On subsequent launches:
    • Starts in seconds (no reinstall)

  To stop: press Ctrl+C.

───────────────────────────────────────────────────────────────
  HEADLESS / SSH / NO DISPLAY
───────────────────────────────────────────────────────────────

  If no display server (X11/Wayland) is detected, the launcher
  skips opening a browser and prints the URL instead.

  Open http://127.0.0.1:5000 in any browser that can reach
  the machine.

───────────────────────────────────────────────────────────────
  WHAT'S IN THIS FOLDER
───────────────────────────────────────────────────────────────

  start.sh              ← Run this to start SpotyVibe
  build-tools/start.sh  ← Main launcher (called automatically)
  app.py                ← Flask web server
  config.py             ← Configuration & credential management
  requirements-core.txt ← Python dependencies (installed automatically)
  core/src/             ← Backend logic
  frontend/             ← HTML, CSS, JS, translations
  prompts/              ← AI prompt templates
  data/                 ← Profile template

  Credentials are stored in your system keyring when available.
  Fallback: ~/.local/share/spotyvibe/.credentials

───────────────────────────────────────────────────────────────
  TROUBLESHOOTING
───────────────────────────────────────────────────────────────

  "Python not found" or "Python 3.10+ required"
    → Install or upgrade Python for your distribution (see above)

  "Python venv module is not installed"
    → Debian/Ubuntu: sudo apt install python3-venv

  "Port 5000 already in use"
    → Find the process: lsof -i :5000
      Kill it: kill <PID>

  "pip install failed"
    → Make sure you have an internet connection.
      The first launch downloads Python packages.

  Browser did not open?
    → Open manually: http://127.0.0.1:5000

  Permission denied on start.sh?
    → chmod +x start.sh build-tools/start.sh
      or use: bash start.sh

───────────────────────────────────────────────────────────────
  MORE INFORMATION
───────────────────────────────────────────────────────────────

  Full documentation: https://github.com/mikgra91/spotyvibe

  Enjoy discovering your next favourite music with SpotyVibe!

