"""Quantitative verification of the enrichment bake-off.

The whole point of enrichment is to make tag-overlap similarity put an
artist's TRUE peers closer than unrelated bands. This script measures
exactly that, three ways, for baseline tags vs each model's enriched
tags:

1. Separation margin — mean similarity(seed -> its true peers) minus
   mean similarity(seed -> the bands the live system WRONGLY suggested).
   Positive and large = enrichment works.

2. Retrieval MAP — treat each seed as a query, rank all other artists
   by similarity, score average precision where "relevant" = same
   ground-truth cluster. Higher = peers rank above noise.

3. Cross-cluster leakage — does a seed's #1 nearest neighbour belong to
   its own cluster?

Similarity = Jaccard on the tag sets (the cheapest thing the retrieval
layer could do; if it works here it works in prod).
"""

import json
from pathlib import Path
from itertools import combinations

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "enrichment_results.json").read_text(encoding="utf-8"))

CLUSTERS = DATA["clusters"]
BASELINE = DATA["baseline_tags"]
RESULTS = DATA["results"]
MODELS = DATA["models"]

SEEDS = [n for n, c in CLUSTERS.items() if c.startswith("SEED_")]
# Map each seed to the peer-cluster label that marks its true peers.
SEED_TO_PEERCLUSTER = {
    "Bear Ghost": "peer_bearghost",
    "Origami Angel": "peer_origami",
    "Mrs. GREEN APPLE": "peer_mga",
}
WRONG = [n for n, c in CLUSTERS.items() if c == "WRONG_suggested"]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def tagset_for(source, name):
    if source == "baseline":
        return BASELINE.get(name, [])
    return RESULTS[source].get(name, {}).get("tags", [])


def separation(source):
    """Mean peer-sim minus mean wrong-sim, averaged over seeds."""
    rows = []
    for seed in SEEDS:
        peers = [n for n, c in CLUSTERS.items()
                 if c == SEED_TO_PEERCLUSTER[seed]]
        s_tags = tagset_for(source, seed)
        peer_sim = sum(jaccard(s_tags, tagset_for(source, p))
                       for p in peers) / max(1, len(peers))
        wrong_sim = sum(jaccard(s_tags, tagset_for(source, w))
                        for w in WRONG) / max(1, len(WRONG))
        rows.append((seed, peer_sim, wrong_sim, peer_sim - wrong_sim))
    return rows


def average_precision(ranked, relevant):
    hits, ap = 0, 0.0
    for i, name in enumerate(ranked, 1):
        if name in relevant:
            hits += 1
            ap += hits / i
    return ap / max(1, len(relevant))


def retrieval_map(source):
    """MAP treating each seed as a query over all non-seed artists."""
    all_artists = [n for n in CLUSTERS if not CLUSTERS[n].startswith("SEED_")]
    aps = []
    nn_correct = 0
    for seed in SEEDS:
        s_tags = tagset_for(source, seed)
        relevant = {n for n in all_artists
                    if CLUSTERS[n] == SEED_TO_PEERCLUSTER[seed]}
        scored = sorted(
            all_artists,
            key=lambda n: jaccard(s_tags, tagset_for(source, n)),
            reverse=True,
        )
        aps.append(average_precision(scored, relevant))
        if scored and scored[0] in relevant:
            nn_correct += 1
    return sum(aps) / len(aps), nn_correct, len(SEEDS)


def avg_tag_count(source):
    names = [n for n in CLUSTERS]
    counts = [len(tagset_for(source, n)) for n in names]
    return sum(counts) / len(counts)


def obedience(source):
    if source == "baseline":
        return None
    oov = sum(len(RESULTS[source].get(n, {}).get("out_of_vocab_tags", []))
              for n in CLUSTERS)
    total = sum(len(RESULTS[source].get(n, {}).get("tags", [])) + 0
                for n in CLUSTERS) + oov
    return oov, total


def main():
    sources = ["baseline"] + MODELS
    print("=" * 70)
    print("METRIC 1 — SEPARATION MARGIN  (peer-sim − wrong-sim; higher=better)")
    print("=" * 70)
    for src in sources:
        rows = separation(src)
        print(f"\n{src}:")
        for seed, ps, ws, margin in rows:
            flag = "✓" if margin > 0 else "✗"
            print(f"  {flag} {seed:22s} peer={ps:.3f}  wrong={ws:.3f}  "
                  f"margin={margin:+.3f}")
        mean_margin = sum(r[3] for r in rows) / len(rows)
        print(f"  → mean margin: {mean_margin:+.3f}")

    print("\n" + "=" * 70)
    print("METRIC 2 — RETRIEVAL QUALITY  (MAP + nearest-neighbour hit)")
    print("=" * 70)
    for src in sources:
        m, nn, total = retrieval_map(src)
        print(f"  {src:14s} MAP={m:.3f}   NN-correct={nn}/{total}")

    print("\n" + "=" * 70)
    print("METRIC 3 — TAG DENSITY & VOCAB OBEDIENCE")
    print("=" * 70)
    for src in sources:
        dens = avg_tag_count(src)
        ob = obedience(src)
        ob_str = ""
        if ob:
            oov, total = ob
            ob_str = f"   out-of-vocab dropped: {oov}/{total} ({100*oov//max(1,total)}%)"
        print(f"  {src:14s} avg tags/artist={dens:.1f}{ob_str}")

    # Token usage projection
    print("\n" + "=" * 70)
    print("METRIC 4 — COST PROJECTION (per-artist tokens → full corpus)")
    print("=" * 70)
    pricing = {  # EUR per 1M tokens (OpenAI direct, pricing.json)
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-4o-mini": (0.15, 0.60),
    }
    CORPUS = 175578
    for model in MODELS:
        usages = [RESULTS[model][n].get("usage", {}) for n in CLUSTERS
                  if "usage" in RESULTS[model].get(n, {})]
        if not usages:
            continue
        n = len(usages)
        in_tok = sum(u.get("prompt_tokens", 0) for u in usages) / n
        out_tok = sum(u.get("completion_tokens", 0) for u in usages) / n
        pin, pout = pricing.get(model, (0, 0))
        # Per-artist cost (no batching — conservative ceiling).
        per_artist = (in_tok * pin + out_tok * pout) / 1_000_000
        full_unbatched = per_artist * CORPUS
        # Batched: system prompt (~the bulk of input) amortised over ~40
        # artists/call. Estimate batched input as out_tok-driven + 1/40
        # of the per-call system overhead. Approximate system prompt as
        # (in_tok - ~60 grounding tokens).
        sys_tok = max(0, in_tok - 60)
        batched_in = (60 + sys_tok / 40)
        batched_per_artist = (batched_in * pin + out_tok * pout) / 1_000_000
        full_batched = batched_per_artist * CORPUS
        print(f"\n  {model}:")
        print(f"    observed avg: {in_tok:.0f} in / {out_tok:.0f} out tokens/artist")
        print(f"    full corpus, per-artist calls : €{full_unbatched:,.2f}")
        print(f"    full corpus, batched (~40/call): €{full_batched:,.2f}")


if __name__ == "__main__":
    main()
