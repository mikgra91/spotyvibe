# B1 — Stage 3 model downgrade probe

**Run:** 2026-05-08 (results dir `evaluation/results/20260508-145519/`,
killed mid-niche-iter-3 due to a Spotify token-penalty 429 cascade —
Retry-After headers came back ≈ 51 600 s ≈ 14 h, so the eval could not
make forward progress on the remaining tracks).

**Scope:** 2 models × 2 scenarios × 3 iter, `playlist_size=15`,
`MAX_GPT_CALLS_PER_RUN=4` (production default left unchanged).
Default scenario completed all 6 runs. Niche scenario completed 2 of 6
(gpt-5.4 iter 1 + iter 2 only).

## Default scenario — Playlist A (generation quality)

| Model | Iter 1 | Iter 2 | Iter 3 | Mean | Wall | Spotify-found |
|---|---:|---:|---:|---:|---:|---|
| gpt-5.4 | 6 | 14 | 13 | **11.0** | 234-293 s | 50-93 % |
| gpt-5.4-mini | 13 | 15 | 15 | **14.3** | 135-169 s | high (15/15 twice) |

mini wins on **completion** (14.3 vs 11.0), **wall clock** (~50 % faster),
and **cost** (~10× cheaper, $0.01/cycle vs $0.10/cycle).

## Default scenario — Playlist B (post-feedback regeneration)

| Model | Iter 1 | Iter 2 | Iter 3 | Mean |
|---|---:|---:|---:|---:|
| gpt-5.4 | 8 | 9 | 8 | **8.3** |
| gpt-5.4-mini | 3 | 7 | 1 | **3.7** |

**mini collapses on Playlist B** — average 3.7 tracks vs gpt-5.4's 8.3.
Likely because the post-feedback profile prose is more nuanced (it
encodes the "I disliked these → infer my real taste" inference),
and mini struggles to generalise. This is a real quality gap.

## niche_only_strict scenario (partial — 2 of 6 iters)

| Model | Iter 1 | Iter 2 | Iter 3 | p95 listeners (A) |
|---|---:|---:|---:|---|
| gpt-5.4 | 13 | 12 | aborted (429) | 215 584 / 215 584 — **fails ≤ 100 k gate** |
| gpt-5.4-mini | — | — | — | not collected |

A3 (niche-bias fix) is **confirmed needed** — the same Last.fm-popular
artists (Bardeux, Brian H. Kim, Anika, Dombrance) keep surfacing in
Playlist A even when avoid prose explicitly bans mainstream popularity.
The popularity prefer in `_artist_popularity()` wins until something
inverts it.

## Quality gates

All 8 completed runs **leakage=pass, fit=pass** (or `no_checks_applied`).
No gate regression introduced by either model.

## Decision — L5 Stage 3 default switch

**Mixed signal — do NOT flip the default to mini unconditionally.**

- For **Playlist A** (initial generation), mini is a clear win: better
  completion, half the wall time, an order of magnitude cheaper.
- For **Playlist B** (post-feedback regeneration), gpt-5.4 is materially
  better (mean 8.3 vs 3.7). Production users routinely run the
  feedback loop — the regression would be visible.

Two viable paths:

1. **Two-tier Stage 3.** Use mini on first generation; promote to
   gpt-5.4 once the profile carries non-trivial feedback weight (e.g.
   `len(profile.feedback.disliked_tracks) > 5`). Cost win on the
   common path, quality preserved on the post-feedback path.
2. **Keep gpt-5.4 as the default**, expose mini as an optional
   "fast / cheap" mode in Settings. Simpler to ship; cost win opt-in.

Either way, **L5 should not default-flip without addressing the
Playlist B regression first.** Recommend path (1) but spec it before
implementing.

## Spotify rate-limit observation (operational)

The 429 cascade fired on `niche_only_strict iter 3` even with the
serial-mode + 1.5 s delay + 90 s cap settings already in place from
2026-05-07. Retry-After ≈ 14 h is a *user-token* penalty, not a
per-call quota — the only fix is a wait or a different token.

Next eval kickoff should wait until the token clears (>= 14 h from
2026-05-08T18:54 UTC → not before 2026-05-09T08:54 UTC).
