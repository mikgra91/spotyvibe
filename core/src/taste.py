"""Taste aggregation — produces data for the taste visualisation dashboard.

Aggregates artist frequency and available metadata from two sources,
keyed by ``(artist, title)`` case-insensitively:

1. **Run history** (`load_runs()`) — saved playlist runs, which carry rich
   per-track metadata (genres, energy, valence, release_year).
2. **The profile feedback store** (`profile["feedback"]`) — likes/dislikes
   the user gave on suggestions/previews. This is **authoritative for
   sentiment** and is what lets the dashboard reflect feedback even when no
   playlist was ever applied (the previous behaviour silently ignored it,
   showing "0 tracks from 0 runs").

Returns three sentiment slices: neutral, liked, disliked — each with its
own top_genres, energy_valence, decades, top_artists, and tracks_considered.
Pure function — no Spotify API calls at aggregation time.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def _key(artist, title):
    return ((artist or "").lower().strip(), (title or "").lower().strip())


def _aggregate_slice(unique_tracks: list) -> dict:
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

    # Top genres — ONLY real per-track genres (GPT-estimated, stored on run
    # tracks). Deliberately NO profile-preference fallback: must_have /
    # soft_preferences are free-text vibe descriptors (e.g. "rich vocal
    # harmonies", "momentous song progression"), not genres, and surfacing
    # them here mislabels the chart. An empty genre chart is correct when no
    # real genre data is available.
    genre_counts = defaultdict(int)
    for track in unique_tracks:
        for genre in track.get("genres", []):
            if genre:
                genre_counts[genre.lower().strip()] += 1
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
    """Aggregate taste data from run history + the profile feedback store.

    Args:
        runs: list of run dicts from history (each has a 'tracks' list).
        profile: optional loaded profile dict. Its ``feedback.liked_tracks``
            / ``feedback.disliked_tracks`` are merged in and are
            **authoritative for sentiment** — so feedback given on
            suggestions/previews appears even with no saved runs.

    Returns a dict with:
        runs_considered, tracks_considered (total),
        neutral, liked, disliked — each a _aggregate_slice dict.
    """
    # 1. Run history: keep the first (richest-metadata) occurrence per track
    #    and its run-stamped sentiment.
    run_meta: dict[tuple, dict] = {}
    run_sentiment: dict[tuple, str] = {}
    for run in runs:
        for track in run.get("tracks", []):
            key = _key(track.get("artist"), track.get("track"))
            if key == ("", "") or key in run_meta:
                continue
            run_meta[key] = track
            s = track.get("sentiment", "neutral")
            run_sentiment[key] = s if s in ("neutral", "liked", "disliked") else "neutral"

    # 2. Profile feedback store — authoritative sentiment; supplies tracks
    #    that never made it into a saved run.
    fb_sentiment: dict[tuple, str] = {}
    fb_only_meta: dict[tuple, dict] = {}
    if profile:
        fb = profile.get("feedback") or {}
        for label, list_key in (("liked", "liked_tracks"),
                                ("disliked", "disliked_tracks")):
            for entry in (fb.get(list_key) or []):
                if not isinstance(entry, dict):
                    continue
                artist, title = entry.get("artist"), entry.get("track")
                if not (artist and title):
                    continue
                key = _key(artist, title)
                fb_sentiment[key] = label  # a later list wins; disliked after liked
                fb_only_meta.setdefault(key, {"artist": artist.strip(),
                                              "track": title.strip()})

    # 3. Union both sources. Sentiment: feedback (authoritative) > run > neutral.
    #    Metadata: run history (richer) where available, else the feedback stub.
    buckets: dict[str, list] = {"neutral": [], "liked": [], "disliked": []}
    for key in set(run_meta) | set(fb_only_meta):
        sentiment = fb_sentiment.get(key) or run_sentiment.get(key, "neutral")
        buckets[sentiment].append(run_meta.get(key) or fb_only_meta[key])

    total_tracks = sum(len(v) for v in buckets.values())

    return {
        "runs_considered": len(runs),
        "tracks_considered": total_tracks,
        "neutral": _aggregate_slice(buckets["neutral"]),
        "liked": _aggregate_slice(buckets["liked"]),
        "disliked": _aggregate_slice(buckets["disliked"]),
    }
