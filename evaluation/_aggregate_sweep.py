"""Aggregate every (block, pool, model) eval.jsonl referenced in a sweep manifest
into a single CSV. Designed to be called by `evaluation/run_pool_sweep.sh`.

Usage:
    python evaluation/_aggregate_sweep.py <manifest.tsv> <out.csv>

The manifest is the TSV produced by `run_pool_sweep.sh`:
    block  pool  run_dir  start  end  status  n_429
"""
import csv
import json
import pathlib
import sys

if len(sys.argv) != 3:
    sys.exit("usage: _aggregate_sweep.py <manifest.tsv> <out.csv>")

MANIFEST = pathlib.Path(sys.argv[1])
OUT      = pathlib.Path(sys.argv[2])
ROOT     = pathlib.Path("evaluation/results")

# Pricing for cost re-derivation (re-derived from token usage in eval.jsonl,
# so the CSV is independent of the harness's own cost reporting).
PRICING = json.loads(
    pathlib.Path("frontend/static/data/pricing.json").read_text(encoding="utf-8")
)["models"]


def usd(model: str, usage: dict | None) -> float:
    if not usage or model not in PRICING:
        return 0.0
    p = PRICING[model]
    inp = usage.get("prompt_tokens", 0) or 0
    out = usage.get("completion_tokens", 0) or 0
    return inp / 1e6 * p["input_per_1m"] + out / 1e6 * p["output_per_1m"]


def parse_run_dir(model_dir: pathlib.Path, model: str) -> dict:
    """Aggregate one model's eval.jsonl into a single row of metrics."""
    n_tracks = n_cited = n_found = 0
    cost_stage3 = cost_stage2 = cost_profile = cost_analysis = 0.0
    lat_stage3: list[float] = []
    stage2_in = stage2_out = None
    track_keys: list[str] = []

    for ln in (model_dir / "eval.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except Exception:
            continue
        kind = r.get("kind")
        if kind == "track":
            n_tracks += 1
            if r.get("has_must_have_cite"):
                n_cited += 1
            if r.get("found_on_spotify"):
                n_found += 1
            # Track-set identity, for inter-block overlap analysis later.
            track_keys.append(f"{r.get('artist','')}::{r.get('track','')}".lower())
        elif kind == "batch_summary":
            cost_stage3 += usd(r.get("model", model), r.get("usage"))
            if r.get("latency_s"):
                lat_stage3.append(float(r["latency_s"]))
        elif kind == "stage2_summary":
            cost_stage2 += usd(r.get("model"), r.get("usage"))
            if stage2_in is None:
                stage2_in = r.get("candidates_in")
                stage2_out = r.get("approved_out")
        elif kind == "profile_update_summary":
            cost_profile += usd(r.get("model", model), r.get("usage"))
        elif kind == "analysis_summary":
            cost_analysis += usd(r.get("model", model), r.get("usage"))

    sj = json.loads((model_dir / "summary.json").read_text(encoding="utf-8"))
    wall = sj.get("duration_s")
    cost_total = cost_stage3 + cost_stage2 + cost_profile + cost_analysis
    p50 = sorted(lat_stage3)[len(lat_stage3) // 2] if lat_stage3 else None

    return {
        "tracks":     n_tracks,
        "found_pct":  round(100 * n_found / max(n_tracks, 1), 1),
        "cite_pct":   round(100 * n_cited / max(n_tracks, 1), 1),
        "cost":       round(cost_total, 4),
        "cost_s3":    round(cost_stage3, 4),
        "wall":       round(wall, 1) if wall else None,
        "p50":        round(p50, 1) if p50 else None,
        "stage2_in":  stage2_in,
        "stage2_out": stage2_out,
        # Pipe-separated for round-trip into a CSV cell. Lets a follow-up
        # analyser compute |B1 ∩ B2| without re-reading every eval.jsonl.
        "track_keys": "|".join(track_keys),
    }


rows = []
with MANIFEST.open(encoding="utf-8") as f:
    next(f)  # header
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        # Tolerant of older 5-column manifests (no status/n_429 columns).
        block, pool, rd = parts[0], parts[1], parts[2]
        status = parts[5] if len(parts) > 5 else "ok"
        n_429  = parts[6] if len(parts) > 6 else "0"
        run_root = ROOT / rd
        if not run_root.exists():
            print(f"⚠ skipping missing run dir: {run_root}", file=sys.stderr)
            continue
        for model_dir in sorted(run_root.iterdir()):
            if not model_dir.is_dir() or not (model_dir / "eval.jsonl").exists():
                continue
            model = model_dir.name.removesuffix("-iter1")
            metrics = parse_run_dir(model_dir, model)
            rows.append({
                "block": int(block), "pool": int(pool), "model": model,
                "run_status": status, "n_429": int(n_429),
                **metrics,
            })

if not rows:
    sys.exit("ERROR: no rows aggregated — manifest empty or all run dirs missing")

with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print(f"Aggregated {len(rows)} rows from {MANIFEST.name} -> {OUT}")


