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

# F4 (2026-05-01): once the user has track-disliked this many distinct
# tracks by the same artist, the next dislike auto-promotes the artist
# to ``artists.rejected``. The threshold is conservative — three distinct
# track-dislikes is a clear signal the user does not want this artist
# at all. Suggestion-pipeline code reads ``artists.rejected`` as a hard
# exclusion, so the next playlist run will not surface that artist again.
DISLIKE_AUTO_REJECT_THRESHOLD = 3


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
            # Track-level dislike — only record the track, don't reject the whole artist.
            # Compare case-insensitively to avoid duplicate entries from
            # rapid double-clicks or case-variant artist names. Mirrors the
            # artist-level dedup pattern below.
            artist_norm = artist.lower().strip()
            track_norm = track.lower().strip()
            existing = {
                ((e.get("artist") or "").lower().strip(),
                 (e.get("track") or "").lower().strip())
                for e in profile["feedback"]["disliked_tracks"]
                if isinstance(e, dict)
            }
            if (artist_norm, track_norm) not in existing:
                profile["feedback"]["disliked_tracks"].append({
                    "artist": artist,
                    "track": track,
                    "reason": reason
                })

            # F4 (2026-05-01): auto-escalate to artist-rejection once the
            # user has track-disliked DISLIKE_AUTO_REJECT_THRESHOLD
            # distinct tracks by this artist. Without this, the user has
            # to manually click "exclude artist" — and as observed in
            # production (49 disliked_tracks, only 5 manually rejected
            # artists, 9 disliked DREAMS COME TRUE / 4 Dreamcatcher
            # tracks) that step rarely happens, so the artist keeps
            # being re-suggested. See `context/claudeAnalyse.md` F4.
            distinct_tracks_for_artist = {
                (e.get("track") or "").lower().strip()
                for e in profile["feedback"]["disliked_tracks"]
                if isinstance(e, dict)
                and (e.get("artist") or "").lower().strip() == artist_norm
                and (e.get("track") or "").strip()
            }
            if len(distinct_tracks_for_artist) >= DISLIKE_AUTO_REJECT_THRESHOLD:
                rejected = profile["artists"]["rejected"]
                rejected_norm = {
                    ((r["name"] if isinstance(r, dict) else r) or "")
                    .lower().strip()
                    for r in rejected
                }
                if artist_norm not in rejected_norm:
                    # Concatenate up to 3 distinct dislike reasons for
                    # context — train_profile (F5) consumes this when
                    # promoting recurring reasons into avoid prose.
                    reasons_seen: list[str] = []
                    for e in profile["feedback"]["disliked_tracks"]:
                        if not isinstance(e, dict):
                            continue
                        if (e.get("artist") or "").lower().strip() != artist_norm:
                            continue
                        r = (e.get("reason") or "").strip()
                        if r and r not in reasons_seen:
                            reasons_seen.append(r)
                        if len(reasons_seen) >= 3:
                            break
                    auto_reason = (
                        f"auto-rejected after "
                        f"{len(distinct_tracks_for_artist)} disliked tracks"
                    )
                    if reasons_seen:
                        auto_reason += " — " + "; ".join(reasons_seen)
                    rejected.append({
                        "name": artist,
                        "reason": auto_reason,
                        "auto": True,
                    })
                    logger.info(
                        "[AUTO-EXCLUDED] %s after %d disliked tracks (%s)",
                        artist, len(distinct_tracks_for_artist), auto_reason,
                    )
        else:
            # Artist-level dislike — reject the entire artist.
            # Compare case-insensitively to avoid duplicate entries that
            # differ only in casing (e.g. "Boards of Canada" vs
            # "boards of canada"). Bug fix 2026-04-28.
            artist_norm = artist.lower().strip()
            existing_norm = {
                ((r["name"] if isinstance(r, dict) else r) or "").lower().strip()
                for r in profile["artists"]["rejected"]
            }
            if artist_norm not in existing_norm:
                profile["artists"]["rejected"].append({
                    "name": artist,
                    "reason": reason
                })

        save_fn(profile)

    if track:
        logger.info("[DISLIKED] %s - %s (%s)", artist, track, reason)
    else:
        logger.info("[EXCLUDED] Artist: %s (%s)", artist, reason)


