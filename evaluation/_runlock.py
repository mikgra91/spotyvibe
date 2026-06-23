"""Cross-platform exclusive run-lock for cost-incurring scripts.

Why this exists
---------------
On 2026-04-27 three orphan ``build_top_tracks_overlay.py`` processes
ran in parallel from earlier sessions and burned the daily Spotify
quota in seconds (HTTP 429, ~66 min cooldown). The same risk applies
to ``evaluation/run_evaluation.py``, which spends real OpenAI money
per run.

Design (intentionally minimal — prototype-grade)
------------------------------------------------
* A single lock file per "kind" (e.g. ``evaluation/.run.lock``).
* Acquire via ``O_CREAT | O_EXCL`` so the existence check + creation
  is atomic. No race window.
* On acquire, write ``{pid, started_at, host, kind}`` as JSON so the
  failure message can name the offending process.
* On release (``atexit`` + ``SIGINT`` / ``SIGTERM`` handler) the lock
  file is removed. If the process is hard-killed (``taskkill /F``) the
  file is left behind — see ``--release-lock`` escape hatch.
* No "is the previous PID alive?" detection. Hard-failing on a stale
  lock is the safer default; the user knows when they killed something.
* ``release_stale_lock(path)`` helper for the escape hatch.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class LockHeldError(RuntimeError):
    """Raised when an exclusive lock is already held by another process."""

    def __init__(self, path: Path, holder: dict | None):
        self.path = path
        self.holder = holder or {}
        msg = f"Run lock {path} is already held"
        if holder:
            msg += (
                f" by PID {holder.get('pid')} on {holder.get('host')} "
                f"(started {holder.get('started_at')}, kind={holder.get('kind')})"
            )
        msg += (
            ". Refusing to start a second concurrent run. "
            "If you are sure no other process is running, delete the lock file "
            f"or pass --release-lock to clear it."
        )
        super().__init__(msg)


def _read_holder(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def acquire(path: Path, kind: str) -> Callable[[], None]:
    """Acquire an exclusive run lock at *path*.

    Returns a no-arg ``release()`` callable. The lock is also released
    automatically on interpreter exit and on ``SIGINT`` / ``SIGTERM``.

    Raises ``LockHeldError`` if the lock file already exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic create-or-fail. O_EXCL is the whole point.
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise LockHeldError(path, _read_holder(path))

    payload = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "kind": kind,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        # If we can't even write the metadata, don't leave a half-baked
        # lock behind — drop it so the next attempt can proceed.
        try:
            os.unlink(str(path))
        except Exception:
            pass
        raise

    released = {"done": False}

    def release() -> None:
        if released["done"]:
            return
        released["done"] = True
        try:
            # Only unlink if we still own it (PID still matches).
            holder = _read_holder(path)
            if holder and holder.get("pid") == os.getpid():
                os.unlink(str(path))
        except FileNotFoundError:
            pass
        except Exception:
            # Best-effort cleanup; never let lock release crash the program.
            pass

    atexit.register(release)

    # Also release on Ctrl-C / kill so the user doesn't have to manually
    # clear the lock after a clean shutdown.
    def _on_signal(signum, frame):  # pragma: no cover — signal path
        release()
        # Re-raise default behaviour (terminate).
        sys.exit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            # SIGTERM is not settable on all Windows interpreters; ignore.
            pass

    return release


def release_stale_lock(path: Path) -> bool:
    """Force-remove a lock file. Returns True if a file was removed."""
    try:
        os.unlink(str(path))
        return True
    except FileNotFoundError:
        return False

