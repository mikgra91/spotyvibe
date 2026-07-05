"""Taste-match benchmark — the measurement instrument for recommendation quality.

Measures how well a candidate-ranking STRATEGY separates a user's real LIKED
artists from their DISLIKED artists (especially same-genre near-misses), using
the user's own profile labels as ground truth. K-fold cross-validated so the
numbers are stable (no single-split noise) and leakage-free (both positives and
negatives are held out per fold).

Why this exists
---------------
The North Star rule "measure before shipping / no quality regression" needs a
metric that captures *taste fit*. The shipped eval (cite-rate, found-on-Spotify)
does not — which is why corpus find-rate rose while quality stayed bad
(.dev-notes/corpus-diag-2026-07-05/). This is that missing metric. Wire it as a
gate: a retrieval change must not lower taste-AUC on any model.

Strategies
----------
  prose_tags          production Stage-1: build_query_tags(profile prose) →
                      TF-IDF query, cosine vs candidate tag vectors.
  anchor_tags         centroid of the TRAIN-fold positives' tag vectors, cosine.
  embed               fastembed(name + tags) centroid of TRAIN positives, cosine.
                      (local ONNX; pip install fastembed. Optional.)
  llm_rerank:<model>  the "Ground then Judge" Stage-2 prototype — an LLM scores
                      each candidate 0-100 against the TRAIN-fold exemplars
                      (loves + rejects-with-reasons). <model> defaults to the
                      app's configured model.

Metrics (mean ± std across folds)
  auc     ROC-AUC( P(love ranked above reject) ). 0.5 = coin flip.
  p_at_k  precision@k over (test loves + test rejects + distractors), k = #test
          loves — how many of the top-k are actually loved.
  rank    mean rank of held-out loves within the full distractor pool (lower=better).

Usage
-----
  python evaluation/taste_bench.py --strategies prose_tags anchor_tags embed
  python evaluation/taste_bench.py --strategies llm_rerank --models google/gemini-3.1-flash-lite anthropic/claude-sonnet-4.5
  python evaluation/taste_bench.py --profile "<path to profile.json>" --folds 5

Ground truth defaults to the user's real legacy profile
(%LOCALAPPDATA%/spotyvibe/backup/personalized_music_profile.json); override with
--profile. No network except the llm_rerank strategy. LLM responses are cached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402
from core.src.rag.corpus import RagCorpus, normalise_name, normalise_tag  # noqa: E402
from core.src.rag import retrieval  # noqa: E402

_DEFAULT_PROFILE = config._APP_DIR / "backup" / "personalized_music_profile.json"
_LLM_CACHE = REPO_ROOT / ".dev-notes" / "corpus-diag-2026-07-05" / "llm_cache"
_EMB_CACHE = REPO_ROOT / ".dev-notes" / "corpus-diag-2026-07-05" / "repro" / "emb_cache"


# ── metric ───────────────────────────────────────────────────────────────
def auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney ROC-AUC = P(random pos > random neg)."""
    n = len(pos) * len(neg)
    if not n:
        return float("nan")
    w = sum((1.0 if p > q else 0.5 if p == q else 0.0) for p in pos for q in neg)
    return w / n


def stratified_folds(items: list, k: int, seed: int) -> list[list]:
    """Return k disjoint held-out folds of *items* (shuffled, near-equal size)."""
    xs = list(items)
    random.Random(seed).shuffle(xs)
    return [xs[i::k] for i in range(k)]


# ── candidate text / tag vectors ─────────────────────────────────────────
def artist_text(a) -> str:
    tags = list(dict.fromkeys(list(a.tags) + list(a.spotify_genres) + list(a.lastfm_tags)))
    tags = [t for t in tags if t][:20]
    return f"{a.name} — a music artist. Style/genre tags: {', '.join(tags) if tags else 'unknown'}."


def tagvec(a, corpus) -> dict:
    v: dict[str, float] = {}
    for t in list(a.tags) + list(a.spotify_genres) + list(a.lastfm_tags):
        nt = normalise_tag(t)
        if nt and nt not in v:
            v[nt] = corpus.tag_idf.get(nt, 1.0)
    return v


def cos_sparse(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(x * x for x in a.values()))
    nb = math.sqrt(sum(x * x for x in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def centroid_sparse(vecs: list[dict]) -> dict:
    c: dict[str, float] = {}
    for v in vecs:
        for k, x in v.items():
            c[k] = c.get(k, 0.0) + x
    n = max(1, len(vecs))
    return {k: x / n for k, x in c.items()}


# ── embeddings (optional, local fastembed) ───────────────────────────────
_fe = None
def _embed(texts: list[str]):
    import numpy as np
    global _fe
    _EMB_CACHE.mkdir(parents=True, exist_ok=True)
    out, todo, ix = [None] * len(texts), [], []
    for i, t in enumerate(texts):
        h = hashlib.sha1(("bge\x00" + t).encode()).hexdigest()
        p = _EMB_CACHE / f"bge.{h}.npy"
        if p.exists():
            out[i] = np.load(p)
        else:
            todo.append(t); ix.append((i, p))
    if todo:
        if _fe is None:
            from fastembed import TextEmbedding
            _fe = TextEmbedding("BAAI/bge-small-en-v1.5")
        for (i, p), v in zip(ix, _fe.embed(todo)):
            v = np.asarray(v, dtype="float32"); np.save(p, v); out[i] = v
    return [np.asarray(v, dtype="float32") for v in out]


def cos_dense(a, b) -> float:
    import numpy as np
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0


# ── LLM re-ranker (the 'Ground then Judge' Stage-2 prototype) ─────────────
def llm_taste_scores(taste_desc: str, loves: list[str],
                     rejects: list[tuple[str, str]], candidates: list[str],
                     model: str) -> dict[str, float]:
    """Score each candidate 0-100 for how likely the user is to LOVE it.

    loves           artist names the user loves (train exemplars).
    rejects         (name, reason) the user rejected (train exemplars).
    candidates      artist names to score (held-out test + distractors).
    Returns {normalised_name: score}. Responses are cached on disk.

    This is the shippable core of Stage 2 — lift into core/src/ once the
    benchmark validates it. It never invents artists; it only scores the
    grounded candidates it is given.
    """
    from core.src.openai_http import chat_completions_create, extract_chat_content
    system = (
        "You are a music-taste model. Given a user's loved and rejected artists, "
        "score how likely the user is to LOVE each candidate. The user's dominant "
        "axis is melody/hook/harmony quality (melody > hook > energy > style); they "
        "reject same-genre artists they find melodically boring or dated. Return "
        "ONLY JSON {\"scores\":[{\"n\":\"<artist name>\",\"s\":<0-100>}]} for EVERY candidate."
    )
    love_block = "\n".join(f"- {a}" for a in loves)
    reject_block = "\n".join(f"- {n} (reason: {why})" for n, why in rejects)
    cand_block = "\n".join(f"{i+1}. {n}" for i, n in enumerate(candidates))
    user = (f"USER TASTE: {taste_desc}\n\nLOVES:\n{love_block}\n\n"
            f"REJECTED (with reasons):\n{reject_block}\n\n"
            f"CANDIDATES (score every one, 0=certain reject, 100=certain love):\n{cand_block}")

    _LLM_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1((model + "\x00" + system + "\x00" + user).encode()).hexdigest()
    cache = _LLM_CACHE / f"{key}.json"
    if cache.exists():
        raw = cache.read_text("utf-8")
    else:
        resp = chat_completions_create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0, response_format={"type": "json_object"})
        raw = extract_chat_content(resp)
        cache.write_text(raw, "utf-8")

    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0) if m else raw)
    items = data.get("scores") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    out: dict[str, float] = {}
    for it in items or []:
        try:
            out[normalise_name(str(it.get("n", it.get("name"))))] = float(it.get("s", it.get("score")))
        except Exception:
            pass
    return out


# ── label loading ────────────────────────────────────────────────────────
def load_labels(profile: dict, include_tracks: bool):
    def _names(seq, key=None):
        out = []
        for x in seq or []:
            nm = x if isinstance(x, str) else (x.get(key) if key else "") or x.get("name") or x.get("artist")
            if nm:
                out.append(nm)
        return out
    arts = profile.get("artists", {})
    pos = _names(arts.get("confirmed"))
    rej = [(r.get("name", ""), r.get("reason", "")) for r in arts.get("rejected", []) if isinstance(r, dict)]
    if include_tracks:
        fb = profile.get("feedback", {})
        pos += _names(fb.get("liked_tracks"), "artist")
        rej += [(t.get("artist", ""), t.get("reason", "user feedback"))
                for t in fb.get("disliked_tracks", []) if isinstance(t, dict) and t.get("artist")]
    posset = {normalise_name(n) for n in pos}
    rej = [(n, w) for n, w in rej if n and normalise_name(n) not in posset]
    return pos, rej


# ── benchmark ─────────────────────────────────────────────────────────────
def run(profile_path: Path, strategies: list[str], models: list[str],
        folds: int, n_distract: int, include_tracks: bool, seed: int):
    profile = json.loads(profile_path.read_text("utf-8"))
    corpus = RagCorpus.load(config.RAG_CORPUS_PATH, config.RAG_TAG_ALIASES_PATH)
    taste = profile.get("preferences", {}).get("core_description", "")

    pos_names, rej_pairs = load_labels(profile, include_tracks)

    def resolve(nm):
        return corpus.by_name_normalised.get(normalise_name(nm))

    pos = [(nm, resolve(nm)) for nm in pos_names]
    pos = [(nm, ix) for nm, ix in pos if ix is not None]
    # dedup by idx
    seen = set(); pos = [(nm, ix) for nm, ix in pos if not (ix in seen or seen.add(ix))]
    neg = [(nm, why, resolve(nm)) for nm, why in rej_pairs]
    neg = [(nm, why, ix) for nm, why, ix in neg if ix is not None]
    negset = {ix for _, _, ix in neg}
    pos = [(nm, ix) for nm, ix in pos if ix not in negset]

    rng = random.Random(seed)
    excl = {ix for _, ix in pos} | negset
    distract_ix = rng.sample([i for i in range(len(corpus)) if i not in excl and corpus.artists[i].tags],
                             min(n_distract, len(corpus)))

    print(f"profile: {profile_path}")
    print(f"corpus: {len(corpus)} | positives: {len(pos)} | negatives: {len(neg)} | "
          f"distractors: {len(distract_ix)} | folds: {folds}\n")

    # Precompute tag vectors + prose query (fold-independent).
    tv = {ix: tagvec(corpus.artists[ix], corpus) for ix in
          {ix for _, ix in pos} | negset | set(distract_ix)}
    q_prose = {t: w * corpus.tag_idf.get(t, 1.0)
               for t, w in retrieval._apply_aliases(corpus, retrieval.build_query_tags(profile)).items()}

    want_emb = any(s == "embed" for s in strategies)
    ev = {}
    if want_emb:
        allix = list({ix for _, ix in pos} | negset | set(distract_ix))
        try:
            vs = _embed([artist_text(corpus.artists[i]) for i in allix])
            ev = dict(zip(allix, vs))
        except Exception as e:
            print(f"[embed] disabled ({e})"); strategies = [s for s in strategies if s != "embed"]

    # Expand llm_rerank into one entry per model.
    expanded = []
    for s in strategies:
        if s == "llm_rerank":
            for mdl in (models or [config.get_model()]):
                expanded.append(("llm_rerank", mdl))
        else:
            expanded.append((s, None))

    results = {}  # label -> {auc:[], p_at_k:[], rank:[]}
    pos_folds = stratified_folds(pos, folds, seed)
    neg_folds = stratified_folds(neg, folds, seed + 1)

    for f in range(folds):
        test_pos = pos_folds[f]
        test_neg = neg_folds[f]
        train_pos = [x for i, fold in enumerate(pos_folds) if i != f for x in fold]
        train_neg = [x for i, fold in enumerate(neg_folds) if i != f for x in fold]
        if not test_pos or not train_pos:
            continue
        pool = ([("pos", nm, ix) for nm, ix in test_pos]
                + [("neg", nm, ix) for nm, why, ix in test_neg]
                + [("dis", corpus.artists[ix].name, ix) for ix in distract_ix])

        for label, mdl in expanded:
            key = f"{label}:{mdl}" if mdl else label
            if label == "prose_tags":
                sc = {ix: cos_sparse(tv[ix], q_prose) for _, _, ix in pool}
            elif label == "anchor_tags":
                c = centroid_sparse([tv[ix] for _, ix in train_pos])
                sc = {ix: cos_sparse(tv[ix], c) for _, _, ix in pool}
            elif label == "embed":
                import numpy as np
                c = np.mean([ev[ix] for _, ix in train_pos], axis=0)
                sc = {ix: cos_dense(ev[ix], c) for _, _, ix in pool}
            elif label == "llm_rerank":
                loves = [nm for nm, _ in train_pos]
                rejects = [(nm, why) for nm, why, _ in train_neg]
                cand_names = [nm for _, nm, _ in pool]
                by_name = llm_taste_scores(taste, loves, rejects, cand_names, mdl)
                sc = {ix: by_name.get(normalise_name(nm), float("nan")) for _, nm, ix in pool}
            else:
                continue

            pos_s = [sc[ix] for kind, _, ix in pool if kind == "pos" and sc[ix] == sc[ix]]
            neg_s = [sc[ix] for kind, _, ix in pool if kind == "neg" and sc[ix] == sc[ix]]
            ranked = sorted(pool, key=lambda t: (sc[t[2]] if sc[t[2]] == sc[t[2]] else -1e9), reverse=True)
            k = len(test_pos)
            p_at_k = sum(1 for kind, _, _ in ranked[:k] if kind == "pos") / max(1, k)
            # mean rank of test positives among the full pool
            order = [ix for _, _, ix in ranked]
            ranks = [order.index(ix) + 1 for nm, ix in test_pos]
            r = results.setdefault(key, {"auc": [], "p_at_k": [], "rank": []})
            r["auc"].append(auc(pos_s, neg_s))
            r["p_at_k"].append(p_at_k)
            r["rank"].append(sum(ranks) / len(ranks))

    def mean(xs): return sum(xs) / len(xs) if xs else float("nan")
    def std(xs):
        if len(xs) < 2: return 0.0
        m = mean(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

    print(f"{'strategy':<40}{'AUC':>14}{'P@k':>8}{'mean_rank':>11}")
    print("-" * 73)
    order_keys = sorted(results, key=lambda k: mean(results[k]["auc"]))
    for key in order_keys:
        r = results[key]
        a = [x for x in r["auc"] if x == x]
        print(f"{key:<40}{mean(a):>7.3f}±{std(a):<5.3f}{mean(r['p_at_k']):>8.2f}{mean(r['rank']):>11.1f}")
    print(f"\npool per fold = held-out loves + held-out rejects + {len(distract_ix)} distractors")
    print("AUC 0.5 = coin flip. Higher AUC & P@k, lower rank = better.")


def main():
    ap = argparse.ArgumentParser(description="Taste-match benchmark")
    ap.add_argument("--profile", type=Path, default=_DEFAULT_PROFILE)
    ap.add_argument("--strategies", nargs="+",
                    default=["prose_tags", "anchor_tags", "embed", "llm_rerank"])
    ap.add_argument("--models", nargs="+", default=None,
                    help="models for llm_rerank (default: app's configured model)")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--distractors", type=int, default=300)
    ap.add_argument("--include-tracks", action="store_true",
                    help="also use liked/disliked TRACKS' artists as labels")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    if a.strategies and any(s.startswith("llm_rerank") for s in a.strategies):
        config.load_config()  # hydrate LLM key from keyring
    run(a.profile, a.strategies, a.models, a.folds, a.distractors, a.include_tracks, a.seed)


if __name__ == "__main__":
    main()
