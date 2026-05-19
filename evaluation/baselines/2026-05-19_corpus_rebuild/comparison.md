# Evaluation comparison

Generated: 20260519-103122

## Quality gate — playlist-B leakage

After feedback (likes + dislikes + refine train) the harness generates a SECOND playlist on the same profile. Any leak below means the production pipeline ignored an earlier signal.

| Model | Iter | Tracks B | Leak status | Total leaks | Rejected artist | Disliked track | Dislike pattern |
|---|---:|---:|---|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | 15 | pass | 0 | 0 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | 15 | pass | 0 | 0 | 0 | 0 |

## Quality gate — playlist completion (≥ 95 % of requested size)

| Model | Iter | Tracks A | Completion A | Tracks B | Completion B |
|---|---:|---:|---|---:|---|
| deepseek/deepseek-v4-flash | 1 | 15 | ok | 15 | ok |
| deepseek/deepseek-v4-flash | 1 | 15 | ok | 15 | ok |

## Diagnostic — F9 trace bundles

| Model | Iter | Trace A | Trace B |
|---|---:|---|---|
| deepseek/deepseek-v4-flash | 1 | C:\git\spotyvibe\evaluation\results\20260519-103122\deepseek_deepseek-v4-flash-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260519-103122\deepseek_deepseek-v4-flash-iter1\trace_B.json |
| deepseek/deepseek-v4-flash | 1 | C:\git\spotyvibe\evaluation\results\20260519-103122\lastfm_tag_weighting__deepseek_deepseek-v4-flash-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260519-103122\lastfm_tag_weighting__deepseek_deepseek-v4-flash-iter1\trace_B.json |

## Quality gate — playlist-B fit-check

Deterministic per-track checks (currently `decade_avoid` via Spotify `release_year`). `no_checks_applied` means the scenario's profile mentions no decade in its avoid prose.

| Model | Iter | Tracks B | Fit status | Total fails | Decade avoid | Checks applied |
|---|---:|---:|---|---:|---:|---|
| deepseek/deepseek-v4-flash | 1 | 15 | fail | 1 | 1 | decade_avoid |
| deepseek/deepseek-v4-flash | 1 | 15 | no_checks_applied | 0 | 0 | — |

### Fit-check hits (per run)

**deepseek/deepseek-v4-flash iter 1**

| Rule | Artist | Track | Detail |
|---|---|---|---|
| decade_avoid | splendor | special lady | release_year=1979 falls in avoided 1970s decade |


## Per-run rollup

| Scenario | Model | Iter | Cost ($) | Wall (s) | p50 (s) | p95 (s) | Tracks | Spotify-found | Must-have cite | Stage2 | Status | Cleanup |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| default | deepseek/deepseek-v4-flash | 1 | 0.0138 | 253.127 | 51.246 | 65.115 | 15 | 96.8% | 93.5% | 31/31 (ok) | ok | ok |
| lastfm_tag_weighting | deepseek/deepseek-v4-flash | 1 | 0.01 | 140.294 | 33.218 | 50.582 | 15 | 93.8% | 65.6% | 50/50 (skipped_no_overlap) | ok | ok |

## Cost breakdown by feature ($)

| Model | Iter | Stage 3 (batches) | Stage 2 | Profile updates | Band/Song Analysis | Total |
|---|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | 0.0121 | 0.0004 | 0.0012 | 0.0002 | 0.0138 |
| deepseek/deepseek-v4-flash | 1 | 0.0087 | — | 0.0011 | 0.0002 | 0.01 |

## Latency by feature (s)

| Model | Iter | Stage 3 sum | Stage 2 | Profile updates | Band/Song Analysis |
|---|---:|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | 421.15 | 19.65 | 30.24 | 7.43 |
| deepseek/deepseek-v4-flash | 1 | 233.58 | — | 26.28 | 5.56 |

## Per-stage breakdown (E1)

Wall-clock + LLM tokens per pipeline stage, pulled from the F9 trace bundle. `calls` is the number of times the stage fired in this run (Stage 3 fires once per generation batch). Empty cells when the stage didn't run on that playlist.

### Playlist A

| Model | Iter | Stage | Wall (s) | Calls | Tokens in | Tokens out |
|---|---:|---|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | RAG retrieve | 0.121 | 1 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | Stage 2 avoid | 9.359 | 1 | 397 | 188 |
| deepseek/deepseek-v4-flash | 1 | Stage 3 select | 208.5721 | 4 | 8898 | 20452 |
| deepseek/deepseek-v4-flash | 1 | Spotify verify | 28.2115 | 2 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | RAG retrieve | 0.2211 | 1 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | Stage 3 select | 122.6976 | 4 | 6550 | 12376 |
| deepseek/deepseek-v4-flash | 1 | Spotify verify | 28.8098 | 2 | 0 | 0 |

### Playlist B

| Model | Iter | Stage | Wall (s) | Calls | Tokens in | Tokens out |
|---|---:|---|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | RAG retrieve | 0.1493 | 1 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | Stage 2 avoid | 10.2889 | 1 | 397 | 876 |
| deepseek/deepseek-v4-flash | 1 | Stage 3 select | 212.5819 | 4 | 9531 | 18375 |
| deepseek/deepseek-v4-flash | 1 | Spotify verify | 30.0623 | 3 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | RAG retrieve | 0.2154 | 1 | 0 | 0 |
| deepseek/deepseek-v4-flash | 1 | Stage 3 select | 110.8848 | 3 | 9118 | 14240 |
| deepseek/deepseek-v4-flash | 1 | Spotify verify | 29.1586 | 3 | 0 | 0 |


## Phase B coverage — Last.fm tags + listener distribution (E2/E3)

`Coverage` = % of corpus-matched tracks whose artist has `lastfm_tags` populated (gate: ≥ 75 %; sub-gate values are flagged with ⚠). `p95 listeners` is computed only over tracks with non-zero `lastfm_listeners` — `n=` shows the sample size. The `niche_only_strict` scenario expects p95 < 100,000.

### Playlist A

| Scenario | Model | Iter | Tracks | Matched | Coverage | Median listeners | p95 listeners | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| default | deepseek/deepseek-v4-flash | 1 | 15 | 15 | 100.0% | 16572 | 265188 | 15 |
| lastfm_tag_weighting | deepseek/deepseek-v4-flash | 1 | 15 | 15 | 100.0% | 4381 | 73821 | 15 |

### Playlist B

| Scenario | Model | Iter | Tracks | Matched | Coverage | Median listeners | p95 listeners | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| default | deepseek/deepseek-v4-flash | 1 | 15 | 15 | 100.0% | 16141 | 51374 | 15 |
| lastfm_tag_weighting | deepseek/deepseek-v4-flash | 1 | 15 | 15 | 100.0% | 62609 | 87937 | 15 |


## Eval-log row counts

(Sanity check that telemetry actually fired for every feature.)

| Model | Iter | track | batch_summary | stage2_summary | profile_update_summary | analysis_summary | run_summary |
|---|---:|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-v4-flash | 1 | 31 | 8 | 2 | 2 | 1 | 2 |
| deepseek/deepseek-v4-flash | 1 | 32 | 7 | 2 | 2 | 1 | 2 |
