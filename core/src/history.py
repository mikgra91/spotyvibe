"""Run history — saves metadata about each generation run for review.

Each entry records: run_id, timestamp, playlist_id, playlist_url, tracks added.
Stored as a JSON array in the app data directory.
"""

import json
from datetime import datetime, timezone

from config import _get_app_dir

_HISTORY_FILE = _get_app_dir() / "run_history.json"
_MAX_HISTORY_ENTRIES = 5


def _load_history() -> list:
    """Load run history from disk, returning an empty list on error."""
    if not _HISTORY_FILE.exists():
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history: list) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_run(run_id: str, playlist_id: str, playlist_url: str, tracks: list) -> None:
    """Append a new run entry to the history file.

    tracks: list of {"artist": ..., "track": ..., "uri": ...}
    """
    history = _load_history()
    entry = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "playlist_id": playlist_id,
        "playlist_url": playlist_url,
        "tracks": [
            {"artist": t.get("artist", ""), "track": t.get("track", ""), "uri": t.get("uri", "")}
            for t in tracks
        ],
    }
    history.append(entry)
    # Keep at most _MAX_HISTORY_ENTRIES runs
    if len(history) > _MAX_HISTORY_ENTRIES:
        history = history[-_MAX_HISTORY_ENTRIES:]
    _save_history(history)


def load_runs() -> list:
    """Return run history newest-first."""
    return list(reversed(_load_history()))

