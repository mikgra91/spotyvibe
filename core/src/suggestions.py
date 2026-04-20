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

import copy
import json
import logging
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from config import BASE_DIR, BATCH_SIZE, GPT_HISTORY_LIMIT, EXHAUSTED_ARTIST_THRESHOLD, get_model, get_gpt_language
from .utils import strip_code_fences, debug_log
from .openai_http import chat_completions_create, extract_chat_content
from .rag import score_artists, format_candidate_pool_block
from .rag.corpus import RagCorpus

# Process-wide corpus handle. Populated once by set_rag_corpus() from app.py
# startup; left as None when the corpus file is absent.
_RAG_CORPUS: RagCorpus | None = None

# Names of the artists in the candidate pool used by the most recent
# build_messages() call. Captured here so the eval log can record the
# *actual* pool the LLM was prompted with — without re-running the
# scorer (which is expensive and would silently drift if the scoring
# logic ever changes). None means RAG was disabled / corpus missing.
_LAST_RAG_POOL_NAMES: list[str] | None = None


def set_rag_corpus(corpus: RagCorpus | None) -> None:
    """Install the process-wide RAG corpus handle."""
    global _RAG_CORPUS
    _RAG_CORPUS = corpus


def get_rag_corpus() -> RagCorpus | None:
    return _RAG_CORPUS


def get_last_rag_pool_names() -> list[str] | None:
    """Return the candidate-pool artist names from the most recent build_messages call.

    None when the last call did not use RAG (no corpus loaded). Used by the
    eval log so it captures the same pool the LLM actually saw, instead of
    re-scoring (which wastes CPU and can drift from the prompt path).
    """
    return _LAST_RAG_POOL_NAMES

logger = logging.getLogger(__name__)

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


def _migrate_suggested_tracks(profile):
    """Convert legacy string suggested_tracks entries to {"artist", "track"} dicts.

    Old format: "artist name track name" (concatenated string)
    New format: {"artist": "artist name", "track": "track name"}

    Uses longest-match against suggested_artists to split the string. If no
    match is found, the full string is stored as track with empty artist —
    the normalize_key dedup still works because it hashes "artist track" as
    the combined key regardless of which field the data is in.
    Idempotent: dict entries are left unchanged.
    """
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if not tracks or all(isinstance(t, dict) for t in tracks):
        return profile

    known_artists = sorted(
        set(profile.get("history", {}).get("suggested_artists", [])),
        key=len, reverse=True,
    )

    migrated = []
    for entry in tracks:
        if isinstance(entry, dict):
            migrated.append(entry)
            continue
        e_lower = str(entry).lower().strip()
        matched_artist, matched_track = "", e_lower
        for artist in known_artists:
            a_lower = artist.lower().strip()
            if e_lower.startswith(a_lower + " "):
                matched_artist = a_lower
                matched_track = e_lower[len(a_lower):].strip()
                break
        migrated.append({"artist": matched_artist, "track": matched_track})

    profile["history"]["suggested_tracks"] = migrated
    return profile


def normalize_history(profile):
    """Lowercase, migrate, and deduplicate history so GPT never sees duplicates.

    Returns a shallow copy of the profile with only the history subtree
    deep-copied — avoids the cost of deep-copying the entire profile
    (preferences, feedback, artists) which are not mutated here.

    suggested_artists stays as a list of lowercase strings.
    suggested_tracks is migrated to {"artist", "track"} dicts (idempotent) and
    then deduplicated by (artist, track) key-pair.
    """
    profile = dict(profile)  # shallow copy — top-level keys only
    profile["history"] = copy.deepcopy(profile.get("history", {}))
    # Migrate legacy string entries to dicts before deduplication
    _migrate_suggested_tracks(profile)

    # Deduplicate suggested_artists (strings)
    artists = profile.get("history", {}).get("suggested_artists", [])
    seen: set = set()
    deduped_artists = []
    for item in artists:
        lower = str(item).lower().strip()
        if lower not in seen:
            seen.add(lower)
            deduped_artists.append(lower)
    profile["history"]["suggested_artists"] = deduped_artists

    # Deduplicate suggested_tracks (dicts)
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    seen_keys: set = set()
    deduped_tracks = []
    for item in tracks:
        if isinstance(item, dict):
            a = item.get("artist", "").lower().strip()
            t = item.get("track", "").lower().strip()
        else:
            a, t = "", str(item).lower().strip()
        key = (a, t)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_tracks.append({"artist": a, "track": t})
    profile["history"]["suggested_tracks"] = deduped_tracks
    return profile


def load_text_file(filepath):
    """Load a plain text file and return its content."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(
            f"{filepath} not found. Please create it."
        )
    return path.read_text(encoding="utf-8")


def _collect_forbidden_artists(profile, normalizer=None):
    """Collect forbidden artist keys from rejected + disliked artists.

    Args:
        profile: The user profile dict.
        normalizer: Function to normalize artist names. Defaults to lower+strip.

    Returns:
        A set of normalized forbidden artist keys.
    """
    if normalizer is None:
        normalizer = lambda name: name.lower().strip()
    forbidden = set()
    for entry in profile.get("artists", {}).get("rejected", []):
        name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
        if name:
            forbidden.add(normalizer(name))
    for name in profile.get("feedback", {}).get("disliked_artists", []):
        if name:
            forbidden.add(normalizer(str(name)))
    return forbidden


def _compute_exhausted_artists(profile, normalizer=None):
    """Compute exhausted artist keys from history (>= EXHAUSTED_ARTIST_THRESHOLD tracks).

    Args:
        profile: The user profile dict.
        normalizer: Function to normalize artist names. Defaults to lower+strip.

    Returns:
        A set of normalized exhausted artist keys.
    """
    if normalizer is None:
        normalizer = lambda name: name.lower().strip()
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if len(tracks) > GPT_HISTORY_LIMIT:
        tracks = tracks[-GPT_HISTORY_LIMIT:]
    artist_counts: dict = defaultdict(int)
    for entry in tracks:
        if isinstance(entry, dict):
            a = normalizer(entry.get("artist", ""))
        else:
            a = normalizer(str(entry))
        if a:
            artist_counts[a] += 1
    return {a for a, c in artist_counts.items() if c >= EXHAUSTED_ARTIST_THRESHOLD}


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
    forbidden_artists = _collect_forbidden_artists(profile)

    # Exhausted artists via history counts
    exhausted = sorted(_compute_exhausted_artists(profile))

    # Build track-by-artist grouping for forbidden_tracks
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if len(tracks) > GPT_HISTORY_LIMIT:
        tracks = tracks[-GPT_HISTORY_LIMIT:]

    by_artist: dict = defaultdict(list)

    for entry in tracks:
        if isinstance(entry, dict):
            a = entry.get("artist", "").lower().strip()
            t = entry.get("track", "").lower().strip()
        else:
            a, t = "", str(entry).lower().strip()

        if a:
            by_artist[a].append(t)
        else:
            by_artist["_unmatched"].append(t)


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


def _format_audio_filters(audio_filters):
    """Convert audio filter dict to a human-readable prompt block.

    Parameters:
        audio_filters: dict like {"energy": {"min": 0.6, "max": 1.0}, "tempo": {"min": 120}}

    Returns a string block for the prompt, or empty string if no filters.
    """
    if not audio_filters:
        return ""

    # Human-readable labels for each feature
    labels = {
        "energy": "energy (0=calm, 1=intense)",
        "valence": "valence/mood (0=sad/dark, 1=happy/cheerful)",
        "danceability": "danceability (0=not danceable, 1=very danceable)",
        "acousticness": "acousticness (0=electronic, 1=acoustic)",
        "instrumentalness": "instrumentalness (0=vocals, 1=instrumental)",
        "speechiness": "speechiness (0=no speech, 1=spoken word)",
        "liveness": "liveness (0=studio, 1=live feel)",
        "tempo": "tempo in BPM",
    }

    lines = ["AUDIO FILTER CONSTRAINTS — only suggest tracks matching ALL of these:"]
    for feature, bounds in audio_filters.items():
        if not bounds:
            continue
        label = labels.get(feature, feature)
        lo = bounds.get("min")
        hi = bounds.get("max")
        if lo is not None and hi is not None:
            lines.append(f"  - {label}: between {lo} and {hi}")
        elif lo is not None:
            lines.append(f"  - {label}: at least {lo}")
        elif hi is not None:
            lines.append(f"  - {label}: at most {hi}")

    if len(lines) == 1:
        return ""  # no actual constraints
    return "\n".join(lines)


# Model-specific validation blocks injected into the unified system prompt.
# GPT-4.1 uses chain-of-thought reasoning; GPT-5.4 uses structured candidate-pool
# validation; default uses a simple verification instruction.
_VALIDATION_BLOCKS = {
    "gpt-4-1": (
        "REASONING: Before output, reason through each candidate: "
        "(a) not in DENY_LIST? (b) satisfies EVERY must_have — if one missing, DISCARD? "
        "(c) matches ZERO avoid traits — if one matches, DISCARD? "
        "Only output tracks passing all checks."
    ),
    "gpt-5-4": (
        "VALIDATION: Build candidate pool > {batch_size}. For each candidate verify:\n"
        "(a) Artist NOT in any DENY_LIST section — else DISCARD.\n"
        "(b) Track NOT in any DENY_LIST section — else DISCARD.\n"
        "(c) Satisfies EVERY must_have trait — if even one missing, DISCARD.\n"
        "(d) Matches ZERO avoid traits — if even one matches, DISCARD.\n"
        "(e) Per-artist count ≤ 2.\n"
        "Select {batch_size} maximizing fit + diversity. "
        "Ensure ≥ {min_new_artists} from new artists."
    ),
}
_DEFAULT_VALIDATION = "VALIDATION: Before output, verify every track against constraints 1–7. Replace failures."


def _get_validation_block(model_name):
    """Return the validation block matching *model_name*, falling back to default."""
    slug = re.sub(r"[^a-z0-9-]", "-", model_name.lower()).strip("-")
    for key, block in _VALIDATION_BLOCKS.items():
        if key in slug:
            return block
    return _DEFAULT_VALIDATION


def build_messages(profile, accepted_tracks=None, batch_size=None,
                   recently_filtered_tracks=None,
                   new_artist_percentage=30, batch_num=0,
                   audio_filters=None, emerging_only=False):
    """Build the system + user message pair for the OpenAI API.

    Key design decisions:
    - Over-requests by +5 (effective_batch_size) to absorb expected filtering;
      +20 when emerging_only is True to account for heavier post-filter rejection.
    - On retries, filtered tracks go into an ephemeral deny set — never
      mentioned in prose (mentioning them primes GPT to repeat them).
    - DENY_LIST JSON comes before profile in the user message (positional bias).
    - Exclusion fields stripped from profile_for_gpt (DENY_LIST is sole source).
    - Diversity hints added when history is large (>50 tracks).
    """
    if batch_size is None:
        batch_size = BATCH_SIZE

    # Over-request: +20 buffer when emerging_only (heavy filtering expected), else +5
    buffer = 20 if emerging_only else 5
    effective_batch_size = batch_size + buffer
    min_new_artists = math.ceil(effective_batch_size * new_artist_percentage / 100)

    gpt_language = get_gpt_language()

    # Single unified system prompt with model-specific validation block injection.
    system_prompt = load_text_file(SYSTEM_PROMPT_FILE)
    validation_block = _get_validation_block(get_model())
    system_prompt = system_prompt.replace("{validation_block}", validation_block)
    system_prompt = system_prompt.replace("{batch_size}", str(effective_batch_size))
    system_prompt = system_prompt.replace("{new_artist_percentage}", str(new_artist_percentage))
    system_prompt = system_prompt.replace("{min_new_artists}", str(min_new_artists))
    system_prompt = system_prompt.replace("{gpt_language}", gpt_language)

    # Item 8 (2026-04): scale the rationale count to profile size so a
    # rich profile gets a richer per-track justification covering more
    # than one facet. Hard cap at 5 to keep responses lean.
    prefs = (profile or {}).get("preferences", {}) if isinstance(profile, dict) else {}
    must_have_n = len((prefs.get("must_have") or []))
    soft_n = len((prefs.get("soft_preferences") or []))
    profile_facets = must_have_n + soft_n
    if profile_facets >= 5:
        rationale_count = "3-5"
    elif profile_facets >= 2:
        rationale_count = "2-3"
    else:
        rationale_count = "1-2"
    system_prompt = system_prompt.replace("{rationale_count}", rationale_count)

    if emerging_only:
        emerging_constraint = (
            "\n8. ONLY suggest tracks by artists whose debut release is within the last 6 months."
            " Prefer unknown, underground, or recently debuted artists."
            " Do NOT suggest any established or long-running artists."
        )
        system_prompt += emerging_constraint

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
    audio_filters_block = _format_audio_filters(audio_filters)

    user_message = user_template.format(
        profile_json=json.dumps(profile_for_gpt, indent=2),
        deny_set_json=deny_set_json,
        batch_size=effective_batch_size,
        recent_feedback=feedback_summary,
        audio_filters_block=audio_filters_block,
    )

    # Inject RAG candidate pool when enabled and a corpus is loaded. The
    # deny set (from forbidden + exhausted artists) doubles as the dedup
    # barrier so the pool never contains artists the user already has.
    global _LAST_RAG_POOL_NAMES
    _LAST_RAG_POOL_NAMES = None
    corpus = get_rag_corpus()
    if corpus is not None:
        try:
            from config import RAG_POOL_SIZE, RAG_POPULARITY_PENALTY
        except ImportError:  # pragma: no cover — defensive
            RAG_POOL_SIZE, RAG_POPULARITY_PENALTY = 20, 0.4
        deny_keys = _collect_forbidden_artists(profile)
        confirmed = {a.get("name", "") if isinstance(a, dict) else str(a)
                     for a in profile.get("artists", {}).get("confirmed", [])}
        deny_keys = deny_keys | {c.lower().strip() for c in confirmed if c}
        pool = score_artists(
            corpus, profile, deny_keys=deny_keys,
            pool_size=RAG_POOL_SIZE,
            popularity_penalty=RAG_POPULARITY_PENALTY,
        )
        _LAST_RAG_POOL_NAMES = [a.name for a in pool]
        pool_block = format_candidate_pool_block(pool)
        if pool_block:
            user_message += f"\n\n{pool_block}"

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

    # Diversity hints when history is large — give GPT a concrete direction.
    # These are instruction-language (always English) — they tell GPT what
    # kind of artists to explore. The output language is controlled separately
    # via {gpt_language} in the prompt template.
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


_ALLOWED_RATIONALE_TYPES = {"profile_match", "artist_match", "recency", "novelty", "audio_match"}


def _normalize_rationale(entry: dict) -> list:
    """Parse and normalise the rationale array from a GPT track entry.

    - Drops entries whose type is not in the allowed set.
    - Truncates arg to 40 characters.
    - Caps array length to 2.
    - Falls back to legacy/fallback if nothing valid remains.
    """
    raw = entry.get("rationale")
    if isinstance(raw, list):
        normalised = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rtype = item.get("type", "")
            if rtype not in _ALLOWED_RATIONALE_TYPES:
                continue
            arg = item.get("arg")
            if not arg or not str(arg).strip():
                continue  # skip entries with empty/missing arg
            chip = {"type": rtype, "arg": str(arg).strip()[:40]}
            normalised.append(chip)
            if len(normalised) >= 2:
                break
        if normalised:
            return normalised

    # Fallback: legacy reason string
    reason = entry.get("reason", "")
    if reason:
        return [{"type": "legacy", "arg": str(reason)[:40]}]

    return [{"type": "fallback"}]


def normalize_response(result):
    """Force-lowercase all artist and track names in the GPT response.

    Strips model-generated metadata fields — new_artists and profile_updates
    are computed code-side in filter_duplicate_suggestions() after truncation,
    so model output for these would be inaccurate anyway.

    Also sanitizes GPT's output:
    - Removes self-excluded placeholder entries (GPT sometimes includes tracks
      with reasons like "Forbidden track, excluded." instead of omitting them).
    - Strips parenthetical meta-commentary from artist names (e.g.
      "Tycho (different track)" → "tycho") to prevent profile pollution.
    - Normalises rationale arrays to the bounded chip vocabulary (Wave 3).
    """
    result.pop("validation", None)

    # Keywords that indicate GPT meta-commentary (not legitimate artist name parts)
    _ANNOTATION_WORDS = {"different", "excluded", "forbidden", "not in",
                         "due to", "see above", "alternate version",
                         "from history", "other track", "previously"}

    sanitized_playlist = []
    for entry in result.get("playlist", []):
        # Drop entries where GPT explicitly flagged them as excluded
        reason = entry.get("reason", "").lower()
        if any(phrase in reason for phrase in
               ("forbidden track", "excluded", "not suggested", "deny list")):
            artist_raw = entry.get("artist", "")
            track_raw = entry.get("track", "")
            # Only drop if the reason makes it clear this is NOT a real suggestion
            if any(w in reason for w in ("excluded", "not suggested")):
                logger.debug("Dropped GPT self-excluded entry: %s - %s", artist_raw, track_raw)
                continue

        # Strip parenthetical GPT annotations from artist names
        artist = entry.get("artist", "")
        artist = _strip_gpt_annotation(artist, _ANNOTATION_WORDS)
        entry["artist"] = artist.lower().strip()
        entry["track"] = entry.get("track", "").lower().strip()

        # Normalise rationale (Wave 3)
        entry["rationale"] = _normalize_rationale(entry)

        # Normalise energy & valence estimates from GPT (Wave 3 dashboard)
        for af_key in ("energy", "valence"):
            raw = entry.get(af_key)
            if raw is not None:
                try:
                    val = float(raw)
                    entry[af_key] = max(0.0, min(1.0, round(val, 3)))
                except (TypeError, ValueError):
                    entry.pop(af_key, None)

        # Normalise genres from GPT (Wave 3 dashboard)
        raw_genres = entry.get("genres")
        if isinstance(raw_genres, list):
            clean = []
            for g in raw_genres:
                if isinstance(g, str) and g.strip():
                    clean.append(g.strip().lower()[:40])
                if len(clean) >= 3:
                    break
            entry["genres"] = clean
        else:
            entry["genres"] = []

        sanitized_playlist.append(entry)

    result["playlist"] = sanitized_playlist

    # These are derived in code — initialize empty so downstream never fails
    result["new_artists"] = []
    result["profile_updates"] = {"suggested_artists": [], "suggested_tracks": []}
    return result


def _strip_gpt_annotation(artist: str, annotation_words: set) -> str:
    """Strip trailing parenthetical text from an artist name if it looks like
    GPT meta-commentary rather than a legitimate part of the name.

    Examples:
        "Tycho (different track)"                              → "Tycho"
        "Boards of Canada (excluded due to forbidden tracks)"  → "Boards of Canada"
        "Nightmares on Wax (different track)"                  → "Nightmares on Wax"
        "Emancipator (excluded due to forbidden tracks and history)" → "Emancipator"
        "Iron & Wine"                                          → "Iron & Wine"  (unchanged)
    """
    # Match trailing (...) content
    match = re.search(r'\s*\(([^)]+)\)\s*$', artist)
    if not match:
        return artist
    paren_content = match.group(1).lower()
    # Check if the parenthetical contains any annotation keywords
    if any(word in paren_content for word in annotation_words):
        return artist[:match.start()].strip()
    return artist


def call_gpt(messages, temperature=0.7):
    """Send the assembled messages to the OpenAI Chat Completions API.

    Temperature is configurable — callers pass a lower value on retries
    to push toward more deterministic (less repetitive) output.
    """
    response = chat_completions_create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    raw_content = extract_chat_content(response)
    debug_log("Suggestion Generation", messages, raw_content)

    content = strip_code_fences(raw_content)

    if not content:
        logger.warning("GPT returned empty response. Using empty playlist.")
        return {"playlist": [], "new_artists": [], "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}

    try:
        result = json.loads(content)
        return normalize_response(result)
    except json.JSONDecodeError:
        logger.warning("GPT response could not be parsed as JSON. Response was: %s", content)
        return {"playlist": [], "new_artists": [], "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}


def update_profile(profile, result):
    """Append newly suggested artists and tracks to the profile history.

    Uses set-based deduplication (lowercased) to prevent history bloat.
    The history is append-only — entries are never removed here, only
    added. This ensures the exclusion list grows monotonically, which
    is essential for the dedup strategy to work correctly.

    suggested_tracks are stored as {"artist", "track"} dicts. Legacy string
    entries in the profile are handled via _normalize_key for dedup but new
    entries are always written as dicts.
    """
    existing_artists = {a.lower() for a in profile["history"]["suggested_artists"]}
    for artist in result["profile_updates"]["suggested_artists"]:
        lower = artist.lower().strip()
        if lower not in existing_artists:
            profile["history"]["suggested_artists"].append(lower)
            existing_artists.add(lower)

    existing_tracks: set = set()
    for t in profile["history"]["suggested_tracks"]:
        if isinstance(t, dict):
            existing_tracks.add(_normalize_key(f"{t.get('artist', '')} {t.get('track', '')}"))
        else:
            existing_tracks.add(_normalize_key(str(t)))

    for track in result["profile_updates"]["suggested_tracks"]:
        if isinstance(track, dict):
            key = _normalize_key(f"{track.get('artist', '')} {track.get('track', '')}")
            entry: dict = {
                "artist": track.get("artist", "").lower().strip(),
                "track": track.get("track", "").lower().strip(),
            }
        else:
            key = _normalize_key(str(track))
            entry = {"artist": "", "track": str(track).lower().strip()}
        if key not in existing_tracks:
            profile["history"]["suggested_tracks"].append(entry)
            existing_tracks.add(key)

    return profile


# ── Code-side dedup (GPT cannot be trusted to follow history) ────────

def _normalize_key(text):
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy dedup.

    NFKD normalization handles curly quotes, accented characters, and
    ligatures (e.g. "Beyoncé" vs "Beyonce", "The Mowgli's" vs "The Mowgli´s").
    Preserves non-Latin scripts (CJK, Cyrillic, Arabic, etc.).
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s, flags=re.UNICODE)  # keep word chars (incl. non-Latin) + spaces
    s = re.sub(r'\s+', ' ', s).strip()   # collapse whitespace
    return s if s else text.lower().strip()  # fallback if normalization yields empty


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
        if isinstance(entry, dict):
            exclude_keys.add(_normalize_key(f"{entry.get('artist', '')} {entry.get('track', '')}"))
        else:
            exclude_keys.add(_normalize_key(entry))
    for dt in profile.get("feedback", {}).get("disliked_tracks", []):
        artist = dt.get("artist", "")
        track = dt.get("track", "")
        if artist and track:
            exclude_keys.add(_normalize_key(f"{artist} {track}"))

    # Build forbidden artist keys (rejected + disliked artists)
    forbidden_artist_keys = _collect_forbidden_artists(profile, normalizer=_normalize_key)

    # Build exhausted artist keys
    exhausted_artist_keys = _compute_exhausted_artists(profile, normalizer=_normalize_key)

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
            logger.debug("Filtered (rejected/disliked artist): %s", artist)
            filtered_out.append(item)
            continue

        if artist_key in exhausted_artist_keys:
            logger.debug("Filtered (exhausted artist): %s", artist)
            filtered_out.append(item)
            continue

        if key in exclude_keys:
            logger.debug("Filtered (already suggested / disliked): %s - %s", artist, track)
            filtered_out.append(item)
            continue

        if key in seen_in_batch:
            logger.debug("Filtered (duplicate in batch): %s - %s", artist, track)
            filtered_out.append(item)
            continue

        artist_counts_in_batch[artist_key] += 1
        if artist_counts_in_batch[artist_key] > 2:
            logger.debug("Filtered (max 2 per artist exceeded): %s", artist)
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
            {"artist": item["artist"].lower().strip(), "track": item["track"].lower().strip()}
            for item in filtered
        ],
    }
    existing_artists = {a.lower() for a in profile.get("history", {}).get("suggested_artists", [])}
    result["new_artists"] = [a for a in filtered_artists if a not in existing_artists]

    return result

