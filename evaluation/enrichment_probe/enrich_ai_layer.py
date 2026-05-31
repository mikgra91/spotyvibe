"""Contained AI tag-enrichment layer (overlay producer).

Implements the layered-enrichment design: the AI layer owns ONLY its own
fields, is keyed by the stable MusicBrainz ``mbid``, and is gated by a
``source_hash`` so re-running it skips entries whose grounding inputs
(name + base tags + top tracks + vocabulary + model) are unchanged. That
gives a true merge/update workflow — no rebuild, no wasted API calls,
and the base + Last.fm layers are never touched.

Output: a single overlay JSON next to (not inside) the base corpus, the
same durable pattern ``RagCorpus.load()`` already uses for
``top_tracks_overlay.json``. It survives Cloud Run base-corpus rebuilds
because the rebuild only overwrites ``artists.jsonl.gz`` + ``manifest.json``.

Overlay schema::

    {
      "schema_version": 1,
      "layer": "ai_tags",
      "model": "gpt-4o-mini",
      "vocabulary_version": "2",
      "updated_at": "<iso>",
      "entries": {
        "<mbid>": {
          "name": "...",
          "ai_tags": [...],            # controlled-vocabulary only
          "ai_confidence": "high|medium|low",
          "source_hash": "<sha256>",   # skip-if-unchanged gate
          "enriched_at": "<iso>",
          "_oov": [...]                # QA only; prod can drop
        }
      }
    }

Usage::

    python evaluation/enrichment_probe/enrich_ai_layer.py \
        --sample 2000 --out evaluation/enrichment_probe/ai_tags_overlay.json
"""

import argparse
import configparser
import datetime as dt
import gzip
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocabulary import VOCABULARY, VOCABULARY_VERSION  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_CORPUS = Path(
    "C:/Users/micha/AppData/Local/spotyvibe/rag_corpus/artists.jsonl.gz")
DEFAULT_OUT = HERE / "ai_tags_overlay.json"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
SCHEMA_VERSION = 1
CHECKPOINT_EVERY = 100

# Known-cluster artists (mbid-independent, matched by normalised name) we
# force-include in any sample so the similarity-separation metric stays
# runnable on the control group.
KNOWN_CLUSTER_NAMES = {
    "bear ghost", "origami angel", "mrs. green apple", "mrs green apple",
    "good kid", "i fight dragons", "tub ring", "dance gavin dance",
    "hail the sun", "the dear hunter", "tally hall",
    "mom jeans.", "oso oso", "tiny moving parts", "hot mulligan",
    "prince daddy & the hyena", "macseal", "michael cera palin", "ben quad",
    "king gnu", "vaundy", "sumika", "kana-boon", "unison square garden",
    "thornley", "hundred reasons", "vex red", "thriving ivory",
    "dolu kadehi ters tut", "tantric", "collapsis", "king hüsky",
}


def _norm(s: str) -> str:
    return "".join(c for c in (s or "").lower() if c.isalnum())


def is_junk(tag: str) -> bool:
    t = (tag or "").strip()
    return (not t) or t.startswith("#") or len(t) > 30 or len(t.split()) > 4


def _load_key() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(REPO / "evaluation" / "settings.ini")
    for sect in cfg.sections():
        if cfg.has_option(sect, "api_key"):
            k = cfg.get(sect, "api_key").strip()
            if k.startswith("sk-") and not k.startswith("sk-or-"):
                return k
    raise SystemExit("No OpenAI api_key (sk-...) in evaluation/settings.ini")


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grounding(a: dict):
    name = a.get("name", "")
    tags = [t for t in (a.get("tags") or []) if not is_junk(t)][:8]
    tt = [t if isinstance(t, str) else t.get("name")
          for t in (a.get("top_tracks") or [])][:6]
    return name, tags, tt


def source_hash(name, tags, top_tracks, model) -> str:
    """Stable hash of everything the AI output depends on. A change in any
    of these (incl. vocabulary or model) flips the hash → re-enrich."""
    canonical = json.dumps({
        "name": name,
        "tags": sorted(tags),
        "top_tracks": list(top_tracks),
        "vocab": VOCABULARY_VERSION,
        "model": model,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


SYSTEM_PROMPT = (
    "You are a precise music taxonomist. You assign style tags to an "
    "artist by selecting ONLY from a fixed controlled vocabulary. You "
    "never invent tags outside the list.\n\n"
    "Rules:\n"
    "1. Choose 8-15 tags from CONTROLLED_VOCABULARY that best capture the "
    "artist's genre, scene, mood, vocal style, instrumentation and "
    "rhythm.\n"
    "2. Use the artist's existing tags and top-track titles as grounding.\n"
    "3. If you do not actually know the artist, infer conservatively from "
    "the grounding only and set confidence \"low\". Do NOT hallucinate.\n"
    "4. Prefer the most specific scene tag you are confident about "
    "(e.g. 'midwest emo' over 'emo', 'melodic death metal' over 'metal').\n"
    "5. Do NOT output nationalities/languages (e.g. 'british', 'german', "
    "'american') or bare vague single words ('melodic', 'heavy', "
    "'traditional', 'composer'). Use the specific genre form ('indie "
    "rock', not 'indie'; 'alternative rock', not 'alternative').\n"
    "6. Output STRICT JSON only: "
    "{\"tags\": [...], \"confidence\": \"high|medium|low\"}.\n\n"
    "CONTROLLED_VOCABULARY:\n" + ", ".join(VOCABULARY)
)


def _user_prompt(name, tags, top_tracks):
    return (f"Artist: {name}\n"
            f"Existing tags: {', '.join(tags) if tags else '(none)'}\n"
            f"Top tracks: {', '.join(top_tracks) if top_tracks else '(none)'}\n\n"
            "Return the JSON object now.")


def enrich_one(key, model, a):
    name, tags, tt = _grounding(a)
    body = {"model": model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": _user_prompt(name, tags, tt)}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(4):
        try:
            r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=60)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code != 200:
                return {"error": f"{r.status_code}: {r.text[:150]}"}
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {"tags": [], "confidence": "parse_error"}
            vocab = set(VOCABULARY)
            in_vocab = [t for t in parsed.get("tags", []) if t in vocab]
            oov = [t for t in parsed.get("tags", []) if t not in vocab]
            return {
                "name": name,
                "ai_tags": in_vocab,
                "ai_confidence": parsed.get("confidence"),
                "source_hash": source_hash(name, tags, tt, model),
                "enriched_at": _iso_now(),
                "_oov": oov,
                "_usage": data.get("usage", {}),
            }
        except requests.RequestException as e:
            if attempt == 3:
                return {"error": str(e)}
            time.sleep(1)
    return {"error": "retries_exhausted"}


def load_overlay(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"schema_version": SCHEMA_VERSION, "layer": "ai_tags",
            "model": DEFAULT_MODEL, "vocabulary_version": VOCABULARY_VERSION,
            "updated_at": None, "entries": {}}


def write_overlay(path: Path, overlay: dict, model: str):
    overlay["updated_at"] = _iso_now()
    overlay["model"] = model
    overlay["vocabulary_version"] = VOCABULARY_VERSION
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(overlay, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)


def _stable_rank(mbid: str) -> str:
    """Deterministic per-artist sort key. Using a hash of the mbid gives a
    fixed pseudo-random ordering that is identical across runs, so taking
    the first-N is a strict SUPERSET as N grows — scaling 5k→10k re-uses
    every earlier pick and the source-hash skip-gate enriches only the
    genuinely new artists."""
    return hashlib.md5(mbid.encode("utf-8")).hexdigest()


def stratified_sample(corpus_path: Path, n: int, seed: int = 42):
    """Deterministic, superset-stable stratified sample across
    head/mid/tail, force-including the known-cluster names so the
    similarity metric stays runnable.

    Unlike reservoir sampling, this sorts each stratum by a stable hash
    and takes the first-k, so a larger n always contains every artist a
    smaller n would have picked.
    """
    targets = {"head": int(n * 0.30), "mid": int(n * 0.40)}
    targets["tail"] = n - targets["head"] - targets["mid"]
    by_strat = {"head": [], "mid": [], "tail": []}
    forced = {}
    known_norm = {_norm(x) for x in KNOWN_CLUSTER_NAMES}

    def classify(a):
        clean = [t for t in (a.get("tags") or []) if not is_junk(t)]
        listeners = a.get("lastfm_listeners") or 0
        if len(clean) >= 4 and listeners >= 50000:
            return "head"
        if len(clean) <= 1 or listeners < 1000:
            return "tail"
        return "mid"

    with gzip.open(corpus_path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            mbid = a.get("mbid")
            if not a.get("name") or not mbid:
                continue
            if _norm(a["name"]) in known_norm:
                forced[mbid] = a
            by_strat[classify(a)].append((_stable_rank(mbid), a))

    out = {}
    for strat, items in by_strat.items():
        items.sort(key=lambda x: x[0])
        for _, a in items[:targets[strat]]:
            out[a["mbid"]] = a
    out.update(forced)  # force known clusters in regardless of sampling
    return list(out.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sample", type=int, default=2000)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    key = _load_key()
    overlay = load_overlay(args.out)
    entries = overlay["entries"]
    # If the overlay was built with a different model/vocab, its hashes are
    # stale by construction; the per-entry hash check below handles that.

    print(f"Sampling {args.sample} artists from {args.corpus.name}…")
    artists = stratified_sample(args.corpus, args.sample)
    print(f"  resolved {len(artists)} unique artists "
          f"(incl. forced known clusters)")

    # Merge/skip gate: only enrich new or changed entries.
    todo = []
    skipped = 0
    for a in artists:
        name, tags, tt = _grounding(a)
        h = source_hash(name, tags, tt, args.model)
        prev = entries.get(a["mbid"])
        if prev and prev.get("source_hash") == h:
            skipped += 1
            continue
        todo.append(a)
    print(f"  skip-unchanged: {skipped}   to-enrich: {len(todo)}")

    done = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(enrich_one, key, args.model, a): a for a in todo}
        for fut in as_completed(futs):
            a = futs[fut]
            res = fut.result()
            if "error" in res:
                errors += 1
            else:
                entries[a["mbid"]] = res
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                write_overlay(args.out, overlay, args.model)
                print(f"    {done}/{len(todo)} (checkpoint, {errors} err)")

    write_overlay(args.out, overlay, args.model)
    print(f"\nWrote overlay: {args.out}")
    print(f"  total entries: {len(entries)}   enriched now: {done - errors}"
          f"   errors: {errors}")


if __name__ == "__main__":
    main()
