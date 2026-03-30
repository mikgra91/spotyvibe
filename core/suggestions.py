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
import unicodedata
from collections import defaultdict
from pathlib import Path
from config import BASE_DIR, BATCH_SIZE, GPT_HISTORY_LIMIT, EXHAUSTED_ARTIST_THRESHOLD, get_model, get_gpt_language
from core.utils import get_openai_client, strip_code_fences, debug_log

# Paths resolved from the package root using pathlib — immune to os.chdir()
SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system_prompt.txt"
PROMPT_FILE = BASE_DIR / "prompts" / "prompt_template.txt"



def build_feedback_summary(profile, max_chars=2000):
    """Build a short 'recent feedback' block from liked/disliked tracks.

    Picks the last N entries from each list and formats them as a concise
    human-readable block that GPT can use to bias the next run.

    Capped at max_chars to prevent prompt bloat.
    """
    liked = profile.get("feedback", {}).get("liked_tracks", [])
    disliked = profile.get("feedback", {}).get("disliked_tracks", [])

    if not liked and not disliked:
        return ""

    lines = ["Recent user feedback (use to fine-tune your suggestions):"]

    recent_liked = liked[-10:]
    for entry in recent_liked:
        artist = entry.get("artist", "")
        track = entry.get("track", "")
        reason = entry.get("reason", "")
        line = f"  + Liked: {artist} - {track}"
        if reason:
            line += f" (reason: {reason})"
        lines.append(line)

    recent_disliked = disliked[-10:]
    for entry in recent_disliked:
        artist = entry.get("artist", "")
        track = entry.get("track", "")
        reason = entry.get("reason", "")
        line = f"  - Disliked: {artist} - {track}"
        if reason:
            line += f" (reason: {reason})"
        lines.append(line)

    summary = "\n".join(lines)
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "\n  [... truncated]"
    return summary


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


def _build_deny_set_json(profile, ephemeral_deny_tracks=None):
    """Build a consolidated JSON deny set for the prompt.

    Merges all exclusion sources into a single structured block:
    - artists.rejected + feedback.disliked_artists → forbidden_artists
    - exhausted artists (computed from history) → exhausted_artists
    - history.suggested_tracks grouped by artist → forbidden_tracks
    - feedback.disliked_tracks → disliked_tracks
    - ephemeral_deny_tracks (retry-filtered, NOT persisted) → retry_forbidden_tracks

    GPT-4.1-mini in json_object mode processes JSON lookups more accurately
    than prose exclusion lists. DENY_LIST is the single source of truth —
    exclusion fields are stripped from the profile JSON before sending.
    """
    # Forbidden artists (merged from all sources)
    forbidden_artists = set()
    for entry in profile.get("artists", {}).get("rejected", []):
        name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
        if name:
            forbidden_artists.add(name.lower().strip())
    for name in profile.get("feedback", {}).get("disliked_artists", []):
        if name:
            forbidden_artists.add(str(name).lower().strip())

    # Exhausted artists via longest-match parsing
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if len(tracks) > GPT_HISTORY_LIMIT:
        tracks = tracks[-GPT_HISTORY_LIMIT:]

    known_artists = sorted(
        set(profile.get("history", {}).get("suggested_artists", [])),
        key=len, reverse=True
    )

    artist_counts = defaultdict(int)
    by_artist = defaultdict(list)

    for entry in tracks:
        e_lower = entry.lower().strip()
        matched = False
        for artist in known_artists:
            a_lower = artist.lower().strip()
            if e_lower.startswith(a_lower + " "):
                track_name = e_lower[len(a_lower):].strip()
                by_artist[a_lower].append(track_name)
                artist_counts[a_lower] += 1
                matched = True
                break
        if not matched:
            by_artist["_unmatched"].append(entry)

    exhausted = [a for a, c in artist_counts.items() if c >= EXHAUSTED_ARTIST_THRESHOLD]

    # Disliked tracks
    disliked_tracks = {}
    for dt in profile.get("feedback", {}).get("disliked_tracks", []):
        artist = dt.get("artist", "").lower().strip()
        track = dt.get("track", "").lower().strip()
        if artist and track:
            disliked_tracks.setdefault(artist, []).append(track)

    deny_set = {
        "forbidden_artists": sorted(forbidden_artists),
        "exhausted_artists": sorted(exhausted),
        "forbidden_tracks": {
            a: sorted(t) for a, t in sorted(by_artist.items()) if a != "_unmatched"
        },
        "disliked_tracks": {a: sorted(t) for a, t in sorted(disliked_tracks.items())},
    }

    if "_unmatched" in by_artist:
        deny_set["other_forbidden_tracks"] = sorted(by_artist["_unmatched"])

    if ephemeral_deny_tracks:
        deny_set["retry_forbidden_tracks"] = sorted(ephemeral_deny_tracks)

    return json.dumps(deny_set, indent=2)


def build_messages(profile, accepted_tracks=None, batch_size=None,
                   recently_filtered_tracks=None,
                   new_artist_percentage=30, batch_num=0):
    """Build the system + user message pair for the OpenAI API.

    Key design decisions:
    - Over-requests by +3 (effective_batch_size) to absorb expected filtering.
    - On retries, filtered tracks go into an ephemeral deny set — never
      mentioned in prose (mentioning them primes GPT to repeat them).
    - DENY_LIST JSON comes before profile in the user message (positional bias).
    - Exclusion fields stripped from profile_for_gpt (DENY_LIST is sole source).
    - Diversity hints added when history is large (>50 tracks).
    """
    if batch_size is None:
        batch_size = BATCH_SIZE

    # Over-request by +3 to absorb filtering; caller truncates after filter
    effective_batch_size = batch_size + 3
    min_new_artists = math.ceil(effective_batch_size * new_artist_percentage / 100)

    gpt_language = get_gpt_language()

    system_prompt = load_text_file(SYSTEM_PROMPT_FILE)
    system_prompt = system_prompt.replace("{batch_size}", str(effective_batch_size))
    system_prompt = system_prompt.replace("{new_artist_percentage}", str(new_artist_percentage))
    system_prompt = system_prompt.replace("{min_new_artists}", str(min_new_artists))
    system_prompt = system_prompt.replace("{gpt_language}", gpt_language)

    user_template = load_text_file(PROMPT_FILE)

    # Build ephemeral deny set from retry-filtered tracks (NOT persisted to profile)
    ephemeral_deny_tracks = set()
    if recently_filtered_tracks:
        for t in recently_filtered_tracks:
            key = _normalize_key(f"{t['artist']} {t['track']}")
            ephemeral_deny_tracks.add(key)

    # Build consolidated JSON deny set (merges all exclusion sources)
    deny_set_json = _build_deny_set_json(profile, ephemeral_deny_tracks or None)

    # Profile copy with exclusion fields stripped — DENY_LIST is the sole source
    profile_for_gpt = json.loads(json.dumps(profile))
    history = profile_for_gpt.get("history", {})
    history.pop("suggested_tracks", None)
    artists_hist = history.get("suggested_artists", [])
    if len(artists_hist) > GPT_HISTORY_LIMIT:
        history["suggested_artists"] = artists_hist[-GPT_HISTORY_LIMIT:]
    profile_for_gpt.get("artists", {}).pop("rejected", None)
    profile_for_gpt.get("feedback", {}).pop("disliked_artists", None)

    feedback_summary = build_feedback_summary(profile)

    user_message = user_template.format(
        profile_json=json.dumps(profile_for_gpt, indent=2),
        deny_set_json=deny_set_json,
        batch_size=effective_batch_size,
        recent_feedback=feedback_summary,
    )

    if accepted_tracks:
        listing = "\n".join(
            f"- {t['artist']} - {t['track']}" for t in accepted_tracks
        )
        user_message += (
            f"\n\nI already accepted these {len(accepted_tracks)} tracks from"
            f" previous batches — do NOT suggest them again:\n{listing}\n\n"
            f"I need {effective_batch_size} MORE tracks. Still return the result in"
            " the same JSON schema but with exactly"
            f" {effective_batch_size} entries in \"playlist\"."
        )

    # Diversity hints when history is large — give GPT a concrete direction
    if len(profile.get("history", {}).get("suggested_tracks", [])) > 50:
        diversity_hints = [
            "Focus on artists from the 1970s-1980s that match the profile.",
            "Explore Japanese, Korean, or Scandinavian artists matching the profile.",
            "Look for artists who released their first album after 2020.",
            "Consider solo projects or side projects of artists similar to the confirmed list.",
            "Explore soundtrack and compilation albums for hidden gems.",
        ]
        hint = diversity_hints[batch_num % len(diversity_hints)]
        user_message += f"\n\nDiversity guidance: {hint}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def normalize_response(result):
    """Force-lowercase all artist and track names in the GPT response.

    Strips model-generated metadata fields — new_artists and profile_updates
    are computed code-side in filter_duplicate_suggestions() after truncation,
    so model output for these would be inaccurate anyway.
    """
    result.pop("validation", None)

    for entry in result.get("playlist", []):
        entry["artist"] = entry.get("artist", "").lower().strip()
        entry["track"] = entry.get("track", "").lower().strip()

    # These are derived in code — initialize empty so downstream never fails
    result["new_artists"] = []
    result["profile_updates"] = {"suggested_artists": [], "suggested_tracks": []}
    return result


def call_gpt(messages, temperature=0.7):
    """Send the assembled messages to the OpenAI Chat Completions API.

    Temperature is configurable — callers pass a lower value on retries
    to push toward more deterministic (less repetitive) output.
    """
    client = get_openai_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    raw_content = (response.choices[0].message.content or "").strip()
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

    NFKD normalization handles curly quotes, accented characters, and
    ligatures (e.g. "Beyoncé" vs "Beyonce", "The Mowgli's" vs "The Mowgli´s").
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s]', '', s)   # keep only letters, digits, spaces
    s = re.sub(r'\s+', ' ', s).strip()   # collapse whitespace
    return s


def filter_duplicate_suggestions(profile, result):
    """Remove tracks that already exist in history, were previously disliked,
    are from rejected/disliked/exhausted artists, exceed the 2-per-artist
    cap, or appear more than once within the current batch.

    Exclusion sources (in priority order):
    1. `artists.rejected` + `feedback.disliked_artists` — artist-level bans.
    2. Exhausted artists (>= EXHAUSTED_ARTIST_THRESHOLD tracks in history).
    3. `history.suggested_tracks` + `feedback.disliked_tracks` — track-level bans.
    4. Within-batch duplicates.
    5. Max 2 tracks per artist per batch.

    Also computes `profile_updates` and `new_artists` code-side so callers
    never rely on model-generated metadata (which would be wrong after truncation).
    """

    # Build track-level exclusion set from history + disliked tracks
    exclude_keys = set()
    for entry in profile.get("history", {}).get("suggested_tracks", []):
        exclude_keys.add(_normalize_key(entry))
    for dt in profile.get("feedback", {}).get("disliked_tracks", []):
        artist = dt.get("artist", "")
        track = dt.get("track", "")
        if artist and track:
            exclude_keys.add(_normalize_key(f"{artist} {track}"))

    # Build forbidden artist keys (rejected + disliked artists)
    forbidden_artist_keys = set()
    for entry in profile.get("artists", {}).get("rejected", []):
        name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
        if name:
            forbidden_artist_keys.add(_normalize_key(name))
    for name in profile.get("feedback", {}).get("disliked_artists", []):
        if name:
            forbidden_artist_keys.add(_normalize_key(str(name)))

    # Build exhausted artist keys using longest-match against known artists
    known_artists = sorted(
        set(profile.get("history", {}).get("suggested_artists", [])),
        key=len, reverse=True
    )
    artist_track_counts = defaultdict(int)
    for entry in profile.get("history", {}).get("suggested_tracks", []):
        e_lower = entry.lower().strip()
        for artist in known_artists:
            a_lower = artist.lower().strip()
            if e_lower.startswith(a_lower + " "):
                artist_track_counts[_normalize_key(a_lower)] += 1
                break
    exhausted_artist_keys = {
        a for a, count in artist_track_counts.items()
        if count >= EXHAUSTED_ARTIST_THRESHOLD
    }

    seen_in_batch = set()
    artist_counts_in_batch = defaultdict(int)
    filtered = []
    filtered_out = []

    for item in result.get("playlist", []):
        artist = item.get("artist", "").lower().strip()
        track = item.get("track", "").lower().strip()
        artist_key = _normalize_key(artist)
        key = _normalize_key(f"{artist} {track}")

        if artist_key in forbidden_artist_keys:
            print(f"Filtered (rejected/disliked artist): {artist}")
            filtered_out.append(item)
            continue

        if artist_key in exhausted_artist_keys:
            print(f"Filtered (exhausted artist): {artist}")
            filtered_out.append(item)
            continue

        if key in exclude_keys:
            print(f"Filtered (already suggested / disliked): {artist} - {track}")
            filtered_out.append(item)
            continue

        if key in seen_in_batch:
            print(f"Filtered (duplicate in batch): {artist} - {track}")
            filtered_out.append(item)
            continue

        artist_counts_in_batch[artist_key] += 1
        if artist_counts_in_batch[artist_key] > 2:
            print(f"Filtered (max 2 per artist exceeded): {artist}")
            filtered_out.append(item)
            continue

        seen_in_batch.add(key)
        filtered.append(item)

    result["playlist"] = filtered
    result["_filtered_out"] = filtered_out

    # Compute profile_updates and new_artists code-side (authoritative after truncation)
    filtered_artists = {item["artist"].lower().strip() for item in filtered}
    result["profile_updates"] = {
        "suggested_artists": list(filtered_artists),
        "suggested_tracks": [
            f"{item['artist'].lower().strip()} {item['track'].lower().strip()}"
            for item in filtered
        ],
    }
    existing_artists = {a.lower() for a in profile.get("history", {}).get("suggested_artists", [])}
    result["new_artists"] = [a for a in filtered_artists if a not in existing_artists]

    return result