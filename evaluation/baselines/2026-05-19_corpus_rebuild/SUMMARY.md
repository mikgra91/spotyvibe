# Baseline — 2026-05-19 — Cloud-rebuilt corpus + OpenRouter (DeepSeek)

**Corpus:** `corpus_version=2026-05-19`, 175 578 artists, **83.4 %**
carrying baked-in `top_tracks` (146 515 rows). Cloud Run job was
modified to fetch top tracks per artist alongside Last.fm enrichment.

**Model:** `deepseek/deepseek-v4-flash` via OpenRouter (paid tier;
`:free` was upstream-rate-limited at run time).

**Scope:** 2 scenarios × 1 model × 1 iter, `--verify-mode spotify`.
Wall time: **24 min**. Cost: **$0.024 total** ($0.0138 default +
$0.01 lastfm_tag_weighting).

## Headline results

| Metric | default | lastfm_tag_weighting | Historical (E7, 2026-05-08) |
|---|---:|---:|---|
| Playlist A tracks | **15/15 ok** | **15/15 ok** | 30/32 under or empty across all models |
| Playlist B tracks | **15/15 ok** | **15/15 ok** | mostly under-fill |
| Spotify-found rate | **96.8 %** | **93.8 %** | gpt-5.4-mini 40 %; lastfm_tag_weighting **7-27 %** (A4 trigger) |
| Must-have cite | 93.5 % | 65.6 % | mini 86 %, gpt-5.4 97 % |
| Leakage (B vs feedback) | **0 leaks** | **0 leaks** | pass |
| Fit-check (decade_avoid) | 1 hit | n/a (no decade in avoid) | similar |
| Last.fm tag coverage | 100 % | 100 % | gate ≥ 75 % |
| Listener p95 (A / B) | 265 k / 51 k | 74 k / 88 k | n/a |
| Total cost | $0.0138 | $0.01 | gpt-5.4 $0.08-0.15, mini $0.04 per playlist |
| Wall | 253 s | 140 s | Stage 3 alone 30-180 s |

## What this confirms

### ✅ A4 — `lastfm_tag_weighting` Spotify-resolvability lift
The most important historical failure mode. E7 (2026-05-08) saw
Stage 3 pick tracks that Spotify could not resolve at all (7-27 %
found-rate, dragging the playlist into `under_filled`). The
2026-05-19 corpus bakes 5 Spotify-resolved top tracks per artist
directly into the RAG row; Stage 3 now picks from a `known:` list
that is by construction Spotify-resolvable. **93.8 % found-rate on
the same scenario = +66-86 pp absolute lift.** A4 task can be closed.

### ✅ A1 — Under-fill cap (`MAX_GPT_CALLS_PER_RUN = 4`)
E7 saw 30/32 playlists `under` or `empty`. With the new corpus
both A and B playlists hit 15/15 in 4 batches on both scenarios.
The cap stops being the binding constraint when Stage 3 actually
produces resolvable tracks. The cap doesn't need to be lifted; the
upstream problem was Stage 3 picks.

### ✅ Cost ceiling holds easily
The cost programme target was **< $0.10 per playlist consistently**.
DeepSeek V4 Flash via OpenRouter hits **$0.007 per playlist**
(2 playlists × 1 scenario = $0.014). C1's gpt-5.4 escalation
becomes far less load-bearing — DeepSeek already covers both the
"fast/cheap" and "post-feedback recovery" cases at this corpus
quality.

### ✅ Leakage discipline preserved
B-playlist leakage = 0 on both scenarios. Profile-update pipeline
correctly prunes disliked artists/tracks even on a cheaper model.

## Caveats

- **n=1.** B-6 variance-floor work showed `n_required_for_5pp_signal`
  is 5+ even on stable models. A single iter is enough to confirm
  the **direction** of the corpus-rebuild effect (the +66 pp on
  A4 is far above noise) but not to set design thresholds.
- **DeepSeek V4 Flash is new to this codebase.** No prior baseline
  on it; the cite-rate of 65.6 % on `lastfm_tag_weighting` could
  be model-specific rather than corpus-effect. Re-running the same
  matrix on `gpt-5.4-mini` would isolate that.
- **Default scenario fit-check fail:** 1 track (`splendor — special
  lady`, release_year=1979) leaked into a 1970s-avoid playlist B.
  Single hit; not a model regression on its own. The trace shows
  Stage 3 fired one decade-mismatch pick — not a corpus issue.
- **`:free` tier failed.** `deepseek/deepseek-v4-flash:free` returned
  429 "temporarily rate-limited upstream" on the very first
  profile-train call. Free tier is unreliable for full evals; use
  the paid tier ($0.024 per 2-scenario run) or another model.

## What the next eval should measure

1. **n=3 confirmation** on the same matrix to lock variance. ~$0.075.
2. **Cross-model sanity:** add `gpt-5.4-mini` for one scenario to
   confirm the corpus-rebuild lift is not DeepSeek-specific. ~$0.10.
3. **R1.2 prompt retry** ("ALWAYS OMIT no-known artists"). With
   83.4 % global coverage the empty-pool case is now rare; the
   previous reason for rejection (collapse to 0 / 15) may not
   reproduce. Add the R1.2 strict variant alongside the current
   prompt and diff.

## Files

- `comparison.md` — full harness report.
- `summary_default.json` — per-run summary for the default scenario.
- `summary_lastfm_tag_weighting.json` — per-run summary for the
  Last.fm-tag-weighted scenario.
- Source results dir: `evaluation/results/20260519-103122/`
  (carries the full trace bundles + eval.jsonl slices, not copied
  here to keep the baseline lean).

