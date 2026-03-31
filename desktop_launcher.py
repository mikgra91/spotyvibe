"""Desktop-only entry point for PyInstaller builds.

Why this exists:
- Keeps app.py unchanged (source + Android flows stay stable)
- Forces debug=False and use_reloader=False in packaged desktop builds
- Auto-opens the default browser to the local server URL (desktop convenience; always on)
- Runs a system tray icon as the main loop so closing the browser window ends the
  process cleanly (right-click tray icon → Exit, or double-click to re-open the browser)

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


def _make_tray_icon_image():
    """Return a PIL Image for the system tray (32×32 green circle on dark bg)."""
    from PIL import Image, ImageDraw

    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Spotify-green filled circle with a thin dark border
    margin = 2
    draw.ellipse(
        [margin, margin, size - margin - 1, size - margin - 1],
        fill=(30, 215, 96, 255),
        outline=(20, 140, 60, 255),
        width=1,
    )
    return img


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"

    # Run Flask in a daemon thread so the process exits when the main thread ends.
    flask_thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    # Open browser once the server is accepting connections.
    threading.Thread(
        target=_open_browser_when_ready,
        args=(url, host, port),
        daemon=True,
    ).start()

    # System tray icon — this is the main loop; stopping it ends the process.
    try:
        import pystray

        def on_open(_icon, _item):
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                pass

        def on_exit(icon, _item):
            icon.stop()

        tray = pystray.Icon(
            "spotyvibe",
            _make_tray_icon_image(),
            "SpotyVibe",
            menu=pystray.Menu(
                pystray.MenuItem("Open SpotyVibe", on_open, default=True),
                pystray.MenuItem("Exit", on_exit),
            ),
        )
        tray.run()

    except ImportError:
        # pystray not available (dev environment without it) — block on the Flask thread.
        flask_thread.join()


if __name__ == "__main__":
    main()
