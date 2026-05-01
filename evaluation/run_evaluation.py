"""Evaluation harness entry point.

Usage:
    python evaluation/run_evaluation.py [--no-confirm] [--cleanup-only]

What this script does:

  1. Reads ``evaluation/settings.ini`` for credentials and model list.
  2. Sets ``SPOTYVIBE_APP_DIR`` to a fresh sandbox under
     ``evaluation/sandbox/{ts}/`` so the user's real profile + eval log
     are never touched.
  3. Copies ``.spotify-cache`` from the user's real app dir (so Spotify
     OAuth doesn't need to re-run) and hardlinks/copies the RAG corpus.
  4. Imports the production code (Flask app, profile, analysis, …).
  5. Estimates the OpenAI bill, prompts for confirmation.
  6. Runs the canonical scenario (see ``scenario.py``) for each model
     in turn — fresh profile, train, analyse, generate, feedback,
     re-train, cleanup.
  7. Writes ``evaluation/results/{ts}/comparison.md`` plus per-run
     ``eval.jsonl`` + ``summary.json`` slices.

Cost: roughly $0.10–$0.20 per full evaluation at current prompt sizes
(4 models, 1 iteration each — gpt-5.4, gpt-5.4-mini, gpt-4.1, gpt-4.1-mini).
Re-running is intentionally billable — that is the point.

Safety: cleanup deletes the Spotify playlist and sandbox profile
in a ``finally`` block so partial failures never leave orphans.
``--cleanup-only`` exists for manual recovery from a hard kill.
"""
from __future__ import annotations

import argparse
import configparser
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# This file lives in evaluation/ — derive repo root before doing anything.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SETTINGS_PATH = HERE / "settings.ini"
SETTINGS_EXAMPLE_PATH = HERE / "settings.ini.example"
RESULTS_DIR_BASE = HERE / "results"
SANDBOX_DIR_BASE = HERE / "sandbox"

# Make ``import config`` etc. work from the repo root.
sys.path.insert(0, str(REPO_ROOT))


# ── Logging ──────────────────────────────────────────────────────────

def _setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Force stdout into UTF-8 mode if possible. On Windows, the default
    # console encoding is cp1252, which can't render the box-drawing chars
    # used in section headers — without this, harness.log gets full output
    # but stdout spews UnicodeEncodeError tracebacks per emit.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ── Settings loader ──────────────────────────────────────────────────

REQUIRED_SECTIONS = {
    "openai": ["api_key"],
    "spotify": ["client_id", "client_secret"],
    "evaluation": ["models", "playlist_size"],
}


def load_settings() -> dict:
    """Read settings.ini. Halts with a friendly message if absent or invalid."""
    if not SETTINGS_PATH.exists():
        print(
            f"\n  ❌ Missing {SETTINGS_PATH.relative_to(REPO_ROOT)}.\n"
            f"     Copy {SETTINGS_EXAMPLE_PATH.name} → settings.ini and fill it in.\n"
            f"     (settings.ini is gitignored — your credentials never leave this machine.)\n",
            file=sys.stderr,
        )
        sys.exit(2)

    cfg = configparser.ConfigParser()
    cfg.read(SETTINGS_PATH, encoding="utf-8")

    missing: list[str] = []
    for section, keys in REQUIRED_SECTIONS.items():
        if not cfg.has_section(section):
            missing.append(f"[{section}]")
            continue
        for k in keys:
            if not cfg.get(section, k, fallback="").strip():
                missing.append(f"[{section}] {k}")
            elif cfg.get(section, k).startswith("REPLACE_ME") or "sk-REPLACE_ME" in cfg.get(section, k):
                missing.append(f"[{section}] {k} (still placeholder)")
    if missing:
        print("\n  ❌ settings.ini is incomplete:\n" + "\n".join(f"     • {m}" for m in missing) + "\n",
              file=sys.stderr)
        sys.exit(2)

    return {
        "openai": {"api_key": cfg.get("openai", "api_key").strip()},
        "spotify": {
            "client_id": cfg.get("spotify", "client_id").strip(),
            "client_secret": cfg.get("spotify", "client_secret").strip(),
            "redirect_uri": cfg.get("spotify", "redirect_uri",
                                    fallback="http://127.0.0.1:5000/callback").strip(),
        },
        "evaluation": {
            "models": [m.strip() for m in cfg.get("evaluation", "models").split(",") if m.strip()],
            "iterations": cfg.getint("evaluation", "iterations", fallback=1),
            "playlist_size": cfg.getint("evaluation", "playlist_size", fallback=30),
            "stage2_model": cfg.get("evaluation", "stage2_model", fallback="").strip() or None,
        },
    }


# ── Cost estimate ────────────────────────────────────────────────────

# Rough per-cycle estimates at current prompt sizes. Conservative.
# gpt-5.5 was removed in Phase 2.6 (2026-04-28) — see
# documentation/ModelRecommendations.md.
_PER_CYCLE_USD = {
    "gpt-5.4": 0.10,
    "gpt-5.4-mini": 0.01,
    "gpt-4.1": 0.04,
    "gpt-4.1-mini": 0.01,
    "gpt-4o": 0.05,  # candidate; ~25% pricier than gpt-4.1 ($2.50/$10.00 vs $2.00/$8.00).
}


def estimate_cost(models: list[str], iterations: int) -> float:
    return sum(_PER_CYCLE_USD.get(m, 0.05) for m in models) * iterations


def confirm_or_exit(estimate: float, models: list[str], iterations: int,
                    no_confirm: bool) -> None:
    msg = (
        f"\n  Evaluation plan:"
        f"\n    Models     : {', '.join(models)}"
        f"\n    Iterations : {iterations} per model"
        f"\n    Est. cost  : ~${estimate:.2f} (real OpenAI billing)"
        f"\n    Spotify    : test playlists prefixed `[EVAL] …` will be created and DELETED at the end."
        f"\n    Sandbox    : {SANDBOX_DIR_BASE.relative_to(REPO_ROOT)}/{{ts}}/ — your real profile is untouched."
        f"\n"
    )
    print(msg)
    if no_confirm:
        return
    reply = input("  Continue? [y/N] ").strip().lower()
    if reply not in ("y", "yes"):
        print("  Aborted.")
        sys.exit(0)


# ── Stage 2 model override ───────────────────────────────────────────

def _apply_stage2_override(stage2_model: str | None) -> None:
    """Patch ``config.STAGE2_MODEL`` in-process if the user requested an
    override. We do this after import (config has already been loaded)
    rather than via env so it is visible to ``get_stage2_model()``.
    """
    if not stage2_model:
        return
    import config
    config.STAGE2_MODEL = stage2_model
    logging.getLogger(__name__).info("STAGE2_MODEL overridden → %s", stage2_model)


# ── Cleanup-only path ────────────────────────────────────────────────

def cleanup_only() -> int:
    """Sweep all `[EVAL] …` playlists from the user's Spotify account.

    Useful when a previous run was hard-killed and left orphans.
    Operates against the user's REAL app dir (no sandbox) because the
    orphans are on the real Spotify account.
    """
    print("\n  Sweeping orphaned [EVAL] playlists from your Spotify account…\n")
    # Don't override SPOTYVIBE_APP_DIR here — we want the user's real
    # Spotify cache so we can authenticate.
    import config
    config.load_config()  # Pull SPOTIPY_* + OPENAI_API_KEY into os.environ
    from core.src.playlist import get_spotify_client, delete_playlist
    sp = get_spotify_client()

    deleted = 0
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        items = page.get("items") or []
        if not items:
            break
        for pl in items:
            name = pl.get("name", "") or ""
            if name.startswith("[EVAL] "):
                try:
                    delete_playlist(pl["id"])
                    print(f"    deleted: {name}")
                    deleted += 1
                except Exception as exc:
                    print(f"    failed: {name} — {exc}")
        offset += len(items)
        if len(items) < 50:
            break

    print(f"\n  Cleanup complete. {deleted} playlist(s) removed.\n")
    return 0


# ── Main ─────────────────────────────────────────────────────────────

_RUN_LOCK_PATH = HERE / ".run.lock"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-confirm", action="store_true",
                        help="Skip the cost-confirmation prompt.")
    parser.add_argument("--cleanup-only", action="store_true",
                        help="Sweep orphaned [EVAL] playlists from your Spotify "
                             "account and exit. Useful after a hard kill.")
    parser.add_argument("--release-lock", action="store_true",
                        help="Force-release a stale run lock left behind by a "
                             "hard-killed previous run, then exit.")
    args = parser.parse_args()

    # ── Run-lock escape hatch ─────────────────────────────────────
    from evaluation._runlock import (
        LockHeldError,
        acquire as _acquire_lock,
        release_stale_lock,
    )
    if args.release_lock:
        removed = release_stale_lock(_RUN_LOCK_PATH)
        print(f"Run lock {'removed' if removed else 'not present'}: {_RUN_LOCK_PATH}")
        return 0

    # cleanup-only is a quick read-only sweep — no need for the lock
    # (and we want it usable even when a previous run wedged the lock).
    if args.cleanup_only:
        return cleanup_only()

    # Acquire the exclusive run lock BEFORE we burn any OpenAI/Spotify
    # quota. A second concurrent run is almost always an accident
    # (orphan process, double-click, forgotten background terminal)
    # and silently doubles the bill — fail fast instead.
    try:
        _acquire_lock(_RUN_LOCK_PATH, kind="evaluation")
    except LockHeldError as exc:
        print(f"\n  ❌ {exc}\n", file=sys.stderr)
        return 4

    settings = load_settings()
    models = settings["evaluation"]["models"]
    iterations = settings["evaluation"]["iterations"]

    estimate = estimate_cost(models, iterations)
    confirm_or_exit(estimate, models, iterations, args.no_confirm)

    # ── Sandbox setup ─────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sandbox_dir = SANDBOX_DIR_BASE / ts
    results_dir = RESULTS_DIR_BASE / ts
    results_dir.mkdir(parents=True, exist_ok=True)

    _setup_logging(results_dir / "harness.log")
    logger = logging.getLogger(__name__)

    # Critical: import nothing from the repo before this point.
    # SPOTYVIBE_APP_DIR is read by config._get_app_dir() at import time.
    os.environ["SPOTYVIBE_APP_DIR"] = str(sandbox_dir)
    os.environ["DEBUG_MODE"] = "1"
    os.environ["RAG_ENABLED"] = "true"

    from evaluation.harness import prepare_sandbox, run_for_model

    try:
        prepare_sandbox(sandbox_dir, settings)
    except Exception as exc:
        logger.error("Sandbox setup failed: %s", exc)
        print(f"\n  ❌ Sandbox setup failed: {exc}\n", file=sys.stderr)
        return 3

    # Now safe to import production code — _APP_DIR resolves to sandbox.
    import config  # noqa: F401  — load + apply env overrides
    from core.src import profile as profile_mod
    from core.src import analysis as analysis_mod
    from core.src import playlist as playlist_mod
    from core.src import feedback as feedback_mod
    import app as flask_module

    _apply_stage2_override(settings["evaluation"].get("stage2_model"))

    flask_app = flask_module.app

    logger.info("Sandbox ready at %s", sandbox_dir)
    logger.info("Results will land in %s", results_dir)
    logger.info("Evaluating models: %s", ", ".join(models))

    # ── Run the matrix ────────────────────────────────────────────
    summaries = []
    overall_t0 = time.monotonic()
    # Inter-model cooldown: prevents Spotify search 429-cascade between
    # consecutive iterations. Spotify enforces a sliding-window quota per
    # user token; back-to-back model runs that fan out many parallel
    # searches can exhaust it and cause the next model to record 0 %
    # Spotify-found purely as a side effect. 60 s is enough for the rolling
    # window to drain in practice (raised from 15 s in Phase 2.6).
    INTER_MODEL_COOLDOWN_S = 60
    try:
        for model_idx, model in enumerate(models):
            if model_idx > 0:
                logger.info("Cooling down %ds before next model to let Spotify rate-limit window drain…",
                            INTER_MODEL_COOLDOWN_S)
                time.sleep(INTER_MODEL_COOLDOWN_S)
            for iteration in range(1, iterations + 1):
                logger.info("─── %s iteration %d/%d ───", model, iteration, iterations)
                result = run_for_model(
                    model=model,
                    iteration=iteration,
                    settings=settings,
                    sandbox_dir=sandbox_dir,
                    results_dir=results_dir,
                    flask_app=flask_app,
                    profile_mod=profile_mod,
                    analysis_mod=analysis_mod,
                    playlist_mod=playlist_mod,
                    feedback_mod=feedback_mod,
                )
                summaries.append(result)
                logger.info(
                    "%s iter %d done in %.1fs — playlist=%d, status=%s, cleanup=%s",
                    model, iteration, result.duration_s or 0,
                    result.playlist_track_count, result.playlist_status,
                    result.cleanup_status,
                )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user — cleanup of in-flight run already ran in finally.")

    # ── Reporting ─────────────────────────────────────────────────
    from evaluation.reporting import write_comparison_report
    try:
        report_path = write_comparison_report(results_dir, REPO_ROOT)
        logger.info("Wrote comparison report: %s", report_path)
    except Exception as exc:
        logger.exception("Reporting step failed: %s", exc)

    elapsed = time.monotonic() - overall_t0
    logger.info("Evaluation finished in %.1fs", elapsed)

    # ── Sandbox teardown ──────────────────────────────────────────
    # Keep eval-log slices in results/, drop the sandbox itself.
    try:
        shutil.rmtree(sandbox_dir)
        logger.info("Sandbox removed: %s", sandbox_dir)
    except Exception as exc:
        logger.warning("Sandbox cleanup failed: %s — please remove manually", exc)

    print(f"\n  ✅ Evaluation complete. See {results_dir}/comparison.md\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
