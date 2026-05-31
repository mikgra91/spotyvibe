"""A/B compare a candidate model against the existing gpt-4o-mini overlay.

Runs the *same* enrichment prompt (system + vocabulary + grounding) through
a candidate model on the artists we already analysed (the known seed
clusters), then compares the candidate's tags head-to-head with the
baseline tags already stored in ``ai_tags_overlay.json``.

Purpose: decide whether a pricier model (e.g. gpt-5.4-mini) is worth it,
or whether gpt-4o-mini is "good enough". Reports, per artist and in
aggregate: tag overlap (Jaccard), added/removed tags, confidence, OOV,
**reasoning-token overhead**, real cost/artist, and latency — writing to a
throwaway file so the production overlay is never touched.

Usage::

    python evaluation/enrichment_probe/compare_models.py --model gpt-5.4-mini
"""

import argparse
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import enrich_ai_layer as E
from vocabulary import (VOCABULARY, MOOD_CHARACTER, RHYTHM_STRUCTURE, ERA,
                        INSTRUMENTATION_PRODUCTION)

# "Generic" tags are excluded from the production similarity space (only
# genre/scene/vocal tags drive clustering — see production_metric.py).
# The discriminative-only Jaccard is the metric that actually decides
# whether two models agree on what matters for retrieval.
GENERIC = (set(MOOD_CHARACTER) | set(RHYTHM_STRUCTURE) | set(ERA)
           | set(INSTRUMENTATION_PRODUCTION))


def _disc(tags):
    return [t for t in tags if t not in GENERIC]

# Pricing (EUR / 1M tokens) from frontend/static/data/pricing.json.
# cached input assumed at 50% of standard input (project convention).
PRICING = {
    "gpt-4o-mini":  {"in": 0.15, "cached": 0.075, "out": 0.60},
    "gpt-5.4-mini": {"in": 0.75, "cached": 0.375, "out": 4.50},
    "gpt-5.4":      {"in": 2.50, "cached": 1.25,  "out": 15.0},
}
VOCAB = set(VOCABULARY)


def _jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa or sb) else 1.0


def _build_body(model, a, *, temperature=None, response_format=True):
    name, tags, tt = E._grounding(a)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": E.SYSTEM_PROMPT},
            {"role": "user", "content": E._user_prompt(name, tags, tt)},
        ],
    }
    if temperature is not None:
        body["temperature"] = temperature
    if response_format:
        body["response_format"] = {"type": "json_object"}
    return body


def _post(key, body):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(E.OPENAI_URL, headers=headers, json=body, timeout=120)
    return r, time.time() - t0


def detect_params(key, model, sample):
    """Find a request-parameter combo the model accepts. Returns
    (temperature, response_format, note) or raises SystemExit with the error."""
    combos = [
        (0.2, True, "temp=0.2 + json_object (same as production)"),
        (1.0, True, "temp=1.0 + json_object"),
        (None, True, "default temp + json_object"),
        (None, False, "default temp, no response_format"),
    ]
    last = ""
    for temp, rf, note in combos:
        r, _ = _post(key, _build_body(model, sample, temperature=temp, response_format=rf))
        if r.status_code == 200:
            return temp, rf, note
        last = f"{r.status_code}: {r.text[:300]}"
        # 400 usually means a param is unsupported — try the next combo.
        if r.status_code not in (400, 422):
            break
    raise SystemExit(f"Model {model!r} rejected every parameter combo. Last error:\n{last}")


def call_compare(key, model, a, temperature, response_format):
    name, tags, tt = E._grounding(a)
    r, latency = _post(key, _build_body(model, a, temperature=temperature,
                                        response_format=response_format))
    if r.status_code != 200:
        return {"name": name, "error": f"{r.status_code}: {r.text[:150]}"}
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"tags": [], "confidence": "parse_error"}
    tags_out = parsed.get("tags", [])
    usage = data.get("usage", {})
    return {
        "name": name,
        "tags": [t for t in tags_out if t in VOCAB],
        "oov": [t for t in tags_out if t not in VOCAB],
        "confidence": parsed.get("confidence"),
        "latency": latency,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
    }


def cost_per_artist(model, prompt, cached, completion):
    p = PRICING.get(model)
    if not p:
        return None
    uncached = max(0, prompt - cached)
    return (uncached * p["in"] + cached * p["cached"] + completion * p["out"]) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.4-mini")
    ap.add_argument("--overlay", type=Path, default=E.DEFAULT_OUT)
    ap.add_argument("--corpus", type=Path, default=E.DEFAULT_CORPUS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max", type=int, default=0, help="cap artist count (0 = all clusters)")
    args = ap.parse_args()

    key = E._load_key()
    overlay = json.loads(args.overlay.read_text(encoding="utf-8"))
    baseline_model = overlay.get("model", "gpt-4o-mini")
    entries = overlay["entries"]

    # Index the corpus by mbid for grounding lookups.
    import gzip
    corpus = {}
    with gzip.open(args.corpus, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            if a.get("mbid"):
                corpus[a["mbid"]] = a

    # Pick the artists we already analysed: known clusters present in BOTH
    # the baseline overlay and the corpus.
    known = {E._norm(x) for x in E.KNOWN_CLUSTER_NAMES}
    picks = []
    for mbid, e in entries.items():
        if E._norm(e.get("name", "")) in known and mbid in corpus:
            picks.append((mbid, e))
    picks.sort(key=lambda x: x[1].get("name", ""))
    if args.max:
        picks = picks[: args.max]
    if not picks:
        raise SystemExit("No overlapping cluster artists found in overlay+corpus.")

    print(f"Baseline model : {baseline_model}")
    print(f"Candidate model: {args.model}")
    print(f"Comparison set : {len(picks)} artists we already analysed\n")

    # Detect a working parameter combo on the first artist.
    temp, rf, note = detect_params(key, args.model, corpus[picks[0][0]])
    print(f"Param combo accepted by {args.model}: {note}\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(call_compare, key, args.model, corpus[mbid], temp, rf): (mbid, e)
                for mbid, e in picks}
        for fut in as_completed(futs):
            mbid, e = futs[fut]
            res = fut.result()
            res["baseline_tags"] = e.get("ai_tags", [])
            res["baseline_conf"] = e.get("ai_confidence")
            results.append(res)

    results.sort(key=lambda r: r.get("name", ""))
    print("=" * 100)
    jac_sum = jacd_sum = n_ok = 0
    tot_prompt = tot_cached = tot_completion = tot_reason = tot_latency = 0
    for r in results:
        if "error" in r:
            print(f"\n[X] {r['name']}: {r['error']}")
            continue
        n_ok += 1
        base, cand = r["baseline_tags"], r["tags"]
        j = _jaccard(base, cand)
        jd = _jaccard(_disc(base), _disc(cand))
        jac_sum += j
        jacd_sum += jd
        shared = sorted(set(base) & set(cand))
        only_base = sorted(set(base) - set(cand))
        only_cand = sorted(set(cand) - set(base))
        tot_prompt += r["prompt_tokens"]; tot_cached += r["cached_tokens"]
        tot_completion += r["completion_tokens"]; tot_reason += r["reasoning_tokens"]
        tot_latency += r["latency"]
        print(f"\n* {r['name']}   Jaccard all={j:.2f} disc={jd:.2f}   "
              f"conf {r['baseline_conf']}->{r['confidence']}   "
              f"reasoning_tok={r['reasoning_tokens']}  ({r['latency']:.1f}s)")
        print(f"   shared      : {shared}")
        print(f"   only {baseline_model[:8]} : {only_base}")
        print(f"   only {args.model[:10]}: {only_cand}")
        if r["oov"]:
            print(f"   OOV (cand)  : {r['oov']}")

    print("\n" + "=" * 100)
    if n_ok:
        cand_cost = cost_per_artist(args.model, tot_prompt / n_ok,
                                    tot_cached / n_ok, tot_completion / n_ok)
        base_cost = 0.000143  # measured gpt-4o-mini €/artist
        print(f"AGGREGATE over {n_ok} artists:")
        print(f"  mean tag Jaccard ALL tags          : {jac_sum/n_ok:.3f}")
        print(f"  mean tag Jaccard DISCRIMINATIVE only: {jacd_sum/n_ok:.3f}  "
              f"<-- the tags that drive clustering")
        print(f"  mean tokens/artist: prompt={tot_prompt/n_ok:.0f} "
              f"(cached {tot_cached/n_ok:.0f}), completion={tot_completion/n_ok:.0f} "
              f"(reasoning {tot_reason/n_ok:.0f})")
        print(f"  mean latency/call: {tot_latency/n_ok:.1f}s  "
              f"(→ ~{args.workers/(tot_latency/n_ok):.1f} artists/s at {args.workers} workers)")
        if cand_cost:
            rate = tot_latency / n_ok
            thru = args.workers / rate if rate else 0
            print(f"\n  COST  {args.model}: €{cand_cost:.6f}/artist  "
                  f"(vs gpt-4o-mini €{base_cost:.6f} = {cand_cost/base_cost:.1f}×)")
            for label, n in [("50k", 50_000), ("full", 176_560)]:
                print(f"    {label:>5}: €{cand_cost*n:6.2f}  "
                      f"(gpt-4o-mini €{base_cost*n:.2f})"
                      + (f"   ~{n/thru/3600:.1f}h @ {args.workers}w" if thru else ""))

        out = args.overlay.parent / f"compare_{args.model.replace('/', '_')}_results.json"
        out.write_text(json.dumps({
            "baseline_model": baseline_model, "candidate_model": args.model,
            "n": n_ok, "mean_jaccard_all": jac_sum / n_ok,
            "mean_jaccard_disc": jacd_sum / n_ok,
            "candidate_cost_per_artist": cand_cost,
            "results": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Saved per-artist detail → {out.name}")


if __name__ == "__main__":
    main()
