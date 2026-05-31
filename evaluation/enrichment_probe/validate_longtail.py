"""500-artist long-tail validation for AI tag enrichment.

The 31-artist bake-off was biased toward well-tagged artists. This
closes the gap: a STRATIFIED sample across the real corpus's tag/
popularity distribution, with emphasis on the sparse/junk-tag long
tail where (a) enrichment's value is highest and (b) hallucination
risk is highest.

Measures:
  - confidence calibration by stratum (low-confidence SHOULD rise in
    the tail — that's correct caution, not a failure)
  - vocabulary obedience
  - junk-tag reduction (baseline dirty tags -> clean controlled tags)
  - tag density lift on sparse inputs
  - real token cost -> full-corpus projection
  - a manual-eyeball dump of tail artists (input vs output) so a human
    can judge hallucination directly
"""

import configparser
import gzip
import json
import os
import random
import sys
import time
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocabulary import VOCABULARY  # noqa: E402
from run_probe import SYSTEM_PROMPT, _user_prompt  # reuse v1 prompt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORPUS = Path("C:/Users/micha/AppData/Local/spotyvibe/rag_corpus/artists.jsonl.gz")
OUT = HERE / "longtail_results.json"
MODEL = "gpt-4o-mini"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
SAMPLE_N = 500
SEED = 42

# Junk-tag heuristics: tags that are clearly not descriptive (names,
# hashtags, run-on sentences). Used to quantify baseline dirtiness.
def is_junk(tag: str) -> bool:
    t = tag.strip()
    if not t:
        return True
    if t.startswith("#"):
        return True
    if len(t) > 30:  # run-on "sentence" tags
        return True
    if len(t.split()) > 4:
        return True
    return False


def _load_key():
    cfg = configparser.ConfigParser()
    cfg.read(REPO / "evaluation" / "settings.ini")
    for sect in cfg.sections():
        if cfg.has_option(sect, "api_key"):
            k = cfg.get(sect, "api_key").strip()
            if k.startswith("sk-") and not k.startswith("sk-or-"):
                return k
    raise SystemExit("No OpenAI key found")


def stratify_sample():
    """Reservoir-sample by stratum: head / mid / tail.

    head = >=4 clean tags AND lastfm_listeners >= 50k
    tail = <=1 clean tag OR lastfm_listeners < 1k (or None)
    mid  = everything else
    """
    rng = random.Random(SEED)
    targets = {"head": 150, "mid": 200, "tail": 150}
    seen = {"head": 0, "mid": 0, "tail": 0}
    reservoir = {"head": [], "mid": [], "tail": []}

    def classify(a):
        tags = a.get("tags") or []
        clean = [t for t in tags if not is_junk(t)]
        listeners = a.get("lastfm_listeners") or 0
        if len(clean) >= 4 and listeners >= 50000:
            return "head"
        if len(clean) <= 1 or listeners < 1000:
            return "tail"
        return "mid"

    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not a.get("name"):
                continue
            strat = classify(a)
            seen[strat] += 1
            res = reservoir[strat]
            k = targets[strat]
            if len(res) < k:
                res.append(a)
            else:
                j = rng.randint(0, seen[strat] - 1)
                if j < k:
                    res[j] = a
    return reservoir


def enrich_one(key, a):
    name = a["name"]
    tags = [t for t in (a.get("tags") or []) if not is_junk(t)][:8]
    tt = [t if isinstance(t, str) else t.get("name")
          for t in (a.get("top_tracks") or [])][:6]
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": _user_prompt(name, tags, tt)}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=60)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code != 200:
                return {"error": f"{r.status_code}"}
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {"tags": [], "confidence": "parse_error"}
            vocab = set(VOCABULARY)
            in_vocab = [t for t in parsed.get("tags", []) if t in vocab]
            oov = [t for t in parsed.get("tags", []) if t not in vocab]
            return {"name": name,
                    "input_tags": tags, "input_listeners": a.get("lastfm_listeners"),
                    "tags": in_vocab, "out_of_vocab": oov,
                    "confidence": parsed.get("confidence"),
                    "usage": data.get("usage", {})}
        except requests.RequestException as e:
            if attempt == 2:
                return {"error": str(e)}
            time.sleep(1)
    return {"error": "retries_exhausted"}


def main():
    key = _load_key()
    print("Sampling corpus (stratified)…")
    strata = stratify_sample()
    for s, items in strata.items():
        print(f"  {s}: {len(items)} artists")

    results = defaultdict(dict)
    for strat, items in strata.items():
        print(f"\nEnriching {strat} ({len(items)})…")
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(enrich_one, key, a): a["name"] for a in items}
            done = 0
            for fut in as_completed(futs):
                nm = futs[fut]
                results[strat][nm] = fut.result()
                done += 1
                if done % 50 == 0:
                    print(f"    {done}/{len(items)}")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    analyze(results)


def analyze(results):
    print("\n" + "=" * 68)
    print("RESULTS")
    print("=" * 68)
    pin, pout = 0.15, 0.60  # gpt-4o-mini EUR/1M
    CORPUS_N = 175578
    all_in = all_out = n_ok = 0
    for strat in ["head", "mid", "tail"]:
        rs = results[strat]
        ok = [r for r in rs.values() if "error" not in r]
        errs = len(rs) - len(ok)
        conf = Counter(r.get("confidence") for r in ok)
        avg_tags = sum(len(r["tags"]) for r in ok) / max(1, len(ok))
        oov = sum(len(r["out_of_vocab"]) for r in ok)
        tottags = sum(len(r["tags"]) for r in ok) + oov
        # sparse-input lift: artists whose input had <=1 clean tag
        sparse = [r for r in ok if len(r["input_tags"]) <= 1]
        sparse_lift = (sum(len(r["tags"]) for r in sparse) / max(1, len(sparse)))
        for r in ok:
            u = r.get("usage", {})
            all_in += u.get("prompt_tokens", 0)
            all_out += u.get("completion_tokens", 0)
            n_ok += 1
        print(f"\n[{strat}] n={len(rs)} ok={len(ok)} err={errs}")
        print(f"  confidence: {dict(conf)}")
        print(f"  avg tags/artist: {avg_tags:.1f}   out-of-vocab: "
              f"{oov}/{tottags} ({100*oov//max(1,tottags)}%)")
        print(f"  sparse-input artists (<=1 input tag): {len(sparse)}, "
              f"avg enriched tags: {sparse_lift:.1f}")

    # Hallucination proxy: tail artists that got HIGH confidence + specific
    # scene tags despite near-zero input grounding = suspicious.
    print("\n" + "-" * 68)
    print("HALLUCINATION PROXY (tail, high-confidence, near-zero input):")
    tail = results["tail"]
    suspicious = [r for r in tail.values()
                  if "error" not in r and r.get("confidence") == "high"
                  and len(r.get("input_tags", [])) == 0]
    print(f"  {len(suspicious)} tail artists claimed HIGH confidence with "
          f"ZERO input tags (should be ~0 if calibration is good)")
    for r in suspicious[:8]:
        print(f"    ! {r['name']} (listeners={r.get('input_listeners')}): "
              f"{r['tags']}")

    # Manual eyeball: 12 random tail artists, input vs output.
    print("\n" + "-" * 68)
    print("MANUAL EYEBALL — 12 tail artists (input → enriched):")
    tail_ok = [r for r in tail.values() if "error" not in r]
    for r in random.Random(7).sample(tail_ok, min(12, len(tail_ok))):
        print(f"  {r['name']}  [{r.get('confidence')}]  "
              f"listeners={r.get('input_listeners')}")
        print(f"      in : {r['input_tags'] or '(none)'}")
        print(f"      out: {r['tags']}")

    # Cost
    print("\n" + "-" * 68)
    if n_ok:
        avg_in, avg_out = all_in / n_ok, all_out / n_ok
        sys_tok = max(0, avg_in - 60)
        batched_in = 60 + sys_tok / 40
        batched = (batched_in * pin + avg_out * pout) / 1_000_000 * CORPUS_N
        unbatched = (avg_in * pin + avg_out * pout) / 1_000_000 * CORPUS_N
        print(f"COST: avg {avg_in:.0f} in / {avg_out:.0f} out tokens/artist")
        print(f"  full corpus unbatched: €{unbatched:,.2f}")
        print(f"  full corpus batched(~40/call): €{batched:,.2f}")


if __name__ == "__main__":
    main()
