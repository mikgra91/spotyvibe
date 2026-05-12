# R1 full re-baseline — 2026-05-12 (n=3 each model + revert validation)

**Two evals this session:**
1. `evaluation/results/20260512-052919/` — gpt-5.4-mini × 3, gpt-5.4 × 3
   with **R1.1 + R1.3-strict** in place (forced `omitted_artists ≥ N−M`).
2. `evaluation/results/20260512-063412/` — gpt-5.4-mini × 3 with
   **R1.1 + R1.3-softened** (transparency hint, no quota).

Combined wall: ~2 h. Combined OpenAI cost: ~$1.10.

## TL;DR

- **R1.3-strict is REJECTED.** Forcing `omitted_artists ≥ N−M` collapsed
  mini Playlist A from 13.0 to 8.0 (-38%) and produced **2 of 3 EMPTY
  Playlist B** for gpt-5.4 (unprecedented in any prior baseline).
- **R1.3 softened to a transparency hint** (no quota, prompt explicitly
  prefers FILLING the QUOTA over inflating the omission list).
- **R1.1 (cite REMINDER at end of user message) is kept.** Cite-rate
  parity with baseline (81.5 % vs 86 %, within iteration variance).
- **R1-softened recovers to baseline** at n=3 mini and lands a first-ever
  15 / 15 perfect playlist on iter 3.
- **Pre-existing bug fixed:** the R1.1 commit added `{min_new_artists}`
  to `prompts/track_select_user.txt` line 7 but the `.format()` call in
  `core/src/suggestions.py` did not pass it → `KeyError` on every Stage-3
  call after the commit. Caught on first iter of run #1 and fixed before
  the rest of the eval ran. The 2026-05-11 partial run never hit this
  because it used the working tree before the prompt was committed.

## Run #1 — R1.3-strict (REJECTED)

`evaluation/results/20260512-052919/comparison.md`

### gpt-5.4-mini × 3

| Iter | Tracks A | Tracks B | Cite | Spot found | Cost |
|---|---:|---:|---:|---:|---:|
| 1 | 12 | 5 | 82.1 % | 43.6 % | $0.0952 |
| 2 |  6 | 1 | 85.7 % | 25.0 % | $0.0809 |
| 3 |  6 | 3 | 88.9 % | 33.3 % | $0.0860 |
| **mean** | **8.0** | **3.0** | **85.6 %** | **34.0 %** | **$0.087** |

### gpt-5.4 × 3

| Iter | Tracks A | Tracks B | Cite | Spot found | Cost |
|---|---:|---:|---:|---:|---:|
| 1 | 13 | **0 (EMPTY)** | 81.5 % | 48.1 % | $0.227 |
| 2 | 10 | **0 (EMPTY)** | 81.8 % | 45.5 % | $0.2508 |
| 3 | 12 | 4 | 97.1 % | 47.1 % | $0.293 |
| **mean** | **11.7** | **1.3** | **86.8 %** | **46.9 %** | **$0.257** |

### Δ vs `2026-05-11_post_fix_validation` baseline (mini n=3)

| Metric | Baseline | R1.3-strict | Δ |
|---|---:|---:|---:|
| Playlist A | 13.0 | 8.0 | **−38 %** ⚠️ |
| Playlist B | 4.3 | 3.0 | **−30 %** ⚠️ |
| Cite | 86 % | 85.6 % | ≈ |
| Spotify-found | 40 % | 34 % | **−6 pp** ⚠️ |
| Cost | ~$0.06 | $0.087 | +45 % |

**Cause:** the model treated the `omitted_artists ≥ N−M` rule as a
binding output constraint and prioritised satisfying it over filling
the QUOTA. Trace bundles for mini iter 2-3 show 28-30 entries in
`omitted_artists` but only 6 picks in `playlist`. For gpt-5.4 the
Playlist-B pool is structurally thinner (post-feedback prune); under
the strict rule the model chose to omit ALL artists rather than risk a
weak ground, returning an empty playlist.

## Run #2 — R1.3-softened (SHIPPED)

`evaluation/results/20260512-063412/comparison.md`

R1.3 prompt rewritten ([`prompts/track_select_system.txt:37`](../../../prompts/track_select_system.txt#L37)):

> `omitted_artists` SHOULD list any APPROVED_ARTISTS you intentionally
> skipped, with a concrete reason ("no known: examples", "wrong genre:
> <X>", "doesn't match Must: <trait>"). It is an aid for transparency,
> not a quota — do NOT pad it, and do NOT omit artists merely to
> satisfy it. Prefer FILLING the playlist to the QUOTA over inflating
> `omitted_artists`.

### gpt-5.4-mini × 3 (validation)

| Iter | Tracks A | Tracks B | Cite | Spot found | Cost |
|---|---:|---:|---:|---:|---:|
| 1 | 11 | 2 | 88.0 % | 26.0 % | $0.0820 |
| 2 | 10 | 2 | 75.9 % | 41.4 % | $0.0772 |
| 3 | **15 ✅** | 7 | 80.5 % | 53.7 % | $0.0807 |
| **mean** | **12.0** | **3.7** | **81.5 %** | **40.4 %** | **$0.080** |

### Δ vs post_fix baseline

| Metric | Baseline | R1-softened | Δ |
|---|---:|---:|---:|
| Playlist A | 13.0 | 12.0 | −7 % (within variance) |
| Playlist B | 4.3 | 3.7 | −14 % (within variance) |
| Cite | 86 % | 81.5 % | −4.5 pp |
| Spotify-found | 40 % | 40.4 % | ≈ ✅ |
| Cost | ~$0.06 | $0.080 | +33 % |

The +33 % cost is the price of the longer system prompt (REMINDER
block + the softened transparency text). All quality metrics are
inside the post_fix variance band. Iter 3 hit the first **15/15
perfect playlist** for mini ever logged on `default`.

## What we learned about model prompt-comprehension

Comparing trace bundles across the two runs gives the cleanest
side-by-side data we have on how mini interprets a "MUST" word
in a system prompt:

1. **"MUST contain (N − M) entries" is treated as a binding output
   shape, not a hint.** Mini will collapse the playlist to whatever
   number lets the omission list satisfy the rule. R1.3-strict did
   not just *encourage* discrimination — it *forced* it past the
   point of usefulness.

2. **"SHOULD … prefer FILLING the QUOTA" is treated as a soft
   priority.** Mini reads "prefer X over Y" as a tiebreaker, not a
   ban. The omission list is still rich (~10-15 entries per batch in
   the softened run) but the playlist is filled.

3. **REMINDER blocks at the end of the user message DO work for
   structural rules** (cite-rate parity in both runs, 88 % on iter 1
   of the softened run is the highest first-batch cite logged for
   mini). They do NOT save you when the rule is over-constrained
   relative to the candidate pool — that's a Stage-1 problem, not a
   Stage-3 problem.

4. **gpt-5.4 is more brittle to over-constraint than mini.** The
   strict R1.3 produced 2 of 3 EMPTY Playlist B for gpt-5.4 (it would
   rather skip the playlist entirely than partially fill); mini at
   least returned 1-3 tracks. This contradicts the post_fix
   prediction that "R1.3 is a no-op on gpt-5.4 because it's already
   doing what R1.3 demands".

5. **The dominant Playlist-B failure mode is still pool starvation,
   not prompt comprehension.** Both runs show B-completion ~3-4
   tracks regardless of prompt strictness. The structural fix
   remains **A6 — RAG re-retrieve on consecutive empty Stage-3
   batches** (post_fix Finding 2; this session reinforces).

## Operational notes

- Spotify cache survived the 2026-05-11 → 2026-05-12 boundary this
  time (perhaps OP2 just wasn't a real bug, or the user moved a fresh
  cache in). Keep monitoring.
- No 429s this session despite 7 sequential evals × 3-4 verify calls
  per iter. The 600 s inter-iter cooldown (commit c18a98f) is doing
  its job.
- Eval wall: ~30 min for mini × 3, ~80 min for mini × 3 + gpt-5.4 × 3.
  The R1 partial's 2-evals-per-day ceiling does **not** appear today;
  OP1 (separate eval app) is still nice-to-have but not P1.

## Decisions

- ✅ **Ship:** R1.1 (cite REMINDER) + R1.3-softened.
- ❌ **Reject:** R1.3-strict. The "MUST contain (N − M) entries"
  formulation is harmful at all model sizes.
- 🔄 **Re-open:** R1.2 stays deferred (waits on top_tracks_overlay
  coverage expansion).

## Next-session priorities

1. **A6 — RAG re-retrieve on consecutive empty Stage-3 batches.**
   This is now the dominant lever for B-completion on both models.
2. **Verify R1-softened on gpt-5.4 at n=3.** This session only
   validated mini. Expected outcome: gpt-5.4 returns to baseline
   Playlist B (≥ 3 / 15) and stops producing empty-B iters.
3. **Investigate cite-rate −4.5 pp on softened run.** The REMINDER
   is in place; the cite drop may be coming from interaction with
   the softened R1.3 (less rationale token budget left after a
   shorter playlist forces more retries). n=6 should disambiguate.
4. **Cost-per-playlist budget review.** R1.1+R1.3-softened is +33 %
   over post_fix on mini. If A6 lands and recovers B-completion,
   measure whether the QUOTA-fill behaviour also drops the per-iter
   batch retry count back toward post_fix levels.

