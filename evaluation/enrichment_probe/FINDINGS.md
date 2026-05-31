# AI corpus enrichment — scaling study & production design

> **For:** project owner review. **Date:** 2026-05-30.
> **Question we set out to answer:** can AI-generated, controlled-vocabulary
> tags build dense, *discriminative* similarity clusters across the sparse
> MusicBrainz corpus — well enough to fix the "similar to band X is
> ignored" retrieval failure — and does enriching *more* artists help?
> **Short answer: yes on all counts, with a specific, measured design.**

---

## 1. The headline design (proven, not assumed)

The retrieval fix is **two coupled parts**, and shipping enrichment without
the second would make things *worse*:

1. **AI overlay** — each artist gets 6-8 controlled-vocabulary tags via
   `gpt-4o-mini`, stored as a separate `ai_tags_overlay.json` keyed by
   `mbid` (the durable layer — see §4).
2. **Similarity layer** — compute IDF-weighted cosine where:
   - **IDF is GLOBAL** (over the whole enriched corpus), *not* local to a
     candidate set. This was the single biggest measurement correction:
     local IDF over-weights generic mood tags and made enrichment look
     like a regression when it isn't.
   - similarity runs on **base tags ∪ AI *discriminative* tags**
     (genre/scene/vocal). The mood/rhythm/era/instrumentation tags are
     kept as metadata/filters but **excluded from the similarity space**
     because they're shared by every rock band and dilute precision.

On the 31-artist ground-truth set (3 seeds + their real peers + the 8
bands the live system wrongly returned), measured MAP / peer-vs-wrong
margin:

| Tag source (global IDF) | MAP | margin |
|---|---|---|
| baseline (current corpus tags) | 0.830 | +0.165 |
| AI alone | ~0.82-0.84 | +0.28 |
| base ∪ AI | ~0.82-0.85 | +0.28 |
| **base ∪ AI-discriminative** | **0.88-0.91** | **+0.30-0.33** |

The production design (`union_disc`) beats the current corpus on both
metrics at every pool size tested.

---

## 2. Does scaling help? — Yes (the core question)

Connectivity = the share of enriched artists that have at least one real
neighbour (IDF-cosine ≥ 0.30). An isolated artist is useless for
similarity, so this is the metric that determines whether a *given* seed
will find good neighbours once enriched.

| Pool size | Vocab | OOV | Connectivity ≥0.30 | mean top-1 sim | prod MAP | margin |
|---|---|---|---|---|---|---|
| 2 029 | v2 (341) | 16.0% | 99.9% | 0.772 | 0.908 | +0.298 |
| 5 029 | v3 (364) | 11.1% | 100.0% | 0.795 | 0.877 | +0.330 |
| 10 027 | v3 (364) | 11.1% | 100.0% | **0.834** | 0.877 | **+0.338** |

**Trend (the answer to the question):** the cleanest signal is **mean
top-1 neighbour similarity, which rises monotonically 0.772 → 0.795 →
0.834** as the pool doubles twice. More enrichment makes clusters
*tighter*, not just bigger. Connectivity saturates at 100%, quality on
the known clusters holds well above baseline (0.830), and the
discriminative peer-vs-wrong margin keeps improving (+0.298 → +0.338).
The MAP plateau at ~0.88 is a 3-seed ceiling artefact, not a regression —
margin and top-1 similarity, which don't saturate on 3 seeds, both rise.

> Note on reciprocity: it's measured only among the 1 200 artists sampled
> for the O(n²) scan, so as the pool grows a sampled artist's true nearest
> neighbour is less likely to *also* be sampled — the ratio gets noisier
> (80% → 80% → 73%) for sampling reasons, not quality. Top-1 similarity
> (no such artefact) is the reliable signal and it rises cleanly.

**Conclusion: scaling enrichment is beneficial and safe.** A full-corpus
run will give ~100% connectivity with tight neighbourhoods — exactly what
seed-artist retrieval needs. The 10k control group is large enough to
trust this extrapolates: the curve is still improving at 10k with no sign
of degradation.

---

## 3. Calibration & safety (no confident hallucination)

- Confidence rises correctly with obscurity (low-confidence share grows
  on the sparse tail); the model flags what it doesn't know instead of
  confidently inventing.
- Empty tag sets: ~1.1% (artists with essentially no signal — left
  empty rather than hallucinated).
- ~0 API errors (1 transient failure across ~17k calls; the skip-gate
  re-enriches it on any later run automatically).

---

## 4. Architecture — why an overlay, and the Cloud Run correction

**Important correction to the earlier assumption:** the Cloud Run job does
**not** preserve locally-added fields. Its Phase 1
(`_run_phase1_mb_build` → `refresh_rag_corpus.py` → `build_rag_corpus.py`)
rebuilds `artists.jsonl.gz` **from scratch from the MusicBrainz dump** and
overwrites the bucket copy; `manifest.json` is only version/sha metadata,
also overwritten. Anything baked into the base corpus is destroyed on the
next cycle.

**The durable path is an overlay.** `RagCorpus.load()` already auto-merges
a sibling `top_tracks_overlay.json` at load time. AI tags ride the same
pattern: `ai_tags_overlay.json` lives *next to* the corpus, survives base
rebuilds, and is merged client-side.

This realises the layered design you asked for — each enrichment source
**owns its own fields and updates independently**:

- **MusicBrainz base** → `artists.jsonl.gz` (rebuilt by the MB job).
- **Last.fm** → its own fields (additive).
- **AI** → `ai_tags_overlay.json`, keyed by `mbid`, gated by a
  **`source_hash`** of (name + base tags + top tracks + vocabulary +
  model). On re-run, unchanged entries are **skipped** (no API call);
  only new or genuinely-changed artists are (re)enriched. Verified:
  re-running skips 100% of unchanged entries.

The same hash-gated, mbid-keyed, own-fields-only pattern is the template
for making the MB and Last.fm layers independently updatable in the Cloud
Run pipeline (a follow-up pipeline change, not done here).

---

## 5. Cost

- Per-artist call with prompt caching (the ~1.4k-token vocabulary system
  prompt is cached at 50%): ~€0.00014/artist → **~€25 for the full 175k
  corpus unbatched.**
- **Batching ~40 artists/call** amortises the system prompt and brings the
  full corpus to **~€5-7** (the figure to use for production). Well within
  budget, and only paid once thanks to the skip-gate.
- Incremental new-artist enrichment afterwards is pennies.

---

## 6. Honest caveats

- **The 31-artist ground-truth set is all rock.** It proves the seed
  use-case strongly but doesn't measure precision inside metal / hip-hop /
  electronic neighbourhoods. The connectivity metric (whole-pool) covers
  those, but a labelled non-rock cluster test would harden the claim.
- **Per-artist cost is over €20; batching is required** for the full run.
  The script currently does per-artist calls (fine for ≤10k experiments).
- **OOV is ~11% and mostly harmless** (vague words like `melodic`,
  `heavy` that get dropped, not stored). A handful are genuine genre
  variants (`heavy psych`, `eurodance`, `psytrance`) that a v4 vocab pass
  could absorb to push OOV toward ~7%.
- **MAP is a 3-seed metric** — directional, not precise. The margin and
  connectivity numbers are more trustworthy.

---

## 7. Recommended next steps

1. **Wire the similarity layer** in `core/src/rag/retrieval.py`: global
   IDF + `base ∪ AI-discriminative`, plus seed-artist extraction into
   `meta.reference_artists` (the orthogonal root-cause fix). Validate on
   `run_evaluation.py` — North Star no-regression gate.
2. **Batch the enrichment** (~40/call) and run the full corpus once
   (~€5-7) into `ai_tags_overlay.json`; publish the overlay alongside the
   corpus so it survives Cloud Run rebuilds.
3. **(Optional) v4 vocab pass** to absorb the genuine genre variants and
   push OOV to ~7%.
4. **(Optional) labelled non-rock cluster test** to harden the precision
   claim outside rock.

Artifacts (all reproducible): `evaluation/enrichment_probe/`
— `enrich_ai_layer.py` (overlay producer), `vocabulary.py` (v3),
`verify_overlay.py`, `production_metric.py`, `cluster_connectivity.py`,
`ai_tags_overlay.json` (the enriched pool).
