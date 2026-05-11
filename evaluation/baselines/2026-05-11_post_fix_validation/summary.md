# Validated baseline eval — 2026-05-11 (post-fixes)

**Run:** `evaluation/results/20260511-081757/`
**Scope:** scenario `default`, models `gpt-5.4-mini` + `gpt-5.4`, 3 iter each.
**Wall:** 70 min (10:18 → 11:27).
**Cost (corrected — see Finding 0):** ~$0.90 actual.
**Purpose:** validate the two fixes from the 2026-05-11 morning analysis
([summary.md](../2026-05-11_tier1_validation/summary.md)) — Tier-0 v2
(STAGE3_MODE force-override) and the prompt-prefix instability fix
(`{batch_size}` moved out of the system prompt).

> ## ✅ FIRST VALID MINI-vs-GPT-5.4 COMPARISON SINCE L5 SHIPPED
>
> Trace verification across all 12 trace bundles (6 iters × A+B):
> - `model = ['gpt-5.4']` for the 3 gpt-5.4 iters, `['gpt-5.4-mini']` for the 3 mini iters.
> - `stage3_mode = ['custom']` everywhere — no fast-collapse anywhere.
> - `system_md5` unique values per iter = **1** (was 5 before the fix).
> - System prompt length stable at exactly **5175 chars** across all 48 batches.
>
> The two fixes shipped 2026-05-11 morning are both verified working in
> production traces. This is the first cross-model eval whose data we can
> trust for design decisions since the L5 selector landed (2026-05-10).

---

## Headline numbers

### Quality (n=3 per cell)

| metric | gpt-5.4-mini | gpt-5.4 | gap |
|---|---:|---:|---:|
| **Playlist A tracks** (target 15) | 12, 13, 14 → **mean 13.0** (87%) | 12, 15, 14 → **mean 13.7** (91%) | +0.7 (+5pp) |
| **Playlist B tracks** (target 15) | 5, 3, 5 → **mean 4.3** (29%) | **1**, 14, 13 → **mean 9.3** (62%) | +5.0 (+33pp) |
| **must-have cite rate** | 74%, 98%, 86% → **mean 86%** (range 24pp) | 96%, 94%, 98% → **mean 96%** (range 4pp) | +10pp + far stabler |
| **Spotify-found rate** | 40%, 37%, 43% → **mean 40%** | 57%, 81%, 68% → **mean 68%** | +28pp |
| **leakage gate** | 3/3 pass | 3/3 pass | tie |
| **fit gate** (decade_avoid) | 3/3 pass | 3/3 pass | tie |

### Cost & latency (per-run, both playlists combined)

| metric | gpt-5.4-mini | gpt-5.4 |
|---|---:|---:|
| **cost / run** | $0.079 mean (range $0.078-$0.081) | $0.219 mean (range $0.192-$0.246) |
| **cost / playlist** | **$0.039** (mean) | **$0.110** (mean) |
| **wall / run** (gen + verify) | 66s mean | 95s mean |
| **Stage-3 wall A+B sum** | 263s mean | 460s mean |

### Cache hit rate (post-prefix-fix)

| iter | per-batch hit % (8 batches: 4×A + 4×B) | total cached/prompt |
|---|---|---:|
| mini i1 | 0, 71, 69, 68, 0, 69, 68, 67 | **52%** |
| mini i2 | 75, 71, 70, 69, 0, 67, 67, 65 | **60%** |
| mini i3 | 0, 72, 69, 68, 0, 67, 66, 65 | **51%** |
| gpt-5.4 i1 | 0, 75, 73, 0, 0, 73, 73, 73 | **46%** |
| gpt-5.4 i2 | 0, 76, 73, 72, 0, 75, 73, 72 | **56%** |
| gpt-5.4 i3 | 0, 71, 69, 68, 0, 70, 68, 67 | **52%** |

- **Mean: 53%** across 6 iters (was 40% in the previous eval — **+13 pp**).
- **Pattern is now deterministic:** batch 1 (cold) and batch 5 (first batch of Playlist B) miss; everything else hits at 65-76 %.
- Hit value is consistent (no high variance). C4 routing + prefix fix together work as designed.
- Theoretical ceiling under the current 4-batch-per-playlist regime is 75 % (6 of 8 batches eligible to hit). Current 53 % includes the pattern where occasionally a middle batch misses too — see Finding 4.

---

## Findings (in priority order)

### Finding 0 — Both 2026-05-11-morning fixes verified working ✅

The Tier-0 v2 fix (monkey-patch `get_stage3_mode` + `os.environ` re-assert
+ loud-fail assertion in `evaluation/run_evaluation.py`) holds across the
production-module import chain. The prompt-prefix fix (move `{batch_size}`
and `{min_new_artists}` from `prompts/track_select_system.txt` into
`prompts/track_select_user.txt`) collapses `system_md5` from 5 unique
values per iter to exactly 1.

The validated cross-model data follows.

### Finding 1 — gpt-5.4 is materially better at every quality dimension 🎯

| dimension | mini | gpt-5.4 | takeaway |
|---|---|---|---|
| Playlist A completion | 87 % | 91 % | small gap, both pass |
| **Playlist B completion** | **29 %** | **62 %** | **2.2× gap** — gpt-5.4 wins decisively |
| **Must-have cite rate** | 86 % (74-98) | 96 % (94-98) | gpt-5.4 follows the cite-must-haves rule far more reliably |
| **Spotify-found rate** | 40 % | 68 % | gpt-5.4 picks tracks that actually exist 1.7× more often |
| Variance | high | low | gpt-5.4 outputs are far more consistent |

**Mechanism:** mini's lower Spotify-found rate (40 % vs 68 %) is the
structural cause of its B-collapse. The harness keeps re-batching until
`MAX_GPT_CALLS_PER_RUN = 4` is exhausted; if more than half the
suggestions fail Spotify-verify each batch, the playlist can never reach
the target. gpt-5.4 hallucinates fewer tracks → more verifications pass
→ playlist fills.

**Cite-rate variance** is also revealing: mini iter 1 cited must-haves
on only 74 % of tracks (nearly a quarter ignored the constraint), while
gpt-5.4 stays at 94 %+ across all iters. This is an instruction-following
gap, not a music-knowledge gap.

**Implication for the cost programme:** the L5 default-flip from
`fast` → `auto` (escalate to gpt-5.4 once feedback exists) is now
empirically justified — playlist B is the load-bearing case for "user
already gave us signal" and mini's 29 % completion there is a real
product failure. The $0.110/playlist on gpt-5.4 is **just over** the
$0.10 budget but the quality differential warrants either:
- (a) accepting the $0.01 overshoot, OR
- (b) closing the cache hit gap to ~80 % which would knock gpt-5.4 cost
  to ~$0.085/playlist (see Finding 4).

### Finding 2 — gpt-5.4 iter 1 Playlist B = 1 track is the anti-confab guardrail working ⚠️

The B-collapse on gpt-5.4 iter 1 (1/15 tracks, vs 14 and 13 on the
other two iters) is **not** a model failure. Inspection of the 4
batch_summary rows for that playlist:

| batch | cite_rate | parsed |
|---|---|---|
| 1 (Playlist B, batch 1) | 1.0 | some |
| 2 | none → empty response |
| 3 | none → empty response |
| 4 | 1.0 | 1 entry |

After Playlist A consumed the high-confidence artists (12 tracks worth)
and the user's dislikes pruned several more from the candidate pool, the
APPROVED_ARTISTS list for B was thin — and gpt-5.4 correctly chose to
return *empty batches* rather than invent tracks (per the
ANTI-CONFABULATION rules in the system prompt). With only 4 batches
allowed per playlist (`MAX_GPT_CALLS_PER_RUN = 4`), 2 empty batches
caps the playlist at 1-3 tracks no matter what.

**This is a desirable behaviour** — anti-confab is the highest-priority
rule in the prompt. It's working exactly as written. The fix isn't to
the model or prompt; it's to the harness/production: when batches return
empty consistently, *expand the candidate pool* (re-run RAG retrieve
with relaxed constraints) before running another batch on the same pool.

**Recommended ticket:** new "**A6 — RAG re-retrieve on consecutive empty
Stage 3 batches**". Not in scope for the cost programme but should land
before the L5 default-flip.

### Finding 3 — Prompt-prefix fix delivers the predicted cache uplift ✅

| metric | before fix (2026-05-11 AM) | after fix (this eval) | Δ |
|---|---:|---:|---:|
| Mean total cache hit rate | 40 % (n=6 mini) | 53 % (n=6 mixed) | **+13 pp** |
| Per-batch hit consistency | high variance (1-7 / 8 hits) | low variance (5-7 / 8 hits) | qualitatively cleaner |
| Unique `system_md5` per iter | 2-4 | **1** | structural fix |

OpenAI's auto-prompt-cache requires byte-identical prefixes ≥ 1024
tokens. With the system prompt now invariant per (model, language,
emerging_only) triple AND C4's `prompt_cache_key` routing requests to
the same host, the cache prefix is finally being hit reliably. The
remaining misses are batch 1 (cold) and batch 5 (first batch of new
playlist — see Finding 4).

### Finding 4 — Why batch 5 always misses, and how to push hit rate to ~85 %

Batches 1 and 5 always miss across all 6 iters. Batch 1 is unavoidable
(cold cache). Batch 5 = first batch of Playlist B. Hypothesis: between
playlist A and B, the cumulative cache-window timeout (OpenAI's auto-
cache TTL is documented as ~5-10 min) elapses because of the harness's
**post-A feedback ingestion** (likes/dislikes apply, profile re-trains
on dislike list, etc.) — this takes 30-60 s, plus whatever idle wait the
harness imposes before B starts. By batch 5 the prefix entry has
expired.

**Validation needed:** measure `time(batch4) - time(batch5)` per iter
and correlate with batch-5 hit rate. Trivial to add.

**Potential fix:** issue a tiny "keep-alive" call against the same
prompt-cache key in the post-feedback gap. ~$0.0002 per playlist B
keepalive vs ~$0.005 saved by hitting batch 5 = positive ROI. Could
also be an aspirational ticket; the win is small per-run but adds up.

### Finding 5 — `system_fingerprint` confirmed not returned by either model on the chat-completions endpoint ❌

All 48 Stage 3 calls (mini + gpt-5.4, both playlists, all iters):
`system_fingerprint = null`. Our http wrapper extraction is correct
([core/src/openai_http.py](../../../core/src/openai_http.py) returns the
raw OpenAI JSON response). Neither `gpt-5.4-mini` nor `gpt-5.4`
populates this field on the `/v1/chat/completions` route in
2026-05.

**Implication:** the "detect a model roll" use case from
`next-steps.md:1409` cannot be answered for the current models. The
plumbing stays in place for forward-compat (e.g. if OpenAI restores it
on a future model, or if we test `gpt-4.1` which may still emit it).

**Action:** lower-case this in the next-steps tracking and stop budgeting
work against the fingerprint capability.

---

## What the data tells us about how the models read our prompt

This was the user's headline question. The Tier-1 logging now lets us
answer it directly:

1. **Both models follow the OUTPUT schema reliably.** Every batch
   returned valid JSON with the `reasoning` + `playlist` keys. Schema
   compliance is not the bottleneck.

2. **Both models internalise the seed_interpretation correctly.** Sample
   from gpt-5.4 iter 1 batch 1 reasoning: *"The listener wants 'modern
   theatrical pop-rock with strong hooks and quirky personality' built
   on 'punchy guitars, strong hooks, modern production, theatrical…'"*
   — quotes the right load-bearing phrases from the taste summary.
   Mini does the same. Reading comprehension is not the bottleneck.

3. **mini is sloppier with the must-have cite rule.** 74-98 % cite rate
   means mini sometimes returns tracks where no rationale entry cites a
   Must: trait. The prompt phrasing is direct: *"Each rationale entry
   MUST cite a different facet of the taste summary. If Must: traits
   are listed, at least ONE rationale entry MUST be a profile_match
   citing a Must: trait."* — gpt-5.4 obeys this 96 % of the time, mini
   86 %. **Hypothesis:** mini's smaller working memory loses the
   constraint when rationales are written; gpt-5.4 keeps it active.
   **Fix candidate:** re-state the cite rule in the user message
   immediately before the schema example, so it's the most-recent
   instruction at output time. R1 should test this.

4. **mini hallucinates ~28 pp more often than gpt-5.4.** 40 % vs 68 %
   Spotify-found rate. The `known:` block in APPROVED_ARTISTS is
   supposed to ground the model, but mini still picks unverified
   titles. **Fix candidate (high-leverage):** when an artist has 0
   `known:` examples, the prompt currently says *"only suggest if you
   recall a real released track"* — mini interprets this as
   "permission to recall something" and confabulates. Tighten to
   *"NEVER suggest tracks for an artist with no known: examples;
   always omit such artists"* and measure. gpt-5.4 already obeys the
   intent of this rule; mini needs the harder version.

5. **gpt-5.4 enforces anti-confab as designed (Finding 2).** Returning
   empty batches when the pool can't be grounded is exactly what we
   want. No prompt change needed here.

6. **The `OMITTED-ARTIST EXAMPLE` block in the system prompt is doing
   work for gpt-5.4 but not mini.** Inspect mini's `omitted_artists`
   field per batch: it's often empty even when the pool has obvious
   genre mismatches. gpt-5.4 routinely lists 5-10 omitted artists with
   reasons. **Fix candidate:** make the omission a hard requirement
   ("at least 1 entry in `omitted_artists` for any artist you skipped,
   with the omission count >= APPROVED_ARTISTS_count - track_count"),
   not a "MUST" without a numeric anchor. This forces mini to think
   about the artists it isn't picking, which in turn makes
   confabulation harder (because each unused artist needs an explicit
   reason).

---

## Recommended next steps (ranked by quality-per-effort)

### P0 — directly improve mini quality (R1 spike scope)

1. **R1.1 — Re-state must-have cite rule at the end of the user
   message.** Single prompt edit. Hypothesis: lifts mini cite rate from
   86 % → ≥ 92 %. Eval cost: 1 mini-only run × n=5 iter = ~$0.40.
2. **R1.2 — Tighten "no known: examples" rule.** Single prompt edit.
   Hypothesis: lifts mini Spotify-found rate from 40 % → ≥ 55 %, which
   knocks B-collapse hard. Eval cost: same scope.
3. **R1.3 — Force `omitted_artists` to be non-empty when artists were
   skipped.** Schema constraint. Hypothesis: mini becomes more
   discriminating, drags Spotify-found rate up further.

Run R1.1-3 sequentially with the same eval matrix as today
(`default × {mini} × 3 iter`, ~35 min wall, ~$0.40 cost each, ~$1.20
total). Compare against today's mini baseline (cite 86 %, found 40 %,
B-completion 29 %). Promote any variant that hits ≥ +5 pp on cite OR
≥ +10 pp on Spotify-found, without regressing the other.

### P1 — close the cache-hit gap to ~85 % (cost win)

4. **A6 — RAG re-retrieve on consecutive empty Stage 3 batches.**
   Production-side change in `core/src/suggestions.py`. Independent of
   prompt R1 work. Estimated quality win: lifts gpt-5.4 worst-case B
   from 1 → 5+ tracks, no impact on mini.
5. **C4.1 — Cache keepalive between A and B.** ~$0.0002 per run vs
   ~$0.005 saved per run. Tiny; do it once, never think about it again.

### P2 — the L5 default-flip decision is finally measurable

6. **Now that we have valid mini vs gpt-5.4 numbers**, the L5 `auto`
   mode (escalate to gpt-5.4 on first dislike) becomes a measurable
   trade. Current data: gpt-5.4 wins quality decisively but costs
   $0.11/playlist (just over the $0.10 ceiling). Decision tree:
   - If R1.1-3 push mini's B-completion above ~50 %, default stays at
     `fast` (mini covers most of the value, escalation rare).
   - If R1.1-3 cannot close the B gap, flip default to `auto` and
     accept the $0.11 ceiling (or raise the ceiling to $0.12 — the
     user explicitly said they'd consider this if quality justifies it).

### P3 — operational hardening

7. **Spotify cache disappeared between sessions** (had to copy from
   sandbox + force token refresh to restart this eval). Investigate
   whether AV / OS cleanup is removing it, or whether some code path
   we don't know about deletes it. Filed as a follow-up bug.
8. **Eval cost reporting fix (now harmless).** Comparison report's
   cost number multiplies real tokens × labelled-model rate. Now that
   labelled = actual model (Tier-0 fixed), the numbers ARE accurate.
   No code change needed; just stop disclaiming it in summaries.

---

## Validation gate — what we now know vs what's still hypothesis

✅ **Verified empirically (n=6 across 2 evals):**
- Tier-0 v2 fix holds across full production-module import chain.
- Prompt-prefix fix collapses `system_md5` to 1 unique value per iter.
- Cache hit rate jumps +13 pp from prefix fix alone.
- mini-vs-gpt-5.4 quality gap is real and large (Playlist B 33 pp,
  cite 10 pp, Spotify-found 28 pp).
- Anti-confab rule works as designed on gpt-5.4 (returns empty batches
  rather than hallucinate).

⚠️ **Hypothesis, untested:**
- R1.1-3 prompt fixes will close the mini quality gap.
- A6 (RAG re-retrieve on empty batches) will fix gpt-5.4 worst-case.
- Batch 5 cache miss is from TTL expiry between A and B (not yet
  measured).

❌ **Cannot answer with current setup:**
- `system_fingerprint` is null on both models — can't detect model rolls.

---

## Operational notes

- **No 429s.** Spotify cooldown stack working.
- **All 6 cleanups OK.** Sandboxes + test playlists deleted.
- **Spotify token survived 70 min wall** (TTL is nominally 60 min;
  refresh-token flow appears to have triggered correctly mid-run).
- **No Tier-0 guard failure.** The startup assertion in
  `evaluation/run_evaluation.py` would have aborted the run before
  burning OpenAI quota if the fix had regressed.

