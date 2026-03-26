from core.profile import load_profile, save_profile


def like_track(artist, track=None, reason=None):
    profile = load_profile()

    if track:
        entry = {"artist": artist, "track": track}
        if reason:
            entry["reason"] = reason
        profile["feedback"]["liked_tracks"].append(entry)

    if artist not in profile["artists"]["confirmed"]:
        profile["artists"]["confirmed"].append(artist)

    save_profile(profile)

    if track:
        print(f"👍 Liked: {artist} - {track}" + (f" ({reason})" if reason else ""))
    else:
        print(f"👍 Liked artist: {artist}" + (f" ({reason})" if reason else ""))


def dislike_track(artist, track=None, reason=None):
    profile = load_profile()

    reason = reason or "user feedback"

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

    save_profile(profile)

    if track:
        print(f"👎 Disliked: {artist} - {track} ({reason})")
    else:
        print(f"👎 Excluded artist: {artist} ({reason})")


