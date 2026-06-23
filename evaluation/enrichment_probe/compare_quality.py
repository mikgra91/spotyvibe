"""Decide which model is *better* (not just different) on what matters.

Reuses the 31-artist labeled cluster set (seeds + real peers + the bands
the live system wrongly returned) and the separation metric from
verify_overlay. For each model's tags it computes, per seed, how well the
seed's true peers rank above the WRONG bands (MAP, peer-vs-wrong margin,
nearest-neighbour hit). Same IDF basis for both models → a fair relative
comparison. Pure computation on the saved compare_*_results.json — no API.

A higher margin / MAP for the candidate is evidence it is genuinely
better; parity means the cheaper model is "good enough".
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_overlay as V  # noqa: E402
from vocabulary import (MOOD_CHARACTER, RHYTHM_STRUCTURE, ERA,  # noqa: E402
                        INSTRUMENTATION_PRODUCTION)

GENERIC = (set(MOOD_CHARACTER) | set(RHYTHM_STRUCTURE) | set(ERA)
           | set(INSTRUMENTATION_PRODUCTION))


def _disc(tags):
    return [t for t in tags if t not in GENERIC]


def evaluate(tags_by_norm, label):
    """Print MAP / margin / NN for one model's tag map (norm-name -> tags)."""
    present = [n for n in V.CLUSTERS if V._norm(n) in tags_by_norm]
    seeds = [s for s in V.SEED_TO_PEER if V._norm(s) in tags_by_norm]
    pool = [n for n in present if not V.CLUSTERS_N[V._norm(n)].startswith("SEED")]

    for variant, pick in [("all-AI", lambda t: t),
                          ("AI-discriminative", _disc)]:
        def ts(name):
            return pick(tags_by_norm.get(V._norm(name), []))
        idf = V.build_idf([ts(n) for n in present])
        aps, margins, nn = [], [], 0
        for s in seeds:
            st = ts(s)
            pl = V.SEED_TO_PEER[s]
            peers = [n for n in pool if V.CLUSTERS_N[V._norm(n)] == pl]
            wrong = [n for n in pool if V.CLUSTERS_N[V._norm(n)] == "WRONG"]
            rel = set(peers)
            ps = sum(V.wcos(st, ts(p), idf) for p in peers) / max(1, len(peers))
            ws = sum(V.wcos(st, ts(w), idf) for w in wrong) / max(1, len(wrong))
            margins.append(ps - ws)
            rk = sorted(pool, key=lambda n: V.wcos(st, ts(n), idf), reverse=True)
            aps.append(V.avg_prec(rk, rel))
            nn += 1 if rk and rk[0] in rel else 0
        ns = max(1, len(seeds))
        print(f"  {label:12s} [{variant:18s}]  MAP={sum(aps)/ns:.3f}  "
              f"margin={sum(margins)/ns:+.3f}  NN={nn}/{len(seeds)}")


def main():
    res = json.loads((HERE / "compare_gpt-5.4-mini_results.json").read_text(encoding="utf-8"))
    base = {V._norm(r["name"]): r["baseline_tags"] for r in res["results"] if "error" not in r}
    cand = {V._norm(r["name"]): r["tags"] for r in res["results"] if "error" not in r}
    print(f"Labeled cluster artists present: {len(base)}  "
          f"(seeds={sum(1 for n in base if V.CLUSTERS_N.get(n,'').startswith('SEED'))})")
    print("Higher MAP / margin = better peer-vs-wrong separation.\n")
    evaluate(base, res["baseline_model"])
    evaluate(cand, res["candidate_model"])


if __name__ == "__main__":
    main()
