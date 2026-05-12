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
import functools
import json
import logging
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from config import (BASE_DIR, BATCH_SIZE, GPT_HISTORY_LIMIT, EXHAUSTED_ARTIST_THRESHOLD,
                    RECENT_VERBATIM_TRACKS,
                    STAGE3_OVER_REQUEST, STAGE3_FAST_MODEL, STAGE3_BEST_MODEL,
                    get_model, get_gpt_language, get_stage2_model, get_debug_mode,
                    get_stage3_mode)
from .utils import strip_code_fences, debug_log
from .openai_http import chat_completions_create, extract_chat_content
from .rag import score_artists, score_artists_stratified, format_candidate_pool_block
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

# Per-component char counts of the most recent build_messages() output.
# Captured so the eval log (log_batch_summary) can record which prompt slice
# changed batch-to-batch without re-tokenising. Char counts (deterministic,
# tokeniser-free) — see eval_log.log_batch_summary docstring for the schema.
_LAST_PROMPT_COMPONENTS: dict | None = None


def set_rag_corpus(corpus: RagCorpus | None) -> None:
    """Install the process-wide RAG corpus handle."""
    global _RAG_CORPUS
    _RAG_CORPUS = corpus


def get_rag_corpus() -> RagCorpus | None:
    return _RAG_CORPUS


def set_last_rag_pool_names(names: list[str] | None) -> None:
    """Set the candidate-pool artist names (used by app.py after Stage 1)."""
    global _LAST_RAG_POOL_NAMES
    _LAST_RAG_POOL_NAMES = names


def get_last_rag_pool_names() -> list[str] | None:
    """Return the candidate-pool artist names from the most recent build_messages call.

    None when the last call did not use RAG (no corpus loaded). Used by the
    eval log so it captures the same pool the LLM actually saw, instead of
    re-scoring (which wastes CPU and can drift from the prompt path).
    """
    return _LAST_RAG_POOL_NAMES


def get_last_prompt_components() -> dict | None:
    """Return per-component char counts of the most recent build_messages output.

    Schema matches eval_log.log_batch_summary's ``prompt_components`` field:
    ``{system, user_total, profile, deny_set, pool, accepted, feedback,
    diversity_hint, audio_filters}``. ``None`` until the first call.
    """
    return _LAST_PROMPT_COMPONENTS


logger = logging.getLogger(__name__)

# Paths resolved from the package root using pathlib — immune to os.chdir()
SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system_prompt.txt"
PROMPT_FILE = BASE_DIR / "prompts" / "prompt_template.txt"
AVOID_CHECK_SYSTEM_FILE = BASE_DIR / "prompts" / "avoid_check_system.txt"
TRACK_SELECT_SYSTEM_FILE = BASE_DIR / "prompts" / "track_select_system.txt"
# Phase 2.5 (2026-04-27): slim variant for local LLM providers (Ollama,
# LM Studio). Llama 3.2 3B / Qwen 2.5 7B suffer "lost-in-middle" past
# ~350 system tokens and have weaker negation handling — the slim
# variant uses positive-form constraints and a 2-field reasoning block.
TRACK_SELECT_SYSTEM_FILE_LOCAL = BASE_DIR / "prompts" / "track_select_system_local.txt"
TRACK_SELECT_USER_FILE = BASE_DIR / "prompts" / "track_select_user.txt"



def build_feedback_summary(profile, max_chars=2000, recent_n=3, line_cap=300):
    """Build a short 'recent feedback' block from liked/disliked tracks.

    Picks the last ``recent_n`` entries from each list and formats them as a
    concise human-readable block that GPT can use to bias the next run.
    Each line is capped at ``line_cap`` chars, and the whole block at
    ``max_chars``.
    """
    liked = profile.get("feedback", {}).get("liked_tracks", [])
    disliked = profile.get("feedback", {}).get("disliked_tracks", [])

    if not liked and not disliked:
        return ""

    lines = ["Recent user feedback (use to fine-tune your suggestions):"]

    def _format(prefix, entries):
        for entry in entries[-recent_n:]:
            artist = entry.get("artist", "")
            track = entry.get("track", "")
            reason = entry.get("reason", "")
            line = f"  {prefix} {artist} - {track}"
            if reason:
                line += f" (reason: {reason})"
            if len(line) > line_cap:
                line = line[:line_cap] + "…"
            lines.append(line)

    _format("+ Liked:", liked)
    _format("- Disliked:", disliked)

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


# L4 (2026-05-07): per-process LRU cache so the prompt files under
# ``prompts/*.txt`` are read from disk at most once each. They are
# treated as immutable at runtime (a developer changing them mid-
# session can call ``load_text_file.cache_clear()``); without the
# cache, every Stage-3 batch (~10 per playlist) re-reads the same
# four files and pays ~5 ms × 10 = ~50 ms / run for nothing.
@functools.lru_cache(maxsize=32)
def _load_text_file_cached(filepath_str: str) -> str:
    path = Path(filepath_str)
    if not path.exists():
        raise FileNotFoundError(
            f"{filepath_str} not found. Please create it."
        )
    return path.read_text(encoding="utf-8")


def load_text_file(filepath):
    """Load a plain text file and return its content (LRU-cached).

    The cache key is the stringified path so callers can pass
    ``Path`` objects without breaking memoisation. Use
    ``load_text_file.cache_clear()`` (exposed below) to force a
    re-read after editing a prompt file in a long-lived process.
    """
    return _load_text_file_cached(str(filepath))


# Surface the underlying cache control on the public name so callers /
# tests can invalidate without reaching into a private symbol.
load_text_file.cache_clear = _load_text_file_cached.cache_clear  # type: ignore[attr-defined]
load_text_file.cache_info = _load_text_file_cached.cache_info  # type: ignore[attr-defined]


def collect_forbidden_artists(profile, normalizer=None):
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


def _aggregate_artist_track_counts(profile, normalizer=None):
    """Count suggested tracks per artist over the (capped) history window.

    C3 (2026-05-10) — single source of truth for both `_compute_exhausted_artists`
    and the new `artist_track_counts` block in `_build_deny_set_json`. The
    GPT_HISTORY_LIMIT cap still applies (caller-side trim) so an unbounded
    profile can't drive token cost up — verbatim render is bounded by
    RECENT_VERBATIM_TRACKS, aggregate render by GPT_HISTORY_LIMIT.
    """
    if normalizer is None:
        normalizer = lambda name: name.lower().strip()
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    if len(tracks) > GPT_HISTORY_LIMIT:
        tracks = tracks[-GPT_HISTORY_LIMIT:]
    counts: dict = defaultdict(int)
    for entry in tracks:
        if isinstance(entry, dict):
            a = normalizer(entry.get("artist", ""))
        else:
            a = normalizer(str(entry))
        if a:
            counts[a] += 1
    return counts


def _compute_exhausted_artists(profile, normalizer=None):
    """Compute exhausted artist keys from history (>= EXHAUSTED_ARTIST_THRESHOLD tracks).

    Args:
        profile: The user profile dict.
        normalizer: Function to normalize artist names. Defaults to lower+strip.

    Returns:
        A set of normalized exhausted artist keys.
    """
    counts = _aggregate_artist_track_counts(profile, normalizer)
    return {a for a, c in counts.items() if c >= EXHAUSTED_ARTIST_THRESHOLD}


def _build_deny_set_json(profile, ephemeral_deny_tracks=None):
    """Build a consolidated JSON deny set for the prompt.

    SCOPE — only the legacy ``build_messages`` path consumes this block
    (RAG disabled / emerging_only mode). The production Stage 3
    (``select_tracks`` + ``track_select_*.txt``) operates on a
    pre-approved artist list and does NOT see DENY_LIST; per-track dedup
    for that path is enforced post-hoc by ``filter_duplicate_suggestions``.

    Merges all exclusion sources into a single structured block:
    - artists.rejected + feedback.disliked_artists → forbidden_artists
    - exhausted artists (computed from history) → exhausted_artists
    - history.suggested_tracks grouped by artist → forbidden_tracks
      (limited to the most-recent ``RECENT_VERBATIM_TRACKS`` entries,
      C3 2026-05-10 — older history is represented as counts only)
    - artist_track_counts (C3): per-artist all-time aggregate over the
      ``GPT_HISTORY_LIMIT`` window — replaces the verbatim long-tail
    - feedback.disliked_tracks → disliked_tracks
    - ephemeral_deny_tracks (retry-filtered, NOT persisted) → retry_forbidden_tracks

    GPT-4.1-mini in json_object mode processes JSON lookups more accurately
    than prose exclusion lists. DENY_LIST is the single source of truth
    for the legacy path; exclusion fields are stripped from the profile
    JSON before sending.
    """
    # Forbidden artists (merged from all sources)
    forbidden_artists = collect_forbidden_artists(profile)

    # C3 (2026-05-10): all-time per-artist counts (within the
    # GPT_HISTORY_LIMIT cap). Drives both `exhausted_artists` and the
    # new `artist_track_counts` block — long-tail history is represented
    # by counts only, not verbatim track names, to keep prompt growth
    # bounded as the profile matures.
    artist_counts = _aggregate_artist_track_counts(profile)
    exhausted = sorted({a for a, c in artist_counts.items() if c >= EXHAUSTED_ARTIST_THRESHOLD})

    # Verbatim forbidden_tracks comes from the most-recent slice only
    # (RECENT_VERBATIM_TRACKS). Older tracks are still represented via
    # artist_track_counts, and once an artist trips EXHAUSTED_ARTIST_THRESHOLD
    # the model is told to skip them entirely — so a track from 6 months
    # ago can't reappear unless its artist count is genuinely low.
    tracks = profile.get("history", {}).get("suggested_tracks", [])
    recent_tracks = tracks[-RECENT_VERBATIM_TRACKS:] if len(tracks) > RECENT_VERBATIM_TRACKS else tracks

    by_artist: dict = defaultdict(list)

    for entry in recent_tracks:
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
        "exhausted_artists": exhausted,
        "forbidden_tracks": {
            a: sorted(t) for a, t in sorted(by_artist.items()) if a != "_unmatched"
        },
        # Sort descending by count so the highest-signal entries are seen
        # first by the model — relevant under truncation / context-budget
        # pressure on smaller models.
        "artist_track_counts": dict(
            sorted(artist_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "disliked_tracks": {a: sorted(t) for a, t in sorted(disliked_tracks.items())},
    }

    if "_unmatched" in by_artist:
        deny_set["other_forbidden_tracks"] = sorted(by_artist["_unmatched"])

    if ephemeral_deny_tracks:
        deny_set["retry_forbidden_tracks"] = sorted(ephemeral_deny_tracks)

    return json.dumps(deny_set, separators=(",", ":"), ensure_ascii=False)


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
    "gpt-5-5": (
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
        rationale_count = "4"
    elif profile_facets >= 2:
        rationale_count = "3"
    else:
        rationale_count = "2"
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
    fb_for_gpt = profile_for_gpt.get("feedback", {})
    fb_for_gpt.pop("disliked_artists", None)
    # P0.3 trim: liked/disliked tracks are surfaced via build_feedback_summary
    # (capped, prose-formatted) — sending the raw arrays as well wastes ~1.5 k
    # tokens per batch with no signal the summary doesn't already carry.
    fb_for_gpt.pop("liked_tracks", None)
    fb_for_gpt.pop("disliked_tracks", None)

    feedback_summary = build_feedback_summary(profile)
    audio_filters_block = _format_audio_filters(audio_filters)

    profile_json_str = json.dumps(profile_for_gpt, separators=(",", ":"), ensure_ascii=False)
    user_message = user_template.format(
        profile_json=profile_json_str,
        deny_set_json=deny_set_json,
        batch_size=effective_batch_size,
        recent_feedback=feedback_summary,
        audio_filters_block=audio_filters_block,
    )

    # Component sizes (chars) — captured for the eval log so we can attribute
    # batch-to-batch prompt growth to a specific slice. Updated below as
    # optional blocks are appended.
    components = {
        "system": len(system_prompt),
        "profile": len(profile_json_str),
        "deny_set": len(deny_set_json),
        "feedback": len(feedback_summary),
        "audio_filters": len(audio_filters_block),
        "pool": 0,
        "accepted": 0,
        "diversity_hint": 0,
    }

    # Inject RAG candidate pool when enabled and a corpus is loaded. The
    # deny set (from forbidden + exhausted artists) doubles as the dedup
    # barrier so the pool never contains artists the user already has.
    #
    # IMPORTANT — bypass RAG when ``emerging_only=True``: the candidate
    # pool is built from a quarterly MusicBrainz dump and cannot contain
    # artists who debuted in the last ~3-6 months. Injecting it would
    # contradict the system constraint *"only suggest tracks by artists
    # whose debut release is within the last 6 months"* and waste tokens.
    # The post-Spotify ``filter_emerging_artists`` (release_date check)
    # remains the factual verification step. See report
    # spotyvibe-decisions-2026-04-21.md for the rationale.
    global _LAST_RAG_POOL_NAMES
    _LAST_RAG_POOL_NAMES = None
    corpus = get_rag_corpus()
    if corpus is not None and not emerging_only:
        try:
            from config import (RAG_POOL_SIZE, RAG_POPULARITY_PENALTY,
                                RAG_STRATIFIED, RAG_FACET_WEIGHTS)
        except ImportError:  # pragma: no cover — defensive
            RAG_POOL_SIZE, RAG_POPULARITY_PENALTY = 100, 0.4
            RAG_STRATIFIED = True
            RAG_FACET_WEIGHTS = {"must_have": 0.5, "soft_preferences": 0.25,
                                 "primary_reference": 0.15, "tags": 0.10}
        deny_keys = collect_forbidden_artists(profile)
        confirmed = {a.get("name", "") if isinstance(a, dict) else str(a)
                     for a in profile.get("artists", {}).get("confirmed", [])}
        deny_keys = deny_keys | {c.lower().strip() for c in confirmed if c}
        if RAG_STRATIFIED:
            pool = score_artists_stratified(
                corpus, profile, deny_keys=deny_keys,
                pool_size=RAG_POOL_SIZE,
                popularity_penalty=RAG_POPULARITY_PENALTY,
                facet_weights=RAG_FACET_WEIGHTS,
            )
        else:
            pool = score_artists(
                corpus, profile, deny_keys=deny_keys,
                pool_size=RAG_POOL_SIZE,
                popularity_penalty=RAG_POPULARITY_PENALTY,
            )
        _LAST_RAG_POOL_NAMES = [a.name for a in pool]
        pool_block = format_candidate_pool_block(pool)
        if pool_block:
            user_message += f"\n\n{pool_block}"
            components["pool"] = len(pool_block)
    elif corpus is not None and emerging_only:
        logger.debug("RAG bypassed: emerging_only=True (corpus cannot contain "
                     "artists who debuted in the last 6 months).")

    if accepted_tracks:
        listing = "\n".join(
            f"- {t['artist']} - {t['track']}" for t in accepted_tracks
        )
        accepted_block = (
            f"\n\nI already accepted these {len(accepted_tracks)} tracks from"
            f" previous batches — do NOT suggest them again:\n{listing}\n\n"
            f"I need {effective_batch_size} MORE tracks. Still return the result in"
            " the same JSON schema but with exactly"
            f" {effective_batch_size} entries in \"playlist\"."
        )
        user_message += accepted_block
        components["accepted"] = len(accepted_block)

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
        # F7 (2026-05-01): drop any hint that contradicts the user's
        # avoid prose (e.g. "1970s-1980s focus" vs. "avoid 80s
        # production style"). Without this filter the model receives
        # contradictory instructions and tends to follow the explicit
        # diversity hint over the soft "Avoid: …" string.
        avoid_traits = (profile.get("preferences") or {}).get("avoid")
        if isinstance(avoid_traits, str):
            avoid_traits = [avoid_traits]
        diversity_hints = _filter_diversity_hints(diversity_hints, avoid_traits)
        if diversity_hints:
            hint = diversity_hints[batch_num % len(diversity_hints)]
            diversity_block = f"\n\nDiversity guidance: {hint}"
            user_message += diversity_block
            components["diversity_hint"] = len(diversity_block)

    components["user_total"] = len(user_message)
    global _LAST_PROMPT_COMPONENTS
    _LAST_PROMPT_COMPONENTS = components

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


_ALLOWED_RATIONALE_TYPES = {"profile_match", "artist_match", "recency", "novelty", "audio_match"}


# Decade aliases so the diversity-hint conflict check treats "80s" and
# "1980s" as the same concept regardless of which form the profile or
# the hint uses.
_DECADE_ALIASES = (
    ("70s", "1970s"),
    ("80s", "1980s"),
    ("90s", "1990s"),
    ("00s", "2000s"),
    ("10s", "2010s"),
    ("20s", "2020s"),
)


def _filter_diversity_hints(
    hints: list[str], avoid_traits: list[str] | None
) -> list[str]:
    """Drop diversity hints that conflict with the user's avoid prose.

    F7 fix (2026-05-01): the static hint cycle includes "Focus on
    artists from the 1970s-1980s …", which contradicts an avoid entry
    like "80s production style". Without this filter the model receives
    contradictory instructions and tends to follow the explicit
    diversity hint over the soft "Avoid: …" string.

    Conflict rules:
    - Decade strings (``70s``…``20s`` or ``1970s``…``2020s``) collide
      across short/long forms.
    - Any 5+ letter alphabetic token that appears in both the avoid
      prose and the hint counts as a conflict.

    Returns hints in original order with conflicting entries removed.
    Empty *avoid_traits* returns *hints* unchanged.
    """
    if not avoid_traits:
        return list(hints)
    avoid_l = " | ".join(
        t.lower() for t in avoid_traits if isinstance(t, str)
    )
    if not avoid_l.strip():
        return list(hints)
    avoid_tokens = set(re.findall(r"[a-z]{5,}", avoid_l))

    def _conflicts(hint: str) -> bool:
        h_l = hint.lower()
        for short, long in _DECADE_ALIASES:
            avoid_has_decade = short in avoid_l or long in avoid_l
            hint_has_decade = short in h_l or long in h_l
            if avoid_has_decade and hint_has_decade:
                return True
        hint_tokens = set(re.findall(r"[a-z]{5,}", h_l))
        return bool(avoid_tokens & hint_tokens)

    return [h for h in hints if not _conflicts(h)]


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
            # 2026-04-28: bumped from 40 → 80 chars. Strict json_schema
            # (OPEN-3) removed the optional `reason`/`energy`/`valence`/
            # `genres` fields; the model compensates by packing richer
            # info into the `arg` field (e.g. "punchy guitars and
            # theatrical personality" instead of "punchy guitars").
            # The 40-char cap was truncating must-have keywords mid-word
            # which caused has_must_have_cite to drop ~50 pp on
            # gpt-5.4-mini despite the model genuinely satisfying the
            # constraint. UI chip styling already wraps long labels.
            chip = {"type": rtype, "arg": str(arg).strip()[:80]}
            normalised.append(chip)
            if len(normalised) >= 2:
                break
        if normalised:
            return normalised

    # Fallback: legacy reason string
    reason = entry.get("reason", "")
    if reason:
        return [{"type": "legacy", "arg": str(reason)[:80]}]

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
    - Drops schema-collapse rows where the model echoed the artist name into
      the `track` field, used a placeholder string, or duplicated the
      previous row's track. Counts each shape on
      ``result["_schema_collapse"]`` for telemetry.
    - Normalises rationale arrays to the bounded chip vocabulary (Wave 3).
    """
    result.pop("validation", None)

    # Keywords that indicate GPT meta-commentary (not legitimate artist name parts)
    _ANNOTATION_WORDS = {"different", "excluded", "forbidden", "not in",
                         "due to", "see above", "alternate version",
                         "from history", "other track", "previously"}

    # Strings the LLM falls back to when it has no real track to supply.
    # Conservative: only obvious schema-collapse placeholders. Single-word
    # fillers like "song" or "track" can plausibly appear in legitimate
    # short titles, so they are excluded.
    _PLACEHOLDER_TRACKS = {"", "-", "—", "untitled", "intro", "outro",
                           "track 1", "interlude", "self-titled"}

    schema_collapse = {"eq_artist": 0, "placeholder_token": 0,
                       "dup_in_batch": 0}
    seen_tracks: set[str] = set()
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
        artist_norm = artist.lower().strip()
        track_norm = entry.get("track", "").lower().strip()
        entry["artist"] = artist_norm
        entry["track"] = track_norm

        # ── Anti-confabulation guards (P1.x schema-collapse fix 2026-04-27) ──
        if artist_norm and track_norm and artist_norm == track_norm:
            # Model echoed the artist name into the track field — most common
            # collapse mode for gpt-5.4-mini against an obscure RAG pool.
            schema_collapse["eq_artist"] += 1
            logger.debug("Dropped schema-collapse (track==artist): %s", artist_norm)
            continue
        if track_norm in _PLACEHOLDER_TRACKS:
            schema_collapse["placeholder_token"] += 1
            logger.debug("Dropped schema-collapse (placeholder track): %r for artist %r",
                         track_norm, artist_norm)
            continue
        track_key = f"{artist_norm}::{track_norm}"
        if track_key in seen_tracks:
            schema_collapse["dup_in_batch"] += 1
            logger.debug("Dropped schema-collapse (duplicate within batch): %s", track_key)
            continue
        seen_tracks.add(track_key)

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
    schema_collapse["total"] = (schema_collapse["eq_artist"]
                                + schema_collapse["placeholder_token"]
                                + schema_collapse["dup_in_batch"])
    result["_schema_collapse"] = schema_collapse

    # These are derived in code — initialize empty so downstream never fails
    result["new_artists"] = []
    result["profile_updates"] = {"suggested_artists": [], "suggested_tracks": []}
    return result


def _hash_messages_for_audit(messages: list) -> dict:
    """Tier 1 (2026-05-10) — md5-hash the system + user prompt prefixes.

    Used by the eval log to detect (a) prompt drift between runs without
    diffing whole trace bundles and (b) which calls hit the same prefix
    (relevant to OpenAI's prompt cache routing). Returns short hex
    digests so the row stays compact. Failures (malformed messages,
    encoding glitches) yield ``None`` rather than crashing telemetry.
    """
    import hashlib as _hl
    out: dict = {}
    try:
        for m in messages or []:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content") or ""
            if role in ("system", "user") and content:
                key = f"{role}_md5"
                if key not in out:
                    out[key] = _hl.md5(content.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return {}
    return out


def _resolve_stage3_model(profile: dict | None, *, mode: str | None = None) -> str:
    """Pick the Stage 3 model based on the configured strategy + profile state.

    L5 (2026-05-08). Modes: "fast" → STAGE3_FAST_MODEL, "best" →
    STAGE3_BEST_MODEL, "auto" → fast for cold profile / best once
    ``feedback.disliked_tracks`` carries ≥ 1 entry, "custom" → whatever
    ``get_model()`` resolves (the existing OPENAI_MODEL path; covers
    local LLMs).

    ``mode`` override is for tests; production resolves via
    ``get_stage3_mode()``.
    """
    resolved_mode = (mode or get_stage3_mode() or "").strip().lower()
    if resolved_mode == "best":
        return STAGE3_BEST_MODEL
    if resolved_mode == "custom":
        return get_model()
    if resolved_mode == "auto":
        feedback = (profile or {}).get("feedback", {}) if isinstance(profile, dict) else {}
        disliked = feedback.get("disliked_tracks") if isinstance(feedback, dict) else None
        if isinstance(disliked, list) and len(disliked) >= 1:
            return STAGE3_BEST_MODEL
        return STAGE3_FAST_MODEL
    # "fast" + any unknown / typo'd value (get_stage3_mode() already
    # falls back to default, this is belt-and-braces for direct callers).
    return STAGE3_FAST_MODEL


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


def call_gpt(messages, temperature=0.7, return_meta=False):
    """Send the assembled messages to the OpenAI Chat Completions API.

    Temperature is configurable — callers pass a lower value on retries
    to push toward more deterministic (less repetitive) output.

    When ``return_meta=True``, returns ``(result, meta)`` where ``meta`` is
    ``{"usage": dict|None, "latency_s": float}``. ``usage`` is the provider's
    ``{prompt_tokens, completion_tokens, total_tokens}`` block when available
    (None for local LLMs that don't report it). Without ``return_meta`` the
    legacy single-return signature is preserved.
    """
    import time as _time
    _t0 = _time.monotonic()
    response = chat_completions_create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    latency_s = _time.monotonic() - _t0

    raw_content = extract_chat_content(response)
    debug_log("Suggestion Generation", messages, raw_content)

    usage = response.get("usage") if isinstance(response, dict) else None
    # Tier 1 (2026-05-10): surface system_fingerprint + prompt-prefix
    # hashes so the eval log can detect (a) silent OpenAI model rolls and
    # (b) any prompt drift across runs. Both fields are diagnostic-only;
    # missing values stay None for non-OpenAI providers.
    system_fp = response.get("system_fingerprint") if isinstance(response, dict) else None
    prompt_hashes = _hash_messages_for_audit(messages)
    meta = {
        "usage": usage,
        "latency_s": latency_s,
        "system_fingerprint": system_fp,
        "prompt_hashes": prompt_hashes,
    }

    content = strip_code_fences(raw_content)

    def _empty():
        return {"playlist": [], "new_artists": [],
                "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}

    if not content:
        logger.warning("GPT returned empty response. Using empty playlist.")
        result = _empty()
        return (result, meta) if return_meta else result

    try:
        result = normalize_response(json.loads(content))
    except json.JSONDecodeError:
        logger.warning("GPT response could not be parsed as JSON. Response was: %s", content)
        result = _empty()

    return (result, meta) if return_meta else result


def build_taste_summary(profile: dict) -> str:
    """Build a compact ≤800-char taste summary for Stage 3 prompts (P1.3).

    Deterministic — no LLM. Extracts must_have, soft_preferences, avoid,
    confirmed artist anchors, era, and core_description from the profile and
    renders them as a concise single-paragraph hint.

    This replaces the full profile JSON + deny set + RAG pool in Stage 3,
    cutting the input from ~7 k tok to ~200 tok.
    """
    prefs = (profile or {}).get("preferences", {}) or {}

    def _join(val: object) -> str:
        if isinstance(val, list):
            return ", ".join(str(v) for v in val if v)
        return str(val).strip() if val else ""

    parts: list[str] = []

    eras = _join(prefs.get("eras"))
    if eras:
        parts.append(f"Era: {eras}.")

    must = _join(prefs.get("must_have"))
    if must:
        parts.append(f"Must: {must}.")

    soft = _join(prefs.get("soft_preferences"))
    if soft:
        parts.append(f"Style: {soft}.")

    avoid = _join(prefs.get("avoid"))
    if avoid:
        parts.append(f"Avoid: {avoid}.")

    primary = (profile or {}).get("meta", {}).get("primary_reference") or ""
    if isinstance(primary, str) and primary.strip():
        parts.append(f"Primary reference: {primary.strip()}.")

    confirmed = (profile or {}).get("artists", {}).get("confirmed", [])
    anchors: list[str] = []
    for a in confirmed[:5]:
        name = a.get("name", "") if isinstance(a, dict) else str(a)
        if name:
            anchors.append(name)
    if anchors:
        parts.append(f"Style anchors: {', '.join(anchors)}.")

    core = (prefs.get("core_description") or "").strip()
    if core:
        if len(core) > 200:
            core = core[:200] + "…"
        parts.append(core)

    summary = " ".join(parts)
    if len(summary) > 800:
        summary = summary[:800] + "…"
    return summary


def check_avoid_compliance(
    artist_names: list[str],
    avoid_traits: list[str] | None,
    pool_avoid_overlap: int | None = None,
    avoid_traits_fully_covered: bool = False,
) -> tuple[list[str], dict]:
    """Stage 2: mini-LLM avoid-compliance filter (P1.2).

    Sends *artist_names* and *avoid_traits* to STAGE2_MODEL (gpt-5.4-mini on
    cloud, main model on local) and returns the approved subset alongside a
    meta dict the caller can write to the eval log. The meta dict contains:

    - ``status``: ``"ok"`` (LLM call succeeded with valid JSON),
      ``"empty_response"`` (LLM returned empty / invalid JSON — fell back
      to passthrough), ``"error"`` (LLM call raised — fell back to
      passthrough), ``"skipped_empty_input"`` (no artists supplied),
      ``"skipped_no_avoid"`` (caller had no avoid traits),
      ``"skipped_no_overlap"`` (L1: Stage 1's avoid-tag filter already
      removed every candidate that matched an avoid trait, so the LLM
      check would be a no-op).
    - ``latency_s``: wall-clock for the LLM call (None on skipped paths).
    - ``usage``: provider usage dict, when supplied.
    - ``model``: which model was actually used.
    - ``prompt_chars``: total system+user prompt char count.

    Failure modes never break a generation run — on error, returns the
    full candidate list. Telemetry callers can see the failure via
    ``status != "ok"``.

    Cost: ~$0.0008 per call at gpt-5.4-mini rates (zero on skipped paths).

    L1 (2026-04-29): when the caller passes ``pool_avoid_overlap=0`` AND
    ``avoid_traits`` is non-empty, the LLM call is skipped — Stage 1's
    tag-based filter has already removed every candidate matching an
    avoid trait, making the LLM verification redundant. See lever L1 in
    `cost-speed-research.md`. Saves ~$6.40 per 1000 playlists.

    F3 (2026-05-01): the L1 skip is ALSO gated on
    ``avoid_traits_fully_covered=True``. For semantic prose like
    "American artists" / "80s production style" / "Songs that are not
    uplifting" the Stage-1 tokeniser produces zero corpus-resolved tags,
    so ``pool_avoid_overlap`` is trivially 0 even though the avoid
    traits were never actually enforced. Without this guard the skip
    fires precisely when the LLM check is the only remaining gate.
    """
    import time as _time

    if not artist_names:
        return [], {"status": "skipped_empty_input", "latency_s": None,
                    "usage": None, "model": get_stage2_model(),
                    "prompt_chars": 0}
    if not avoid_traits:
        return list(artist_names), {"status": "skipped_no_avoid",
                                    "latency_s": None, "usage": None,
                                    "model": get_stage2_model(),
                                    "prompt_chars": 0}
    # L1: Stage 1 already filtered out every candidate matching an avoid
    # tag — no LLM verification needed. We trust the caller's flag (it
    # comes from `retrieval.get_last_retrieval_meta()` which counts
    # surviving overlap by construction). F3: only safe when every
    # avoid prose entry was reducible to ≥1 corpus tag — otherwise the
    # zero-overlap signal is meaningless and the LLM is the only gate.
    if pool_avoid_overlap == 0 and avoid_traits_fully_covered:
        return list(artist_names), {"status": "skipped_no_overlap",
                                    "latency_s": None, "usage": None,
                                    "model": get_stage2_model(),
                                    "prompt_chars": 0}

    stage2_model = get_stage2_model()
    system_prompt = load_text_file(AVOID_CHECK_SYSTEM_FILE)
    avoid_str = "\n".join(f"- {t}" for t in avoid_traits[:20])
    artists_str = "\n".join(
        f"{i + 1}. {name}" for i, name in enumerate(artist_names)
    )
    user_message = f"AVOID TRAITS:\n{avoid_str}\n\nARTISTS:\n{artists_str}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    prompt_chars = sum(len(m.get("content", "")) for m in messages)

    meta: dict = {"status": "ok", "latency_s": None, "usage": None,
                  "model": stage2_model, "prompt_chars": prompt_chars}

    try:
        t0 = _time.monotonic()
        response = chat_completions_create(
            model=stage2_model,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        meta["latency_s"] = _time.monotonic() - t0
        if isinstance(response, dict):
            meta["usage"] = response.get("usage")
        raw = extract_chat_content(response)
        # F9 (2026-05-01): capture Stage 2 prompt + raw response so a
        # diagnosis can answer "why did Stage 2 approve / reject artist
        # X?" without re-running the LLM call.
        try:
            from core.src import trace
            if trace.is_active():
                trace.record("stage2_prompt", {
                    "model": stage2_model,
                    "system": system_prompt,
                    "user": user_message,
                    "candidates_in": list(artist_names),
                    "avoid_traits": list(avoid_traits),
                })
                trace.record("stage2_response", {
                    "raw": raw,
                    "latency_s": meta.get("latency_s"),
                    "usage": meta.get("usage"),
                })
                # E1 (2026-05-06): per-stage rollup. Latency was just
                # measured around the LLM call; usage carries token
                # counts. Record both even if `usage` is missing — the
                # call still ate wall-clock.
                _u = meta.get("usage") or {}
                trace.stage_metrics_record(
                    trace.STAGE_STAGE2_AVOID,
                    duration_s=float(meta.get("latency_s") or 0.0),
                    tokens_in=_u.get("prompt_tokens"),
                    tokens_out=_u.get("completion_tokens"),
                )
        except Exception as _trace_exc:  # pragma: no cover
            logger.debug("trace capture (stage2) failed: %s", _trace_exc)
        data = json.loads(strip_code_fences(raw))
        approved = data.get("approved", [])
        if isinstance(approved, list):
            valid_lower = {n.lower().strip() for n in artist_names}
            filtered = [
                n for n in approved
                if isinstance(n, str) and n.lower().strip() in valid_lower
            ]
            return filtered, meta
        meta["status"] = "empty_response"
    except Exception as exc:
        logger.warning("check_avoid_compliance failed (%s) — using all candidates", exc)
        meta["status"] = "error"

    return list(artist_names), meta


def _format_approved_artists_block(
    approved_artist_names: list[str],
    approved_top_tracks: dict | None,
    max_tracks_per_artist: int = 5,
) -> str:
    """Render the APPROVED_ARTISTS section of the Stage 3 user prompt.

    Without overlay data, lines are bare names: ``- {name}``.

    With overlay data, lines carry an indented ``known:`` listing of up
    to *max_tracks_per_artist* real released tracks per artist. This is
    the in-context track-level grounding that prevents the LLM from
    confabulating titles for obscure artists. The model is explicitly
    told (in the system prompt) it MAY pick from the listed tracks OR
    another real released track by the same artist — preserving deep-cut
    discovery while eliminating the bare-name guessing regime.

    Artists with no overlay entry get a marker line so the model knows
    grounding is unavailable for them and the anti-confab clause applies.
    """
    overlay = approved_top_tracks or {}
    lines: list[str] = []
    for name in approved_artist_names:
        lines.append(f"- {name}")
        key = (name or "").lower().strip()
        tracks = overlay.get(key) or []
        tracks = [t for t in tracks if isinstance(t, str) and t.strip()][:max_tracks_per_artist]
        if tracks:
            quoted = ", ".join(f'"{t}"' for t in tracks)
            lines.append(f"    known: {quoted}")
        elif overlay:
            # Overlay is in use but we have no entry for this artist — be
            # explicit so the model invokes the anti-confab clause.
            lines.append("    known: (no track examples available — only suggest if you recall a real release)")
    return "\n".join(lines)


def select_tracks(
    approved_artist_names: list[str],
    taste_summary: str,
    batch_size: int,
    profile: dict,
    *,
    accepted_tracks=None,
    recently_filtered_tracks=None,
    new_artist_percentage: int = 30,
    batch_num: int = 0,
    audio_filters=None,
    emerging_only: bool = False,
    temperature: float = 0.7,
    approved_top_tracks: dict | None = None,
) -> tuple[dict, dict]:
    """Stage 3: track selection from pre-approved artists (P1.3).

    Much smaller prompt than build_messages — no deny list, no full profile
    JSON, no RAG pool. Only the approved artist list and a compact taste
    summary reach the model.

    *approved_top_tracks* is an optional ``{artist_name_lower: [track_titles]}``
    map sourced from the corpus / runtime overlay. When present, each
    artist's APPROVED_ARTISTS bullet line is followed by an indented
    ``known: "t1", "t2", ...`` listing of up to 5 real released tracks.
    This is the load-bearing track-level grounding signal that prevents
    confabulation when the model has weak parametric recall for obscure
    artists (root cause of the 2026-04-27 hallucination regression).

    Returns ``(result, meta)`` where ``meta = {"usage": …, "latency_s": …}``.
    Same result shape as call_gpt so all downstream code (filter_duplicate_
    suggestions, update_profile) works unchanged.
    """
    import time as _time

    # Stage 3 is gated to non-emerging runs in app.py; the over-request
    # buffer is the only one reachable here. emerging_only is still threaded
    # through so the function stays reusable if/when staged emerging support
    # lands.
    # L11 (2026-04-29): buffer reduced from hardcoded +5 to STAGE3_OVER_REQUEST
    # (config.py default = 2) — sweep showed Spotify-found = 100% on 58/60
    # rows, the old +5 was tuned for a regime that no longer exists.
    effective_batch_size = batch_size + STAGE3_OVER_REQUEST
    min_new_artists = math.ceil(effective_batch_size * new_artist_percentage / 100)

    gpt_language = get_gpt_language()

    prefs = (profile or {}).get("preferences", {}) if isinstance(profile, dict) else {}
    must_have_n = len((prefs.get("must_have") or []))
    soft_n = len((prefs.get("soft_preferences") or []))
    profile_facets = must_have_n + soft_n
    if profile_facets >= 5:
        rationale_count = "4"
    elif profile_facets >= 2:
        rationale_count = "3"
    else:
        rationale_count = "2"

    system_prompt = load_text_file(TRACK_SELECT_SYSTEM_FILE)
    # Phase 2.5 (2026-04-27): swap to slim local variant for Ollama /
    # LM Studio. Cloud providers (OpenAI, Groq, OpenRouter) keep the
    # full prompt with the 5-field reasoning block.
    try:
        from config import LOCAL_PRESETS, get_llm_provider_preset
        if get_llm_provider_preset() in LOCAL_PRESETS and TRACK_SELECT_SYSTEM_FILE_LOCAL.exists():
            system_prompt = load_text_file(TRACK_SELECT_SYSTEM_FILE_LOCAL)
            logger.info("[Stage 3] using slim local-LLM prompt variant "
                        "(provider=%s)", get_llm_provider_preset())
    except Exception as _exc:  # pragma: no cover
        logger.debug("local-prompt-variant lookup failed (%s) — using cloud variant", _exc)
    # L5 (2026-05-08): resolve the Stage 3 model once per call so the
    # validation block + the chat completion + the trace + the prompt log
    # all reference the same model. ``profile`` is the input the resolver
    # uses for "auto" mode — feedback-aware downgrade/upgrade decision.
    stage3_model = _resolve_stage3_model(profile)
    # Phase 2.5 (2026-04-27): {validation_block} moved out of the system
    # prompt into a per-request prepend on the user message. The validation
    # block is per-request data (model-specific verification reminder) and
    # keeping it in the system prompt broke OpenAI's prompt-prefix caching
    # (50 % discount on the cached prefix). System prompt is now invariant
    # across all requests for a given (model, language) pair.
    validation_block = _get_validation_block(stage3_model)
    system_prompt = system_prompt.replace("{batch_size}", str(effective_batch_size))
    system_prompt = system_prompt.replace("{min_new_artists}", str(min_new_artists))
    system_prompt = system_prompt.replace("{gpt_language}", gpt_language)
    system_prompt = system_prompt.replace("{rationale_count}", rationale_count)

    if emerging_only:
        emerging_constraint = (
            "\n7. ONLY suggest tracks by artists whose debut release is within the last 6 months."
            " Prefer unknown, underground, or recently debuted artists."
        )
        system_prompt += emerging_constraint

    user_template = load_text_file(TRACK_SELECT_USER_FILE)
    artists_str = _format_approved_artists_block(
        approved_artist_names, approved_top_tracks
    )

    feedback_summary = build_feedback_summary(profile)
    audio_filters_block = _format_audio_filters(audio_filters or {})

    # L8 (2026-04-29): when the user has no liked/disliked feedback yet,
    # `feedback_summary` is "" and the `{recent_feedback}` placeholder leaves
    # an empty line in the rendered prompt. Strip the entire placeholder line
    # (including its trailing newline) in that case so we don't pay the input
    # token + a blank-line attention distraction. Same treatment for an empty
    # audio_filters_block — both placeholders sit on dedicated lines in
    # `prompts/track_select_user.txt`.
    _user_template_for_render = user_template
    if not feedback_summary:
        _user_template_for_render = _user_template_for_render.replace(
            "{recent_feedback}\n", "", 1
        )
    if not audio_filters_block:
        _user_template_for_render = _user_template_for_render.replace(
            "{audio_filters_block}\n", "", 1
        )

    user_message = _user_template_for_render.format(
        approved_artists=artists_str,
        taste_summary=taste_summary,
        batch_size=effective_batch_size,
        min_new_artists=min_new_artists,
        recent_feedback=feedback_summary,
        audio_filters_block=audio_filters_block,
    )

    # Prepend validation_block (model-specific, per-request) to the user
    # message — moved out of the system prompt to preserve prefix caching.
    if validation_block and validation_block.strip():
        user_message = f"{validation_block}\n\n{user_message}"

    if recently_filtered_tracks:
        retry_list = "\n".join(
            f"- {t.get('artist', '?')} — {t.get('track', '')}"
            for t in recently_filtered_tracks[:20]
        )
        user_message += f"\n\nDo NOT suggest these tracks again (already filtered):\n{retry_list}"

    accepted_block = ""
    if accepted_tracks:
        listing = "\n".join(
            f"- {t['artist']} - {t['track']}" for t in accepted_tracks
        )
        accepted_block = (
            f"\n\nI already accepted these {len(accepted_tracks)} tracks"
            f" — do NOT suggest them again:\n{listing}"
            f"\n\nI need {effective_batch_size} MORE tracks. Still return"
            " the result in the same JSON schema."
        )
        user_message += accepted_block

    _history_tracks = (
        (profile or {}).get("history", {}).get("suggested_tracks", [])
        if isinstance(profile, dict) else []
    )
    if len(_history_tracks) > 50:
        diversity_hints = [
            "Focus on artists from the 1970s-1980s that match the profile.",
            "Explore Japanese, Korean, or Scandinavian artists matching the profile.",
            "Look for artists who released their first album after 2020.",
            "Consider solo projects or side projects of artists similar to the anchors.",
            "Explore soundtrack and compilation albums for hidden gems.",
        ]
        # F7 (2026-05-01): drop hints that contradict the user's avoid
        # prose. See _filter_diversity_hints for the conflict rules.
        _avoid_traits = prefs.get("avoid")
        if isinstance(_avoid_traits, str):
            _avoid_traits = [_avoid_traits]
        diversity_hints = _filter_diversity_hints(diversity_hints, _avoid_traits)
        if diversity_hints:
            hint = diversity_hints[batch_num % len(diversity_hints)]
            user_message += f"\n\nDiversity guidance: {hint}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Capture prompt components for the eval log (pool = approved artists block).
    global _LAST_PROMPT_COMPONENTS
    _LAST_PROMPT_COMPONENTS = {
        "system": len(system_prompt),
        "profile": 0,
        "deny_set": 0,
        "feedback": len(feedback_summary),
        "audio_filters": len(audio_filters_block),
        "pool": len(artists_str),
        "accepted": len(accepted_block),
        "diversity_hint": 0,
        "user_total": len(user_message),
    }

    def _empty() -> dict:
        return {
            "playlist": [], "new_artists": [],
            "profile_updates": {"suggested_artists": [], "suggested_tracks": []},
        }

    # C4 (2026-05-10) — stable cache-routing hint per (model, language,
    # emerging_only). System prompt is invariant under that triple so the
    # cache router consistently sends batches in the same /api/run to the
    # same host. Without this, OpenAI's load balancer sprays requests
    # across hosts and the auto-cache hits sporadically (B1 2026-05-08
    # showed 71-76 % hit rate when it landed, 0 % otherwise).
    _stage3_cache_key = f"sv-stage3:{stage3_model}:{gpt_language}:{int(bool(emerging_only))}"

    _t0 = _time.monotonic()
    response = chat_completions_create(
        model=stage3_model,
        messages=messages,
        temperature=temperature,
        # OPEN-3 (2026-04-28): json_schema variant evaluated and reverted —
        # measured +80% cost on gpt-5.4, +89% on gpt-5.4-mini, with a
        # quality regression on must-have cite. Stage 3 uses plain json_object.
        response_format={"type": "json_object"},
        prompt_cache_key=_stage3_cache_key,
    )
    latency_s = _time.monotonic() - _t0

    raw_content = extract_chat_content(response)
    debug_log("Stage 3 Track Selection", messages, raw_content)

    # F9 (2026-05-01): per-batch Stage 3 capture. Multiple batches
    # accumulate via trace.append so a diagnosis can walk batch-by-batch.
    # Tier 1 (2026-05-10): system_fingerprint + stage3_mode added so
    # post-mortems can detect (a) silent OpenAI model rolls and
    # (b) the L5 selector's resolved-mode at call time.
    _s3_system_fp = (response or {}).get("system_fingerprint") if isinstance(response, dict) else None
    try:
        from core.src import trace
        if trace.is_active():
            _s3_usage = (response or {}).get("usage") if isinstance(response, dict) else None
            trace.append("stage3_batches", {
                "batch_num": batch_num,
                "model": stage3_model,
                "stage3_mode": get_stage3_mode(),
                "system_fingerprint": _s3_system_fp,
                "system": system_prompt,
                "user": user_message,
                "approved_artists": list(approved_artist_names),
                "raw_response": raw_content,
                "latency_s": latency_s,
                "usage": _s3_usage,
                "temperature": temperature,
                "effective_batch_size": effective_batch_size,
            })
            # E1 (2026-05-06): per-stage rollup. Stage 3 fires once per
            # batch, so each call accumulates here — duration/tokens
            # sum across all batches for a single playlist generation.
            _u = _s3_usage or {}
            trace.stage_metrics_record(
                trace.STAGE_STAGE3_SELECT,
                duration_s=float(latency_s or 0.0),
                tokens_in=_u.get("prompt_tokens"),
                tokens_out=_u.get("completion_tokens"),
            )
    except Exception as _trace_exc:  # pragma: no cover
        logger.debug("trace capture (stage3) failed: %s", _trace_exc)

    # ── Diagnostic logging (2026-04-27, Phase 1 quality investigation) ──
    # The full prompt + raw response contain user-tied data (taste
    # summary, anchor artists, recent feedback). Keep them off the INFO
    # channel so they don't end up in shipped log files / bug reports;
    # gate behind debug mode (2026-04-28).
    logger.info(
        "[Stage 3 prompt] system=%d chars, user=%d chars, model=%s",
        len(system_prompt), len(user_message), stage3_model,
    )
    if get_debug_mode():
        debug_log("Stage 3 user message", [], user_message)
        debug_log("Stage 3 raw response", [], raw_content)

    usage = response.get("usage") if isinstance(response, dict) else None
    # Tier 1 (2026-05-10): same diagnostic fields as call_gpt's meta.
    # _s3_system_fp captured above. Stage 3's prompt-prefix is the
    # invariant-per-call portion C4's `prompt_cache_key` hints on, so
    # tracking the hash gives a per-batch view of cache eligibility.
    meta = {
        "usage": usage,
        "latency_s": latency_s,
        "system_fingerprint": _s3_system_fp,
        "prompt_hashes": _hash_messages_for_audit(messages),
        "stage3_mode": get_stage3_mode(),
    }

    content = strip_code_fences(raw_content)
    if not content:
        logger.warning("Stage 3 returned empty response.")
        return _empty(), meta

    try:
        result = normalize_response(json.loads(content))
    except json.JSONDecodeError:
        logger.warning("Stage 3 JSON parse failed: %s", content[:200])
        result = _empty()

    # ── Surface the model's `reasoning` block at INFO level ──
    # The reasoning block (added 2026-04-27) is the diagnostic anchor —
    # it tells us how the model interpreted the seed, judged the
    # candidate pool, and decided what to omit / pick / reach outside
    # the pool for. Without this we can only observe that the playlist
    # is bad; with it we can pinpoint whether the failure is in
    # retrieval (wrong pool), prompt comprehension (model misread the
    # constraints), or knowledge (model has no tracks for these
    # obscure artists).
    reasoning = result.get("reasoning") if isinstance(result, dict) else None
    if reasoning and isinstance(reasoning, dict):
        for key in ("seed_interpretation", "pool_assessment",
                    "selection_strategy", "constraints_evaluated"):
            val = reasoning.get(key)
            if val:
                logger.info("[Stage 3 reasoning] %s: %s", key, val)
        omitted = reasoning.get("omitted_artists") or []
        if omitted:
            logger.info("[Stage 3 reasoning] omitted_artists (%d):", len(omitted))
            for entry in omitted:
                logger.info("    - %s", entry)

        # Phase 2.5 (2026-04-27): derive a structured "pool quality" flag
        # from the reasoning block. Surfaced via llm_meta so downstream
        # callers (eval harness, retry logic) can act on it without
        # parsing prose. Two signals trigger "pool_bad":
        #   1) omitted_artists ≥ 50 % of approved pool size
        #   2) pool_assessment text matches a "wrong genre / poor fit" pattern
        _approved_count = len(approved_artist_names) if approved_artist_names else 0
        _omitted_ratio = (len(omitted) / _approved_count) if _approved_count else 0.0
        _assessment_text = (reasoning.get("pool_assessment") or "").lower()
        _bad_pool_patterns = (
            "wrong genre", "wrong-genre", "poor fit", "very poor",
            "mostly wrong", "does not fit", "doesn't fit",
            "barely fits", "weak match", "weak fit", "mismatch",
        )
        _pool_bad = (
            _omitted_ratio >= 0.5
            or any(p in _assessment_text for p in _bad_pool_patterns)
        )
        if meta is not None and isinstance(meta, dict):
            meta["pool_quality"] = {
                "omitted_ratio": round(_omitted_ratio, 3),
                "approved_count": _approved_count,
                "omitted_count": len(omitted),
                "pool_bad": _pool_bad,
            }
        if _pool_bad:
            logger.warning(
                "[Stage 3 reasoning] POOL_BAD signal: omitted=%d/%d (%.0f%%), "
                "assessment matches bad-pool pattern. Caller may want to "
                "retry Stage 1 with a larger target_size.",
                len(omitted), _approved_count, _omitted_ratio * 100,
            )
    else:
        logger.warning("[Stage 3 reasoning] MISSING from response — model did "
                       "not follow the new schema. Raw start: %s",
                       (raw_content or "")[:200])

    return result, meta


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
    forbidden_artist_keys = collect_forbidden_artists(profile, normalizer=_normalize_key)

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

