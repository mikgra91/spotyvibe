import html
import logging
import logging.handlers
import math
import os
import re
import sys
import json
import threading
import time
import traceback
import uuid
from datetime import datetime


# Ensure the spotyvibe package directory is on sys.path so all
# imports resolve correctly regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, render_template, jsonify, request, redirect, stream_with_context, send_from_directory
from config import (
    load_config, get_credentials, save_credentials, save_settings,
    CREDENTIALS_FILE, SETTINGS_FILE,
    BATCH_SIZE, BASE_DIR, get_model, get_settings, get_debug_mode,
    get_playlist_size, DEBUG_LOG_FILE, MAX_CONSECUTIVE_EMPTY_BATCHES,
    get_new_artist_percentage, get_gpt_language, IS_ANDROID, PROFILE_IMPORT_MAX_BYTES,
    GENERAL_REQUEST_MAX_BYTES, MAX_GPT_CALLS_PER_RUN,
    MAX_CORE_DESCRIPTION_LEN, MAX_PROFILE_SECTION_LEN,
    MAX_FEEDBACK_REASON_LEN, MAX_FEEDBACK_ARTIST_LEN, MAX_FEEDBACK_TRACK_LEN,
    is_onboarding_completed, set_onboarding_completed, MAX_SONG_LIST_SIZE,
    _get_app_dir, get_active_profile_id, MAX_PROFILE_NAME_LEN,
)
import markdown

load_config()


def _setup_logging():
    """Configure Python logging with file rotation and console output."""
    log_dir = DEBUG_LOG_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler — always active, rotates at 5 MB, keeps 3 backups
    fh = logging.handlers.RotatingFileHandler(
        str(DEBUG_LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8", errors="replace",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # Console handler — for development
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if get_debug_mode() else logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(ch)


_setup_logging()

from core.src.profile import (
    load_profile, save_profile, is_profile_trained,
    get_profile_status, train_profile, save_profile_sections,
    export_profile_dict, import_profile_dict,
    swap_profile_with_history,
    list_profiles, create_profile, delete_profile, activate_profile,
)
from core.src.suggestions import (
    normalize_history,
    build_messages, call_gpt, update_profile,
    filter_duplicate_suggestions,
)
from core.src.feedback import like_track, dislike_track
from core.src.analysis import analyze_band_song
from core.src.history import save_run, load_runs
from core.src.utils import get_openai_models, clear_debug_log, sanitize_text, app_log
from core.src.openai_http import OpenAIConfigError, OpenAIError
from core.src.playlist import (
    search_tracks, add_to_playlist, remove_from_playlist, delete_playlist,
    get_spotify_auth_status, get_spotify_auth_url, handle_spotify_callback,
    disconnect_spotify, get_user_playlists, get_playlist_tracks,
)

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = GENERAL_REQUEST_MAX_BYTES


@app.template_filter("datetimeformat")
def _datetimeformat(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)

# Clear debug log on startup so it only contains data from the current session
clear_debug_log()

# Model list cache: avoid repeated OpenAI API calls for the same data
_models_cache: dict = {"data": None, "expires": 0.0}
_MODELS_CACHE_TTL = 300  # 5 minutes

# Active generation runs: run_id → {"cancel": Event, "finalize_on_cancel": bool, "verified_tracks": [], "created_at": float}
_runs: dict = {}
_runs_lock = threading.Lock()
_STALE_RUN_SECONDS = 600  # 10 minutes


def _sweep_stale_runs():
    """Remove _runs entries older than _STALE_RUN_SECONDS to prevent leaks.

    Acquires _runs_lock internally — safe to call from any context.
    """
    with _runs_lock:
        now = time.monotonic()
        stale = [rid for rid, r in _runs.items() if now - r.get("created_at", now) > _STALE_RUN_SECONDS]
        for rid in stale:
            _runs.pop(rid, None)


_PLAYLIST_MODES = [
    {"value": "create", "label": "Create new"},
    {"value": "append", "label": "Append to existing"},
    {"value": "replace", "label": "Replace existing"},
]

_DEFAULT_AUDIO_FILTERS = {
    k: {"min": None, "max": None}
    for k in ("energy", "valence", "tempo", "danceability", "acousticness")
}


@app.route("/")
def index():
    if not is_onboarding_completed():
        return redirect("/onboarding")

    has_profile = bool(get_active_profile_id())
    if has_profile:
        profile_data_dict = load_profile()
        prefs = profile_data_dict.get("preferences", {})
        profile_trained = is_profile_trained()
    else:
        prefs = {}
        profile_trained = False

    spotify_connected = get_spotify_auth_status() == "authenticated"
    raw_settings = get_settings()
    gpt_lang = get_gpt_language()
    settings = {
        "model": raw_settings.get("model", ""),
        "playlist_size": raw_settings.get("playlist_size", 10),
        "new_artist_pct": raw_settings.get("new_artist_percentage", 30),
        "gpt_language": gpt_lang,
        "debug_mode": raw_settings.get("debug_mode", False),
    }
    debug_controls_available = raw_settings.get("debug_controls_available", True)
    current_language = "en"  # UI language is client-side (localStorage); server always sends 'en' as default
    credentials = get_credentials()
    return render_template(
        "base.html",
        profile=prefs,
        profile_trained=profile_trained,
        profile_edit_mode=False,
        spotify_connected=spotify_connected,
        current_language=current_language,
        current_theme="equalizer",
        audio_filters=_DEFAULT_AUDIO_FILTERS,
        playlist_modes=_PLAYLIST_MODES,
        current_playlist_mode="create",
        playlist_name="",
        playlist_options=[],
        can_generate=profile_trained and spotify_connected,
        last_analysis_result=None,
        artist_input=None,
        track_input=None,
        settings=settings,
        available_models=None,
        debug_controls_available=debug_controls_available,
        credentials=credentials,
        help_html="",
    )


@app.route("/onboarding")
def onboarding():
    return render_template("onboarding.html")



@app.route("/api/onboarding/status")
def onboarding_status():
    """Return whether the user has completed onboarding."""
    return jsonify({"completed": is_onboarding_completed()})


@app.route("/api/onboarding/complete", methods=["POST"])
def onboarding_complete():
    """Mark onboarding as completed (or skipped)."""
    try:
        set_onboarding_completed(True)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/docs/screenshots/<path:filename>")
def docs_screenshot(filename):
    """Serve documentation screenshot images."""
    screenshot_dir = BASE_DIR / "documentation" / "assets" / "screenshots"
    return send_from_directory(str(screenshot_dir), filename)


@app.route("/api/help")
def help_content():
    """Return the help guide rendered as HTML."""
    manual_path = BASE_DIR / "documentation" / "help.md"
    if not manual_path.exists():
        return jsonify({"error": "Help file not found."}), 404
    md_text = manual_path.read_text(encoding="utf-8")
    html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    return jsonify({"html": html})


def _extract_help_section(full_html, anchor):
    """Extract a single section from rendered help HTML by heading anchor ID.

    Returns everything from the matched heading up to (but not including)
    the next heading of the same or higher level. Trailing ``<hr>`` tags
    are stripped for cleaner display in the section-help popup.
    """
    heading_pat = re.compile(
        rf'<h([2-6])\s[^>]*id="{re.escape(anchor)}"[^>]*>',
        re.IGNORECASE,
    )
    match = heading_pat.search(full_html)
    if not match:
        return None

    heading_level = int(match.group(1))
    start = match.start()

    # Find the next heading at the same or higher level (lower number)
    after = full_html[match.end():]
    levels = "".join(str(i) for i in range(1, heading_level + 1))
    next_match = re.search(rf"<h[{levels}][\s>]", after, re.IGNORECASE)

    end = (match.end() + next_match.start()) if next_match else len(full_html)
    section = full_html[start:end].strip()
    section = re.sub(r"\s*<hr\s*/?\s*>\s*$", "", section)
    return section


@app.route("/api/help/section/<anchor>")
def help_section(anchor):
    """Return a single help section by its heading anchor ID."""
    manual_path = BASE_DIR / "documentation" / "help.md"
    if not manual_path.exists():
        return jsonify({"error": "Help file not found."}), 404
    md_text = manual_path.read_text(encoding="utf-8")
    full_html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    section_html = _extract_help_section(full_html, anchor)
    if not section_html:
        return jsonify({"error": "Section not found."}), 404
    return jsonify({"html": section_html})


def _sse(event_type, **data):
    """Format a single Server-Sent Event line."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


@app.route("/api/run", methods=["POST"])
def run_pipeline():
    """Generate suggestions via OpenAI in batches of BATCH_SIZE, verify on
    Spotify, and repeat until the configured playlist_size is reached.

    Accepts an optional JSON body with a ``run_id`` field so the client can
    cancel the run via ``POST /api/cancel``.

    Returns an SSE stream so the UI can show real-time progress.
    """
    body = request.get_json(force=True, silent=True) or {}
    run_id = body.get("run_id") or str(uuid.uuid4())
    playlist_mode = body.get("playlist_mode", "default")
    playlist_target_id = body.get("playlist_id") or None
    playlist_custom_name = sanitize_text(str(body.get("playlist_name") or "").strip()) or None
    if playlist_custom_name and len(playlist_custom_name) > 200:
        playlist_custom_name = playlist_custom_name[:200]
    # Audio feature filters: {"energy": {"min": 0.6, "max": 1.0}, ...}
    audio_filters = body.get("audio_filters") or {}
    cancel_event = threading.Event()
    _sweep_stale_runs()
    with _runs_lock:
        _runs[run_id] = {"cancel": cancel_event, "finalize_on_cancel": False, "verified_tracks": [], "created_at": time.monotonic()}

    def generate():
        try:
            if not is_profile_trained():
                yield _sse("error", message="Please train your taste profile first.")
                return

            # Verify Spotify is connected before starting the expensive GPT pipeline
            spotify_status = get_spotify_auth_status()
            if spotify_status != "authenticated":
                yield _sse("error", message="Spotify is not connected. Please connect via ⚙️ Settings first.")
                return

            # Clear debug log at the start of each run so it only
            # contains data from the current generation.
            if get_debug_mode():
                clear_debug_log()

            app_log(f"Generation run started: run_id={run_id} mode={playlist_mode}")

            playlist_size = get_playlist_size()
            new_artist_percentage = get_new_artist_percentage()

            yield _sse("progress", message="Loading profile…")
            profile = load_profile()
            normalize_history(profile)

            # Two-pass mode: when history is large, boost new-artist pressure
            # after the first half of the playlist is filled to break recycling loops.
            _history_len = len(profile.get("history", {}).get("suggested_tracks", []))
            large_history = _history_len > 150
            large_history_half = math.ceil(playlist_size / 2) if large_history else None

            verified_tracks = []   # tracks with a confirmed Spotify URI
            verified_uris = set()  # fast URI dedup across attempts
            all_not_found = []
            batch_num = 0
            gpt_call_count = 0
            was_cancelled = False
            gpt_exhausted = False

            # Retry tracking: how many consecutive batches returned entirely
            # filtered results, and which tracks were in the last such batch.
            consecutive_empty_batches = 0
            last_filtered_tracks = []  # filtered tracks from most recent empty batch

            while len(verified_tracks) < playlist_size:
                # ── Check for cancellation before each expensive GPT call ──
                if cancel_event.is_set():
                    was_cancelled = True
                    break

                batch_num += 1
                remaining = playlist_size - len(verified_tracks)
                # Request either a full batch or just the remaining count
                request_count = min(BATCH_SIZE, remaining)

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: "
                            f"Asking GPT for {request_count} suggestions… "
                            f"(have {len(verified_tracks)}/{playlist_size})",
                )

                # 1 — Ask GPT for suggestions.
                # On retries after all-filtered batches, pass the filtered tracks
                # explicitly so GPT cannot claim it didn't know about them.
                accepted = verified_tracks if batch_num > 1 else None
                # Hard cost guardrail
                if gpt_call_count >= MAX_GPT_CALLS_PER_RUN:
                    yield _sse(
                        "progress",
                        message=f"Reached GPT call limit ({MAX_GPT_CALLS_PER_RUN}). "
                                f"Stopping with {len(verified_tracks)} verified track(s).",
                    )
                    break

                # Phase 3 two-pass: once we have half the playlist from a large
                # history, ramp up new-artist pressure for remaining batches.
                effective_nap = new_artist_percentage
                if large_history and large_history_half is not None and len(verified_tracks) >= large_history_half:
                    effective_nap = min(new_artist_percentage + 40, 95)

                messages = build_messages(
                    profile,
                    accepted_tracks=accepted,
                    batch_size=request_count,
                    recently_filtered_tracks=last_filtered_tracks if last_filtered_tracks else None,
                    new_artist_percentage=effective_nap,
                    batch_num=batch_num,
                    audio_filters=audio_filters or None,
                )
                gpt_call_count += 1
                # Adaptive temperature: lower on retries for more deterministic output
                temperature = max(0.3, 0.7 - (consecutive_empty_batches * 0.2))
                result = call_gpt(messages, temperature=temperature)

                # ── Check again after the blocking GPT call ──
                if cancel_event.is_set():
                    was_cancelled = True
                    break

                # 2 — Code-side duplicate / disliked filter.
                # Extracts _filtered_out so we can pass it back to GPT on retry.
                result = filter_duplicate_suggestions(profile, result)
                filtered_out = result.pop("_filtered_out", [])

                # Truncate over-requested batch (+3 buffer) to the actual count needed.
                # Recompute profile_updates so history reflects only added tracks.
                if len(result["playlist"]) > request_count:
                    result["playlist"] = result["playlist"][:request_count]
                    truncated_artists = {item["artist"].lower().strip() for item in result["playlist"]}
                    result["profile_updates"]["suggested_artists"] = list(truncated_artists)
                    result["profile_updates"]["suggested_tracks"] = [
                        {"artist": item["artist"].lower().strip(), "track": item["track"].lower().strip()}
                        for item in result["playlist"]
                    ]
                    result["new_artists"] = [a for a in result["new_artists"] if a in truncated_artists]

                if not result["playlist"]:
                    consecutive_empty_batches += 1
                    last_filtered_tracks = filtered_out  # used in next build_messages call

                    if consecutive_empty_batches >= MAX_CONSECUTIVE_EMPTY_BATCHES:
                        gpt_exhausted = True
                        yield _sse(
                            "progress",
                            message=f"Batch {batch_num}: GPT suggested only already-known tracks "
                                    f"for {consecutive_empty_batches} consecutive batches. "
                                    f"Stopping with {len(verified_tracks)} verified track(s).",
                        )
                        break

                    yield _sse(
                        "progress",
                        message=f"Batch {batch_num}: All {len(filtered_out)} suggestion(s) already known "
                                f"(retry {consecutive_empty_batches}/{MAX_CONSECUTIVE_EMPTY_BATCHES}). "
                                f"Sending explicit reminder to GPT…",
                    )
                    profile = update_profile(profile, result)
                    save_profile(profile)
                    continue

                # Success — reset consecutive-empty counter
                consecutive_empty_batches = 0
                last_filtered_tracks = []

                # 3 — Verify each track exists on Spotify
                batch_count = len(result["playlist"])
                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: Verifying {batch_count} tracks on Spotify…",
                )
                found, not_found = search_tracks(result["playlist"])
                all_not_found.extend(not_found)


                for t in found:
                    if t["uri"] not in verified_uris:
                        verified_tracks.append(t)
                        verified_uris.add(t["uri"])

                # Keep run state updated so the cancel endpoint can report progress
                with _runs_lock:
                    if run_id in _runs:
                        _runs[run_id]["verified_tracks"] = list(verified_tracks)

                # 4 — Update history
                profile = update_profile(profile, result)
                save_profile(profile)

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: {len(found)} found on Spotify, "
                            f"{len(verified_tracks)}/{playlist_size} total verified",
                )
                # Inform the UI how many tracks we have so far (drives the
                # "Use X tracks now" button label)
                yield _sse("batch_verified", count=len(verified_tracks), total=playlist_size)

            # ── Handle cancellation ────────────────────────────────────────
            if was_cancelled:
                finalize = _runs.get(run_id, {}).get("finalize_on_cancel", False)
                if not finalize or not verified_tracks:
                    msg = (
                        "Generation cancelled. No tracks were found yet."
                        if not verified_tracks
                        else f"Generation cancelled. {len(verified_tracks)} track(s) found but not added to playlist."
                    )
                    yield _sse("cancelled", message=msg, count=len(verified_tracks))
                    return
                # finalize=True → fall through to playlist creation below

            # ── Handle GPT exhaustion ──────────────────────────────────────
            if gpt_exhausted and not verified_tracks:
                yield _sse(
                    "error",
                    message=(
                        "GPT kept suggesting already-known tracks and could not produce "
                        "any new ones. Try updating your taste profile with new preferences, "
                        "or reduce the playlist size."
                    ),
                )
                return
            # gpt_exhausted with some verified_tracks → fall through to create
            # playlist with what was found (same as "Use X tracks now")

            if not verified_tracks:
                yield _sse("error", message="No tracks could be verified on Spotify.")
                return

            # Cap at target count
            verified_tracks = verified_tracks[:playlist_size]

            # 5 — Add all verified tracks to the Spotify playlist
            yield _sse("progress", message=f"Adding {len(verified_tracks)} tracks to Spotify playlist…")
            playlist_info = add_to_playlist(
                verified_tracks,
                mode=playlist_mode,
                playlist_id=playlist_target_id,
                playlist_name=playlist_custom_name,
                profile=profile,
            )

            # Save run history (before stripping internal keys)
            try:
                save_run(
                    run_id=run_id,
                    playlist_id=playlist_info.get("playlist_id") or "",
                    playlist_url=playlist_info.get("url") or "",
                    tracks=verified_tracks,
                )
            except Exception:
                pass  # history save is best-effort

            # Strip internal "uri" key — the UI doesn't need it
            _HIDDEN_KEYS = {"uri"}
            visible_playlist = [
                {k: v for k, v in t.items() if k not in _HIDDEN_KEYS}
                for t in verified_tracks
            ]

            # Append new tracks to the persistent song list (best-effort)
            try:
                if _SONGLIST_FILE.exists():
                    existing_songs = json.loads(_SONGLIST_FILE.read_text(encoding="utf-8"))
                else:
                    existing_songs = []
                combined = existing_songs + visible_playlist
                combined = combined[-MAX_SONG_LIST_SIZE:]  # keep newest, drop oldest
                _SONGLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
                _SONGLIST_FILE.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            yield _sse(
                "result",
                playlist=visible_playlist,
                playlist_url=playlist_info.get("url"),
                added=playlist_info.get("added", 0),
                not_found=all_not_found,
                was_cancelled=was_cancelled or gpt_exhausted,
            )

        except Exception as e:
            traceback.print_exc()
            yield _sse("error", message=str(e))
        finally:
            with _runs_lock:
                _runs.pop(run_id, None)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/run/<run_id>/status")
def run_status(run_id):
    """Return the current state of an active or recently completed run.

    Used by the UI to recover after an SSE disconnect.
    """
    with _runs_lock:
        run = _runs.get(run_id)
    if run is None:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": "running" if not run["cancel"].is_set() else "cancelled",
        "tracks_found": len(run.get("verified_tracks", [])),
    })


@app.route("/api/cancel", methods=["POST"])
def cancel_run():
    """Signal an active generation run to stop.

    Request body (JSON):
      run_id  – the run to cancel
      finalize – if true, create the Spotify playlist with however many
                 tracks have been verified so far instead of discarding them.
    """
    data = request.get_json(force=True, silent=True) or {}
    run_id = data.get("run_id")
    finalize = bool(data.get("finalize", False))

    with _runs_lock:
        if run_id and run_id in _runs:
            _runs[run_id]["finalize_on_cancel"] = finalize
            _runs[run_id]["cancel"].set()
            return jsonify({"status": "ok"})
    # Run may have already finished — that is fine
    return jsonify({"status": "not_found"})


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """Record a like or dislike and persist it in music_profile.json.

    For dislikes the track is also removed from the Spotify playlist.
    """
    data   = request.get_json(force=True)
    action = data.get("action")
    artist = sanitize_text(str(data.get("artist") or ""))
    track  = sanitize_text(str(data.get("track") or "")) or None
    reason = sanitize_text(str(data.get("reason") or "")) or None

    if not artist:
        return jsonify({"error": "Artist is required."}), 400
    if len(artist) > MAX_FEEDBACK_ARTIST_LEN:
        return jsonify({"error": f"Artist name too long (max {MAX_FEEDBACK_ARTIST_LEN} chars)."}), 400
    if track and len(track) > MAX_FEEDBACK_TRACK_LEN:
        return jsonify({"error": f"Track name too long (max {MAX_FEEDBACK_TRACK_LEN} chars)."}), 400
    if reason and len(reason) > MAX_FEEDBACK_REASON_LEN:
        reason = reason[:MAX_FEEDBACK_REASON_LEN]
    if action not in ("like", "dislike"):
        return jsonify({"error": "Action must be 'like' or 'dislike'."}), 400

    try:
        removal = None
        if action == "like":
            like_track(artist, track=track, reason=reason)
        else:
            dislike_track(artist, track=track, reason=reason)
            # Also remove the track from the Spotify playlist
            if track:
                removal = remove_from_playlist(artist, track)
            else:
                removal = {"removed": False, "reason": "No track specified"}

        response: dict = {"status": "ok"}
        if removal is not None:
            response["removal"] = removal
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove", methods=["POST"])
def remove_track():
    """Remove a track from the Spotify playlist without recording feedback."""
    data   = request.get_json(force=True)
    artist = sanitize_text(str(data.get("artist") or ""))
    track  = sanitize_text(str(data.get("track") or ""))

    if not artist or not track:
        return jsonify({"error": "Artist and track are required."}), 400

    try:
        result = remove_from_playlist(artist, track)
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/credentials", methods=["GET"])
def read_credentials():
    """Return masked credential values and their set/unset status."""
    return jsonify(get_credentials())


@app.route("/api/settings/credentials", methods=["POST"])
def write_credentials():
    """Update one or more credentials.  Only non-empty values are written."""
    data = request.get_json(force=True)
    save_credentials(data)
    return jsonify({"status": "ok", "path": str(CREDENTIALS_FILE)})


@app.route("/api/settings/models")
def list_models():
    """Return available OpenAI chat models and the currently selected one.

    Results are cached for _MODELS_CACHE_TTL seconds to avoid redundant
    API calls each time the Settings panel is opened.
    """
    now = time.time()
    if _models_cache["data"] is not None and now < _models_cache["expires"]:
        return jsonify({"models": _models_cache["data"], "selected": get_model()})

    try:
        models = get_openai_models()
        _models_cache["data"] = models
        _models_cache["expires"] = now + _MODELS_CACHE_TTL
        return jsonify({"models": models, "selected": get_model()})
    except (ValueError, OpenAIConfigError) as e:
        return jsonify({"error": str(e), "models": [], "selected": get_model()}), 400
    except (OpenAIError, Exception) as e:
        return jsonify({"error": str(e), "models": [], "selected": get_model()}), 500


@app.route("/api/settings", methods=["GET"])
def read_settings():
    """Return non-secret settings (model, debug mode)."""
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def write_settings():
    """Update non-secret settings (model, debug mode, playlist size)."""
    data = request.get_json(force=True)
    payload = {}
    if "model" in data:
        payload["OPENAI_MODEL"] = data["model"]

    # Debug Mode is desktop-only.
    if "debug_mode" in data and not IS_ANDROID:
        payload["DEBUG_MODE"] = "true" if data["debug_mode"] else ""

    if "playlist_size" in data:
        try:
            payload["PLAYLIST_SIZE"] = str(int(data["playlist_size"]))
        except (ValueError, TypeError):
            return jsonify({"error": "playlist_size must be a valid integer."}), 400
    if "new_artist_percentage" in data:
        try:
            payload["NEW_ARTIST_PERCENTAGE"] = str(max(1, min(100, int(data["new_artist_percentage"]))))
        except (ValueError, TypeError):
            return jsonify({"error": "new_artist_percentage must be a valid integer."}), 400
    if "gpt_language" in data:
        lang = sanitize_text(str(data["gpt_language"]).strip())
        if lang:
            payload["GPT_LANGUAGE"] = lang
    if "ui_language" in data:
        payload["UI_LANGUAGE"] = sanitize_text(str(data["ui_language"]).strip())
    save_settings(payload)
    app_log(f"Settings changed: {list(payload.keys())}")
    return jsonify({"status": "ok"})


@app.route("/api/settings/open-data-dir", methods=["POST"])
def open_data_dir():
    """Open the app data directory in the OS file explorer.

    Desktop-only — on Android this is a no-op (returns 404).
    Uses platform-appropriate commands: os.startfile (Windows),
    xdg-open (Linux), open (macOS).
    """
    if IS_ANDROID:
        return jsonify({"error": "Not available on Android."}), 404

    import subprocess
    import platform

    data_dir = str(_get_app_dir())
    system = platform.system()

    try:
        if system == "Windows":
            os.startfile(data_dir)
        elif system == "Darwin":
            subprocess.Popen(["open", data_dir])
        else:
            subprocess.Popen(["xdg-open", data_dir])
        return jsonify({"status": "ok", "path": data_dir})
    except Exception as e:
        return jsonify({"error": f"Could not open directory: {e}", "path": data_dir}), 500


@app.route("/api/settings/debug-log", methods=["DELETE"])
def clear_debug_log_endpoint():
    """Clear the debug log file.

    Desktop-only (Android builds must not expose prompt logging controls).
    """
    if IS_ANDROID:
        return jsonify({"error": "Not available on Android."}), 404

    try:
        clear_debug_log()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ── Taste profile training ──────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze_endpoint():
    """Analyse a band/song with GPT and return structured characteristics.

    Request body (JSON): {"artist": "...", "track": "..."}
    Returns structured JSON with genre, style_tags, characteristics, profile_suggestions.
    """
    data = request.get_json(force=True, silent=True) or {}
    artist = sanitize_text(str(data.get("artist") or "").strip())
    track = sanitize_text(str(data.get("track") or "").strip())

    if not artist:
        return jsonify({"error": "Artist name is required."}), 400
    if len(artist) > 200:
        return jsonify({"error": "Artist name too long."}), 400
    if len(track) > 200:
        return jsonify({"error": "Track name too long."}), 400

    try:
        result = analyze_band_song(artist, track)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Multi-profile CRUD ──────────────────────────────────────────────

@app.route("/api/profiles")
def get_profiles():
    """List all profiles: [{id, name, trained, last_updated}]."""
    try:
        profiles = list_profiles()
        active_id = get_active_profile_id()
        return jsonify({"profiles": profiles, "active_id": active_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles", methods=["POST"])
def create_profile_endpoint():
    """Create a new profile with a display name."""
    data = request.get_json(force=True, silent=True) or {}
    name = sanitize_text((data.get("name") or "").strip())
    if not name:
        return jsonify({"error": "Profile name is required."}), 400
    if len(name) > MAX_PROFILE_NAME_LEN:
        return jsonify({"error": f"Name too long (max {MAX_PROFILE_NAME_LEN} characters)."}), 400

    try:
        result = create_profile(name)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<profile_id>", methods=["DELETE"])
def delete_profile_endpoint(profile_id):
    """Delete a profile by ID."""
    profile_id = sanitize_text(profile_id.strip())
    try:
        delete_profile(profile_id)
        return jsonify({"status": "ok"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<profile_id>/activate", methods=["POST"])
def activate_profile_endpoint(profile_id):
    """Switch the active profile."""
    profile_id = sanitize_text(profile_id.strip())
    try:
        activate_profile(profile_id)
        return jsonify({"status": "ok"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Profile data ────────────────────────────────────────────────────

@app.route("/api/profile/status")
def profile_status():
    """Return whether the profile has been trained and when."""
    if not get_active_profile_id():
        return jsonify({"trained": False, "last_updated": None, "no_profile": True})
    return jsonify(get_profile_status())


@app.route("/api/profile/data")
def profile_data():
    """Return the current profile preferences for pre-filling the UI."""
    if not get_active_profile_id():
        app.logger.debug("profile/data called with no active profile")
        return jsonify({})
    profile = load_profile()
    return jsonify(profile)


@app.route("/api/profile/export")
def export_profile_endpoint():
    """Download the full profile JSON as a file.

    This is used by the UI's "Export" button. The filename is fixed so
    users don't accidentally tie their local profile to an arbitrary
    import filename.
    """
    profile = export_profile_dict()
    payload = json.dumps(profile, indent=2, ensure_ascii=False) + "\n"
    app_log("Profile exported")

    return Response(
        payload,
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="spotyvibe_profile.json"',
            "Cache-Control": "no-store",
        },
    )


@app.route("/api/profile/import", methods=["POST"])
def import_profile_endpoint():
    """Replace the current profile JSON with an imported profile.

    Request body (JSON): {"profile": {...}}

    The previous profile is backed up to the .history.json file by the
    standard save_profile() copy-on-write mechanism.
    """
    # Enforce request size (defense-in-depth; the client also checks).
    if request.content_length is not None and request.content_length > PROFILE_IMPORT_MAX_BYTES:
        return jsonify({"error": "Import is too large (max 10MB)."}), 413

    raw = request.get_data(cache=True) or b""
    if len(raw) > PROFILE_IMPORT_MAX_BYTES:
        return jsonify({"error": "Import is too large (max 10MB)."}), 413

    data = request.get_json(force=True, silent=True) or {}
    imported = data.get("profile")
    if imported is None:
        return jsonify({"error": "Missing 'profile' object."}), 400

    try:
        updated = import_profile_dict(imported)
        app_log("Profile imported")
        return jsonify({
            "status": "ok",
            "last_updated": updated.get("last_updated"),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile/reset-to-history", methods=["POST"])
def reset_profile_to_history_endpoint():
    """Swap the current profile with the history backup."""
    try:
        updated = swap_profile_with_history()
        app_log("Profile reset to history")
        return jsonify({
            "status": "ok",
            "last_updated": updated.get("last_updated"),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/api/train-profile", methods=["POST"])
def train_profile_endpoint():
    """Send the user's structured taste description to GPT and update the profile."""
    data = request.get_json(force=True)

    vibe_description = sanitize_text((data.get("vibe_description") or "").strip())
    core_description = sanitize_text((data.get("core_description") or "").strip())

    if not core_description and not vibe_description:
        return jsonify({"error": "Either a vibe description or core description is required."}), 400
    if core_description and len(core_description) > MAX_CORE_DESCRIPTION_LEN:
        return jsonify({"error": f"Core description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400
    if vibe_description and len(vibe_description) > MAX_CORE_DESCRIPTION_LEN:
        return jsonify({"error": f"Vibe description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400

    sections = {
        "vibe_description": vibe_description,
        "core_description": core_description,
        "must_have": sanitize_text((data.get("must_have") or "").strip())[:MAX_PROFILE_SECTION_LEN],
        "soft_preferences": sanitize_text((data.get("soft_preferences") or "").strip())[:MAX_PROFILE_SECTION_LEN],
        "avoid": sanitize_text((data.get("avoid") or "").strip())[:MAX_PROFILE_SECTION_LEN],
    }

    try:
        updated = train_profile(sections)
        return jsonify({
            "status": "ok",
            "last_updated": updated.get("last_updated"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save-profile", methods=["POST"])
def save_profile_endpoint():
    """Save the user's profile preferences directly without AI processing."""
    data = request.get_json(force=True)

    vibe_description = sanitize_text((data.get("vibe_description") or "").strip())
    core_description = sanitize_text((data.get("core_description") or "").strip())

    if core_description and len(core_description) > MAX_CORE_DESCRIPTION_LEN:
        return jsonify({"error": f"Core description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400
    if vibe_description and len(vibe_description) > MAX_CORE_DESCRIPTION_LEN:
        return jsonify({"error": f"Vibe description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400

    sections = {
        "vibe_description": vibe_description,
        "core_description": core_description,
        "must_have": sanitize_text((data.get("must_have") or "").strip())[:MAX_PROFILE_SECTION_LEN],
        "soft_preferences": sanitize_text((data.get("soft_preferences") or "").strip())[:MAX_PROFILE_SECTION_LEN],
        "avoid": sanitize_text((data.get("avoid") or "").strip())[:MAX_PROFILE_SECTION_LEN],
    }

    try:
        updated = save_profile_sections(sections)
        app_log("Profile saved directly")
        return jsonify({
            "status": "ok",
            "last_updated": updated.get("last_updated"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Spotify authentication ──────────────────────────────────────────

@app.route("/api/runs")
def get_runs():
    """Return the run history (newest first)."""
    try:
        runs = load_runs()
        return jsonify({"runs": runs})
    except Exception as e:
        return jsonify({"error": str(e), "runs": []}), 500



_SONGLIST_FILE = _get_app_dir() / "songlist.json"


@app.route("/api/songlist")
def get_songlist():
    """Return the persistent song list."""
    if _SONGLIST_FILE.exists():
        songs = json.loads(_SONGLIST_FILE.read_text(encoding="utf-8"))
    else:
        songs = []
    return jsonify(songs=songs, max_size=MAX_SONG_LIST_SIZE)


@app.route("/api/songlist", methods=["POST"])
def save_songlist():
    """Save/update the persistent song list."""
    data = request.get_json(force=True)
    songs = data.get("songs", [])
    if len(songs) > MAX_SONG_LIST_SIZE:
        return jsonify(error=f"Song list exceeds maximum of {MAX_SONG_LIST_SIZE}"), 400
    _SONGLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SONGLIST_FILE.write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, count=len(songs))


@app.route("/api/songlist/track", methods=["DELETE"])
def delete_songlist_track():
    """Permanently remove a specific track from the persistent song list."""
    data = request.get_json(force=True)
    artist = data.get("artist", "").strip()
    track = data.get("track", "").strip()
    if not _SONGLIST_FILE.exists():
        return jsonify(ok=True, count=0)
    songs = json.loads(_SONGLIST_FILE.read_text(encoding="utf-8"))
    songs = [s for s in songs if not (s.get("artist") == artist and s.get("track") == track)]
    _SONGLIST_FILE.write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, count=len(songs))


@app.route("/api/playlists")
def list_playlists():
    """Return the current user's Spotify playlists."""
    try:
        playlists = get_user_playlists()
        return jsonify({"playlists": playlists})
    except Exception as e:
        return jsonify({"error": str(e), "playlists": []}), 500


@app.route("/api/playlist/<playlist_id>/tracks")
def playlist_tracks(playlist_id):
    """Return all tracks in a Spotify playlist with enriched metadata."""
    try:
        tracks = get_playlist_tracks(playlist_id)
        return jsonify({"tracks": tracks})
    except Exception as e:
        return jsonify({"error": str(e), "tracks": []}), 500


@app.route("/api/playlist/<playlist_id>", methods=["DELETE"])
def delete_playlist_endpoint(playlist_id):
    """Delete (unfollow) a Spotify playlist by ID."""
    try:
        delete_playlist(playlist_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/spotify/status")
def spotify_status():
    """Return the current Spotify auth state."""
    return jsonify({"status": get_spotify_auth_status()})


@app.route("/api/spotify/auth")
def spotify_auth():
    """Redirect the browser to Spotify's authorization page."""
    return redirect(get_spotify_auth_url())



@app.route("/api/spotify/disconnect", methods=["POST"])
def spotify_disconnect():
    """Clear the cached Spotify token so the user can re-authenticate."""
    disconnect_spotify()
    return jsonify({"status": "ok"})


@app.route("/callback")
def spotify_callback():
    """Handle the OAuth callback from Spotify."""
    error = request.args.get("error")
    code = request.args.get("code")

    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>body{{background:#121212;color:#fff;font-family:sans-serif;'
        'text-align:center;padding:4rem 1rem}}'
        'h2{{margin-bottom:.5rem}}p{{color:#b3b3b3;max-width:480px;margin:0 auto}}'
        'a{{color:#1DB954;text-decoration:none}}a:hover{{text-decoration:underline}}'
        'code{{background:#282828;padding:2px 6px;border-radius:4px;font-size:.85em}}'
        '</style></head>'
        '<body><h2 style="color:{colour}">{icon} {title}</h2>'
        '{message}{script}</body></html>'
    )

    close_script = (
        '<script>'
        'if(window.opener){'
        'window.opener.postMessage("spotify-auth-complete","*");'
        'setTimeout(()=>window.close(),1500);'
        '}else{'
        'setTimeout(()=>window.location.href="/",1500);'
        '}'
        '</script>'
    )

    if error:
        desc = request.args.get("error_description", "")
        app_log(f"Spotify OAuth callback error: {error}")
        safe_error = html.escape(error)
        safe_desc = html.escape(desc)
        hint = (
            "<p style='margin-top:1.5rem;font-size:.85rem'>"
            "<strong>Common fix:</strong> make sure "
            "<code>http://127.0.0.1:5000/callback</code> "
            "(desktop) or <code>spotyvibe://callback</code> "
            "(Android) is listed as a Redirect URI in your "
            "<a href='https://developer.spotify.com/dashboard' target='_blank'>"
            "Spotify Developer Dashboard</a>.</p>"
            "<p style='margin-top:1rem'>"
            "<a href='/api/spotify/auth'>↻ Try again</a></p>"
        )
        return page.format(
            colour="#e74c3c", icon="❌", title="Authentication Failed",
            message=f"<p>{safe_error}</p>"
                    + (f"<p>{safe_desc}</p>" if safe_desc else "")
                    + hint,
            script="",
        )

    if code and handle_spotify_callback(code):
        return page.format(
            colour="#1DB954", icon="✅", title="Spotify Connected!",
            message="<p>You can close this window and return to the app.</p>",
            script=close_script,
        )

    return page.format(
        colour="#e74c3c", icon="❌", title="Authentication Failed",
        message="<p>Could not exchange the authorization code. Please try again.</p>"
               "<p style='margin-top:1rem'><a href='/api/spotify/auth'>↻ Try again</a></p>",
        script="",
    )


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host="127.0.0.1",
        port=5000,
        # The reloader forks a child process which crashes under Chaquopy
        use_reloader=False if IS_ANDROID else None,
    )

