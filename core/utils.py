"""Shared utilities for the core modules.

Technologies & patterns used:
- **openai** (v1.x): Official Python SDK for the OpenAI API. Uses the
  new resource-based client (`OpenAI(...)`) introduced in v1.0, replacing
  the legacy module-level `openai.ChatCompletion.create()` style.
- **Singleton / lazy initialisation**: The OpenAI client is created once
  and reused across requests. This avoids repeated HTTP-session setup and
  reduces latency. The client is automatically recreated when the API key
  changes, supporting runtime credential updates without a restart.
- **python-dotenv integration**: API keys live in environment variables,
  loaded from a `.credentials` file by config.py. This module reads them
  via `os.getenv()` — the standard twelve-factor-app approach.
"""

import json
import os
from datetime import datetime, timezone
# OpenAI Python SDK v1.x — provides a class-based client (`OpenAI`) that
# manages HTTP sessions, retries, and streaming internally.
from openai import OpenAI
from config import DEBUG_LOG_FILE, get_debug_mode

# Module-level singleton cache for the OpenAI client.
# Why a global singleton? Creating an OpenAI() client spins up an
# httpx.Client with connection pooling. Reusing it across requests
# avoids repeated TLS handshakes and keeps connection overhead low.
_openai_client = None
_openai_key = None


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

    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(parts))


def clear_debug_log():
    """Delete the debug log file if it exists."""
    try:
        if DEBUG_LOG_FILE.exists():
            DEBUG_LOG_FILE.unlink()
    except OSError:
        pass


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


def get_openai_client():
    """Return a lazily-initialised OpenAI client.

    Re-creates the client when the API key changes (e.g. after the user
    updates credentials via the Settings UI).  Raises ``ValueError`` early
    if the key is not configured.

    Pattern: **Lazy Singleton with key-change detection**.
    - First call creates the client and caches it in module globals.
    - Subsequent calls return the cached instance (fast path).
    - If the API key has been rotated via the Settings UI, the old client
      is discarded and a fresh one is created with the new key.

    Alternative considered: Dependency injection (passing the client as a
    parameter). This was rejected because every Flask route and core
    function would need the client threaded through, adding boilerplate
    with no practical benefit for a single-user desktop app.
    """
    global _openai_client, _openai_key

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key is not configured. "
            "Go to ⚙️ → Credentials to set it."
        )

    if _openai_client is None or _openai_key != api_key:
        _openai_client = OpenAI(api_key=api_key)
        _openai_key = api_key

    return _openai_client


def get_openai_models():
    """Fetch available GPT chat models from the OpenAI API.

    Returns a sorted list of model ID strings suitable for chat completions.

    Uses the OpenAI Models API (`client.models.list()`) which returns all
    models accessible to the current API key. The results are filtered to
    chat-capable models (gpt-*, o1, o3, o4 prefixes) and excludes
    specialised models (audio, TTS, embeddings, etc.) that cannot be used
    for chat completions.

    This dynamic listing means the Settings UI always shows the latest
    models without code changes — new OpenAI model releases appear
    automatically.
    """
    client = get_openai_client()
    models = client.models.list()

    chat_prefixes = ("gpt-", "o1", "o3", "o4")
    chat_models = [
        m.id for m in models.data
        if m.id.startswith(chat_prefixes)
        and "realtime" not in m.id
        and "audio" not in m.id
        and "transcribe" not in m.id
        and "tts" not in m.id
        and "embedding" not in m.id
        and "search" not in m.id
    ]

    return sorted(chat_models)


