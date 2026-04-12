"""Run history — saves metadata about each generation run for review.

Each entry records: run_id, timestamp, playlist_id, playlist_url, tracks added.
Stored as a JSON array in the app data directory.

Schema versions:
  1 (implicit): tracks have optional 'reason' string
  2 (Wave 3):   tracks have 'rationale' array [{type, arg?}], no 'reason'
"""

import json
import logging
import threading
from datetime import datetime, timezone

from config import _get_app_dir

logger = logging.getLogger(__name__)

_HISTORY_FILE = _get_app_dir() / "run_history.json"
_MAX_HISTORY_ENTRIES = 5
_history_lock = threading.Lock()

# Current schema version for new runs
CURRENT_SCHEMA_VERSION = 2


def _migrate_track_rationale(track: dict) -> dict:
    """On-the-fly migration: convert legacy 'reason' to 'rationale' array.

    Returns a new dict — the original is not mutated.
    """
    if "rationale" in track:
        return track
    migrated = dict(track)
    reason = track.get("reason")
    if reason:
        migrated["rationale"] = [{"type": "legacy", "arg": str(reason)}]
    else:
        migrated["rationale"] = [{"type": "fallback"}]
    return migrated


def _load_history() -> list:
    """Load run history from disk, returning an empty list on error."""
    if not _HISTORY_FILE.exists():
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load run history: %s", e)
        return []


def _save_history(history: list) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_run(run_id: str, playlist_id: str, playlist_url: str, tracks: list) -> None:
    """Append a new run entry to the history file.

    tracks: list of {"artist": ..., "track": ..., "uri": ..., "rationale": [...]}
    New runs are written with schema_version 2.
    """
    with _history_lock:
        history = _load_history()
        entry = {
            "run_id": run_id,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "tracks": [
                {
                    "artist": t.get("artist", ""),
                    "track": t.get("track", ""),
                    "uri": t.get("uri", ""),
                    "rationale": t.get("rationale", [{"type": "fallback"}]),
                }
                for t in tracks
            ],
        }
        history.append(entry)
        # Keep at most _MAX_HISTORY_ENTRIES runs
        if len(history) > _MAX_HISTORY_ENTRIES:
            history = history[-_MAX_HISTORY_ENTRIES:]
        _save_history(history)


def load_runs() -> list:
    """Return run history newest-first, with on-the-fly rationale migration."""
    with _history_lock:
        raw = _load_history()
        for run in raw:
            run["tracks"] = [_migrate_track_rationale(t) for t in run.get("tracks", [])]
        return list(reversed(raw))
