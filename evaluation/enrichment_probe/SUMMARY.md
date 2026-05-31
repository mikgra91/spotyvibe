# AI corpus enrichment — bake-off probe results (2026-05-30)

**Question:** Can AI-generated controlled-vocabulary tags fix the
"similar to band X is ignored" retrieval failure, for < €20 one-time?

**Test set:** 31 corpus artists with ground-truth clusters — 3 seed
bands (Bear Ghost / Origami Angel / Mrs. Green Apple), their real
peers (confirmed in corpus), and the 8 bands the *live* system
wrongly suggested (Thornley, Dolu Kadehi Ters Tut, etc.).

**Method:** enrich each with controlled-vocab tags (2 models + 1
refined prompt), then measure whether tag-overlap similarity ranks
true peers above the wrongly-suggested bands. Baseline = existing
corpus tags.

## Headline results

| Config | Jaccard MAP | IDF MAP | IDF peer/wrong margin | avg tags | vocab obey |
|---|---|---|---|---|---|
| baseline (existing tags) | 0.826 | 0.777 | +0.163 | 3.5 | — |
| gpt-4.1-nano | 0.805 | **0.844** | +0.195 | 6.2 | 90% |
| gpt-4o-mini (v1) | 0.697 | 0.748 | **+0.211** | 8.9 | 97% |
| gpt-4o-mini v2 (refined) | 0.679 | 0.656 | +0.190 | 5.7 | 97% |

## What's proven

1. **Enrichment works — but ONLY with IDF-weighted similarity.** Under
   plain Jaccard, enrichment REGRESSES retrieval (generic mood tags
   shared by every rock band dilute the rare scene tags). Under IDF
   weighting (rare scene tags up-weighted), `gpt-4.1-nano` beats
   baseline MAP (0.844 vs 0.777) and every model beats baseline on
   peer-vs-wrong separation. **The prod fix is two coupled parts:
   enrichment + IDF-weighted similarity. Enrichment alone would make
   things worse.**

2. **Output is dramatically better than the live system.** For Mrs.
   Green Apple, the IDF top-4 nearest neighbours are *all* its real
   J-rock peers (UNISON SQUARE GARDEN, sumika, KANA-BOON, King Gnu) —
   versus the Turkish bands the live system actually returned.

3. **Cost is feasible.** Batched (~40 artists/call):
   - gpt-4.1-nano: **~€4.10** full corpus (175,578 artists)
   - gpt-4o-mini:  **~€6.28** full corpus
   Both well under the €20 budget. (Per-artist unbatched: €15 / €23 —
   batching is required.)

4. **Vocabulary obedience is excellent** (gpt-4o-mini 97% in-vocab),
   and low-confidence flagging fired correctly on the artists the
   model didn't know (sumika, Dolu Kadehi Ters Tut).

## Honest caveats / what this probe did NOT prove

- **Test set is biased toward well-tagged artists** (they need known
  peers to be testable). This UNDER-states enrichment's real value:
  60% of the real corpus has ≤2 sparse/junk tags where baseline has
  nothing to match on.
- **Long-tail hallucination not validated at scale.** The confidence
  flag is a safety valve but accuracy on truly-obscure artists is
  unmeasured.
- **My "be more discriminative" prompt (v2) backfired** — it
  over-pruned and over-used "energetic", regressing both metrics. The
  robust lever is IDF on the similarity side, not prompt self-censoring.
- **Bear Ghost is the hardest case** (genuinely genre-bending) — its
  margin is smallest and shows some cross-scene leakage. Inherent to a
  genre-bending seed, not a fatal flaw.

## Recommended next step (before the full run)

Run a ~500-artist validation that INCLUDES sparse/junk-tag long-tail
artists (~€0.05) to (a) confirm enrichment quality on the hard cases
and (b) measure hallucination rate via the confidence flag. Then the
full-corpus run is justified and de-risked.

Production change is therefore: enrichment job (reusing the existing
Cloud-Run batched harness) + IDF-weighted similarity in retrieval +
the seed-artist extraction fix (orthogonal, still required).

---

## 500-artist long-tail validation (2026-05-30, follow-up)

Stratified sample (150 head / 200 mid / 150 tail) across the real
corpus distribution, gpt-4o-mini, v1 prompt. **0 errors / 500 calls.**

**Confirmed good:**
- **Confidence calibration is sound.** Low-confidence rises with
  obscurity: head 1 → mid 10 → tail 28. **Zero** tail artists claimed
  HIGH confidence with zero input grounding — no confident
  hallucination. This was the key safety property and it held.
- **Sparse long-tail gets filled:** 88 tail artists had ≤1 input tag →
  avg 5.7 enriched tags each.
- **Cost confirmed: €5.75** batched for the full 175,578 corpus.

**Critical gap found — vocabulary is too rock-centric for the full corpus:**
- Out-of-vocab tags jumped to **18% (tail) – 37% (head)** vs 3% on the
  rock test set. The model *correctly* wanted real genres my vocab
  omits: pop, electronic, black/death/doom metal, lo-fi hip hop, trap,
  house, k-pop, latin, classical, boom bap, techno (468 unique OOV).
- Failure modes on non-rock artists: drops the genre and keeps only
  mood (enka→melancholic), force-fits a wrong neighbour (latin→folk),
  or returns **empty** (Slimelord, a death-doom band → []).
- This is a VOCABULARY COVERAGE problem, not a model/cost/hallucination
  problem. Enrichment quality is high WHERE the vocab fits (the rock /
  emo / J-rock seed neighbourhood — the actual use case).

**Scale-up verdict: not the full 175k yet. Two prerequisites first:**
1. **Expand the controlled vocabulary** to ~400-500 terms covering all
   major genre families (metal/hip-hop/electronic/world/jazz/classical
   subgenres). Re-validate OOV < ~5%.
2. **Implement IDF-weighted similarity** in retrieval (mandatory; plain
   Jaccard regresses).

**Cheaper interim option:** enrich only the rock/alt/pop/emo/J-rock
subset (or enrich on-demand around a user's reference artists). That
fixes this user's discovery experience immediately for a fraction of
the cost, deferring the death-metal/k-pop/latin long tail this user
will never seed.
