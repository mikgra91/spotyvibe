"""Desktop-only entry point for PyInstaller builds.

Why this exists:
- Keeps app.py unchanged (source + Android flows stay stable)
- Forces debug=False and use_reloader=False in packaged desktop builds
- Embeds a native window (via pywebview) that renders the Flask app,
  giving users a real desktop-app experience
- Closing the window terminates the Flask server and the process cleanly —
  no orphaned background processes

The Flask app itself lives in app.py as `app`.
"""

from __future__ import annotations

import socket
import threading
import time

from app import app


def _wait_for_server(host: str, port: int, timeout_s: float = 15.0) -> bool:
    """Block until the Flask server accepts connections (or timeout)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"

    # Start Flask in a daemon thread — it dies automatically when main exits.
    flask_thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    # Wait for the server to be ready before opening the window.
    if not _wait_for_server(host, port):
        print("ERROR: Flask server did not start within timeout.")
        return

    # Open a native window pointing at the Flask app.
    # pywebview blocks on `start()` until the window is closed, then we exit.
    import webview  # noqa: WPS433 — imported late so Flask starts first

    window = webview.create_window(
        title="SpotyVibe",
        url=url,
        width=1280,
        height=900,
        min_size=(800, 600),
        text_select=True,
    )
    webview.start()
    # Window closed → process ends (daemon Flask thread stops automatically).


if __name__ == "__main__":
    main()
