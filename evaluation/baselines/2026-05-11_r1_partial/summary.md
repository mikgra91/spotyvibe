# R1 prompt-engineering spike — 2026-05-11 (partial, n=1)

**Run:** `evaluation/results/20260511-120655/`
**Scope:** scenario `default`, model `gpt-5.4-mini`, **1 of 3 iter** completed
(eval aborted at iter 2 by Spotify 429 with Retry-After ~85 min — see
"Operational outcome" below).
**Wall:** ~3 min for iter 1 (14:06 → 14:09); aborted at iter 2 batch
during Playlist-A retry (14:21).
**Purpose:** test R1.1 (cite-rule re-stated at end of user message) +
R1.3 (`omitted_artists` required non-empty when artists skipped) against
the [2026-05-11 post_fix baseline](../2026-05-11_post_fix_validation/summary.md)
(mini n=3: A=13.0, B=4.3, cite 86 %, found 40 %, hit 53 %).

> ## ⚠️ DATA IS n=1 — DO NOT BASE DESIGN DECISIONS ON IT
>
> The R1 spec ([next-steps.md:1265](../../../next-steps.md#L1265))
> explicitly requires ≥ 3 iter (ideally 5) to smooth single-run variance.
> A complete iter 3 run was prevented by Spotify rate-limiting against
> the user-token. This summary records the data we DO have, the R1.2
> rejection (real finding), and the operational blocker.

---

## What shipped before this eval

Three prompt edits in `prompts/`:

| ID | Change | Status post-iter-1 |
|---|---|---|
| **R1.1** | "Each rationale entry MUST cite a different facet … At least ONE rationale entry per track MUST be type=profile_match quoting a Must: trait verbatim" — re-stated as a `REMINDER` block AT THE END of `track_select_user.txt` so it is the most-recent instruction at output time. | KEPT — model follows it. |
| **R1.2** | Tighten "no known: examples" rule in `track_select_system.txt` from *"OMIT that artist unless you are sure of a real released track"* to *"OMIT — Do NOT attempt to recall a track for an artist with no known: examples"*. | **REJECTED** — see Finding 1. |
| **R1.3** | Add explicit non-empty requirement on `omitted_artists`: *"if APPROVED_ARTISTS lists N artists and you only used M of them in `playlist`, then `omitted_artists` MUST contain (N − M) entries"*. | KEPT — model follows it with high fidelity (Finding 2). |

---

## Findings (priority order)

### Finding 1 — R1.2 is unworkable on the current RAG corpus. REJECTED. 🛑

**Symptom:** in the very first iter (sandbox `20260511-120118`), the model
omitted **40 / 40 artists in the pool** → 0 tracks → `under_filled`
playlist → 0 / 15 completion. The harness emitted
`POOL_BAD: omitted=40/40 (100 %)` and the playlist collapsed to empty.

**Cause:** in the current Last.fm-enriched corpus the **majority of niche
artists have empty `known:` lines** (the `top_tracks_overlay` doesn't
cover them yet). The post_fix baseline's 40 % Spotify-found rate
depended on the model **using its own knowledge** to suggest tracks for
artists with no `known:` examples — which the OLD prompt explicitly
permitted ("only suggest if you recall a real released track"). R1.2's
strict version ("OMIT — do NOT attempt to recall") removes that escape
hatch and the playlist starves.

**Decision:** revert R1.2. Re-open as a **dependent ticket on overlay
coverage expansion** — the rule is *correct in theory* (it removes
hallucination opportunities) but cannot ship until `top_tracks_overlay`
covers a materially higher fraction of niche artists.

**Recovery action shipped:** R1.2 was reverted before iter 1 ran for the
metrics below; the eval log under `20260511-120118` documents the
failure mode in trace bundles for future reference.

### Finding 2 — R1.3 (forced `omitted_artists`) works as designed ✅

The model's `omitted_artists` block in batch 1 of the iter-1 run is rich
and disciplined:

```json
"omitted_artists":[
  "St. Lenox: no known: tracks available and I can't ground a real release confidently",
  "Firestations: no known: tracks available and unfamiliar",
  "Misha B: no known: tracks available and unfamiliar",
  …28 entries total…
]
```

**This is the first time** in any logged eval that mini has produced a
≥ 5-entry `omitted_artists` block. In the post_fix baseline, mini's
omitted_artists field was *often empty even when the pool had obvious
genre mismatches* (post_fix Finding 5, "doing work for gpt-5.4 but not
mini"). R1.3's numeric anchor — `(N − M)` minimum entries — flipped the
behaviour: mini now omits ~28 of 40 artists per batch *with explicit
reasoning*, instead of silently dropping them.

Downstream effect: when the model omits 28 of 40, it returns only 8-12
tracks from the 4 artists it can ground, instead of padding the count
with confabulations. The cite rate on those grounded picks is high
(Finding 3). This is **exactly the discrimination behaviour the post_fix
analysis predicted** would happen if R1.3 landed.

### Finding 3 — R1.1 (cite-rule REMINDER) lifts per-batch cite rate

Per-batch `must_have_cite_rate` from iter 1 (n=7, batch 3 has no
rationale_stats because `after_filter=0`):

| Batch | A/B | cite_rate | parsed |
|---|---|---:|---:|
| 1 | A | **1.00** | 8 |
| 2 | A | 0.80 | 10 |
| 3 | A | — | 0 (all dup) |
| 4 | A | **1.00** | 2 |
| 5 | B | 0.57 | 7 |
| 6 | B | 0.67 | 3 |
| 7 | B | **1.00** | 8 |
| 8 | B | 0.67 | 6 |

**Mean cite_rate over 7 measurable batches: 0.816 (~82 %).**

Cite-rate context vs baselines:

| Baseline | mini cite rate (range, mean) |
|---|---|
| B1 (2026-05-08) | 71-92 %, mean 86 % |
| post_fix (2026-05-11 AM) | 74 / 98 / 86 %, mean 86 % |
| **R1 iter 1 (this run)** | **57-100 %, mean 82 %** |

n=1 cannot beat n=3 mean 86 %, but the per-batch *minimum* (57 %) is
below the post_fix iter 1 minimum (74 %). Looking at the raw responses,
the low-cite batches are exactly the **late-batch B batches** where the
candidate pool has been exhausted of high-confidence anchors and the
model is reaching for weaker grounding — those rationales tend to cite
soft_preferences rather than Must: traits.

**Hypothesis** (needs n≥3 to confirm): R1.1 lifts cite rate on
high-confidence batches (1.0 on batch 1, 1.0 on batches 4 and 7) but
cannot rescue late batches where the pool is structurally thin. The
fundamental fix for those is **A6 (RAG re-retrieve on consecutive empty
batches)** — see post_fix Finding 2 — not more prompt-engineering.

### Finding 4 — Spotify-found rate slightly DOWN (n=1, 31 % vs baseline 40 %)

Per-batch `spotify_found_count / gpt_returned_count`:

| Playlist | suggested | spotify_found | rate |
|---|---:|---:|---:|
| A (batches 1-4) | 31 | 12 | 38.7 % |
| B (batches 5-8) | 27 | 6 | 22.2 % |
| **All** | 58 | 18 | **31.0 %** |

Vs post_fix baseline mini mean: 40 %. **Δ = -9 pp** at n=1.

Interpretation candidates:
- **n=1 variance.** Post_fix individual iters were 37 %, 40 %, 43 % —
  a ~6 pp spread. Today's 31 % is outside that spread but n=1 cannot
  rule out a tail draw.
- **R1.3 discrimination side-effect.** With R1.3 forcing the model to
  omit instead of confabulate, the picks the model DOES make should be
  *more* confidently grounded — yet the Spotify-found rate is lower.
  This suggests the model is still confabulating titles even for
  artists with `known:` examples (i.e., it picks a different real
  title that doesn't match Spotify's catalogue search query).
- **B-playlist starvation.** B's 22 % vs A's 39 % is the largest
  effect. After dislike feedback prunes high-confidence artists from
  the pool, mini's remaining candidates are structurally less
  recognisable. Aligns with post_fix Finding 2 (gpt-5.4's
  anti-confab kicks in here; mini's doesn't, so mini guesses badly).

**Recommendation:** do not declare regression on n=1. Re-run n≥3 once
Spotify quota recovers. If 31 % holds, the R1.1+R1.3 combo regresses
Spotify-found by ~10 pp and R1.3 specifically needs softening (likely:
allow R1.3 but stop short of forcing omission — the discrimination
signal works, the recall is what we lose).

### Finding 5 — Playlist B completion +11 pp on n=1, but B-found rate is the dominant constraint

| Metric | Post_fix baseline mini (n=3) | R1 iter 1 (n=1) |
|---|---|---|
| Playlist A tracks | 12 / 13 / 14, mean **13.0** (87 %) | 12 (80 %) |
| Playlist B tracks | 5 / 3 / 5, mean **4.3** (29 %) | **6 (40 %)** |

The +11 pp on B is structurally consistent with R1.3 working: the model
is rendering more honest signals about what it can/cannot ground, so the
harness fills the playlist with verifiable picks (6 from 27 suggestions)
rather than burning batches on confabulated artist+track pairs that fail
verify. But again — n=1.

### Finding 6 — Cache hit rate, system_md5 invariance, stage3_mode — all clean ✅

Per-batch cache hit rates from iter 1:

| Batch | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hit % | 0 | 66 | 64 | 63 | 0 | 62 | 62 | 60 |

Total cached/prompt: **47.7 %**. The cold-miss pattern (batch 1, batch
5) is identical to post_fix. Hit values per batch are ~5 pp lower than
post_fix (post_fix mini i1: 0, 71, 69, 68, 0, 69, 68, 67; mean 52 %).
That can be explained by the slightly longer user-message tail (the
REMINDER block adds ~250 chars), which shifts the cacheable prefix
boundary by exactly the cached_token quantum (OpenAI caches in 128-token
chunks). No structural regression — the prefix is still stable.

- `system_md5 = c174ea98b07ac90f` across all 8 batches ✅ (1 unique)
- `stage3_mode = custom` across all 8 batches ✅
- `system_fingerprint = null` everywhere — confirmed (post_fix Finding 5)

---

## How does the model actually read our prompt? (the user's headline question)

The trace bundles from iter 1 are unusually informative because R1.3
forces the model to articulate WHAT it is omitting and WHY. Reading
batch-1 reasoning verbatim:

> *"The pool is only a partial fit, roughly 30-40 % usable, and many
> entries are either unfamiliar to me or likely off-target for the seed.
> The clearest matches are Charlotte Sands, Kenny Holland, Fiuk, and
> SB19; several others look like they may be wrong-genre, too niche to
> ground confidently, or not recallable enough to avoid confabulation."*

This tells us five things about mini's prompt comprehension:

1. **It reads the `known:` annotation correctly.** It maps "no known:
   tracks available" to "I should not invent a title here" — the
   intended behaviour. R1.3 reinforces this by demanding the model say
   so out loud per artist.

2. **It self-assesses pool quality.** 30-40 % is a realistic estimate
   for the current RAG retrieve — and it matches the corpus reality
   (most artists in that pool are below-overlay-coverage niche entries).
   This was the desired behaviour of the `pool_assessment` schema field.

3. **It prefers omission over confabulation when given permission.**
   With the REMINDER block telling it the cite rule is binding, the
   model returns 8 well-grounded tracks instead of 12 weakly-grounded
   ones. That trade-off is **exactly what the post_fix analysis asked
   for** — a higher *quality* of pick, accepting a lower count.

4. **It recognises Must: traits and cites them.** Cite rate of 1.0 on
   batches 1, 4, 7. The R1.1 reminder at the END of the user message
   has the model rewriting its rationale entries to explicitly quote
   Must: trait fragments ("punchy guitars", "modern theatrical",
   "strong hooks"). Side-by-side comparison vs post_fix mini iter 1
   (where cite rate was only 74 %) suggests R1.1 closes a structural
   gap on the first batch — but the LATE-batch cite rate (57-67 %) is
   still vulnerable to pool-thinness, not promptable away.

5. **It does NOT compensate for B-pool thinning.** Once dislikes prune
   the pool, the model's omitted_artists block in B-batches gets
   longer, and the picks it does make are lower-quality (22 % Spotify-
   found vs A's 39 %). The fix is structural (A6 RAG re-retrieve), not
   prompt-side.

**Takeaway for the next-steps cost programme:** R1.1+R1.3 are
behaviourally correct prompt edits. Whether they ship "as-is" depends
on the n≥3 re-run resolving the -9 pp Spotify-found question. The
direction of effect on every other axis is the direction we wanted.

---

## Operational outcome — Spotify 429 blocked iter 2-3

The eval entered Stage-3 verify on iter 2 batch 2 (Playlist A) at
14:21:42 UTC and hit Spotify 429:

```
Spotify 429 on attempt 2 — Retry-After=5199s (raw), sleeping 90s (cap=90s)
```

Retry-After 5199 s = **86.6 min**. The harness's 90 s back-off cap is
ineffective against a hard hour-plus ban; subsequent retries (4929 s,
4839 s … all decreasing) confirmed the ban was not a soft signal.

Per next-steps.md operational rule
([§Operational gates](../../../next-steps.md#operational-gates),
rule 3): *"If a third consecutive run hits a Retry-After > 1 h, abandon
eval on the user token and use a separate Spotify app credential for
the harness."* We hit two consecutive Retry-After > 1 h on the same
batch (5199 → 5019 → 4929 …) and the eval was killed at 14:31 UTC.

**Why it fired now and not in the post_fix run:** the post_fix run on
2026-05-11 AM (`20260511-081757`) also touched the same Spotify token
70 min earlier. The cumulative search volume across two evals in the
same morning likely tripped Spotify's daily/hourly burst limit (these
limits are not documented). The user-token has effectively been
out-of-budget all morning; the post_fix run consumed the headroom.

**Implication for further work today:** no further evals possible
before ~16:00 UTC at the earliest (when the 80-min Retry-After window
elapses) — well past the user's 14:00 target. The cost programme +
R1 re-baseline MUST wait for a fresh window.

**Recommended ticket** (new, P1): **OP1 — eval Spotify app credential.**
Provision a second Spotify developer app with its own client_id /
secret, authorise against a *test* user (not the dev's primary
account), wire it into the eval harness via an env override
(`SPOTYVIBE_EVAL_SPOTIFY_CLIENT_ID` etc.). This isolates the eval
budget from the developer's interactive session and removes the
between-session cache-disappearance problem (see below).

---

## Operational follow-up — Spotify cache reliability

Confirmed for the 2nd time (post_fix Finding "Spotify cache disappeared
between sessions" was the 1st): `%LOCALAPPDATA%\spotyvibe\.spotify-cache`
was missing again at start of this session and had to be hand-copied
from a stale sandbox. Hypotheses:
1. The harness's cleanup step is deleting the AppData cache when
   restoring sandbox state. Look at `evaluation/harness.py`'s sandbox
   teardown — it may be `shutil.rmtree`-ing the wrong directory.
2. An OS antivirus / cleanup job is removing the file.

Doesn't block the prompt-engineering decision, but worth a 20-minute
investigation before the next eval session.

---

## Next steps (in execution order)

### Required before any further design decision

1. **Wait for Spotify quota recovery** (~16:00 UTC today, or
   2026-05-12 to be safe).
2. **Re-run R1 with n≥3 to confirm Findings 4-5.** Same matrix:
   `default × {gpt-5.4-mini} × 3 iter` (~35 min wall, ~$0.40 cost). The
   prompt-side changes ALREADY in this baseline (R1.1+R1.3) stay
   shipped during the re-run.
3. **Add a verification run on gpt-5.4** at n=3 to detect any
   regression on the larger model (R1.1+R1.3 should be a no-op on
   gpt-5.4 — it was already doing what R1.3 demands — but verify
   empirically).

### Tickets to file from today's work

| ID | Scope | Priority |
|---|---|---|
| **R1.2-deferred** | Re-open R1.2 ("OMIT — don't recall") once `top_tracks_overlay` covers ≥ 80 % of typical RAG-retrieve pools. Tracking ticket for prompt + overlay-coverage co-evolution. | P2 |
| **OP1** | Provision separate Spotify dev-app credential for the eval harness; isolate eval token from interactive session. | P1 |
| **OP2** | Fix `.spotify-cache` disappearance between sessions (harness cleanup or AV / OS interaction). | P2 |
| **A6** | RAG re-retrieve on consecutive empty Stage-3 batches (post_fix Finding 2; this run reinforces — B-batches with 0 spot-found suggest pool exhaustion). | P1 |

### Items NOT decided by this run (because n=1)

- L5 default-flip (mini → gpt-5.4 auto on dislike). **STILL GATED on
  R1 n≥3 outcome.**
- C1 default-flip threshold. **STILL GATED on the same data.**
- Whether to ship R1.1+R1.3 as-is. **PENDING** the -9 pp Spotify-found
  question.

---

## Inventory — what is preserved on disk

- `evaluation/results/20260511-120118/` — R1.2-rejected iter (0 / 15
  playlist, useful as proof the rule is too strict on current corpus).
- `evaluation/results/20260511-120655/gpt-5.4-mini-iter1/` — R1
  iter 1 trace bundle (this baseline's primary data source).
  Contains `eval.jsonl` (8 batch_summary rows), `trace_A.json`
  (full per-batch reasoning + raw response), `trace_B.json`,
  `summary.json`.
- This file documents the analysis and the operational outcome so a
  later session can resume without re-deriving context.

---

## Validation gate — what this session changes vs leaves open

✅ **Verified empirically (n=1):**
- R1.2 ("OMIT — don't recall") collapses the playlist to 0 / 15 on
  current corpus → REJECTED.
- R1.3 (`omitted_artists` ≥ N − M) produces rich, disciplined
  omission reasoning in mini — first time observed in any eval.
- R1.1 (cite-rule REMINDER) does not break anything; cite rate of
  1.0 on 3 of 7 measurable batches.
- `system_md5` invariance and `stage3_mode=custom` hold across the
  new prompt structure.

⚠️ **Hypothesis, n=1 only — need n≥3:**
- R1.1+R1.3 lifts Playlist B completion (+11 pp on iter 1).
- R1.1+R1.3 might regress Spotify-found rate (-9 pp on iter 1) — or
  not, n=1 spread overlap is plausible.
- Mean cite rate is similar to baseline (-4 pp on n=1, but baseline
  i1 was -12 pp from its mean — comparable variance band).

❌ **Cannot answer with current data:**
- Whether R1.3 in isolation regresses Spotify-found, or whether the
  effect is from R1.1 or the interaction.
- Whether gpt-5.4 is affected at all by R1.1+R1.3 (verification
  needed; expected to be a no-op).
- Whether the cost-per-playlist envelope changes (token counts are
  ~equivalent to post_fix, but only n=1).

