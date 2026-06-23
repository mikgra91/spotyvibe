"""Decisive follow-up: does IDF-weighted similarity rescue enrichment?

The plain-Jaccard verifier showed enrichment REGRESSING retrieval MAP.
Hypothesis: generic mood tags (energetic, catchy, guitar-driven) that
every rock band shares dilute the rare discriminative scene tags
(swancore, midwest emo, j-rock). IDF weighting down-weights common tags
and up-weights rare ones — the standard fix. If enrichment beats
baseline under IDF, the enrichment DATA is good and prod just needs
weighted similarity.

We compute IDF over the test-set tag corpus (per source) and score
similarity as weighted-overlap cosine.
"""

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "enrichment_results.json").read_text(encoding="utf-8"))
CLUSTERS = DATA["clusters"]
BASELINE = DATA["baseline_tags"]
RESULTS = DATA["results"]
MODELS = DATA["models"]

SEEDS = [n for n, c in CLUSTERS.items() if c.startswith("SEED_")]
SEED_TO_PEERCLUSTER = {
    "Bear Ghost": "peer_bearghost",
    "Origami Angel": "peer_origami",
    "Mrs. GREEN APPLE": "peer_mga",
}
WRONG = [n for n, c in CLUSTERS.items() if c == "WRONG_suggested"]
ALL = [n for n in CLUSTERS if not CLUSTERS[n].startswith("SEED_")]


def tagset_for(source, name):
    if source == "baseline":
        return BASELINE.get(name, [])
    return RESULTS[source].get(name, {}).get("tags", [])


def build_idf(source):
    names = list(CLUSTERS)
    N = len(names)
    df = {}
    for n in names:
        for t in set(tagset_for(source, n)):
            df[t] = df.get(t, 0) + 1
    # Smoothed IDF.
    return {t: math.log((N + 1) / (d + 0.5)) for t, d in df.items()}


def wcos(a, b, idf):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    num = sum(idf.get(t, 0) ** 2 for t in (sa & sb))
    na = math.sqrt(sum(idf.get(t, 0) ** 2 for t in sa))
    nb = math.sqrt(sum(idf.get(t, 0) ** 2 for t in sb))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


def average_precision(ranked, relevant):
    hits, ap = 0, 0.0
    for i, name in enumerate(ranked, 1):
        if name in relevant:
            hits += 1
            ap += hits / i
    return ap / max(1, len(relevant))


def evaluate(source):
    idf = build_idf(source)
    aps, margins, nn = [], [], 0
    for seed in SEEDS:
        s = tagset_for(source, seed)
        relevant = {n for n in ALL
                    if CLUSTERS[n] == SEED_TO_PEERCLUSTER[seed]}
        peers = list(relevant)
        peer_sim = sum(wcos(s, tagset_for(source, p), idf)
                       for p in peers) / max(1, len(peers))
        wrong_sim = sum(wcos(s, tagset_for(source, w), idf)
                        for w in WRONG) / max(1, len(WRONG))
        margins.append(peer_sim - wrong_sim)
        ranked = sorted(ALL, key=lambda n: wcos(s, tagset_for(source, n), idf),
                        reverse=True)
        aps.append(average_precision(ranked, relevant))
        if ranked and ranked[0] in relevant:
            nn += 1
    return sum(aps) / len(aps), sum(margins) / len(margins), nn


def main():
    print("IDF-WEIGHTED SIMILARITY  (rare scene tags up-weighted)")
    print("=" * 60)
    print(f"{'source':14s}  {'MAP':>6s}  {'mean-margin':>11s}  {'NN':>4s}")
    print("-" * 60)
    for src in ["baseline"] + MODELS:
        m, margin, nn = evaluate(src)
        print(f"{src:14s}  {m:6.3f}  {margin:+11.3f}  {nn}/3")

    # Per-seed nearest-neighbour ranking for the winning model, to eyeball.
    print("\nNearest neighbours under IDF (gpt-4o-mini):")
    src = "gpt-4o-mini"
    idf = build_idf(src)
    for seed in SEEDS:
        s = tagset_for(src, seed)
        ranked = sorted(
            [n for n in ALL],
            key=lambda n: wcos(s, tagset_for(src, n), idf), reverse=True)
        top5 = [(n, CLUSTERS[n], round(wcos(s, tagset_for(src, n), idf), 2))
                for n in ranked[:6]]
        print(f"\n  {seed} (wants {SEED_TO_PEERCLUSTER[seed]}):")
        for n, c, sim in top5:
            mark = "✓" if c == SEED_TO_PEERCLUSTER[seed] else (
                "✗WRONG" if c == "WRONG_suggested" else "·")
            print(f"     {mark:6s} {sim:.2f}  {n}  [{c}]")


if __name__ == "__main__":
    main()
