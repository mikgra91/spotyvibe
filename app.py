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
from datetime import datetime, timezone


# Ensure the spotyvibe package directory is on sys.path so all
# imports resolve correctly regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, render_template, jsonify, request, redirect, stream_with_context, send_from_directory
from config import (
    load_config, get_credentials, save_credentials, save_settings,
    CREDENTIALS_FILE,
    BATCH_SIZE, BASE_DIR, get_model, get_settings, get_debug_mode,
    get_playlist_size, DEBUG_LOG_FILE, MAX_CONSECUTIVE_EMPTY_BATCHES,
    get_new_artist_percentage, get_gpt_language, PROFILE_IMPORT_MAX_BYTES,
    GENERAL_REQUEST_MAX_BYTES, MAX_GPT_CALLS_PER_RUN,
    MAX_CORE_DESCRIPTION_LEN, MAX_PROFILE_SECTION_LEN,
    MAX_FEEDBACK_REASON_LEN, MAX_FEEDBACK_ARTIST_LEN, MAX_FEEDBACK_TRACK_LEN,
    is_onboarding_completed, set_onboarding_completed, MAX_SONG_LIST_SIZE,
    _get_app_dir, get_active_profile_id, MAX_PROFILE_NAME_LEN,
    get_ui_language,
    EVAL_LOG_FILE, RAG_META_PATH, get_rag_enabled,
    RETRIEVE_CANDIDATES_SIZE, RAG_POPULARITY_PENALTY,
)
import markdown

load_config()


def _setup_logging():
    """Configure Python logging with file rotation and console output."""
    log_dir = DEBUG_LOG_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Delete stale log files *before* opening the file handler so the
    # RotatingFileHandler doesn't hold the file open when we try to unlink.
    from config import PROMPT_LOG_FILE
    for log_file in (DEBUG_LOG_FILE, PROMPT_LOG_FILE):
        try:
            if log_file.exists():
                log_file.unlink()
        except OSError:
            pass

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
    ch.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(ch)


_setup_logging()

# Module-level logger for handlers below the setup helpers.
logger = logging.getLogger(__name__)

from core.src.profile import (
    load_profile, save_profile, is_profile_trained,
    get_profile_status, train_profile, save_profile_sections,
    export_profile_dict, import_profile_dict,
    swap_profile_with_history,
    list_profiles, create_profile, delete_profile, activate_profile,
    draft_profile_from_playlist,
)
from core.src.suggestions import (
    normalize_history,
    build_messages, call_gpt, update_profile,
    filter_duplicate_suggestions,
    set_rag_corpus, get_rag_corpus,
    build_taste_summary, check_avoid_compliance, select_tracks,
    collect_forbidden_artists,
    get_last_rag_pool_names, get_last_prompt_components,
    set_last_rag_pool_names,
)
from core.src.feedback import like_track, dislike_track
from core.src.analysis import analyze_band_song
from core.src.history import save_run, load_runs, update_track_sentiment
from core.src.utils import get_openai_models, clear_debug_log, sanitize_text, safe_text, app_log
from core.src.eval_log import (log_batch_outcome, log_batch_summary,
                                compute_config_signature, log_stage2_summary)
from core.src.rag import retrieve_candidates
from core.src.openai_http import OpenAIConfigError, OpenAIError
from core.src.playlist import (
    search_tracks, add_to_playlist, remove_from_playlist, delete_playlist,
    get_spotify_auth_status, get_spotify_auth_url, handle_spotify_callback,
    disconnect_spotify, get_user_playlists, get_playlist_tracks,
    filter_emerging_artists, fetch_user_playlists, fetch_playlist_items_for_seed,
    get_spotify_client, get_spotify_access_token, get_spotify_session_info,
    remove_all_tracks_by_artist,
)
from core.src.taste import aggregate_taste

def _load_rag_corpus_if_enabled():
    """Load the RAG corpus at startup when the feature flag is on.

    Failures are logged and swallowed — a missing or broken corpus
    falls back to the legacy (non-RAG) prompt, never crashes boot.
    """
    try:
        from config import get_rag_enabled, RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH
        if not get_rag_enabled():
            return
        from core.src.rag import RagCorpus
        corpus = RagCorpus.load(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH)
        set_rag_corpus(corpus)
        logging.getLogger(__name__).info(
            "RAG corpus active: %d artists from %s", len(corpus), RAG_CORPUS_PATH)
    except FileNotFoundError:
        logging.getLogger(__name__).info(
            "RAG enabled but corpus file missing — running without candidate pool.")
    except Exception as exc:  # pragma: no cover — defensive
        logging.getLogger(__name__).warning("RAG corpus load failed: %s", exc)


# Populated once at startup by _check_rag_corpus_update(); exposed to the
# frontend via /api/config. Schema matches distribution.check_for_update().
_rag_update_status: dict = {"status": "unknown"}


def _check_rag_corpus_update():
    """Probe the GitHub-hosted manifest for a newer corpus version.

    Best-effort: a failed fetch (offline, rate-limited, 404) leaves the
    status as ``{"status": "offline"}`` and never blocks startup.
    """
    global _rag_update_status
    try:
        from config import RAG_CORPUS_PATH, RAG_META_PATH, RAG_MANIFEST_URL
        from core.src.rag.distribution import check_for_update
        _rag_update_status = check_for_update(
            RAG_CORPUS_PATH, RAG_META_PATH, RAG_MANIFEST_URL)
        logging.getLogger(__name__).info(
            "RAG update check: %s", _rag_update_status.get("status"))
    except Exception as exc:  # pragma: no cover — defensive
        logging.getLogger(__name__).info("RAG update check failed: %s", exc)
        _rag_update_status = {"status": "offline"}


def get_rag_update_status() -> dict:
    """Return the cached RAG update status (refreshed once per startup)."""
    return dict(_rag_update_status)


_load_rag_corpus_if_enabled()
_check_rag_corpus_update()


# Pricing sanity check — log any models we route LLM calls to that lack a
# pricing entry, so the cost estimator and the eval-log analyst know to
# treat their cost as missing rather than $0.
try:
    from config import validate_pricing_entries as _validate_pricing
    _missing_pricing = _validate_pricing()
    if _missing_pricing:
        logger.warning(
            "pricing.json missing entries for: %s — cost estimator will under-report",
            ", ".join(_missing_pricing),
        )
except Exception as _exc:  # pragma: no cover
    logger.debug("pricing validation skipped: %s", _exc)


app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = GENERAL_REQUEST_MAX_BYTES

# --- Performance: gzip compression for all responses ---
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    pass  # flask-compress is optional; skip if not installed

# --- Performance: Cache-Control for static assets ---
@app.after_request
def _add_cache_headers(response):
    if request.path.startswith('/static/'):
        if '/i18n/' in request.path:
            # Translation files: short cache so language updates propagate quickly
            response.headers['Cache-Control'] = 'public, max-age=300'  # 5 min
        else:
            # CSS, JS, images, fonts: cache for 1 day
            response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.template_filter("datetimeformat")
def _datetimeformat(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


# Model list cache: avoid repeated OpenAI API calls for the same data
_models_cache: dict = {"data": None, "expires": 0.0}
_MODELS_CACHE_TTL = 300  # 5 minutes

# Active generation runs: run_id → {"cancel": Event, "finalize_on_cancel": bool, "verified_tracks": [], "created_at": float}
_runs: dict = {}
_runs_lock = threading.Lock()
_STALE_RUN_SECONDS = 600  # 10 minutes

# Persistent song list file and lock
_SONGLIST_FILE = _get_app_dir() / "songlist.json"
_songlist_lock = threading.Lock()

# Spotify base62 IDs are 22 chars (track / playlist / album), but we accept
# anything that *looks* like a base62 id of plausible length so we don't
# blow up on future format tweaks. Used to reject obviously malformed
# client-supplied ids before we hand them to Spotipy.
_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{16,40}$")


def _safe_spotify_id(value):
    """Return *value* if it looks like a Spotify base62 ID, else None.

    A `None`/empty input is silently mapped to `None` (callers treat that
    as "no client hint"). A non-empty but malformed value is also mapped
    to `None` and logged — we'd rather fall back to the slow text-search
    path than pass garbage straight to the Spotify API.
    """
    if not value:
        return None
    if _SPOTIFY_ID_RE.match(value):
        return value
    logger.warning("Rejected malformed Spotify id from client: %r", value[:60])
    return None


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
        "rag_enabled": raw_settings.get("rag_enabled", False),
        "rag_corpus_available": raw_settings.get("rag_corpus_available", False),
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
    # Allow re-running the wizard even if onboarding was completed
    if request.args.get('replay') != '1' and is_onboarding_completed():
        return redirect('/')
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


@app.route("/api/onboarding/progress")
def onboarding_progress():
    """Return getting-started checklist progress derived from app state.

    Drives the frontend smart checklist (replaces the auto-tour). Each flag
    auto-checks based on real state, so completed steps never re-prompt.
    """
    creds = get_credentials()
    keys_saved = all(creds.get(k, {}).get("is_set") for k in
                     ("OPENAI_API_KEY", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"))
    spotify_connected = get_spotify_auth_status() == "authenticated"
    profile_created = bool(get_active_profile_id())
    feedback_count = 0
    playlist_generated = False
    if profile_created:
        try:
            playlist_generated = bool(load_runs())
        except Exception:
            pass
        try:
            prof = load_profile()
            fb = prof.get("feedback", {}) or {}
            feedback_count = len(fb.get("liked_tracks", []) or []) + len(fb.get("disliked_tracks", []) or [])
        except Exception:
            pass
    feedback_target = 3
    return jsonify({
        "keys_saved": keys_saved,
        "spotify_connected": spotify_connected,
        "profile_created": profile_created,
        "playlist_generated": playlist_generated,
        "feedback_count": feedback_count,
        "feedback_target": feedback_target,
        "feedback_done": feedback_count >= feedback_target,
    })


@app.route("/docs/screenshots/<path:filename>")
def docs_screenshot(filename):
    """Serve documentation screenshot images."""
    screenshot_dir = BASE_DIR / "documentation" / "assets" / "screenshots"
    return send_from_directory(str(screenshot_dir), filename)


@app.route("/docs/guides/<path:filename>")
def docs_guide_image(filename):
    """Serve setup guide images (screenshots for the setup guide overlays)."""
    guide_img_dir = BASE_DIR / "documentation" / "assets" / "guides"
    return send_from_directory(str(guide_img_dir), filename)


_GUIDE_SLUG_WHITELIST = {"openai_api_key", "spotify_developer_app", "python_install_macos", "python_install_linux"}


@app.route("/api/help/guide/<slug>")
def help_guide(slug):
    """Return a setup guide as structured JSON.

    Reads ``documentation/guides/<slug>.en.md``, parses YAML-like frontmatter
    and ``## Step N — Title`` sections into a JSON response.
    """
    if slug not in _GUIDE_SLUG_WHITELIST:
        return jsonify({"error": "Guide not found."}), 404

    # Try localised version first, fall back to English
    from core.src.localised_docs import resolve_guide
    lang = get_ui_language() or 'en'
    try:
        guide_path, served_lang, fallback_used = resolve_guide(slug, lang)
    except FileNotFoundError:
        return jsonify({"error": "Guide not found."}), 404

    raw = guide_path.read_text(encoding="utf-8")

    # Parse frontmatter (between --- lines)
    title = ""
    subtitle = ""
    body = raw
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        body = raw[fm_match.end():]
        for line in fm_text.strip().splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("subtitle:"):
                subtitle = line.split(":", 1)[1].strip().strip("\"'")

    # Parse steps: split on ## Step N — Title
    step_pattern = re.compile(r"^## Step \d+ — (.+)$", re.MULTILINE)
    splits = list(step_pattern.finditer(body))
    steps = []
    for i, m in enumerate(splits):
        step_title = m.group(1).strip()
        start = m.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(body)
        content = body[start:end].strip()

        # Extract optional image: ![alt](path)
        image = None
        img_match = re.search(r"!\[.*?\]\((.+?)\)", content)
        if img_match:
            image = img_match.group(1)
            content = content[:img_match.start()] + content[img_match.end():]

        # Extract optional copy block: ```copy ... ```
        copy = None
        copy_match = re.search(r"```copy\s*\n(.+?)\n```", content, re.DOTALL)
        if copy_match:
            copy = copy_match.group(1).strip()
            content = content[:copy_match.start()] + content[copy_match.end():]

        steps.append({
            "title": step_title,
            "description": content.strip(),
            "image": image,
            "copy": copy,
        })

    return jsonify({"title": title, "subtitle": subtitle, "steps": steps})


def _load_help_html(lang):
    """Load and render the help guide to HTML for the given language.

    Returns:
        Tuple of (html, served_lang, fallback_used).

    Raises:
        FileNotFoundError: If the help file doesn't exist in any language.
    """
    from core.src.localised_docs import resolve_help
    path, served_lang, fallback_used = resolve_help(lang)
    md_text = path.read_text(encoding="utf-8")
    html_content = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    return html_content, served_lang, fallback_used


@app.route("/api/help")
def help_content():
    """Return the help guide rendered as HTML, language-aware."""
    lang = get_ui_language() or 'en'
    try:
        html_content, served_lang, fallback_used = _load_help_html(lang)
        return jsonify({
            "html": html_content,
            "requested_lang": lang,
            "served_lang": served_lang,
            "fallback_used": fallback_used,
        })
    except FileNotFoundError:
        return jsonify({"error": "Help file not found."}), 404


def _extract_help_section(full_html, anchor):
    """Extract a single section from rendered help HTML by heading anchor ID.

    Supports two anchor styles:
    - Heading with id attribute (toc-generated): <h2 id="anchor">...</h2>
    - Named anchor before heading (translated files): <a id="anchor"></a><h2>...</h2>

    Returns everything from the matched heading up to (but not including)
    the next heading of the same or higher level. Trailing ``<hr>`` tags
    are stripped for cleaner display in the section-help popup.
    """
    # Style 1: heading element with id attribute (toc-generated, e.g. English)
    heading_pat = re.compile(
        rf'<h([2-6])\s[^>]*id="{re.escape(anchor)}"[^>]*>',
        re.IGNORECASE,
    )
    match = heading_pat.search(full_html)

    if match:
        heading_level = int(match.group(1))
        start = match.start()
        search_from = match.end()
    else:
        # Style 2: <a id="anchor"> immediately before a heading (translated files)
        anchor_tag_pat = re.compile(
            rf'<a\b[^>]*\bid="{re.escape(anchor)}"[^>]*>.*?</a>',
            re.IGNORECASE | re.DOTALL,
        )
        anchor_match = anchor_tag_pat.search(full_html)
        if not anchor_match:
            return None
        rest = full_html[anchor_match.end():]
        next_heading = re.search(r'<h([2-6])[\s>]', rest, re.IGNORECASE)
        if not next_heading:
            return None
        heading_level = int(next_heading.group(1))
        start = anchor_match.start()
        search_from = anchor_match.end() + next_heading.end()

    # Find the next heading at the same or higher level (lower number)
    levels = "".join(str(i) for i in range(1, heading_level + 1))
    after = full_html[search_from:]
    next_match = re.search(rf"<h[{levels}][\s>]", after, re.IGNORECASE)

    end = (search_from + next_match.start()) if next_match else len(full_html)
    section = full_html[start:end].strip()
    section = re.sub(r"\s*<hr\s*/?\s*>\s*$", "", section)
    return section


@app.route("/api/help/section/<anchor>")
def help_section(anchor):
    """Return a single help section by its heading anchor ID."""
    lang = get_ui_language() or 'en'
    try:
        full_html, served_lang, fallback_used = _load_help_html(lang)
        section_html = _extract_help_section(full_html, anchor)
        if not section_html:
            return jsonify({"error": "Section not found."}), 404
        return jsonify({"html": section_html, "fallback_used": fallback_used})
    except FileNotFoundError:
        return jsonify({"error": "Help file not found."}), 404


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
    emerging_only = bool(body.get("emerging_only"))
    # Wave 2: client-specified temperature (clamped to 0.0–2.0)
    client_temperature = body.get("temperature")
    if client_temperature is not None:
        try:
            client_temperature = float(client_temperature)
            client_temperature = max(0.0, min(2.0, client_temperature))
        except (TypeError, ValueError):
            client_temperature = None
    # Wave 2: client-specified playlist size (clamped to 5–30)
    client_playlist_size = body.get("playlist_size")
    if client_playlist_size is not None:
        try:
            client_playlist_size = int(client_playlist_size)
            client_playlist_size = max(5, min(30, client_playlist_size))
        except (TypeError, ValueError):
            client_playlist_size = None
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
            # Wave 2: client-specified size overrides server default
            if client_playlist_size is not None:
                playlist_size = client_playlist_size
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

            # P0.2: capture wall-clock latencies (per-batch and run-total) for
            # the eval log so Goal #3's p95 ≤ 60 s target is measurable.
            _run_t0 = time.monotonic()
            _batch_latencies: list[float] = []

            # Forward declarations populated by the staged-pipeline block below
            # so _emit_batch_summary can read them without conditionally importing.
            _stage1_candidates: list = []
            _approved_names: list[str] = []
            _stage2_meta: dict = {}
            _config_sig_cache: str | None = None

            # In-run ephemeral deny: tracks GPT suggested that Spotify could
            # not verify. Without this, GPT keeps re-suggesting the same
            # hallucinated track names every batch (since they never enter
            # history — only verified tracks do). Capped to keep the prompt
            # small; the suggestions module further trims to the 20 most
            # recent before injection.
            _run_unverified: list[dict] = []
            _RUN_UNVERIFIED_CAP = 80

            def _build_config_signature(batch_size_used: int) -> str:
                """Build the eval-log config_signature for this run/batch.

                Adds ``phase1_pipeline`` to ``extra`` so legacy vs staged runs
                bucket cleanly in pandas. Cached per batch so signature is
                stable across batch_summary and stage2_summary rows.
                """
                rag_pool_size_cfg = None
                rag_stratified_cfg = None
                try:
                    from config import (RAG_POOL_SIZE as _RPS,
                                        RAG_STRATIFIED as _RST)
                    rag_pool_size_cfg = _RPS
                    rag_stratified_cfg = _RST
                except ImportError:
                    pass
                return compute_config_signature(
                    rag_enabled=get_rag_enabled(),
                    rag_pool_size=rag_pool_size_cfg,
                    rag_stratified=rag_stratified_cfg,
                    effective_batch_size=batch_size_used,
                    extra={
                        "compact_json": True,
                        "stripped_track_arrays": True,
                        "phase1_pipeline": _use_staged_pipeline,
                    },
                )

            def _emit_batch_summary(*, llm_meta, gpt_returned_count, after_filter_count,
                                     spotify_found_count, in_pool_count,
                                     batch_size_used, suggested_playlist,
                                     schema_collapse=None):
                """Best-effort write of one ``batch_summary`` row to eval.jsonl.

                Failure is logged as a warning — telemetry must never break a run.
                """
                try:
                    rag_enabled_now = get_rag_enabled()
                    components = get_last_prompt_components() or {}
                    rag_pool_size_cfg = None
                    rag_stratified_cfg = None
                    try:
                        from config import (RAG_POOL_SIZE as _RPS,
                                            RAG_STRATIFIED as _RST)
                        rag_pool_size_cfg = _RPS
                        rag_stratified_cfg = _RST
                    except ImportError:
                        pass

                    # Per-track in_candidate_pool measures membership in the
                    # binding constraint set: Stage 2 approved (staged path)
                    # or the legacy RAG pool (legacy path).
                    if _use_staged_pipeline:
                        per_track_pool_names = _approved_names
                    else:
                        per_track_pool_names = get_last_rag_pool_names()

                    log_batch_summary(
                        run_id=run_id,
                        batch_num=batch_num,
                        model=get_model(),
                        rag_enabled=rag_enabled_now,
                        rag_corpus_meta_path=RAG_META_PATH,
                        profile_id=get_active_profile_id(),
                        profile=profile,
                        eval_log_path=EVAL_LOG_FILE,
                        debug_mode=get_debug_mode(),
                        effective_batch_size=batch_size_used,
                        rag_pool_size=rag_pool_size_cfg,
                        rag_stratified=rag_stratified_cfg,
                        candidate_pool_names=per_track_pool_names,
                        prompt_components=components,
                        usage=llm_meta.get("usage"),
                        latency_s=llm_meta.get("latency_s"),
                        gpt_returned_count=gpt_returned_count,
                        after_filter_count=after_filter_count,
                        spotify_found_count=spotify_found_count,
                        in_pool_count=in_pool_count,
                        consecutive_empty_batches=consecutive_empty_batches,
                        config_signature=_build_config_signature(batch_size_used),
                        suggested_playlist=suggested_playlist,
                        stage1_candidate_count=len(_stage1_candidates) if _use_staged_pipeline else None,
                        stage2_approved_count=len(_approved_names) if _use_staged_pipeline else None,
                        schema_collapse=schema_collapse,
                    )
                except Exception as _exc:  # pragma: no cover — never break a run
                    logger.warning("log_batch_summary skipped: %s", _exc)

            # ── Phase 1: three-stage pipeline pre-computation ────────────────
            # Stage 1 (code-side retrieval) + Stage 2 (avoid-compliance mini
            # LLM) run once per generation run, before the batching loop.
            # Stage 3 (select_tracks) is then called per batch.
            #
            # Activated when RAG is enabled and the corpus is loaded.
            # Falls back to the existing build_messages + call_gpt path otherwise.
            _corpus = get_rag_corpus()
            _use_staged_pipeline = _corpus is not None and get_rag_enabled() and not emerging_only

            _taste_summary: str = ""
            _avoid_traits: list[str] = []
            _approved_top_tracks: dict = {}

            if _use_staged_pipeline:
                try:
                    yield _sse("progress", message="Stage 1: building candidate pool…")
                    # deny_keys = forbidden artists + history (for novelty).
                    # 2026-04-27: confirmed anchors are NO LONGER added to
                    # deny_keys — they are precisely the artists the model
                    # has the strongest discography knowledge for, and
                    # excluding them was a load-bearing source of obscurity
                    # in the candidate pool (driving the schema-collapse
                    # regression). Stage 1's popularity penalty + tag
                    # scoring still prevents the pool from collapsing to
                    # confirmed-only output, and Stage 3's "≥ min_new_artists
                    # not in accepted list" constraint preserves discovery.
                    _deny_keys = collect_forbidden_artists(profile)
                    _history_names = {
                        a.lower().strip()
                        for a in profile.get("history", {}).get("suggested_artists", [])
                    }
                    _deny_keys = _deny_keys | _history_names
                    _stage1_candidates = retrieve_candidates(
                        _corpus, profile,
                        deny_keys=_deny_keys,
                        target_size=RETRIEVE_CANDIDATES_SIZE,
                        popularity_penalty=RAG_POPULARITY_PENALTY,
                    )
                    set_last_rag_pool_names([a.name for a in _stage1_candidates])

                    _avoid_traits = (profile.get("preferences", {}) or {}).get("avoid") or []
                    if isinstance(_avoid_traits, str):
                        _avoid_traits = [_avoid_traits]

                    if _stage1_candidates:
                        yield _sse("progress",
                                   message=f"Stage 2: avoid-compliance check on {len(_stage1_candidates)} candidates…")
                        _approved_names, _stage2_meta = check_avoid_compliance(
                            [a.name for a in _stage1_candidates],
                            _avoid_traits,
                        )
                    else:
                        _approved_names = []
                        _stage2_meta = {"status": "skipped_empty_input",
                                        "latency_s": None, "usage": None,
                                        "model": None, "prompt_chars": 0}

                    # Distinguish three cases when _approved_names is empty:
                    #   (a) Stage 1 returned nothing — fall back to legacy.
                    #   (b) Stage 2 errored out — check_avoid_compliance falls
                    #       back internally to the full candidate list, so this
                    #       branch is unreachable for status="error".
                    #   (c) Stage 2 correctly rejected ALL candidates (empty
                    #       response or every artist matched an avoid trait) —
                    #       falling back to legacy hides this from the user;
                    #       continue with empty approved and surface a warning.
                    if not _approved_names and not _stage1_candidates:
                        logger.warning("Stage 1 returned no candidates — falling back to legacy path")
                        _use_staged_pipeline = False
                    elif not _approved_names:
                        logger.warning(
                            "Stage 2 rejected all %d candidates — staying on staged path with empty approved list",
                            len(_stage1_candidates),
                        )
                        _taste_summary = build_taste_summary(profile)
                        yield _sse("progress",
                                   message="Stage 2 rejected all candidates — Stage 3 will surface this as no tracks.")
                    else:
                        _taste_summary = build_taste_summary(profile)
                        yield _sse("progress",
                                   message=f"Stage 2 approved {len(_approved_names)} artists. Starting track selection…")

                    # Build a name → top_tracks lookup for Stage 3 grounding
                    # (2026-04-27 schema-collapse follow-up). Empty list when
                    # the corpus / overlay has no tracks for that artist —
                    # Stage 3's anti-confab clause then takes over.
                    _approved_top_tracks = {}
                    if _stage1_candidates:
                        _approved_lower = {n.lower().strip() for n in _approved_names}
                        for a in _stage1_candidates:
                            key = (a.name or "").lower().strip()
                            if key and key in _approved_lower:
                                _approved_top_tracks[key] = list(a.top_tracks or [])[:5]
                except Exception as _stage_exc:
                    logger.warning("Phase 1 staging failed (%s) — falling back to legacy path", _stage_exc)
                    _use_staged_pipeline = False

                # Stage 2 telemetry — one row per generation run.
                try:
                    if _stage2_meta:
                        log_stage2_summary(
                            run_id=run_id,
                            model=(_stage2_meta.get("model") or get_model()),
                            profile_id=get_active_profile_id(),
                            profile=profile,
                            eval_log_path=EVAL_LOG_FILE,
                            debug_mode=get_debug_mode(),
                            candidates_in=len(_stage1_candidates),
                            approved_out=len(_approved_names),
                            avoid_traits_count=len(_avoid_traits),
                            status=_stage2_meta.get("status", "ok"),
                            latency_s=_stage2_meta.get("latency_s"),
                            usage=_stage2_meta.get("usage"),
                            prompt_chars=_stage2_meta.get("prompt_chars"),
                            config_signature=_build_config_signature(BATCH_SIZE),
                        )
                except Exception as _exc:  # pragma: no cover
                    logger.warning("log_stage2_summary skipped: %s", _exc)

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

                # Adaptive temperature: lower on retries for more deterministic output.
                base_temp = client_temperature if client_temperature is not None else 0.7
                floor = 0.0 if client_temperature is not None else 0.3
                temperature = max(floor, base_temp - (consecutive_empty_batches * 0.2))

                gpt_call_count += 1
                if _use_staged_pipeline:
                    # Phase 1 path: Stage 3 select_tracks uses approved artists
                    # and compact taste summary — no deny list, no full profile JSON.
                    result, _llm_meta = select_tracks(
                        _approved_names,
                        _taste_summary,
                        request_count,
                        profile,
                        accepted_tracks=accepted,
                        recently_filtered_tracks=(
                            (last_filtered_tracks or []) + _run_unverified
                        ) or None,
                        new_artist_percentage=effective_nap,
                        batch_num=batch_num,
                        audio_filters=audio_filters or None,
                        emerging_only=emerging_only,
                        temperature=temperature,
                        approved_top_tracks=_approved_top_tracks or None,
                    )
                else:
                    # Legacy path: full build_messages + call_gpt (RAG disabled
                    # or corpus not loaded or emerging_only mode).
                    messages = build_messages(
                        profile,
                        accepted_tracks=accepted,
                        batch_size=request_count,
                        recently_filtered_tracks=(
                            (last_filtered_tracks or []) + _run_unverified
                        ) or None,
                        new_artist_percentage=effective_nap,
                        batch_num=batch_num,
                        audio_filters=audio_filters or None,
                        emerging_only=emerging_only,
                    )
                    result, _llm_meta = call_gpt(messages, temperature=temperature, return_meta=True)

                _batch_latencies.append(_llm_meta.get("latency_s") or 0.0)
                _gpt_returned_count = len(result.get("playlist", []))

                # ── HC2 violation detector (2026-04-27 diagnostic) ──
                # Stage 3's HC2 says "ONLY suggest tracks by artists in the
                # APPROVED_ARTISTS list". When the model violates this we
                # only used to find out via Spotify-search misses, which
                # masks the root cause. Surface it directly here so the
                # log line says "le grand sbam (NOT IN POOL)" rather than
                # forcing us to cross-reference two systems later.
                if _use_staged_pipeline:
                    _approved_lower = {n.lower().strip() for n in (_approved_names or [])}
                    _stage3_picks = result.get("playlist", []) if isinstance(result, dict) else []
                    _hc2_violations = []
                    for _entry in _stage3_picks:
                        _a = (_entry.get("artist") or "").lower().strip()
                        if _a and _a not in _approved_lower:
                            _hc2_violations.append(f"{_a} - {_entry.get('track', '')}")
                    if _hc2_violations:
                        logger.warning(
                            "[HC2 VIOLATION] Stage 3 returned %d/%d picks "
                            "for artists OUTSIDE the approved pool. "
                            "Approved pool size=%d. Out-of-pool picks: %s",
                            len(_hc2_violations), len(_stage3_picks),
                            len(_approved_lower), _hc2_violations[:10],
                        )
                    else:
                        logger.info(
                            "[HC2 OK] Stage 3 returned %d picks, all in "
                            "approved pool (size=%d).",
                            len(_stage3_picks), len(_approved_lower),
                        )

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

                    _emit_batch_summary(
                        llm_meta=_llm_meta,
                        gpt_returned_count=_gpt_returned_count,
                        after_filter_count=0,
                        spotify_found_count=0,
                        in_pool_count=0,
                        batch_size_used=request_count,
                        suggested_playlist=[],
                        schema_collapse=result.get("_schema_collapse"),
                    )

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

                # Build the ephemeral in-run deny set from this batch's
                # Spotify misses. _run_unverified holds {artist, track} dicts
                # so the suggestions module can hash them the same way as
                # accepted/filtered tracks — strings would crash the lookup.
                _found_keys_set = {
                    (t["artist"].lower().strip(), t["track"].lower().strip())
                    for t in found
                }
                for t in result["playlist"]:
                    key = (t["artist"].lower().strip(),
                           t["track"].lower().strip())
                    if key not in _found_keys_set:
                        _run_unverified.append({"artist": t["artist"],
                                                "track": t["track"]})
                if len(_run_unverified) > _RUN_UNVERIFIED_CAP:
                    _run_unverified = _run_unverified[-_RUN_UNVERIFIED_CAP:]

                # ── Eval log: one JSONL row per suggested track ────────
                # Lets us measure hallucination rate / candidate-pool hit
                # rate offline (see TechnicalManual.md §"RAG design
                # reference" → Hallucination measurement). Gated on debug
                # mode inside the helper.
                # We pull the *actual* pool the LLM was prompted with from
                # suggestions.get_last_rag_pool_names() — re-scoring here
                # would waste CPU and silently drift if the scoring logic
                # ever changes.
                try:
                    _pool_names = get_last_rag_pool_names()
                    _found_keys = [f"{t['artist']} - {t['track']}" for t in found]
                    log_batch_outcome(
                        run_id=run_id,
                        batch_num=batch_num,
                        model=get_model(),
                        rag_enabled=get_rag_enabled(),
                        rag_corpus_meta_path=RAG_META_PATH,
                        candidate_pool_names=_pool_names,
                        profile_id=get_active_profile_id(),
                        profile=profile,
                        suggested_playlist=result["playlist"],
                        found_keys=_found_keys,
                        eval_log_path=EVAL_LOG_FILE,
                        debug_mode=get_debug_mode(),
                    )
                    _pool_set = ({n.lower().strip() for n in _pool_names if n}
                                 if _pool_names is not None else set())
                    _in_pool_count = sum(
                        1 for t in result["playlist"]
                        if (t.get("artist") or "").lower().strip() in _pool_set
                    ) if _pool_set else 0
                    _emit_batch_summary(
                        llm_meta=_llm_meta,
                        gpt_returned_count=_gpt_returned_count,
                        after_filter_count=len(result["playlist"]),
                        spotify_found_count=len(found),
                        in_pool_count=_in_pool_count,
                        batch_size_used=request_count,
                        suggested_playlist=result["playlist"],
                        schema_collapse=result.get("_schema_collapse"),
                    )
                except Exception as _exc:  # pragma: no cover — never break a run
                    logger.warning("eval_log_outcome skipped: %s", _exc)

                # When emerging_only is active, discard tracks whose release_date
                # predates the 6-month cutoff window.
                if emerging_only and found:
                    found, _rejected = filter_emerging_artists(found, cutoff_months=6)
                    if _rejected:
                        yield _sse(
                            "progress",
                            message=f"Batch {batch_num}: {len(_rejected)} track(s) filtered out (emerging artists only).",
                            emerging_filtered=len(_rejected),
                        )


                for t in found:
                    if t["uri"] not in verified_uris:
                        verified_tracks.append(t)
                        verified_uris.add(t["uri"])

                # Keep run state updated so the cancel endpoint can report progress
                with _runs_lock:
                    if run_id in _runs:
                        _runs[run_id]["verified_tracks"] = list(verified_tracks)

                # 4 — Update history (in memory; saved once after loop)
                # Only Spotify-verified tracks land in history. Without this
                # restriction, GPT-suggested tracks that fail Spotify lookup
                # still inflate per-artist counts, pushing artists past
                # EXHAUSTED_ARTIST_THRESHOLD (= 4) even though no playlist
                # ever contained them — which poisons the candidate pool
                # for all subsequent batches in the same run.
                verified_artist_keys = sorted(
                    {t["artist"].lower().strip() for t in found}
                )
                verified_track_entries = [
                    {"artist": t["artist"].lower().strip(),
                     "track": t["track"].lower().strip()}
                    for t in found
                ]
                result["profile_updates"] = {
                    "suggested_artists": verified_artist_keys,
                    "suggested_tracks": verified_track_entries,
                }
                profile = update_profile(profile, result)

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: {len(found)} found on Spotify, "
                            f"{len(verified_tracks)}/{playlist_size} total verified",
                )
                # Inform the UI how many tracks we have so far (drives the
                # "Use X tracks now" button label)
                yield _sse("batch_verified", count=len(verified_tracks), total=playlist_size)

            # P0.2: emit run-level latency baseline (Goal #3 measurability).
            try:
                from core.src.eval_log import log_run_summary
                log_run_summary(
                    run_id=run_id,
                    model=get_model(),
                    profile_id=get_active_profile_id(),
                    eval_log_path=EVAL_LOG_FILE,
                    debug_mode=get_debug_mode(),
                    batch_count=batch_num,
                    batch_latencies_s=_batch_latencies,
                    total_wall_s=time.monotonic() - _run_t0,
                    verified_count=len(verified_tracks),
                    playlist_size=playlist_size,
                    gpt_call_count=gpt_call_count,
                )
            except Exception as _exc:  # pragma: no cover
                logger.warning("log_run_summary skipped: %s", _exc)

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

            # Persist accumulated profile updates (history) once after all batches
            save_profile(profile)

            # Cap at target count — skip when emerging_only so all survivors are shown
            emerging_checked = len(verified_tracks)
            if not emerging_only:
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
                with _songlist_lock:
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
                playlist_id=playlist_info.get("playlist_id"),
                added=playlist_info.get("added", 0),
                not_found=all_not_found,
                was_cancelled=was_cancelled or gpt_exhausted,
                **({"emerging_shown": len(visible_playlist), "emerging_checked": emerging_checked} if emerging_only else {}),
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
    artist = safe_text(data, "artist")
    track  = safe_text(data, "track") or None
    reason = safe_text(data, "reason") or None
    playlist_id = _safe_spotify_id(safe_text(data, "playlist_id") or None)
    track_id    = _safe_spotify_id(safe_text(data, "track_id") or None)

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
            # Stamp sentiment in run history for dashboard charts
            if track:
                update_track_sentiment(artist, track, "liked")
        else:
            dislike_track(artist, track=track, reason=reason)
            # Stamp sentiment in run history for dashboard charts
            if track:
                update_track_sentiment(artist, track, "disliked")
            # Also remove the track from the Spotify playlist
            if track:
                removal = remove_from_playlist(
                    artist, track,
                    playlist_id=playlist_id,
                    track_id=track_id,
                )
            else:
                removal = {"removed": False, "reason": "No track specified"}

        response: dict = {"status": "ok"}
        if removal is not None:
            response["removal"] = removal
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feedback/dislike-artist", methods=["POST"])
def dislike_artist_purge():
    """Artist-level dislike that also strips every track by that artist
    from the active playlist (Item 6, 2026-04).

    Frontend should show a confirmation dialog **before** calling this
    endpoint — there is no further confirmation server-side.

    Body: {"artist": str, "playlist_id": str, "reason": str (optional)}
    Returns: {"status": "ok", "removal": {...}}
    """
    data = request.get_json(force=True)
    artist = safe_text(data, "artist")
    playlist_id = _safe_spotify_id(safe_text(data, "playlist_id") or None)
    reason = safe_text(data, "reason") or None

    if not artist:
        return jsonify({"error": "Artist is required."}), 400
    if len(artist) > MAX_FEEDBACK_ARTIST_LEN:
        return jsonify({"error": f"Artist name too long (max {MAX_FEEDBACK_ARTIST_LEN} chars)."}), 400
    if reason and len(reason) > MAX_FEEDBACK_REASON_LEN:
        reason = reason[:MAX_FEEDBACK_REASON_LEN]

    try:
        # 1. Persist the artist-level dislike (no track ⇒ artist-level).
        dislike_track(artist, track=None, reason=reason)
        # 2. Strip the active playlist.
        removal = remove_all_tracks_by_artist(artist, playlist_id=playlist_id)
        return jsonify({"status": "ok", "removal": removal})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove", methods=["POST"])
def remove_track():
    """Remove a track from the Spotify playlist without recording feedback."""
    data   = request.get_json(force=True)
    artist = safe_text(data, "artist")
    track  = safe_text(data, "track")
    playlist_id = _safe_spotify_id(safe_text(data, "playlist_id") or None)
    track_id    = _safe_spotify_id(safe_text(data, "track_id") or None)

    if not artist or not track:
        return jsonify({"error": "Artist and track are required."}), 400

    try:
        result = remove_from_playlist(
            artist, track,
            playlist_id=playlist_id,
            track_id=track_id,
        )
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
    payload = get_settings()
    payload["rag_update"] = get_rag_update_status()
    return jsonify(payload)


@app.route("/api/rag/download-corpus", methods=["POST"])
def download_rag_corpus():
    """Download (or update) the RAG corpus from the GitHub manifest URL.

    Idempotent: the file is streamed to a ``.part`` sibling, sha256-
    verified against the manifest, then atomically renamed. On success,
    the in-memory corpus handle is swapped and the update-check status
    is refreshed.
    """
    try:
        from config import (RAG_CORPUS_PATH, RAG_META_PATH, RAG_MANIFEST_URL,
                            RAG_TAG_ALIASES_PATH)
        from core.src.rag import RagCorpus
        from core.src.rag.distribution import (
            download_corpus, fetch_remote_manifest,
        )
        manifest = fetch_remote_manifest(RAG_MANIFEST_URL)
        if manifest is None:
            return jsonify({"error": "remote_unavailable"}), 503
        download_corpus(manifest, RAG_CORPUS_PATH, RAG_META_PATH)
        set_rag_corpus(RagCorpus.load(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH))
        _check_rag_corpus_update()
        return jsonify({
            "status": "ok",
            "corpus_version": manifest.corpus_version,
            "size_bytes": manifest.size_bytes,
        })
    except ValueError as exc:  # sha mismatch
        return jsonify({"error": "checksum_failed", "detail": str(exc)}), 502
    except Exception as exc:  # pragma: no cover — defensive
        app_log(f"RAG download failed: {exc}")
        return jsonify({"error": "download_failed", "detail": str(exc)}), 500


@app.route("/api/settings", methods=["POST"])
def write_settings():
    """Update non-secret settings (model, debug mode, playlist size)."""
    data = request.get_json(force=True)
    payload = {}
    if "model" in data:
        payload["OPENAI_MODEL"] = data["model"]

    if "debug_mode" in data:
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
        lang = safe_text(data, "gpt_language")
        if lang:
            payload["GPT_LANGUAGE"] = lang
    if "ui_language" in data:
        payload["UI_LANGUAGE"] = safe_text(data, "ui_language")

    # Wave 4: Provider preset + base URL
    valid_presets = {"openai", "ollama", "lmstudio", "groq", "openrouter"}
    if "provider_preset" in data:
        preset = safe_text(data, "provider_preset")
        if preset in valid_presets:
            payload["PROVIDER_PRESET"] = preset
    if "llm_base_url" in data:
        url = safe_text(data, "llm_base_url")
        if url:
            payload["LLM_BASE_URL"] = url

    if "rag_enabled" in data:
        payload["RAG_ENABLED"] = "true" if data["rag_enabled"] else "false"

    save_settings(payload)
    app_log(f"Settings changed: {list(payload.keys())}")

    # Hot-swap the RAG corpus handle when the toggle flips. Avoids the
    # need to restart the app for the flag to take effect.
    if "rag_enabled" in data:
        try:
            from config import get_rag_enabled, RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH
            from core.src.rag import RagCorpus
            if get_rag_enabled():
                set_rag_corpus(RagCorpus.load(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH))
            else:
                set_rag_corpus(None)
        except FileNotFoundError:
            set_rag_corpus(None)
        except Exception as exc:
            app_log(f"RAG toggle load failed: {exc}")

    return jsonify({"status": "ok"})


@app.route("/api/llm/fetch_models", methods=["POST"])
def fetch_llm_models():
    """Proxy a GET {base_url}/models to fetch available models from a provider."""
    data = request.get_json(silent=True) or {}
    base_url = safe_text(data, "base_url")
    api_key = data.get("api_key", "")

    # Fall back to stored credential when caller doesn't provide a key
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    if not base_url:
        return jsonify({"error": "base_url is required"}), 400

    # SSRF mitigation: only allow https:// or http:// on localhost/127.0.0.1
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    is_local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme == "http" and not is_local:
        return jsonify({"error": "Only HTTPS is allowed for remote providers."}), 400
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "Invalid URL scheme."}), 400

    # Determine timeout: 2s for localhost, 5s for remote
    timeout = 2 if is_local else 5

    models_url = base_url.rstrip("/") + "/models"

    try:
        import urllib.request
        import urllib.error

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        model_ids = []
        for item in payload.get("data", []):
            mid = item.get("id", "")
            if mid:
                model_ids.append(mid)

        return jsonify({"models": sorted(model_ids)})
    except Exception as e:
        app.logger.warning("Fetch models failed for %s: %s", base_url, e)
        return jsonify({"error": str(e)}), 502


@app.route("/api/settings/open-data-dir", methods=["POST"])
def open_data_dir():
    """Open the app data directory in the OS file explorer.

    Uses platform-appropriate commands: os.startfile (Windows),
    xdg-open (Linux), open (macOS).
    """
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
    """Clear the debug log file."""
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
    artist = safe_text(data, "artist")
    track = safe_text(data, "track")

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


@app.route("/api/profile/prompt-size")
def profile_prompt_size():
    """Return prompt-slice char counts for the live profile.

    Used by the cost estimator (P0.1) so it can compute realistic per-batch
    token costs against the *actual* serialised profile + deny set + RAG pool,
    not against the train-form textareas (which omit ~3/4 of the real prompt).

    Response shape::

        {"trained": bool,
         "batch_size": 10,
         "system_chars": int,
         "user_chars": int,
         "profile_chars": int,
         "deny_chars": int,
         "pool_chars": int,
         "feedback_chars": int,
         "ai_update_chars": int}        # estimated train-profile prompt size

    ``ai_update_chars`` is an estimate — the train_profile prompt sends the
    full profile JSON and expects an updated profile back. The estimator uses
    profile size × 2 plus a fixed system-prompt overhead.
    """
    if not get_active_profile_id() or not is_profile_trained():
        return jsonify({"trained": False})
    try:
        profile = load_profile()
        normalize_history(profile)
        msgs = build_messages(profile, batch_size=BATCH_SIZE)
        components = get_last_prompt_components() or {}
        # Rough AI Profile Update size: profile JSON sent + returned, plus
        # ~1500 chars system overhead. Real number depends on user input
        # length; this is a consistent-direction estimate for the UI.
        profile_chars = components.get("profile") or len(json.dumps(profile, separators=(",", ":")))
        ai_update_chars = profile_chars * 2 + 1500
        return jsonify({
            "trained": True,
            "batch_size": BATCH_SIZE,
            "system_chars": len(msgs[0]["content"]),
            "user_chars": len(msgs[1]["content"]),
            "profile_chars": profile_chars,
            "deny_chars": components.get("deny_set", 0),
            "pool_chars": components.get("pool", 0),
            "feedback_chars": components.get("feedback", 0),
            "ai_update_chars": ai_update_chars,
        })
    except Exception as exc:
        app.logger.warning("prompt-size endpoint failed: %s", exc)
        return jsonify({"trained": False, "error": str(exc)}), 500


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




def _parse_profile_sections(data, require_description=False):
    """Parse and validate profile section fields from request data.

    Args:
        data: Parsed JSON request body.
        require_description: If True, at least one of vibe/core description must be non-empty.

    Returns:
        Tuple of (sections_dict, error_response_or_None).
        If error_response is not None, the caller should return it immediately.
    """
    vibe_description = safe_text(data, "vibe_description")
    core_description = safe_text(data, "core_description")

    if require_description and not core_description and not vibe_description:
        return None, (jsonify({"error": "Either a vibe description or core description is required."}), 400)
    if core_description and len(core_description) > MAX_CORE_DESCRIPTION_LEN:
        return None, (jsonify({"error": f"Core description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400)
    if vibe_description and len(vibe_description) > MAX_CORE_DESCRIPTION_LEN:
        return None, (jsonify({"error": f"Vibe description too long (max {MAX_CORE_DESCRIPTION_LEN} chars)."}), 400)

    sections = {
        "vibe_description": vibe_description,
        "core_description": core_description,
        "must_have": safe_text(data, "must_have")[:MAX_PROFILE_SECTION_LEN],
        "soft_preferences": safe_text(data, "soft_preferences")[:MAX_PROFILE_SECTION_LEN],
        "avoid": safe_text(data, "avoid")[:MAX_PROFILE_SECTION_LEN],
    }
    return sections, None


@app.route("/api/train-profile", methods=["POST"])
def train_profile_endpoint():
    """Send the user's structured taste description to GPT and update the profile."""
    data = request.get_json(force=True)

    sections, error = _parse_profile_sections(data, require_description=True)
    if error:
        return error

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

    sections, error = _parse_profile_sections(data, require_description=False)
    if error:
        return error

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


# ── Wave 3: Playlist seed, taste aggregate ───────────────────────────

@app.route("/api/spotify/playlists_for_seed")
def api_playlists_for_seed():
    """Return user's Spotify playlists for the seed picker."""
    if get_spotify_auth_status() != "authenticated":
        return jsonify({"error": "not_authenticated"}), 401
    try:
        playlists = fetch_user_playlists(limit=50)
        return jsonify({"playlists": playlists})
    except Exception as e:
        app.logger.exception("Failed to fetch playlists for seed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile/seed_from_playlist", methods=["POST"])
def api_seed_from_playlist():
    """Draft a taste profile from a Spotify playlist."""
    data = request.get_json(silent=True) or {}
    pid = data.get("playlist_id")
    if not pid:
        return jsonify({"error": "missing_playlist_id"}), 400
    if get_spotify_auth_status() != "authenticated":
        return jsonify({"error": "not_authenticated"}), 401

    try:
        summary = fetch_playlist_items_for_seed(pid)

        # Compute top genres from artist metadata if we have artist_ids
        # Note: audio features API was removed Feb 2026, so we pass descriptive values
        top_genres = []
        try:
            sp = get_spotify_client()
            artist_ids = summary.get("artist_ids", [])[:50]
            if artist_ids:
                # Batch fetch artist details (max 50 per request)
                artists_data = sp.artists(artist_ids)
                genre_counts = {}
                for a in artists_data.get("artists", []):
                    for g in (a.get("genres") or []):
                        genre_counts[g] = genre_counts.get(g, 0) + 1
                top_genres = sorted(genre_counts.keys(), key=lambda g: genre_counts[g], reverse=True)[:5]
        except Exception:
            pass

        summary["top_genres"] = top_genres
        summary["energy"] = "moderate"
        summary["valence"] = "moderate"
        summary["tempo"] = "120"
        summary["moods"] = ["mixed"]

        draft = draft_profile_from_playlist(summary)

        meta = {
            "playlist_id": pid,
            "playlist_name": summary["name"],
            "track_count": summary["track_count"],
            "top_genres": summary.get("top_genres", [])[:5],
            "top_artists": summary.get("top_artists", [])[:5],
            "drafted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return jsonify({"draft": draft, "meta": meta})
    except Exception as e:
        app.logger.exception("Seed draft failed")
        return jsonify({"error": "draft_failed", "detail": str(e)}), 502


@app.route("/api/taste/aggregate")
def api_taste_aggregate():
    """Return aggregated taste data for the dashboard."""
    try:
        runs = load_runs()
        profile = load_profile()
        aggregated = aggregate_taste(runs, profile=profile)
        return jsonify(aggregated)
    except Exception as e:
        app.logger.exception("Taste aggregation failed")
        return jsonify({"error": str(e)}), 500





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
    with _songlist_lock:
        _SONGLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SONGLIST_FILE.write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, count=len(songs))


@app.route("/api/songlist/track", methods=["DELETE"])
def delete_songlist_track():
    """Permanently remove a specific track from the persistent song list."""
    data = request.get_json(force=True)
    artist = sanitize_text(data.get("artist", "")).strip()
    track = sanitize_text(data.get("track", "")).strip()
    with _songlist_lock:
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


@app.route("/api/session")
def api_session():
    """Return per-session info the frontend needs to pick a playback path.

    Includes ``is_premium`` so preview.js can branch between the Web
    Playback SDK and the iframe fallback.
    """
    info = get_spotify_session_info()
    info["authenticated"] = get_spotify_auth_status() == "authenticated"
    return jsonify(info)


@app.route("/api/spotify/token")
def api_spotify_token():
    """Return a fresh Spotify access token for the Web Playback SDK.

    The SDK invokes this via its ``getOAuthToken`` callback. Tokens are
    never embedded in HTML; they're fetched on demand.
    """
    if get_spotify_auth_status() != "authenticated":
        return jsonify({"error": "not_authenticated"}), 401
    token = get_spotify_access_token()
    if not token:
        return jsonify({"error": "no_token"}), 401
    return jsonify({"access_token": token})


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
            "is listed as a Redirect URI in your "
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
        # Enable threaded mode so API calls (settings, feedback, status)
        # are not blocked while an SSE generation stream is active.
        threaded=True,
    )

