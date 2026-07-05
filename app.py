import html
import ipaddress
import logging
import logging.handlers
import math
import os
import re
import socket
import sys
import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse


# Ensure the spotyvibe package directory is on sys.path so all
# imports resolve correctly regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, render_template, jsonify, request, redirect, stream_with_context, send_from_directory
from config import (
    load_config, get_credentials, save_credentials, save_settings,
    CREDENTIALS_FILE,
    BATCH_SIZE, BASE_DIR, get_model, get_settings, get_debug_mode,
    get_playlist_size, DEBUG_LOG_FILE, MAX_CONSECUTIVE_EMPTY_BATCHES,
    MAX_TRACKS_PER_ARTIST_PER_PLAYLIST,
    get_new_artist_percentage, get_gpt_language, PROFILE_IMPORT_MAX_BYTES,
    GENERAL_REQUEST_MAX_BYTES, MAX_GPT_CALLS_PER_RUN,
    MAX_CORE_DESCRIPTION_LEN, MAX_PROFILE_SECTION_LEN,
    MAX_FEEDBACK_REASON_LEN, MAX_FEEDBACK_ARTIST_LEN, MAX_FEEDBACK_TRACK_LEN,
    is_onboarding_completed, set_onboarding_completed, MAX_SONG_LIST_SIZE,
    _get_app_dir, get_active_profile_id, MAX_PROFILE_NAME_LEN,
    get_ui_language,
    EVAL_LOG_FILE, RAG_META_PATH, get_rag_enabled,
    RETRIEVE_CANDIDATES_SIZE, RAG_POPULARITY_PENALTY, RAG_RERETRIEVE_SIZE,
    get_or_create_secret_key, get_filter_ai_artists,
)
from core.src.ai_filter import filter_ai_tracks
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
    swap_profile_with_history, recover_orphaned_swap_tmps,
    list_profiles, create_profile, delete_profile, activate_profile,
    draft_profile_from_playlist,
)
from core.src.suggestions import (
    normalize_history,
    build_messages, call_gpt, update_profile,
    filter_duplicate_suggestions,
    set_rag_corpus, get_rag_corpus,
    build_taste_summary, build_focused_taste_summary,
    check_avoid_compliance, select_tracks, select_artists,
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
from core.src.rag import retrieve_candidates, retrieve_anchor_candidates
from core.src import rerank as _taste_rerank
from core.src.openai_http import OpenAIConfigError, OpenAIError
from core.src.errors import TranslatableError, as_response_payload
from core.src.playlist import (
    search_tracks, iter_search_tracks, add_to_playlist, remove_from_playlist,
    delete_playlist,
    get_spotify_auth_status, get_spotify_auth_url, handle_spotify_callback,
    disconnect_spotify, get_user_playlists, get_playlist_tracks,
    filter_emerging_artists, fetch_user_playlists, fetch_playlist_items_for_seed,
    get_spotify_client, get_spotify_access_token, get_spotify_session_info,
    remove_all_tracks_by_artist,
    spotify_cooldown_remaining_s, is_spotify_in_cooldown,
)
from core.src.taste import aggregate_taste

def _load_rag_corpus_if_enabled():
    """Load the RAG corpus at startup when the feature flag is on.

    Failures are logged and swallowed — a missing or broken corpus
    falls back to the legacy (non-RAG) prompt, never crashes boot.
    """
    log = logging.getLogger(__name__)
    try:
        from config import (get_rag_enabled, use_sqlite_corpus,
                            RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH)
        if not get_rag_enabled():
            return
        from core.src.rag import RagCorpus

        # Packaged installs use the on-disk SQLite corpus: built once (~30s the
        # first time / after a corpus update) then opened in ~20ms every launch.
        # Any failure falls through to the in-memory path so boot never breaks.
        if use_sqlite_corpus():
            try:
                from config import RAG_CORPUS_DB_PATH
                from core.src.rag.sqlite_corpus import (
                    SqliteCorpus, build_sqlite_corpus, corpus_signature,
                    is_sqlite_corpus_valid)
                sig = corpus_signature(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH)
                if not is_sqlite_corpus_valid(RAG_CORPUS_DB_PATH, sig):
                    log.info("Building SQLite corpus (first run / corpus changed)…")
                    ram = RagCorpus.load(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH)
                    build_sqlite_corpus(ram, RAG_CORPUS_DB_PATH, sig)
                    del ram
                corpus = SqliteCorpus.open(RAG_CORPUS_DB_PATH)
                set_rag_corpus(corpus)
                log.info("RAG corpus active (SQLite): %d artists from %s",
                         len(corpus), RAG_CORPUS_DB_PATH)
                return
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("SQLite corpus unavailable (%s) — falling back to in-memory.", exc)

        corpus = RagCorpus.load(RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH)
        set_rag_corpus(corpus)
        log.info("RAG corpus active: %d artists from %s", len(corpus), RAG_CORPUS_PATH)
    except FileNotFoundError:
        log.info("RAG enabled but corpus file missing — running without candidate pool.")
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("RAG corpus load failed: %s", exc)


def _load_ai_blocklist():
    """Load the AI-artist blocklist at startup if the file is present.

    Best-effort and independent of the FILTER_AI_ARTISTS toggle — we keep the
    deny set in memory whenever the file exists so flipping the toggle takes
    effect without a restart. A missing file leaves the filter inert.
    """
    try:
        from config import AI_BLOCKLIST_PATH
        from core.src.ai_filter import load_ai_blocklist
        if AI_BLOCKLIST_PATH.exists():
            load_ai_blocklist(AI_BLOCKLIST_PATH)
    except Exception as exc:  # pragma: no cover — defensive
        logging.getLogger(__name__).warning("AI blocklist load failed: %s", exc)


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


try:
    _n_recovered = recover_orphaned_swap_tmps()
    if _n_recovered:
        logger.info("Recovered %d orphan profile swap-tmp file(s) at startup", _n_recovered)
except Exception as exc:  # pragma: no cover — defensive
    logger.warning("Profile swap-tmp recovery failed: %s", exc)

# Loaded synchronously at import so the corpus is guaranteed present before the
# server accepts requests. (Backgrounding this was tried and reverted: in the
# pywebview desktop build the GUI/CLR main loop starves a background loader
# thread of the GIL — the corpus took >40s and generation would stall. The
# desktop splash covers the load instead; see desktop_launcher.py.)
_load_rag_corpus_if_enabled()
_load_ai_blocklist()
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
app.secret_key = get_or_create_secret_key()
app.config["MAX_CONTENT_LENGTH"] = GENERAL_REQUEST_MAX_BYTES
# Session cookie hardening (WS1): scope cookies to same-site, no JS access.
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

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
    # Security headers (WS4) — defense-in-depth, non-breaking on every
    # response. nosniff stops MIME-confusion; DENY blocks clickjacking
    # (the app is never framed; the desktop webview is not an iframe);
    # same-origin Referrer-Policy avoids leaking paths to external links.
    # NOTE: a Content-Security-Policy is intentionally deferred — the app
    # uses ~80-120 inline event handlers, so even report-only CSP floods
    # the console (breaking console-assertion tests) and needs the
    # handler→listener migration first. See HARDENING_PLAN.md WS4.
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    return response


# --- Security: same-origin guard for state-changing requests (WS1) ---
# SpotyVibe binds to loopback, but other web pages in the user's browser can
# still issue cross-origin requests to 127.0.0.1 (CSRF) — including to the
# credential-storage endpoint. For mutating methods we require the request's
# Origin (or Referer) to be same-origin or a loopback host; everything else
# is rejected with 403. GET/HEAD/OPTIONS are never blocked.
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _header_host(value):
    """Hostname of an Origin/Referer header value (or None)."""
    if not value:
        return None
    try:
        return urlparse(value).hostname
    except ValueError:
        return None


def _request_is_loopback():
    host = _header_host("//" + (request.host or ""))
    return (host or "") in _LOOPBACK_HOSTS


@app.before_request
def _csrf_origin_guard():
    if request.method in _CSRF_SAFE_METHODS:
        return None
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    src = origin if origin is not None else referer
    if src is None:
        # A cross-origin fetch always sends Origin, so a request with neither
        # header is normally a same-origin or native (pywebview) caller. Allow
        # only when we are bound to loopback (the desktop default); log it.
        if _request_is_loopback():
            return None
        logger.warning("Blocked mutating %s %s: no Origin/Referer on non-loopback host %s",
                       request.method, request.path, request.host)
        return jsonify({"error": "Origin required."}), 403
    same_origin = urlparse(src).netloc == request.host
    if same_origin or _header_host(src) in _LOOPBACK_HOSTS:
        return None
    logger.warning("Blocked cross-origin mutating %s %s from %s",
                   request.method, request.path, src)
    return jsonify({"error": "Cross-origin request rejected."}), 403


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


def _taste_rerank_enabled() -> bool:
    """Whether the taste re-ranker ("Ground then Judge") Stage-1 path is active.

    Default ON; set ``SPOTYVIBE_TASTE_RERANK=0`` to fall back to the legacy prose
    retrieval. The path builds an anchor-seeded candidate pool and orders it with
    an LLM taste re-rank — validated in .dev-notes/corpus-diag-2026-07-05/
    (tag/vector retrieval ranks this taste at chance; the re-ranker does not).
    """
    return os.environ.get("SPOTYVIBE_TASTE_RERANK", "1") != "0"


def _sanitize_audio_filters(raw):
    """Structurally sanitise client audio filters (WS2).

    Keep only known audio-feature keys, each with numeric-or-None ``min`` /
    ``max``. Drops malformed shapes (non-dict, non-numeric, unknown keys) so
    downstream filtering never sees an unexpected type. No value range is
    imposed — ``tempo`` is BPM, the others are 0-1 — this is type/shape
    hardening only.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in _DEFAULT_AUDIO_FILTERS:
        spec = raw.get(key)
        if not isinstance(spec, dict):
            continue
        clean = {}
        for bound in ("min", "max"):
            v = spec.get(bound)
            if v is None:
                clean[bound] = None
            else:
                try:
                    clean[bound] = float(v)
                except (TypeError, ValueError):
                    clean[bound] = None
        out[key] = clean
    return out


def _is_internal_host(hostname):
    """True if *hostname* resolves to a non-loopback private/reserved address.

    SSRF guard for user-supplied provider URLs (WS2/F8). Loopback is allowed
    (local LLMs are first-class) and public hosts are allowed (custom
    OpenAI-compatible providers), but RFC1918 / link-local (incl. the
    169.254.169.254 cloud-metadata endpoint) / reserved ranges are blocked.
    """
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False  # unresolvable → let the request fail naturally downstream
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_loopback:
            continue
        if (ip.is_private or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return True
    return False


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


_GUIDE_SLUG_WHITELIST = {"openrouter_api_key", "openai_api_key", "spotify_developer_app", "python_install_macos", "python_install_linux"}


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


def _build_taste_summary_for_pool(profile, stage1_candidates, approved_names):
    """Pick the taste-summary builder based on env + facet count.

    Default path: ``build_taste_summary(profile)`` — preserves prior
    behaviour for profiles of all sizes (CLAUDE.md North Star rule #1,
    no regression on any model).

    Focused path: when ``SPOTYVIBE_FOCUSED_TASTE=1`` is set AND the
    profile carries more facets than the focus threshold (default 12),
    score must_have/soft/avoid items against the approved-pool's tag
    distribution and keep the top-K per section. Lets eval A/B the
    "smart compaction" lever on large profiles without flipping the
    default. See ``build_focused_taste_summary`` in suggestions.py.
    """
    use_focused = os.environ.get("SPOTYVIBE_FOCUSED_TASTE") == "1"
    if not use_focused:
        return build_taste_summary(profile)

    try:
        threshold = int(
            os.environ.get("SPOTYVIBE_FOCUSED_TASTE_THRESHOLD", "12")
        )
    except (TypeError, ValueError):
        threshold = 12

    prefs = (profile or {}).get("preferences", {}) or {}
    facet_n = (
        len(prefs.get("must_have") or [])
        + len(prefs.get("soft_preferences") or [])
        + len(prefs.get("avoid") or [])
    )
    if facet_n <= threshold:
        return build_taste_summary(profile)

    try:
        top_k = int(
            os.environ.get("SPOTYVIBE_FOCUSED_TASTE_TOP_K", "10")
        )
    except (TypeError, ValueError):
        top_k = 10

    approved_lower = {n.lower().strip() for n in (approved_names or [])}
    pool_tags: list[str] = []
    for a in (stage1_candidates or []):
        key = (getattr(a, "name", "") or "").lower().strip()
        if approved_lower and key not in approved_lower:
            continue
        for t in (getattr(a, "tags", None) or []):
            if isinstance(t, str) and t.strip():
                pool_tags.append(t)

    if not pool_tags:
        return build_taste_summary(profile)

    logger.info(
        "[taste_summary] focused mode active — facet_n=%d, top_k=%d, "
        "pool_tag_n=%d",
        facet_n, top_k, len(pool_tags),
    )
    return build_focused_taste_summary(
        profile, pool_tags=pool_tags, top_k_per_section=top_k,
    )


def _classify_unknown_exception(exc):
    """U2: best-effort classification for exceptions not carrying their own
    ``error_class`` / ``key`` attrs — most importantly spotipy's
    ``SpotifyException`` which is a third-party type we can't subclass.

    Returns a dict suitable for splatting into ``_sse('error', ...)``.
    """
    try:
        from spotipy.exceptions import SpotifyException as _SpotifyException
    except Exception:  # pragma: no cover - import guard
        _SpotifyException = ()  # type: ignore[assignment]
    if _SpotifyException and isinstance(exc, _SpotifyException):
        status = getattr(exc, "http_status", None)
        if status == 429:
            return {
                "error_class": "transient",
                "error_key": "error.transient.spotify_rate_limited",
            }
        if status in (502, 503, 504):
            return {
                "error_class": "transient",
                "error_key": "error.transient.spotify_unavailable",
            }
    return {}


def _sse_error(exc_or_message):
    """Emit an SSE ``error`` event with i18n-aware payload.

    Accepts either a :class:`TranslatableError` (or any exception with a
    ``key`` attribute) or a plain string. Sends ``message`` for backwards
    compatibility plus ``error_key`` / ``error_params`` / ``error_class``
    when available.
    """
    if isinstance(exc_or_message, BaseException):
        payload = as_response_payload(exc_or_message)
        kwargs = {"message": payload["error"]}
        if "error_key" in payload:
            kwargs["error_key"] = payload["error_key"]
        if "error_params" in payload:
            kwargs["error_params"] = payload["error_params"]
        if "error_class" in payload:
            kwargs["error_class"] = payload["error_class"]
        else:
            kwargs.update(_classify_unknown_exception(exc_or_message))
        return _sse("error", **kwargs)
    return _sse("error", message=str(exc_or_message))


def _add_tracks_to_suggested(profile, tracks):
    """Add tracks to suggested_tracks in the profile (distinct by artist+track key)."""
    history = profile.setdefault("history", {})
    existing = history.get("suggested_tracks", [])
    existing_keys = {
        (e.get("artist", "").lower().strip(), e.get("track", "").lower().strip())
        for e in existing
    }
    new_entries = []
    for t in tracks:
        key = (t.get("artist", "").lower().strip(), t.get("track", "").lower().strip())
        if key not in existing_keys and key[0] and key[1]:
            new_entries.append({"artist": key[0], "track": key[1]})
            existing_keys.add(key)
    if new_entries:
        history["suggested_tracks"] = existing + new_entries
        existing_artists = set(history.get("suggested_artists", []))
        for entry in new_entries:
            existing_artists.add(entry["artist"])
        history["suggested_artists"] = sorted(existing_artists)
        save_profile(profile)


def _should_widen_pool_on_low_found_rate(
    *,
    batch_num: int,
    cum_stage3_returned: int,
    cum_spotify_found: int,
    use_staged_pipeline: bool,
    reretrieve_done: bool,
    corpus_loaded: bool,
    min_batches: int = 2,
    threshold: float = 0.3,
) -> bool:
    """Q3 (2026-05-23): trigger condition for the low-found-rate A6
    pool widening.

    Returns True when the cumulative Spotify-found rate has fallen
    below *threshold* after at least *min_batches* completed batches
    and re-retrieve hasn't already been attempted this run. The
    existing A6 trigger (`consecutive_empty_batches`) only sees
    post-dedup-empty batches; this catches the Spotify-cascade
    failure mode (production trace 435c7016: 4/30 verified across
    7 batches at 7% Spotify-found, never tripped the old trigger).
    """
    if not (use_staged_pipeline and corpus_loaded) or reretrieve_done:
        return False
    if batch_num < min_batches:
        return False
    if cum_stage3_returned <= 0:
        return False
    return (cum_spotify_found / cum_stage3_returned) < threshold


def _enforce_per_artist_cap(tracks: list, cap: int) -> list:
    """2026-05-30: reorder a verified-track list so no artist exceeds *cap*
    in the leading (kept) portion, with the overflow appended after.

    This is a STABLE reorder, not a filter — every input track survives, so
    the playlist's fill count never regresses. The first ``cap`` tracks per
    artist are front-loaded; anything beyond the cap is pushed to the tail
    and only surfaces if the diverse set alone can't fill the target size.

    Motivation: field testing produced playlists of 3 artists × 5 tracks
    when the candidate pool was thin. Concentrating a playlist on a handful
    of bands makes a single artist-dislike wipe most of it — exactly the
    chain reaction users complained about.
    """
    if cap <= 0:
        return tracks
    from collections import defaultdict
    counts: dict = defaultdict(int)
    primary: list = []
    overflow: list = []
    for t in tracks:
        key = (t.get("artist") or "").lower().strip()
        if counts[key] < cap:
            counts[key] += 1
            primary.append(t)
        else:
            overflow.append(t)
    return primary + overflow


def _prune_dead_tracks_from_overlay(
    approved_top_tracks: dict | None,
    verified_tracks: list,
    run_unverified: list,
) -> dict | None:
    """Q2 (2026-05-23): drop already-verified + already-failed-verify
    tracks from the per-batch `approved_top_tracks` overlay.

    Production trace 435c7016 showed Spotify-found rate collapsing
    batch-over-batch because Stage 3 kept seeing the SAME `known:`
    track titles every batch and re-picking ones that had already
    failed Spotify resolution. Stripping them here makes each batch's
    overlay strictly smaller than the last, so the model is forced
    onto a different choice the moment a track has been tried.

    Returns the same shape (dict[str, list[str]]) with dead tracks
    removed. Returns the input unchanged when there's nothing to prune.
    """
    if not approved_top_tracks:
        return approved_top_tracks
    dead_keys = set()
    for entries, _src in ((verified_tracks, "verified"),
                          (run_unverified, "unverified")):
        for t in entries or []:
            a = (t.get("artist") or "").lower().strip()
            tk = (t.get("track") or "").lower().strip()
            if a and tk:
                dead_keys.add((a, tk))
    if not dead_keys:
        return approved_top_tracks
    pruned = {}
    for artist_key, tracks in approved_top_tracks.items():
        live = [
            t for t in (tracks or [])
            if (artist_key, (t or "").lower().strip()) not in dead_keys
        ]
        pruned[artist_key] = live
    return pruned


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
    # Audio feature filters: {"energy": {"min": 0.6, "max": 1.0}, ...}
    audio_filters = _sanitize_audio_filters(body.get("audio_filters"))
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
        # M3 (2026-05-07): closure-shared state read by the finally block
        # for the perf-log row. Survives every termination path (return,
        # exception, GeneratorExit) — a generator's locals snapshot is
        # not reliable in a finally that runs after the iterator closes.
        _run_state = {
            "tracks_found": 0,
            "tracks_target": 0,
            "exhausted": False,
            "error": None,
        }
        try:
            if not is_profile_trained():
                yield _sse(
                    "error",
                    message="Please train your taste profile first.",
                    error_key="error.profile.not_trained",
                )
                return

            # Verify Spotify is connected before starting the expensive GPT pipeline.
            # N3 (2026-05-13): the eval harness can opt out of this check
            # by setting the env var ``SPOTYVIBE_SKIP_SPOTIFY_CONNECT=1``
            # before importing this module. Used together with
            # ``--verify-mode null`` (or any non-spotify verifier) so a
            # probe-style run can exercise the full Stage-1+2+3 pipeline
            # on a machine that has never authorized Spotify. NEVER set
            # this in a user-facing context — the production flow needs
            # Spotify to push the verified playlist.
            spotify_status = get_spotify_auth_status()
            _skip_spotify_check = os.environ.get(
                "SPOTYVIBE_SKIP_SPOTIFY_CONNECT", ""
            ).strip().lower() in ("1", "true", "yes")
            if spotify_status != "authenticated" and not _skip_spotify_check:
                yield _sse(
                    "error",
                    message="Spotify is not connected. Please connect via ⚙️ Settings first.",
                    error_key="error.spotify.not_connected",
                )
                return

            # P0 (2026-05-24): refuse to start a run while a Spotify
            # long-cooldown is active. The verify pipeline would just
            # short-circuit every pick to not_found, burning LLM cost
            # for a guaranteed-empty playlist. Surface a clear error
            # with the wait time so the user knows when to retry.
            _cd_seconds = spotify_cooldown_remaining_s()
            if _cd_seconds > 0 and not _skip_spotify_check:
                _cd_minutes = (_cd_seconds + 59) // 60
                yield _sse(
                    "error",
                    message=(
                        f"Spotify rate-limit cooldown active "
                        f"(~{_cd_minutes} min remaining). Please try again later."
                    ),
                    error_key="error.spotify.cooldown",
                    error_params={"seconds_remaining": _cd_seconds},
                )
                return

            # Clear debug log at the start of each run so it only
            # contains data from the current generation.
            if get_debug_mode():
                clear_debug_log()

            app_log(f"Generation run started: run_id={run_id}")

            playlist_size = get_playlist_size()
            # Wave 2: client-specified size overrides server default
            if client_playlist_size is not None:
                playlist_size = client_playlist_size
            _run_state["tracks_target"] = int(playlist_size)
            new_artist_percentage = get_new_artist_percentage()

            yield _sse("progress", message="Loading profile…")
            profile = load_profile()
            normalize_history(profile)

            # F9 (2026-05-01): start the per-run trace bundle. No-op
            # when DEBUG_MODE is off. Captures profile snapshot now so
            # downstream feedback writes during generation don't
            # contaminate the snapshot. Finalised in the `finally`
            # below so partial runs / cancellations still produce a
            # diagnostic trace.
            try:
                from core.src import trace as _trace
                _trace.start_trace(run_id, profile=profile)
            except Exception as _exc:
                app_log(f"trace.start_trace failed: {_exc}")

            # L2 (2026-05-06): bracket the multi-batch generation in a
            # per-run Spotify search-result cache. Closed in the
            # ``finally`` below so cancellations / errors never leave
            # stale cache state for the next run.
            try:
                from core.src import playlist as _pl_cache
                _pl_cache.start_run_search_cache()
            except Exception as _exc:
                app_log(f"playlist.start_run_search_cache failed: {_exc}")

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

            # Q3 (2026-05-23): cumulative spotify-found tracking. Drives
            # the low-found-rate A6 trigger (production post-mortem
            # showed a 4/30 fill at 7% found-rate with A6 never firing
            # because dedup filter was passing the batches and the
            # `consecutive_empty_batches` trigger only sees post-filter
            # empties, not the Spotify cascade).
            _cum_stage3_returned = 0
            _cum_spotify_found = 0

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
                        # Tier 1 (2026-05-10) — diagnostics from llm_meta:
                        # system_fingerprint detects silent OpenAI model rolls;
                        # prompt_hashes catches inadvertent prompt drift;
                        # stage3_mode audits the L5 selector at call time.
                        system_fingerprint=llm_meta.get("system_fingerprint"),
                        prompt_hashes=llm_meta.get("prompt_hashes"),
                        stage3_mode=llm_meta.get("stage3_mode"),
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
            # OPEN-4 (2026-04-28): Stage-1 pool widening on POOL_BAD was
            # implemented and reverted. It cost +1 free Stage-1 + 1 cheap
            # Stage-2 per run as designed, but downstream the doubled
            # candidate pool inflated subsequent Stage-3 prompts (~2× user
            # message size) and Spotify-search volume, contributing to
            # measured cost regressions and 429 rate-limit cascades during
            # multi-model evals. Re-enable only with stricter guards.

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

                    # Phase 2.5 (P2.2 fix, 2026-04-27): plumb the user's
                    # north-star reference into Stage 1 so the 15 % facet
                    # quota in score_artists_stratified actually fires.
                    # Pre-fix the quota was silently absorbed by flat-fill.
                    # Source priorities:
                    #  1) profile.meta.primary_reference dict (preferred)
                    #  2) profile.meta.primary_reference string + analysis dict
                    #  3) latest band/song analysis result if available
                    _meta = profile.get("meta", {}) if isinstance(profile, dict) else {}
                    _primary_ref = _meta.get("primary_reference")
                    if isinstance(_primary_ref, str):
                        # Legacy string form — wrap as dict so the retrieval
                        # helper can ingest it. analysis text fallback is
                        # whatever build_taste_summary already surfaces.
                        _primary_ref = {"name": _primary_ref, "analysis": _primary_ref}
                    elif not isinstance(_primary_ref, dict):
                        _primary_ref = None

                    # E1 (2026-05-06): wall-clock for the full Stage 1
                    # body (stratified scorer + must-have/avoid filters
                    # + popularity band). No-op when DEBUG_MODE off.
                    from core.src import trace as _e1_trace
                    with _e1_trace.time_stage(_e1_trace.STAGE_RAG_RETRIEVE):
                        if _taste_rerank_enabled():
                            # "Ground then Judge": anchor-seeded wide pool (real
                            # taste-adjacent artists) → LLM taste re-rank → trim.
                            # Tag/prose retrieval alone ranks the user's taste at
                            # ~chance; the re-ranker lifts it decisively (see
                            # .dev-notes/corpus-diag-2026-07-05/).
                            _wide = retrieve_anchor_candidates(
                                _corpus, profile,
                                deny_keys=_deny_keys,
                                target_size=RAG_RERETRIEVE_SIZE,
                            )
                            _reranked = _taste_rerank.rerank_pool(
                                profile, _wide, model=get_model(),
                            )
                            _stage1_candidates = _reranked[:RETRIEVE_CANDIDATES_SIZE]
                            yield _sse("progress",
                                       message=f"Taste re-rank: ordered {len(_wide)} "
                                               f"candidates, kept top {len(_stage1_candidates)}.")
                        else:
                            _stage1_candidates = retrieve_candidates(
                                _corpus, profile,
                                deny_keys=_deny_keys,
                                target_size=RETRIEVE_CANDIDATES_SIZE,
                                popularity_penalty=RAG_POPULARITY_PENALTY,
                                primary_reference=_primary_ref,
                            )
                    set_last_rag_pool_names([a.name for a in _stage1_candidates])
                    if _primary_ref:
                        logger.info(
                            "[Stage 1] primary_reference active: %r",
                            _primary_ref.get("name") or "(unnamed)",
                        )

                    _avoid_traits = (profile.get("preferences", {}) or {}).get("avoid") or []
                    if isinstance(_avoid_traits, str):
                        _avoid_traits = [_avoid_traits]

                    if _stage1_candidates:
                        # L1 (2026-04-29): fetch Stage 1's avoid-overlap flag
                        # so check_avoid_compliance can short-circuit when
                        # Stage 1's tag-based avoid filter already cleared
                        # the pool — saves the LLM call entirely. See
                        # `cost-speed-research.md` lever L1.
                        from core.src.rag.retrieval import get_last_retrieval_meta
                        _retrieval_meta = get_last_retrieval_meta() or {}
                        _pool_overlap = _retrieval_meta.get("pool_avoid_overlap")
                        _traits_fully_covered = bool(
                            _retrieval_meta.get("avoid_traits_fully_covered")
                        )
                        yield _sse("progress",
                                   message=f"Stage 2: avoid-compliance check on {len(_stage1_candidates)} candidates…")
                        _approved_names, _stage2_meta = check_avoid_compliance(
                            [a.name for a in _stage1_candidates],
                            _avoid_traits,
                            pool_avoid_overlap=_pool_overlap,
                            avoid_traits_fully_covered=_traits_fully_covered,
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
                        _taste_summary = _build_taste_summary_for_pool(
                            profile, _stage1_candidates, _approved_names
                        )
                        yield _sse("progress",
                                   message="Stage 2 rejected all candidates — Stage 3 will surface this as no tracks.")
                    else:
                        _taste_summary = _build_taste_summary_for_pool(
                            profile, _stage1_candidates, _approved_names
                        )
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

                    # Diagnostic: snapshot the pool the batching loop will
                    # run against, so a trace post-mortem can answer "did
                    # the pool have enough material to fill N tracks?".
                    try:
                        from core.src import trace as _diag_trace
                        if _diag_trace.is_active():
                            _coverage = sum(
                                1 for n in _approved_names
                                if _approved_top_tracks.get((n or "").lower().strip())
                            )
                            _diag_trace.record("run_pool_initial", {
                                "stage1_size": len(_stage1_candidates),
                                "stage2_approved_size": len(_approved_names),
                                "approved_names": list(_approved_names),
                                "approved_top_tracks_coverage": _coverage,
                                "avoid_traits": list(_avoid_traits),
                                "primary_reference": (
                                    _primary_ref.get("name") if isinstance(_primary_ref, dict) else None
                                ),
                                "playlist_size": playlist_size,
                                "batch_size": BATCH_SIZE,
                            })
                    except Exception as _diag_exc:  # pragma: no cover
                        logger.debug("trace run_pool_initial skipped: %s", _diag_exc)
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
            last_found_rate = None  # OPEN-1 exp2: adaptive ask-size
            _rag_reretrieve_done = False  # A6: one-shot pool re-retrieve guard

            while len(verified_tracks) < playlist_size:
                # ── Check for cancellation before each expensive GPT call ──
                if cancel_event.is_set():
                    was_cancelled = True
                    break

                # Q3 (2026-05-23): low-found-rate A6 trigger. The existing
                # A6 path only fires on `consecutive_empty_batches` AFTER
                # the dedup filter — it misses the Spotify-cascade failure
                # mode where every batch returns 10 picks but Spotify
                # resolves 0-1 of them (production trace 435c7016:
                # 4/30 verified across 7 batches at 7% found-rate, A6
                # never fired). Fire pool widening when:
                #   (a) at least 2 batches have completed,
                #   (b) cumulative found-rate < 0.3,
                #   (c) re-retrieve hasn't already been attempted this run,
                #   (d) the staged pipeline is in use and a corpus is loaded.
                # The re-retrieve uses the same path A6 uses today (just
                # promoted to fire earlier on this failure shape).
                if _should_widen_pool_on_low_found_rate(
                    batch_num=batch_num,
                    cum_stage3_returned=_cum_stage3_returned,
                    cum_spotify_found=_cum_spotify_found,
                    use_staged_pipeline=_use_staged_pipeline,
                    reretrieve_done=_rag_reretrieve_done,
                    corpus_loaded=_corpus is not None,
                ):
                    _rag_reretrieve_done = True
                    _old_pool_size = len(_approved_names)
                    _found_rate_pct = round(
                        100 * _cum_spotify_found / _cum_stage3_returned, 1
                    )
                    logger.warning(
                        "[Q3] low spotify-found rate %.1f%% after batch %d — "
                        "triggering pool re-retrieve (old_pool=%d)",
                        _found_rate_pct, batch_num, _old_pool_size,
                    )
                    yield _sse(
                        "progress",
                        message=(
                            f"Spotify resolved only {_cum_spotify_found}/"
                            f"{_cum_stage3_returned} picks ({_found_rate_pct}%) — "
                            f"widening candidate pool…"
                        ),
                    )
                    try:
                        from core.src import trace as _e1_trace
                        with _e1_trace.time_stage(_e1_trace.STAGE_RAG_RETRIEVE):
                            _stage1_candidates = retrieve_candidates(
                                _corpus, profile,
                                deny_keys=_deny_keys,
                                target_size=RAG_RERETRIEVE_SIZE,
                                popularity_penalty=0.0,
                                primary_reference=_primary_ref,
                            )
                        set_last_rag_pool_names(
                            [a.name for a in _stage1_candidates])
                        if _stage1_candidates:
                            from core.src.rag.retrieval import get_last_retrieval_meta
                            _rr_meta = get_last_retrieval_meta() or {}
                            _approved_names, _stage2_meta = check_avoid_compliance(
                                [a.name for a in _stage1_candidates],
                                _avoid_traits,
                                pool_avoid_overlap=_rr_meta.get("pool_avoid_overlap"),
                                avoid_traits_fully_covered=bool(
                                    _rr_meta.get("avoid_traits_fully_covered")),
                            )
                            if _approved_names:
                                _taste_summary = _build_taste_summary_for_pool(
                                    profile, _stage1_candidates, _approved_names)
                                _approved_top_tracks = {}
                                _rr_lower = {n.lower().strip() for n in _approved_names}
                                for a in _stage1_candidates:
                                    key = (a.name or "").lower().strip()
                                    if key and key in _rr_lower:
                                        _approved_top_tracks[key] = list(a.top_tracks or [])[:5]
                                logger.info(
                                    "[Q3] re-retrieve widened approved pool %d → %d artists",
                                    _old_pool_size, len(_approved_names))
                                yield _sse(
                                    "progress",
                                    message=(
                                        f"Pool widened to {len(_approved_names)} "
                                        f"artists — continuing…"
                                    ),
                                )
                    except Exception as _rr_exc:
                        logger.warning(
                            "[Q3] low-found-rate re-retrieve failed (%s) — "
                            "continuing with old pool", _rr_exc)

                batch_num += 1
                remaining = playlist_size - len(verified_tracks)
                # Request either a full batch or just the remaining count
                request_count = min(BATCH_SIZE, remaining)
                # OPEN-1 exp2: adaptive ask-size when Spotify-found rate <40%.
                if (os.environ.get("SPOTYVIBE_ADAPTIVE_ASK") == "1"
                        and last_found_rate is not None
                        and last_found_rate < 0.4
                        and remaining > 0):
                    request_count = min(20, max(request_count, math.ceil(remaining / 0.4)))

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: "
                            f"Asking the AI for {request_count} suggestions… "
                            f"(have {len(verified_tracks)}/{playlist_size})",
                )

                # 1 — Ask GPT for suggestions.
                # On retries after all-filtered batches, pass the filtered tracks
                # explicitly so GPT cannot claim it didn't know about them.
                accepted = verified_tracks if batch_num > 1 else None
                # Hard cost guardrail. OPEN-1: when a run is below 60 % of
                # target after batch 3, allow up to 6 calls (was 4) — adds
                # ~$0 for pool-starved runs, rescues underfilled ones.
                effective_max_calls = MAX_GPT_CALLS_PER_RUN
                if batch_num > 3 and len(verified_tracks) < 0.6 * playlist_size:
                    effective_max_calls = max(MAX_GPT_CALLS_PER_RUN, 6)
                if gpt_call_count >= effective_max_calls:
                    yield _sse(
                        "progress",
                        message=f"Reached the AI call limit ({effective_max_calls}). "
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
                    # Q2 (2026-05-23): per-batch overlay pruning. Production
                    # post-mortem showed Spotify-found rate collapsing
                    # run-over-run (26% → 7% → 0%) because Stage 3 kept
                    # picking from the SAME `known:` track lines even
                    # after Spotify proved them unresolvable in this run.
                    # Strip already-verified tracks AND tracks that
                    # failed Spotify verify in this run from the overlay
                    # the model sees this batch — turns repeated misses
                    # into a strictly monotonic walk away from dead picks.
                    _live_overlay_for_batch = _prune_dead_tracks_from_overlay(
                        _approved_top_tracks, verified_tracks, _run_unverified,
                    )
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
                        approved_top_tracks=_live_overlay_for_batch or None,
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

                # Diagnostic: snapshot Stage 3's RAW picks BEFORE the HC
                # drops below so the per-batch trace can show what the
                # model originally produced vs. what survived enforcement.
                _stage3_raw_picks_snapshot = [
                    {"artist": _p.get("artist"), "track": _p.get("track")}
                    for _p in (result.get("playlist") or [])
                ]
                # Always-defined (HC block below may not run on legacy path).
                _hc2_violations = []
                _hc1_violations = []

                # ── HC2 + HC1 enforcement (2026-04-27) ──
                # Phase 2.5 hardening: previously these checks only LOGGED
                # violations. Now they DROP the offending entries from the
                # playlist so a future prompt regression can't silently ship
                # out-of-pool tracks or self-titled "track == artist" picks.
                # HC1: anti-confab — track field MUST NOT equal artist field.
                # HC2: ONLY tracks by artists in APPROVED_ARTISTS list.
                if _use_staged_pipeline:
                    _approved_lower = {n.lower().strip() for n in (_approved_names or [])}
                    _stage3_picks = result.get("playlist", []) if isinstance(result, dict) else []
                    _kept_picks = []
                    for _entry in _stage3_picks:
                        _a = (_entry.get("artist") or "").lower().strip()
                        _t = (_entry.get("track") or "").lower().strip()
                        if _a and _a not in _approved_lower:
                            _hc2_violations.append(f"{_a} - {_entry.get('track', '')}")
                            continue  # DROP — out of pool
                        if _t and _a and _t == _a:
                            _hc1_violations.append(f"{_a} - {_entry.get('track', '')}")
                            continue  # DROP — track == artist (self-titled echo)
                        _kept_picks.append(_entry)
                    if _hc2_violations:
                        logger.warning(
                            "[HC2 VIOLATION] DROPPED %d/%d picks "
                            "for artists OUTSIDE the approved pool. "
                            "Approved pool size=%d. Dropped picks: %s",
                            len(_hc2_violations), len(_stage3_picks),
                            len(_approved_lower), _hc2_violations[:10],
                        )
                    if _hc1_violations:
                        logger.warning(
                            "[HC1 VIOLATION] DROPPED %d/%d picks where "
                            "track == artist (self-titled echo). Dropped: %s",
                            len(_hc1_violations), len(_stage3_picks),
                            _hc1_violations[:10],
                        )
                    if not _hc2_violations and not _hc1_violations:
                        logger.info(
                            "[HC2 OK] Stage 3 returned %d picks, all in "
                            "approved pool (size=%d).",
                            len(_stage3_picks), len(_approved_lower),
                        )
                    if _hc2_violations or _hc1_violations:
                        # Mutate result so downstream consumers (filter,
                        # truncate, profile updates) see the cleaned list.
                        result["playlist"] = _kept_picks
                        # Re-derive profile_updates from kept picks only.
                        if isinstance(result.get("profile_updates"), dict):
                            _kept_artists = {(e.get("artist") or "").lower().strip() for e in _kept_picks}
                            result["profile_updates"]["suggested_artists"] = list(_kept_artists)
                            result["profile_updates"]["suggested_tracks"] = [
                                {"artist": (e.get("artist") or "").lower().strip(),
                                 "track": (e.get("track") or "").lower().strip()}
                                for e in _kept_picks
                            ]
                            if "new_artists" in result:
                                result["new_artists"] = [
                                    a for a in result.get("new_artists", [])
                                    if a in _kept_artists
                                ]

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

                    # A6 (2026-05-21): consecutive empty Stage-3 batches mean
                    # the approved pool can't satisfy the must-haves — Stage 3
                    # honestly refused rather than confabulate. Re-retrieve
                    # ONCE with a widened, popularity-flat net before giving
                    # up. Guarded re-attempt of OPEN-4 pool widening: fires
                    # only on an already-failing run, and only once, so the
                    # prompt-inflation / 429 cascade that killed OPEN-4 is
                    # bounded to a single run.
                    if (consecutive_empty_batches >= MAX_CONSECUTIVE_EMPTY_BATCHES
                            and _use_staged_pipeline
                            and not _rag_reretrieve_done
                            and _corpus is not None):
                        _rag_reretrieve_done = True
                        _old_pool_size = len(_approved_names)
                        yield _sse(
                            "progress",
                            message=f"Batch {batch_num}: candidate pool exhausted — "
                                    f"re-retrieving a wider pool…",
                        )
                        try:
                            from core.src import trace as _e1_trace
                            with _e1_trace.time_stage(_e1_trace.STAGE_RAG_RETRIEVE):
                                _stage1_candidates = retrieve_candidates(
                                    _corpus, profile,
                                    deny_keys=_deny_keys,
                                    target_size=RAG_RERETRIEVE_SIZE,
                                    popularity_penalty=0.0,
                                    primary_reference=_primary_ref,
                                )
                            set_last_rag_pool_names(
                                [a.name for a in _stage1_candidates])
                            if _stage1_candidates:
                                from core.src.rag.retrieval import get_last_retrieval_meta
                                _rr_meta = get_last_retrieval_meta() or {}
                                _approved_names, _stage2_meta = check_avoid_compliance(
                                    [a.name for a in _stage1_candidates],
                                    _avoid_traits,
                                    pool_avoid_overlap=_rr_meta.get("pool_avoid_overlap"),
                                    avoid_traits_fully_covered=bool(
                                        _rr_meta.get("avoid_traits_fully_covered")),
                                )
                            else:
                                _approved_names = []
                        except Exception as _rr_exc:
                            logger.warning(
                                "[A6] re-retrieve failed (%s) — stopping run", _rr_exc)
                            _approved_names = []
                        if _approved_names:
                            _taste_summary = _build_taste_summary_for_pool(
                                profile, _stage1_candidates, _approved_names)
                            _approved_top_tracks = {}
                            _rr_lower = {n.lower().strip() for n in _approved_names}
                            for a in _stage1_candidates:
                                key = (a.name or "").lower().strip()
                                if key and key in _rr_lower:
                                    _approved_top_tracks[key] = list(a.top_tracks or [])[:5]
                            logger.info(
                                "[A6] re-retrieve widened approved pool %d → %d artists",
                                _old_pool_size, len(_approved_names))
                            consecutive_empty_batches = 0
                            last_filtered_tracks = []
                            yield _sse(
                                "progress",
                                message=f"Batch {batch_num}: widened pool to "
                                        f"{len(_approved_names)} artists — retrying…",
                            )
                            continue
                        # re-retrieve produced nothing usable → fall through
                        # to the normal exhaustion stop below.

                    if consecutive_empty_batches >= MAX_CONSECUTIVE_EMPTY_BATCHES:
                        gpt_exhausted = True
                        _run_state["exhausted"] = True
                        yield _sse(
                            "progress",
                            message=f"Batch {batch_num}: The AI suggested only already-known tracks "
                                    f"for {consecutive_empty_batches} consecutive batches. "
                                    f"Stopping with {len(verified_tracks)} verified track(s).",
                        )
                        break

                    yield _sse(
                        "progress",
                        message=f"Batch {batch_num}: All {len(filtered_out)} suggestion(s) already known "
                                f"(retry {consecutive_empty_batches}/{MAX_CONSECUTIVE_EMPTY_BATCHES}). "
                                f"Sending explicit reminder to the AI…",
                    )
                    # Diagnostic: empty-after-filter batch (Stage 3 picked
                    # but every pick was a duplicate / disliked). Records
                    # WHICH tracks were dropped so the post-mortem can see
                    # whether Stage 3 is recycling the same artist's
                    # catalogue or hitting genuine pool exhaustion.
                    try:
                        from core.src import trace as _diag_trace
                        if _diag_trace.is_active():
                            _diag_trace.append("run_batches", {
                                "batch_num": batch_num,
                                "outcome": "empty_after_filter",
                                "requested": request_count,
                                "stage3_returned": _gpt_returned_count,
                                "stage3_raw_picks": _stage3_raw_picks_snapshot,
                                "hc2_violations": list(_hc2_violations),
                                "hc1_violations": list(_hc1_violations),
                                "filter_dropped": [
                                    {"artist": _x.get("artist"), "track": _x.get("track"),
                                     "reason": _x.get("reason")}
                                    for _x in (filtered_out or [])
                                ],
                                "consecutive_empty_after": consecutive_empty_batches,
                                "temperature": temperature,
                                "effective_new_artist_pct": effective_nap,
                                "a6_reretrieve_triggered": _rag_reretrieve_done,
                            })
                    except Exception as _diag_exc:  # pragma: no cover
                        logger.debug("trace run_batches (empty) skipped: %s", _diag_exc)
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
                # E1 (2026-05-06): wall-clock for Spotify verify.
                # L3 (2026-05-06): consume the streaming generator so a
                # `track_verified` SSE event fires per Spotify match —
                # the user sees each track land as soon as it's
                # confirmed, instead of waiting 2-3 s for the whole
                # batch to finish. Total batch counter (`batch_verified`)
                # still fires once at end so the "Use X tracks now"
                # button increments by batch.
                from core.src import trace as _e1_trace
                found = []
                not_found = []
                with _e1_trace.time_stage(_e1_trace.STAGE_SPOTIFY_VERIFY):
                    for _kind, _payload in iter_search_tracks(result["playlist"]):
                        if _kind == "found":
                            found.append(_payload)
                            yield _sse(
                                "track_verified",
                                track={
                                    "artist": _payload.get("artist"),
                                    "track": _payload.get("track"),
                                    "uri": _payload.get("uri"),
                                    "cover_url": _payload.get("cover_url"),
                                    "preview_url": _payload.get("preview_url"),
                                    "spotify_url": _payload.get("spotify_url"),
                                    "release_year": _payload.get("release_year"),
                                },
                                # Cumulative count across the whole run
                                # (verified_tracks not yet extended; this
                                # batch's `found` is what just landed).
                                count=len(verified_tracks) + len(found),
                                total=playlist_size,
                            )
                        else:
                            not_found.append(_payload)
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

                # Drop tracks by AI-generated artists (matched on Spotify
                # artist_id) before they count toward the playlist — the run
                # then refills the gap on the next batch.
                if get_filter_ai_artists() and found:
                    found, _ai_rejected = filter_ai_tracks(found)
                    if _ai_rejected:
                        yield _sse(
                            "progress",
                            message=f"Batch {batch_num}: {len(_ai_rejected)} AI-generated track(s) filtered out.",
                            ai_filtered=len(_ai_rejected),
                        )


                # N3d (2026-05-13) — Track-A verifier-swap bug-fix.
                # Production (SpotifyVerifier) returns a unique URI per
                # track, so dedup-by-URI is safe. NullVerifier (used by
                # `--verify-mode null` / probe-style evals) returns
                # ``uri=None`` for every track — the URI-set then
                # contains a single ``None`` and every subsequent track
                # is silently dropped (collapsed to playlist=1). Fall
                # back to a (artist, track) dedup key when uri is
                # falsy so the verifier-swap path actually accumulates
                # tracks.
                for t in found:
                    _uri = t.get("uri")
                    _key = _uri if _uri else (
                        (t.get("artist") or "").lower().strip(),
                        (t.get("track") or "").lower().strip(),
                    )
                    if _key not in verified_uris:
                        verified_tracks.append(t)
                        verified_uris.add(_key)
                _run_state["tracks_found"] = len(verified_tracks)

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

                last_found_rate = len(found) / max(request_count, 1)
                # Q3: cumulative spotify-found rate drives the new A6
                # low-found-rate trigger at the top of the next iteration.
                _cum_stage3_returned += _gpt_returned_count
                _cum_spotify_found += len(found)
                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: {len(found)} found on Spotify, "
                            f"{len(verified_tracks)}/{playlist_size} total verified",
                )
                # Inform the UI how many tracks we have so far (drives the
                # "Use X tracks now" button label)
                yield _sse("batch_verified", count=len(verified_tracks), total=playlist_size)

                # Diagnostic: consolidate per-batch outcome. Lets a
                # post-mortem walk batch-by-batch through "Stage 3 picked
                # X, HC dropped Y, dedup dropped Z, Spotify resolved W".
                try:
                    from core.src import trace as _diag_trace
                    if _diag_trace.is_active():
                        _diag_trace.append("run_batches", {
                            "batch_num": batch_num,
                            "outcome": "verified",
                            "requested": request_count,
                            "stage3_returned": _gpt_returned_count,
                            "stage3_raw_picks": _stage3_raw_picks_snapshot,
                            "hc2_violations": list(_hc2_violations),
                            "hc1_violations": list(_hc1_violations),
                            "filter_dropped": [
                                {"artist": _x.get("artist"), "track": _x.get("track"),
                                 "reason": _x.get("reason")}
                                for _x in (filtered_out or [])
                            ],
                            "spotify_found": [
                                {"artist": _t.get("artist"), "track": _t.get("track"),
                                 "uri": _t.get("uri")}
                                for _t in found
                            ],
                            "spotify_not_found": [
                                {"artist": _t.get("artist"), "track": _t.get("track")}
                                for _t in not_found
                            ],
                            "verified_total_after": len(verified_tracks),
                            "playlist_size": playlist_size,
                            "consecutive_empty_after": consecutive_empty_batches,
                            "temperature": temperature,
                            "effective_new_artist_pct": effective_nap,
                            "gpt_call_count_after": gpt_call_count,
                        })
                except Exception as _diag_exc:  # pragma: no cover
                    logger.debug("trace run_batches (verified) skipped: %s", _diag_exc)

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

            # Diagnostic: why did the batching loop terminate?
            try:
                from core.src import trace as _diag_trace
                if _diag_trace.is_active():
                    if was_cancelled:
                        _exit_reason = "cancelled"
                    elif gpt_exhausted:
                        _exit_reason = "gpt_exhausted"
                    elif len(verified_tracks) >= playlist_size:
                        _exit_reason = "target_hit"
                    elif gpt_call_count >= MAX_GPT_CALLS_PER_RUN:
                        _exit_reason = "max_calls_reached"
                    else:
                        _exit_reason = "other"
                    _diag_trace.record("run_exit", {
                        "reason": _exit_reason,
                        "batches_run": batch_num,
                        "verified_total": len(verified_tracks),
                        "playlist_size": playlist_size,
                        "gpt_calls_used": gpt_call_count,
                        "gpt_call_limit": MAX_GPT_CALLS_PER_RUN,
                        "a6_reretrieve_triggered": _rag_reretrieve_done,
                        "fill_ratio": (len(verified_tracks) / playlist_size
                                        if playlist_size else 0.0),
                    })
            except Exception as _diag_exc:  # pragma: no cover
                logger.debug("trace run_exit skipped: %s", _diag_exc)

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
                        "Couldn't find more matching tracks. Try a smaller playlist "
                        "or adjust the exploration slider."
                    ),
                    error_key="error.run.gpt_exhausted",
                )
                return
            # gpt_exhausted with some verified_tracks → fall through to create
            # playlist with what was found (same as "Use X tracks now")

            if not verified_tracks:
                yield _sse(
                    "error",
                    message="No tracks could be verified on Spotify.",
                    error_key="error.run.no_tracks_verified",
                )
                return

            # Persist accumulated profile updates (history) once after all batches
            save_profile(profile)

            # 2026-05-30: front-load artist variety before the size cap so a
            # thin pool can't produce a 3-band playlist. Stable reorder +
            # overflow backfill ⇒ the track count is unchanged (no fill-rate
            # regression), only the ordering favours diversity.
            verified_tracks = _enforce_per_artist_cap(
                verified_tracks, MAX_TRACKS_PER_ARTIST_PER_PLAYLIST)

            # Cap at target count — skip when emerging_only so all survivors are shown
            emerging_checked = len(verified_tracks)
            if not emerging_only:
                verified_tracks = verified_tracks[:playlist_size]

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

            _run_state["tracks_found"] = len(verified_tracks)
            yield _sse(
                "result",
                playlist=visible_playlist,
                not_found=all_not_found,
                was_cancelled=was_cancelled or gpt_exhausted,
                **({"emerging_shown": len(visible_playlist), "emerging_checked": emerging_checked} if emerging_only else {}),
            )

        except Exception as e:
            traceback.print_exc()
            _run_state["error"] = str(e)[:500]
            yield _sse_error(e)
        finally:
            with _runs_lock:
                _runs.pop(run_id, None)
            # M3 (2026-05-07): persist a per-run perf summary to local
            # sqlite BEFORE finalize_trace clears the metrics
            # accumulator. One row per generation regardless of
            # DEBUG_MODE. Diagnostic-only — failures are swallowed.
            # Reads out of the closure-shared ``_run_state`` so the
            # values survive whichever branch (success / except /
            # GeneratorExit) ended the run.
            try:
                from core.src import trace as _trace
                from core.src import perf_log as _perf_log
                _stage_metrics = _trace.current_stage_metrics()
                _perf_log.record_run(
                    run_id,
                    stage_metrics=_stage_metrics,
                    model=get_model(),
                    tracks_found=_run_state.get("tracks_found", 0),
                    tracks_target=_run_state.get("tracks_target", 0),
                    exhausted=_run_state.get("exhausted", False),
                    error=_run_state.get("error"),
                )
            except Exception as _exc:
                app_log(f"perf_log.record_run failed: {_exc}")
            # F9: write the trace bundle. Always runs — partial runs
            # and cancellations should still leave a diagnostic
            # artifact. No-op when DEBUG_MODE was off.
            try:
                from core.src import trace as _trace
                _trace.finalize_trace()
            except Exception as _exc:
                app_log(f"trace.finalize_trace failed: {_exc}")
            # L2 (2026-05-06): tear down the per-run Spotify cache so
            # the next run starts clean. Stale `not_found` entries
            # would otherwise mask retries for tracks the LLM tries
            # again later.
            try:
                from core.src import playlist as _pl_cache
                _pl_cache.end_run_search_cache()
            except Exception as _exc:
                app_log(f"playlist.end_run_search_cache failed: {_exc}")

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


@app.route("/api/apply-playlist", methods=["POST"])
def apply_playlist():
    """Apply the staged suggestion list to a Spotify playlist.

    Body: {
        tracks: [{artist, track, track_id, uri?, ...}, ...],
        playlist_mode: "create" | "append" | "replace",
        playlist_name: str (for create mode),
        playlist_id: str (for append/replace mode),
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    tracks = data.get("tracks")
    if not tracks or not isinstance(tracks, list):
        return jsonify({"error": "No tracks provided."}), 400
    if len(tracks) > MAX_SONG_LIST_SIZE:
        tracks = tracks[:MAX_SONG_LIST_SIZE]

    playlist_mode = data.get("playlist_mode", "create")
    if playlist_mode not in ("create", "append", "replace"):
        return jsonify({"error": "Invalid playlist_mode."}), 400
    playlist_name = sanitize_text(str(data.get("playlist_name") or "").strip()) or None
    if playlist_name and len(playlist_name) > 200:
        playlist_name = playlist_name[:200]
    playlist_id = _safe_spotify_id(data.get("playlist_id") or None)

    if playlist_mode in ("append", "replace") and not playlist_id:
        return jsonify({"error": "playlist_id is required for append/replace mode."}), 400

    try:
        spotify_status = get_spotify_auth_status()
        if spotify_status != "authenticated":
            return jsonify({"error": "Spotify is not connected."}), 401

        # Build track list with URIs for add_to_playlist
        verified_tracks = []
        for t in tracks:
            if t.get("uri"):
                verified_tracks.append(t)
            elif t.get("track_id"):
                verified_tracks.append({**t, "uri": f"spotify:track:{t['track_id']}"})
            else:
                continue

        if not verified_tracks:
            return jsonify({"error": "No tracks with valid Spotify IDs."}), 400

        profile = load_profile()
        playlist_info = add_to_playlist(
            verified_tracks,
            mode=playlist_mode,
            playlist_id=playlist_id,
            playlist_name=playlist_name,
            profile=profile,
        )

        # Add all tracks to suggested_tracks in profile (distinct)
        _add_tracks_to_suggested(profile, verified_tracks)

        # Save run history
        try:
            save_run(
                run_id=str(uuid.uuid4()),
                playlist_id=playlist_info.get("playlist_id") or "",
                playlist_url=playlist_info.get("url") or "",
                tracks=verified_tracks,
            )
        except Exception:
            pass

        return jsonify({
            "status": "ok",
            "playlist_url": playlist_info.get("url"),
            "playlist_id": playlist_info.get("playlist_id"),
            "added": playlist_info.get("added", 0),
        })

    except TranslatableError as e:
        return jsonify(as_response_payload(e)), e.status_code
    except Exception as e:
        logger.exception("apply_playlist failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/discover_artists", methods=["POST"])
def discover_artists():
    """Discover NEW artists matching the user's taste profile.

    Body: { artist_count: int (1-10), exploration: int (1-5) }

    Runs one RAG retrieval + one LLM artist-selection pass, then verifies
    each artist's tracks on Spotify so they can be applied to a playlist.
    Non-streaming JSON — the single LLM call is fast enough not to need
    SSE progress.
    """
    if not is_profile_trained():
        return jsonify({"error": "Train your taste profile first."}), 400

    data = request.get_json(force=True, silent=True) or {}

    def _clamp(value, lo, hi, default):
        try:
            return max(lo, min(int(value), hi))
        except (TypeError, ValueError):
            return default

    artist_count = _clamp(data.get("artist_count"), 1, 10, 8)
    exploration = _clamp(data.get("exploration"), 1, 5, 3)

    try:
        corpus = get_rag_corpus()
        if corpus is None:
            return jsonify({"error": "Artist discovery needs the music corpus. "
                                     "Enable RAG in Settings."}), 400

        profile = normalize_history(load_profile())
        result, _meta = select_artists(
            profile, artist_count=artist_count,
            exploration=exploration, corpus=corpus,
        )
        artists = result.get("artists", []) or []

        # Verify each artist's tracks on Spotify so they can be applied to
        # a playlist. A stable per-track id (_tid) survives the search
        # (search_tracks returns {**input, **payload}) so found tracks map
        # back to their artist unambiguously.
        flat = []
        for a in artists:
            for t in (a.get("tracks") or []):
                title = (t.get("track") or "").strip()
                if title:
                    flat.append({"artist": a.get("artist", ""), "track": title,
                                 "_tid": len(flat)})

        found_by_tid = {}
        if flat and get_spotify_auth_status() == "authenticated":
            found, _nf = search_tracks(flat)
            for f in found:
                if "_tid" in f:
                    found_by_tid[f["_tid"]] = f

        out_artists = []
        tid = 0
        for a in artists:
            tracks_out = []
            for t in (a.get("tracks") or []):
                title = (t.get("track") or "").strip()
                if not title:
                    continue
                hit = found_by_tid.get(tid)
                tid += 1
                entry = {
                    "artist": a.get("artist", ""),
                    "track": title,
                    "reason": t.get("reason", ""),
                }
                if hit:
                    entry.update({
                        "track_id": hit.get("track_id"),
                        "uri": hit.get("uri"),
                        "cover_url": hit.get("cover_url"),
                        "spotify_url": hit.get("spotify_url"),
                        "found": True,
                    })
                else:
                    entry["found"] = False
                tracks_out.append(entry)
            out_artists.append({
                "artist": a.get("artist", ""),
                "reason": a.get("reason", ""),
                "genres": a.get("genres", []) or [],
                "rationale": a.get("rationale", []) or [],
                "tracks": tracks_out,
            })

        return jsonify({
            "status": "ok",
            "artists": out_artists,
            "reasoning": result.get("reasoning", {}) or {},
        })

    except TranslatableError as e:
        return jsonify(as_response_payload(e)), e.status_code
    except Exception as e:
        logger.exception("discover_artists failed")
        return jsonify({"error": str(e)}), 500


def _request_json_object():
    """Parse the request body as a JSON object, or yield a 400.

    Hardening (2026-06-01): several POST/DELETE endpoints read
    ``request.get_json(force=True)`` then call ``data.get(...)`` directly.
    A wrong-type body (JSON ``null`` / list / number / string) made that
    ``.get`` raise ``AttributeError`` → HTTP 500. This returns
    ``(data, None)`` for a JSON object, or ``(None, <400 response>)``
    otherwise, so callers reject malformed bodies with 400 instead of
    crashing:  ``data, err = _request_json_object()``; ``if err: return err``.
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object."}), 400)
    return data, None


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """Record a like or dislike and persist it in music_profile.json.

    For dislikes the track is also removed from the Spotify playlist.
    """
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
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
            # Only remove from Spotify playlist when source is "review"
            source = data.get("source", "discover")
            if source == "review" and track:
                removal = remove_from_playlist(
                    artist, track,
                    playlist_id=playlist_id,
                    track_id=track_id,
                )
            elif source == "review" and not track:
                removal = {"removed": False, "reason": "No track specified"}
            else:
                removal = {"removed": False, "reason": "discover_mode"}

        response: dict = {"status": "ok"}
        if removal is not None:
            response["removal"] = removal
        return jsonify(response)

    except TranslatableError as e:
        return jsonify(as_response_payload(e)), e.status_code
    except Exception as e:
        return jsonify(as_response_payload(e)), 500


@app.route("/api/feedback/dislike-artist", methods=["POST"])
def dislike_artist_purge():
    """Artist-level dislike that also strips every track by that artist
    from the active playlist (Item 6, 2026-04).

    Frontend should show a confirmation dialog **before** calling this
    endpoint — there is no further confirmation server-side.

    Body: {"artist": str, "playlist_id": str, "reason": str (optional)}
    Returns: {"status": "ok", "removal": {...}}
    """
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
    artist = safe_text(data, "artist")
    playlist_id = _safe_spotify_id(safe_text(data, "playlist_id") or None)
    reason = safe_text(data, "reason") or None

    if not artist:
        return jsonify({"error": "Artist is required."}), 400
    if len(artist) > MAX_FEEDBACK_ARTIST_LEN:
        return jsonify({"error": f"Artist name too long (max {MAX_FEEDBACK_ARTIST_LEN} chars)."}), 400
    if reason and len(reason) > MAX_FEEDBACK_REASON_LEN:
        reason = reason[:MAX_FEEDBACK_REASON_LEN]

    source = data.get("source", "discover")

    try:
        # 1. Persist the artist-level dislike (no track ⇒ artist-level).
        dislike_track(artist, track=None, reason=reason)
        # 2. Strip the active playlist only in review mode.
        if source == "review":
            removal = remove_all_tracks_by_artist(artist, playlist_id=playlist_id)
        else:
            removal = {"removed_count": 0, "reason": "discover_mode"}
        return jsonify({"status": "ok", "removal": removal})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove", methods=["POST"])
def remove_track():
    """Remove a track. In review mode, also removes from Spotify playlist."""
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
    artist = safe_text(data, "artist")
    track  = safe_text(data, "track")
    playlist_id = _safe_spotify_id(safe_text(data, "playlist_id") or None)
    track_id    = _safe_spotify_id(safe_text(data, "track_id") or None)
    source = data.get("source", "discover")

    if not artist or not track:
        return jsonify({"error": "Artist and track are required."}), 400

    try:
        if source == "review":
            result = remove_from_playlist(
                artist, track,
                playlist_id=playlist_id,
                track_id=track_id,
            )
        else:
            # Discover mode: add to suggested_tracks, no Spotify removal
            profile = load_profile()
            _add_tracks_to_suggested(profile, [{"artist": artist, "track": track}])
            result = {"removed": False, "reason": "discover_mode"}
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
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
    save_credentials(data)
    return jsonify({"status": "ok", "path": str(CREDENTIALS_FILE)})


@app.route("/api/settings/models")
def list_models():
    """Return available chat models for the active provider preset.

    Provider-aware as of 2026-05-23: ``get_openai_models()`` reads
    ``PROVIDER_SUGGESTED_MODELS[preset]`` so the dropdown matches the
    JS-side ``PROVIDER_PRESETS`` declarations. The cache MUST key on
    the provider preset so switching from OpenAI → OpenRouter does
    not return a stale OpenAI list.
    """
    from config import get_llm_provider_preset
    preset = get_llm_provider_preset()
    now = time.time()
    cache_key = _models_cache.get("preset")
    if (cache_key == preset
            and _models_cache["data"] is not None
            and now < _models_cache["expires"]):
        return jsonify({"models": _models_cache["data"],
                        "selected": get_model()})

    try:
        models = get_openai_models()
        _models_cache["data"] = models
        _models_cache["preset"] = preset
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


@app.route("/api/ai-blocklist/download", methods=["POST"])
def download_ai_blocklist():
    """Download (or update) the AI-artist blocklist from the manifest URL.

    Streams the artifact to a ``.part`` sibling, sha256-verifies, atomically
    renames, then reloads the in-memory deny set so the filter takes effect
    without a restart.
    """
    try:
        from config import AI_BLOCKLIST_PATH, RAG_MANIFEST_URL
        from core.src.ai_filter import load_ai_blocklist
        from core.src.rag.distribution import (
            download_blocklist, fetch_remote_manifest,
        )
        manifest = fetch_remote_manifest(RAG_MANIFEST_URL)
        if manifest is None:
            return jsonify({"error": "remote_unavailable"}), 503
        if not manifest.has_ai_blocklist():
            return jsonify({"error": "blocklist_unavailable"}), 404
        download_blocklist(manifest, AI_BLOCKLIST_PATH)
        count = load_ai_blocklist(AI_BLOCKLIST_PATH)
        return jsonify({
            "status": "ok",
            "version": manifest.ai_blocklist_version,
            "count": count,
        })
    except ValueError as exc:  # sha mismatch
        return jsonify({"error": "checksum_failed", "detail": str(exc)}), 502
    except Exception as exc:  # pragma: no cover — defensive
        app_log(f"AI blocklist download failed: {exc}")
        return jsonify({"error": "download_failed", "detail": str(exc)}), 500


@app.route("/api/settings", methods=["POST"])
def write_settings():
    """Update non-secret settings (model, debug mode, playlist size)."""
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
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
    valid_presets = {"openai", "ollama", "lmstudio", "llamacpp", "openrouter"}
    if "provider_preset" in data:
        preset = safe_text(data, "provider_preset")
        if preset in valid_presets:
            payload["PROVIDER_PRESET"] = preset
    if "llm_base_url" in data:
        url = safe_text(data, "llm_base_url")
        if url:
            payload["LLM_BASE_URL"] = url

    # Detect whether the RAG toggle actually changed value — the frontend
    # sends `rag_enabled` on every Save (its current checkbox state), and
    # reloading a 175k-artist corpus on every Save takes 30-50 s, hanging
    # the Settings dialog for unrelated changes.
    from config import get_rag_enabled as _get_rag_enabled_now
    _rag_was = _get_rag_enabled_now() if "rag_enabled" in data else None
    if "rag_enabled" in data:
        payload["RAG_ENABLED"] = "true" if data["rag_enabled"] else "false"

    # AI-artist filter toggle. The deny set is loaded in-process at startup
    # (when present), so flipping this only persists the gate — no reload.
    if "filter_ai_artists" in data:
        payload["FILTER_AI_ARTISTS"] = "true" if data["filter_ai_artists"] else "false"

    save_settings(payload)
    app_log(f"Settings changed: {list(payload.keys())}")

    # Invalidate the model-list cache when provider OR model changes
    # so the next /api/settings/models call rebuilds against the new
    # PROVIDER_SUGGESTED_MODELS list (2026-05-23 fix: dropdown was
    # showing OpenAI's models after switching to OpenRouter).
    if ("provider_preset" in data or "model" in data
            or "llm_base_url" in data):
        _models_cache["data"] = None
        _models_cache["preset"] = None
        _models_cache["expires"] = 0.0

    # Hot-swap the RAG corpus handle ONLY when the toggle actually flipped.
    if "rag_enabled" in data and bool(data["rag_enabled"]) != bool(_rag_was):
        try:
            from config import RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH
            from core.src.rag import RagCorpus
            if _get_rag_enabled_now():
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
    # SSRF: block private/link-local/reserved targets (loopback + public OK).
    if _is_internal_host(parsed.hostname):
        return jsonify({"error": "Requests to internal/private addresses are not allowed."}), 400

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
    except TranslatableError as e:
        return jsonify(as_response_payload(e)), e.status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify(as_response_payload(e)), 500


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
    # 2026-05-14: STAGE3_MODE was ripped out (DeepSeek matches gpt-5.4 cite
    # at 1/10 cost — the mode switch's whole purpose is gone). The cost
    # estimator now just reports the configured model directly.
    resolved_model = get_model()

    if not get_active_profile_id() or not is_profile_trained():
        return jsonify({
            "trained": False,
            "stage3_resolved_model": resolved_model,
        })
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
            "stage3_resolved_model": resolved_model,
        })
    except Exception as exc:
        app.logger.warning("prompt-size endpoint failed: %s", exc)
        return jsonify({
            "trained": False,
            "error": str(exc),
            "stage3_resolved_model": resolved_model,
        }), 500


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
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr

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
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr

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
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
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
    data, _jerr = _request_json_object()
    if _jerr:
        return _jerr
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

