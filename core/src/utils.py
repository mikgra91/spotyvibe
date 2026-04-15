"""Shared utilities for the core modules.

Technologies & patterns used:
- **Direct HTTP**: OpenAI API calls use core.openai_http (stdlib urllib +
  json) instead of the openai SDK. This removes native/Rust transitive
  dependencies (jiter, pydantic-core) that break Android/Chaquopy builds.
- **python-dotenv integration**: API keys live in environment variables,
  loaded from a `.credentials` file by config.py. This module reads them
  via `os.getenv()` — the standard twelve-factor-app approach.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from config import (
    PROMPT_LOG_FILE, DEBUG_LOG_FILE, get_debug_mode,
    OPENAI_SUPPORTED_MODELS_JSON, OPENAI_EXTRA_ALLOWED_MODELS, get_model,
)


def debug_log(label, messages, response_content):
    """Append a GPT request/response pair to the debug log file.

    Only writes if debug mode is enabled.  Each entry is separated by a
    visual divider and includes a timestamp, the full messages sent, and
    the raw response content.

    Design note: This uses simple file-append logging rather than Python's
    `logging` module because the output is structured GPT I/O (prompt +
    response), not conventional log levels. The file lives in the user's
    AppData directory alongside credentials, keeping all runtime data out
    of the project tree.
    """
    if not get_debug_mode():
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    separator = "=" * 80

    parts = [
        separator,
        f"[{timestamp}]  {label}",
        separator,
        "",
        "── MESSAGES SENT ──",
        "",
    ]

    for msg in messages:
        parts.append(f"[{msg['role'].upper()}]")
        parts.append(msg["content"])
        parts.append("")

    parts.append("── GPT RESPONSE ──")
    parts.append("")
    # Pretty-print if it's valid JSON, otherwise dump raw
    try:
        parsed = json.loads(response_content)
        parts.append(json.dumps(parsed, indent=2, ensure_ascii=False))
    except (json.JSONDecodeError, TypeError):
        parts.append(str(response_content))
    parts.append("")
    parts.append("")

    PROMPT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(parts))


def clear_debug_log():
    """Delete both debug and prompt log files if they exist."""
    for f in (DEBUG_LOG_FILE, PROMPT_LOG_FILE):
        try:
            if f.exists():
                f.unlink()
        except OSError as e:
            logger.warning("Failed to delete log file %s: %s", f, e)


def app_log(message):
    """Log a backend event to debug.log."""
    if not get_debug_mode():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def strip_code_fences(text):
    """Remove markdown code fences (```json...``` or ```...```) from text.

    Why this exists: Even when `response_format={"type": "json_object"}` is
    used, some models occasionally wrap their output in markdown code fences.
    Stripping them defensively prevents json.loads() from failing on what is
    otherwise valid JSON content.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def sanitize_text(text):
    """Remove null bytes, control characters, and normalize whitespace.

    Keeps standard whitespace (newline, tab, carriage return) but strips
    all other control characters (0x01–0x08, 0x0b, 0x0c, 0x0e–0x1f, 0x7f).
    Collapses multiple spaces/tabs on a single line to a single space.
    """
    if not isinstance(text, str):
        return ""
    text = text.replace('\x00', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def sanitize_profile(profile):
    """Recursively apply sanitize_text() to all string values in a profile dict."""
    if isinstance(profile, dict):
        return {k: sanitize_profile(v) for k, v in profile.items()}
    if isinstance(profile, list):
        return [sanitize_profile(item) for item in profile]
    if isinstance(profile, str):
        return sanitize_text(profile)
    return profile


def get_openai_models():
    """Return available OpenAI chat models for the Settings dropdown.

    Returns a list of model dicts: {"id", "label", "supported"}.

    Uses the curated allowlist from config — no API call required.
    This approach works on Android/Chaquopy where the openai SDK (and its
    native deps) are not available, and avoids a network round-trip just
    to populate a dropdown.

    The currently configured model is appended at the end if it is not
    already in the allowlist, marked as unsupported so the UI can warn
    the user.

    Model ordering: allowlist order first, then OPENAI_EXTRA_ALLOWED_MODELS,
    then the configured model (if missing from both lists).
    """
    allowed_ids = list(OPENAI_SUPPORTED_MODELS_JSON)
    extra_ids = list(OPENAI_EXTRA_ALLOWED_MODELS)
    all_allowed: set = set(allowed_ids) | set(extra_ids)

    # Build display list preserving declaration order, deduplicating
    models = []
    seen: set = set()
    for mid in allowed_ids + extra_ids:
        if mid not in seen:
            models.append({"id": mid, "label": mid, "supported": True})
            seen.add(mid)

    # Append configured model at the end if it is not in the allowlist
    current = get_model()
    if current and current not in all_allowed:
        models.append({
            "id": current,
            "label": f"{current} (unsupported)",
            "supported": False,
        })

    return models
