"""Corpus-wide cluster-connectivity metric for the AI-tags overlay.

The known-cluster similarity test proves QUALITY on 31 labelled artists.
This proves COVERAGE/SCALING: as the enriched pool grows, do the AI tags
form a denser, more coherent similarity graph? That is the whole point
of enriching more artists — a seed can only find good neighbours if its
neighbours are also enriched with consistent tags.

Metrics (all on the enriched pool, IDF-weighted cosine on AI tags):
  - connectivity: % of artists with >=1 neighbour above a similarity
    threshold (an isolated artist is useless for similarity retrieval).
  - mean top-1 / top-5 neighbour similarity.
  - reciprocity: % of artists whose nearest neighbour also ranks them in
    its top-5 (a sign of genuine mutual clusters, not hubs).

Run after each scale-up; rising connectivity ⇒ scaling helps.
"""

import json
import math
import random
import sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OVERLAY = HERE / "ai_tags_overlay.json"
SIM_THRESHOLD = 0.30   # "has a usable neighbour" bar
SAMPLE_FOR_PAIRS = 1200  # cap O(n^2) — sample artists for the pairwise scan


def build_idf(tagsets):
    N = len(tagsets)
    df = defaultdict(int)
    for ts in tagsets:
        for t in set(ts):
            df[t] += 1
    return {t: math.log((N + 1) / (d + 0.5)) for t, d in df.items()}


def wcos(a, b, idf):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    num = sum(idf.get(t, 0) ** 2 for t in sa & sb)
    na = math.sqrt(sum(idf.get(t, 0) ** 2 for t in sa))
    nb = math.sqrt(sum(idf.get(t, 0) ** 2 for t in sb))
    return num / (na * nb) if na and nb else 0.0


def main():
    overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    entries = [e for e in overlay["entries"].values()
               if e.get("ai_tags")]
    names = [e["name"] for e in entries]
    tags = [e["ai_tags"] for e in entries]
    idf = build_idf(tags)

    # IDF over the FULL enriched pool, but pairwise scan on a sample to
    # keep it O(sample^2). Each sampled artist is compared to ALL others.
    n = len(entries)
    rng = random.Random(7)
    idxs = list(range(n))
    sample = idxs if n <= SAMPLE_FOR_PAIRS else rng.sample(idxs, SAMPLE_FOR_PAIRS)

    has_neighbour = 0
    top1s, top5s = [], []
    nn_of = {}
    for i in sample:
        sims = []
        ti = tags[i]
        for j in idxs:
            if j == i:
                continue
            s = wcos(ti, tags[j], idf)
            if s > 0:
                sims.append((s, j))
        sims.sort(reverse=True)
        if sims:
            top1s.append(sims[0][0])
            top5 = sims[:5]
            top5s.append(sum(s for s, _ in top5) / len(top5))
            nn_of[i] = [j for _, j in sims[:5]]
            if sims[0][0] >= SIM_THRESHOLD:
                has_neighbour += 1
        else:
            top1s.append(0.0)
            top5s.append(0.0)

    # Reciprocity on the sampled set (only where both ends were sampled).
    recip = total = 0
    sample_set = set(sample)
    for i in sample:
        nn = nn_of.get(i, [])
        if not nn:
            continue
        nearest = nn[0]
        if nearest in sample_set:
            total += 1
            if i in nn_of.get(nearest, []):
                recip += 1

    k = len(sample)
    print("=" * 60)
    print(f"CLUSTER CONNECTIVITY  (enriched pool = {n} artists)")
    print("=" * 60)
    print(f"  sampled for pairwise scan : {k}")
    print(f"  has neighbour >= {SIM_THRESHOLD:.2f}    : "
          f"{has_neighbour}/{k} ({100*has_neighbour/k:.1f}%)")
    print(f"  mean top-1 neighbour sim  : {sum(top1s)/k:.3f}")
    print(f"  mean top-5 neighbour sim  : {sum(top5s)/k:.3f}")
    if total:
        print(f"  NN reciprocity            : {recip}/{total} ({100*recip/total:.1f}%)")
    # Distribution of top-1 sims
    buckets = defaultdict(int)
    for s in top1s:
        buckets[round(s * 10) / 10] += 1
    print("  top-1 sim distribution:")
    for b in sorted(buckets):
        bar = "#" * (buckets[b] * 40 // k)
        print(f"    {b:.1f} | {bar} {buckets[b]}")


if __name__ == "__main__":
    main()
