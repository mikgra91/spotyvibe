import json
import re
from collections import defaultdict
from pathlib import Path
from config import BASE_DIR, BATCH_SIZE, GPT_HISTORY_LIMIT, EXHAUSTED_ARTIST_THRESHOLD, load_config, get_model
from core.profile import load_profile, save_profile
from core.utils import get_openai_client, strip_code_fences, debug_log

# Paths resolved from the package root — no os.chdir() dependency
SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system_prompt.txt"
PROMPT_FILE = BASE_DIR / "prompts" / "prompt_template.txt"



def normalize_history(profile):
    """Lowercase and deduplicate history lists so GPT never sees case-duplicates."""
    for key in ("suggested_artists", "suggested_tracks"):
        items = profile.get("history", {}).get(key, [])
        seen = set()
        deduped = []
        for item in items:
            lower = item.lower().strip()
            if lower not in seen:
                seen.add(lower)
                deduped.append(lower)
        profile["history"][key] = deduped
    return profile


def load_text_file(filepath):
    """Load a plain text file and return its content."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(
            f"{filepath} not found. Please create it."
        )
    return path.read_text(encoding="utf-8")


def _build_exclusion_block(profile):
    """Build a human-readable exclusion block grouped by artist.

    Instead of sending a flat JSON array of "artist track" strings
    (which LLMs struggle to cross-reference), we format the history
    as a structured list grouped by artist — much easier for the model
    to scan.  Artists with many exhausted tracks are flagged so the
    model avoids them entirely.
    """
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if not tracks:
        return ""

    # Truncate to the GPT history limit
    if len(tracks) > GPT_HISTORY_LIMIT:
        tracks = tracks[-GPT_HISTORY_LIMIT:]

    # Build artist→tracks from the raw entries by matching against
    # the known suggested_artists list.
    known_artists = profile.get("history", {}).get("suggested_artists", [])
    # Sort by length descending so longer artist names match first
    known_artists_sorted = sorted(set(known_artists), key=len, reverse=True)

    by_artist = defaultdict(list)
    unmatched = []

    for entry in tracks:
        matched = False
        for artist in known_artists_sorted:
            # Check if entry starts with the artist name (both lowercased)
            a_lower = artist.lower().strip()
            e_lower = entry.lower().strip()
            if e_lower.startswith(a_lower + " "):
                track_name = e_lower[len(a_lower):].strip()
                by_artist[a_lower].append(track_name)
                matched = True
                break
        if not matched:
            unmatched.append(entry)

    # Build the formatted block
    lines = []
    lines.append("=" * 60)
    lines.append("ALREADY SUGGESTED TRACKS (DO NOT REPEAT)")
    lines.append("=" * 60)
    lines.append("")
    lines.append("The following tracks have ALREADY been suggested.")
    lines.append("Do NOT suggest any of them again.")
    lines.append("If an artist is marked [EXHAUSTED], do NOT suggest ANY track by that artist.")
    lines.append("")

    exhausted_artists = []

    for artist in sorted(by_artist.keys()):
        track_list = by_artist[artist]
        is_exhausted = len(track_list) >= EXHAUSTED_ARTIST_THRESHOLD
        if is_exhausted:
            exhausted_artists.append(artist)
            lines.append(f"■ {artist} [EXHAUSTED — do NOT suggest this artist at all]:")
        else:
            lines.append(f"■ {artist}:")
        for t in track_list:
            lines.append(f"  - {t}")
        lines.append("")

    if unmatched:
        lines.append("■ Other previously suggested tracks:")
        for t in unmatched:
            lines.append(f"  - {t}")
        lines.append("")

    if exhausted_artists:
        lines.append("EXHAUSTED ARTISTS (do NOT suggest ANY track by these):")
        for a in exhausted_artists:
            lines.append(f"  ✗ {a}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def build_messages(profile, accepted_tracks=None, batch_size=None):
    """Build the system + user message pair for the OpenAI API.

    accepted_tracks: optional list of {"artist": ..., "track": ...} dicts
        already confirmed from previous attempts.  When provided, a short
        addendum is appended telling GPT how many more tracks are needed and
        which ones are already accepted (so it can skip them).
    batch_size: how many tracks to request from GPT in this call.
        Defaults to BATCH_SIZE from config.
    """
    if batch_size is None:
        batch_size = BATCH_SIZE

    system_prompt = load_text_file(SYSTEM_PROMPT_FILE)
    # Replace the placeholder count in the system prompt
    system_prompt = system_prompt.replace("{batch_size}", str(batch_size))

    user_template = load_text_file(PROMPT_FILE)

    # Build a copy of the profile WITHOUT history.suggested_tracks —
    # that data is now presented separately in the exclusion block
    # so the LLM can parse it more easily.
    profile_for_gpt = json.loads(json.dumps(profile))  # deep copy
    history = profile_for_gpt.get("history", {})
    # Remove the raw track list from the JSON — it will be in the exclusion block
    history.pop("suggested_tracks", None)
    # Keep a trimmed suggested_artists list so GPT knows which artists are old
    artists = history.get("suggested_artists", [])
    if len(artists) > GPT_HISTORY_LIMIT:
        history["suggested_artists"] = artists[-GPT_HISTORY_LIMIT:]

    # Build the exclusion block from the full profile (before trimming)
    exclusion_block = _build_exclusion_block(profile)

    user_message = user_template.format(
        profile_json=json.dumps(profile_for_gpt, indent=2),
        exclusion_block=exclusion_block,
        batch_size=batch_size,
    )

    if accepted_tracks:
        remaining = batch_size
        listing = "\n".join(
            f"- {t['artist']} - {t['track']}" for t in accepted_tracks
        )
        user_message += (
            f"\n\nI already accepted these {len(accepted_tracks)} tracks from"
            f" previous batches — do NOT suggest them again:\n{listing}\n\n"
            f"I need {remaining} MORE tracks. Still return the result in"
            " the same JSON schema but with exactly"
            f" {remaining} entries in \"playlist\"."
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def normalize_response(result):
    """Force-lowercase all artist and track names in the GPT response."""
    for entry in result.get("playlist", []):
        entry["artist"] = entry.get("artist", "").lower().strip()
        entry["track"] = entry.get("track", "").lower().strip()

    result["new_artists"] = [
        a.lower().strip() for a in result.get("new_artists", [])
    ]

    updates = result.get("profile_updates", {})
    updates["suggested_artists"] = [
        a.lower().strip() for a in updates.get("suggested_artists", [])
    ]
    updates["suggested_tracks"] = [
        t.lower().strip() for t in updates.get("suggested_tracks", [])
    ]
    result["profile_updates"] = updates
    return result


def call_gpt(messages):
    client = get_openai_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content.strip()
    debug_log("Suggestion Generation", messages, raw_content)

    content = strip_code_fences(raw_content)

    if not content:
        print("Warning: GPT returned empty response. Using empty playlist.")
        return {"playlist": [], "new_artists": [], "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}

    try:
        result = json.loads(content)
        return normalize_response(result)
    except json.JSONDecodeError:
        print("Warning: GPT response could not be parsed as JSON.")
        print("Response was:", content)
        return {"playlist": [], "new_artists": [], "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}


def update_profile(profile, result):
    existing_artists = {a.lower() for a in profile["history"]["suggested_artists"]}
    for artist in result["profile_updates"]["suggested_artists"]:
        lower = artist.lower().strip()
        if lower not in existing_artists:
            profile["history"]["suggested_artists"].append(lower)
            existing_artists.add(lower)

    existing_tracks = {t.lower() for t in profile["history"]["suggested_tracks"]}
    for track in result["profile_updates"]["suggested_tracks"]:
        lower = track.lower().strip()
        if lower not in existing_tracks:
            profile["history"]["suggested_tracks"].append(lower)
            existing_tracks.add(lower)

    return profile


# ── Code-side dedup (GPT cannot be trusted to follow history) ────────

def _normalize_key(text):
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy dedup."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s]', '', text)   # keep only letters, digits, spaces
    text = re.sub(r'\s+', ' ', text).strip()   # collapse whitespace
    return text


def filter_duplicate_suggestions(profile, result):
    """Remove tracks that already exist in history, were previously disliked,
    or appear more than once within the current batch."""

    # Build an exclusion set from history + disliked tracks
    exclude_keys = set()

    for entry in profile.get("history", {}).get("suggested_tracks", []):
        exclude_keys.add(_normalize_key(entry))

    for dt in profile.get("feedback", {}).get("disliked_tracks", []):
        artist = dt.get("artist", "")
        track = dt.get("track", "")
        if artist and track:
            exclude_keys.add(_normalize_key(f"{artist} {track}"))

    seen_in_batch = set()
    filtered = []

    for item in result.get("playlist", []):
        artist = item.get("artist", "").lower().strip()
        track = item.get("track", "").lower().strip()
        key = _normalize_key(f"{artist} {track}")

        if key in exclude_keys:
            print(f"Filtered (already suggested / disliked): {artist} - {track}")
            continue
        if key in seen_in_batch:
            print(f"Filtered (duplicate in batch): {artist} - {track}")
            continue

        seen_in_batch.add(key)
        filtered.append(item)

    # Rebuild profile_updates to match the filtered playlist
    result["playlist"] = filtered
    filtered_artists = {item["artist"].lower().strip() for item in filtered}
    result["profile_updates"]["suggested_artists"] = list(filtered_artists)
    result["profile_updates"]["suggested_tracks"] = [
        f"{item['artist'].lower().strip()} {item['track'].lower().strip()}"
        for item in filtered
    ]
    result["new_artists"] = [
        a for a in result.get("new_artists", [])
        if a.lower().strip() in filtered_artists
    ]

    return result


def main():
    load_config()
    profile = load_profile()
    normalize_history(profile)
    messages = build_messages(profile)
    result = call_gpt(messages)
    result = filter_duplicate_suggestions(profile, result)
    updated_profile = update_profile(profile, result)
    save_profile(updated_profile)

    # Print only valid JSON for createPlaylist.py
    print(json.dumps(result))


if __name__ == "__main__":
    main()