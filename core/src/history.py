"""Run history -- saves metadata about each generation run for review.

Each entry records: run_id, timestamp, playlist_id, playlist_url, tracks added.
Stored as a JSON array **per profile** in the profiles directory.

Schema versions:
  1 (implicit): tracks have optional 'reason' string
  2 (Wave 3):   tracks have 'rationale' array [{type, arg?}], no 'reason'
  3 (Wave 3):   tracks add 'energy', 'valence' (GPT estimates),
                'genres' (from GPT), 'release_year' (from album)
  4 (Wave 3):   tracks add 'sentiment' ("neutral" | "liked" | "disliked")
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import _get_app_dir, get_active_profile_id, PROFILES_DIR

logger = logging.getLogger(__name__)

# Legacy global path (kept for migration)
_LEGACY_HISTORY_FILE = _get_app_dir() / "run_history.json"
_MAX_HISTORY_ENTRIES = 5
_history_lock = threading.Lock()

# Current schema version for new runs
CURRENT_SCHEMA_VERSION = 4


def _history_file() -> Path:
    """Return the history file path for the active profile.

    Falls back to the legacy global file when no profile is active.
    """
    pid = get_active_profile_id()
    if pid:
        return PROFILES_DIR / f"{pid}_run_history.json"
    return _LEGACY_HISTORY_FILE


def _migrate_track(track: dict) -> dict:
    """On-the-fly migration for legacy track dicts.

    - Converts legacy 'reason' → 'rationale' array (schema v1 → v2).
    - Adds missing 'sentiment' field with default "neutral" (< v4).

    Returns a new dict — the original is not mutated.
    """
    migrated = dict(track)

    # rationale migration (v1 → v2)
    if "rationale" not in migrated:
        reason = migrated.get("reason")
        if reason:
            migrated["rationale"] = [{"type": "legacy", "arg": str(reason)}]
        else:
            migrated["rationale"] = [{"type": "fallback"}]

    # sentiment migration (< v4)
    migrated.setdefault("sentiment", "neutral")

    return migrated


def _load_history() -> list:
    """Load run history from disk, returning an empty list on error."""
    path = _history_file()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load run history: %s", e)
        return []


def _save_history(history: list) -> None:
    path = _history_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_run(run_id: str, playlist_id: str, playlist_url: str, tracks: list) -> None:
    """Append a new run entry to the active profile's history file.

    tracks: list of {"artist": ..., "track": ..., "uri": ..., "rationale": [...],
                      "energy": float?, "valence": float?, "genres": list?,
                      "release_year": int?}
    New runs are written with schema_version 4.  All tracks start as "neutral".
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
                    "energy": t.get("energy"),
                    "valence": t.get("valence"),
                    "genres": t.get("genres", []),
                    "release_year": t.get("release_year"),
                    "sentiment": "neutral",
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
    """Return run history newest-first, with on-the-fly migration."""
    with _history_lock:
        raw = _load_history()
        for run in raw:
            run["tracks"] = [_migrate_track(t) for t in run.get("tracks", [])]
        return list(reversed(raw))


def update_track_sentiment(artist: str, track: str, sentiment: str) -> bool:
    """Update the sentiment of a track across all runs in history.

    Args:
        artist: artist name (case-insensitive match).
        track: track title (case-insensitive match).
        sentiment: one of "liked", "disliked", "neutral".

    Returns True if at least one track was updated.
    """
    if sentiment not in ("liked", "disliked", "neutral"):
        return False

    artist_lower = (artist or "").lower().strip()
    track_lower = (track or "").lower().strip()
    if not artist_lower or not track_lower:
        return False

    with _history_lock:
        history = _load_history()
        updated = False
        for run in history:
            for t in run.get("tracks", []):
                if (t.get("artist", "").lower().strip() == artist_lower
                        and t.get("track", "").lower().strip() == track_lower):
                    t["sentiment"] = sentiment
                    updated = True
        if updated:
            _save_history(history)
        return updated

