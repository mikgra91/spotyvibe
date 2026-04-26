# result-improvement.md — Quality & cost rework plan

> Created 2026-04-25. Replaces `todo.md` and `documentation/guides/rag-implementation.md` (both deleted in this commit; substantive design rationale migrated into `documentation/TechnicalManual.md` §"RAG design reference"). References to those filenames below are historical pointers, not active links.
>
> **Driving problem**: GPT-5.4 produces a 40% dislike rate at ~$1/evening. The architecture (one mega-call with 14 KB profile JSON, 1.6 KB deny set, 600-token RAG pool, every call) is the bottleneck — not the model. This plan reworks the pipeline into staged calls and enforces constraints the model is currently ignoring.

## Operating principle (decided 2026-04-25)

**Quality first, cost second.** A cheaper model that produces worse suggestions is a regression, not a win. Every cost optimization in this plan must show no like-rate regression in A/B before adoption — we lock in the architecture's quality wins on quality models, *then* test cheaper variants against that baseline. Local LLMs stay first-class throughout: we don't control model throughput, but everything we control (prompt segmentation, parallel pipeline stages, streaming UI) is optimized so a slow model never feels broken.

## Goals (in priority order)

1. **Dislike rate ≤ 25%** (today ≈ 40%). Above 25% = profile is being misinterpreted. **This is the gate for every other goal.**
2. **Cost per 30-track run reduced ≥ 2× without quality regression** — driven by smaller prompts (Phase 1, 4) and a leaner AI Profile Update (Phase 3), keeping the suggestion model on the current quality default. Further reductions via cheaper-model A/B (Phase 5) only if Goal #1 still holds.
3. **Latency optimized within our control** — p95 ≤ 60 s for a 30-track run on cloud LLM. For local LLMs we don't control model throughput, but parallelizable stages, streamed batches to the UI, and segmented prompts are all in-scope (Phase 5.3).
4. **Hallucination rate stays ≥ 95%** Spotify-found (today: 96.8% with RAG on — RAG keeps this).
5. **Local LLMs first-class** — 8 K context as the supported floor (Llama 3.2 3B, Qwen 2.5 7B, Mistral 7B); 16 K context as the recommended sweet spot (Qwen 2.5 14B, Llama 3.1 8B with extended context, Mistral Nemo). 32 K+ is a pipedream for casual users and not a target. Local model latency is bounded by user hardware; our job is to feed it the smallest correct prompt and keep the UI responsive while it runs.
6. **Progressive precision** — feedback absorbed into the profile so each session is better than the last. Two complementary paths (decided 2026-04-25): inline use of dislike reasons in the per-call avoid-checker (Stage 2, P1.2) AND periodic batched absorption into `must_have`/`avoid` via AI Profile Update (P3.3). Inline gives immediate same-session correction; batched gives long-term profile evolution.

## Non-goals

- Multi-tenant hosting (deferred — see carry-forward §C.1).
- Android client (deferred — needs hosted backend first).
- Replacing MusicBrainz with embeddings (TF-IDF stays — reasoning in carry-forward §B.3).
- Self-hosted LLM on Cloud Run GPU (rejected — cost/quality trade-off bad).

## Post-Phase-0 measurements (2026-04-26, from eval.jsonl after P0 landed)

Two real runs captured immediately after Phase 0 shipped.

| Metric | GPT-5.5 | GPT-5.4-mini | Notes |
|---|---:|---:|---|
| Batches | 3 | 4 | mini uses smaller effective batch |
| Wall-clock (30 tracks) | **299.9 s** | **41.8 s** | 5.5 blows Goal #3 (≤ 60 s) |
| Batch latency p50 | 105.3 s | 9.1 s | — |
| Batch latency p95 | **110.4 s** | **9.4 s** | 5.5 is 1.8× over target |
| Tracks in RAG pool | **0 / 30** | 11 / 30 | pool still not influencing 5.5 picks |
| must_have cited | 21 / 30 (70%) | 26 / 31 (84%) | mini actually stronger on constraint |
| Spotify-found | 30 / 30 | 30 / 31 | both excellent |
| Profile chars/batch | 6,548–6,813 | 7,166–7,270 | ≈ 1.6–1.8 k tok (down from ~7 k) |
| Deny-set chars/batch | 4,308–4,970 | 5,486–6,257 | grows as run accumulates deny history |
| Token counts (batch_summary) | **None** | **None** | telemetry bug — see CF-Bug-5 |

**Conclusions**:
- P0.3 trims landed: profile is ~1.6 k tok, not 7 k. Target (~4 k total) approximately met.
- GPT-5.5 latency is unacceptably high at p95=110 s. Not usable as the default model unless Phase 1 shrinks the prompt dramatically. Interim: consider switching default back to gpt-5.4-mini until Phase 1 ships.
- GPT-5.4-mini quality signals are surprisingly competitive (84% must_have_cite vs 70% for 5.5, identical Spotify-found). Warrants staying as the interim default.
- RAG pool still yields 0 picks on gpt-5.5 — pool-inclusion problem predates Phase 0 and requires Phase 1 P1.1 code-side retrieval to fix.
- Token counts in batch_summary rows are all `None` — the `llm_usage` from `call_gpt(return_meta=True)` is not flowing into `log_batch_summary`. See CF-Bug-5.

## Measured baseline (2026-04-24, from eval.jsonl + OpenAI billing)

| Metric | Value | Source |
|---|---:|---|
| Like rate (judged tracks) | 60.3% | eval.jsonl × profile.feedback |
| **Dislike rate (judged)** | **39.7%** | same |
| Spotify-found rate | 96.8% | eval.jsonl |
| Pool tracks among dislikes | **78%** (pool actively hurts) | eval.jsonl × in_candidate_pool |
| Off-pool like rate | 77% | eval.jsonl |
| Pool like rate | 50% | eval.jsonl |
| Confirmed-artist recycling | 43% (53/124 suggestions) | eval.jsonl |
| Rejected-artist hits (filtered) | 9 | eval.jsonl × profile.artists.rejected |
| Primary references hit | **0 / 5** | eval.jsonl × profile.artists.moderate |
| Vintage rock bias | 42% of suggestions | eval.jsonl |
| Per-batch input tokens | ~6,500–7,500 | measured against profile.json |
| Per-batch output tokens | ~2,000–2,500 | over-request 10+5 × ~150 tok/track |
| **Per-batch cost (gpt-5.4)** | **~$0.047** | $3/M in + $12/M out |
| AI Profile Update cost | ~$0.094 | sends + receives full 26 KB profile |
| In-app cost estimator error | **~10× under-counts** | misses deny set, full profile, batch count |
| Per-batch wall-clock latency | **not measured** | telemetry hole — fixed in P0.2 |

> **Note (2026-04-25)**: `DEFAULT_OPENAI_MODEL` is now `gpt-5.5` ([config.py:77](config.py#L77)). The eval baseline above was captured against gpt-5.4. Phase 0 telemetry must re-baseline on gpt-5.5 *before* Phase 1 ships, so quality and cost deltas attribute to the right cause.

---

# Phase 0 — Bleed stop (this week, no quality risk) ✅ DONE 2026-04-26

Goal: stop losing money, start measuring, cleanup false-shipped claims.

**Status**: shipped. P0.1 cost estimator now multiplies by batch count and pulls live prompt sizes from `GET /api/profile/prompt-size`; P0.2 wires `log_batch_summary` + new `log_run_summary` (with p50/p95 batch latency); P0.3 trims (compact JSON in deny set + profile, stripped `liked_tracks`/`disliked_tracks` from `profile_for_gpt`, `recent_feedback` capped to 3 each side × 300 chars/line) all landed. P0.4 reckoning is captured here in this file's commit message when the migration commit lands.

## P0.1 — Fix the cost estimator ✅
**File**: [frontend/static/js/modules/cost_estimate.js](frontend/static/js/modules/cost_estimate.js#L25-L37)

Today's `estimate()` ignores the deny set, the full profile JSON, the RAG pool, and treats a 30-track playlist as one call.

Changes:
- Compute `batches = Math.ceil(tracks / BATCH_SIZE)`. Multiply `tokensIn` and `tokensOut` by it.
- Replace `profileText` source: fetch a profile-size hint from a new `GET /api/profile/prompt-size` endpoint that returns the *actual* sizes returned by `_build_deny_set_json` and `build_messages` for the live profile (not the train-form textarea bytes).
- Add a separate "AI Profile Update cost" line on the train screen.
- Add a session-cumulative spend display.

**Acceptance**: estimator reports within ±20% of OpenAI billing for a 30-track run. Verified by running 1 generation and comparing against billing dashboard.

## P0.2 — Wire eval-log telemetry (incl. latency baseline) ✅
The functions exist in [eval_log.py:236](core/src/eval_log.py#L236) (`log_batch_summary`, `compute_config_signature`) but `app.py::run_pipeline` never calls them. Net effect: `eval.jsonl` has 0 `batch_summary` rows. We also have no latency baseline today — Goal #3 ("p95 ≤ 60 s") is currently unmeasurable.

Changes in [app.py:712](app.py#L712):
- Capture `_usage` from `chat_completions_create` response (modify `call_gpt` in [suggestions.py:729](core/src/suggestions.py#L729) to return usage alongside the parsed result).
- Capture per-component prompt sizes (system, user-profile, deny-set, RAG-pool — broken out so we can see which slice changed batch-to-batch).
- Capture per-batch wall-clock latency (LLM call duration) and end-to-end run wall-clock latency.
- Call `log_batch_summary()` after each batch.

**Acceptance**: a generation run produces ≥ 1 `batch_summary` row per LLM call in `eval.jsonl`. Sum of `usage.total_tokens` reconciles to OpenAI dashboard within 5%. Run-level row records p50/p95 batch latency and total wall-clock — establishing the latency baseline that Goal #3 measures against.

## P0.3 — Land the Option A + Option C trims that were claimed shipped but aren't ✅
todo.md §14 marked these as shipped 2026-04-22. They are not in the codebase. Either ship them or update todo (we're picking ship).

| Trim | File / line | Saving |
|---|---|---:|
| Compact JSON (`separators=(",", ":")`) in `_build_deny_set_json` and `profile_json` | [suggestions.py:333](core/src/suggestions.py#L333) + [suggestions.py:504](core/src/suggestions.py#L504) | ~1,500 tok/batch |
| Strip `feedback.liked_tracks` and `feedback.disliked_tracks` from `profile_for_gpt` | [suggestions.py:498](core/src/suggestions.py#L498) | ~1,500 tok/batch |
| Truncate `recent_feedback` to last 3 each side, cap 300 chars | [suggestions.py:84-123](core/src/suggestions.py#L84-L123) | ~150–300 tok/batch |

`BATCH_SIZE_WITH_RAG` is intentionally **not** in this list — it increases total cloud cost (more calls). Its local-LLM cousin lives in Phase 5 (`BATCH_SIZE_WITH_LOCAL`).

**Acceptance**: per-batch input drops from ~7,000 to ~4,000 tok measured via the new telemetry. No regression in like-rate (run 30 tracks, compare).

## P0.4 — Update todo.md "Re-opened bugs" reckoning ✅ (process change)
Before deleting todo.md (final step of this plan), document in commit message which "✅ shipped" claims were actually false:
- Option A (BATCH_SIZE_WITH_RAG) — never shipped
- Option C #1, #4, #5 — never shipped
- Item 15 telemetry wiring — partially shipped (functions exist, app.py wiring missing)

Process change: from now on, the "shipped" check requires a grep-verifiable artifact (function name, constant, or test) referenced in the todo entry. No more "claimed shipped" without evidence.

---

# Phase 1 — Pipeline restructure (weeks 2–3, the architectural shift) ✅ DONE 2026-04-26

**Status**: shipped. Stage 1 `retrieve_candidates()` in `retrieval.py` (hard avoid filter + popularity band on top of stratified scoring); Stage 2 `check_avoid_compliance()` in `suggestions.py` (mini LLM, gpt-5.4-mini on cloud, main model on local, falls back to all candidates on error); Stage 3 `select_tracks()` in `suggestions.py` (compact prompt — approved artists + taste summary, no deny list, no full profile JSON, no RAG pool); `build_taste_summary()` computes a ≤800-char taste string deterministically. Wired in `app.py` before the batch loop: staged path when RAG enabled + corpus loaded, legacy `build_messages`/`call_gpt` path otherwise. 20 new tests added (retrieve_candidates, check_avoid_compliance, select_tracks, build_taste_summary). 564 core tests pass.

Goal: replace the one mega-call with three small, focused calls. Each stage does one thing well.

## P1.1 — Stage 1: Code-side retrieval (no LLM) ✅

**Why**: The current RAG pool actively hurts quality (78% of dislikes were from the pool). The MusicBrainz corpus is biased toward vintage/classic rock, but it has all the data needed to filter — just not in the right shape.

**Implementation**: extend [core/src/rag/retrieval.py](core/src/rag/retrieval.py) with a `retrieve_candidates()` function that:
1. **Tag-match against `must_have`** — find artists whose tags overlap. Hard filter, not soft score.
2. **Tag-match against `avoid`** — exclude artists whose tags overlap. Hard filter.
3. **Tag-overlap from `primary_reference` seeds** — for each primary reference, look up the seed artist in the corpus by `spotify_id` (already matched in Phase 2 enrichment, commit `625af0a`), pull its `mb_tags ∪ spotify_genres`, and boost candidates whose tag set overlaps highly with the seed's. **No external Spotify call**: `GET /artists/{id}/related-artists` was removed in Spotify's February 2026 platform update (see [SKILL.md:50](SKILL.md#L50)). Tag-overlap on the enriched corpus reproduces what related-artists gave us — the corpus already groups artists by overlapping genres.
4. **Apply popularity band** — keep `0.3 ≤ popularity ≤ 0.7` (the discovery sweet-spot, not famous-but-not-obscure). Already in corpus from Phase 2 enrichment.
5. **Dedupe against history + confirmed + rejected** — code-side, not in prompt.

Output: 30–50 candidate artists. No LLM needed. Cost: $0.

**Files**:
- [core/src/rag/retrieval.py](core/src/rag/retrieval.py) — new `retrieve_candidates()`, plus a `seed_tag_overlap(seed_artist, candidates)` helper.
- No new Spotify wrappers (the prior plan's `get_related_artists()` and `core/src/rag/spotify_seed.py` are obsolete given the endpoint removal).

**Acceptance**: for the "Rock" profile, output includes ≥ 3 of: Foxy Shazam, Jukebox the Ghost, Mother Mother, Royal Republic, Major Parkinson, The Orion Experience, Crown Lands, The Wrecks (artists in the modern theatrical-quirky-pop-rock space the user actually wants). None of: Pink Floyd, U2, Springsteen, Led Zeppelin (avoid violators).

## P1.2 — Stage 2: Avoid-checker (mini LLM, fits 8 K easily) ✅

**Why**: GPT-5.4 ignored the explicit avoid list (26 of 27 dislikes mapped to an avoid trait). A second cheap pass that does *only* avoid-checking gives much better enforcement.

**Implementation**: new function `check_avoid_compliance(candidates, avoid_traits)` in [core/src/suggestions.py](core/src/suggestions.py):
- Input: list of 30–50 artist names + the `avoid` list (compact).
- Prompt: ~800 tok system + ~400 tok user. Output: ~50 tok (`["match", "reject", "match", ...]`).
- Model: gpt-5.4-mini (or local Qwen 2.5 7B / Llama 3.2 — easy to fit 8 K).
- Cost: ~$0.0008 per call (gpt-5.4-mini at $0.20/M in, $0.80/M out).

**Acceptance**: ≥ 90% of "match"-rated candidates do not get disliked when the user judges them. Measured against current 60% baseline.

## P1.3 — Stage 3: Track selection (main LLM, small focused prompt) ✅

**Why**: Now that retrieval and avoid-checking are done, the main LLM only needs to pick *which track* per artist and produce rationale. Prompt shrinks dramatically.

**Implementation**: new `select_tracks(approved_artists, taste_summary, batch_size)`:
- Input prompt: ~600 tok system + (artist list + taste_summary) ~1,500 tok user. **No deny list, no full profile JSON, no RAG pool.**
- Output: 10 tracks × ~120 tok = ~1,200 tok.
- Model: `DEFAULT_OPENAI_MODEL` (currently gpt-5.5). **Stays on the quality model — no swap to mini until Phase 5 A/B confirms no like-rate regression.** Quality is the gate; cost reduction in this phase comes from the smaller prompt, not from a cheaper model.
- Cost: ~$0.020 per call (similar to gpt-5.4 pricing; verify gpt-5.5 entry in [pricing.json](frontend/static/data/pricing.json)).

**`taste_summary`** is a 200-token compact string built from the profile (full taste-vector format comes in Phase 4):
```
Era: modern (post-2010 lean). Energy: high. Style: theatrical, quirky,
melodic. Must: punchy guitars, hooks, modern feel. Avoid: classic rock,
indie guitar rock dominance, synth-heavy. Anchors: Bear Ghost (theatrical
indie), Mrs. Green Apple (J-pop-rock), Tally Hall (art-pop).
```

**Acceptance**: per-batch input prompt drops from ~7 k tok to ~2.1 k tok and **like-rate does not regress vs the gpt-5.5 baseline established in P0.2**. Cost reduction (~57%) follows mechanically from the smaller prompt; it is measured but is not the gate at this phase.

## P1.4 — Wire stages into `run_pipeline` ✅
Replace the current monolithic loop in [app.py:657-833](app.py#L657-L833) with:
```
candidates = retrieve_candidates(profile)
approved = check_avoid_compliance(candidates, profile.avoid)  # mini LLM
tracks = select_tracks(approved, taste_summary, batch_size)   # main LLM
verified = spotify_verify(tracks)
```

Keep the existing `MAX_GPT_CALLS_PER_RUN`, `MAX_CONSECUTIVE_EMPTY_BATCHES`, retry-with-explicit-deny logic — those stay in Stage 3.

**Acceptance**: end-to-end 30-track run completes in ≤ 60 s p95 and **like-rate ≥ 70%** (vs current 60.3%). Cost is measured and reported but is **not a pass/fail gate at this phase** — Goal #2 lands fully after Phase 3 (AI Profile Update reform) and is re-tested under Phase 5 (model A/B).

## Phase 1 — Code review feedback applied 2026-04-26

Code review of the Phase 1 commit surfaced 5 blockers for the eval-period analytics + 8 correctness/polish items. All addressed in a follow-up before the eval period starts. 572 core tests pass (8 new). Two action items still open for the user (bottom of this section).

### Blockers — telemetry plumbing for the eval period

The eval period needs to compare **AI Profile Update**, **Playlist Generation**, and **Band/Song Analysis** on cost, latency, and quality. Phase 1 as shipped only logged Playlist Generation. Five gaps fixed:

| ID | Fix | Where |
|---|---|---|
| B1 | Stage 2 mini-LLM cost/latency emitted as `kind: "stage2_summary"` rows. `check_avoid_compliance` now returns `(approved, meta)` with `status` ∈ `ok`/`empty_response`/`error`/`skipped_*`. | [core/src/suggestions.py:884](core/src/suggestions.py#L884), [core/src/eval_log.py:444](core/src/eval_log.py#L444), [app.py:854-873](app.py#L854-L873) |
| B2 | AI Profile Update telemetry: `call_gpt_json_with_meta` returns usage + latency. `train_profile` + `draft_profile_from_playlist` write `kind: "profile_update_summary"` rows with before/after profile hashes. | [core/src/openai_http.py:330](core/src/openai_http.py#L330), [core/src/profile.py:629-696](core/src/profile.py#L629-L696), [core/src/profile.py:846-893](core/src/profile.py#L846-L893) |
| B3 | Band/Song Analysis writes `kind: "analysis_summary"` rows with quality counts (`genre_count`, `style_tag_count`, `suggestion_count`). | [core/src/analysis.py](core/src/analysis.py), [core/src/eval_log.py:489](core/src/eval_log.py#L489) |
| B4 | `compute_config_signature` buckets `extra={"phase1_pipeline": …}` so legacy vs staged runs join cleanly in pandas. | [app.py:680-704](app.py#L680-L704) |
| B5 | `log_batch_summary` adds first-class `stage1_candidate_count` / `stage2_approved_count`. Per-track `in_candidate_pool` now derives from the **binding** constraint set: Stage 2 approved on the staged path, legacy RAG pool on the legacy path — pre-Phase-1 vs post-Phase-1 numbers are no longer silently incomparable. | [core/src/eval_log.py:236-352](core/src/eval_log.py#L236-L352), [app.py:740-758](app.py#L740-L758) |

### Correctness / robustness

| ID | Fix | Where |
|---|---|---|
| C1 | `_collect_forbidden_artists` → public `collect_forbidden_artists` (private symbol no longer crosses module boundary into `app.py`). | [core/src/suggestions.py:242](core/src/suggestions.py#L242) |
| C2 | Dead `+20` buffer arm in `select_tracks` removed (the staged path excludes `emerging_only`, so the branch was unreachable). | [core/src/suggestions.py:967](core/src/suggestions.py#L967) |
| C3 | `isinstance(profile, dict)` guard added to the history lookup in `select_tracks` for symmetry with the prefs guard above it. | [core/src/suggestions.py:1067](core/src/suggestions.py#L1067) |
| C4 | Stage 2 failure modes surface in the eval log via `stage2_summary.status` rather than silently degrading to "blocking nothing". | [core/src/suggestions.py:909-960](core/src/suggestions.py#L909-L960) |
| C5 | `run_pipeline` now distinguishes three Stage-2-empty cases: Stage 1 empty → legacy fallback; Stage 2 errored (handled internally with passthrough); Stage 2 correctly rejected all → stay on staged path with a warning so the user/analyst sees the constraint bind, not a silent fallback. | [app.py:822-849](app.py#L822-L849) |
| C7 | `validate_pricing_entries()` runs at app startup; logs any model in `{DEFAULT_OPENAI_MODEL, STAGE2_MODEL}` missing from `pricing.json`. Currently fires for `gpt-5.5` (CF-Bug-4 — entry never added). | [config.py:687-712](config.py#L687-L712), [app.py:177-188](app.py#L177-L188) |
| C8 | `latency_s` moved out of `prompt_components` (where it polluted a "what was sent in chars" dict) to a top-level field on the batch_summary row. | [core/src/eval_log.py:355-358](core/src/eval_log.py#L355-L358) |

### Polish

- `retrieve_candidates` avoid-threshold floor scales with `target_size` so the filter is reachable for small targets used in unit tests (was previously hard-pinned at 10). [core/src/rag/retrieval.py:506-509](core/src/rag/retrieval.py#L506-L509)
- Top-of-file `from config import …` block in `app.py` consolidated; nested `from config import RETRIEVE_CANDIDATES_SIZE, RAG_POPULARITY_PENALTY` removed.
- `TestCheckAvoidCompliance` cleaned up (unused `MagicMock` block); new tests cover meta-dict shape + `error`/`empty_response` status paths.
- New `test_eval_log` cases pin the new row kinds and the top-level `latency_s` placement.

### Eval row schema (cheat sheet for analysts)

All rows live in `eval.jsonl`, gated on `DEBUG_MODE`. Join on `run_id` (within a generation run) or `profile_id` + `config_signature` (across runs).

| `kind` | Frequency | Key cost/latency/quality fields |
|---|---|---|
| `track` | per AI-suggested track | `found_on_spotify`, `in_candidate_pool` (now binding-set membership), `rationale_types`, `rationale_args`, `has_must_have_cite` |
| `batch_summary` | per Stage-3 LLM call | `latency_s` (top-level), `usage`, `prompt_components`, `gpt_returned_count`/`after_filter_count`/`spotify_found_count`/`in_pool_count`, `stage1_candidate_count`, `stage2_approved_count`, `rationale_stats`, `config_signature` (incl. `phase1_pipeline`) |
| `run_summary` | per generation run | `total_wall_s`, `batch_latency_s.{p50,p95,max}`, `verified_count` |
| `stage2_summary` | per generation run (staged path only) | `candidates_in`, `approved_out`, `avoid_traits_count`, `status`, `latency_s`, `usage`, `prompt_chars` |
| `profile_update_summary` | per `train_profile` + per `draft_profile_from_playlist` | `label`, `status`, `latency_s`, `usage`, `prompt_chars`, `response_chars`, `profile_hash_before`/`profile_hash_after` |
| `analysis_summary` | per `analyze_band_song` | `artist`, `track`, `status`, `latency_s`, `usage`, `prompt_chars`, `response_chars`, `genre_count`, `style_tag_count`, `suggestion_count` |

### Action items still open

1. **Confirm `DEBUG_MODE=1`** in the test user's `settings.conf` *before* the eval period starts — all eval-log writes are gated on it. Without this, no rows are written and the comparison is impossible. (The evaluation harness below sets this automatically inside its sandbox; this item only matters for ad-hoc dev-server testing.)
2. **Add a `gpt-5.5` entry** to [frontend/static/data/pricing.json](frontend/static/data/pricing.json) (CF-Bug-4). The startup warning will keep firing until then, and both the in-app cost estimator AND the evaluation comparison report will under-report cost for the default model.

## Phase 1 — Evaluation harness 2026-04-26

Manual A/B testing across three models (gpt-5.5 / gpt-5.4 / gpt-5.4-mini) is too slow and too noisy to be useful as a feedback loop during the rest of the rework. The evaluation harness automates one canonical scenario across all models and produces a single `comparison.md` per invocation.

> **Future agents: this harness exists. If you are tuning a model, prompt size, or pipeline stage and would benefit from before/after numbers, run it.** Do not reinvent it. Do not invoke it on a normal run — it is real-money / real-Spotify and only runs when the user explicitly asks ("call the evaluation tests").

### How to invoke

```bash
python evaluation/run_evaluation.py
```

The script prints a plan + cost estimate and waits for `y/N` confirmation. Use `--no-confirm` to skip the prompt in scripts. Use `--cleanup-only` to sweep orphaned `[EVAL] …` Spotify playlists after a hard kill.

The agent should run this **only when the user says "call the evaluation tests"** (or similar explicit phrasing). Do not invoke it as a side effect of any other request.

### What it does (one cycle per model)

1. Fresh profile in an isolated sandbox app dir (`SPOTYVIBE_APP_DIR` env override added in [config.py:183](config.py#L183)).
2. `train_profile()` with the canonical seed sections from [evaluation/scenario.py](evaluation/scenario.py) (modern theatrical-quirky-pop-rock, fixed across all model runs).
3. `analyze_band_song("Bear Ghost", "Mr. Bubbles")`.
4. `/api/run` via Flask test client → real Stage 1 retrieval → real Stage 2 mini-LLM → real Stage 3 selection → real Spotify verify.
5. Push the verified tracks to a Spotify playlist named `[EVAL] {model} {ts}`.
6. Apply deterministic feedback: like indices `(0, 3, 6, 9, 12)`, dislike indices `(2, 7, 11)`.
7. `train_profile()` again with refine sections to absorb the feedback.
8. **`finally`-block cleanup**: delete the Spotify playlist, delete the sandbox profile.

### Output

```
evaluation/results/{ts}/
  harness.log
  comparison.md                    # cost / latency / quality table per (model, iter)
  {model}-iter{n}/
    eval.jsonl                     # raw per-feature telemetry rows
    summary.json                   # ModelRunResult dump
```

`comparison.md` covers per-run rollup (cost, p50/p95, Spotify-found rate, must-have cite rate, Stage 2 status, cleanup status) plus a feature-level cost breakdown (Stage 3 vs Stage 2 vs Profile Update vs Analysis) plus a row-count sanity check (telemetry must fire for every feature — 0 rows in any column means the harness or production code regressed).

### Files

| File | Purpose |
|---|---|
| [evaluation/run_evaluation.py](evaluation/run_evaluation.py) | CLI entry point, sandbox setup, orchestration loop |
| [evaluation/harness.py](evaluation/harness.py) | One `ModelRunResult` per (model, iteration); cleanup in `finally` |
| [evaluation/scenario.py](evaluation/scenario.py) | Canonical seed + deterministic feedback rule (do NOT parametrise per-model) |
| [evaluation/reporting.py](evaluation/reporting.py) | `eval.jsonl` → `summary.json` + `comparison.md` |
| [evaluation/README.md](evaluation/README.md) | Prerequisites, safety notes, extension points |
| [evaluation/settings.ini.example](evaluation/settings.ini.example) | Template — copy to `settings.ini` (gitignored) and fill in |
| [core/tests/test_evaluation_scenario.py](core/tests/test_evaluation_scenario.py) | Pins the canonical scenario constants — fast unit tests, no real calls |

### Prerequisites

- Authorize Spotify once via the dev server (`python app.py`, click "Connect to Spotify" in the browser). The harness re-uses your real `.spotify-cache` so OAuth doesn't have to run from a non-interactive script.
- `cp evaluation/settings.ini.example evaluation/settings.ini`, then fill in `[openai] api_key`, `[spotify] client_id`, `[spotify] client_secret`. The file is gitignored.
- Optional: add `gpt-5.5` to `frontend/static/data/pricing.json` so the comparison report shows real $ figures for the default model.

### Cost

Approx ~$0.30 per full evaluation (3 models × 1 iteration, playlist_size=30). gpt-5.5 dominates. Re-running is intentionally billable — the user explicitly accepted this trade-off in favour of having a reusable feedback loop.

### Safety properties

- **Sandbox isolation.** All production code reads/writes inside `evaluation/sandbox/{ts}/` for the duration of the run. The user's real profile, real eval log, and real settings are untouched.
- **Tagged playlists.** Every playlist starts with `[EVAL] ` so `--cleanup-only` can sweep the account safely.
- **Cleanup in `finally`.** Each model run's cleanup runs even on uncaught exception or `KeyboardInterrupt`. If the process is `kill -9`'d, run with `--cleanup-only` to sweep orphans.
- **No production-code modifications.** The only seam is `SPOTYVIBE_APP_DIR` in `config._get_app_dir()`. Future harness extensions should add new seams in `config.py`, not monkey-patch in the harness.

### When to run

- **Before adopting a cheaper model in any stage** (gates on Goal #1: dislike rate ≤ 25%).
- **After non-trivial prompt changes** (taste_summary format, system prompt restructure, validation block tweaks).
- **After pipeline restructures** (new stage, retrieval algorithm change, audio-filter changes).
- **Before tagging a release** so the changelog can cite hard before/after numbers.

If you find yourself manually running the dev server multiple times to compare two model variants — stop, run `python evaluation/run_evaluation.py`, and read `comparison.md`. That is what it exists for.

---

# Phase 2 — Quality enforcement (weeks 3–4)

Goal: stop violating the constraints we already collect.

## P2.1 — Demote `confirmed` from suggestion source
The system prompt says confirmed = "style anchors, NOT suggestion pool" but GPT recycled them in 43% of suggestions. Fix: treat `confirmed` exactly like `history.suggested_artists` — a deny list for new suggestions. Anchors are now communicated only via the `taste_summary` natural-language description.

**File**: [suggestions.py:535-538](core/src/suggestions.py#L535-L538) — add confirmed to `deny_keys` unconditionally.

**Acceptance**: confirmed-artist recycling drops to ≤ 5% in a fresh run (down from 43%).

## P2.2 — Tracking primary-reference yield
Primary-reference seeding is implemented in P1.1 step 3 (corpus tag-overlap, no Spotify graph call). This phase adds **tracking only**: log how many of each batch's suggestions originated from a primary-reference seed (new field in `batch_summary`). Target: ≥ 30% of suggestions originate from a primary-reference seed (today: 0 / 5 references hit).

## P2.3 — Code-side semantic avoid checker (post-LLM safety net)
Even with Stage 2 avoid-checking, some violations slip through (e.g. tracks that match an avoid trait the model didn't recognize). Add a final pass after Spotify verification that:
- Pulls each verified track's Spotify genres.
- Cross-references against the `avoid` list using a precomputed mapping (e.g. "classic rock" → spotify genre `"classic rock"`, `"album rock"`, `"hard rock"`).
- Drops matches; logs to telemetry.

**File**: new `core/src/rag/avoid_filter.py`. Mapping seeded from MusicBrainz tag aliases.

**Acceptance**: dislike rate ≤ 25% measured over a full week of real usage (≥ 100 judged tracks).

---

# Phase 3 — Profile reform (week 4–5)

Goal: AI Profile Update should be cheap, bounded, and absorb feedback over time.

## P3.1 — `train_profile()` sends only mutable sections
**File**: [core/src/profile.py:561-641](core/src/profile.py#L561-L641)

Today: sends entire 26 KB profile, gets back entire 26 KB profile. ~$0.094 per call.

After: sends only `meta`, `preferences` (must_have, soft_preferences, avoid, core_description, vibe_description), and the new training input. Strips `history`, `feedback.liked_tracks/disliked_tracks`, `artists.confirmed/moderate/rejected`, `taste_rules`. Asks GPT to return only the same mutable sections. Merges code-side.

Cost projection: ~$0.015 per AI Profile Update (84% saving).

**Acceptance**: AI Profile Update completes in < 5 s, costs < 2 ¢, and the user-visible profile fields update correctly. Verified by snapshot-comparing the post-update profile against an equivalent run on the old code.

## P3.2 — Consolidation step on overgrowth
After each AI Profile Update, if `soft_preferences` > 8 entries OR `avoid` > 8 entries OR `meta.goal` > 600 chars, append a one-shot consolidation call:

```
"These overlap. Consolidate to ≤ 8 distinct ideas, preserving meaning.
Return only the consolidated arrays."
```

Single mini-LLM call, ~$0.001. Bounds profile growth structurally.

**File**: [core/src/profile.py](core/src/profile.py) — new `_consolidate_oversized_sections()`.

**Acceptance**: profiles do not exceed 12 KB after 10 successive AI Profile Updates with feedback (today's profile is 26 KB after fewer than 10 updates).

## P3.3 — Periodic feedback absorption
Liked/disliked reasons accumulate in `feedback.liked_tracks[*].reason` and `feedback.disliked_tracks[*].reason`. They drive nothing today.

After every 20 new feedback entries (or weekly, whichever first), run a one-shot LLM call that:
1. Reads the last 20 reasons from each side.
2. Suggests additions/edits to `must_have`, `soft_preferences`, `avoid` (delta only, not full sections).
3. Surfaces the proposed deltas in the UI as a non-blocking tip toast: *"Based on recent feedback, your profile would benefit from adding X to avoid. Apply?"*

User confirms before write. Cost: ~$0.01 per absorption. Frequency: ~weekly for an active user.

**File**: new `core/src/feedback_absorption.py`. New endpoint `POST /api/profile/absorb-feedback`. New tip in [tips.js](frontend/static/js/modules/tips.js).

**Acceptance**: after absorbing 20 disliked-track reasons, the resulting profile must include at least 2 new `avoid` entries derived from recurring reasons. Verified by manual review on a seeded test profile.

---

# Phase 4 — Compact taste vector (week 6+)

Goal: promote P1.3's freeform `taste_summary` string into a structured `taste_vector` object computed once per AI Profile Update. Replaces the last hand-written summary with a deterministic, comparable representation that Stage 1 retrieval and Stage 2 avoid-checking can also consume directly.

## P4.1 — Define schema
```json
{
  "schema_version": 1,
  "computed_at": "2026-04-25T12:00:00Z",
  "axes": {
    "era_lean": "modern",          // vintage | mixed | modern
    "energy": "high",              // low | mid | high
    "complexity": "high",          // simple | mid | complex
    "theatricality": 0.9,          // 0..1
    "polish": 0.4,                 // 0..1 (low = lo-fi, high = polished)
    "vocal_emphasis": 0.7
  },
  "primary_anchors": ["bear_ghost", "mrs_green_apple", "tally_hall"],
  "must_have_tags": ["quirky", "punchy guitars", "hooks", "modern"],
  "avoid_tags": ["classic_rock_straight", "indie_guitar_dominant", "synth_heavy"],
  "language_pool": ["en", "ja"],
  "discovery_temp": 0.6            // 0=conservative, 1=adventurous
}
```

Stored in profile.json under new `taste_vector` key. Computed by AI Profile Update. Used by Stage 1 retrieval (axes + tags), Stage 2 avoid-checker (avoid_tags), and Stage 3 selector (full vector as compact prompt).

## P4.2 — Compute on AI Profile Update
Extends P3.1's reduced-scope train_profile to also emit `taste_vector`. One-time migration tool: `python build-tools/migrate_profile_taste_vector.py <profile_id>` derives a vector for existing profiles.

## P4.3 — Use throughout pipeline
Stage 1 (`retrieve_candidates`) reads `axes` + `must_have_tags` + `avoid_tags` directly.
Stage 2 (`check_avoid_compliance`) reads `avoid_tags` only.
Stage 3 (`select_tracks`) gets the full vector serialized as ~200-token natural language.

**Acceptance**: Stage 3 input prompt drops from ~2.1 k tok (post-P1.3 freeform `taste_summary`) to ≤ 1.5 k tok (structured serialization). Like-rate matches or beats the P1 baseline. Stage 1 retrieval becomes deterministic given identical `axes` + tags, so retrieval can be regression-tested in CI.

---

# Phase 5 — Quality-validated cost A/B + local-LLM optimizations (after architecture stable)

Goal: with the architecture stable and quality locked in on quality models (Phase 1–4), test whether cheaper models hit the same like-rate. Separately, optimize the parts of the pipeline we control so local LLMs feel responsive despite slower model throughput.

## P5.1 — Model A/B harness (cost gated on quality)
Once eval-log telemetry is wired (P0.2) and `compute_config_signature` is in use, run paired comparisons against the locked Phase 1–4 quality baseline:
- **Stage 3 selector**: gpt-5.5 (baseline) vs gpt-5.5-mini (when available) vs gpt-5.4-mini.
- **Stage 2 avoid-checker**: gpt-5.4-mini (default mini) vs Llama 3.2 3B (local) vs Qwen 2.5 7B (local). Stage 2 is binary classification — the lowest-risk place to switch to mini or local first.
- **AI Profile Update**: gpt-5.5 (baseline) vs gpt-5.5-mini. This drives core profile evolution; only swap if quality holds.

**Decision rule**: adopt the cheaper variant only if its like-rate is within 1 percentage point of the baseline over ≥ 100 judged tracks. Otherwise stay on the quality model and accept the higher cost — Goal #1 dominates Goal #2.

## P5.2 — Local-LLM path
Stages are now small enough for the 8 K floor:
- Stage 1: no LLM (free, runs anywhere).
- Stage 2: ~1,300 tok in, ~50 tok out — fits 8 K with massive headroom.
- Stage 3: ~2,100 tok in, ~1,200 tok out (3,300 total) — fits 8 K with room. **At 16 K (recommended), Stage 3 can grow `batch_size` from 5 to 10 with output room to spare.**

Add `BATCH_SIZE_WITH_LOCAL = 5` gated on `get_llm_provider_preset() in LOCAL_PRESETS`. Auto-detect 16 K+ context via the model's reported `n_ctx` (Ollama) or `context_length` (LM Studio) and bump to `BATCH_SIZE = 10` when available.

**Documentation**: settings tooltip on the model picker should state "8 K context minimum, 16 K recommended for full batch sizes." Surface clearly in onboarding.

## P5.3 — Latency optimizations (the parts we control)
Local model throughput is bounded by user hardware — but everything else can be made fast. Goal: even on a slow local model, the user sees progress immediately and never waits for a fully-finished playlist before interacting.

- **Pipeline overlap (backend)**: kick off Stage 1 retrieval for batch N+1 while Stage 3 LLM runs for batch N. Stage 1 is pure CPU/IO, so this is wall-clock saving with no extra cost.
- **Streaming results (frontend)**: send each verified batch to the UI as it completes (SSE or chunked JSON in [app.py](app.py)) instead of waiting for the full 30-track run. The user can start liking/disliking after the first batch lands.
- **Skeleton rendering (frontend)**: show placeholder track slots for the in-flight batch so the UI conveys "X of 30 done" continuously, not just on completion.
- **Spotify verification parallelization**: each batch's tracks can be verified in parallel — currently sequential. Bounded concurrency (e.g. 5) to respect rate limits.
- **Optimized local prompts**: re-tune Stage 3 system prompt for terser outputs on local models (less padding tokens to generate = less wall-clock time on slow models).

**Acceptance**:
- Cloud (gpt-5.5): full 30-track run ≤ 60 s p95 (Goal #3). **Time-to-first-batch ≤ 12 s p95** so the user sees suggestions within ~10 s of clicking "go".
- Local Llama 3.2 3B (Ollama, 8 K): full run < 120 s with like-rate within 15 pp of cloud baseline.
- Local Qwen 2.5 14B (16 K): full run < 90 s with like-rate within 10 pp of cloud baseline.

---

# Carry-forward: open bugs not in scope of the cost/quality rework

These are real bugs that need fixing but don't fit the phased architecture work above. They get picked up in normal sprint flow.

## CF-Bug-1 — Player auto-advance regression (re-opened)
History: items 5 & 11 in old todo.md both "fixed" this. User reports it broken again 2026-04-22.

Investigation steps (carried over):
1. Reproduce against current build (Web Playback SDK path).
2. Add explicit logging around `_sdkLastPositionMs`, `_sdkPaused`, `_sdkCurrentTrackId`, ticker projection.
3. Consider belt-and-braces wall-clock timeout: fire `nextPreview()` after `duration + 2000ms` if neither ticker nor SDK handler advanced.

**File**: [frontend/static/js/modules/preview.js](frontend/static/js/modules/preview.js)

## CF-Bug-2 — Player title wrap stretches in some cases
Item 13 added `-webkit-line-clamp` but user reports stretching persists. Re-verify and tighten CSS.

**File**: [frontend/static/css/preview.css](frontend/static/css/preview.css)

## CF-Bug-3 — Like/dislike click breaks player initialization
Hitting like/dislike on a track keeps current song playing instead of advancing, and afterwards the player can no longer initialise the next song. Likely tied to CF-Bug-1.

**File**: [frontend/static/js/modules/feedback.js](frontend/static/js/modules/feedback.js) interaction with [preview.js](frontend/static/js/modules/preview.js).

## CF-Bug-4 — Verify GPT-5.5 default-model wiring (mostly shipped)
**Status**: gpt-5.5 is already the default ([config.py:77](config.py#L77)) and listed first in `OPENAI_SUPPORTED_MODELS_JSON`. Remaining checks: confirm gpt-5.5 pricing entry exists in [pricing.json](frontend/static/data/pricing.json), confirm `documentation/TechnicalManual.md` § Models reflects the new default, confirm no `_VALIDATION_BLOCKS` entry references the old default.

## CF-Doc-1 — UserManual + README catch-up
- `documentation/UserManual.md` — add "Dislike a whole artist" subsection (already in help.{en,de,jp}.md).
- `README.md` — describe the offline-corpus prompt and the artist-dislike behaviour.

## CF-Bug-5 — Batch-summary token counts are always `None`
`log_batch_summary` receives `llm_usage=None` on every batch despite `call_gpt(return_meta=True)` returning a meta dict. The `_llm_meta` dict is captured and `_batch_latencies` accumulates correctly (run_summary has valid p50/p95), but the usage part never reaches `log_batch_summary`. Root cause likely: `_emit_batch_summary` closure in `app.py` is not forwarding `_llm_meta` to the call. Net effect: we have latency telemetry but zero token-count data — Goal #2 cost reconciliation is unmeasurable until fixed.

**File**: [app.py](app.py) `_emit_batch_summary` closure — verify `llm_usage` argument.

## CF-Bug-6 — Track removal does not stop playback; other tracks cannot start
Removing a track from the playlist leaves it playing in the preview player. After removal, clicking play on any other track does nothing — the player is stuck. Likely: the removal handler doesn't call `stopPreview()` / reset player state, so the player believes a track is still active and ignores new play requests.

**File**: [frontend/static/js/modules/feedback.js](frontend/static/js/modules/feedback.js) (removal handler) + [frontend/static/js/modules/preview.js](frontend/static/js/modules/preview.js) (player state reset). Likely related to CF-Bug-1 and CF-Bug-3.

## CF-Bug-7 — Settings Save button has no loading indicator
The `saveSettings()` call can take several seconds (API key validation, model fetch). During this time the button gives no visual feedback, causing users to click multiple times and submit duplicate saves. Fix: disable the Save button and show a spinner immediately on click; re-enable on completion or error.

**File**: [frontend/templates/modals/settings_modal.html](frontend/templates/modals/settings_modal.html) + whichever JS module handles `saveSettings()`.

## CF-Test-1 — Brittle Playwright selectors
Replace `text=⚙️ Settings` and `>> text=...` selectors in [frontend/tests/test_page_load.py](frontend/tests/test_page_load.py) and [frontend/tests/test_modals.py](frontend/tests/test_modals.py) with `aria-label` / `data-menu-item` hooks.

## CF-Test-2 — Profile cache TOCTOU
[core/src/profile.py:202-204](core/src/profile.py#L202-L204) — stat→read race. Only relevant if multiple processes write the profile (currently single-user desktop). Defer until hosted variant.

## CF-Test-3 — Add tests pinning P0/P1/P2 changes
For each phase that ships, add tests covering the new contracts (Stage 1 retrieval shape, Stage 2 avoid-checker output, Stage 3 prompt size, P3.1 reduced-scope train, P3.2 consolidation, P3.3 absorption).

---

# Carry-forward: design rationale to preserve

These are the *whys* from the old rag-implementation.md that should survive. Will become the §RAG section of `documentation/TechnicalManual.md`.

## CF-Rat-1 — RAG pool size evolution (20 → 100, justified)
Initial 20-slot pool was expanded to 100 because eval data showed only ~19% of GPT picks came from the pool — too narrow to anchor an eclectic profile. Stratified retrieval (must_have 50%, soft 25%, primary_reference 15%, tags 10%) ensures all profile dimensions get representation.

**Status under new plan**: stratified scoring stays, but the *output* of the scorer changes — Phase 1 uses it to build candidates for Stage 1 retrieval, not a 100-artist prompt block.

## CF-Rat-2 — Popularity penalty (`RAG_POPULARITY_PENALTY = 0.4`)
Formula: `final_score = tf_idf_score * (1 - 0.4 * popularity_normalised)`. Discovery sweet-spot band `0.3 ≤ popularity ≤ 0.7` (not famous, not obscure).

Tune post-A/B once Phase 1 is shipped and we have new like-rate data.

## CF-Rat-3 — Sparse retrieval over embeddings
TF-IDF + tag matching chosen over sentence-transformers because:
- The corpus is already human-curated tags (no semantic gap to bridge).
- Workload is short-tail filtering, not fuzzy similarity.
- Debuggability — you can read the score breakdown.

`score_artists()` interface is the replacement seam if "profile mentions a vibe with no exact tag match" becomes a measured failure mode.

## CF-Rat-4 — Pre-1960s artist filter
`MIN_ARTIST_BEGIN_YEAR = 1960` in both build pipeline and runtime corpus iteration. Historical/classical artists dominate tag-weighted rankings but don't fit modern music discovery.

## CF-Rat-5 — Corpus storage location
Moved from `BASE_DIR/data/rag_corpus/` to `%LOCALAPPDATA%/spotyvibe/rag_corpus/` so the corpus survives PyInstaller-EXE launches. One-time migration on startup.

## CF-Rat-6 — Cloud Run RAG service (deferred, design preserved)
Scenario C.2 from the old todo.md: `POST /api/rag/score_artists` shim wrapping `core/src/rag/retrieval.py`, reading corpus from GCS instead of GitHub Releases. Stays free (~2 k vCPU-sec/mo, well inside always-free tier). Unblocks Android. Implementation guide already in [documentation/guides/cloud-run-rag-setup.md](documentation/guides/cloud-run-rag-setup.md).

**Status**: defer until after Phase 5 (local-LLM stable). The remote RAG endpoint is identical regardless of pipeline architecture.

---

# Carry-forward: reference numbers

| Constant | Value | Rationale |
|---|---:|---|
| `MIN_ARTIST_BEGIN_YEAR` | 1960 | Pre-1960 artists don't fit modern discovery |
| Top-N for corpus build | 350,000 | 100K missed niche; 500K+ no measurable recall gain |
| Resident memory after slimming | ~200 MB | Acceptable for desktop |
| `RAG_POPULARITY_PENALTY` | 0.4 | Starting coefficient, tune post-A/B |
| Discovery sweet-spot band | 0.3 ≤ popularity ≤ 0.7 | Not famous, not obscure |
| `RAG_POOL_SIZE` (legacy) | 100 | After expansion from 20 |
| Stratified facet weights | must=0.50, soft=0.25, ref=0.15, tags=0.10 | Tuned for 60-slot default |
| RAG hallucination uplift | +30.7 pp Spotify-found | 63.8% → 94.5% (Apr 2026 eval) |
| Pool target hit rate (post-stratified) | ≥ 40% | From Apr-21 decision report |
| Per-batch input tokens (current, measured) | 6.5–7.5 k | Per P0 baseline |
| After Phase 0 trims (target) | ~4 k | Compact JSON + feedback strip |
| After Phase 1 (Stage 3, freeform `taste_summary`) | ~2.1 k | Three-stage split |
| **After Phase 4 (target, structured `taste_vector`)** | **≤ 1.5 k** | Stage 3 only |
| Pricing gpt-5.4 | $3 / $12 per M tok | input / output |
| Pricing gpt-5.4-mini | $0.20 / $0.80 per M tok | 15× cheaper |
| Pricing gpt-5.5 | verify in `pricing.json` | currently the default model |
| Cloud Run task timeout (build) | 60 min | Hard ceiling by design |
| Cloud Run free tier | 180 k vCPU-sec/mo | Workload uses ~2 k |

---

# Migration log (2026-04-25)

The two old files were deleted in this commit. Migration steps that were performed:

1. **Cross-reference scan** — found 15 references across code comments and docs. All updated to point at [documentation/TechnicalManual.md](documentation/TechnicalManual.md) §"RAG design reference" (newly added) or this file's CF-Rat-6 (for the deferred Cloud Run remote-RAG scenario).
2. **Substantive design rationale** from `rag-implementation.md` (per-artist schema, retrieval scoring formula, stratified retrieval rationale, pool-size sweet-spot data, sparse-over-embeddings choice, hallucination measurement guide, token budget, KV-cache placement) **migrated into** [documentation/TechnicalManual.md](documentation/TechnicalManual.md) §"RAG design reference".
3. **Open items from `todo.md`** (re-opened bugs, deferred features, false-shipped reckoning) consolidated into this file's Phase 0 + Carry-forward sections.
4. Both source files deleted in the same commit so reviewers can verify nothing was lost.

---

# Sequencing summary

| Week | Phase | Effort | Risk |
|---|---|---|---|
| 1 | P0 (bleed stop, telemetry, false-shipped fixes) | ~2 days | None |
| 2–3 | P1 (three-stage pipeline) | ~5 days | Medium — new architecture |
| 3–4 | P2 (constraint enforcement) | ~3 days | Low |
| 4–5 | P3 (AI Profile Update reform + absorption) | ~4 days | Medium — UI involvement |
| 6+ | P4 (taste vector) | ~3 days | Low (after P3) |
| Ongoing | P5 (cost A/B, local LLM, latency optimizations) | ~2 days/week sustained | Low |
| Ongoing | CF-Bug-1..3 (player regression) | as time permits | Independent |

**End-state cost & quality projection (two tiers)**

| Tier | Stage 3 model | Stage 2 model | AI Profile Update | Per run | Per AI Profile Update | Evening (5 runs + 3 AI Profile Updates) | Like rate target |
|---|---|---|---|---:|---:|---:|---:|
| Today | gpt-5.4 → 5.5 | n/a | gpt-5.4 → 5.5 | ~$0.15 | ~$0.094 | ~$1.00 | 60% |
| **After P1–P4 (quality models locked)** | gpt-5.5 | gpt-5.4-mini | gpt-5.5 | **~$0.06** | **~$0.015** | **~$0.36** | **≥ 75%** |
| **After P5 A/B (only if quality holds)** | gpt-5.5-mini or 5.4-mini | mini or local | gpt-5.5 | **~$0.005** | ~$0.015 | **~$0.07** | **≥ 75% (gated)** |

The **first tier** (~2.5–3× cheaper) comes purely from architectural changes — no model swap, no quality risk. It's the goal-1-and-2 deliverable. The **second tier** (~30× cheaper) requires Phase 5 A/B to confirm a cheaper model meets the like-rate floor; if it doesn't, we stay on tier 1 and accept the higher cost as the price of quality.

Latency target both tiers: **≤ 60 s p95** end-to-end on cloud (Goal #3). Time-to-first-batch ≤ 12 s p95 (P5.3). Local LLM bounded by user hardware; we own everything else (P5.2 + P5.3).

If only tier 1 lands, the rework still hits Goal #1 (quality) and most of Goal #2 (cost) in the first week of regular use. Tier 2 is upside, not a precondition.
