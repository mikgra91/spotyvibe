"""Run history — saves metadata about each generation run for undo/review.

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


def undo_last_run(sp) -> dict:
    """Remove tracks added by the most recent run from the Spotify playlist.

    Returns {"undone": True, "removed": N, "run_id": "..."} or raises ValueError.
    """
    history = _load_history()
    if not history:
        raise ValueError("No run history to undo.")

    last = history[-1]
    playlist_id = last.get("playlist_id")
    uris = [t["uri"] for t in last.get("tracks", []) if t.get("uri")]

    if not playlist_id:
        raise ValueError("Last run has no playlist ID — cannot undo.")
    if not uris:
        raise ValueError("Last run has no track URIs recorded — cannot undo.")

    sp.playlist_remove_all_occurrences_of_items(playlist_id, uris)

    # Remove the last entry
    history = history[:-1]
    _save_history(history)

    return {"undone": True, "removed": len(uris), "run_id": last.get("run_id")}
