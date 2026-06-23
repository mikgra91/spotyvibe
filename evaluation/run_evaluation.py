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
        "openrouter": {
            "api_key": cfg.get("openrouter", "api_key", fallback="").strip(),
        },
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
            # F8.2 (2026-05-01): selects which scenario from
            # evaluation/scenario.py to run. Empty/missing → "default".
            "scenario": cfg.get("evaluation", "scenario", fallback="").strip() or "default",
            # E7 (2026-05-07): comma-separated multi-scenario list.
            # When set, OVERRIDES the singular ``scenario`` field and
            # the harness loops scenarios × models × iterations. The
            # special value ``all`` expands to every scenario in
            # ``SCENARIOS`` (alphabetical, "default" first).
            "scenarios": cfg.get("evaluation", "scenarios", fallback="").strip(),
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


def run_probe_gate(models: list[str], *, allow_regressions: bool) -> int:
    """Run the Track B probe battery against each model and diff against
    the committed baseline. Returns the exit code the caller should
    propagate (0 = pass, 7 = regression with gate enforced). Never
    raises — every error path is a no-op that prints and continues.

    Cost: ~$0.10 per model (default 8-probe battery, 16 calls).
    """
    from evaluation.probes import cli as _probes_cli
    from evaluation.probes import runner as _probes_runner
    from evaluation.probes import diff as _probes_diff

    fingerprints_dir = HERE / "probes" / "fingerprints"
    modules = _probes_cli._BATTERIES["default"]

    total_regressions: list[_probes_diff.Regression] = []
    print("\n  Probe gate — Track B battery against each model:\n")
    for model in models:
        baseline_path = _probes_diff.baseline_path_for(
            model, fingerprints_dir=fingerprints_dir,
        )
        if not baseline_path.exists():
            print(f"  ⚠ {model}: no baseline at {baseline_path.name} — "
                  f"capture one with `python -m evaluation.probes --model "
                  f"{model} --battery default --confirm` and copy the "
                  f"fingerprint.json into evaluation/probes/fingerprints/. "
                  f"Gate is informational only for this model.")
            continue

        print(f"  Running probes for {model}…")
        results = _probes_runner.run_battery(modules, model)
        new_fp = _probes_runner.aggregate_fingerprint(
            results,
            model=model,
            captured_at=datetime.now(timezone.utc).isoformat(),
            probe_modules=modules,
        ).to_dict()
        baseline = _probes_diff.load_fingerprint(baseline_path)
        print(_probes_diff.render_fingerprint_diff(baseline, new_fp))
        regressions = _probes_diff.detect_regressions(baseline, new_fp)
        if regressions:
            print(f"\n  ❌ {len(regressions)} regression(s) for {model}:")
            for r in regressions:
                print(f"    - {r.describe()}")
            total_regressions.extend(regressions)
        else:
            print(f"\n  ✅ {model}: no regressions vs baseline.")

    if total_regressions and not allow_regressions:
        print(f"\n  Aborting full eval — {len(total_regressions)} probe "
              f"regression(s) across {len(models)} model(s). "
              f"Re-run with --no-probe-gate to override.")
        return 7
    if total_regressions:
        print(f"\n  ⚠ {len(total_regressions)} regression(s) — gate "
              f"override (--no-probe-gate) in effect; continuing.")
    return 0


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


# ── Spotify pre-flight 429 check ────────────────────────────────────

def check_spotify_not_rate_limited() -> int | None:
    """Fire one cheap Spotify search to detect an active 429 penalty block.

    Returns the raw ``Retry-After`` value (seconds) if blocked, or ``None``
    when the account is clear.  Called BEFORE any OpenAI quota is burned so
    a hard block aborts early with a human-readable message and exit code 7.
    """
    try:
        from core.src.playlist import get_spotify_client
        import spotipy

        sp = get_spotify_client()
        sp.search(
            q='track:"primadonna like me" artist:"the struts"',
            limit=1,
            type="track",
            market="from_token",
        )
        return None  # no 429
    except Exception as exc:  # noqa: BLE001
        # Import spotipy lazily — only available inside the production path.
        try:
            import spotipy  # noqa: F401
            if hasattr(exc, "http_status") and exc.http_status == 429:  # type: ignore[union-attr]
                return int(exc.headers.get("Retry-After", 0))  # type: ignore[union-attr]
        except Exception:
            pass
        # Non-429 error (auth, network) — don't block the run on this check.
        return None


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
    parser.add_argument("--seed-profile", type=Path, default=None,
                        help="Path to a JSON profile to import into the sandbox "
                             "instead of running train_profile(seed_sections). "
                             "Use to evaluate against a stateful (anonymised "
                             "production) profile. Overrides any "
                             "scenario.seed_profile_path.")
    parser.add_argument("--verify-mode",
                        choices=["spotify", "null", "overlay", "l0_l1"],
                        default=None,
                        help="Track A: which existence verifier the harness "
                             "should install. 'spotify' = ground-truth via "
                             "Spotify search (production default; pushes "
                             "tagged [EVAL] playlists). 'null' = treat every "
                             "Stage-3 pick as found, skip Spotify entirely, "
                             "skip the playlist-push step. 'overlay' = "
                             "verify against the RAG corpus's top_tracks "
                             "overlay (L0 — cheap offline check; falls back "
                             "to not_found for artists or titles missing "
                             "from the overlay). 'overlay' also skips the "
                             "push step. Overrides any scenario.verify_mode "
                             "for this invocation.")
    parser.add_argument("--probe-check", action="store_true",
                        help="Run the Track B probe battery against every "
                             "configured model BEFORE the full eval, diff "
                             "against the committed baseline at "
                             "evaluation/probes/fingerprints/<model>.v1.json, "
                             "and abort on regression (unless --no-probe-gate).")
    parser.add_argument("--no-probe-gate", action="store_true",
                        help="With --probe-check, print the diff but never "
                             "abort. Use to ship a deliberately-regressing "
                             "prompt change with full visibility of what "
                             "regressed.")
    parser.add_argument("--iterations", type=int, default=None,
                        help="Override [evaluation] iterations from "
                             "settings.ini for this invocation. Useful when "
                             "the model's B-6 n_required_for_5pp_signal "
                             "fingerprint indicates the static default is "
                             "noise (gpt-4.1=5, gpt-5.4=19, gpt-5.4-mini=85 "
                             "as of 2026-05-12 v1 fingerprints). Cost scales "
                             "linearly with this value.")
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
    # N2 (2026-05-13): allow CLI override of the iterations count. B-6
    # fingerprint shows the static default of 5 is well below the
    # n_required_for_5pp_signal floor for gpt-5.4 (19) and gpt-5.4-mini
    # (85); override here when an investigation needs a tighter
    # variance signal on one of those rows.
    if args.iterations is not None:
        if args.iterations < 1:
            print(f"\n  [ERROR] --iterations must be >= 1 (got {args.iterations}).\n",
                  file=sys.stderr)
            return 2
        if args.iterations != iterations:
            print(f"\n  [INFO] --iterations override: settings.ini={iterations} "
                  f"-> runtime={args.iterations}")
        iterations = args.iterations
    scenario_name = settings["evaluation"].get("scenario", "default")
    scenarios_raw = settings["evaluation"].get("scenarios", "") or ""

    # Validate the scenario name now (loud failure on typo) before
    # spending any OpenAI/Spotify quota.
    from evaluation.scenario import get_scenario, SCENARIOS

    # E7 (2026-05-07): expand the multi-scenario field if present.
    # Precedence: ``scenarios`` (plural) wins over ``scenario`` so a
    # template can opt into "run everything" without rewriting the
    # singular field. ``all`` is the convenience for the canonical
    # baseline run.
    scenario_names: list[str]
    if scenarios_raw:
        if scenarios_raw.strip().lower() == "all":
            # Stable order — default first so the report's "first row"
            # is the legacy reference scenario.
            scenario_names = (
                ["default"]
                + sorted(n for n in SCENARIOS if n != "default")
            )
        else:
            scenario_names = [
                s.strip() for s in scenarios_raw.split(",") if s.strip()
            ]
    else:
        scenario_names = [scenario_name]

    try:
        active_scenarios = [get_scenario(n) for n in scenario_names]
    except KeyError as exc:
        print(f"\n  ❌ {exc}\n", file=sys.stderr)
        return 5

    # P1 #6: --seed-profile overrides whatever the scenario would have
    # done at the seed-train step. Validate the file exists *now* so a
    # typo fails before we burn OpenAI / Spotify quota.
    if args.seed_profile is not None:
        if not args.seed_profile.exists():
            print(f"\n  ❌ --seed-profile not found: {args.seed_profile}\n",
                  file=sys.stderr)
            return 6
        from dataclasses import replace
        active_scenarios = [
            replace(s, seed_profile_path=args.seed_profile.resolve())
            for s in active_scenarios
        ]

    # Track A: --verify-mode overrides scenario.verify_mode for THIS
    # invocation. Applied after --seed-profile so the two flags compose
    # cleanly (anonymised profile + null verifier = the cheapest mode).
    if args.verify_mode is not None:
        from dataclasses import replace
        active_scenarios = [
            replace(s, verify_mode=args.verify_mode) for s in active_scenarios
        ]

    estimate = estimate_cost(models, iterations) * len(active_scenarios)

    # Probe gate (Track B Step 4) - cheap fingerprint check against the
    # committed baseline before any full-eval billing. Spends ~$0.10/model
    # in the worst case; aborts the run on regression unless the user
    # explicitly opted into --no-probe-gate.
    if args.probe_check:
        import config as _cfg
        _cfg.load_config()
        gate_rc = run_probe_gate(
            models, allow_regressions=args.no_probe_gate,
        )
        if gate_rc != 0:
            return gate_rc

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
    # OPEN-1a (2026-05-14): when routing via OpenRouter, the prior probe-check
    # call to config.load_config() already loaded the user's REAL OpenAI key
    # into os.environ. Subsequent sandbox loads use override=True but still
    # read CREDENTIALS_FILE (bound at config-import time) from the REAL app
    # dir — never seeing the sandbox's [openrouter] key. Force the OR key
    # into env here before any prod import re-resolves credentials.
    if any("/" in m for m in models):
        or_key = settings.get("openrouter", {}).get("api_key", "").strip()
        if or_key:
            os.environ["OPENAI_API_KEY"] = or_key
            os.environ["LLM_BASE_URL"] = "https://openrouter.ai/api/v1"
            os.environ["PROVIDER_PRESET"] = "openrouter"
            # Disable keyring overlay so the real OpenAI key in Windows
            # Credential Manager doesn't clobber the OR bearer.
            os.environ["SPOTYVIBE_SKIP_KEYRING"] = "1"
            # 4000-token cap ONLY on `:free` routes (free tier has ~8k
            # credit budget per call). Paid routes get 8000 so verbose-
            # reasoning models (Claude Haiku/Sonnet) don't truncate
            # mid-playlist. See analysis.md §1 (2026-05-23).
            if any(":free" in m.lower() for m in models):
                os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "4000")
            else:
                os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "8000")
            logger.info("OpenRouter routing active for this run (key + base URL set, keyring overlay disabled, max_tokens=%s).",
                        os.environ["SPOTYVIBE_MAX_OUTPUT_TOKENS"])
        else:
            logger.warning("Eval includes OpenRouter models but [openrouter] "
                           "api_key is missing — calls will 401.")
    os.environ["RAG_ENABLED"] = "true"
    # 2026-05-07: Spotify rate-limit hardening for the eval harness.
    # The user-facing app keeps the prior 5-worker pool with no
    # post-call sleep — these env vars are eval-only. Serial mode +
    # 0.5 s per-call delay keeps the steady-state rate at ≤ 2 calls/s
    # (vs Spotify's documented ≤ 6/s per-token guidance), which has
    # two purposes:
    #   1. The previous parallel + no-sleep pattern burst-saturated
    #      the per-token sliding-window quota during a multi-scenario
    #      eval, cascading into hard 429s and (per the user) risking
    #      the account being flagged for unusual API behaviour.
    #   2. Serial calls give Retry-After back-off a fair chance to
    #      drain the window before the next call lands; parallel
    #      back-off just delays the next burst by N workers.
    # Tunable via env vars so a future low-traffic eval (single
    # scenario / single model) can opt back into faster behaviour
    # without code changes. See playlist._is_serial_search_mode.
    os.environ.setdefault("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", "1")
    os.environ.setdefault("SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S", "1.5")

    # 2026-05-14: STAGE3_MODE switch removed. Stage 3 now always uses
    # get_model() — the per-iteration OPENAI_MODEL override the harness
    # sets is respected by default. No env wiring needed here.

    from evaluation.harness import prepare_sandbox, run_for_model

    # N3 (2026-05-13): Spotify cache / 429 pre-flight is required only
    # when at least one active scenario actually verifies via Spotify
    # (push step + Spotify-search verifier). All-null / overlay / l0_l1
    # runs are decoupled from Spotify and must succeed on a machine
    # that has never authorized — that is the entire point of the
    # Track-A verifier abstraction.
    _needs_spotify = any(s.verify_mode == "spotify" for s in active_scenarios)

    try:
        prepare_sandbox(sandbox_dir, settings,
                        require_spotify_cache=_needs_spotify)
    except Exception as exc:
        logger.error("Sandbox setup failed: %s", exc)
        print(f"\n  [ERROR] Sandbox setup failed: {exc}\n", file=sys.stderr)
        return 3

    # ── Spotify 429 pre-flight ────────────────────────────────────────
    # Fire one test search BEFORE burning any OpenAI quota.  A 429 here
    # means Spotify has imposed a penalty window that our per-call back-off
    # cap (90 s) cannot drain — aborting now saves money and avoids a run
    # full of partial failures. Skipped when no active scenario uses the
    # Spotify verifier (Track A): no Spotify calls = no 429 risk worth
    # paying a pre-flight call for.
    import config as _cfg_tmp  # noqa: F401
    _cfg_tmp.load_config()
    if _needs_spotify:
        blocked_for_s = check_spotify_not_rate_limited()
        if blocked_for_s is not None:
            h, rem = divmod(blocked_for_s, 3600)
            m = rem // 60
            msg = (
                f"\n  [ERROR] Spotify search API returned 429 - account is rate-limited.\n"
                f"     Retry-After: {blocked_for_s:,} s  (~{h}h {m:02d}m)\n"
                f"     Re-run after the block expires.  No OpenAI quota was burned.\n"
            )
            logger.error(
                "Spotify 429 pre-flight: blocked for %d s (~%dh %02dm). Aborting.",
                blocked_for_s, h, m,
            )
            print(msg, file=sys.stderr)
            return 7
    else:
        logger.info(
            "Spotify 429 pre-flight skipped: no active scenario uses verify_mode='spotify'."
        )
        # N3 (2026-05-13): tell app.py's /api/run pipeline to skip its
        # production-side "Spotify is not connected" pre-check too.
        # Without this, run_pipeline aborts with status=error even
        # though the rest of the harness (sandbox setup, 429 pre-flight,
        # push step) is already Spotify-decoupled. Set BEFORE importing
        # ``app`` so the env var is visible to its request-handler scope.
        os.environ["SPOTYVIBE_SKIP_SPOTIFY_CONNECT"] = "1"

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
    logger.info("Scenarios (%d): %s", len(active_scenarios),
                ", ".join(s.name for s in active_scenarios))

    # ── Run the matrix ────────────────────────────────────────────
    summaries = []
    overall_t0 = time.monotonic()
    # 2026-05-07 (attempt 3): Spotify rate-limit hardening.
    #
    # The root problem: each run_for_model() call generates TWO
    # playlists (A + B), each verifying ~15 tracks via Spotify search.
    # Even at 1.5 s per call, that's ~45 s of sustained search traffic
    # per playlist × 2 = ~90 s per model run. With 4 models per
    # scenario and 11 scenarios, the cumulative load within Spotify's
    # rolling-window quota (believed to be 30 s or 60 s) triggers 429s
    # even when individual calls are well-spaced.
    #
    # Fix: a full 10-MINUTE cooldown between every run_for_model()
    # call (i.e. between every model × iteration slot). This ensures
    # the Spotify rolling window has fully drained before the next
    # burst of ~30 search calls begins. Yes, this makes the full eval
    # take ~18 h for 44 runs — but each run actually completes and
    # produces usable data instead of burning OpenAI tokens on a run
    # that will 429-crash during Spotify verify.
    #
    # The inter-scenario cooldown is subsumed by the per-run cooldown
    # (every scenario boundary is also a run boundary).
    # N3 (2026-05-13): the 10-minute cooldown exists solely to drain
    # Spotify's rolling-window quota between bursts of search calls.
    # When NO active scenario uses verify_mode='spotify' (null /
    # overlay / l0_l1) there is zero Spotify search traffic, so the
    # cooldown is pure dead weight — a 10-iter run would idle for
    # ~90 minutes with no benefit. Skip it in that case.
    INTER_RUN_COOLDOWN_S = 600 if _needs_spotify else 0  # 10 minutes
    is_first_run = True
    try:
        for scn_idx, active_scenario in enumerate(active_scenarios):
            logger.info(
                "═══ Scenario: %s — %s ═══",
                active_scenario.name, active_scenario.description,
            )
            for model in models:
                for iteration in range(1, iterations + 1):
                    if not is_first_run and INTER_RUN_COOLDOWN_S > 0:
                        logger.info(
                            "Cooling down %ds (%.1f min) before next run to let "
                            "Spotify rate-limit window fully drain…",
                            INTER_RUN_COOLDOWN_S,
                            INTER_RUN_COOLDOWN_S / 60,
                        )
                        time.sleep(INTER_RUN_COOLDOWN_S)
                    is_first_run = False
                    logger.info(
                        "─── %s · %s · iter %d/%d ───",
                        active_scenario.name, model, iteration, iterations,
                    )
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
                        scn=active_scenario,
                    )
                    summaries.append(result)
                    logger.info(
                        "%s · %s iter %d done in %.1fs — playlist=%d, status=%s, cleanup=%s",
                        active_scenario.name, model, iteration,
                        result.duration_s or 0,
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
