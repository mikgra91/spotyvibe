"""GPT-powered music suggestion engine with deduplication and retry logic.

Technologies & patterns used:
- **OpenAI Chat Completions API**: Uses the messages-based API with system
  + user roles. The system prompt defines the AI's persona and rules;
  the user prompt provides per-request context (profile, exclusion list).
- **Structured Outputs** (`response_format={"type": "json_object"}`):
  Forces GPT to return valid JSON, eliminating brittle regex-based parsing.
- **Prompt template files**: System and user prompts live in `prompts/`
  as plain text with `{placeholder}` variables. This separates prompt
  engineering from code — prompts can be iterated without deployments.
- **Exclusion block pattern**: History is formatted as a human-readable
  grouped list rather than raw JSON. LLMs parse structured text better
  than deeply nested JSON when doing set-membership checks.
- **Code-side deduplication**: GPT cannot be relied on to perfectly avoid
  repeats. A deterministic Python filter (`filter_duplicate_suggestions`)
  catches any duplicates the model misses — defence in depth.
- **Adaptive retry with escalating warnings**: When GPT returns all-
  duplicate batches, the retry prompt gets progressively more explicit,
  telling the model exactly which tracks it repeated. This is a prompt-
  engineering technique called "iterative correction".
- **collections.defaultdict**: Used to group tracks by artist efficiently
  for the exclusion block, avoiding manual key-existence checks.
- **re (regex)**: Used for fuzzy key normalisation in dedup — strips
  punctuation and collapses whitespace so "Don't Stop" and "dont stop"
  are recognised as the same track.
- **math.ceil**: Calculates the minimum number of new-artist slots from
  a percentage, ensuring at least one new artist even at low percentages.
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from config import BASE_DIR, BATCH_SIZE, GPT_HISTORY_LIMIT, EXHAUSTED_ARTIST_THRESHOLD, get_model
from core.utils import get_openai_client, strip_code_fences, debug_log

# Paths resolved from the package root using pathlib — immune to os.chdir()
SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system_prompt.txt"
PROMPT_FILE = BASE_DIR / "prompts" / "prompt_template.txt"



def normalize_history(profile):
    """Lowercase and deduplicate history lists so GPT never sees case-duplicates.

    Why lowercase everything? GPT is case-insensitive when reasoning about
    artist/track names, but exact-string deduplication is case-sensitive.
    Normalising to lowercase at the boundary (when history is loaded)
    prevents "Radiohead" and "radiohead" from being treated as different
    entries in both the exclusion list and the Python-side filter.
    """
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
    to scan.

    Design rationale: Early versions sent the raw JSON array of track
    strings directly in the prompt. GPT frequently failed to match
    entries against its own suggestions because it had to mentally
    parse compound "artist track" strings. The grouped format with
    clear headers and per-artist bullet points dramatically reduced
    repeat rates.

    The EXHAUSTED_ARTIST_THRESHOLD marks artists with many prior
    tracks as [EXHAUSTED], telling GPT to skip them entirely. This
    pushes the model toward fresh artist discovery instead of
    suggesting the 5th track by the same artist.
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


def build_messages(profile, accepted_tracks=None, batch_size=None,
                   recently_filtered_tracks=None, consecutive_empty=0,
                   new_artist_percentage=30):
    """Build the system + user message pair for the OpenAI API.

    This is the core prompt-assembly function. It combines:
    1. A system prompt (from file) that defines GPT's role and rules.
    2. A user prompt (from template) that injects the profile JSON,
       exclusion block, and batch-size requirement.
    3. Optional addenda for multi-batch workflows and retry warnings.

    **Multi-batch continuation**: When generating playlists larger than
    one batch, `accepted_tracks` carries forward the tracks already
    confirmed, and the prompt instructs GPT to fill the remaining slots.

    **Retry escalation** (`recently_filtered_tracks`, `consecutive_empty`):
    When the code-side dedup filter removes ALL tracks in a batch, the
    next request includes a strongly-worded warning with the specific
    tracks that failed. This uses prompt-engineering escalation — each
    retry attempt increases the severity of the language to overcome
    GPT's tendency to repeat recent outputs.

    **New artist percentage**: Ensures diversity by requiring a minimum
    percentage of suggestions from previously-unseen artists. The value
    is injected into the system prompt via placeholder replacement.

    Parameters:
        accepted_tracks: list of {"artist", "track"} already confirmed.
        batch_size: tracks to request (default: BATCH_SIZE from config).
        recently_filtered_tracks: tracks that were all-filtered last batch.
        consecutive_empty: count of consecutive all-filtered batches.
        new_artist_percentage: min % of suggestions from new artists (1–100).
    """
    if batch_size is None:
        batch_size = BATCH_SIZE

    min_new_artists = math.ceil(batch_size * new_artist_percentage / 100)

    system_prompt = load_text_file(SYSTEM_PROMPT_FILE)
    # Replace all per-run placeholders in the system prompt
    system_prompt = system_prompt.replace("{batch_size}", str(batch_size))
    system_prompt = system_prompt.replace("{new_artist_percentage}", str(new_artist_percentage))
    system_prompt = system_prompt.replace("{min_new_artists}", str(min_new_artists))

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

    if recently_filtered_tracks:
        # Cap at 30 entries so the prompt stays manageable
        capped = recently_filtered_tracks[:30]
        filtered_listing = "\n".join(
            f"  - {t['artist']} - {t['track']}" for t in capped
        )
        attempt_label = f"attempt {consecutive_empty + 1}" if consecutive_empty > 0 else "attempt 1"
        user_message += (
            f"\n\n{'=' * 60}\n"
            f"⚠️  RETRY WARNING ({attempt_label}) — YOUR PREVIOUS BATCH WAS ENTIRELY FILTERED\n"
            f"{'=' * 60}\n"
            f"Every single track you suggested in the last batch was already\n"
            f"present in the exclusion list above. You are NOT following the\n"
            f"\"ALREADY SUGGESTED TRACKS\" section. This is the {attempt_label}.\n\n"
            f"The {len(capped)} specific tracks from your last batch that were\n"
            f"ALL rejected (already in history — do NOT suggest these again):\n"
            f"{filtered_listing}\n\n"
            f"STRICT REQUIREMENT: You MUST suggest {batch_size} tracks that\n"
            f"appear neither in the exclusion list NOR in the list above.\n"
            f"Explore different artists, sub-genres, or time periods you have\n"
            f"not yet touched.\n"
            f"{'=' * 60}\n"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def normalize_response(result):
    """Force-lowercase all artist and track names in the GPT response.
    Also strips the 'validation' key which is only for GPT's self-check."""
    # 'validation' is an internal self-check block — discard it so it never
    # pollutes profile_updates or the UI.
    result.pop("validation", None)

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
    """Send the assembled messages to the OpenAI Chat Completions API.

    Uses `response_format={"type": "json_object"}` (Structured Outputs)
    to guarantee parseable JSON. Temperature 0.7 balances creativity
    (important for music discovery) with coherence.

    Gracefully handles empty or unparseable responses by returning
    a valid empty-playlist structure rather than crashing — the caller
    can then retry or report "no results" to the user.
    """
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
    """Append newly suggested artists and tracks to the profile history.

    Uses set-based deduplication (lowercased) to prevent history bloat.
    The history is append-only — entries are never removed here, only
    added. This ensures the exclusion list grows monotonically, which
    is essential for the dedup strategy to work correctly.
    """
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
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy dedup.

    Why fuzzy? GPT may return "Don't Stop Me Now" while history has
    "dont stop me now". Stripping punctuation and normalising whitespace
    catches these near-duplicates that exact string comparison would miss.
    Uses regex character classes for fast, single-pass cleaning.
    """
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s]', '', text)   # keep only letters, digits, spaces
    text = re.sub(r'\s+', ' ', text).strip()   # collapse whitespace
    return text


def filter_duplicate_suggestions(profile, result):
    """Remove tracks that already exist in history, were previously disliked,
    or appear more than once within the current batch.

    This is the **code-side safety net** for deduplication. Even with
    detailed exclusion lists in the prompt, GPT will occasionally repeat
    tracks. This function provides deterministic, 100% reliable filtering
    as a second layer of defence.

    The function also builds an internal `_filtered_out` list that is
    used by the retry logic in `build_messages()` to tell GPT exactly
    which tracks it repeated, enabling targeted correction on the next
    attempt.

    Three exclusion sources:
    1. `history.suggested_tracks` — everything previously suggested.
    2. `feedback.disliked_tracks` — tracks the user explicitly rejected.
    3. Within-batch duplicates — GPT sometimes repeats within one response.
    """

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
    filtered_out = []  # tracks removed because they are already known / disliked

    for item in result.get("playlist", []):
        artist = item.get("artist", "").lower().strip()
        track = item.get("track", "").lower().strip()
        key = _normalize_key(f"{artist} {track}")

        if key in exclude_keys:
            print(f"Filtered (already suggested / disliked): {artist} - {track}")
            filtered_out.append(item)
            continue
        if key in seen_in_batch:
            print(f"Filtered (duplicate in batch): {artist} - {track}")
            filtered_out.append(item)
            continue

        seen_in_batch.add(key)
        filtered.append(item)

    # Rebuild profile_updates to match the filtered playlist
    result["playlist"] = filtered
    # Expose the tracks that were removed so callers can feed them back to GPT
    # as an explicit retry warning (internal key, stripped before returning to UI).
    result["_filtered_out"] = filtered_out
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