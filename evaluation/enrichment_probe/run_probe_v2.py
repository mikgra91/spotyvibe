"""Refined enrichment prompt — discriminative-tag focus.

v1 let the model add many generic mood tags (energetic, catchy,
guitar-driven) that every rock band shares, which diluted Jaccard
similarity. v2 instructs the model to lead with the rarest, most
scene-specific tags it is confident about and to cap generic mood/
production tags. Goal: win on BOTH plain-Jaccard MAP and IDF margin,
removing the metric fragility.

Runs gpt-4o-mini only (the v1 quality leader). Appends results to the
existing enrichment_results.json under model key 'gpt-4o-mini-v2'.
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
RESULTS_FILE = HERE / "enrichment_results.json"
MODEL = "gpt-4o-mini"
MODEL_KEY = "gpt-4o-mini-v2"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Scene/genre/vocal terms are the discriminators; mood/production/era are
# the "common" terms to cap.
from vocabulary import (GENRE_SCENE, VOCAL_STYLE, MOOD_CHARACTER,  # noqa: E402
                        INSTRUMENTATION_PRODUCTION, RHYTHM_STRUCTURE, ERA)
DISCRIMINATIVE = set(GENRE_SCENE) | set(VOCAL_STYLE)


def _load_key():
    cfg = configparser.ConfigParser()
    cfg.read(REPO / "evaluation" / "settings.ini")
    for sect in cfg.sections():
        if cfg.has_option(sect, "api_key"):
            k = cfg.get(sect, "api_key").strip()
            if k.startswith("sk-") and not k.startswith("sk-or-"):
                return k
    raise SystemExit("No OpenAI key found")


SYSTEM_PROMPT = (
    "You are a precise music taxonomist. Assign tags from a fixed "
    "controlled vocabulary so that two artists from the SAME scene share "
    "many tags and artists from DIFFERENT scenes share few.\n\n"
    "Rules:\n"
    "1. LEAD with the most specific genre/scene and vocal-style tags you "
    "are confident about — these are what make two similar artists match "
    "(e.g. 'midwest emo', 'swancore', 'j-rock', 'art punk', "
    "'vocal harmonies', 'gang vocals'). Include EVERY specific scene tag "
    "that genuinely applies.\n"
    "2. Add AT MOST 3 general mood/production/era tags (e.g. energetic, "
    "catchy, modern production). Do not pad with generic descriptors — "
    "they make unrelated bands look similar.\n"
    "3. Target 5-10 tags total. Specificity over quantity.\n"
    "4. Use ONLY vocabulary terms. Ground in the existing tags + top "
    "tracks. If you don't know the artist, infer conservatively and set "
    "confidence 'low'.\n"
    "5. Output STRICT JSON: {\"tags\": [...], \"confidence\": "
    "\"high|medium|low\"}.\n\n"
    "CONTROLLED_VOCABULARY:\n" + ", ".join(VOCABULARY)
)


def _user_prompt(name, tags, top_tracks):
    return (f"Artist: {name}\n"
            f"Existing tags: {', '.join(tags) if tags else '(none)'}\n"
            f"Top tracks: {', '.join(top_tracks) if top_tracks else '(none)'}\n\n"
            "Return the JSON object now.")


def enrich_one(key, name, rec):
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": _user_prompt(
                             name, rec["tags"], rec["top_tracks"])}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=60)
    dt = time.time() - t0
    if r.status_code != 200:
        return {"error": f"{r.status_code}: {r.text[:200]}"}
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"tags": []}
    vocab = set(VOCABULARY)
    in_vocab = [t for t in parsed.get("tags", []) if t in vocab]
    oov = [t for t in parsed.get("tags", []) if t not in vocab]
    n_generic = sum(1 for t in in_vocab if t not in DISCRIMINATIVE)
    return {"tags": in_vocab, "out_of_vocab_tags": oov,
            "confidence": parsed.get("confidence"),
            "n_discriminative": len(in_vocab) - n_generic,
            "n_generic": n_generic,
            "usage": data.get("usage", {}), "latency_s": round(dt, 2)}


def main():
    key = _load_key()
    testset = json.loads(TESTSET.read_text(encoding="utf-8"))
    out = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(enrich_one, key, n, rec): n
                for n, rec in testset.items()}
        for fut in as_completed(futs):
            n = futs[fut]
            out[n] = fut.result()
            r = out[n]
            if "error" in r:
                print(f"  ! {n}: {r['error']}")
            else:
                print(f"  {n} [{r.get('confidence')}] "
                      f"(disc={r['n_discriminative']},gen={r['n_generic']}): "
                      f"{r['tags']}")

    payload = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    payload["results"][MODEL_KEY] = out
    if MODEL_KEY not in payload["models"]:
        payload["models"].append(MODEL_KEY)
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\nAppended {MODEL_KEY} to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
