"""Android bootstrap entry-point for SpotyVibe.

The Android app (MainActivity.kt) starts Python via Chaquopy and calls
`spotyvibe_bootstrap.start(files_dir)`.

We must set SPOTYVIBE_FILES_DIR before importing the Flask app, because
config.py determines the credential/profile storage location at import-time.
"""

from __future__ import annotations

import os
import threading


def start(files_dir: str, host: str = "127.0.0.1", port: int = 5000) -> None:
    """Start the Flask server.

    This function is expected to block (it's called on a dedicated thread in
    MainActivity). It will only return if the server stops or crashes.

    Args:
        files_dir: Android `Context.getFilesDir()` absolute path.
        host: Bind host (default 127.0.0.1 for WebView localhost access).
        port: Bind port (default 5000).
    """
    # Make Android internal storage available to config.py
    os.environ["SPOTYVIBE_FILES_DIR"] = files_dir

    # Import after environment is set.
    import app as spotyvibe_app  # noqa: WPS433 (import inside function by design)

    # Flask's reloader starts a child process, which doesn't work reliably under Chaquopy.
    # Also, make the server threaded so it can serve multiple WebView requests.
    spotyvibe_app.app.run(
        debug=False,
        host=host,
        port=port,
        use_reloader=False,
        threaded=True,
    )


def start_in_background(files_dir: str, host: str = "127.0.0.1", port: int = 5000) -> threading.Thread:
    """Convenience helper for non-Android usage/testing."""
    t = threading.Thread(target=start, args=(files_dir, host, port), daemon=True)
    t.start()
    return t
