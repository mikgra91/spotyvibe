# Cross-model confirmation: gpt-5.4-mini on 2026-05-19 corpus

**Date:** 2026-05-20
**Model:** openai/gpt-5.4-mini (via OpenRouter)
**Corpus:** 2026-05-19 rebuild (175,578 artists, 83.4% with top_tracks)
**Verify mode:** l0_l1 (Overlay → MusicBrainz → Last.fm)
**Scope:** 2 scenarios × 1 iter × 1 model

## Purpose

Confirm that the corpus-rebuild lift observed on DeepSeek V4 Flash
(2026-05-19 baseline) is corpus-side, not model-specific. If gpt-5.4-mini
also lands ≥ 90% found rate on `lastfm_tag_weighting`, A4 is fully closed.

## Headline results

| Metric | default | lastfm_tag_weighting |
|---|---:|---:|
| Playlist A/B tracks | 15/15 + 15/15 | 15/15 + 15/15 |
| Spotify-found (l0_l1) | **100.0%** | **100.0%** |
| Must-have cite rate | 86.7% | 50.0% |
| Leakage | 0 | 0 |
| Fit-check | pass | no_checks_applied |
| Last.fm coverage | 100% | 100% |
| Wall time / scenario | 20.6s | 18.7s |
| Stage 2 approval | 39/40 | 21/21 |

## Comparison with DeepSeek V4 Flash baseline (2026-05-19)

| Metric | gpt-5.4-mini (today) | DeepSeek V4 Flash (05-19) | Historical E7 (05-08) |
|---|---:|---:|---:|
| default found rate | 100.0% (l0_l1) | 96.8% (spotify) | varies |
| lastfm found rate | **100.0%** (l0_l1) | **93.8%** (spotify) | **7-27%** |
| default cite rate | 86.7% | — | — |
| lastfm cite rate | 50.0% | 65.6% | — |
| Cost / playlist | ~$0.002 (OR) | $0.005-0.007 | $0.04-0.15 |

## Verdict

**A4 — Spotify-resolvability collapse on `lastfm_tag_weighting` → FULLY CLOSED.**

Both gpt-5.4-mini and DeepSeek V4 Flash hit ≥ 93% found rate on the
`lastfm_tag_weighting` scenario. The +66–93 pp absolute lift vs historical
E7 numbers is corpus-driven, not model-specific.

## B-12 compaction battery (same session)

Cross-model `facets_20_focused` variant added to the B-12 probe:

| Model | facets_2 | facets_6 | facets_12 | facets_20 | facets_20_focused |
|---|---:|---:|---:|---:|---:|
| gpt-5.4-mini | 1.00 | 0.25 | 0.25 | 0.50 | 0.25 |
| gpt-5.4 | 1.00 | 0.25 | 0.00 | 0.25 | 0.25 |
| deepseek-v4-flash | 1.00 | 0.00 | 0.50 | 0.25 | 0.25 |

The focused compactor (top_k=3 per section) preserves the load-bearing
"hooks" facet but cite-rate remains at the facets_6 floor (0.25). The
lost-in-the-middle effect manifests at ≥ 6 facets regardless of compaction.
This suggests the compactor reduces token count without recovering attention
— further investigation needed (e.g. reordering facets, stronger priming).

## B-11 probe result (same session)

- `empty_pool` → bucket_a (healthy refusal) ✅
- `single_artist_no_known` → bucket_c (model confabulates at boundary,
  but N1 code-side guard catches it before production)

## Files

- Eval results: `evaluation/results/20260520-061237/`
- Probe results: `evaluation/probes/results/20260520T060152Z/` (gpt-5.4-mini),
  `20260520T060253Z/` (deepseek-v4-flash), `20260520T060925Z/` (gpt-5.4)
- B-11 probe: `evaluation/probes/results/20260520T060105Z/`

