"""Aggregate eval.jsonl rows into per-run summaries and a comparison.md.

Reads the per-run ``eval.jsonl`` slices written by ``harness.py`` and
rolls up:

  - Cost (input/output tokens × pricing.json $/M-tok rates)
  - Latency (p50/p95 from run_summary rows; per-feature from the
    relevant *_summary rows)
  - Quality signals (Spotify-found rate, must_have cite rate, like/dislike
    rate against the deterministic feedback rule)

The output is a plain-text ``comparison.md`` file the user can open in
any editor, plus per-model ``summary.json`` files (already written by
the harness). The comparison Markdown is the "executive summary" — the
full row-level data stays in eval.jsonl for pandas analysis.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_pricing(repo_root: Path) -> dict[str, dict[str, float]]:
    """Read pricing.json. Returns model_id → {input_per_1m, output_per_1m}."""
    p = repo_root / "frontend" / "static" / "data" / "pricing.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("models", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _cost_for_usage(usage: dict | None, pricing_entry: dict | None) -> float | None:
    """Compute USD cost for one ``usage`` dict against a pricing entry.

    Returns None when either input is missing — surfaces "unmeasured"
    rather than silently reporting $0.
    """
    if not usage or not pricing_entry:
        return None
    pin = usage.get("prompt_tokens") or 0
    pout = usage.get("completion_tokens") or 0
    return (pin / 1_000_000) * pricing_entry.get("input_per_1m", 0) + \
           (pout / 1_000_000) * pricing_entry.get("output_per_1m", 0)


# ── Per-run rollup ───────────────────────────────────────────────────

def summarise_run(eval_log: Path, model: str,
                   pricing: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Aggregate one run's ``eval.jsonl`` slice into a flat summary dict."""
    rows = _read_jsonl(eval_log)
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_kind[r.get("kind", "track")].append(r)

    pricing_entry = pricing.get(model)

    # ── Feature costs ─────────────────────────────────────────────
    feature_costs: dict[str, float | None] = {}
    feature_latencies: dict[str, float | None] = {}
    feature_token_totals: dict[str, int | None] = {}

    def _aggregate(rows_for_feature: list[dict]) -> tuple[float | None, float | None, int | None]:
        if not rows_for_feature:
            return None, None, None
        total_cost = 0.0
        total_latency = 0.0
        total_tokens = 0
        any_priced = False
        for r in rows_for_feature:
            usage = r.get("usage")
            # Per-feature rows may use the model under test (analysis,
            # profile_update, batch_summary) OR a different model
            # (stage2_summary uses STAGE2_MODEL).
            row_model = r.get("model") or model
            row_pricing = pricing.get(row_model) or pricing_entry
            cost = _cost_for_usage(usage, row_pricing)
            if cost is not None:
                total_cost += cost
                any_priced = True
            if r.get("latency_s") is not None:
                total_latency += r["latency_s"]
            if usage and usage.get("total_tokens"):
                total_tokens += usage["total_tokens"]
        return (total_cost if any_priced else None,
                total_latency if total_latency else None,
                total_tokens if total_tokens else None)

    for feature in ("batch_summary", "stage2_summary",
                    "profile_update_summary", "analysis_summary"):
        c, lat, tok = _aggregate(by_kind.get(feature, []))
        feature_costs[feature] = c
        feature_latencies[feature] = lat
        feature_token_totals[feature] = tok

    total_cost = sum(c for c in feature_costs.values() if c is not None) or None

    # ── Quality signals ───────────────────────────────────────────
    track_rows = by_kind.get("track", [])
    spotify_found_rate = None
    must_have_cite_rate = None
    if track_rows:
        spotify_found_rate = round(
            sum(1 for r in track_rows if r.get("found_on_spotify"))
            / len(track_rows), 3,
        )
        cited_rows = [r for r in track_rows if r.get("has_must_have_cite") is not None]
        if cited_rows:
            must_have_cite_rate = round(
                sum(1 for r in cited_rows if r["has_must_have_cite"])
                / len(cited_rows), 3,
            )

    # ── Latency from run_summary if available ─────────────────────
    run_p50 = run_p95 = total_wall = None
    if by_kind.get("run_summary"):
        rs = by_kind["run_summary"][-1]
        latency_block = rs.get("batch_latency_s") or {}
        run_p50 = latency_block.get("p50")
        run_p95 = latency_block.get("p95")
        total_wall = rs.get("total_wall_s")

    # ── Stage 2 specific ──────────────────────────────────────────
    stage2_status = stage2_candidates_in = stage2_approved_out = None
    if by_kind.get("stage2_summary"):
        s2 = by_kind["stage2_summary"][-1]
        stage2_status = s2.get("status")
        stage2_candidates_in = s2.get("candidates_in")
        stage2_approved_out = s2.get("approved_out")

    return {
        "model": model,
        "row_count": len(rows),
        "rows_by_kind": {k: len(v) for k, v in by_kind.items()},
        "total_cost_usd": round(total_cost, 4) if total_cost is not None else None,
        "feature_costs_usd": {
            k: (round(v, 4) if v is not None else None)
            for k, v in feature_costs.items()
        },
        "feature_latency_s": {
            k: (round(v, 2) if v is not None else None)
            for k, v in feature_latencies.items()
        },
        "feature_total_tokens": feature_token_totals,
        "playlist_p50_s": run_p50,
        "playlist_p95_s": run_p95,
        "playlist_total_wall_s": total_wall,
        "spotify_found_rate": spotify_found_rate,
        "must_have_cite_rate": must_have_cite_rate,
        "stage2": {
            "status": stage2_status,
            "candidates_in": stage2_candidates_in,
            "approved_out": stage2_approved_out,
        },
    }


# ── Comparison report ────────────────────────────────────────────────

def write_comparison_report(results_dir: Path, repo_root: Path) -> Path:
    """Aggregate all per-run summaries into ``comparison.md``.

    Picks up every ``{model}-iter{n}/`` subdirectory under ``results_dir``,
    reads each one's ``eval.jsonl`` slice, and writes a side-by-side
    table per model.
    """
    pricing = _load_pricing(repo_root)
    rows: list[dict] = []
    for sub in sorted(results_dir.iterdir()):
        if not sub.is_dir():
            continue
        eval_log = sub / "eval.jsonl"
        run_summary = sub / "summary.json"
        if not run_summary.exists():
            continue
        meta = json.loads(run_summary.read_text(encoding="utf-8"))
        agg = summarise_run(eval_log, meta["model"], pricing)
        agg["iteration"] = meta["iteration"]
        agg["duration_s"] = meta.get("duration_s")
        agg["error"] = meta.get("error")
        agg["seed_train_status"] = meta.get("seed_train_status")
        agg["analysis_status"] = meta.get("analysis_status")
        agg["playlist_status"] = meta.get("playlist_status")
        agg["feedback_status"] = meta.get("feedback_status")
        agg["refine_train_status"] = meta.get("refine_train_status")
        agg["cleanup_status"] = meta.get("cleanup_status")
        agg["playlist_track_count"] = meta.get("playlist_track_count")
        rows.append(agg)

    if not rows:
        logger.warning("No run summaries found in %s", results_dir)
        return results_dir / "comparison.md"

    # ── Format Markdown ───────────────────────────────────────────
    out = ["# Evaluation comparison",
           "",
           f"Generated: {results_dir.name}",
           "",
           "## Per-run rollup",
           "",
           "| Model | Iter | Cost ($) | Wall (s) | p50 (s) | p95 (s) | Tracks | Spotify-found | Must-have cite | Stage2 | Status | Cleanup |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for r in rows:
        s2 = r["stage2"]
        s2_label = (
            f"{s2['approved_out']}/{s2['candidates_in']} ({s2['status']})"
            if s2["status"] else "—"
        )
        status = "ok"
        if r["error"]:
            status = f"error: {r['error'][:40]}"
        out.append(
            f"| {r['model']} | {r['iteration']} "
            f"| {_fmt(r['total_cost_usd'])} "
            f"| {_fmt(r['playlist_total_wall_s'])} "
            f"| {_fmt(r['playlist_p50_s'])} "
            f"| {_fmt(r['playlist_p95_s'])} "
            f"| {r.get('playlist_track_count') or '—'} "
            f"| {_fmt_pct(r['spotify_found_rate'])} "
            f"| {_fmt_pct(r['must_have_cite_rate'])} "
            f"| {s2_label} "
            f"| {status} "
            f"| {r.get('cleanup_status', '—')} |"
        )

    out += ["", "## Cost breakdown by feature ($)", "",
            "| Model | Iter | Stage 3 (batches) | Stage 2 | Profile updates | Band/Song Analysis | Total |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        fc = r["feature_costs_usd"]
        out.append(
            f"| {r['model']} | {r['iteration']} "
            f"| {_fmt(fc['batch_summary'])} "
            f"| {_fmt(fc['stage2_summary'])} "
            f"| {_fmt(fc['profile_update_summary'])} "
            f"| {_fmt(fc['analysis_summary'])} "
            f"| {_fmt(r['total_cost_usd'])} |"
        )

    out += ["", "## Latency by feature (s)", "",
            "| Model | Iter | Stage 3 sum | Stage 2 | Profile updates | Band/Song Analysis |",
            "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        fl = r["feature_latency_s"]
        out.append(
            f"| {r['model']} | {r['iteration']} "
            f"| {_fmt(fl['batch_summary'])} "
            f"| {_fmt(fl['stage2_summary'])} "
            f"| {_fmt(fl['profile_update_summary'])} "
            f"| {_fmt(fl['analysis_summary'])} |"
        )

    out += ["", "## Eval-log row counts", "",
            "(Sanity check that telemetry actually fired for every feature.)",
            "",
            "| Model | Iter | track | batch_summary | stage2_summary | profile_update_summary | analysis_summary | run_summary |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        rk = r["rows_by_kind"]
        out.append(
            f"| {r['model']} | {r['iteration']} "
            f"| {rk.get('track', 0)} "
            f"| {rk.get('batch_summary', 0)} "
            f"| {rk.get('stage2_summary', 0)} "
            f"| {rk.get('profile_update_summary', 0)} "
            f"| {rk.get('analysis_summary', 0)} "
            f"| {rk.get('run_summary', 0)} |"
        )

    out.append("")
    dest = results_dir / "comparison.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    return dest


def _fmt(v: float | None, places: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{places}f}".rstrip("0").rstrip(".") or "0"
    return str(v)


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"
