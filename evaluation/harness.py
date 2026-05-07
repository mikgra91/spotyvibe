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
from .scenario import DEFAULT_SCENARIO, Scenario

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
    scenario_name: str = "default"
    finished_at: str | None = None
    duration_s: float | None = None

    profile_id: str | None = None
    playlist_id: str | None = None
    playlist_url: str | None = None
    # F8 (2026-05-01): a SECOND playlist generated on the post-feedback
    # profile is the load-bearing regression signal. Tracked separately
    # so the report can show "playlist A had X tracks, playlist B had Y
    # tracks, leakage = Z" at a glance.
    playlist_b_id: str | None = None
    playlist_b_url: str | None = None

    seed_train_status: str = "skipped"
    analysis_status: str = "skipped"
    playlist_status: str = "skipped"
    feedback_status: str = "skipped"
    refine_train_status: str = "skipped"
    playlist_b_status: str = "skipped"
    leakage_status: str = "skipped"
    fit_status: str = "skipped"
    cleanup_status: str = "skipped"
    # P1 #5: pure-count completion gate against the requested playlist
    # size, independent of the production-derived ``playlist_*_status``.
    # Values: ``ok`` / ``under`` / ``empty`` / ``skipped``. Treat any
    # non-``ok`` as a quality regression in the report.
    completion_a_status: str = "skipped"
    completion_b_status: str = "skipped"
    # P1 #7: durable copy of the F9 per-run trace bundle into the
    # results dir. ``None`` when DEBUG_MODE was off or the source file
    # was missing. Stored as a string path (relative to the results
    # root) so the eval JSON stays portable.
    trace_a_path: str | None = None
    trace_b_path: str | None = None
    # E1 (2026-05-06): per-stage rollup pulled out of the trace bundle
    # at copy time. Shape mirrors ``trace.TraceBundle.stage_metrics`` —
    # ``{stage_name: {duration_s, calls, tokens_in, tokens_out}}``. None
    # when DEBUG_MODE was off or no metrics were recorded.
    stage_metrics_a: dict | None = None
    stage_metrics_b: dict | None = None
    # E2/E3 (2026-05-07): Last.fm-aware coverage + listener distribution
    # rollup, computed against the loaded RAG corpus. None when the
    # corpus isn't available (RAG disabled / file missing). Schema is
    # ``corpus_metrics.CorpusMetricsReport.to_json()``.
    corpus_metrics_a: dict | None = None
    corpus_metrics_b: dict | None = None

    # Raw result snapshots — kept terse so summary.json stays readable.
    seed_train_chars: int | None = None
    analysis_genre_count: int | None = None
    analysis_style_tag_count: int | None = None
    playlist_track_count: int = 0
    likes_applied: int = 0
    dislikes_applied: int = 0
    refine_train_chars: int | None = None

    # F8 — playlist-B leakage report (full LeakageReport.to_json() shape
    # so the comparison renderer can inspect individual hits without
    # re-loading the eval-log slice).
    playlist_b_track_count: int = 0
    leakage: dict | None = None
    # F8.3 — deterministic per-track fit-check report (decade-avoid for
    # now; future checks slot in via evaluation/fit_checks.py without
    # changing this field's contract).
    fit: dict | None = None

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
        for fname in ("artists.jsonl.gz", "artists.meta.json", "top_tracks_overlay.json"):
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

def _step_seed_train(profile_mod, scn: Scenario) -> dict[str, Any]:
    """Run the seed train_profile call. Returns a small status dict."""
    updated = profile_mod.train_profile(scn.seed_sections)
    return {
        "status": "ok",
        "profile_chars": len(json.dumps(updated, ensure_ascii=False)),
    }


def _step_seed_profile(profile_mod, scn: Scenario) -> dict[str, Any]:
    """P1 #6: bypass train_profile and import the file at scn.seed_profile_path.

    Used to evaluate against a stateful (large/aged/accumulated-dislikes)
    profile fixture instead of the clean-room ``seed_sections`` train.
    The file must be a JSON object accepted by
    ``profile.import_profile_dict`` — anything else raises ValueError
    and the step fails loudly so a typo in the fixture doesn't get
    silently swallowed by the eval.
    """
    path = Path(scn.seed_profile_path)  # type: ignore[arg-type]
    if not path.exists():
        raise FileNotFoundError(
            f"seed_profile fixture not found: {path}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    merged = profile_mod.import_profile_dict(payload)
    return {
        "status": "ok",
        "profile_chars": len(json.dumps(merged, ensure_ascii=False)),
    }


def _step_analysis(analysis_mod, scn: Scenario) -> dict[str, Any]:
    result = analysis_mod.analyze_band_song(
        scn.analysis_artist, scn.analysis_track,
    )
    return {
        "status": "ok",
        "genre_count": len(result.get("genre") or []),
        "style_tag_count": len(result.get("style_tags") or []),
    }


_PLAYLIST_STEP_TIMEOUT_S = 1800.0  # 30 min hard ceiling per model run

# P1 #5: hard completion gate. Per next-steps.md, anything below 95 % of
# the requested playlist size is a quality regression that must surface
# in the eval report — the legacy `under_filled` status (anti-confab
# guard fired) was being treated as a non-error and silently masking
# real production "I only got 9 of 15" failures.
COMPLETION_THRESHOLD = 0.95


def _completion_status(track_count: int, playlist_size: int) -> str:
    """Classify a completed playlist against the 95 % gate.

    Returns:
      - ``empty`` — got zero tracks
      - ``under`` — got some, but fewer than 95 % of the request
      - ``ok``    — at or above 95 % of the request
    """
    if track_count <= 0:
        return "empty"
    if playlist_size <= 0:
        return "ok"  # avoid div-by-zero; without a target there's no gate
    return "ok" if track_count >= playlist_size * COMPLETION_THRESHOLD else "under"


def _step_playlist(flask_app, playlist_size: int) -> dict[str, Any]:
    """Drive ``/api/run`` via Flask test client and consume the SSE stream.

    Returns ``{"tracks": [...], "status": "ok", "run_id": "<uuid>"}``
    on success. The harness pushes the resulting tracks to Spotify in
    a separate step so failures are isolated. ``run_id`` is included
    so the caller can locate the F9 trace bundle written at
    ``<sandbox>/debug/<run_id>/trace.json``.

    Progress events are logged as they arrive so a long run is visible
    in ``harness.log``. Hard timeout at ``_PLAYLIST_STEP_TIMEOUT_S`` —
    if the production loop genuinely runs that long, MAX_GPT_CALLS_PER_RUN
    has not stopped it and something is wrong.
    """
    run_id = str(_uuid.uuid4())
    client = flask_app.test_client()
    resp = client.post(
        "/api/run",
        json={"run_id": run_id, "playlist_size": playlist_size},
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
        # Distinguish "honest under-fill" — model refused to confabulate
        # because the candidate pool didn't yield enough grounded tracks
        # — from a real error (Spotify down, network, exception). Both
        # currently surface as the same "error" SSE event for UI reasons,
        # but for eval purposes they are NOT the same: honest under-fill
        # means the system worked AS DESIGNED (anti-hallucination guard
        # fired) and the eval should NOT mark it as broken. Added
        # 2026-04-27 after a reasoning-tier model + pool=32 produced
        # playlist=0 / status=error, hiding what was actually correct
        # behaviour. (The reasoning-tier model in question — gpt-5.5 —
        # was removed from the supported list in Phase 2.6.)
        _UNDER_FILL_PHRASES = (
            "no tracks could be verified on spotify",
            "couldn't find more matching tracks",
        )
        if any(p in error_msg.lower() for p in _UNDER_FILL_PHRASES):
            logger.info(
                "[playlist] reclassifying as under_filled (model refused "
                "to confabulate or exhausted candidate pool): %s", error_msg,
            )
            return {"status": "under_filled", "tracks": [],
                    "warning": error_msg, "run_id": run_id}
        raise RuntimeError(f"run_pipeline returned error: {error_msg}")
    return {"status": "ok", "tracks": tracks, "run_id": run_id}


def _copy_trace_bundle(sandbox_dir: Path, run_id: str | None,
                        dest_dir: Path, label: str) -> str | None:
    """Copy ``<sandbox>/debug/<run_id>/trace.json`` → ``<dest>/trace_<label>.json``.

    Returns the destination path as a string when the copy succeeds, or
    ``None`` if either the source bundle is missing (e.g. DEBUG_MODE was
    off, so trace.py wrote nothing) or the copy raises. The trace
    bundle is diagnostic — never let a missing file break the eval.
    """
    if not run_id:
        return None
    src = sandbox_dir / "debug" / run_id / "trace.json"
    if not src.exists():
        logger.info("[trace] no bundle at %s — DEBUG_MODE off or stage skipped", src)
        return None
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = dest_dir / f"trace_{label}.json"
        shutil.copy2(src, dst)
        logger.info("[trace] copied bundle %s → %s", src.name, dst)
        return str(dst)
    except OSError as exc:
        logger.warning("[trace] copy failed (%s → %s): %s", src, dest_dir, exc)
        return None


def _extract_stage_metrics(trace_path: str | None) -> dict | None:
    """Read ``stage_metrics`` out of a copied trace bundle.

    Returns the dict on success, ``None`` when the path is missing,
    unreadable, malformed, or the bundle has no ``stage_metrics`` key
    (older bundles, or DEBUG_MODE-off runs whose copy step returned None
    upstream so this function never sees the path). The harness must
    keep working on legacy bundles, so every error path returns None.
    """
    if not trace_path:
        return None
    try:
        with open(trace_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("[trace] could not read %s: %s", trace_path, exc)
        return None
    metrics = payload.get("stage_metrics")
    if isinstance(metrics, dict) and metrics:
        return metrics
    return None


def _extract_corpus_metrics(tracks: list[dict]) -> dict | None:
    """E2/E3: Last.fm coverage + listener stats for *tracks* against the
    live RAG corpus singleton.

    Reads the corpus via ``suggestions.get_rag_corpus()`` rather than
    re-loading from disk — the production code has already loaded it
    at app startup, so this is a free lookup. Returns the
    ``CorpusMetricsReport.to_json()`` dict or None if the corpus is
    unavailable AND the playlist is empty (so the report wouldn't
    carry useful information either way).

    Never raises — corpus metrics are diagnostic; a lookup failure
    must not fail the eval run.
    """
    if not tracks:
        return None
    try:
        from core.src.suggestions import get_rag_corpus
        from .corpus_metrics import compute_corpus_metrics
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("[corpus_metrics] import failed: %s", exc)
        return None
    try:
        corpus = get_rag_corpus()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("[corpus_metrics] get_rag_corpus failed: %s", exc)
        corpus = None
    try:
        report = compute_corpus_metrics(tracks, corpus)
        return report.to_json()
    except Exception as exc:
        logger.warning("[corpus_metrics] compute failed: %s", exc)
        return None


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


def _step_feedback(feedback_mod, tracks: list[dict],
                    scn: Scenario) -> dict[str, Any]:
    """Apply the deterministic like/dislike rule from ``scenario``.

    Skips out-of-range indices silently — a short playlist (e.g. one
    where Spotify verify dropped a lot) just gets fewer feedback signals.
    """
    likes = 0
    dislikes = 0
    for i in scn.like_indices:
        if i < len(tracks):
            t = tracks[i]
            feedback_mod.like_track(t["artist"], t["track"], scn.like_reason)
            likes += 1
    for i in scn.dislike_indices:
        if i < len(tracks):
            t = tracks[i]
            feedback_mod.dislike_track(t["artist"], t["track"], scn.dislike_reason)
            dislikes += 1
    return {"status": "ok", "likes": likes, "dislikes": dislikes}


def _step_refine_train(profile_mod, scn: Scenario) -> dict[str, Any]:
    """Run the second train_profile call (post-feedback absorption)."""
    updated = profile_mod.train_profile(scn.refine_sections)
    return {
        "status": "ok",
        "profile_chars": len(json.dumps(updated, ensure_ascii=False)),
    }


# ── Cleanup ──────────────────────────────────────────────────────────

def _cleanup(playlist_id: str | None, profile_id: str | None,
             playlist_mod, profile_mod,
             playlist_b_id: str | None = None) -> str:
    """Best-effort cleanup. Returns ``ok``, ``partial`` or ``error``.

    Runs in ``finally`` even if upstream raised — partial cleanup is
    better than none. Each step is logged. F8 (2026-05-01): also
    deletes playlist B (post-feedback regression playlist) when present.
    """
    issues: list[str] = []

    for label, pl_id in (("A", playlist_id), ("B", playlist_b_id)):
        if not pl_id:
            continue
        try:
            playlist_mod.delete_playlist(pl_id)
            logger.info("Cleanup: deleted playlist %s (%s)", pl_id, label)
        except Exception as exc:
            issues.append(f"playlist {pl_id} ({label}): {exc}")
            logger.warning(
                "Cleanup: failed to delete playlist %s (%s) — %s",
                pl_id, label, exc,
            )

    if profile_id:
        try:
            profile_mod.delete_profile(profile_id)
            logger.info("Cleanup: deleted profile %s", profile_id)
        except Exception as exc:
            issues.append(f"profile {profile_id}: {exc}")
            logger.warning("Cleanup: failed to delete profile %s — %s", profile_id, exc)

    any_target = bool(playlist_id or playlist_b_id or profile_id)
    if not issues:
        return "ok" if any_target else "skipped"
    return "partial" if any_target else "error"


# ── Main per-model entry point ───────────────────────────────────────

def run_for_model(*, model: str, iteration: int, settings: dict,
                   sandbox_dir: Path, results_dir: Path,
                   flask_app, profile_mod, analysis_mod,
                   playlist_mod, feedback_mod,
                   scn: Scenario | None = None) -> ModelRunResult:
    """Run one full evaluation cycle for one model.

    Caller is responsible for:
      - Setting ``SPOTYVIBE_APP_DIR`` env *before* importing the prod modules
      - Importing the modules and passing them in (so Flask app singleton
        is reused across model runs in the same invocation)
      - Switching ``OPENAI_MODEL`` env var before each call

    *scn* selects the named scenario from ``evaluation.scenario``. When
    omitted, falls back to :data:`DEFAULT_SCENARIO` for back-compat.

    Always returns a ``ModelRunResult`` — never raises. Errors are
    reported via the ``error`` field and the per-step status fields.
    """
    if scn is None:
        scn = DEFAULT_SCENARIO
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    eval_log = sandbox_dir / "eval.jsonl"
    log_pos_start = _eval_log_position(eval_log)

    result = ModelRunResult(
        model=model, iteration=iteration, started_at=started_at,
        scenario_name=scn.name,
    )

    # Switch the model for every production call below via env.
    os.environ["OPENAI_MODEL"] = model
    if settings["evaluation"].get("stage2_model"):
        os.environ["STAGE2_MODEL_OVERRIDE"] = settings["evaluation"]["stage2_model"]

    profile_id: str | None = None
    playlist_id: str | None = None
    playlist_b_id: str | None = None
    tracks: list[dict] = []
    # P1 #7: per_run_dir is built in `finally`, but we resolve it now
    # so the per-playlist trace copies land alongside the eval-log
    # slice and summary.json instead of in a separate directory.
    # E7 (2026-05-07): include the scenario name when it isn't the
    # default so multi-scenario runs don't collide on the same
    # ``{model}-iter{n}`` slot.
    if scn.name and scn.name != "default":
        per_run_dir = results_dir / f"{scn.name}__{model}-iter{iteration}"
    else:
        per_run_dir = results_dir / f"{model}-iter{iteration}"

    try:
        # ── 0. Profile creation ──────────────────────────────────
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        profile_name = f"eval-{model}-{iteration}-{ts}"
        prof = profile_mod.create_profile(profile_name)
        profile_id = prof["id"]
        result.profile_id = profile_id
        profile_mod.activate_profile(profile_id)

        # ── 1. Seed train (or fixture import — P1 #6) ────────────
        try:
            if scn.seed_profile_path is not None:
                r = _step_seed_profile(profile_mod, scn)
                # Distinguish in the report so a stateful run isn't
                # confused with a fresh-train run when reading
                # summary.json by hand.
                result.seed_train_status = "imported_fixture"
            else:
                r = _step_seed_train(profile_mod, scn)
                result.seed_train_status = r["status"]
            result.seed_train_chars = r["profile_chars"]
        except Exception as exc:
            result.seed_train_status = "error"
            result.error = f"seed_train: {exc}"
            raise

        # ── 2. Band/Song Analysis ────────────────────────────────
        try:
            r = _step_analysis(analysis_mod, scn)
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
            # Reclassified statuses (2026-04-27):
            #   "ok"           — got at least one verified track
            #   "under_filled" — anti-confab guard fired honestly (system worked)
            #   "empty"        — got zero tracks but no warning surfaced (rare)
            #   "error"        — exception raised (real failure, propagated below)
            if r.get("status") == "under_filled":
                result.playlist_status = "under_filled"
            elif tracks:
                result.playlist_status = "ok"
            else:
                result.playlist_status = "empty"
            # P1 #5: pure-count gate runs regardless of the semantic
            # playlist_status above.
            result.completion_a_status = _completion_status(
                len(tracks), settings["evaluation"]["playlist_size"],
            )
            # P1 #7: copy F9 trace bundle for playlist A while the
            # source still exists in the sandbox debug dir.
            result.trace_a_path = _copy_trace_bundle(
                sandbox_dir, r.get("run_id"), per_run_dir, "A",
            )
            # E1 (2026-05-06): pull stage rollup out of the just-copied
            # bundle so summary.json carries the timing/token data
            # without a separate consumer having to re-open the file.
            result.stage_metrics_a = _extract_stage_metrics(result.trace_a_path)
            # E2/E3 (2026-05-07): Last.fm coverage + listener stats on
            # playlist A. Reads the live RAG corpus singleton so the
            # lookup is consistent with what Stage 1 actually saw.
            result.corpus_metrics_a = _extract_corpus_metrics(tracks)
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
                r = _step_feedback(feedback_mod, tracks, scn)
                result.feedback_status = r["status"]
                result.likes_applied = r["likes"]
                result.dislikes_applied = r["dislikes"]
            except Exception as exc:
                result.feedback_status = "error"
                logger.warning("Feedback step failed: %s — continuing", exc)

        # ── 5. Refine train (absorb feedback) ────────────────────
        try:
            r = _step_refine_train(profile_mod, scn)
            result.refine_train_status = r["status"]
            result.refine_train_chars = r["profile_chars"]
        except Exception as exc:
            result.refine_train_status = "error"
            logger.warning("Refine train failed: %s — continuing", exc)

        # ── 6. Playlist B — same profile, post-feedback (F8) ─────
        # The single highest-leverage harness change: this is the only
        # step that exercises the production code's ability to RESPECT
        # prior feedback when generating fresh suggestions. Without it
        # rejected/disliked-artist leakage stays invisible to the eval.
        # (F8.)
        if tracks:  # only meaningful if playlist A produced something
            try:
                r = _step_playlist(flask_app, settings["evaluation"]["playlist_size"])
                tracks_b = r["tracks"]
                result.playlist_b_track_count = len(tracks_b)
                if r.get("status") == "under_filled":
                    result.playlist_b_status = "under_filled"
                elif tracks_b:
                    result.playlist_b_status = "ok"
                else:
                    result.playlist_b_status = "empty"
                # P1 #5: pure-count gate for playlist B.
                result.completion_b_status = _completion_status(
                    len(tracks_b), settings["evaluation"]["playlist_size"],
                )
                # P1 #7: copy F9 trace bundle for playlist B before
                # the next-iteration sandbox reuse can clobber it.
                result.trace_b_path = _copy_trace_bundle(
                    sandbox_dir, r.get("run_id"), per_run_dir, "B",
                )
                # E1: same rollup extraction as playlist A.
                result.stage_metrics_b = _extract_stage_metrics(result.trace_b_path)
                # E2/E3: same coverage rollup as playlist A.
                result.corpus_metrics_b = _extract_corpus_metrics(tracks_b)
            except Exception as exc:
                result.playlist_b_status = "error"
                tracks_b = []
                logger.warning("Playlist B step failed: %s — continuing", exc)

            # Push playlist B to Spotify under a tagged name so the
            # user can audit it manually if leakage flags something
            # unexpected. Cleanup deletes both at the end.
            if tracks_b:
                try:
                    pl_b_name = f"[EVAL] {model} {ts} — B"
                    profile = profile_mod.load_profile()
                    push_b = _step_push_to_spotify(
                        playlist_mod, tracks_b, pl_b_name, profile,
                    )
                    playlist_b_id = push_b["playlist_id"]
                    result.playlist_b_id = playlist_b_id
                    result.playlist_b_url = push_b["playlist_url"]
                except Exception as exc:
                    logger.warning(
                        "Spotify push (playlist B) failed: %s — continuing",
                        exc,
                    )

            # ── 7. Leakage audit ─────────────────────────────────
            # Read the (post-feedback) profile fresh — the scenario's
            # like/dislike rule may have changed it since the analysis
            # snapshot above.
            try:
                from .leakage import compute_leakage  # local import
                profile_post = profile_mod.load_profile()
                report = compute_leakage(tracks_b, profile_post)
                result.leakage = report.to_json()
                result.leakage_status = "pass" if report.passed else "fail"
                if not report.passed:
                    logger.warning(
                        "[leakage] %s iter %d: %d total leaks "
                        "(rejected=%d, disliked=%d, pattern=%d)",
                        model, iteration, report.total_leaks,
                        report.rejected_artist_count,
                        report.disliked_track_count,
                        report.dislike_pattern_count,
                    )
                    for hit in report.hits[:10]:  # cap log volume
                        logger.warning(
                            "[leakage] %s — %s — %s — %s",
                            hit.rule, hit.artist, hit.track, hit.detail,
                        )
            except Exception as exc:
                result.leakage_status = "error"
                logger.warning("Leakage audit failed: %s — continuing", exc)

            # ── 8. Deterministic fit-check (F8.3) ────────────────
            # Independent of leakage: leakage answers "did production
            # respect prior feedback?", fit answers "does each track
            # honour profile constraints expressible from track
            # metadata?". Currently only `decade_avoid` ships — uses
            # Spotify-returned release_year on each track; corpus-
            # independent so it works regardless of corpus quality.
            try:
                from .fit_checks import compute_fit  # local import
                profile_post = profile_mod.load_profile()
                fit_report = compute_fit(tracks_b, profile_post)
                result.fit = fit_report.to_json()
                if not fit_report.checks_applied:
                    result.fit_status = "no_checks_applied"
                else:
                    result.fit_status = (
                        "pass" if fit_report.passed else "fail"
                    )
                if not fit_report.passed:
                    logger.warning(
                        "[fit] %s iter %d: %d total fails "
                        "(decade_avoid=%d, checks=%s)",
                        model, iteration, fit_report.total_fails,
                        fit_report.decade_avoid_count,
                        ", ".join(fit_report.checks_applied),
                    )
                    for hit in fit_report.hits[:10]:
                        logger.warning(
                            "[fit] %s — %s — %s — %s",
                            hit.rule, hit.artist, hit.track, hit.detail,
                        )
            except Exception as exc:
                result.fit_status = "error"
                logger.warning("Fit-check failed: %s — continuing", exc)

    except Exception as exc:
        if not result.error:
            result.error = str(exc)
        logger.exception("run_for_model crashed for %s iter %d", model, iteration)

    finally:
        # ── Cleanup — ALWAYS runs ────────────────────────────────
        result.cleanup_status = _cleanup(
            playlist_id, profile_id, playlist_mod, profile_mod,
            playlist_b_id=playlist_b_id,
        )

        # Snapshot the eval-log slice for this run BEFORE other model
        # runs append to the same file. ``per_run_dir`` was resolved
        # at the top of run_for_model so playlist-A/B trace copies
        # land in the same directory; mkdir is idempotent.
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
