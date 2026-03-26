"""Centralised music profile management.

The active profile lives in %LOCALAPPDATA%\\spotyvibe\\ (same
directory as .credentials).  A single history file is kept so the user
can later revert to the previous version.
"""

import json
import shutil
from datetime import datetime, timezone
from config import BASE_DIR, PROFILE_FILE, PROFILE_HISTORY_FILE, get_model
from core.utils import get_openai_client, strip_code_fences, debug_log

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
    """Save the profile to AppData, keeping one history backup."""
    ensure_profile()
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


# ── Training ─────────────────────────────────────────────────────────

def train_profile(user_text):
    """Send the user's taste description to GPT and update the profile.

    Returns the updated profile dict.
    """
    profile = load_profile()

    with open(TRAINING_PROMPT_FILE, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    user_message = (
        "Here is my current music taste profile:\n\n"
        f"{json.dumps(profile, indent=2)}\n\n"
        "Here is what I want to tell you about my music taste:\n\n"
        f"{user_text}\n\n"
        "Update the profile based on my input.  Merge with existing data — "
        "do not remove anything from the \"history\" or \"feedback\" sections.\n"
        "Return ONLY the updated JSON object."
    )

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

