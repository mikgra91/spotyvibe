"""Per-model evaluation orchestration.

Each ``run_for_model()`` invocation:

  1. Creates a fresh profile in the sandbox app dir
  2. Trains the profile from the canonical seed sections
  3. Runs Band/Song Analysis on the canonical target
  4. Generates a 30-track playlist (real OpenAI + Spotify)
  5. Pushes the playlist to Spotify under a tagged name
  6. Applies deterministic likes / dislikes via ``feedback`` module
  7. Re-runs ``train_profile`` to absorb the feedback
  8. ALWAYS deletes the Spotify playlist and the sandbox profile in
     a ``finally`` block — even if any step above raised.

The evaluation telemetry (token counts, latency, status) is captured
by the production code paths through ``eval.jsonl``. The harness only
needs to snapshot that file at the boundaries of each model run.

Sandbox isolation: the parent ``run_evaluation.py`` sets
``SPOTYVIBE_APP_DIR`` *before* importing anything, so all production
code reads/writes inside the sandbox. The user's real profile and
real eval log are untouched.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid as _uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import scenario

logger = logging.getLogger(__name__)


# ── Per-model run record ─────────────────────────────────────────────

@dataclass
class ModelRunResult:
    """What ``run_for_model()`` returns. Persisted to ``summary.json``.

    Each step's status is one of:
      - ``ok`` — completed cleanly.
      - ``error`` — raised; ``error`` field carries the message.
      - ``skipped`` — earlier step failed; this one was not attempted.
    """
    model: str
    iteration: int
    started_at: str
    finished_at: str | None = None
    duration_s: float | None = None

    profile_id: str | None = None
    playlist_id: str | None = None
    playlist_url: str | None = None

    seed_train_status: str = "skipped"
    analysis_status: str = "skipped"
    playlist_status: str = "skipped"
    feedback_status: str = "skipped"
    refine_train_status: str = "skipped"
    cleanup_status: str = "skipped"

    # Raw result snapshots — kept terse so summary.json stays readable.
    seed_train_chars: int | None = None
    analysis_genre_count: int | None = None
    analysis_style_tag_count: int | None = None
    playlist_track_count: int = 0
    likes_applied: int = 0
    dislikes_applied: int = 0
    refine_train_chars: int | None = None

    error: str | None = None
    eval_log_lines: int = 0


# ── Sandbox setup helpers ────────────────────────────────────────────

def _user_real_app_dir() -> Path:
    """Return the user's REAL app dir (ignoring SPOTYVIBE_APP_DIR override).

    Used to copy ``.spotify-cache`` and reuse the RAG corpus from the
    user's actual install — re-OAuthing on every run would be hostile,
    and re-downloading a 100 MB corpus per run is wasteful.
    """
    import sys
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "spotyvibe"


def prepare_sandbox(sandbox_dir: Path, settings: dict) -> None:
    """Populate the sandbox app dir before any production import runs.

    Copies (or hardlinks where possible) just enough state from the
    user's real app dir to make Spotify work without re-OAuth and so
    RAG retrieval has its corpus. Writes fresh ``.credentials`` and
    ``settings.conf`` from the harness settings.

    Raises ``RuntimeError`` if Spotify cache is missing — in that case
    the user has to authorize via the dev server once first.
    """
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    real = _user_real_app_dir()

    # 1) Spotify token cache — required, never re-create
    src_cache = real / ".spotify-cache"
    if not src_cache.exists():
        raise RuntimeError(
            f"Spotify cache not found at {src_cache}. Run the app once "
            "(`python app.py`) and authorize Spotify in the browser, then re-run "
            "the evaluation."
        )
    shutil.copy2(src_cache, sandbox_dir / ".spotify-cache")
    logger.info("Copied Spotify cache from %s", src_cache)

    # 2) RAG corpus — hardlink the file so 100 MB isn't duplicated.
    # Falls back to copy on cross-volume / permission errors.
    src_rag_dir = real / "rag_corpus"
    dst_rag_dir = sandbox_dir / "rag_corpus"
    dst_rag_dir.mkdir(parents=True, exist_ok=True)
    if src_rag_dir.exists():
        for fname in ("artists.jsonl.gz", "artists.meta.json"):
            src = src_rag_dir / fname
            if not src.exists():
                continue
            dst = dst_rag_dir / fname
            if dst.exists():
                continue
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        logger.info("RAG corpus shared from %s", src_rag_dir)
    else:
        logger.warning(
            "No RAG corpus at %s — staged pipeline will fall back to legacy path",
            src_rag_dir,
        )

    # 3) .credentials — dotenv-style. Same keys as the real app expects.
    creds = (
        f"OPENAI_API_KEY={settings['openai']['api_key']}\n"
        f"SPOTIPY_CLIENT_ID={settings['spotify']['client_id']}\n"
        f"SPOTIPY_CLIENT_SECRET={settings['spotify']['client_secret']}\n"
    )
    (sandbox_dir / ".credentials").write_text(creds, encoding="utf-8")

    # 4) settings.conf — turn on DEBUG_MODE so eval.jsonl gets written;
    # turn on RAG so the staged pipeline activates; everything else
    # left to defaults.
    settings_conf = (
        "DEBUG_MODE=1\n"
        "RAG_ENABLED=true\n"
        "GPT_LANGUAGE=English\n"
        f"PLAYLIST_SIZE={settings['evaluation']['playlist_size']}\n"
    )
    (sandbox_dir / "settings.conf").write_text(settings_conf, encoding="utf-8")

    # 5) Ensure profiles dir exists so profile.create_profile() works
    (sandbox_dir / "profiles").mkdir(parents=True, exist_ok=True)


# ── Telemetry boundary helpers ───────────────────────────────────────

def _eval_log_position(eval_log: Path) -> int:
    """Byte offset of EOF, used to slice per-run telemetry from the shared
    ``eval.jsonl`` (the same file is appended to across all model runs)."""
    return eval_log.stat().st_size if eval_log.exists() else 0


def _slice_eval_log(eval_log: Path, start_pos: int, dest: Path) -> int:
    """Copy ``eval.jsonl`` content from ``start_pos`` to EOF into ``dest``.

    Returns the line count of the slice (for the summary report).
    """
    if not eval_log.exists():
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(eval_log, "rb") as src, open(dest, "wb") as out:
        src.seek(start_pos)
        data = src.read()
        out.write(data)
    return data.count(b"\n")


# ── Per-step runners — thin wrappers around production functions ─────

def _step_seed_train(profile_mod) -> dict[str, Any]:
    """Run the seed train_profile call. Returns a small status dict."""
    updated = profile_mod.train_profile(scenario.SEED_SECTIONS)
    return {
        "status": "ok",
        "profile_chars": len(json.dumps(updated, ensure_ascii=False)),
    }


def _step_analysis(analysis_mod) -> dict[str, Any]:
    result = analysis_mod.analyze_band_song(
        scenario.ANALYSIS_ARTIST, scenario.ANALYSIS_TRACK,
    )
    return {
        "status": "ok",
        "genre_count": len(result.get("genre") or []),
        "style_tag_count": len(result.get("style_tags") or []),
    }


_PLAYLIST_STEP_TIMEOUT_S = 1800.0  # 30 min hard ceiling per model run


def _step_playlist(flask_app, playlist_size: int) -> dict[str, Any]:
    """Drive ``/api/run`` via Flask test client and consume the SSE stream.

    Returns ``{"tracks": [...], "status": "ok"}`` on success. The harness
    pushes the resulting tracks to Spotify in a separate step so failures
    are isolated.

    Progress events are logged as they arrive so a long run is visible
    in ``harness.log``. Hard timeout at ``_PLAYLIST_STEP_TIMEOUT_S`` —
    if the production loop genuinely runs that long, MAX_GPT_CALLS_PER_RUN
    has not stopped it and something is wrong.
    """
    client = flask_app.test_client()
    resp = client.post(
        "/api/run",
        json={"run_id": str(_uuid.uuid4()), "playlist_size": playlist_size},
    )
    tracks: list[dict] = []
    error_msg: str | None = None
    started = time.monotonic()
    progress_count = 0
    # SSE comes back as `data: {...}\n\n` lines. Parse each.
    for chunk in resp.response:
        elapsed = time.monotonic() - started
        if elapsed > _PLAYLIST_STEP_TIMEOUT_S:
            # Werkzeug test_client iterates the SSE generator in the same
            # thread — no way to call /api/cancel from here. Just abort the
            # iteration; the orphaned generator gets GC'd.
            raise TimeoutError(
                f"playlist step exceeded {_PLAYLIST_STEP_TIMEOUT_S:.0f}s "
                f"(received {progress_count} progress events, "
                f"{len(tracks)} tracks so far) — production code's "
                f"MAX_GPT_CALLS_PER_RUN guard should have stopped it"
            )
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        for line in chunk.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "progress":
                progress_count += 1
                # Log every event so harness.log shows live batch progress
                # rather than a 15-minute silence.
                msg = event.get("message", "")
                logger.info("[playlist] %s", msg)
            elif etype == "result":
                # /api/run emits the verified playlist under the "playlist"
                # key (with "tracks"/"verified_tracks" as historical aliases
                # we still accept for safety).
                tracks = (event.get("playlist") or event.get("tracks")
                          or event.get("verified_tracks") or [])
                logger.info(
                    "[playlist] result: %d tracks after %.1fs",
                    len(tracks), time.monotonic() - started,
                )
            elif etype == "error":
                error_msg = event.get("message")
                logger.warning("[playlist] error event: %s", error_msg)
    if error_msg:
        raise RuntimeError(f"run_pipeline returned error: {error_msg}")
    return {"status": "ok", "tracks": tracks}


def _step_push_to_spotify(playlist_mod, tracks: list[dict],
                           playlist_name: str, profile: dict) -> dict[str, Any]:
    """Create a Spotify playlist and push verified tracks to it.

    Tagged name (`[EVAL] {model} {ts}`) makes orphan cleanup easy.
    """
    result = playlist_mod.add_to_playlist(
        verified_tracks=tracks,
        mode="create",
        playlist_name=playlist_name,
        profile=profile,
    )
    return {
        "status": "ok",
        "playlist_id": result["playlist_id"],
        "playlist_url": result["url"],
        "added": result["added"],
    }


def _step_feedback(feedback_mod, tracks: list[dict]) -> dict[str, Any]:
    """Apply the deterministic like/dislike rule from ``scenario.py``.

    Skips out-of-range indices silently — a short playlist (e.g. one
    where Spotify verify dropped a lot) just gets fewer feedback signals.
    """
    likes = 0
    dislikes = 0
    for i in scenario.LIKE_INDICES:
        if i < len(tracks):
            t = tracks[i]
            feedback_mod.like_track(t["artist"], t["track"], scenario.LIKE_REASON)
            likes += 1
    for i in scenario.DISLIKE_INDICES:
        if i < len(tracks):
            t = tracks[i]
            feedback_mod.dislike_track(t["artist"], t["track"], scenario.DISLIKE_REASON)
            dislikes += 1
    return {"status": "ok", "likes": likes, "dislikes": dislikes}


def _step_refine_train(profile_mod) -> dict[str, Any]:
    """Run the second train_profile call (post-feedback absorption)."""
    updated = profile_mod.train_profile(scenario.REFINE_SECTIONS)
    return {
        "status": "ok",
        "profile_chars": len(json.dumps(updated, ensure_ascii=False)),
    }


# ── Cleanup ──────────────────────────────────────────────────────────

def _cleanup(playlist_id: str | None, profile_id: str | None,
             playlist_mod, profile_mod) -> str:
    """Best-effort cleanup. Returns ``ok``, ``partial`` or ``error``.

    Runs in ``finally`` even if upstream raised — partial cleanup is
    better than none. Each step is logged.
    """
    issues: list[str] = []

    if playlist_id:
        try:
            playlist_mod.delete_playlist(playlist_id)
            logger.info("Cleanup: deleted playlist %s", playlist_id)
        except Exception as exc:
            issues.append(f"playlist {playlist_id}: {exc}")
            logger.warning("Cleanup: failed to delete playlist %s — %s", playlist_id, exc)

    if profile_id:
        try:
            profile_mod.delete_profile(profile_id)
            logger.info("Cleanup: deleted profile %s", profile_id)
        except Exception as exc:
            issues.append(f"profile {profile_id}: {exc}")
            logger.warning("Cleanup: failed to delete profile %s — %s", profile_id, exc)

    if not issues:
        return "ok"
    return "partial" if (playlist_id or profile_id) else "error"


# ── Main per-model entry point ───────────────────────────────────────

def run_for_model(*, model: str, iteration: int, settings: dict,
                   sandbox_dir: Path, results_dir: Path,
                   flask_app, profile_mod, analysis_mod,
                   playlist_mod, feedback_mod) -> ModelRunResult:
    """Run one full evaluation cycle for one model.

    Caller is responsible for:
      - Setting ``SPOTYVIBE_APP_DIR`` env *before* importing the prod modules
      - Importing the modules and passing them in (so Flask app singleton
        is reused across model runs in the same invocation)
      - Switching ``OPENAI_MODEL`` env var before each call

    Always returns a ``ModelRunResult`` — never raises. Errors are
    reported via the ``error`` field and the per-step status fields.
    """
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    eval_log = sandbox_dir / "eval.jsonl"
    log_pos_start = _eval_log_position(eval_log)

    result = ModelRunResult(
        model=model, iteration=iteration, started_at=started_at,
    )

    # Switch the model for every production call below via env.
    os.environ["OPENAI_MODEL"] = model
    if settings["evaluation"].get("stage2_model"):
        os.environ["STAGE2_MODEL_OVERRIDE"] = settings["evaluation"]["stage2_model"]

    profile_id: str | None = None
    playlist_id: str | None = None
    tracks: list[dict] = []

    try:
        # ── 0. Profile creation ──────────────────────────────────
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        profile_name = f"eval-{model}-{iteration}-{ts}"
        prof = profile_mod.create_profile(profile_name)
        profile_id = prof["id"]
        result.profile_id = profile_id
        profile_mod.activate_profile(profile_id)

        # ── 1. Seed train ────────────────────────────────────────
        try:
            r = _step_seed_train(profile_mod)
            result.seed_train_status = r["status"]
            result.seed_train_chars = r["profile_chars"]
        except Exception as exc:
            result.seed_train_status = "error"
            result.error = f"seed_train: {exc}"
            raise

        # ── 2. Band/Song Analysis ────────────────────────────────
        try:
            r = _step_analysis(analysis_mod)
            result.analysis_status = r["status"]
            result.analysis_genre_count = r["genre_count"]
            result.analysis_style_tag_count = r["style_tag_count"]
        except Exception as exc:
            result.analysis_status = "error"
            logger.warning("Analysis step failed: %s — continuing", exc)
            # Non-fatal — analysis failure should not block playlist eval.

        # ── 3. Playlist generation ───────────────────────────────
        try:
            r = _step_playlist(flask_app, settings["evaluation"]["playlist_size"])
            tracks = r["tracks"]
            result.playlist_track_count = len(tracks)
            result.playlist_status = "ok" if tracks else "empty"
        except Exception as exc:
            result.playlist_status = "error"
            result.error = f"playlist: {exc}"
            raise

        # ── 3b. Push to Spotify (tagged name for cleanup) ────────
        if tracks:
            try:
                pl_name = f"[EVAL] {model} {ts}"
                profile = profile_mod.load_profile()
                push = _step_push_to_spotify(playlist_mod, tracks, pl_name, profile)
                playlist_id = push["playlist_id"]
                result.playlist_id = playlist_id
                result.playlist_url = push["playlist_url"]
            except Exception as exc:
                logger.warning("Spotify push failed: %s — continuing without playlist_id", exc)

        # ── 4. Feedback ──────────────────────────────────────────
        if tracks:
            try:
                r = _step_feedback(feedback_mod, tracks)
                result.feedback_status = r["status"]
                result.likes_applied = r["likes"]
                result.dislikes_applied = r["dislikes"]
            except Exception as exc:
                result.feedback_status = "error"
                logger.warning("Feedback step failed: %s — continuing", exc)

        # ── 5. Refine train (absorb feedback) ────────────────────
        try:
            r = _step_refine_train(profile_mod)
            result.refine_train_status = r["status"]
            result.refine_train_chars = r["profile_chars"]
        except Exception as exc:
            result.refine_train_status = "error"
            logger.warning("Refine train failed: %s — continuing", exc)

    except Exception as exc:
        if not result.error:
            result.error = str(exc)
        logger.exception("run_for_model crashed for %s iter %d", model, iteration)

    finally:
        # ── Cleanup — ALWAYS runs ────────────────────────────────
        result.cleanup_status = _cleanup(
            playlist_id, profile_id, playlist_mod, profile_mod,
        )

        # Snapshot the eval-log slice for this run BEFORE other model
        # runs append to the same file.
        per_run_dir = results_dir / f"{model}-iter{iteration}"
        per_run_dir.mkdir(parents=True, exist_ok=True)
        result.eval_log_lines = _slice_eval_log(
            eval_log, log_pos_start, per_run_dir / "eval.jsonl",
        )

        result.duration_s = round(time.monotonic() - started, 2)
        result.finished_at = datetime.now(timezone.utc).isoformat()

        # Per-run summary alongside the eval-log slice.
        (per_run_dir / "summary.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return result
