"""Taste aggregation — produces data for the taste visualisation dashboard.

Aggregates artist frequency and available metadata from run history.
Pure function — no Spotify API calls at aggregation time.

Returns three sentiment slices: neutral, liked, disliked — each with its
own top_genres, energy_valence, decades, top_artists, and tracks_considered.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def _aggregate_slice(unique_tracks: list, profile: dict | None = None) -> dict:
    """Aggregate chart data from a list of unique track dicts.

    Returns a dict with: tracks_considered, top_genres, top_artists,
    energy_valence, decades.
    """
    tracks_considered = len(unique_tracks)

    # Top artists
    artist_counts = defaultdict(int)
    for track in unique_tracks:
        artist = (track.get("artist") or "").strip()
        if artist:
            artist_counts[artist] += 1
    top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    top_artists = [{"artist": a, "count": c} for a, c in top_artists]

    # Top genres
    genre_counts = defaultdict(int)
    for track in unique_tracks:
        for genre in track.get("genres", []):
            if genre:
                genre_counts[genre.lower().strip()] += 1

    # Supplement with profile genre data if tracks had no genres
    if not genre_counts and profile:
        prefs = profile.get("preferences", "")
        if isinstance(prefs, str):
            for section_key in ("must_have", "soft_preferences"):
                for item in (profile.get(section_key) or []):
                    if isinstance(item, str) and item.strip():
                        genre_counts[item.strip().lower()] += 1

    top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    top_genres = [{"genre": g, "count": c} for g, c in top_genres]

    # Energy × valence scatter
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

    # Decades
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
        "top_genres": top_genres,
        "top_artists": top_artists,
        "energy_valence": energy_valence,
        "decades": decades,
    }


def aggregate_taste(runs: list, profile: dict | None = None) -> dict:
    """Aggregate taste data from run history for the dashboard.

    Args:
        runs: list of run dicts from history (each has 'tracks' list).
        profile: optional loaded profile dict for genre extraction.

    Returns a dict with:
        runs_considered, tracks_considered (total),
        neutral, liked, disliked — each a _aggregate_slice dict.
    """
    # Deduplicate tracks by (artist, title) case-insensitively
    seen = set()
    buckets: dict[str, list] = {"neutral": [], "liked": [], "disliked": []}

    for run in runs:
        for track in run.get("tracks", []):
            artist = (track.get("artist") or "").lower().strip()
            title = (track.get("track") or "").lower().strip()
            key = (artist, title)
            if key not in seen:
                seen.add(key)
                sentiment = track.get("sentiment", "neutral")
                if sentiment not in buckets:
                    sentiment = "neutral"
                buckets[sentiment].append(track)

    total_tracks = sum(len(v) for v in buckets.values())

    return {
        "runs_considered": len(runs),
        "tracks_considered": total_tracks,
        "neutral": _aggregate_slice(buckets["neutral"], profile=profile),
        "liked": _aggregate_slice(buckets["liked"]),
        "disliked": _aggregate_slice(buckets["disliked"]),
    }


