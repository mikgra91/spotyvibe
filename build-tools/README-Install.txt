═══════════════════════════════════════════════════════════════
  SpotyVibe — macOS & Linux Installation Guide
═══════════════════════════════════════════════════════════════

  AI-powered music discovery: personalised Spotify playlists
  based on your taste, powered by OpenAI.

───────────────────────────────────────────────────────────────
  WHAT'S IN THIS FOLDER
───────────────────────────────────────────────────────────────

  README.txt                  ← You are reading this
  spotyvibe-<version>.whl     ← The SpotyVibe application

  That's all you need. Follow the steps below.

───────────────────────────────────────────────────────────────
  STEP 1 — INSTALL PYTHON 3.10+
───────────────────────────────────────────────────────────────

  SpotyVibe requires Python 3.10 or newer.

  macOS (Homebrew — recommended):
      brew install python@3.12

  macOS (manual):
      Download from https://www.python.org/downloads/

  Debian / Ubuntu:
      sudo apt install python3 python3-pip

  Fedora:
      sudo dnf install python3 python3-pip

  Arch:
      sudo pacman -S python python-pip

  Verify your installation:
      python3 --version

───────────────────────────────────────────────────────────────
  STEP 2 — GET YOUR API KEYS (free)
───────────────────────────────────────────────────────────────

  You need two sets of API keys to use SpotyVibe:

  1. OpenAI API Key
     → https://platform.openai.com/api-keys
     Sign up or log in, then create a new API key.

  2. Spotify Client ID & Client Secret
     → https://developer.spotify.com/dashboard
     Create a new app and add this Redirect URI:

         http://127.0.0.1:5000/callback

     Copy the Client ID and Client Secret.

  You will also need a Spotify Premium account.

  You will enter these keys in SpotyVibe's onboarding screen
  on first launch — no config files to edit.

───────────────────────────────────────────────────────────────
  STEP 3 — INSTALL SPOTYVIBE
───────────────────────────────────────────────────────────────

  Open a terminal in this folder and run:

      pip install spotyvibe-*.whl

  (On some systems you may need to use pip3 instead of pip.)

  This installs SpotyVibe and all its dependencies. It only
  needs to be done once. To upgrade, download a new ZIP and
  run the same command again.

───────────────────────────────────────────────────────────────
  STEP 4 — RUN SPOTYVIBE
───────────────────────────────────────────────────────────────

  Simply run:

      spotyvibe

  What happens:
    • The server starts on http://127.0.0.1:5000
    • Your default browser opens automatically
    • On first launch, an onboarding screen asks for your
      API keys (see Step 2)

  To stop: press Ctrl+C in the terminal.

  To start again later, just run "spotyvibe" again.

───────────────────────────────────────────────────────────────
  macOS: PORT 5000 CONFLICT (AirPlay Receiver)
───────────────────────────────────────────────────────────────

  macOS AirPlay Receiver uses port 5000 by default.
  If you see "Port 5000 is already in use":

      System Settings → General → AirDrop & Handoff
      → AirPlay Receiver → Off

  This is only needed on macOS. Port 5000 is required
  because Spotify's OAuth redirect URI is fixed to
  http://127.0.0.1:5000/callback.

───────────────────────────────────────────────────────────────
  CREDENTIAL STORAGE
───────────────────────────────────────────────────────────────

  Your API keys are stored securely:
    • macOS: in your Keychain (Keychain Access app)
    • Linux: in your system keyring (if available),
      otherwise in ~/.local/share/spotyvibe/.credentials

  Keys are never stored inside this folder.

───────────────────────────────────────────────────────────────
  UNINSTALL
───────────────────────────────────────────────────────────────

  To remove SpotyVibe:

      pip uninstall spotyvibe

  Your API keys and music profiles are kept in your system
  keyring / application data and are not removed.

───────────────────────────────────────────────────────────────
  TROUBLESHOOTING
───────────────────────────────────────────────────────────────

  "python3: command not found"
    → Install Python 3.10+ (see Step 1)

  "pip: command not found"
    → Try: python3 -m pip install spotyvibe-*.whl

  "Port 5000 is already in use"
    → macOS: disable AirPlay Receiver (see above)
    → Linux: find the process with: lsof -i :5000
      then stop it with: kill <PID>

  Browser did not open?
    → Open manually: http://127.0.0.1:5000

  "No module named spotyvibe"
    → Make sure pip installed to the same Python version
      you are running. Try: python3 -m spotyvibe

───────────────────────────────────────────────────────────────
  MORE INFORMATION
───────────────────────────────────────────────────────────────

  Full documentation: https://github.com/mikgra91/spotyvibe

  Enjoy discovering your next favourite music with SpotyVibe!

