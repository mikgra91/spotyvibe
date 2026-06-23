"""CLI entry point — ``python -m evaluation.benchmark``.

Usage:
    python -m evaluation.benchmark --model <model>
    python -m evaluation.benchmark --model X --scenarios A,B
    python -m evaluation.benchmark --model X --dry-run
    python -m evaluation.benchmark --list-scenarios

Exit codes:
    0 — PRODUCTION_READY or DEGRADED
    1 — NOT_PRODUCTION_READY (any FAIL or avg score < 60)
    2 — configuration error (missing settings.ini, unknown scenario)
    130 — Ctrl+C
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make ``import evaluation.*`` work when run as a module from repo root.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _setup_logging():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m evaluation.benchmark",
        description=(
            "Production-readiness benchmark for SpotyVibe. Runs a "
            "curated set of realistic scenarios + hard pass/fail "
            "gates and prints a one-screen scorecard."
        ),
    )
    p.add_argument(
        "--model",
        help=(
            "Model id to benchmark (e.g. anthropic/claude-haiku-4.5). "
            "When omitted, uses the first model in evaluation/settings.ini."
        ),
    )
    p.add_argument(
        "--scenarios",
        help=(
            "Comma-separated subset of benchmark scenarios to run. "
            "Default: all. Use --list-scenarios to see options."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan + scorecard skeleton without burning quota.",
    )
    p.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the cost-confirmation prompt. Use in CI.",
    )
    p.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print the benchmark scenario list with gate thresholds + exit.",
    )
    p.add_argument(
        "--reset-spotify-cooldown",
        action="store_true",
        help=(
            "Clear the persistent inter-benchmark Spotify cooldown. Use "
            "ONLY if you are certain the account is not currently 429-blocked "
            "(e.g. you waited the full cooldown manually)."
        ),
    )
    return p


def _list_scenarios() -> int:
    from .scenarios import BENCHMARK_SCENARIOS
    print("\n  Benchmark scenarios:\n")
    for name, scn in BENCHMARK_SCENARIOS.items():
        g = scn.gate
        print(f"  {name}")
        print(f"    {scn.description}")
        print(f"    gate: min_verified={g.min_verified_count}/30 "
              f"min_found={g.min_spotify_found_rate:.2f} "
              f"max_leakage={g.max_leakage_count} "
              f"min_unique_artists={g.min_unique_artist_count}")
        if scn.seed_profile_path:
            print(f"    aged-state fixture: "
                  f"{scn.seed_profile_path.name}")
        print("")
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = _build_parser().parse_args(argv)

    if args.list_scenarios:
        return _list_scenarios()

    if args.reset_spotify_cooldown:
        from .runner import _benchmark_state_file
        p = _benchmark_state_file()
        if p.exists():
            try:
                p.unlink()
                print(f"  Cleared {p}")
            except OSError as exc:
                print(f"  [ERROR] Could not delete {p}: {exc}",
                      file=sys.stderr)
                return 2
        else:
            print("  No cooldown state file to clear.")
        return 0

    try:
        # Local import so --list-scenarios works without evaluation/
        # settings.ini.
        from .runner import run_benchmark
        from .scorecard import render_console
    except ImportError as exc:
        print(f"  [ERROR] Benchmark package import failed: {exc}",
              file=sys.stderr)
        return 2

    try:
        from .runner import _resolve_models
        models = _resolve_models(args.model)
    except SystemExit:
        return 2
    if not models:
        print("  [ERROR] No model specified and none configured in "
              "evaluation/settings.ini.", file=sys.stderr)
        return 2

    if len(models) > 1:
        print(f"  [WARN] {len(models)} models in settings — "
              f"benchmarking only the first: {models[0]}",
              file=sys.stderr)
    model = models[0]

    scenarios = (
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
        if args.scenarios else None
    )

    try:
        scorecard = run_benchmark(
            model=model,
            scenarios=scenarios,
            no_confirm=args.no_confirm,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        return 130
    except KeyError as exc:
        print(f"  [ERROR] {exc}", file=sys.stderr)
        return 2

    print(render_console(scorecard))
    return scorecard.exit_code


if __name__ == "__main__":
    sys.exit(main())
