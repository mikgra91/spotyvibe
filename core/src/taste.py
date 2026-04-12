"""Taste aggregation — produces data for the taste visualisation dashboard.

Aggregates genre, energy/valence, and decade data from run history.
Pure function — no Spotify API calls at aggregation time.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def aggregate_taste(runs: list) -> dict:
    """Aggregate taste data from run history for the dashboard.

    Args:
        runs: list of run dicts from history (each has 'tracks' list).

    Returns a dict with:
        tracks_considered, runs_considered, top_genres, energy_valence, decades.
    """
    # Deduplicate tracks by (artist, title) case-insensitively
    seen = set()
    unique_tracks = []

    for run in runs:
        for track in run.get("tracks", []):
            artist = (track.get("artist") or "").lower().strip()
            title = (track.get("track") or "").lower().strip()
            key = (artist, title)
            if key not in seen:
                seen.add(key)
                unique_tracks.append(track)

    tracks_considered = len(unique_tracks)
    runs_considered = len(runs)

    # Top genres — count artist genres across deduped tracks
    genre_counts = defaultdict(int)
    for track in unique_tracks:
        for genre in track.get("genres", []):
            if genre:
                genre_counts[genre.lower().strip()] += 1

    top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    top_genres = [{"genre": g, "count": c} for g, c in top_genres]

    # Energy × valence scatter — up to 100 tracks with both features
    energy_valence = []
    for track in unique_tracks:
        energy = track.get("energy")
        valence = track.get("valence")
        if energy is not None and valence is not None:
            energy_valence.append({
                "energy": energy,
                "valence": valence,
                "artist": track.get("artist", ""),
                "title": track.get("track", ""),
            })
            if len(energy_valence) >= 100:
                break

    # Decades — bucket by release_year // 10 * 10
    decade_counts = defaultdict(int)
    for track in unique_tracks:
        year = track.get("release_year")
        if year and isinstance(year, (int, float)) and year > 1900:
            decade = (int(year) // 10) * 10
            decade_counts[f"{decade}s"] += 1

    decades = sorted(
        [{"decade": d, "count": c} for d, c in decade_counts.items()],
        key=lambda x: x["decade"],
    )

    return {
        "tracks_considered": tracks_considered,
        "runs_considered": runs_considered,
        "top_genres": top_genres,
        "energy_valence": energy_valence,
        "decades": decades,
    }

