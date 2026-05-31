# Benchmark — production-readiness for a model

A focused benchmark suite that answers ONE question:

> **Is this model good enough to ship?**

Designed after the 2026-05-22 production incident where the eval
harness reported the active model as healthy while the user's real
profile collapsed to 4 / 30 tracks. The benchmark closes that gap.

## TL;DR

```bash
# Change the model in evaluation/settings.ini OR pass --model.
python -m evaluation.benchmark --model anthropic/claude-haiku-4.5
```

You get a one-screen scorecard with a verdict:

- `PRODUCTION_READY` (exit 0) — ship it.
- `DEGRADED` (exit 0) — shippable with caveats; read the hints.
- `NOT_PRODUCTION_READY` (exit 1) — do not default users to this model.

Cost: ~$0.05–$0.20 per benchmark depending on model. Wall time:
~15–25 minutes (Spotify rate-limit cooldowns dominate).

> **⚠️ Spotify rate-limit protection.** Each benchmark fires ~360-720
> Spotify search calls. Running multiple back-to-back can trigger a
> hard 429 block (Retry-After up to 3 hours) that locks YOUR account
> out of Spotify, not just the benchmark.
>
> Three layers of defence are now built in:
> 1. **Pre-flight check** — a single test search runs before any quota
>    is spent. If the account is already 429-blocked, the benchmark
>    aborts with a clear `Retry-After` reading.
> 2. **Persistent inter-benchmark cooldown** — every Spotify-heavy
>    benchmark records its end timestamp to
>    `evaluation/.benchmark_state.json`. The next benchmark refuses to
>    start until 12 minutes have elapsed, giving the rolling-window
>    quota time to drain. Override with `--reset-spotify-cooldown`
>    only if you waited manually.
> 3. **Mid-run abort** — if a scenario's verified count collapses to
>    0-2 AND the Spotify-found rate is < 30 %, a 429 pre-flight fires.
>    On confirmation, the remaining scenarios are marked SKIPPED
>    instead of churning through the block.

## What it measures

Six scenarios spanning the real production failure axes:

| Scenario | What it stresses | Why it exists |
|---|---|---|
| `broad_mainstream_clean` | Baseline. Big approved pool, easy wins. | Failure here = system-wide bug, not a model issue. |
| `niche_japanese_clean` | Narrow language / regional constraint. | Tests Stage 1 retrieval depth on niche genres. |
| `aged_japanese_session5` | **THE PRODUCTION FAILURE** — niche profile after 4 prior sessions. | Reproduces the 4/30 user-reported collapse. Regression test for the Q1/Q2/Q3 fixes (2026-05-23). |
| `aged_mainstream_session5` | Broad profile after 4 prior sessions. | Control: if THIS fails too, the dedup logic is broken across the board. |
| `contradictory_facets` | Must-have items that conflict (lo-fi + polished). | Tests graceful degradation vs. garbage output. |
| `post_dislike_regression` | Generate → dislike → regenerate. | Anti-leakage: disliked tracks/artists must NOT re-appear. |

Each scenario carries a **hard gate** with explicit thresholds:

| Sub-gate | Default threshold | Meaning |
|---|---|---|
| `min_verified_count` | 21–27 / 30 (scenario-specific) | Playlist must fill. Single most user-visible metric. |
| `min_spotify_found_rate` | 0.40–0.70 | Stage 3 picks must resolve on Spotify. Catches the Spotify-cascade failure. |
| `max_leakage_count` | **0** (always) | Disliked tracks / rejected artists must NOT re-appear in playlist B. Non-negotiable. |
| `min_unique_artist_count` | 10–18 | Diversity floor. Catches the Stage-3-recycles-6-artists anti-pattern. |
| `max_wall_seconds` | 180–300 | Soft cap. Breach → WARN, not FAIL. |
| `max_cost_usd` | $0.10–$0.15 | Soft cap. Breach → WARN, not FAIL. |

Sub-gates are HARD (`FAIL` on breach) for verified-count, found-rate, and
leakage; SOFT (`WARN`) for diversity, wall, and cost.

## The scorecard

```
================================================================================================
SpotyVibe Benchmark - anthropic/claude-haiku-4.5
Started: 2026-05-23T20:15:00+00:00    Finished: 2026-05-23T20:34:22+00:00
================================================================================================

  SCENARIO                          VERDICT  SCORE     FILL    FOUND  LEAK  UNIQ
  ----------------------------------------------------------------------------------------------
  broad_mainstream_clean            [PASS]      95    30/30      92%     0    19
  niche_japanese_clean              [FAIL]      35    11/24      31%     0     8
  aged_japanese_session5            [FAIL]       8     3/21      12%     0     4
  aged_mainstream_session5          [PASS]      90    27/25      75%     0    18
  contradictory_facets              [PASS]      80    21/18      62%     0    12
  post_dislike_regression           [PASS]      88    26/24      71%     0    16

  PASS: 4   WARN: 0   FAIL: 2   SKIP: 0
  AVG SCORE: 65.0 / 100
  COST:      $0.082
  WALL:      19m

  VERDICT: NOT_PRODUCTION_READY

  SCENARIO HINTS
  ----------------------------------------------------------------------------------------------
  [FAIL] niche_japanese_clean
      Verified 11/24 (short by 54%). Likely causes: pool starvation, Spotify
      cascade, or model refusal. Inspect trace_a `run_batches[*].outcome`.
      Spotify-found rate 31% < 50% threshold. Stage 3 is picking tracks
      Spotify cannot resolve. Check Q2 overlay pruning + corpus `top_tracks`
      coverage.

  [FAIL] aged_japanese_session5
      Verified 3/21 (short by 86%). Likely causes: pool starvation, Spotify
      cascade, or model refusal. Inspect trace_a `run_batches[*].outcome`.
      Spotify-found rate 12% < 40% threshold. Stage 3 is picking tracks
      Spotify cannot resolve. Check Q2 overlay pruning + corpus `top_tracks`
      coverage.

  CROSS-SCENARIO DIAGNOSES
  ----------------------------------------------------------------------------------------------
    Niche-genre scenarios FAIL while mainstream PASSes. Likely a
    corpus-coverage gap (Stage 1 retrieval is fine on broad pools but thin
    on niche). Try: expand the corpus's `top_tracks` coverage on
    niche-language artists, or relax the must_have_tags filter on
    re-retrieve.
================================================================================================
```

Key parts:

- **Per-scenario row**: verdict, score (0–100), fill (`verified/target`),
  found rate, leakage count, unique artists.
- **Scenario hints**: per-failed-gate explanation + where to look.
- **Cross-scenario diagnoses**: PATTERN detection across scenarios
  (e.g. niche fails + mainstream passes ⇒ corpus issue, not model).

## CLI reference

```bash
# Full benchmark, default 6 scenarios, single model
python -m evaluation.benchmark --model <model>

# Subset of scenarios (faster iteration during a fix)
python -m evaluation.benchmark --model X \
    --scenarios broad_mainstream_clean,aged_japanese_session5

# Print plan only, burn no quota
python -m evaluation.benchmark --model X --dry-run

# CI-friendly (no interactive prompt)
python -m evaluation.benchmark --model X --no-confirm

# Inspect what's available
python -m evaluation.benchmark --list-scenarios
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | `PRODUCTION_READY` or `DEGRADED` — safe to merge / deploy |
| 1 | `NOT_PRODUCTION_READY` — at least one FAIL, do not default users |
| 2 | Configuration error (missing `evaluation/settings.ini`, unknown scenario) |
| 130 | Ctrl+C |

## Adding a scenario

1. Pick or create a harness scenario in
   [`evaluation/scenario.py`](../evaluation/scenario.py) (the harness's
   open-ended registry of seed-prose + feedback rule).
2. If the scenario needs an aged-state fixture, drop a profile JSON in
   [`evaluation/seed_profiles/`](../evaluation/seed_profiles/) shaped
   like the existing ones (preferences + artists + history +
   feedback).
3. Add a `BenchmarkScenario` entry in
   [`evaluation/benchmark/scenarios.py`](../evaluation/benchmark/scenarios.py)
   that pairs the harness scenario with explicit gate thresholds.
4. Update the **coverage matrix** docstring at the top of `scenarios.py`.
5. Add a row to the coverage table in this file.

## Choosing gate thresholds

Don't pull numbers from nowhere. Each threshold should be backed by:

- **A trace bundle** that documents the failure shape we're guarding
  against (e.g. "production trace 435c7016 showed 4 / 30, so 21 / 30 is
  the floor we accept post-fix").
- **A clear blast radius statement** in the scenario's `description`
  (e.g. "control variant of X: if THIS fails too, the bug is broader
  than niche").

Avoid "feels about right" thresholds. They drift, they don't survive
the next post-mortem, and they erode trust in the benchmark.

## When the benchmark says "PRODUCTION_READY" but the user still
complains

The benchmark covers the failure axes we KNOW about. It does NOT
substitute for the manual `testcase.md` flow (the user runs the new
profile in the real app, captures the trace, we analyse). Treat them
as complementary:

- **Benchmark** → automated, catches REGRESSIONS we've codified.
- **Manual testcase** → human-in-the-loop, catches NEW failure modes
  the benchmark hasn't been taught about.

When a manual testcase exposes a new failure mode, the loop closes by:

1. Capturing the production-trace receipts.
2. Adding the failure as a NEW benchmark scenario (with a gate that
   the model fails on the receipt and passes after the fix).
3. Re-running the benchmark to confirm the FAIL flips to PASS.

That is the only durable path. A model that "passes the benchmark" is
guaranteed to dodge the failure modes the benchmark encodes. Anything
beyond that is the next test we have to add.

## Relationship to the open-ended harness

The benchmark **wraps** `evaluation/harness.py`. It does not duplicate
any execution code — every benchmark run goes through `run_for_model`,
gets the same sandbox / verifier / trace / leakage / fit-check
machinery, and writes per-run `eval.jsonl` + `summary.json` to the
benchmark results dir.

The differences are at the **interface** layer:

| Aspect | Open-ended harness | Benchmark |
|---|---|---|
| Audience | Researchers / probe authors | Anyone evaluating a model |
| Output | `comparison.md` (detailed) | `scorecard.md` (verdict) |
| Pass/fail | Reports + you decide | Hard gates + exit code |
| Scope | All scenarios + models matrix | One model × 6 scenarios |
| Cost | $0.10–$0.74 per matrix | $0.05–$0.20 per model |
| Use when | Investigating a prompt change | Deciding whether to ship a model |

Both live next to each other in `evaluation/`; pick the right one for
the question you're asking.
