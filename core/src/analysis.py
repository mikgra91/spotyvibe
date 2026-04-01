"""Band/Song Analysis — structured AI analysis of artists and tracks.

Sends artist (and optional track) to GPT with structured output, returning
genre, style characteristics, and profile suggestion strings the user can
copy into their taste profile.
"""

import json
from pathlib import Path

from config import BASE_DIR, get_model, get_gpt_language
from .utils import strip_code_fences, debug_log
from .openai_http import chat_completions_create, extract_chat_content

ANALYSIS_PROMPT_FILE = BASE_DIR / "prompts" / "analysis_prompt.txt"


def analyze_band_song(artist: str, track: str = "") -> dict:
    """Call GPT to analyse a band/song and return structured JSON.

    Parameters:
        artist: Band or artist name (required).
        track:  Optional specific track or song title.

    Returns a dict with keys: artist, track, genre, style_tags,
    characteristics, profile_suggestions.
    """
    if not artist or not artist.strip():
        raise ValueError("Artist name is required.")

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

    response = chat_completions_create(
        model=get_model(),
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw = extract_chat_content(response)
    debug_log("Band/Song Analysis", messages, raw)

    content = strip_code_fences(raw)
    if not content:
        raise ValueError("AI returned an empty response. Please try again.")

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("AI returned invalid JSON. Please try again.")

    # Normalise keys so the UI always gets a predictable shape
    result.setdefault("artist", artist.strip())
    result.setdefault("track", track.strip() if track else "")
    result.setdefault("genre", [])
    result.setdefault("style_tags", [])
    result.setdefault("characteristics", {})
    result.setdefault("audio_features", {})
    result.setdefault("profile_suggestions", [])

    return result
