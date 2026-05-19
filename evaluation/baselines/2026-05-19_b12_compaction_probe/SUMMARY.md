# B-12 facet-scaling probe — first cross-model run (2026-05-19)

**Probe:** `B-12.facet_scaling`
([evaluation/probes/probe_b12_facet_scaling.py](../../probes/probe_b12_facet_scaling.py))
**Battery:** `compaction`
**Hypothesis under test.** As the number of facets in a Stage 3 taste
summary grows from 2 → 20 (must_have + avoid items), the cite-rate of
the load-bearing first must_have ("hooks") degrades. Same approved-pool
(2 artists, each with known: tracks), same schema, same model temp.
Holds everything else constant so any delta is attributable to
facet-count alone.

**Models run (1 iter each, n=1).** gpt-5.4-mini, gpt-5.4,
deepseek/deepseek-v4-flash via OpenRouter.

## Headline results

Cite-rate of the load-bearing first must_have ("hooks") across the
facet-count axis:

| Model | facets_2 | facets_6 | facets_12 | facets_20 | Pattern |
|---|---:|---:|---:|---:|---|
| **gpt-5.4-mini** | 1.00 | 0.50 | 0.20 | 0.25 | -75pp from 2 → 12 |
| **gpt-5.4** | 1.00 | 0.00 | 0.50 | 0.25 | -100pp at 6, partial recovery |
| **deepseek-v4-flash** | 1.00 | 0.33 | 0.25 | 0.25 | -67pp from 2 → 12 |

**All three models show monotonic-ish cite-rate degradation.** At
facets_2 every model nailed it (1.00 cite-rate). By facets_12 every
model dropped to ≤ 0.50, plateauing around 0.20-0.25 at facets_20.

The degradation is **not** about ignoring must_have entirely — picks
arrived and were generally valid. It is specifically about the
load-bearing first must_have ("hooks") being **edged out of attention**
as distractors accumulate, which is the textbook "lost in the middle"
signature (Liu et al. 2024 TACL; Chroma 2025 context-rot).

## Per-model fingerprints

| File | path |
|---|---|
| gpt-5.4-mini | [fingerprint_gpt-5.4-mini.json](fingerprint_gpt-5.4-mini.json) |
| gpt-5.4 | [fingerprint_gpt-5.4.json](fingerprint_gpt-5.4.json) |
| deepseek-v4-flash | [fingerprint_deepseek-v4-flash.json](fingerprint_deepseek-v4-flash.json) |

Per-call `probes.jsonl` traces stay under `evaluation/probes/results/`
(gitignored) since they are reproducible from a re-run.

## Cost & wall

| Model | Tokens in | Tokens out | Wall | Reported cost | Actual cost (corrected rates) |
|---|---:|---:|---:|---:|---:|
| gpt-5.4-mini | 5,780 | 2,250 | 17.8 s | $0.0022 | $0.0022 |
| gpt-5.4 | n/a | n/a | 37.0 s | $0.0414 | $0.0414 |
| deepseek-v4-flash | 5,925 | 9,578 | 95.9 s | $0.1106 ⚠ | ~$0.004 |

**Note on DeepSeek cost.** The probe runner's
`_PRICING_USD_PER_MTOK` dict in
[runner.py](../runner.py) does not include `deepseek/*` rates and
falls back to gpt-4o defaults ($2.50 / $10 per M). Real DeepSeek V4
Flash cost via OpenRouter is $0.14 / $0.28 per M (Galaxy.ai 2026), so
the actual spend was ~$0.004 — about 27× lower than the reported
number. Filed as a probe-runner follow-up: add DeepSeek + cross-model
pricing entries.

## What this validates

1. **Lost-in-the-middle is real on this codebase.** All three production-
   candidate models drop cite-rate by 50-100pp as facets grow — under
   identical grounding (same approved-pool, same `known:` block).
2. **No model is immune.** Even gpt-5.4 (the most expensive, generally
   best on B-pool quality) drops to 0.0 cite-rate on facets_6 then
   only partially recovers at facets_12. Mini and DeepSeek follow a
   smoother but equally steep curve.
3. **The compaction lever
   (`build_focused_taste_summary` + `SPOTYVIBE_FOCUSED_TASTE=1`)
   is worth measuring on a real eval.** B-12 confirms the underlying
   degradation it targets; a follow-up paid eval with `--scenarios
   default,lastfm_tag_weighting --iterations 3` and the env enabled
   would measure end-to-end whether the lever recovers cite-rate.

## Caveats

- **n=1.** B-6 variance work showed `n_required_for_5pp_signal ≥ 5`.
  The *direction* of the cite-rate degradation is reproducible across
  3 models, which buys some confidence, but the absolute numbers
  carry single-iter noise. n=3 confirmation costs ~$0.15.
- **Cite-rate scoring is narrow.** B-12 only counts cites of the
  first must_have item ("hooks"). gpt-5.4's 0.0 on facets_6 may
  reflect cites of *other* must_haves (punchy guitars, theatrical
  vocals) — the model is still doing some profile_match work, just
  not on the specific load-bearing facet. A future B-12 revision
  could score the union over all must_have items; the current
  rubric is the harder constraint and aligned with the lost-in-
  middle hypothesis.
- **Identical pool across variants.** Real production also varies
  pool size (RAG retrieval result) per request. The B-12 fixed pool
  isolates the facet axis; production effects on this axis may
  compound with pool variation.

## Recommended next move (cost-gated)

The compaction-lever validation eval would be:

```bash
# 1 — Re-run B-12 with focused mode enabled to measure recovery.
$env:SPOTYVIBE_FOCUSED_TASTE = "1"
$env:SPOTYVIBE_FOCUSED_TASTE_THRESHOLD = "6"  # activate at facets >= 6
$env:SPOTYVIBE_FOCUSED_TASTE_TOP_K = "3"
python -m evaluation.probes --model gpt-5.4-mini --battery compaction --confirm
# NOTE: B-12 does not currently call build_focused_taste_summary —
# the probe builds messages directly. To test the lever, a new
# B-12.focused variant or end-to-end paid eval is required.
# Easier path: paid run_evaluation.py with the env set + a
# large-facet synthetic scenario (~$0.10).
```

Alternative: file B-12.focused as a follow-up — add a variant that
applies `build_focused_taste_summary` to the same large-facet input
and re-scores. Confirms the lever works without burning a paid eval.
