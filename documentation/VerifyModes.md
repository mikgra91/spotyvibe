# Verify Modes

> **Project priorities (in order):** **1. Quality → 2. Price → 3. Speed.**
>
> "Verify mode" controls how the evaluation harness (and, where applicable, the production pipeline) confirms that a GPT-suggested `(artist, title)` pair refers to a real, playable track before it is added to a playlist. It is **orthogonal to model choice** — see `ModelRecommendations.md` for that axis.

This document records measured behaviour of the three verify modes on the canonical evaluation scenario (`playlist_size=15`, default scenario, 5 iterations × 2 models). Re-run with:

```bash
python -m evaluation.run_evaluation --no-confirm --verify-mode <mode>
```

## TL;DR Recommendation

| Mode | Verdict | When to pick it |
|---|---|---|
| `spotify` | ✅ **Production default** | The only mode whose "found on Spotify" rate corresponds to reality and whose must-have-cite rate is not artificially inflated. Use for all user-facing runs and for any evaluation gating quality. |
| `l0_l1` | ❌ **Not recommended (experiment, parked)** | MusicBrainz pre-filter ahead of Spotify. Improves Spotify-found rate by +6.5 pp and shaves ~24 s wall-clock, **but regresses must-have-cite by −1.7 pp** vs `spotify`. Blocked by the "no regression — ever" rule (`AGENTS.md`). |
| `null` | ✅ **Dev / unit-test only** | No real verification — every suggestion is accepted. Useful for pipeline-shape tests where Spotify availability is irrelevant. Numbers are not comparable to the other modes (Spotify-found is fake 100 %, completion is artificially 15/15). **Never use as a quality baseline.** |

## Measured baseline — step 7 (2026-05-13)

Source dirs (5 iters × {gpt-5.4, gpt-5.4-mini} per mode):

- `null` → `evaluation/results/20260513-081434/`
- `spotify` → `evaluation/results/20260513-090518/`
- `l0_l1` → `evaluation/results/20260513-110357/`

Means across 5 iterations of the `default` scenario:

| Mode | Model | Tracks A (mean) | Completion ≥15 | Spotify-found | **Must-have-cite** | Cost $ | Wall s |
|---|---|---:|---:|---:|---:|---:|---:|
| null | gpt-5.4 | 15.0 | 5/5 ok | 100 %* | 83.9 % | $0.207 | 33.5 |
| null | gpt-5.4-mini | 14.8 | 4/5 ok | 100 %* | 88.3 % | $0.064 | 36.0 |
| spotify | gpt-5.4 | 13.0 | 1/5 ok | 31.7 % | 86.4 % | $0.272 | 69.2 |
| spotify | gpt-5.4-mini | 9.6 | 0/5 ok | 30.1 % | 80.4 % | $0.082 | 58.2 |
| **l0_l1** | gpt-5.4 | 10.4 | 0/5 ok | 38.5 % | 89.5 % | $0.259 | 37.6 |
| **l0_l1** | gpt-5.4-mini | 12.4 | 1/5 ok | 37.7 % | 74.0 % | $0.088 | 52.5 |

\* `null` Spotify-found is a tautology (no check performed); it is **not** a real-world metric and should never be cited as evidence of quality.

### Headline deltas (l0_l1 vs spotify, both models pooled)

| Metric | spotify | l0_l1 | Δ |
|---|---:|---:|---:|
| Spotify-found | 31.2 % | **37.7 %** | **+6.5 pp** ✅ |
| Must-have-cite | 83.4 % | 81.7 % | **−1.7 pp** ❌ |
| Cost (gpt-5.4) | $0.272 | $0.259 | −5 % ✅ |
| Cost (gpt-5.4-mini) | $0.082 | $0.088 | +7 % ❌ |
| Wall time | 64 s | 45 s | −30 % ✅ |
| Completion ≥15 | 1/10 | 1/10 | 0 ➖ |
| Leakage | pass | pass | 0 ➖ |
| Fit-check (decade) | pass | pass | 0 ➖ |

## Why `l0_l1` is parked, not shipped

1. **Must-have-cite regressed by 1.7 pp.** `AGENTS.md` is explicit: *"No regression — ever. … If a change improves cost/speed but regresses quality on any model, it does not ship. Quality always wins ties."* Must-have-cite is the canonical quality metric. One regression is enough to block promotion.
2. **The +6.5 pp Spotify-found gain is smaller than hoped.** MusicBrainz still admits "ghost" tracks — entries MB knows but Spotify does not. Examples seen in the run log: *daniela pes — furore*, *fancy hagood — goodbye sunshine*, *cecco e cipo — vita da bar*. MB returns HTTP 200 with a recording, Spotify returns no match. The L0 filter therefore does *not* fully shield Stage 3 from un-verifiable proposals.
3. **The quality regression is structural, not random.** MB returns 0 hits for canonical-but-niche titles (regional spellings, parenthetical suffixes, remix indicators). Some of those would have been cite-worthy under pure-Spotify mode; the L0 gate removes them before Stage 3 ever sees them, so the model substitutes weaker picks.
4. **Cost is a wash.** Cheaper on `gpt-5.4` (−5 %), more expensive on `gpt-5.4-mini` (+7 %). No clear price win to offset the quality loss.

## What to fix next (instead of changing the verify mode)

Completion is the dominant failure across both real-verify modes: only **1/10** iterations reach the 15-track target. The terminal event is almost always *"Reached GPT call limit (4). Stopping with N verified track(s)."* This is upstream of the verify mode and unaffected by swapping `spotify` ↔ `l0_l1`.

Two targeted experiments worth running before any further verify-mode work:

1. **Conditional batch-budget bump** — raise the per-playlist Stage-3 cap from 4 → 6, *only when verified < 60 % of target after batch 3*. Expected cost impact: 1–2 extra Stage-3 calls on the runs that currently fail completion (~$0.05 on `gpt-5.4`, ~$0.018 on `gpt-5.4-mini`), with no impact on already-completing runs.
2. **Adaptive ask size** — when a batch's Spotify-found rate drops below 40 %, request `ceil(remaining / 0.4)` instead of `remaining` in the next batch. Partially exists via the bad-pool retry, but the trigger threshold may be too lax.

If `l0_l1` is revisited later, tighten the MB gate (require non-empty `lastfm_tags` or an attached `release-id`, not just a recording hit) to filter out the ghost-track class above, and re-evaluate with **non-regression required on every metric including must-have-cite** before considering promotion.

## How to reproduce

```bash
# Default (recommended)
python -m evaluation.run_evaluation --no-confirm --verify-mode spotify

# L0+L1 experiment (parked)
python -m evaluation.run_evaluation --no-confirm --verify-mode l0_l1

# Null (dev/test only)
python -m evaluation.run_evaluation --no-confirm --verify-mode null
```

Result directories land in `evaluation/results/<YYYYMMDD-HHMMSS>/`; the headline tables in this document come from each run's `comparison.md`.

