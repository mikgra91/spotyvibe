# Evaluation comparison

Generated: 20260508-071253

## Quality gate — playlist-B leakage

After feedback (likes + dislikes + refine train) the harness generates a SECOND playlist on the same profile. Any leak below means the production pipeline ignored an earlier signal.

| Model | Iter | Tracks B | Leak status | Total leaks | Rejected artist | Disliked track | Dislike pattern |
|---|---:|---:|---|---:|---:|---:|---:|
| gpt-4.1 | 1 | 6 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1-mini | 1 | — | skipped | — | — | — | — |
| gpt-5.4 | 1 | 2 | pass | 0 | 0 | 0 | 0 |
| gpt-5.4-mini | 1 | 5 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1 | 1 | 5 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1-mini | 1 | — | skipped | — | — | — | — |
| gpt-5.4 | 1 | 2 | pass | 0 | 0 | 0 | 0 |
| gpt-5.4-mini | 1 | 2 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1 | 1 | 9 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1-mini | 1 | — | skipped | — | — | — | — |
| gpt-5.4 | 1 | 7 | pass | 0 | 0 | 0 | 0 |
| gpt-5.4-mini | 1 | 8 | pass | 0 | 0 | 0 | 0 |
| gpt-4.1 | 1 | — | pass | 0 | 0 | 0 | 0 |
| gpt-4.1-mini | 1 | — | pass | 0 | 0 | 0 | 0 |
| gpt-5.4 | 1 | 9 | pass | 0 | 0 | 0 | 0 |
| gpt-5.4-mini | 1 | 2 | pass | 0 | 0 | 0 | 0 |

## Quality gate — playlist completion (≥ 95 % of requested size)

| Model | Iter | Tracks A | Completion A | Tracks B | Completion B |
|---|---:|---:|---|---:|---|
| gpt-4.1 | 1 | 6 | under | 6 | under |
| gpt-4.1-mini | 1 | — | empty | — | skipped |
| gpt-5.4 | 1 | 12 | under | 2 | under |
| gpt-5.4-mini | 1 | 13 | under | 5 | under |
| gpt-4.1 | 1 | 10 | under | 5 | under |
| gpt-4.1-mini | 1 | — | empty | — | skipped |
| gpt-5.4 | 1 | 3 | under | 2 | under |
| gpt-5.4-mini | 1 | 3 | under | 2 | under |
| gpt-4.1 | 1 | 15 | ok | 9 | under |
| gpt-4.1-mini | 1 | — | empty | — | skipped |
| gpt-5.4 | 1 | 14 | under | 7 | under |
| gpt-5.4-mini | 1 | 6 | under | 8 | under |
| gpt-4.1 | 1 | 15 | ok | — | empty |
| gpt-4.1-mini | 1 | 4 | under | — | empty |
| gpt-5.4 | 1 | 12 | under | 9 | under |
| gpt-5.4-mini | 1 | 4 | under | 2 | under |

## Diagnostic — F9 trace bundles

| Model | Iter | Trace A | Trace B |
|---|---:|---|---|
| gpt-4.1 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-4.1-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-4.1-iter1\trace_B.json |
| gpt-4.1-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-4.1-mini-iter1\trace_A.json | — |
| gpt-5.4 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-5.4-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-5.4-iter1\trace_B.json |
| gpt-5.4-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-5.4-mini-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\gpt-5.4-mini-iter1\trace_B.json |
| gpt-4.1 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-4.1-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-4.1-iter1\trace_B.json |
| gpt-4.1-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-4.1-mini-iter1\trace_A.json | — |
| gpt-5.4 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-5.4-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-5.4-iter1\trace_B.json |
| gpt-5.4-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-5.4-mini-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\lastfm_tag_weighting__gpt-5.4-mini-iter1\trace_B.json |
| gpt-4.1 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-4.1-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-4.1-iter1\trace_B.json |
| gpt-4.1-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-4.1-mini-iter1\trace_A.json | — |
| gpt-5.4 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-5.4-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-5.4-iter1\trace_B.json |
| gpt-5.4-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-5.4-mini-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\niche_only_strict__gpt-5.4-mini-iter1\trace_B.json |
| gpt-4.1 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-4.1-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-4.1-iter1\trace_B.json |
| gpt-4.1-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-4.1-mini-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-4.1-mini-iter1\trace_B.json |
| gpt-5.4 | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-5.4-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-5.4-iter1\trace_B.json |
| gpt-5.4-mini | 1 | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-5.4-mini-iter1\trace_A.json | C:\git\spotyvibe\evaluation\results\20260508-071253\post_feedback_tag_regression__gpt-5.4-mini-iter1\trace_B.json |

## Quality gate — playlist-B fit-check

Deterministic per-track checks (currently `decade_avoid` via Spotify `release_year`). `no_checks_applied` means the scenario's profile mentions no decade in its avoid prose.

| Model | Iter | Tracks B | Fit status | Total fails | Decade avoid | Checks applied |
|---|---:|---:|---|---:|---:|---|
| gpt-4.1 | 1 | 6 | pass | 0 | 0 | decade_avoid |
| gpt-4.1-mini | 1 | — | skipped | — | — | — |
| gpt-5.4 | 1 | 2 | pass | 0 | 0 | decade_avoid |
| gpt-5.4-mini | 1 | 5 | pass | 0 | 0 | decade_avoid |
| gpt-4.1 | 1 | 5 | no_checks_applied | 0 | 0 | — |
| gpt-4.1-mini | 1 | — | skipped | — | — | — |
| gpt-5.4 | 1 | 2 | no_checks_applied | 0 | 0 | — |
| gpt-5.4-mini | 1 | 2 | no_checks_applied | 0 | 0 | — |
| gpt-4.1 | 1 | 9 | no_checks_applied | 0 | 0 | — |
| gpt-4.1-mini | 1 | — | skipped | — | — | — |
| gpt-5.4 | 1 | 7 | no_checks_applied | 0 | 0 | — |
| gpt-5.4-mini | 1 | 8 | no_checks_applied | 0 | 0 | — |
| gpt-4.1 | 1 | — | pass | 0 | 0 | decade_avoid |
| gpt-4.1-mini | 1 | — | pass | 0 | 0 | decade_avoid |
| gpt-5.4 | 1 | 9 | fail | 3 | 3 | decade_avoid |
| gpt-5.4-mini | 1 | 2 | pass | 0 | 0 | decade_avoid |

### Fit-check hits (per run)

**gpt-5.4 iter 1**

| Rule | Artist | Track | Detail |
|---|---|---|---|
| decade_avoid | bardeux | magic carpet ride | release_year=1988 falls in avoided 1980s decade |
| decade_avoid | bardeux | when we kiss | release_year=1988 falls in avoided 1980s decade |
| decade_avoid | bardeux | bleeding heart | release_year=1988 falls in avoided 1980s decade |


## Per-run rollup

| Scenario | Model | Iter | Cost ($) | Wall (s) | p50 (s) | p95 (s) | Tracks | Spotify-found | Must-have cite | Stage2 | Status | Cleanup |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| default | gpt-4.1 | 1 | 0.1297 | 57.157 | 9.142 | 11.241 | 6 | 66.7% | 77.8% | 42/43 (ok) | ok | ok |
| default | gpt-4.1-mini | 1 | 0.009 | 31.92 | 9.236 | 14.395 | — | — | — | 39/41 (ok) | ok | ok |
| default | gpt-5.4 | 1 | 0.1964 | 67.029 | 12.436 | 16.984 | 12 | 66.7% | 90.5% | 32/32 (ok) | ok | ok |
| default | gpt-5.4-mini | 1 | 0.076 | 66.15 | 9.276 | 12.756 | 13 | 52.9% | 73.5% | 36/39 (ok) | ok | ok |
| lastfm_tag_weighting | gpt-4.1 | 1 | 0.162 | 126.869 | 21.13 | 22.607 | 10 | 27.3% | 61.8% | 20/21 (ok) | ok | ok |
| lastfm_tag_weighting | gpt-4.1-mini | 1 | 0.0073 | 21.339 | 6.947 | 7.668 | — | — | — | 22/22 (skipped_no_overlap) | ok | ok |
| lastfm_tag_weighting | gpt-5.4 | 1 | 0.1638 | 65.415 | 12.314 | 13.177 | 3 | 23.8% | 100.0% | 22/26 (ok) | ok | ok |
| lastfm_tag_weighting | gpt-5.4-mini | 1 | 0.0903 | 63.867 | 10.456 | 10.941 | 3 | 7.2% | 82.6% | 50/50 (skipped_no_overlap) | ok | ok |
| niche_only_strict | gpt-4.1 | 1 | 0.1699 | 111.925 | 19.805 | 24.988 | 15 | 63.2% | 57.9% | 50/50 (skipped_no_overlap) | ok | ok |
| niche_only_strict | gpt-4.1-mini | 1 | 0.0103 | 37.042 | 11.209 | 14.333 | — | — | — | 50/50 (skipped_no_overlap) | ok | ok |
| niche_only_strict | gpt-5.4 | 1 | 0.2878 | 145.744 | 21.322 | 28.704 | 14 | 38.2% | 98.2% | 47/49 (ok) | ok | ok |
| niche_only_strict | gpt-5.4-mini | 1 | 0.0784 | 78.393 | 12.14 | 13.254 | 6 | 29.8% | 70.2% | 50/50 (ok) | ok | ok |
| post_feedback_tag_regression | gpt-4.1 | 1 | 0.0997 | 13.61 | 3.694 | 6.354 | 15 | 93.8% | 81.2% | 49/49 (skipped_no_overlap) | ok | ok |
| post_feedback_tag_regression | gpt-4.1-mini | 1 | 0.0212 | 33.711 | 11.018 | 12.121 | 4 | 100.0% | 75.0% | 50/50 (skipped_no_overlap) | ok | ok |
| post_feedback_tag_regression | gpt-5.4 | 1 | 0.2407 | 97.762 | 16.721 | 19.415 | 12 | 58.3% | 97.2% | 49/49 (skipped_no_overlap) | ok | ok |
| post_feedback_tag_regression | gpt-5.4-mini | 1 | 0.0725 | 40.222 | 6.037 | 8.195 | 4 | 27.3% | 100.0% | 46/46 (skipped_no_overlap) | ok | ok |

## Cost breakdown by feature ($)

| Model | Iter | Stage 3 (batches) | Stage 2 | Profile updates | Band/Song Analysis | Total |
|---|---:|---:|---:|---:|---:|---:|
| gpt-4.1 | 1 | 0.1135 | 0.0025 | 0.0107 | 0.003 | 0.1297 |
| gpt-4.1-mini | 1 | 0.0053 | 0.0011 | 0.0021 | 0.0006 | 0.009 |
| gpt-5.4 | 1 | 0.1687 | 0.0019 | 0.02 | 0.0058 | 0.1964 |
| gpt-5.4-mini | 1 | 0.0673 | 0.0023 | 0.005 | 0.0014 | 0.076 |
| gpt-4.1 | 1 | 0.1476 | 0.0006 | 0.0107 | 0.0031 | 0.162 |
| gpt-4.1-mini | 1 | 0.0046 | — | 0.002 | 0.0007 | 0.0073 |
| gpt-5.4 | 1 | 0.1391 | 0.0007 | 0.0181 | 0.006 | 0.1638 |
| gpt-5.4-mini | 1 | 0.0833 | — | 0.0052 | 0.0018 | 0.0903 |
| gpt-4.1 | 1 | 0.1555 | — | 0.0112 | 0.0031 | 0.1699 |
| gpt-4.1-mini | 1 | 0.0075 | — | 0.0022 | 0.0006 | 0.0103 |
| gpt-5.4 | 1 | 0.2607 | 0.0014 | 0.0198 | 0.006 | 0.2878 |
| gpt-5.4-mini | 1 | 0.0699 | 0.0014 | 0.0052 | 0.0019 | 0.0784 |
| gpt-4.1 | 1 | 0.0864 | — | 0.0101 | 0.0031 | 0.0997 |
| gpt-4.1-mini | 1 | 0.0185 | — | 0.0021 | 0.0006 | 0.0212 |
| gpt-5.4 | 1 | 0.218 | — | 0.0167 | 0.006 | 0.2407 |
| gpt-5.4-mini | 1 | 0.0659 | — | 0.0048 | 0.0018 | 0.0725 |

## Latency by feature (s)

| Model | Iter | Stage 3 sum | Stage 2 | Profile updates | Band/Song Analysis |
|---|---:|---:|---:|---:|---:|
| gpt-4.1 | 1 | 66.97 | 3.41 | 6.53 | 2.43 |
| gpt-4.1-mini | 1 | 29.29 | 2.48 | 10.35 | 7.23 |
| gpt-5.4 | 1 | 123.79 | 2.68 | 11.5 | 6.77 |
| gpt-5.4-mini | 1 | 84.58 | 3.79 | 5.53 | 3.23 |
| gpt-4.1 | 1 | 148.7 | 1.7 | 12.7 | 6.15 |
| gpt-4.1-mini | 1 | 21.14 | — | 16.33 | 5.77 |
| gpt-5.4 | 1 | 102.42 | 1.11 | 10.74 | 5.43 |
| gpt-5.4-mini | 1 | 88.84 | — | 4.85 | 2.83 |
| gpt-4.1 | 1 | 147.34 | — | 8.57 | 4.83 |
| gpt-4.1-mini | 1 | 36.88 | — | 8.98 | 4.17 |
| gpt-5.4 | 1 | 182.93 | 2.44 | 12.58 | 5.6 |
| gpt-5.4-mini | 1 | 85.68 | 1.62 | 4.36 | 2.75 |
| gpt-4.1 | 1 | 55.75 | — | 6.35 | 3.13 |
| gpt-4.1-mini | 1 | 122.03 | — | 10.45 | 3.53 |
| gpt-5.4 | 1 | 152.16 | — | 9.1 | 6.33 |
| gpt-5.4-mini | 1 | 62.59 | — | 6.2 | 3.54 |

## Per-stage breakdown (E1)

Wall-clock + LLM tokens per pipeline stage, pulled from the F9 trace bundle. `calls` is the number of times the stage fired in this run (Stage 3 fires once per generation batch). Empty cells when the stage didn't run on that playlist.

### Playlist A

| Model | Iter | Stage | Wall (s) | Calls | Tokens in | Tokens out |
|---|---:|---|---:|---:|---:|---:|
| gpt-4.1 | 1 | RAG retrieve | 0.1216 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 2 avoid | 1.8087 | 1 | 454 | 203 |
| gpt-4.1 | 1 | Stage 3 select | 32.085 | 4 | 9994 | 4360 |
| gpt-4.1 | 1 | Spotify verify | 13.2708 | 2 | 0 | 0 |
| gpt-4.1-mini | 1 | RAG retrieve | 0.0917 | 1 | 0 | 0 |
| gpt-4.1-mini | 1 | Stage 2 avoid | 2.4809 | 1 | 423 | 169 |
| gpt-4.1-mini | 1 | Stage 3 select | 29.2938 | 3 | 7026 | 1547 |
| gpt-5.4 | 1 | RAG retrieve | 0.1451 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 2 avoid | 1.4332 | 1 | 381 | 144 |
| gpt-5.4 | 1 | Stage 3 select | 70.0871 | 4 | 9355 | 4501 |
| gpt-5.4 | 1 | Spotify verify | 28.451 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.1452 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 2 avoid | 1.8965 | 1 | 455 | 204 |
| gpt-5.4-mini | 1 | Stage 3 select | 45.2974 | 4 | 10575 | 5956 |
| gpt-5.4-mini | 1 | Spotify verify | 32.8623 | 4 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.1405 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 3 select | 75.4914 | 4 | 8174 | 6371 |
| gpt-4.1 | 1 | Spotify verify | 45.0212 | 4 | 0 | 0 |
| gpt-4.1-mini | 1 | RAG retrieve | 0.1596 | 1 | 0 | 0 |
| gpt-4.1-mini | 1 | Stage 3 select | 21.1389 | 3 | 5805 | 1451 |
| gpt-5.4 | 1 | RAG retrieve | 0.2309 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 3 select | 54.0081 | 4 | 8162 | 3359 |
| gpt-5.4 | 1 | Spotify verify | 23.962 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.1301 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 3 select | 47.6284 | 4 | 11023 | 7216 |
| gpt-5.4-mini | 1 | Spotify verify | 44.5776 | 4 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.1056 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 3 select | 67.8242 | 4 | 10947 | 6893 |
| gpt-4.1 | 1 | Spotify verify | 36.2909 | 4 | 0 | 0 |
| gpt-4.1-mini | 1 | RAG retrieve | 0.0955 | 1 | 0 | 0 |
| gpt-4.1-mini | 1 | Stage 3 select | 36.8831 | 3 | 7824 | 2718 |
| gpt-5.4 | 1 | RAG retrieve | 0.0782 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 3 select | 93.375 | 4 | 11269 | 6664 |
| gpt-5.4 | 1 | Spotify verify | 43.8312 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.0962 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 3 select | 36.1116 | 4 | 8036 | 5096 |
| gpt-5.4-mini | 1 | Spotify verify | 40.4829 | 4 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.1447 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 3 select | 42.2923 | 3 | 7978 | 5460 |
| gpt-4.1 | 1 | Spotify verify | 29.3729 | 3 | 0 | 0 |
| gpt-4.1-mini | 1 | RAG retrieve | 0.0989 | 1 | 0 | 0 |
| gpt-4.1-mini | 1 | Stage 3 select | 88.4887 | 4 | 10538 | 4432 |
| gpt-4.1-mini | 1 | Spotify verify | 7.9623 | 2 | 0 | 0 |
| gpt-5.4 | 1 | RAG retrieve | 0.1214 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 3 select | 83.966 | 4 | 10827 | 5995 |
| gpt-5.4 | 1 | Spotify verify | 36.8534 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.2002 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 3 select | 36.9766 | 4 | 10695 | 6786 |
| gpt-5.4-mini | 1 | Spotify verify | 23.252 | 3 | 0 | 0 |

### Playlist B

| Model | Iter | Stage | Wall (s) | Calls | Tokens in | Tokens out |
|---|---:|---|---:|---:|---:|---:|
| gpt-4.1 | 1 | RAG retrieve | 0.1426 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 2 avoid | 1.6035 | 1 | 457 | 190 |
| gpt-4.1 | 1 | Stage 3 select | 34.8871 | 4 | 10355 | 4745 |
| gpt-4.1 | 1 | Spotify verify | 20.4383 | 3 | 0 | 0 |
| gpt-5.4 | 1 | RAG retrieve | 0.1112 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 2 avoid | 1.2459 | 1 | 385 | 147 |
| gpt-5.4 | 1 | Stage 3 select | 53.7034 | 4 | 9922 | 3535 |
| gpt-5.4 | 1 | Spotify verify | 11.904 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.1318 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 2 avoid | 1.896 | 1 | 434 | 157 |
| gpt-5.4-mini | 1 | Stage 3 select | 39.2799 | 4 | 10547 | 5479 |
| gpt-5.4-mini | 1 | Spotify verify | 24.7674 | 2 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.1268 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 2 avoid | 1.6983 | 1 | 311 | 90 |
| gpt-4.1 | 1 | Stage 3 select | 73.2095 | 4 | 8780 | 7837 |
| gpt-4.1 | 1 | Spotify verify | 51.6434 | 4 | 0 | 0 |
| gpt-5.4 | 1 | RAG retrieve | 0.1991 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 2 avoid | 1.1135 | 1 | 341 | 95 |
| gpt-5.4 | 1 | Stage 3 select | 48.4144 | 4 | 8587 | 3120 |
| gpt-5.4 | 1 | Spotify verify | 15.6118 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.1374 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 3 select | 41.2132 | 4 | 11447 | 7550 |
| gpt-5.4-mini | 1 | Spotify verify | 22.4453 | 4 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.0773 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 3 select | 79.5201 | 4 | 11437 | 6948 |
| gpt-4.1 | 1 | Spotify verify | 32.2391 | 3 | 0 | 0 |
| gpt-5.4 | 1 | RAG retrieve | 0.0634 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 2 avoid | 2.4364 | 1 | 534 | 222 |
| gpt-5.4 | 1 | Stage 3 select | 89.5561 | 4 | 11728 | 6880 |
| gpt-5.4 | 1 | Spotify verify | 53.6041 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.0987 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 2 avoid | 1.6179 | 1 | 506 | 230 |
| gpt-5.4-mini | 1 | Stage 3 select | 49.5698 | 4 | 11625 | 7159 |
| gpt-5.4-mini | 1 | Spotify verify | 27.001 | 4 | 0 | 0 |
| gpt-4.1 | 1 | RAG retrieve | 0.1181 | 1 | 0 | 0 |
| gpt-4.1 | 1 | Stage 3 select | 13.4581 | 3 | 8286 | 1274 |
| gpt-4.1-mini | 1 | RAG retrieve | 0.1054 | 1 | 0 | 0 |
| gpt-4.1-mini | 1 | Stage 3 select | 33.5453 | 3 | 8004 | 2483 |
| gpt-5.4 | 1 | RAG retrieve | 0.121 | 1 | 0 | 0 |
| gpt-5.4 | 1 | Stage 3 select | 68.198 | 4 | 11632 | 4798 |
| gpt-5.4 | 1 | Spotify verify | 29.3543 | 4 | 0 | 0 |
| gpt-5.4-mini | 1 | RAG retrieve | 0.1375 | 1 | 0 | 0 |
| gpt-5.4-mini | 1 | Stage 3 select | 25.6104 | 4 | 10814 | 4271 |
| gpt-5.4-mini | 1 | Spotify verify | 14.3823 | 2 | 0 | 0 |


## Phase B coverage — Last.fm tags + listener distribution (E2/E3)

`Coverage` = % of corpus-matched tracks whose artist has `lastfm_tags` populated (gate: ≥ 75 %; sub-gate values are flagged with ⚠). `p95 listeners` is computed only over tracks with non-zero `lastfm_listeners` — `n=` shows the sample size. The `niche_only_strict` scenario expects p95 < 100,000.

### Playlist A

| Scenario | Model | Iter | Tracks | Matched | Coverage | Median listeners | p95 listeners | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| default | gpt-4.1 | 1 | 6 | 6 | 100.0% | 95429 | 252942 | 6 |
| default | gpt-5.4 | 1 | 12 | 12 | 100.0% | 25883 | 97694 | 12 |
| default | gpt-5.4-mini | 1 | 13 | 13 | 100.0% | 97694 | 252942 | 13 |
| lastfm_tag_weighting | gpt-4.1 | 1 | 10 | 10 | 100.0% | 17532 | 73738 | 10 |
| lastfm_tag_weighting | gpt-5.4 | 1 | 3 | 3 | 100.0% | 696441 | 696441 | 3 |
| lastfm_tag_weighting | gpt-5.4-mini | 1 | 3 | 3 | 100.0% | 73738 | 73738 | 3 |
| niche_only_strict | gpt-4.1 | 1 | 15 | 15 | 100.0% | 39075 | 215584 | 15 |
| niche_only_strict | gpt-5.4 | 1 | 14 | 14 | 100.0% | 73256 | 215584 | 14 |
| niche_only_strict | gpt-5.4-mini | 1 | 6 | 6 | 100.0% | 891389 | 891389 | 6 |
| post_feedback_tag_regression | gpt-4.1 | 1 | 15 | 15 | 100.0% | 8900 | 154769 | 15 |
| post_feedback_tag_regression | gpt-4.1-mini | 1 | 4 | 4 | 100.0% | 31389 | 31389 | 4 |
| post_feedback_tag_regression | gpt-5.4 | 1 | 12 | 12 | 100.0% | 15984 | 143835 | 12 |
| post_feedback_tag_regression | gpt-5.4-mini | 1 | 4 | 4 | 100.0% | 5166 | 60278 | 4 |

### Playlist B

| Scenario | Model | Iter | Tracks | Matched | Coverage | Median listeners | p95 listeners | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| default | gpt-4.1 | 1 | 6 | 6 | 100.0% | 10430 | 21110 | 6 |
| default | gpt-5.4 | 1 | 2 | 2 | 100.0% | 11906 | 17737 | 2 |
| default | gpt-5.4-mini | 1 | 5 | 5 | 100.0% | 30315 | 57162 | 5 |
| lastfm_tag_weighting | gpt-4.1 | 1 | 5 | 5 | 100.0% | 152652 | 152652 | 5 |
| lastfm_tag_weighting | gpt-5.4 | 1 | 2 | 2 | 100.0% | 152652 | 152652 | 2 |
| lastfm_tag_weighting | gpt-5.4-mini | 1 | 2 | 2 | 50.0% ⚠ | 17026 | 17026 | 1 |
| niche_only_strict | gpt-4.1 | 1 | 9 | 9 | 100.0% | 5126 | 12914 | 9 |
| niche_only_strict | gpt-5.4 | 1 | 7 | 7 | 100.0% | 29747 | 39075 | 7 |
| niche_only_strict | gpt-5.4-mini | 1 | 8 | 8 | 100.0% | 116542 | 215584 | 8 |
| post_feedback_tag_regression | gpt-5.4 | 1 | 9 | 9 | 100.0% | 43304 | 166050 | 9 |
| post_feedback_tag_regression | gpt-5.4-mini | 1 | 2 | 2 | 100.0% | 17827 | 17827 | 2 |


## Eval-log row counts

(Sanity check that telemetry actually fired for every feature.)

| Model | Iter | track | batch_summary | stage2_summary | profile_update_summary | analysis_summary | run_summary |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-4.1 | 1 | 18 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1-mini | 1 | 0 | 3 | 1 | 2 | 1 | 1 |
| gpt-5.4 | 1 | 21 | 8 | 2 | 2 | 1 | 2 |
| gpt-5.4-mini | 1 | 34 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1 | 1 | 55 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1-mini | 1 | 0 | 3 | 1 | 2 | 1 | 1 |
| gpt-5.4 | 1 | 21 | 8 | 2 | 2 | 1 | 2 |
| gpt-5.4-mini | 1 | 69 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1 | 1 | 38 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1-mini | 1 | 0 | 3 | 1 | 2 | 1 | 1 |
| gpt-5.4 | 1 | 55 | 8 | 2 | 2 | 1 | 2 |
| gpt-5.4-mini | 1 | 47 | 8 | 2 | 2 | 1 | 2 |
| gpt-4.1 | 1 | 16 | 6 | 2 | 2 | 1 | 2 |
| gpt-4.1-mini | 1 | 4 | 7 | 2 | 2 | 1 | 2 |
| gpt-5.4 | 1 | 36 | 8 | 2 | 2 | 1 | 2 |
| gpt-5.4-mini | 1 | 22 | 8 | 2 | 2 | 1 | 2 |
