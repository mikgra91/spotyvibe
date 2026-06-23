"""Shared utilities for the core modules.

Technologies & patterns used:
- **Direct HTTP**: OpenAI API calls use core.openai_http (stdlib urllib +
  json) instead of the openai SDK.
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
    """Clear both debug and prompt log files.

    On Windows the ``RotatingFileHandler`` keeps ``debug.log`` open, so
    ``unlink()`` fails with *WinError 32 (file in use)*.  We therefore
    truncate files that are held by an active logging handler, and only
    ``unlink()`` files that are not (e.g. the prompt log).
    """
    import logging.handlers
    from pathlib import Path

    root = logging.getLogger()

    for log_path in (DEBUG_LOG_FILE, PROMPT_LOG_FILE):
        # Try to truncate via an active handler first (avoids WinError 32)
        truncated = False
        for handler in root.handlers:
            if isinstance(handler, (logging.FileHandler, logging.handlers.RotatingFileHandler)):
                try:
                    handler_file = Path(handler.baseFilename).resolve()
                except Exception:
                    continue
                if handler_file == log_path.resolve():
                    handler.acquire()
                    try:
                        handler.stream.seek(0)
                        handler.stream.truncate(0)
                        truncated = True
                    finally:
                        handler.release()
                    break

        if not truncated:
            # No active handler holds this file — safe to delete
            try:
                if log_path.exists():
                    log_path.unlink()
            except OSError as e:
                logger.warning("Failed to delete log file %s: %s", log_path, e)


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


def loads_lenient(text):
    """``json.loads`` that tolerates prose around the JSON object.

    Why this exists: some models (notably Claude Haiku under a strict
    constraint prompt) append an explanatory sentence *after* the JSON
    object — e.g. ``{...}\\n\\nZero is correct here.`` Standard
    ``json.loads`` then raises ``JSONDecodeError: Extra data``, which
    collapses the whole batch to an empty playlist even though the JSON
    itself is valid. ``raw_decode`` parses the first complete JSON value
    and ignores whatever follows. A leading-bracket scan also tolerates
    prose *before* the JSON.

    Raises ``json.JSONDecodeError`` if no JSON value can be found — callers
    already catch that and fall back to an empty result.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    s = text.lstrip()
    for i, ch in enumerate(s):
        if ch in "{[":
            s = s[i:]
            break
    obj, _end = json.JSONDecoder().raw_decode(s)
    return obj


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


def safe_text(data, key):
    """Extract, sanitize, and strip a text field from a request dict.

    Shorthand for the common pattern:
        sanitize_text(str(data.get(key) or "").strip())
    """
    return sanitize_text(str(data.get(key) or "").strip())


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
    """Return available chat models for the Settings dropdown.

    Provider-aware as of 2026-05-23: the dropdown must list models
    that ACTUALLY work for the active provider preset. Hard-coding
    the OpenAI allowlist when the user is on OpenRouter produced a
    dropdown of unreachable model IDs (gpt-4o, gpt-4.1-nano, etc.)
    and hid the curated OpenRouter list (gemini / gpt-5.4-mini /
    haiku) the JS layer already declared.

    Reads ``PROVIDER_SUGGESTED_MODELS[preset]`` from config.py — the
    single server-side source of truth that mirrors provider.js
    ``PROVIDER_PRESETS[*].suggested_models``.

    Returns a list of dicts ``{"id", "label", "supported"}``. The
    currently configured model is appended at the end marked
    ``unsupported`` when it isn't in the provider's curated list.
    """
    try:
        # Local import to avoid a circular at module load — config
        # imports core/src/utils.py only at runtime.
        from config import (
            PROVIDER_SUGGESTED_MODELS, get_llm_provider_preset,
        )
        preset = get_llm_provider_preset()
    except Exception:  # pragma: no cover — defensive
        preset = "openai"

    suggested = PROVIDER_SUGGESTED_MODELS.get(preset)
    if not suggested:
        # Fallback to the OpenAI list for any provider without a
        # curated set (e.g. local LLMs before Fetch Models has been
        # used). User can still hand-edit via the free-text toggle.
        suggested = (
            list(OPENAI_SUPPORTED_MODELS_JSON)
            + list(OPENAI_EXTRA_ALLOWED_MODELS)
        )

    # Build display list preserving declaration order, deduplicating
    models = []
    seen: set = set()
    for mid in suggested:
        if mid not in seen:
            models.append({"id": mid, "label": mid, "supported": True})
            seen.add(mid)

    # Append configured model at the end if it is not in the curated
    # list — marked unsupported so the UI can warn the user.
    current = get_model()
    if current and current not in seen:
        models.append({
            "id": current,
            "label": f"{current} (unsupported)",
            "supported": False,
        })

    return models
