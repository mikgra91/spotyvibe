"""Band/Song Analysis — structured AI analysis of artists and tracks.

Sends artist (and optional track) to GPT with structured output, returning
genre, style characteristics, and profile suggestion strings the user can
copy into their taste profile.
"""

import json
import logging
import uuid as _uuid
from pathlib import Path

from config import (BASE_DIR, EVAL_LOG_FILE, get_active_profile_id,
                    get_debug_mode, get_gpt_language, get_model)
from .errors import TranslatableError
from .openai_http import call_gpt_json_with_meta
from .eval_log import log_analysis_summary

ANALYSIS_PROMPT_FILE = BASE_DIR / "prompts" / "analysis_prompt.txt"

logger = logging.getLogger(__name__)


def analyze_band_song(artist: str, track: str = "") -> dict:
    """Call GPT to analyse a band/song and return structured JSON.

    Parameters:
        artist: Band or artist name (required).
        track:  Optional specific track or song title.

    Returns a dict with keys: artist, track, genre, style_tags,
    characteristics, profile_suggestions.

    Telemetry: emits one ``kind: "analysis_summary"`` row to the eval log
    (when DEBUG_MODE is on) so cost / latency / quality of Band/Song
    Analysis can be compared across model A/B variants.
    """
    if not artist or not artist.strip():
        raise TranslatableError(
            "error.analysis.artist_required",
            "Artist name is required.",
        )

    with open(ANALYSIS_PROMPT_FILE, "r", encoding="utf-8") as f:
        system_prompt = f.read().replace("{gpt_language}", get_gpt_language())

    subject = artist.strip()
    if track and track.strip():
        subject = f"{artist.strip()} — {track.strip()}"

    user_message = (
        f'Analyse the following: "{subject}"\n\n'
        "Return ONLY the JSON object described in your instructions."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    run_id = str(_uuid.uuid4())
    status = "ok"
    meta: dict = {}
    result: dict | None = None

    try:
        result, meta = call_gpt_json_with_meta(
            messages, temperature=0.3, label="Band/Song Analysis",
        )
    except ValueError as exc:
        # Empty or unparseable response — still log so a flaky model surfaces.
        status = "empty_response" if "empty" in str(exc).lower() else "invalid_json"
        try:
            log_analysis_summary(
                run_id=run_id,
                model=get_model(),
                profile_id=get_active_profile_id(),
                eval_log_path=EVAL_LOG_FILE,
                debug_mode=get_debug_mode(),
                artist=artist, track=track or "",
                status=status,
                latency_s=meta.get("latency_s"),
                usage=meta.get("usage"),
                prompt_chars=prompt_chars,
                response_chars=meta.get("raw_response_chars"),
            )
        except Exception as _exc:  # pragma: no cover — telemetry must never break a feature
            logger.warning("log_analysis_summary skipped: %s", _exc)
        raise

    # Normalise keys so the UI always gets a predictable shape
    result.setdefault("artist", artist.strip())
    result.setdefault("track", track.strip() if track else "")
    result.setdefault("genre", [])
    result.setdefault("style_tags", [])
    result.setdefault("characteristics", {})
    result.setdefault("audio_features", {})
    result.setdefault("profile_suggestions", [])

    try:
        log_analysis_summary(
            run_id=run_id,
            model=meta.get("model") or get_model(),
            profile_id=get_active_profile_id(),
            eval_log_path=EVAL_LOG_FILE,
            debug_mode=get_debug_mode(),
            artist=artist, track=track or "",
            status=status,
            latency_s=meta.get("latency_s"),
            usage=meta.get("usage"),
            prompt_chars=prompt_chars,
            response_chars=meta.get("raw_response_chars"),
            genre_count=len(result.get("genre") or []),
            style_tag_count=len(result.get("style_tags") or []),
            suggestion_count=len(result.get("profile_suggestions") or []),
        )
    except Exception as _exc:  # pragma: no cover
        logger.warning("log_analysis_summary skipped: %s", _exc)

    return result
