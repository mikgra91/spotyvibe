"""SpotyVibe CLI — start the Flask server and open the browser.

Entry point for both ``spotyvibe`` console command and ``python -m spotyvibe``.
"""

import os
import signal
import socket
import sys
import threading
import webbrowser

PORT = 5000


def _port_in_use(port: int) -> bool:
    """Return True if something is already listening on *port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    if _port_in_use(PORT):
        print(f"\u2716 Port {PORT} is already in use.", file=sys.stderr)
        print(
            f"  Port {PORT} is required \u2014 Spotify OAuth redirect is "
            f"fixed to http://127.0.0.1:{PORT}/callback.",
            file=sys.stderr,
        )
        if sys.platform == "darwin":
            print(
                "\n  macOS AirPlay Receiver uses port 5000 by default.\n"
                "  Disable it: System Settings \u2192 General \u2192 "
                "AirDrop & Handoff \u2192 AirPlay Receiver \u2192 Off\n",
                file=sys.stderr,
            )
        sys.exit(1)

    # Ensure the package directory is on sys.path so app.py's
    # internal imports (``from config import ...``, ``from core.src...``)
    # resolve correctly from the installed wheel location.
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    # Packaged installs use the on-disk SQLite corpus (built once, then opened
    # in ~20ms per launch instead of re-parsing the ~180k-artist corpus). Must
    # be set before importing app, whose module-level code reads it. First run
    # builds the DB (~30s) — a one-time cost.
    os.environ.setdefault("SPOTYVIBE_SQLITE_CORPUS", "1")

    # Import *after* path setup — app.py runs load_config() at import time.
    from app import app  # noqa: E402

    def _open_browser():
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    print(f"\u2139  Starting SpotyVibe at http://127.0.0.1:{PORT}")
    print("Press Ctrl+C to stop.\n")

    threading.Timer(1.5, _open_browser).start()

    try:
        app.run(host="127.0.0.1", port=PORT)
    except KeyboardInterrupt:
        print("\n\u2714 Stopped. Goodbye!")


if __name__ == "__main__":
    main()

