"""AI tag-enrichment bake-off probe.

Enriches a curated test set of artists with controlled-vocabulary tags
using OpenAI directly, recording exact token usage so we can project
the full-corpus cost. Independent of the prod config (loads the key
straight from evaluation/settings.ini, hits api.openai.com directly)
so it can't be perturbed by an OpenRouter base-url override.

Output: enrichment_results.json — per (model, artist) tags + usage.
"""

import configparser
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocabulary import VOCABULARY  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TESTSET = Path(os.environ.get("TMP", "/tmp")) / "enrich_testset.json"
OUT = HERE / "enrichment_results.json"

# Cheap OpenAI models worth comparing for a bulk tagging job.
MODELS = ["gpt-4.1-nano", "gpt-4o-mini"]

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _load_key() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(REPO / "evaluation" / "settings.ini")
    # First section with an OpenAI-style key wins.
    for sect in cfg.sections():
        if cfg.has_option(sect, "api_key"):
            k = cfg.get(sect, "api_key").strip()
            if k.startswith("sk-") and not k.startswith("sk-or-"):
                return k
    raise SystemExit("No OpenAI api_key (sk-...) found in evaluation/settings.ini")


SYSTEM_PROMPT = (
    "You are a precise music taxonomist. You assign style tags to an "
    "artist by selecting ONLY from a fixed controlled vocabulary. You "
    "never invent tags outside the list.\n\n"
    "Rules:\n"
    "1. Choose 8-15 tags from the CONTROLLED_VOCABULARY that best "
    "capture the artist's genre, scene, mood, vocal style, "
    "instrumentation and rhythm.\n"
    "2. Use the artist's existing tags and top-track titles as grounding "
    "signals.\n"
    "3. If you do not actually know the artist, infer conservatively "
    "from the grounding signals only, and set confidence to \"low\". "
    "Do NOT hallucinate specifics you cannot support.\n"
    "4. Prefer the most specific scene tag you are confident about "
    "(e.g. 'midwest emo' over just 'emo', 'swancore' over "
    "'post-hardcore') when the evidence supports it.\n"
    "5. Output STRICT JSON only: "
    "{\"tags\": [...], \"confidence\": \"high|medium|low\"}.\n\n"
    "CONTROLLED_VOCABULARY:\n" + ", ".join(VOCABULARY)
)


def _user_prompt(name, tags, top_tracks):
    return (
        f"Artist: {name}\n"
        f"Existing tags: {', '.join(tags) if tags else '(none)'}\n"
        f"Top tracks: {', '.join(top_tracks) if top_tracks else '(none)'}\n\n"
        "Return the JSON object now."
    )


def enrich_one(key, model, name, rec):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(
                name, rec["tags"], rec["top_tracks"])},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=60)
    dt = time.time() - t0
    if r.status_code != 200:
        return {"error": f"{r.status_code}: {r.text[:200]}", "latency_s": dt}
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"tags": [], "confidence": "parse_error", "raw": content[:300]}
    # Enforce vocabulary: drop any out-of-vocab tag (measures obedience).
    vocab = set(VOCABULARY)
    in_vocab = [t for t in parsed.get("tags", []) if t in vocab]
    out_of_vocab = [t for t in parsed.get("tags", []) if t not in vocab]
    return {
        "tags": in_vocab,
        "out_of_vocab_tags": out_of_vocab,
        "confidence": parsed.get("confidence"),
        "usage": usage,
        "latency_s": round(dt, 2),
    }


def main():
    key = _load_key()
    testset = json.loads(TESTSET.read_text(encoding="utf-8"))
    print(f"Test set: {len(testset)} artists × {len(MODELS)} models "
          f"= {len(testset) * len(MODELS)} calls")

    results = {m: {} for m in MODELS}
    for model in MODELS:
        print(f"\n=== {model} ===")
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {
                ex.submit(enrich_one, key, model, name, rec): name
                for name, rec in testset.items()
            }
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    results[model][name] = fut.result()
                    r = results[model][name]
                    if "error" in r:
                        print(f"  ! {name}: {r['error']}")
                    else:
                        print(f"  {name} [{r.get('confidence')}]: "
                              f"{r['tags']}")
                        if r["out_of_vocab_tags"]:
                            print(f"      (dropped out-of-vocab: "
                                  f"{r['out_of_vocab_tags']})")
                except Exception as e:
                    results[model][name] = {"error": str(e)}
                    print(f"  ! {name}: EXC {e}")

    # Attach clusters for the verifier.
    payload = {
        "models": MODELS,
        "clusters": {n: testset[n]["cluster"] for n in testset},
        "baseline_tags": {n: testset[n]["tags"] for n in testset},
        "results": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
