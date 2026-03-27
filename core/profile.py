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
from datetime import datetime, timezone
from config import BASE_DIR, PROFILE_FILE, PROFILE_HISTORY_FILE, get_model
from core.utils import get_openai_client, strip_code_fences, debug_log

# Template and prompt paths are resolved from BASE_DIR (the project root)
# using pathlib. This means the app can run from any working directory
# without breaking file resolution.
TEMPLATE_FILE = BASE_DIR / "data" / "music_profile.json"
TRAINING_PROMPT_FILE = BASE_DIR / "prompts" / "profile_training_prompt.txt"


# ── Profile I/O ─────────────────────────────────────────────────────

def _load_template():
    """Load the empty profile template from the project's data/ directory."""
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_profile():
    """Create the personalized profile from the template if it doesn't exist."""
    if not PROFILE_FILE.exists():
        template = _load_template()
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)


def load_profile():
    """Load the personalized music profile from AppData."""
    ensure_profile()
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(profile):
    """Save the profile to AppData, keeping one history backup.

    Pattern: **Copy-on-write with single backup**. Before each save,
    the current file is copied to a `.history.json` sibling. This
    provides a simple undo mechanism. More complex alternatives
    (git-like versioning, append-only log) were considered unnecessary
    for a single-user app with infrequent writes.
    """
    # Back up the current file before overwriting
    if PROFILE_FILE.exists():
        shutil.copy2(str(PROFILE_FILE), str(PROFILE_HISTORY_FILE))
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


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

    *sections* is a dict with keys: core_description, must_have,
    soft_preferences, avoid — each a string (lines separated by newlines).

    Design choice: This function provides a **manual save path** that
    bypasses GPT entirely. Users can edit their profile without consuming
    API tokens. The AI training path (`train_profile`) is a separate
    opt-in action. This dual approach lets users choose between speed
    (manual) and intelligence (AI-assisted).

    Returns the updated profile dict.
    """
    profile = load_profile()

    profile["preferences"]["core_description"] = sections["core_description"]
    profile["preferences"]["must_have"] = [
        line.strip() for line in sections.get("must_have", "").splitlines() if line.strip()
    ]
    profile["preferences"]["soft_preferences"] = [
        line.strip() for line in sections.get("soft_preferences", "").splitlines() if line.strip()
    ]
    profile["preferences"]["avoid"] = [
        line.strip() for line in sections.get("avoid", "").splitlines() if line.strip()
    ]

    profile["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_profile(profile)
    return profile


# ── Training ─────────────────────────────────────────────────────────

def train_profile(sections):
    """Send the user's structured taste input to GPT and update the profile.

    *sections* is a dict with keys: core_description, must_have,
    soft_preferences, avoid — each a string (lines separated by newlines).

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
        system_prompt = f.read()

    # Build a structured user message so GPT knows what each section means
    parts = [
        "Here is my current music taste profile:\n\n"
        f"{json.dumps(profile, indent=2)}\n\n"
        "Here is my updated taste input, broken into sections:\n"
    ]

    parts.append(
        f"\n## CORE DESCRIPTION (required — the foundation of my sound):\n"
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

    client = get_openai_client()
    train_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    response = client.chat.completions.create(
        model=get_model(),
        messages=train_messages,
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content.strip()
    debug_log("Profile Training", train_messages, raw_content)

    content = strip_code_fences(raw_content)

    updated_profile = json.loads(content)

    # Safety: preserve history + feedback from the original (GPT might mangle them)
    for key in ("history", "feedback"):
        if key in profile:
            updated_profile[key] = profile[key]

    # Stamp the update time
    updated_profile["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_profile(updated_profile)
    return updated_profile

