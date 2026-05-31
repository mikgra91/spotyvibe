"""Production-realistic quality metric for the AI-tags overlay.

The naive verifier computes IDF over only the 31 cluster artists, which
over-weights generic mood tags and understates quality. In production
IDF is GLOBAL (over the whole enriched corpus). This script reproduces
the production scenario and reports the design that was proven best on
the 2000-run:

    similarity = IDF-weighted cosine, IDF over the FULL enriched pool,
    tag source = base ∪ AI-discriminative (genre/scene/vocal only;
    mood/rhythm/era/instrumentation dropped from the similarity space).

Outputs MAP, peer-vs-wrong margin, and nearest-neighbour hit on the
known seed clusters — comparable across scale-ups.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_overlay as V  # noqa: E402
from vocabulary import (MOOD_CHARACTER, RHYTHM_STRUCTURE, ERA,  # noqa: E402
                        INSTRUMENTATION_PRODUCTION)

GENERIC = (set(MOOD_CHARACTER) | set(RHYTHM_STRUCTURE) | set(ERA)
           | set(INSTRUMENTATION_PRODUCTION))


def run():
    overlay, entries, ai, base = V.load()
    global_idf = V.build_idf([e["ai_tags"] for e in entries.values()
                              if e.get("ai_tags")])
    names = [k for k in V.CLUSTERS]
    present = [n for n in names if V._norm(n) in ai]

    def ts(src, name):
        nn = V._norm(name)
        b, a = base.get(nn, []), ai.get(nn, [])
        ad = [t for t in a if t not in GENERIC]
        return {"baseline": b, "ai": a, "union": list(set(b) | set(a)),
                "ai_disc": ad, "union_disc": list(set(b) | set(ad))}[src]

    seeds = [s for s in V.SEED_TO_PEER if V._norm(s) in ai]
    pool = [n for n in present if not V.CLUSTERS_N[V._norm(n)].startswith("SEED")]

    print(f"  pool enriched = {sum(1 for e in entries.values() if e.get('ai_tags'))}"
          f" | cluster artists present = {len(present)}/{len(names)}")
    print(f"  {'source':12s} {'MAP':>6s} {'margin':>8s} {'NN':>5s}")
    for src in ["baseline", "ai", "union", "ai_disc", "union_disc"]:
        idf = (V.build_idf([ts(src, n) for n in present])
               if src == "baseline" else global_idf)
        aps, margins, nn = [], [], 0
        for s in seeds:
            st = ts(src, s)
            pl = V.SEED_TO_PEER[s]
            peers = [n for n in pool if V.CLUSTERS_N[V._norm(n)] == pl]
            wrong = [n for n in pool if V.CLUSTERS_N[V._norm(n)] == "WRONG"]
            rel = set(peers)
            ps = sum(V.wcos(st, ts(src, p), idf) for p in peers) / max(1, len(peers))
            ws = sum(V.wcos(st, ts(src, w), idf) for w in wrong) / max(1, len(wrong))
            margins.append(ps - ws)
            rk = sorted(pool, key=lambda n: V.wcos(st, ts(src, n), idf), reverse=True)
            aps.append(V.avg_prec(rk, rel))
            nn += 1 if rk and rk[0] in rel else 0
        ns = len(seeds)
        star = "  <-- production design" if src == "union_disc" else ""
        print(f"  {src:12s} {sum(aps)/ns:6.3f} {sum(margins)/ns:+8.3f} "
              f"{nn}/{ns}{star}")


if __name__ == "__main__":
    print("GLOBAL-IDF production metric")
    run()
