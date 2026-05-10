# Validation run — 2026-05-10 (Option A — partial, INVALID for cross-model comparison)

**Generated:** 2026-05-10. Per-iter `summary.json` artefacts were
removed after the analysis; the source raw files remain in
`evaluation/results/20260510-134821/` if a deeper re-analysis is ever
needed.

> **🚨 KNOWN INVALID — Tier-0 post-mortem 2026-05-10:** every iter in
> this run executed `gpt-5.4-mini` regardless of the `models =` setting
> in `evaluation/settings.ini`. Root cause: the harness's
> `os.environ.setdefault("STAGE3_MODE", "custom")` no-oped because
> `config.ensure_env()` had already loaded the user's pinned
> `STAGE3_MODE='fast'` from `settings.conf`, and the L5 selector
> ignores `OPENAI_MODEL` under `fast`. **Cross-model rows in this
> report (gpt-5.4 vs mini) are mini-vs-mini comparisons.** Mini-only
> aggregates (n=6) remain trustworthy. Fixed in
> [run_evaluation.py:411](evaluation/run_evaluation.py#L411) —
> `setdefault` replaced with explicit assign on the same date.

**Run:** `evaluation/results/20260510-134821/`. Killed mid-niche-iter-2
when the Spotify access token expired (~1.5 h into the run, 1 h TTL).
7 of 12 planned iterations landed cleanly.

**Scope (planned vs actual):** 2 models × 2 scenarios × 3 iter ⇒ 12.
Salvageable: 6 default + 1 niche · gpt-5.4 iter 1.

## Default scenario — Playlist A (generation)

| Model | iter 1 | iter 2 | iter 3 | Mean | B1 mean | Δ |
|---|---:|---:|---:|---:|---:|---|
| gpt-5.4 | 15 | 8 | 10 | **11.0** | 11.0 | 0 |
| gpt-5.4-mini | 15 | 14 | 12 | **13.7** | 14.3 | -0.6 |

**No regression introduced by C1-C4.** Validation reproduces B1's
mean within iteration variance for both models. mini still wins
default Playlist A; gpt-5.4 still under-performs there.

## Default scenario — Playlist B (post-feedback)

| Model | iter 1 | iter 2 | iter 3 | Mean | B1 mean |
|---|---:|---:|---:|---:|---:|
| gpt-5.4 | 3 | 7 | 4 | **4.7** | 8.3 |
| gpt-5.4-mini | 1 | 7 | 11 | **6.3** | 3.7 |

**Surprising flip on Playlist B.** B1 had gpt-5.4 winning B clearly
(8.3 vs 3.7 mini). Validation shows mini ahead (6.3 vs 4.7) — but
both means moved a lot vs B1, suggesting the metric is dominated by
single-run variance at n=3. This **reopens the L5 design question:**
is the mini-collapse-on-Playlist-B effect from B1 reproducible at
all? A focused B-only re-run with n≥5 would settle it.

## Quality gates (all 6 default runs)

- **Leakage:** pass × 6/6
- **Fit:** pass × 6/6 (no decade-avoid violations)

C1-C4 introduced **no quality regression** on the default scenario.

## niche_only_strict (1 of 6 iters; rest blocked by token expiry)

- gpt-5.4 iter 1: 5 / 15 tracks (under), 196.3 s. p95 listeners
  data not analysed in this report — single iter is below useful
  variance threshold.
- Remaining 2 gpt-5.4 iters + all 3 mini iters: not run.

The A3 niche-bias open question is **still open**. Need a follow-up
run after a fresh Spotify auth.

## C4 cache-routing verification — `cached_tokens` hit rate

Per-Stage 3 batch hit-rate (cached_tokens / prompt_tokens × 100):

| Run | Hit-rates | Hits / batches |
|---|---|---:|
| gpt-5.4 iter 1 | 0, 0, 0, 0, 72.8, 69.3, 67.3 | 3 / 7 |
| gpt-5.4 iter 2 | 0, 73.5, 0, 0, 0, 0, 69.6, 0 | 2 / 8 |
| gpt-5.4 iter 3 | 0, 72.1, 72.1, 0, 0, 67.8, 67.3, 65.1 | 5 / 8 |
| gpt-5.4-mini iter 1 | 0, 71.5, 0, 0, 68.1, 0, 66.4 | 3 / 7 |
| gpt-5.4-mini iter 2 | 0, 67.9, 0, 65.0, 0, 67.0, 0, 0 | 3 / 8 |
| gpt-5.4-mini iter 3 | 0, 0, 0, 0, 0, 67.8, 0, 0 | 1 / 8 |

**B1 baseline for comparison:**
- gpt-5.4 iter 2: `[0, 0, 0, 0, 0, 71.9, 71.3, 0]` — 2 / 8
- gpt-5.4-mini iter 2: `[0, 76.7, 0, 0, 0, 68.6, 0]` — 2 / 7

**Verdict on C4: inconclusive.** Hit rates *when they land* are
unchanged (65-77% in both runs). Frequency of hits is *slightly*
higher on average (3.0 / 8 batches in validation vs 2.5 / 8 in
B1), but the variance is huge — gpt-5.4 iter 3 hit 5/8 while mini
iter 3 hit only 1/8 in the same eval session. The `prompt_cache_key`
field reaches OpenAI (gating by `_is_openai_provider()` confirmed),
but its actual effect on routing is hard to measure at n=6 runs.
**Next data point would need either:** (a) ≥ 20 runs to smooth
variance, or (b) a controlled A/B with the key explicitly disabled
in some runs.

## Operational notes

- **Spotify token TTL = 1 hour.** Eval started 15:48, crashed
  17:16 = 88 min in. Refresh-token flow in `.spotify-cache` did
  not auto-refresh — likely because the eval-side spotipy client
  doesn't share cache state with the live app's refresh path.
  See [follow-up below](#follow-up).
- **Cooldown stack worked.** No 429s in the 7 successful iters
  (one of B1's main failure modes did not recur).

## Follow-up

1. **Spotify auth refresh in eval.** The harness should either
   (a) refresh the access token once before the run starts, OR
   (b) detect token expiry mid-run and auto-refresh via the
   stored refresh_token. Without this, any eval longer than ~50
   min crashes. File as bug.
2. **niche_only_strict + mini coverage.** Run a focused 1-scenario,
   2-model, 3-iter follow-up after a fresh `python app.py` auth.
   ~45 min wall. The remaining open question from this run.
3. **R1 prep.** With C4's marginal effect confirmed, R1's
   prompt-engineering directions become higher-priority for the
   "make mini hold up at depth" goal. The B-playlist mini collapse
   (B1's load-bearing observation) is also less certain after
   today's variance — R1's first task should re-establish it.
