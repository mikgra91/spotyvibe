"""Desktop-only entry point for PyInstaller builds.

Why this exists:
- Keeps app.py unchanged (source + Android flows stay stable)
- Forces debug=False and use_reloader=False in packaged desktop builds
- Auto-opens the default browser to the local server URL (desktop convenience; always on)

The Flask app itself lives in app.py as `app`.
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

from app import app


def _open_browser_when_ready(url: str, host: str, port: int, timeout_s: float = 10.0) -> None:
    """Wait for the Flask server to accept connections, then open the browser."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    try:
        webbrowser.open(url)
    except webbrowser.Error:
        # Best-effort only; user can still manually navigate.
        pass


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"

    # Desktop UX: always open the default browser.
    # (PyInstaller build uses this entry point; app.py remains unchanged.)
    threading.Thread(
        target=_open_browser_when_ready,
        args=(url, host, port),
        daemon=True,
    ).start()

    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
