"""Retry the rate-limited / partial models from openrouter_smoke.py.

Skips probes that already PASSED. Re-fires only failures + ERR + missing.
Appends to responses.jsonl and rewrites SUMMARY.md.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import openrouter_smoke as base  # noqa: E402

KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("SV_TEST_KEY")
if not KEY:
    print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
    sys.exit(2)
base.KEY = KEY

OUT_DIR = Path(__file__).parent / "results" / "openrouter_smoke"
JSONL = OUT_DIR / "responses.jsonl"

# Load existing
existing = []
if JSONL.exists():
    with JSONL.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                existing.append(json.loads(line))

# Build {model: {probe: row}} from latest pass
by_model: dict[str, dict[str, dict]] = {}
for r in existing:
    by_model.setdefault(r["model"], {})[r["probe"]] = r

# Retry plan: any (model, probe) where row missing or pass != True
retry_targets = []
for model in base.MODELS:
    for probe in base.PROBES:
        existing_row = by_model.get(model, {}).get(probe["id"])
        needs = existing_row is None or not existing_row.get("pass")
        if needs:
            retry_targets.append((model, probe))

print(f"Retry plan: {len(retry_targets)} (model, probe) cells\n")
for m, p in retry_targets:
    print(f"  - {m} :: {p['id']}")
print()

# Fire
new_rows = []
with JSONL.open("a", encoding="utf-8") as fh:
    for i, (model, probe) in enumerate(retry_targets, 1):
        print(f"[{i}/{len(retry_targets)}] {model} :: {probe['id']}", end=" ", flush=True)
        resp = base.call(model, probe["system"], probe["user"])
        row = {"model": model, "probe": probe["id"], "wall_s": resp.get("_wall_s"), "_retry": True}
        if "_error" in resp:
            row["error"] = resp["_error"]
            row["pass"] = False
            print(f"ERR {resp['_error'][:80]}")
        elif "choices" not in resp or not resp["choices"]:
            row["error"] = f"no_choices: {json.dumps(resp)[:300]}"
            row["pass"] = False
            print(f"ERR no choices")
        else:
            content = resp["choices"][0].get("message", {}).get("content") or ""
            usage = resp.get("usage") or {}
            row["usage_in"] = usage.get("prompt_tokens", 0)
            row["usage_out"] = usage.get("completion_tokens", 0)
            pl, parse_err = base.parse_playlist(content)
            if parse_err:
                row["parse_error"] = parse_err
                row["content_head"] = content[:200]
                row["pass"] = False
                print(f"PARSE-FAIL {parse_err}")
            else:
                s = base.score(probe["id"], pl)
                row.update(s)
                print(f"{'PASS' if s['pass'] else 'FAIL'} (n={s['count']})")
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        new_rows.append(row)
        time.sleep(3)

# Merge: prefer the latest pass per (model, probe). Read jsonl fresh.
by_model2: dict[str, dict[str, dict]] = {}
with JSONL.open(encoding="utf-8") as fh:
    for line in fh:
        if not line.strip():
            continue
        r = json.loads(line)
        cur = by_model2.setdefault(r["model"], {}).get(r["probe"])
        # keep the row with pass=True if any; otherwise keep latest
        if cur is None or (r.get("pass") and not cur.get("pass")):
            by_model2[r["model"]][r["probe"]] = r
        elif cur.get("pass"):
            pass
        else:
            by_model2[r["model"]][r["probe"]] = r

# Rebuild summary
lines = [
    "# OpenRouter free-tier smoke screen — results (with retry)",
    "",
    "Date: 2026-05-14 (retry session)",
    "",
    f"Models: {len(base.MODELS)}. Probes: {len(base.PROBES)}.",
    "",
    "Cost: $0 (free tier).",
    "",
    "## Probe pass matrix (best result per cell across retries)",
    "",
    "| Model | p1 cold | p2 refuse | p3 must/avoid | p4 grounding | p5 scale | Pass rate |",
    "|---|:-:|:-:|:-:|:-:|:-:|---:|",
]
for m in base.MODELS:
    cells = []
    passes = 0
    total = 0
    for p in base.PROBES:
        r = by_model2.get(m, {}).get(p["id"])
        if r is None:
            cells.append("—")
            continue
        total += 1
        if r.get("error"):
            cells.append("ERR")
        elif r.get("parse_error"):
            cells.append("PARSE")
        elif r.get("pass"):
            cells.append("✅")
            passes += 1
        else:
            cells.append("❌")
    rate = f"{passes}/{total}" if total else "—"
    lines.append(f"| `{m}` | " + " | ".join(cells) + f" | **{rate}** |")

lines += [
    "",
    "## Token + wall per model (mean across PASSED probes)",
    "",
    "| Model | passes | mean tokens out | mean wall s |",
    "|---|---:|---:|---:|",
]
for m in base.MODELS:
    rs = [by_model2.get(m, {}).get(p["id"]) for p in base.PROBES]
    passed = [r for r in rs if r and r.get("pass")]
    out_tokens = [r["usage_out"] for r in passed if r.get("usage_out") is not None]
    walls = [r["wall_s"] for r in passed if r.get("wall_s") is not None]
    if out_tokens:
        lines.append(
            f"| `{m}` | {len(passed)} | {sum(out_tokens)//len(out_tokens)} | {sum(walls)/len(walls):.1f} |"
        )
    else:
        lines.append(f"| `{m}` | 0 | — | — |")

(OUT_DIR / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nWrote {OUT_DIR / 'SUMMARY.md'}")
