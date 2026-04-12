"""Centralised music profile management.

Technologies & patterns used:
- **JSON as a document store**: The profile is a single JSON file acting
  as a lightweight NoSQL-like document. This avoids the overhead of a
  database engine (SQLite, PostgreSQL) for what is fundamentally a
  single-document, single-user dataset. Trade-off: no concurrent writes,
  no transactions — acceptable for a desktop/single-user app.
- **shutil.copy2**: Used for history backups, preserving file metadata
  (timestamps). This gives a simple one-level undo without a full
  version-control or journaling system.
- **pathlib.Path**: All file paths use `pathlib` instead of `os.path`
  string manipulation. This gives type-safe, cross-platform path handling
  with a fluent API (`.exists()`, `.parent.mkdir()`, etc.).
- **Separation of I/O and business logic**: Profile CRUD is isolated here
  so that `suggestions.py` and `feedback.py` never touch the filesystem
  directly — they call `load_profile()` / `save_profile()`.
- **GPT-powered profile training**: The `train_profile()` function sends
  structured user input to GPT with `response_format={"type": "json_object"}`
  (structured outputs), ensuring the AI returns parseable JSON rather than
  free-form text.

The active profile lives in %LOCALAPPDATA%\\spotyvibe\\ (same
directory as .credentials).  A single history file is kept so the user
can later revert to the previous version.
"""

import json
import shutil
import threading
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config import (
    BASE_DIR, PROFILES_DIR, MAX_PROFILE_NAME_LEN,
    MAX_CORE_DESCRIPTION_LEN, MAX_PROFILE_SECTION_LEN,
    get_model, get_gpt_language,
    get_active_profile_id, set_active_profile_id,
    get_active_profile_path, get_active_history_path,
    validate_profile_id,
)
from .utils import debug_log, strip_code_fences, sanitize_profile, sanitize_text
from .openai_http import chat_completions_create, extract_chat_content


# Template and prompt paths are resolved from BASE_DIR (the project root)
# using pathlib. This means the app can run from any working directory
# without breaking file resolution.
TEMPLATE_FILE = BASE_DIR / "data" / "music_profile.json"
TRAINING_PROMPT_FILE = BASE_DIR / "prompts" / "profile_training_prompt.txt"

# Guards all read-modify-write cycles on profile files so concurrent
# requests (e.g. feedback during generation) cannot silently overwrite
# each other's changes.
_profile_lock = threading.Lock()


# ── Helpers ──────────────────────────────────────────────────────────

def _require_active_profile():
    """Return (profile_path, history_path) for the active profile.

    Raises ValueError if no profile is active.
    """
    profile_path = get_active_profile_path()
    history_path = get_active_history_path()
    if not profile_path:
        raise ValueError("No active profile. Create or select a profile first.")
    return profile_path, history_path


# ── Profile I/O ─────────────────────────────────────────────────────

def _load_template():
    """Load the empty profile template from the project's data/ directory."""
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_profile():
    """Ensure the profiles directory exists and the active profile file is present.

    If no active profile is set, does nothing (the UI must create one first).
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = get_active_profile_path()
    if profile_path and not profile_path.exists():
        template = _load_template()
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)


def load_profile():
    """Load the active music profile from the profiles directory.

    Thread-safe: acquires _profile_lock internally.
    Raises ValueError if no active profile is set.
    """
    profile_path, _ = _require_active_profile()
    with _profile_lock:
        ensure_profile()
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)


def save_profile(profile):
    """Save the active profile, keeping one history backup.

    Thread-safe: acquires _profile_lock internally.
    Raises ValueError if no active profile is set.
    """
    profile_path, history_path = _require_active_profile()
    with _profile_lock:
        if profile_path.exists():
            shutil.copy2(str(profile_path), str(history_path))
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)


@contextmanager
def profile_transaction():
    """Hold _profile_lock for an entire read-modify-write cycle.

    Prevents lost updates when load→modify→save would otherwise release
    the lock between load and save.

    Usage::

        with profile_transaction() as (load_fn, save_fn):
            data = load_fn()
            data["field"] = "value"
            save_fn(data)
    """
    profile_path, history_path = _require_active_profile()

    with _profile_lock:
        def _load():
            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            if not profile_path.exists():
                template = _load_template()
                with open(profile_path, "w", encoding="utf-8") as f:
                    json.dump(template, f, indent=2)
            with open(profile_path, "r", encoding="utf-8") as f:
                return json.load(f)

        def _save(profile):
            if profile_path.exists():
                shutil.copy2(str(profile_path), str(history_path))
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)

        yield _load, _save


def swap_profile_with_history():
    """Swap the active profile with its one-level history backup.

    Thread-safe: acquires _profile_lock for the entire swap sequence.

    Raises:
        ValueError: if no active profile or the history file does not exist.

    Returns:
        The new active profile dict (loaded from disk after the swap).
    """
    profile_path, history_path = _require_active_profile()

    with _profile_lock:
        # Ensure the profile file exists (inline, no separate lock acquisition)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        if not profile_path.exists():
            template = _load_template()
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2)

        if not history_path.exists():
            raise ValueError("No history profile exists yet.")

        profile_path.parent.mkdir(parents=True, exist_ok=True)

        tmp = profile_path.parent / (profile_path.name + ".swap.tmp")
        if tmp.exists():
            tmp.unlink()

        # Atomic-ish swap via renames.
        profile_path.rename(tmp)
        history_path.rename(profile_path)
        tmp.rename(history_path)

        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)


def _deep_merge(dst, src):
    """Recursively merge *src* onto *dst*.

    Used to ensure imported profiles preserve any missing keys from the
    template without requiring the imported JSON to be perfectly complete.

    Rules:
    - dict + dict → deep merge
    - otherwise  → src replaces dst
    """
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return src

    for key, value in src.items():
        if key in dst and isinstance(dst.get(key), dict) and isinstance(value, dict):
            dst[key] = _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def export_profile_dict():
    """Return the current active profile as a Python dict."""
    return load_profile()


_ALLOWED_PROFILE_KEYS = {
    "name", "last_updated", "meta", "preferences", "artists",
    "history", "feedback", "taste_rules",
}

# Per-field length limits to prevent runaway prompts
_MAX_STR_LEN = 5000
_MAX_LIST_ITEMS = 100
_MAX_LIST_ITEM_STR_LEN = 500


def _validate_str_field(value, name):
    if not isinstance(value, str):
        raise ValueError(f"'{name}' must be a string.")
    if len(value) > _MAX_STR_LEN:
        raise ValueError(f"'{name}' exceeds maximum length of {_MAX_STR_LEN} characters.")


def _validate_str_list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"'{name}' must be a list.")
    if len(value) > _MAX_LIST_ITEMS:
        raise ValueError(f"'{name}' exceeds maximum of {_MAX_LIST_ITEMS} items.")
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"'{name}[{i}]' must be a string.")
        if len(item) > _MAX_LIST_ITEM_STR_LEN:
            raise ValueError(f"'{name}[{i}]' exceeds maximum length.")


def validate_profile_schema(data):
    """Validate an imported profile against the expected schema.

    - Strips unknown top-level keys (graceful degradation).
    - Validates types and length limits for all known fields.
    - Raises ValueError with a descriptive message on failure.
    """
    if not isinstance(data, dict):
        raise ValueError("Profile must be a JSON object.")

    # Strip unknown top-level keys
    for key in list(data.keys()):
        if key not in _ALLOWED_PROFILE_KEYS:
            del data[key]

    # meta
    if "meta" in data:
        if not isinstance(data["meta"], dict):
            raise ValueError("'meta' must be an object.")
        if "goal" in data["meta"]:
            _validate_str_field(data["meta"]["goal"], "meta.goal")

    # preferences
    if "preferences" in data:
        prefs = data["preferences"]
        if not isinstance(prefs, dict):
            raise ValueError("'preferences' must be an object.")
        for field in ("core_description", "must_have", "soft_preferences", "avoid"):
            if field in prefs:
                if field == "core_description":
                    _validate_str_field(prefs[field], f"preferences.{field}")
                else:
                    _validate_str_list(prefs[field], f"preferences.{field}")

    # artists
    if "artists" in data:
        artists = data["artists"]
        if not isinstance(artists, dict):
            raise ValueError("'artists' must be an object.")
        if "confirmed" in artists:
            _validate_str_list(artists["confirmed"], "artists.confirmed")
        for list_of_dicts in ("moderate", "rejected"):
            if list_of_dicts in artists:
                val = artists[list_of_dicts]
                if not isinstance(val, list):
                    raise ValueError(f"'artists.{list_of_dicts}' must be a list.")
                if len(val) > _MAX_LIST_ITEMS:
                    raise ValueError(f"'artists.{list_of_dicts}' exceeds maximum of {_MAX_LIST_ITEMS} items.")

    # history / feedback — allow but cap lists
    for section in ("history", "feedback"):
        if section in data:
            sec = data[section]
            if not isinstance(sec, dict):
                raise ValueError(f"'{section}' must be an object.")
            for key, val in sec.items():
                if isinstance(val, list) and len(val) > _MAX_LIST_ITEMS * 10:
                    sec[key] = val[-(  _MAX_LIST_ITEMS * 10):]

    # taste_rules
    if "taste_rules" in data:
        tr = data["taste_rules"]
        if not isinstance(tr, dict):
            raise ValueError("'taste_rules' must be an object.")
        if "primary_driver" in tr:
            _validate_str_field(tr["primary_driver"], "taste_rules.primary_driver")
        if "dealbreaker_priority" in tr:
            _validate_str_list(tr["dealbreaker_priority"], "taste_rules.dealbreaker_priority")


def import_profile_dict(imported_profile):
    """Replace the current profile with *imported_profile*.

    This performs a template-based merge so missing keys are filled from
    the default template.

    IMPORTANT: This replaces the full personalized_music_profile.json.
    The existing file is moved to personalized_music_profile.history.json
    by the standard save_profile() backup mechanism.

    Returns the imported (normalized) profile dict.
    """
    if not isinstance(imported_profile, dict):
        raise ValueError("Imported profile must be a JSON object.")

    # Sanitise all string values (remove null bytes, control chars, etc.)
    sanitized = sanitize_profile(imported_profile)
    if not isinstance(sanitized, dict):
        raise ValueError("Imported profile must be a JSON object.")
    imported_profile = sanitized

    # Validate schema — strips unknown keys, checks types and lengths
    validate_profile_schema(imported_profile)

    template = _load_template()
    merged = _deep_merge(template, imported_profile)

    # Structural sanity checks so other modules don't crash.
    if not isinstance(merged.get("preferences"), dict):
        raise ValueError("Imported profile is missing a valid 'preferences' object.")
    if not isinstance(merged.get("history"), dict):
        raise ValueError("Imported profile is missing a valid 'history' object.")
    if not isinstance(merged.get("feedback"), dict):
        raise ValueError("Imported profile is missing a valid 'feedback' object.")

    save_profile(merged)
    return merged


# ── Status ───────────────────────────────────────────────────────────


def is_profile_trained():
    """True if the profile has been trained at least once (has a timestamp)."""
    return bool(load_profile().get("last_updated"))


def get_profile_status():
    """Return a status dict for the UI."""
    profile = load_profile()
    return {
        "trained": bool(profile.get("last_updated")),
        "last_updated": profile.get("last_updated"),
    }


# ── Manual save ──────────────────────────────────────────────────────

def save_profile_sections(sections):
    """Update the profile preferences directly from user input (no AI).

    *sections* is a dict with keys: vibe_description, core_description,
    must_have, soft_preferences, avoid — each a string (lines separated
    by newlines).

    Design choice: This function provides a **manual save path** that
    bypasses GPT entirely. Users can edit their profile without consuming
    API tokens. The AI training path (`train_profile`) is a separate
    opt-in action. This dual approach lets users choose between speed
    (manual) and intelligence (AI-assisted).

    Returns the updated profile dict.
    """
    profile = load_profile()

    profile["preferences"]["vibe_description"] = sanitize_text(
        sections.get("vibe_description", "")
    )[:MAX_PROFILE_SECTION_LEN]
    profile["preferences"]["core_description"] = sanitize_text(
        sections.get("core_description", "")
    )[:MAX_CORE_DESCRIPTION_LEN]
    profile["preferences"]["must_have"] = [
        sanitize_text(line.strip())[:MAX_PROFILE_SECTION_LEN]
        for line in sections.get("must_have", "").splitlines()
        if line.strip()
    ]
    profile["preferences"]["soft_preferences"] = [
        sanitize_text(line.strip())[:MAX_PROFILE_SECTION_LEN]
        for line in sections.get("soft_preferences", "").splitlines()
        if line.strip()
    ]
    profile["preferences"]["avoid"] = [
        sanitize_text(line.strip())[:MAX_PROFILE_SECTION_LEN]
        for line in sections.get("avoid", "").splitlines()
        if line.strip()
    ]

    profile["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_profile(profile)
    return profile


# ── Training ─────────────────────────────────────────────────────────

def train_profile(sections):
    """Send the user's structured taste input to GPT and update the profile.

    *sections* is a dict with keys: vibe_description, core_description,
    must_have, soft_preferences, avoid — each a string (lines separated
    by newlines).

    How it works:
    1. Loads the current profile and the training system prompt from disk.
    2. Constructs a user message with the existing profile JSON and the
       new user input, structured into labelled sections so GPT can parse
       each one with the correct semantics.
    3. Calls GPT with `response_format={"type": "json_object"}` — this
       enables OpenAI's **Structured Outputs** mode, which constrains the
       model to return valid JSON. This prevents formatting issues that
       would otherwise require complex parsing/retry logic.
    4. Merges the AI-refined profile with the original's history/feedback
       sections (safety net — GPT might accidentally modify them).
    5. Stamps the update time and saves.

    Temperature 0.3 is used (low creativity) because profile training
    should faithfully represent user input, not hallucinate preferences.

    Returns the updated profile dict.
    """
    profile = load_profile()

    with open(TRAINING_PROMPT_FILE, "r", encoding="utf-8") as f:
        system_prompt = f.read().replace("{gpt_language}", get_gpt_language())

    # Build a structured user message so GPT knows what each section means
    parts = [
        "Here is my current music taste profile:\n\n"
        f"{json.dumps(profile, indent=2)}\n\n"
        "Here is my updated taste input, broken into sections:\n"
    ]

    if sections.get("vibe_description"):
        parts.append(
            f"\n## VIBE DESCRIPTION (free-form natural language — the user describes "
            f"what they want conversationally; CLASSIFY each statement into the "
            f"correct profile section: must_have, avoid, soft_preferences, or "
            f"core_description, following the VIBE DESCRIPTION CLASSIFICATION "
            f"rules in your system prompt):\n"
            f"{sections['vibe_description']}\n"
        )

    if sections.get("core_description"):
        parts.append(
            f"\n## CORE DESCRIPTION (the foundation of my sound):\n"
            f"{sections['core_description']}\n"
        )

    if sections.get("must_have"):
        parts.append(
            f"\n## MUST HAVE (non-negotiable hard requirements — every suggestion must satisfy ALL of these):\n"
            f"{sections['must_have']}\n"
        )

    if sections.get("soft_preferences"):
        parts.append(
            f"\n## SOFT PREFERENCES (nice-to-have traits, not required):\n"
            f"{sections['soft_preferences']}\n"
        )

    if sections.get("avoid"):
        parts.append(
            f"\n## AVOID (absolute disqualifiers — any match removes a track immediately):\n"
            f"{sections['avoid']}\n"
        )

    parts.append(
        "\nUpdate the profile based on my input. Merge with existing data — "
        "do not remove anything from the \"history\" or \"feedback\" sections.\n"
        "Return ONLY the updated JSON object."
    )

    user_message = "".join(parts)

    train_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = chat_completions_create(
        model=get_model(),
        messages=train_messages,
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw_content = extract_chat_content(response)
    if not raw_content:
        raise ValueError(
            "AI returned an empty response while training the profile. "
            "Please try again."
        )

    debug_log("Profile Training", train_messages, raw_content)


    content = strip_code_fences(raw_content)

    try:
        gpt_profile = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(
            "AI returned an invalid response while training the profile. "
            "Please try again."
        )

    # Start from the template to guarantee all required keys survive,
    # then deep-merge the GPT output on top (shallow .update() would lose
    # nested template defaults if GPT omits sub-keys).
    updated_profile = _load_template()
    updated_profile = _deep_merge(updated_profile, gpt_profile)

    # Safety: preserve history + feedback from the original (GPT might mangle them)
    for key in ("history", "feedback"):
        if key in profile:
            updated_profile[key] = profile[key]

    # Clear vibe_description — it was a one-time instruction that GPT has now
    # incorporated into the structured profile sections.
    updated_profile.setdefault("preferences", {})["vibe_description"] = ""

    # Stamp the update time
    updated_profile["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_profile(updated_profile)
    return updated_profile


# ── Multi-profile management ────────────────────────────────────────

def list_profiles():
    """Return a list of all profiles: [{id, name, trained, last_updated}].

    Scans the profiles/ directory for *.json files (excluding *.history.json).
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        if path.name.endswith(".history.json"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name", "")
            if not name:
                continue
            profiles.append({
                "id": path.stem,
                "name": name,
                "trained": bool(data.get("last_updated")),
                "last_updated": data.get("last_updated"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return profiles


def create_profile(name):
    """Create a new profile with the given display name.

    Returns {"id": "<uuid>", "name": "<name>"}.
    Raises ValueError on invalid name or duplicate.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name cannot be empty.")
    if len(name) > MAX_PROFILE_NAME_LEN:
        raise ValueError(f"Profile name too long (max {MAX_PROFILE_NAME_LEN} characters).")

    # Check for duplicate names (case-insensitive)
    existing = list_profiles()
    for p in existing:
        if p["name"].lower() == name.lower():
            raise ValueError(f"A profile named \"{name}\" already exists.")

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_id = str(_uuid.uuid4())
    profile_path = PROFILES_DIR / f"{profile_id}.json"

    template = _load_template()
    template["name"] = name
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)

    # Auto-activate the new profile
    set_active_profile_id(profile_id)

    return {"id": profile_id, "name": name}


def delete_profile(profile_id):
    """Delete a profile by ID.

    Raises ValueError if the profile doesn't exist or ID is invalid.
    Removes both the profile and its history file.
    If the deleted profile was active, clears the active pointer.
    """
    if not profile_id:
        raise ValueError("Profile ID is required.")
    validate_profile_id(profile_id)

    profile_path = PROFILES_DIR / f"{profile_id}.json"
    history_path = PROFILES_DIR / f"{profile_id}.history.json"

    if not profile_path.exists():
        raise ValueError("Profile not found.")

    profile_path.unlink()
    if history_path.exists():
        history_path.unlink()

    # If this was the active profile, clear the pointer
    if get_active_profile_id() == profile_id:
        set_active_profile_id("")


def activate_profile(profile_id):
    """Set a profile as the active one.

    Raises ValueError if the profile doesn't exist or ID is invalid.
    """
    if not profile_id:
        raise ValueError("Profile ID is required.")
    validate_profile_id(profile_id)

    profile_path = PROFILES_DIR / f"{profile_id}.json"
    if not profile_path.exists():
        raise ValueError("Profile not found.")

    set_active_profile_id(profile_id)


# ── Profile seeding from playlists (Wave 3) ─────────────────────────

SEED_PROMPT_FILE = BASE_DIR / "prompts" / "profile_seed_from_playlist.txt"


def draft_profile_from_playlist(summary: dict) -> dict:
    """Draft a taste profile from a Spotify playlist summary via GPT.

    Args:
        summary: dict with keys: name, track_count, top_artists, top_genres,
                 energy, valence, tempo, moods.

    Returns a profile dict with: core_description, must_have, soft_preferences,
    avoid (always []), vibe_description (always "").
    """
    prompt_template = SEED_PROMPT_FILE.read_text(encoding="utf-8")

    top_artists_list = ", ".join(summary.get("top_artists", [])[:5]) or "various"
    top_genres_list = ", ".join(summary.get("top_genres", [])[:5]) or "mixed"
    energy = summary.get("energy", "unknown")
    valence = summary.get("valence", "unknown")
    tempo = summary.get("tempo", "unknown")
    moods = ", ".join(summary.get("moods", [])) or "mixed"

    prompt = prompt_template.format(
        name=summary.get("name", "Untitled"),
        count=summary.get("track_count", 0),
        top_artists_list=top_artists_list,
        top_genres_list=top_genres_list,
        energy=energy,
        valence=valence,
        tempo=tempo,
        moods=moods,
    )

    from .openai_http import chat_completions_create, extract_chat_content
    from .utils import strip_code_fences

    response = chat_completions_create(
        model=get_model(),
        messages=[
            {"role": "system", "content": "You draft music taste profiles from playlist data. Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    raw = extract_chat_content(response)
    content = strip_code_fences(raw)

    import json as _json
    result = _json.loads(content)

    # Enforce shape constraints
    draft = {
        "core_description": str(result.get("core_description", ""))[:MAX_CORE_DESCRIPTION_LEN],
        "must_have": [str(x)[:MAX_PROFILE_SECTION_LEN] for x in (result.get("must_have") or [])[:3]],
        "soft_preferences": [str(x)[:MAX_PROFILE_SECTION_LEN] for x in (result.get("soft_preferences") or [])[:3]],
        "avoid": [],
        "vibe_description": str(result.get("vibe_description", "")),
    }
    return draft

