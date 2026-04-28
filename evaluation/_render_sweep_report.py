"""Generate a markdown comparison report from a sweep summary CSV.

Usage:
    python evaluation/_render_sweep_report.py <summary.csv> <out.md>

The CSV is the one produced by `_aggregate_sweep.py`. The report adapts to the
actual (block, pool, model) combinations present — it does NOT assume a fixed
sequence, so it works for any sweep configuration the driver script ran.
"""
import csv
import pathlib
import statistics
import sys

if len(sys.argv) != 3:
    sys.exit("usage: _render_sweep_report.py <summary.csv> <out.md>")

CSV = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
if not rows:
    sys.exit("ERROR: summary CSV is empty")

# Discover the actual sweep dimensions from the data.
models = sorted({r["model"] for r in rows})
pools  = sorted({int(r["pool"]) for r in rows})
blocks = sorted({int(r["block"]) for r in rows})


def by(b, p, m):
    for r in rows:
        if int(r["block"]) == b and int(r["pool"]) == p and r["model"] == m:
            return r
    return None


def mean_cell(p, m, key):
    vals = []
    for b in blocks:
        r = by(b, p, m)
        if r and r.get(key) not in (None, ""):
            vals.append(float(r[key]))
    return statistics.mean(vals) if vals else None


def overlap_pct(b1, b2, p, m):
    """|tracks(b1) ∩ tracks(b2)| / max  — measures how much of the noise is in
    the picks vs in the rationale phrasing."""
    r1, r2 = by(b1, p, m), by(b2, p, m)
    if not (r1 and r2):
        return None
    s1 = set(filter(None, (r1.get("track_keys") or "").split("|")))
    s2 = set(filter(None, (r2.get("track_keys") or "").split("|")))
    if not s1 or not s2:
        return None
    return round(100 * len(s1 & s2) / max(len(s1), len(s2)), 1)


out = []
W = out.append

W("# Pool-size sweep — comparison report")
W("")
W(f"**Sweep dimensions:** pools = {pools}, blocks = {blocks}, models = {models}")
W(f"**Source:** `{CSV.name}` ({len(rows)} rows)")
W("")
W("---")
W("")

# ── Raw results ─────────────────────────────────────────────────────────────
W("## Raw results — every (model, pool, block)")
W("")
W("| Model | Pool | Block | Cite % | Cost $ | Stage 3 $ | Wall s | p50 s | Stage 2 | 429 |")
W("|---|---:|---:|---:|---:|---:|---:|---:|---|---:|")
for m in models:
    for p in pools:
        for b in blocks:
            r = by(b, p, m)
            if not r:
                continue
            W(f"| {m} | {p} | {b} | {r['cite_pct']} | {r['cost']} | {r['cost_s3']} | "
              f"{r['wall']} | {r['p50']} | {r['stage2_out']}/{r['stage2_in']} | {r['n_429']} |")
W("")
W("---")
W("")

# ── Determinism: only meaningful when ≥ 2 blocks exist ──────────────────────
if len(blocks) >= 2:
    b1, b2 = blocks[0], blocks[1]
    W(f"## Determinism — block {b1} vs block {b2}")
    W("")
    W(f"`Δ` = block {b2} − block {b1}. `Picks shared` = % of tracks shared between blocks "
      "(higher → noise is in rationale phrasing, not pick stability).")
    W("")
    W(f"| Model | Pool | Cite % B{b1} → B{b2} (Δ) | Picks shared | Cost $ Δ | Wall s Δ |")
    W("|---|---:|---|---:|---:|---:|")
    for m in models:
        for p in pools:
            r1, r2 = by(b1, p, m), by(b2, p, m)
            if not (r1 and r2):
                continue
            dc = float(r2["cite_pct"]) - float(r1["cite_pct"])
            d_cost = float(r2["cost"]) - float(r1["cost"])
            d_wall = float(r2["wall"]) - float(r1["wall"])
            ov = overlap_pct(b1, b2, p, m)
            ov_str = f"{ov}%" if ov is not None else "—"
            W(f"| {m} | {p} | {r1['cite_pct']} → {r2['cite_pct']} ({dc:+.1f} pp) "
              f"| {ov_str} | {d_cost:+.4f} | {d_wall:+.1f} |")
    W("")

    W("### Determinism verdict (cite-rate variance between blocks)")
    W("")
    W("(1 cited track out of 15 = 6.67 pp.)")
    W("")
    W("| Model | Pool | Mean cite % | B↔B Δ | Verdict |")
    W("|---|---:|---:|---:|---|")
    for m in models:
        for p in pools:
            r1, r2 = by(b1, p, m), by(b2, p, m)
            if not (r1 and r2):
                continue
            c1 = float(r1["cite_pct"]); c2 = float(r2["cite_pct"])
            mean = (c1 + c2) / 2
            delta = abs(c2 - c1)
            if delta <= 6.7:
                v = "✅ stable (≤1 track flip)"
            elif delta <= 13.4:
                v = "🟡 moderate (2 tracks)"
            else:
                v = "🔴 noisy (≥3 tracks)"
            W(f"| {m} | {p} | {mean:.1f} | {delta:.1f} pp | {v} |")
    W("")
    W("---")
    W("")

# ── Per-model pool effect (mean over blocks) ────────────────────────────────
W(f"## Per-model pool-size effect (mean over {len(blocks)} block(s))")
W("")
W("| Model | Pool | Cite % (mean) | Cost $ (mean) | Wall s (mean) | Stage 2 approved |")
W("|---|---:|---:|---:|---:|---|")
for m in models:
    for p in pools:
        cite = mean_cell(p, m, "cite_pct")
        cost = mean_cell(p, m, "cost")
        wall = mean_cell(p, m, "wall")
        any_row = by(blocks[0], p, m) or {}
        s2 = f"{any_row.get('stage2_out','?')}/{any_row.get('stage2_in','?')}"
        if cite is None:
            continue
        W(f"| {m} | {p} | {cite:.1f} | {cost:.4f} | {wall:.1f} | {s2} |")
W("")

# ── Best pool per model ─────────────────────────────────────────────────────
W("### Best pool per model (by mean cite, cost as tie-breaker)")
W("")
W("| Model | Best pool | Mean cite % | Mean cost $ | Other pools |")
W("|---|---:|---:|---:|---|")
for m in models:
    cands = []
    for p in pools:
        cite = mean_cell(p, m, "cite_pct")
        cost = mean_cell(p, m, "cost")
        if cite is None:
            continue
        cands.append((p, cite, cost))
    if not cands:
        continue
    cands.sort(key=lambda t: (-t[1], t[2]))
    p, c, co = cands[0]
    others = " | ".join(f"pool {pp}: {cc:.1f}%" for pp, cc, _ in cands if pp != p)
    W(f"| {m} | **{p}** | {c:.1f} | {co:.4f} | {others} |")
W("")

# ── Per-block winner cross-check (only when ≥ 2 blocks) ─────────────────────
if len(blocks) >= 2:
    W("### Per-block winners (a robust winner appears in every block)")
    W("")
    hdr = "| Model | " + " | ".join(f"Block {b} best" for b in blocks) + " | Robust? |"
    sep = "|---|" + "|".join("---" for _ in blocks) + "|---|"
    W(hdr); W(sep)
    for m in models:
        per_block = []
        for b in blocks:
            ranked = sorted(
                ((p, float(by(b, p, m)["cite_pct"])) for p in pools if by(b, p, m)),
                key=lambda t: -t[1],
            )
            per_block.append(ranked[0] if ranked else (None, None))
        winners = {p for p, _ in per_block if p is not None}
        robust = "✅ yes" if len(winners) == 1 else "❌ no"
        cells = " | ".join(
            f"pool {p} ({c:.1f}%)" if p is not None else "—"
            for p, c in per_block
        )
        W(f"| {m} | {cells} | {robust} |")
    W("")
    W("---")
    W("")

# ── 429 / aborted-run summary ───────────────────────────────────────────────
total_429 = sum(int(r["n_429"]) for r in rows)
if total_429 > 0:
    W("## ⚠ Spotify rate-limit hits during this sweep")
    W("")
    W(f"Total 429 errors observed: **{total_429}** across all runs. Cells with non-zero `429`")
    W("in the raw table above had retries kick in; if any run hit the abort threshold the")
    W("sweep stopped early. Increase the cooldown (env `COOLDOWN`) before re-running.")
    W("")

# ── Footer ──────────────────────────────────────────────────────────────────
W("---")
W("")
W("## How to read this report")
W("")
W("- **Cite %** is the share of picked tracks whose rationale arg cites a `must_have`"
  " preference token. It's a paraphrase-sensitive proxy — treat ±13 pp differences as"
  " possible noise unless the same delta repeats across blocks.")
W("- **Picks shared** measures how much of the block-to-block variance is *real* model"
  " non-determinism (low overlap → different picks) vs *metric* noise (high overlap →"
  " same picks, different rationale wording).")
W("- **Stage 2 approved** at `N/N` means the retrieval pipeline gave 100% on-genre"
  " candidates. Anything below means Stage 2 had to filter avoid-list violators.")
W("- **Best pool** is the strongest signal when a model wins the *same* pool across"
  " every block. A model whose winner flips between blocks is in the noise floor.")

OUT.write_text("\n".join(out), encoding="utf-8")
print(f"Wrote {OUT} ({len(out)} lines)")

