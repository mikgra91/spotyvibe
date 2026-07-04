"""AI-generated-artist blocklist — filters AI artists out of suggestions.

The blocklist is a curated set of Spotify **artist IDs** sourced from the
community project `CennoxX/spotify-ai-blocker` (MIT). We use the IDs only as a
deny set: any verified track whose primary ``artist_id`` is in the set is
dropped before it counts toward the playlist. Matching on the Spotify ID
(rather than the artist name) is collision-free — no false positives from AI
acts that mimic a legitimate artist's name.

The set is populated once at startup from a local ``ai_artists.json`` (kept
current via the same manifest/download plumbing as the RAG corpus). When the
file is absent the set stays empty and every filter call is a transparent
no-op, so the feature degrades gracefully when the blocklist hasn't been
downloaded yet.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Process-wide deny set of Spotify artist IDs. Empty until load_ai_blocklist()
# succeeds; an empty set makes filter_ai_tracks() a no-op.
_AI_ARTIST_IDS: set[str] = set()


def load_ai_blocklist(path) -> int:
    """Load the AI-artist deny set from a local JSON file. Best-effort.

    Accepts either a bare JSON array of artist IDs or an object with an
    ``artist_ids`` list (the form published by the distribution pipeline).
    Never raises — a missing/corrupt file just leaves the set empty and the
    filter inert.

    Returns the number of IDs loaded.
    """
    global _AI_ARTIST_IDS
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("AI blocklist not loaded (%s): %s", p, exc)
        _AI_ARTIST_IDS = set()
        return 0
    ids = data.get("artist_ids", []) if isinstance(data, dict) else data
    _AI_ARTIST_IDS = {str(i) for i in ids if i}
    logger.info("AI blocklist loaded: %d artist IDs", len(_AI_ARTIST_IDS))
    return len(_AI_ARTIST_IDS)


def is_ai_artist(artist_id) -> bool:
    """Return True if *artist_id* is in the AI-artist deny set."""
    return bool(artist_id) and artist_id in _AI_ARTIST_IDS


def filter_ai_tracks(tracks):
    """Partition *tracks* into (kept, dropped) on their ``artist_id``.

    Mirrors the return shape of ``filter_emerging_artists`` so the pipeline
    integration is symmetric. When the deny set is empty, every track is kept.
    """
    if not _AI_ARTIST_IDS:
        return list(tracks), []
    kept, dropped = [], []
    for track in tracks:
        (dropped if is_ai_artist(track.get("artist_id")) else kept).append(track)
    return kept, dropped


def ai_blocklist_available() -> bool:
    """Return True if the deny set has been populated."""
    return bool(_AI_ARTIST_IDS)


def ai_blocklist_size() -> int:
    """Return the number of artist IDs currently in the deny set."""
    return len(_AI_ARTIST_IDS)
