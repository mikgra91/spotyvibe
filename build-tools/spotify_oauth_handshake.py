"""One-shot Spotify OAuth handshake for headless scripts.

Why this exists
---------------
The production app uses ``open_browser=False`` because the Flask UI
controls when/how the browser opens. Headless scripts (the eval
harness, the overlay-build script) need the opposite — let spotipy
auto-launch the browser AND auto-capture the redirect on the local
listener so the script can run unattended afterward.

Usage
-----
    python build-tools/spotify_oauth_handshake.py

Behaviour
---------
* If a valid cached token already exists at ``$LOCALAPPDATA/spotyvibe/
  .spotify-cache``, reports "already authorised" and exits 0 — no
  browser pop-up, no API call.
* Otherwise opens a browser tab, waits for the user to click "Agree",
  captures the redirect on ``http://127.0.0.1:5000/callback``, writes
  the cache file, and exits.
* Aborts cleanly if port 5000 is busy with a clear error message
  pointing at the conflict (Flask dev server is the usual culprit).
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402
from spotipy.oauth2 import CacheFileHandler, SpotifyOAuth  # noqa: E402

REDIRECT_URI = "http://127.0.0.1:5000/callback"
SCOPES = (
    "playlist-modify-private playlist-read-private "
    "user-read-private streaming"
)


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def main() -> int:
    config.load_config()
    cache_path = str(config._APP_DIR / ".spotify-cache")  # type: ignore[attr-defined]
    cache_handler = CacheFileHandler(cache_path=cache_path)

    auth = SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_handler=cache_handler,
        open_browser=True,  # headless script: auto-open + auto-listen
    )

    cached = auth.validate_token(cache_handler.get_cached_token())
    if cached:
        print(f"✅ Already authorised. Cache at {cache_path}")
        return 0

    if _port_busy(5000):
        print(
            "❌ Port 5000 is busy. spotipy needs it for the OAuth callback "
            "listener. Stop whatever is using port 5000 (usually the Flask "
            "dev server) and re-run.",
            file=sys.stderr,
        )
        return 2

    print("Opening browser for Spotify authorisation. Click 'Agree'…")
    token = auth.get_access_token(as_dict=False)
    if not token:
        print("❌ OAuth flow did not return a token.", file=sys.stderr)
        return 3
    print(f"✅ Authorised. Cache written to {cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

