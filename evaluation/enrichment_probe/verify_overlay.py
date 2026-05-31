"""Verify the AI-tags overlay produced by enrich_ai_layer.py.

Reports, over the whole 2000-artist control group:
  1. OOV rate + tag density + confidence calibration (vs the rock-centric
     v1 baseline of 18-37% OOV).
  2. Real cost — accounting for OpenAI prompt caching (the vocabulary
     system prompt is cached at 50%), projected to the full corpus.
  3. Decisive quality: similarity separation on the known seed clusters
     (baseline corpus tags vs AI tags, plain Jaccard + IDF) — does the
     AI overlay rank a seed's true peers above the bands the live system
     wrongly suggested?
"""

import gzip
import json
import math
import sys
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from vocabulary import VOCABULARY  # noqa: E402

OVERLAY = HERE / "ai_tags_overlay.json"
CORPUS = Path("C:/Users/micha/AppData/Local/spotyvibe/rag_corpus/artists.jsonl.gz")

# Ground-truth clusters for the similarity metric (same as the 31-artist
# bake-off), matched by normalised name.
CLUSTERS = {
    "bear ghost": "SEED_bearghost",
    "good kid": "peer_bearghost", "i fight dragons": "peer_bearghost",
    "tub ring": "peer_bearghost", "dance gavin dance": "peer_bearghost",
    "hail the sun": "peer_bearghost", "the dear hunter": "peer_bearghost",
    "tally hall": "peer_bearghost",
    "origami angel": "SEED_origami",
    "mom jeans.": "peer_origami", "oso oso": "peer_origami",
    "tiny moving parts": "peer_origami", "hot mulligan": "peer_origami",
    "prince daddy & the hyena": "peer_origami", "macseal": "peer_origami",
    "michael cera palin": "peer_origami", "ben quad": "peer_origami",
    "mrs. green apple": "SEED_mga",
    "king gnu": "peer_mga", "vaundy": "peer_mga", "sumika": "peer_mga",
    "kana-boon": "peer_mga", "unison square garden": "peer_mga",
    "thornley": "WRONG", "hundred reasons": "WRONG", "vex red": "WRONG",
    "thriving ivory": "WRONG", "dolu kadehi ters tut": "WRONG",
    "tantric": "WRONG", "collapsis": "WRONG", "king hüsky": "WRONG",
}
SEED_TO_PEER = {"Bear Ghost": "peer_bearghost", "Origami Angel": "peer_origami",
                "Mrs. GREEN APPLE": "peer_mga"}


def _norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


# Normalised cluster lookup so name-matching is robust to spacing/case.
CLUSTERS_N = {_norm(k): v for k, v in CLUSTERS.items()}


def is_junk(t):
    t = (t or "").strip()
    return (not t) or t.startswith("#") or len(t) > 30 or len(t.split()) > 4


def load():
    overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    entries = overlay["entries"]
    # name -> ai_tags  and  name -> baseline tags (for the cluster set)
    ai_by_name, base_by_name = {}, {}
    wanted = set(CLUSTERS)
    # Pull baseline tags for the cluster artists from the corpus.
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            nm = _norm(a.get("name", ""))
            if nm in {_norm(x) for x in wanted}:
                base_by_name[nm] = [t for t in (a.get("tags") or [])
                                    if not is_junk(t)]
    for v in entries.values():
        ai_by_name[_norm(v.get("name", ""))] = v.get("ai_tags", [])
    return overlay, entries, ai_by_name, base_by_name


# ── similarity ──────────────────────────────────────────────────────
def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


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


def avg_prec(ranked, rel):
    hits = ap = 0
    for i, n in enumerate(ranked, 1):
        if n in rel:
            hits += 1
            ap += hits / i
    return ap / max(1, len(rel))


def similarity_report(ai_by_name, base_by_name):
    names = list(CLUSTERS)
    present = [n for n in names if _norm(n) in ai_by_name]
    print(f"\nCluster artists with AI tags: {len(present)}/{len(names)}")

    def tagset(src, name):
        nn = _norm(name)
        return (base_by_name.get(nn, []) if src == "baseline"
                else ai_by_name.get(nn, []))

    for src in ["baseline", "ai"]:
        idf = build_idf([tagset(src, n) for n in present])
        seeds = [s for s in SEED_TO_PEER if _norm(s) in ai_by_name]
        all_pool = [n for n in present if not CLUSTERS_N[_norm(n)].startswith("SEED")]
        margins_j, margins_w, aps_j, aps_w, nn_j, nn_w = [], [], [], [], 0, 0
        for s in seeds:
            st = tagset(src, s)
            peer_label = SEED_TO_PEER[s]
            peers = [n for n in all_pool if CLUSTERS_N[_norm(n)] == peer_label]
            wrong = [n for n in all_pool if CLUSTERS_N[_norm(n)] == "WRONG"]
            rel = set(peers)
            # plain
            ps = sum(jaccard(st, tagset(src, p)) for p in peers) / max(1, len(peers))
            ws = sum(jaccard(st, tagset(src, w)) for w in wrong) / max(1, len(wrong))
            margins_j.append(ps - ws)
            rk = sorted(all_pool, key=lambda n: jaccard(st, tagset(src, n)), reverse=True)
            aps_j.append(avg_prec(rk, rel))
            nn_j += 1 if rk and rk[0] in rel else 0
            # idf
            ps2 = sum(wcos(st, tagset(src, p), idf) for p in peers) / max(1, len(peers))
            ws2 = sum(wcos(st, tagset(src, w), idf) for w in wrong) / max(1, len(wrong))
            margins_w.append(ps2 - ws2)
            rk2 = sorted(all_pool, key=lambda n: wcos(st, tagset(src, n), idf), reverse=True)
            aps_w.append(avg_prec(rk2, rel))
            nn_w += 1 if rk2 and rk2[0] in rel else 0
        ns = len(seeds)
        print(f"\n  [{src}]  (seeds={ns})")
        print(f"    plain Jaccard : MAP={sum(aps_j)/ns:.3f}  margin={sum(margins_j)/ns:+.3f}  NN={nn_j}/{ns}")
        print(f"    IDF-weighted  : MAP={sum(aps_w)/ns:.3f}  margin={sum(margins_w)/ns:+.3f}  NN={nn_w}/{ns}")

    # Nearest-neighbour eyeball under IDF (AI tags)
    idf = build_idf([ai_by_name.get(_norm(n), []) for n in present])
    all_pool = [n for n in present if not CLUSTERS_N[_norm(n)].startswith("SEED")]
    print("\n  Nearest neighbours under IDF (AI tags):")
    for s in [x for x in SEED_TO_PEER if _norm(x) in ai_by_name]:
        st = ai_by_name[_norm(s)]
        rk = sorted(all_pool, key=lambda n: wcos(st, ai_by_name.get(_norm(n), []), idf),
                    reverse=True)[:6]
        print(f"    {s} (wants {SEED_TO_PEER[s]}):")
        for n in rk:
            c = CLUSTERS_N[_norm(n)]
            mark = "OK " if c == SEED_TO_PEER[s] else ("XX " if c == "WRONG" else " · ")
            print(f"       {mark} {wcos(st, ai_by_name.get(_norm(n), []), idf):.2f}  {n} [{c}]")


def main():
    overlay, entries, ai_by_name, base_by_name = load()
    ok = [e for e in entries.values() if "ai_tags" in e]
    print("=" * 66)
    print(f"OVERLAY: {len(entries)} entries | model={overlay.get('model')} "
          f"| vocab v{overlay.get('vocabulary_version')}")
    print("=" * 66)

    # OOV + density + calibration
    oov = sum(len(e.get("_oov", [])) for e in ok)
    tottags = sum(len(e.get("ai_tags", [])) for e in ok) + oov
    dens = sum(len(e.get("ai_tags", [])) for e in ok) / max(1, len(ok))
    conf = Counter(e.get("ai_confidence") for e in ok)
    print(f"  avg tags/artist : {dens:.1f}")
    print(f"  out-of-vocab    : {oov}/{tottags} ({100*oov/max(1,tottags):.1f}%)  "
          f"[v1 was 18-37%]")
    print(f"  confidence      : {dict(conf)}")
    empties = sum(1 for e in ok if not e.get("ai_tags"))
    print(f"  empty tag sets  : {empties} ({100*empties/max(1,len(ok)):.1f}%)")

    # Cost (with caching)
    pin, pin_cached, pout = 0.15, 0.075, 0.60  # EUR/1M; cached input = 50%
    tot_in = tot_cached = tot_out = n = 0
    for e in ok:
        u = e.get("_usage", {})
        if not u:
            continue
        tot_in += u.get("prompt_tokens", 0)
        tot_cached += u.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        tot_out += u.get("completion_tokens", 0)
        n += 1
    if n:
        ai_in = tot_in / n
        ai_cached = tot_cached / n
        ai_out = tot_out / n
        uncached = ai_in - ai_cached
        per_artist = (uncached * pin + ai_cached * pin_cached + ai_out * pout) / 1e6
        print(f"\n  tokens/artist   : {ai_in:.0f} in ({ai_cached:.0f} cached), {ai_out:.0f} out")
        print(f"  cost/artist     : €{per_artist*1000:.4f} per 1000... "
              f"= €{per_artist:.6f}")
        print(f"  FULL CORPUS (175,578) projection: €{per_artist*175578:.2f}")

    # Similarity (the decisive metric)
    similarity_report(ai_by_name, base_by_name)


if __name__ == "__main__":
    main()
