"""CLI entry point for Track B probes.

Examples:
    # Dry-run (no API calls): print prompts and rough cost estimate.
    python -m evaluation.probes --model gpt-5.4-mini --battery default --dry-run

    # Run the default 8-probe battery against one model (real billing).
    python -m evaluation.probes --model gpt-5.4-mini --battery default --confirm

    # Pick specific probes.
    python -m evaluation.probes --model gpt-5.4 --probes B-1,B-6 --confirm

Outputs land under ``evaluation/probes/results/<UTC timestamp>/``:
    probes.jsonl       — one ProbeResult per line
    fingerprint.json   — aggregated fingerprint card (one per model)

Per S.6 #3 of next-steps.md: probes are on-demand and investigation-
driven; this CLI never auto-runs. ``--confirm`` is required for real
OpenAI billing, mirroring the eval harness UX.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    probe_b1_constraint,
    probe_b2_overconstraint,
    probe_b3_confabulation,
    probe_b4_omission,
    probe_b5_format,
    probe_b6_consistency,
    probe_b10_cite,
    probe_b11_empty_pool,
    runner,
)


# Battery presets - canonical name -> module list.
_BATTERIES: dict[str, list[Any]] = {
    "default": [
        probe_b1_constraint,
        probe_b2_overconstraint,
        probe_b3_confabulation,
        probe_b4_omission,
        probe_b5_format,
        probe_b6_consistency,
        probe_b10_cite,
        probe_b11_empty_pool,
    ],
    "minimal": [probe_b1_constraint, probe_b6_consistency],          # validates wiring
}


_ALL_PROBES_BY_PREFIX: dict[str, Any] = {
    "B-1":  probe_b1_constraint,
    "B-2":  probe_b2_overconstraint,
    "B-3":  probe_b3_confabulation,
    "B-4":  probe_b4_omission,
    "B-5":  probe_b5_format,
    "B-6":  probe_b6_consistency,
    "B-10": probe_b10_cite,
    "B-11": probe_b11_empty_pool,
}


_RESULTS_ROOT = Path(__file__).resolve().parent / "results"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m evaluation.probes",
        description="Run Track B synthetic model-behaviour probes.",
    )
    p.add_argument("--model", required=True,
                   help="OpenAI model id (e.g. gpt-5.4-mini).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--battery", choices=sorted(_BATTERIES.keys()), default="default",
                   help="Named probe battery (default: 'default' = all 8).")
    g.add_argument("--probes",
                   help="Comma-separated probe prefixes (e.g. 'B-1,B-6').")
    p.add_argument("--dry-run", action="store_true",
                   help="Print prompts and estimated cost; no API calls.")
    p.add_argument("--confirm", action="store_true",
                   help="Required to actually call OpenAI (otherwise dry-run).")
    p.add_argument("--out", type=Path, default=None,
                   help="Output directory (default: evaluation/probes/results/<ts>/).")
    p.add_argument("--fingerprint-version", type=int, default=1)
    return p.parse_args(argv)


def _select_probes(args: argparse.Namespace) -> list[Any]:
    if args.probes:
        modules: list[Any] = []
        for raw in args.probes.split(","):
            key = raw.strip()
            if not key:
                continue
            if key not in _ALL_PROBES_BY_PREFIX:
                raise SystemExit(
                    f"Unknown probe prefix '{key}'. "
                    f"Known: {sorted(_ALL_PROBES_BY_PREFIX.keys())}"
                )
            modules.append(_ALL_PROBES_BY_PREFIX[key])
        return modules
    return _BATTERIES[args.battery]


def _estimate_cost(modules: list[Any], model: str) -> tuple[float, int]:
    """Rough cost estimate using a 500-in / 300-out token assumption per
    call. Multiplied by total call count (sum of runs across variants).
    """
    total_calls = 0
    for mod in modules:
        for v in mod.VARIANTS:
            total_calls += int(mod.RUNS_PER_VARIANT.get(v, 1))
    per_call_usd = runner.estimate_cost_usd(model, 500, 300)
    return per_call_usd * total_calls, total_calls


def _print_dry_run(modules: list[Any], model: str) -> None:
    print(f"\nDry-run plan for model: {model}")
    total_cost, total_calls = _estimate_cost(modules, model)
    for mod in modules:
        for v in mod.VARIANTS:
            runs = mod.RUNS_PER_VARIANT.get(v, 1)
            print(f"  - {mod.PROBE_ID:<35} variant={v:<25} runs={runs}")
            if runs >= 1:
                msgs = mod.build_messages(v)
                preview = msgs[-1]["content"][:140].replace("\n", " ")
                print(f"      user[:140] = {preview!r}")
    print(f"\nTotal calls: {total_calls}")
    print(f"Estimated cost: ~${total_cost:.4f}")
    print("(no API calls made; pass --confirm to run for real)\n")


def _confirm_or_exit(modules: list[Any], model: str) -> None:
    total_cost, total_calls = _estimate_cost(modules, model)
    print(f"\nProbe battery plan")
    print(f"  Model        : {model}")
    print(f"  Probe count  : {len(modules)}")
    print(f"  Total calls  : {total_calls}")
    print(f"  Est. cost    : ~${total_cost:.4f} (real OpenAI billing)")
    print( "  Output       : see --out")
    ans = input("\nProceed? [y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)


def _write_outputs(
    *,
    out_dir: Path,
    results: list[runner.ProbeResult],
    fingerprint: runner.Fingerprint,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probes.jsonl").write_text(
        runner.results_to_jsonl(results), encoding="utf-8"
    )
    (out_dir / "fingerprint.json").write_text(
        json.dumps(fingerprint.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {len(results)} probe results to: {out_dir}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    modules = _select_probes(args)

    if not args.confirm or args.dry_run:
        _print_dry_run(modules, args.model)
        return 0

    # Pull OPENAI_API_KEY out of keyring / .credentials into os.environ
    # (same mechanism the eval harness uses). Skipped on dry-run so the
    # CLI is usable without credentials.
    import config
    config.load_config()

    _confirm_or_exit(modules, args.model)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or (_RESULTS_ROOT / ts)

    t0 = time.monotonic()
    results = runner.run_battery(modules, args.model)
    duration = time.monotonic() - t0

    fingerprint = runner.aggregate_fingerprint(
        results,
        model=args.model,
        captured_at=datetime.now(timezone.utc).isoformat(),
        fingerprint_version=args.fingerprint_version,
        probe_modules=modules,
    )
    _write_outputs(out_dir=out_dir, results=results, fingerprint=fingerprint)
    print(f"Battery wall time: {duration:.2f}s | total cost: ${fingerprint.total_cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
