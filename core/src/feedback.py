"""User feedback recording (like / dislike) for tracks and artists.

Technologies & patterns used:
- **Append-only feedback log**: Likes and dislikes are appended to lists
  in the JSON profile, never deleted. This creates a growing training
  signal that improves GPT suggestions over time — both the prompt
  (which includes feedback history) and the code-side dedup filter
  (which excludes disliked tracks) benefit from this data.
- **Two-tier rejection model**:
  - Track-level dislike: Records the specific track but does NOT reject
    the artist. The user may still enjoy other tracks by the same artist.
  - Artist-level dislike: Adds the artist to `artists.rejected`, which
    is a hard exclusion — GPT is told to never suggest any track by
    that artist again.
  This granularity prevents over-filtering while respecting strong
  preferences.
- **Separation from suggestions.py**: Feedback is recorded in its own
  module to keep the suggestion engine stateless — it only reads the
  profile, never writes feedback. This follows the Single Responsibility
  Principle.
"""

import logging

from .profile import profile_transaction
from .utils import sanitize_text

logger = logging.getLogger(__name__)


def like_track(artist, track=None, reason=None):
    """Record a positive signal for a track or artist.

    If `track` is provided, the specific track is added to liked_tracks.
    The artist is always added to `artists.confirmed` (if not already
    present), strengthening it as a reference for future suggestions.

    The optional `reason` field captures WHY the user liked the track,
    which enriches the context GPT receives in future prompts.
    """
    artist = sanitize_text(artist or "")
    track = sanitize_text(track) if track else None
    reason = sanitize_text(reason) if reason else None

    with profile_transaction() as (load_fn, save_fn):
        profile = load_fn()

        if track:
            entry = {"artist": artist, "track": track}
            if reason:
                entry["reason"] = reason
            profile["feedback"]["liked_tracks"].append(entry)

        if artist not in profile["artists"]["confirmed"]:
            profile["artists"]["confirmed"].append(artist)

        save_fn(profile)

    if track:
        logger.info("[LIKED] %s - %s%s", artist, track, f" ({reason})" if reason else "")
    else:
        logger.info("[LIKED] Artist: %s%s", artist, f" ({reason})" if reason else "")


def dislike_track(artist, track=None, reason=None):
    """Record a negative signal for a track or artist.

    Behaviour depends on whether `track` is provided:
    - With track:    Track-level dislike — only that track is recorded in
                     disliked_tracks. The artist is NOT rejected, so other
                     tracks by the same artist can still be suggested.
    - Without track: Artist-level dislike — the artist is added to
                     `artists.rejected` with a reason. GPT is instructed
                     to never suggest this artist again.

    The `reason` defaults to "user feedback" to ensure every dislike has
    an explanation — this context helps GPT understand the rejection
    pattern (e.g. "too slow", "wrong genre") and avoid similar tracks.
    """
    artist = sanitize_text(artist or "")
    track = sanitize_text(track) if track else None
    reason = sanitize_text(reason or "user feedback")

    with profile_transaction() as (load_fn, save_fn):
        profile = load_fn()

        if track:
            # Track-level dislike — only record the track, don't reject the whole artist
            profile["feedback"]["disliked_tracks"].append({
                "artist": artist,
                "track": track,
                "reason": reason
            })
        else:
            # Artist-level dislike — reject the entire artist
            rejected_names = [r["name"] if isinstance(r, dict) else r for r in profile["artists"]["rejected"]]
            if artist not in rejected_names:
                profile["artists"]["rejected"].append({
                    "name": artist,
                    "reason": reason
                })

        save_fn(profile)

    if track:
        logger.info("[DISLIKED] %s - %s (%s)", artist, track, reason)
    else:
        logger.info("[EXCLUDED] Artist: %s (%s)", artist, reason)


