"""Benchmark orchestrator — runs the curated scenarios + gates a model.

Public entry point: :func:`run_benchmark`. The :mod:`__main__` module
provides the CLI; this module focuses on the run logic so it can also
be invoked programmatically (e.g. from a future scheduled job).

Reuses ``evaluation.harness.run_for_model`` as the per-scenario
execution unit. Adds:

  - benchmark-scenario → harness-scenario conversion (seed_profile_path
    override + playlist_size enforcement),
  - per-scenario gate evaluation (PASS/WARN/FAIL),
  - aggregate Scorecard + console + markdown rendering,
  - process exit code reflecting the verdict.

Cost note: with 6 scenarios × 1 iteration, the benchmark spends
roughly 6× one playlist generation, which on the user's defaults
(claude-haiku-4.5 via OpenRouter) is about $0.05-0.15 total. Read
the printed estimate before confirming.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .gates import (
    GateResult, VERDICT_FAIL, VERDICT_SKIPPED, evaluate_gate,
)
from .scenarios import BENCHMARK_SCENARIOS, BenchmarkScenario
from .scorecard import (
    Scorecard, finalise, render_console, render_markdown,
)


logger = logging.getLogger(__name__)


# ── Spotify rate-limit protection ────────────────────────────────────
#
# Spotify imposes a rolling-window quota on search calls. The benchmark
# generates roughly 60-120 search calls per scenario × 6 scenarios per
# run = up to ~720 calls per benchmark. Run two benchmarks back-to-back
# (different models, same account) and you risk a hard 10000+s block.
#
# Three layers of defence:
#   1. Pre-flight detection — refuse to start if the account is already
#      in a 429 penalty window.
#   2. Persistent inter-benchmark cooldown — write a timestamp on every
#      Spotify-search-heavy run; the next benchmark waits until at least
#      INTER_BENCHMARK_QUIET_S have passed since the previous run ended.
#   3. Mid-run abort — if a 429 hits during a scenario, stop the WHOLE
#      benchmark immediately instead of churning through the remaining
#      scenarios at zero Spotify-found rate.

# Inter-benchmark quiet period budget, in seconds PER SCENARIO actually
# executed in the previous run. The Spotify rolling-window quota is
# linear in search-call volume — a 6-scenario benchmark fires 6× more
# calls than a 1-scenario one and warrants 6× more cooldown. Capped at
# the FULL-benchmark equivalent (12 min) so back-to-back runs against
# the same model can't exceed Spotify's safe envelope.
INTER_BENCHMARK_QUIET_S_PER_SCENARIO = 120
INTER_BENCHMARK_QUIET_S_CAP = 720

# Per-scenario cooldown. Bumped 2026-05-23 after a back-to-back two-
# model benchmark triggered a 10922s Retry-After block. 180s gives the
# rolling-window time to drain between scenario bursts.
INTER_SCENARIO_COOLDOWN_S = 180


def _benchmark_state_file() -> Path:
    """Sandbox-relative state file the persistent tracker writes."""
    from evaluation.run_evaluation import HERE
    return HERE / ".benchmark_state.json"


def _read_last_run() -> tuple[float | None, int]:
    """Return (last_end_ts, scenario_count_last_run). (None, 0) when absent."""
    p = _benchmark_state_file()
    if not p.exists():
        return None, 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return (
            float(data.get("last_end") or 0) or None,
            int(data.get("scenarios") or 0),
        )
    except (ValueError, OSError):
        return None, 0


def _write_last_run_end(scenario_count: int) -> None:
    """Record now() as the end of a Spotify-heavy benchmark, plus its
    scenario count — the next run's cooldown scales by it."""
    p = _benchmark_state_file()
    try:
        p.write_text(
            json.dumps({"last_end": time.time(),
                        "scenarios": int(scenario_count)}),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write benchmark state: %s", exc)


def _check_inter_benchmark_cooldown() -> int:
    """Return seconds left of the inter-benchmark quiet period.

    Scales by the scenario count of the PREVIOUS run — a 1-scenario
    validation pass earns a ~2 min wait, a full 6-scenario benchmark
    earns the 12 min cap.
    """
    last_end, prev_scenarios = _read_last_run()
    if last_end is None:
        return 0
    elapsed = time.time() - last_end
    quiet_for = min(
        INTER_BENCHMARK_QUIET_S_CAP,
        max(prev_scenarios, 1) * INTER_BENCHMARK_QUIET_S_PER_SCENARIO,
    )
    remaining = quiet_for - elapsed
    return max(0, int(remaining))


# ── Cost lookup ──────────────────────────────────────────────────────


def _per_scenario_cost_estimate(model: str) -> float:
    """Best-effort per-scenario cost estimate in USD.

    The benchmark scenarios each generate two playlists (the harness's
    A + B pattern) so the per-scenario cost is roughly 2× one playlist.
    Falls back to a conservative default for unknown models — the
    estimate is a budgeting hint, not the actual bill.
    """
    # Order matters — earlier entries match more specific tokens first.
    table = [
        ("claude-haiku", 0.005),
        ("claude-sonnet", 0.03),
        ("claude-opus", 0.10),
        ("gpt-5.4-mini", 0.005),
        ("gpt-5.4", 0.04),
        ("gpt-4.1-mini", 0.005),
        ("gpt-4.1", 0.02),
        ("gpt-4o", 0.025),
        ("deepseek-v4-flash", 0.005),
        ("deepseek", 0.005),
        ("gemini-3.1-flash", 0.003),
        ("gemini", 0.01),
    ]
    m = (model or "").lower()
    for token, per_pl in table:
        if token in m:
            return per_pl * 2  # A + B playlists per scenario
    return 0.05  # unknown model — conservative


# ── Per-scenario execution ───────────────────────────────────────────


def _seed_active_profile_with_fixture(
    profile_path: Path, fixture_path: Path,
) -> None:
    """Copy *fixture_path* into the sandbox's active profile slot.

    The harness's per-scenario ``Scenario.seed_profile_path`` machinery
    handles training-step replacement. We pre-place the file so the
    fresh profile created by the harness's setup step actually carries
    the aged state before ``train_profile`` runs.
    """
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_path, profile_path)


def _build_harness_scenario(bench: BenchmarkScenario):
    """Materialise a harness ``Scenario`` for one ``BenchmarkScenario``.

    Looks up the named scenario from :mod:`evaluation.scenario`, then
    overrides ``seed_profile_path`` if the benchmark provides one.
    Returns a NEW frozen instance — the original registry entry is
    untouched.
    """
    from evaluation.scenario import SCENARIOS as HARNESS_SCENARIOS

    if bench.harness_scenario_name not in HARNESS_SCENARIOS:
        raise KeyError(
            f"Benchmark scenario {bench.name!r} references unknown "
            f"harness scenario {bench.harness_scenario_name!r}."
        )
    harness_scn = HARNESS_SCENARIOS[bench.harness_scenario_name]
    overrides: dict = {}
    # Name and description are augmented so the per-run results dir
    # collides cleanly with the benchmark scenario name (which the
    # scorecard groups on), not the underlying harness scenario.
    overrides["name"] = bench.name
    if bench.seed_profile_path:
        overrides["seed_profile_path"] = bench.seed_profile_path
    return replace(harness_scn, **overrides)


def _read_cost_from_eval_log(eval_log_path: Path) -> float | None:
    """Sum per-row USD cost from the eval.jsonl slice. None if absent."""
    if not eval_log_path.exists():
        return None
    total = 0.0
    saw_row = False
    try:
        with eval_log_path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                cost = row.get("cost_usd")
                if isinstance(cost, (int, float)):
                    total += float(cost)
                    saw_row = True
    except OSError:
        return None
    return total if saw_row else None


# ── CLI-side helpers (settings, env, prompt) ─────────────────────────


def _confirm(prompt: str, no_confirm: bool) -> bool:
    if no_confirm:
        return True
    try:
        reply = input(prompt).strip().lower()
    except EOFError:
        return False
    return reply in ("y", "yes")


def _resolve_models(cli_model: str | None) -> list[str]:
    """Pick the model(s) to benchmark.

    Precedence: CLI ``--model`` > settings.ini ``[evaluation] models``.
    A single model is expected; multi-model benchmark is a stretch
    feature (see open-ended `evaluation/run_evaluation.py` for that).
    """
    if cli_model:
        return [cli_model.strip()]
    # Reuse the existing loader so credentials + spotify config come
    # from the same place run_evaluation reads.
    from evaluation.run_evaluation import load_settings
    settings = load_settings()
    return settings["evaluation"]["models"][:1]


# ── Public entry point ──────────────────────────────────────────────


def run_benchmark(
    *,
    model: str,
    scenarios: list[str] | None = None,
    no_confirm: bool = False,
    dry_run: bool = False,
    results_dir: Path | None = None,
) -> Scorecard:
    """Run the benchmark for one model. Returns the finalised Scorecard.

    Mirrors ``evaluation.run_evaluation.main`` but:
      - always one model (the input ``model``),
      - always 1 iteration per scenario,
      - executes the benchmark scenario subset (``scenarios`` filter
        defaults to all),
      - returns a Scorecard the caller turns into an exit code.

    ``dry_run=True`` prints the plan + scorecard skeleton but does NOT
    burn any LLM/Spotify quota. Useful for "show me what would run."
    """
    # Resolve scenarios early so we fail fast on a typo
    active_names = scenarios or list(BENCHMARK_SCENARIOS.keys())
    active: list[BenchmarkScenario] = []
    for name in active_names:
        if name not in BENCHMARK_SCENARIOS:
            known = ", ".join(sorted(BENCHMARK_SCENARIOS))
            raise KeyError(
                f"Unknown benchmark scenario {name!r}. Known: {known}"
            )
        active.append(BENCHMARK_SCENARIOS[name])

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started_mono = time.monotonic()
    scorecard = Scorecard(model=model, started_at=started, finished_at=None)

    if dry_run:
        plan = [
            f"DRY RUN — would benchmark {model!r}",
            f"Scenarios ({len(active)}):",
        ]
        plan.extend(f"  - {s.name}  (target {s.gate.min_verified_count}/30)"
                    for s in active)
        plan.append("")
        plan.append("Per-scenario cost estimate: "
                    f"${_per_scenario_cost_estimate(model):.3f}")
        plan.append("Total estimate: "
                    f"${_per_scenario_cost_estimate(model) * len(active):.3f}")
        print("\n".join(plan))
        for s in active:
            scorecard.add(GateResult(
                scenario_name=s.name,
                verdict=VERDICT_SKIPPED,
                score=0.0,
                verified_count=0,
                target_count=s.gate.min_verified_count,
                spotify_found_rate=None,
                leakage_count=0,
                unique_artist_count=0,
                wall_seconds=None,
                cost_usd=None,
                hints=["DRY RUN — scenario not executed."],
            ))
        scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return finalise(scorecard)

    # Wire the same env + sandbox the open-ended harness uses
    from evaluation.run_evaluation import (
        load_settings, REPO_ROOT, RESULTS_DIR_BASE, SANDBOX_DIR_BASE,
    )

    settings = load_settings()
    # Override models list with the single model we're benchmarking
    settings["evaluation"]["models"] = [model]
    settings["evaluation"]["iterations"] = 1
    # PLAYLIST_SIZE is read by the production code via env later;
    # set it now so config.load_config() picks it up. Hard-coded 30
    # because that's the production failure size the benchmark exists
    # to catch.
    os.environ["PLAYLIST_SIZE"] = "30"
    # Settings_dict pickup: tell load_config which keys to apply.
    settings["evaluation"]["playlist_size"] = 30

    # Sandbox + results dir per benchmark invocation
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_safe = model.replace("/", "_").replace(":", "_")
    if results_dir is None:
        results_dir = RESULTS_DIR_BASE / f"benchmark-{ts}-{model_safe}"
    results_dir.mkdir(parents=True, exist_ok=True)
    sandbox_dir = SANDBOX_DIR_BASE / f"benchmark-{ts}-{model_safe}"

    # Confirm cost before burning quota
    est = _per_scenario_cost_estimate(model) * len(active)
    plan = (
        f"\n  Benchmark plan:\n"
        f"    Model      : {model}\n"
        f"    Scenarios  : {len(active)} ({', '.join(s.name for s in active)})\n"
        f"    Est. cost  : ~${est:.3f} (real LLM billing + Spotify API)\n"
        f"    Wall       : ~{4 * len(active)} min (varies by model)\n"
        f"    Sandbox    : {sandbox_dir.relative_to(REPO_ROOT)}\n"
        f"    Results    : {results_dir.relative_to(REPO_ROOT)}\n"
    )
    print(plan)
    if not _confirm("  Continue? [y/N] ", no_confirm):
        print("  Aborted — no quota spent.")
        scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return finalise(scorecard)

    # Build env + import production code under the sandbox app dir
    os.environ["SPOTYVIBE_APP_DIR"] = str(sandbox_dir)
    os.environ.setdefault("DEBUG_MODE", "true")  # always trace benchmark runs

    # OpenRouter routing — mirrors run_evaluation.py OPEN-1a logic.
    # When the model id contains "/" (provider/model form), force the
    # OpenRouter bearer, base URL, provider preset, and DISABLE the
    # keyring overlay (otherwise Windows Credential Manager's stored
    # OpenAI key clobbers our OR key and every call 401s).
    if "/" in model:
        or_key = settings.get("openrouter", {}).get("api_key", "").strip()
        if not or_key:
            print("  [ERROR] Model id contains '/' (OpenRouter form) but "
                  "[openrouter] api_key is missing from settings.ini.",
                  file=sys.stderr)
            scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return finalise(scorecard)
        os.environ["OPENAI_API_KEY"] = or_key
        os.environ["LLM_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["PROVIDER_PRESET"] = "openrouter"
        os.environ["SPOTYVIBE_SKIP_KEYRING"] = "1"
        # Output-token cap: 4000 ONLY on `:free` routes (OpenRouter's
        # free tier rejects requests without an explicit max_tokens and
        # has a ~8k credit budget per call). Paid routes get 8000 so
        # verbose-reasoning models (Claude Haiku, Sonnet) don't truncate
        # mid-playlist. Bug fix 2026-05-23: the universal 4000 cap was
        # clipping Haiku's JSON after the reasoning block, leaving the
        # playlist empty and surfacing as "1/30 verified" on aged-niche
        # scenarios. See analysis.md §1.
        if ":free" in model.lower():
            os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "4000")
        else:
            os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "8000")
        logger.info("OpenRouter routing active for %s "
                    "(OR key + keyring overlay disabled, "
                    "max_tokens=%s)",
                    model, os.environ["SPOTYVIBE_MAX_OUTPUT_TOKENS"])
    else:
        os.environ.setdefault("OPENAI_API_KEY", settings["openai"]["api_key"])

    os.environ.setdefault("SPOTIPY_CLIENT_ID",
                          settings["spotify"]["client_id"])
    os.environ.setdefault("SPOTIPY_CLIENT_SECRET",
                          settings["spotify"]["client_secret"])

    from evaluation.harness import prepare_sandbox, run_for_model

    needs_spotify = any(
        _build_harness_scenario(b).verify_mode == "spotify"
        for b in active
    )
    try:
        prepare_sandbox(sandbox_dir, settings,
                        require_spotify_cache=needs_spotify)
    except Exception as exc:
        logger.error("Sandbox setup failed: %s", exc)
        print(f"\n  [ERROR] Sandbox setup failed: {exc}\n", file=sys.stderr)
        scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return finalise(scorecard)

    if not needs_spotify:
        os.environ["SPOTYVIBE_SKIP_SPOTIFY_CONNECT"] = "1"

    # ── Spotify pre-flight + inter-benchmark cooldown ─────────────
    # Together these prevent the user from being hard-blocked by a
    # back-to-back benchmark across multiple models. Skip both when
    # no active scenario uses verify_mode='spotify' (would be wasted
    # API calls + needless wait).
    if needs_spotify:
        # Layer 2: inter-benchmark quiet period — if the previous
        # benchmark finished < INTER_BENCHMARK_QUIET_S ago, refuse to
        # start. Better to make the user wait 10 min than burn 3 h of
        # their account.
        remaining = _check_inter_benchmark_cooldown()
        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            print(
                f"\n  [WAIT] Inter-benchmark Spotify cooldown active — "
                f"{minutes}m {seconds:02d}s remaining.\n"
                f"     The previous benchmark ended recently and the "
                f"Spotify rolling-window quota needs time to drain.\n"
                f"     Last run end recorded at {_benchmark_state_file()}.\n"
                f"     Re-run after the cooldown, or pass --no-spotify-cooldown "
                f"if you are CERTAIN the account is clear.\n",
                file=sys.stderr,
            )
            scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return finalise(scorecard)

        # Layer 1: pre-flight one cheap search to confirm the account
        # is not already in a 429 penalty window. Reuses the helper
        # the open-ended harness uses for the same purpose.
        from evaluation.run_evaluation import check_spotify_not_rate_limited
        blocked_for = check_spotify_not_rate_limited()
        if blocked_for is not None and blocked_for > 0:
            h, rem = divmod(blocked_for, 3600)
            m = rem // 60
            print(
                f"\n  [ABORT] Spotify is already rate-limiting this account.\n"
                f"     Retry-After: {blocked_for:,} s  (~{h}h {m:02d}m)\n"
                f"     Re-run after the block expires. No quota was burned.\n",
                file=sys.stderr,
            )
            scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return finalise(scorecard)
        logger.info("Spotify pre-flight clear — benchmark proceeding.")

    import config  # noqa: F401 — load + apply env overrides
    from core.src import profile as profile_mod
    from core.src import analysis as analysis_mod
    from core.src import playlist as playlist_mod
    from core.src import feedback as feedback_mod
    import app as flask_module
    flask_app = flask_module.app

    # Inter-scenario cooldown — Spotify's rolling-window quota needs
    # time to drain between bursts of ~60-120 search calls per scenario.
    # Bumped 90→180s on 2026-05-23 after a back-to-back benchmark
    # triggered a 10922s Retry-After block on the user's account.
    cooldown = INTER_SCENARIO_COOLDOWN_S if needs_spotify else 0
    is_first = True
    spotify_429_aborted = False

    for bench in active:
        if spotify_429_aborted:
            # Mid-run 429 detected — record SKIPPED for remaining scenarios
            # instead of churning. Better to surface partial data with a
            # clear reason than to fake-run 5 scenarios at zero found-rate.
            scorecard.add(GateResult(
                scenario_name=bench.name,
                verdict=VERDICT_SKIPPED,
                score=0.0,
                verified_count=0,
                target_count=bench.gate.min_verified_count,
                spotify_found_rate=None,
                leakage_count=0,
                unique_artist_count=0,
                wall_seconds=None,
                cost_usd=None,
                hints=["Skipped: Spotify 429 abort earlier in this run."],
            ))
            continue
        if not is_first and cooldown:
            logger.info("Cooldown %ds before next scenario "
                        "(Spotify rolling-window drain)", cooldown)
            time.sleep(cooldown)
        is_first = False

        logger.info("Running scenario: %s", bench.name)
        harness_scn = _build_harness_scenario(bench)
        scn_t0 = time.monotonic()

        # If the benchmark supplies an aged-state fixture, the
        # harness's seed_profile_path mechanism handles it — but only
        # for the SECOND profile in the A→B pattern. For the FIRST
        # we'd need to swap before the harness's training step runs.
        # The harness's _step_seed_profile() already does this when
        # the Scenario carries a seed_profile_path. Verified by
        # reading harness.py:_step_seed_profile.

        try:
            result = run_for_model(
                model=model,
                iteration=1,
                settings=settings,
                sandbox_dir=sandbox_dir,
                results_dir=results_dir,
                flask_app=flask_app,
                profile_mod=profile_mod,
                analysis_mod=analysis_mod,
                playlist_mod=playlist_mod,
                feedback_mod=feedback_mod,
                scn=harness_scn,
            )
        except Exception as exc:
            logger.exception("Scenario %s crashed: %s", bench.name, exc)
            scorecard.add(GateResult(
                scenario_name=bench.name,
                verdict=VERDICT_FAIL,
                score=0.0,
                verified_count=0,
                target_count=bench.gate.min_verified_count,
                spotify_found_rate=None,
                leakage_count=0,
                unique_artist_count=0,
                wall_seconds=time.monotonic() - scn_t0,
                cost_usd=None,
                hints=[f"Scenario raised an exception: {exc}"],
            ))
            continue

        # Per-run eval.jsonl slice lives in results_dir/<scn>__<model>-iter1/
        per_run_dir = (
            results_dir
            / f"{bench.name}__{model.replace('/', '_').replace(':', '_')}-iter1"
        )
        eval_log = per_run_dir / "eval.jsonl"
        wall = time.monotonic() - scn_t0
        cost = _read_cost_from_eval_log(eval_log)

        gate_result = evaluate_gate(
            gate=bench.gate,
            scenario_name=bench.name,
            result_obj=result,
            eval_log_path=eval_log,
            cost_usd=cost,
            wall_seconds=wall,
        )
        scorecard.add(gate_result)
        logger.info(
            "Scenario %s: verdict=%s score=%.0f verified=%d/%d found=%.2f",
            bench.name, gate_result.verdict, gate_result.score,
            gate_result.verified_count, gate_result.target_count,
            (gate_result.spotify_found_rate or 0.0),
        )

        # Mid-run abort: if THIS scenario's verified count collapsed to
        # near-zero AND Spotify-found rate is also near-zero, a hard 429
        # is very likely. Pre-flight again — if confirmed, abort the
        # rest of the benchmark to avoid burning quota on a poisoned run.
        if needs_spotify and gate_result.verified_count <= 2 and (
            (gate_result.spotify_found_rate or 1.0) < 0.30
        ):
            from evaluation.run_evaluation import check_spotify_not_rate_limited
            try:
                blocked = check_spotify_not_rate_limited()
            except Exception:
                blocked = None
            if blocked and blocked > 60:
                h, rem = divmod(blocked, 3600)
                m = rem // 60
                logger.error(
                    "[ABORT] Spotify 429 mid-run (Retry-After %ds ~%dh %02dm). "
                    "Skipping remaining scenarios to preserve quota.",
                    blocked, h, m,
                )
                print(
                    f"\n  [ABORT] Spotify 429 detected mid-run "
                    f"(Retry-After: {blocked:,}s ~{h}h {m:02d}m).\n"
                    f"     Remaining scenarios will be marked SKIPPED.\n"
                    f"     Re-run after the block expires.\n",
                    file=sys.stderr,
                )
                spotify_429_aborted = True

    scorecard.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    final = finalise(scorecard)

    # Persist scorecard.md alongside the per-run eval slices
    try:
        (results_dir / "scorecard.md").write_text(
            render_markdown(final), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("scorecard.md write failed: %s", exc)

    # Persistent inter-benchmark cooldown bookkeeping: any Spotify-heavy
    # benchmark records its end time so the next invocation can refuse
    # to run inside the rolling-window quiet period.
    if needs_spotify:
        _write_last_run_end(len(active))
        wait_s = min(
            INTER_BENCHMARK_QUIET_S_CAP,
            len(active) * INTER_BENCHMARK_QUIET_S_PER_SCENARIO,
        )
        logger.info(
            "Recorded benchmark end (scenarios=%d); next Spotify-heavy "
            "benchmark must wait %ds (%dm) before starting.",
            len(active), wait_s, wait_s // 60,
        )

    # Sandbox teardown — keep results, drop sandbox
    try:
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
    except OSError as exc:
        logger.warning("Sandbox cleanup failed: %s", exc)

    return final


__all__ = ["run_benchmark"]
