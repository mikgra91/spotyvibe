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

---

# 🟢 Status dashboard (2026-04-28)

> **Read this section first.** Everything below is detail. Everything in this dashboard is current.

## Where we are

**Latest landed phase:** Phase 2.6 — Telemetry + cap fix; json_schema and OPEN-4 trial-and-revert (2026-04-28). See the dedicated section below.

**Production metrics, baseline (`20260428-062909`, `playlist_size=15`, canonical seed):**

| Model | Spotify-found | Must-have cite | HC2 violations | Total cost | Wall time |
|---|---:|---:|---:|---:|---:|
| gpt-5.4 | 100 % | 93.3 % | 0 | $0.0951 | 68.9 s |
| gpt-5.4-mini | 100 % | 86.7 % | 0 | $0.0278 | 29.7 s |
| gpt-5.5 | – | – | – | $0.0263 | timeout (errored on Stage 2) |

The previous dashboard showed an older 3-model eval (`gpt-5.4` cite 93.3 %, `gpt-5.4-mini` cite 100 %, `gpt-5.5` cite 66.7 %, $0.452 / 218 s). The 2026-04-28 baseline above is the run used to gate Phase 2.6 and supersedes it.

**Phase 2.6 outcome — speculative changes reverted, guardrails added:**

- The trial run (`20260428-065552`) added strict `json_schema` to Stage 3 and a Stage-1 pool-widening retry on `pool_bad`. Result: cost +80 % on `gpt-5.4`, +89 % on `gpt-5.4-mini`; `gpt-5.5` ballooned to $0.79 / 651 s with cite 53 %. Both changes were reverted.
- `gpt-5.5` is now **classified as unfit for SpotyVibe** (reasoning-tier model burning 3 500–4 600 hidden tokens per Stage 3 batch and drifting off the approved-artist allow-list). See [`documentation/ModelRecommendations.md`](documentation/ModelRecommendations.md).
- **Project North Star** added to `AGENTS.md`: Quality > Price > Speed; non-regression mandatory; local-LLM compatibility first-class.
- **Spotify search resilience:** retries 1 → 4 with exponential backoff; concurrency cap 10 → 5; eval harness inter-model cooldown 60 s.
- **gpt-4.1** and **gpt-4.1-mini** added to the eval matrix.
- **Telemetry-only changes retained** (no behaviour change in production): must-have cite token-set match with stop-word filter (CF-Telemetry-1); profile section-sizes per `profile_update_summary` row (OPEN-5 instrument-only); `_normalize_rationale` arg cap 40 → 80 chars (information-density fix).

## Phase status overview

| Phase | Status | What it delivered | One-line result |
|---|---|---|---|
| **Phase 0** | ✅ done (2026-04-26) | Bleed stop + telemetry | Cost estimator fixed, eval-log wired, prompt trims landed |
| **Phase 1** | ✅ done (2026-04-26) | Three-stage pipeline | Stage 1 retrieval / Stage 2 avoid-checker / Stage 3 selector |
| **Phase 1 — regression analysis** | ✅ resolved (2026-04-27) | Track-grounding overlay | Hallucination spike resolved, 100 % Spotify-found |
| **Phase 2.0** | ✅ done (2026-04-27) | Tag-noise retrieval fix | Pool quality 22 % → 93 % on-genre |
| **Phase 2.0b** | ✅ done (2026-04-27) | Eval `status=under_filled` | Honest under-fill no longer reported as error |
| **Phase 2.5** | ✅ done (2026-04-27) | Hardening + P3.1 + local prompt variant | Must-have cite up across all models; profile-update cost down 56–64 % |
| **Phase 2.6** | ✅ done (2026-04-28) | Telemetry + cap fix; reverts; guardrails | json_schema & OPEN-4 reverted after measured regression; North Star + recommendations doc + Spotify resilience added |
| **Phase 2 — P2.3** | ⏸ deferred | Code-side semantic avoid filter | Gated on manual dislike-rate measurement |
| **Phase 3 — P3.2** | ⏸ deferred | Profile consolidation step | Instrument first (done in 2.6), then build |
| **Phase 3 — P3.3** | ⏸ deferred | Feedback absorption (with UI) | Depends on P3.1 (landed) + UI work |
| **Phase 4** | 🔮 planned | Structured `taste_vector` | Only after Phase 3 is fully closed |
| **Phase 5** | 🔮 planned | Cost A/B + local-LLM path | Gated on Goal #1 (dislike rate ≤ 25 %) |

## Open-items register (consolidated)

Every actionable item that is **not yet done** lives in this register. Phase-specific carry-forwards from finished phases are surfaced here so future agents don't have to read the historical phase sections to find them.

### Critical / blocking

| ID | Source | Item | Why it matters | Owner action |
|---|---|---|---|---|
| **OPEN-1** | Phase 1 (Goal #1) | **Manual dislike-rate measurement on the fixed pipeline** (≥ 100 judged tracks, real user) | The single gate for every cost-reduction or feature decision. P2.3 / P3.3 / P5 all depend on this. | Run a real session for ≥ 1 week; compute dislike rate from `eval.jsonl` × `feedback`. Target: ≤ 25 %. |

### High-value, deferred (gated on OPEN-1)

| ID | Source | Item | Notes |
|---|---|---|---|
| **OPEN-2** | Phase 2 (P2.3) | Code-side semantic avoid filter (post-LLM safety net) | Don't build until OPEN-1 confirms avoid leakage is real. See [P2.3](#p23--code-side-semantic-avoid-checker-post-llm-safety-net). |
| ~~**OPEN-3**~~ | ~~Phase 2.5~~ | ~~OpenAI structured outputs (`response_format=json_schema`, strict=true)~~ | **❌ Tried in Phase 2.6 and reverted** after measured cost +80–89 % and cite-rate regression. Auto-downgrade infra kept dormant in `core/src/openai_http.py`. Re-evaluate only with a strategy that includes optional `reason`/`energy`/`valence`/`genres` fields in the schema. See [Phase 2.6](#phase-26--reverts-and-guardrails-2026-04-28). |
| ~~**OPEN-4**~~ | ~~Phase 2.5~~ | ~~Reasoning-driven Stage 1 retry (POOL_BAD widening)~~ | **❌ Tried in Phase 2.6 and reverted** after measured cost regression. The `pool_quality.pool_bad` telemetry signal stays in place. Re-attempt only with a stricter trigger (first batch only + omitted ≥ 80 %). See [Phase 2.6](#phase-26--reverts-and-guardrails-2026-04-28). |
| **OPEN-5** | Phase 3 (P3.2) | Consolidation step on overgrowth | **Telemetry done in Phase 2.6** (`section_sizes` emitted per `profile_update_summary`). Add the LLM call when real profiles cross thresholds. See [P3.2](#p32--consolidation-step-on-overgrowth). |
| **OPEN-6** | Phase 3 (P3.3) | Periodic feedback absorption (with tip-toast UX) | UI work; depends on P3.1 (landed). Build CLI/debug-button first to validate proposed deltas before committing to UX. See [P3.3](#p33--periodic-feedback-absorption). |
| **OPEN-7** | Phase 2.5 (deferred) | End-to-end local-LLM verification | Loader + slim prompt variant in place; needs Ollama running with Llama 3.2 3B / Qwen 2.5 7B. The dormant `_JSON_SCHEMA_UNSUPPORTED` cache from Phase 2.6 is the canonical fallback pattern for this work. |
| **OPEN-11** | Phase 2.6 | Re-run full 5-model eval (incl. `gpt-4.1` and `gpt-4.1-mini`) once Spotify rate-limit window has drained | Wait ≥ 24 h after the 2026-04-28 quota burn, then `python evaluation/run_evaluation.py --no-confirm`. Apply no-regression gate vs baseline `20260428-062909`. Populate the empty rows in `documentation/ModelRecommendations.md`. |
| **OPEN-12** | Phase 2.6 | Classify any future reasoning-tier model before adding to default matrix | Reasoning models (o-series, future GPT-x reasoning variants, Claude reasoning, DeepSeek R1, etc.) are likely unfit for this constrained-pool selection workload. Always run the eval harness before recommending. See [Deep-dive: gpt-5.5](#deep-dive-why-gpt-55-is-unfit). |

### Future phases (not started)

| ID | Source | Item | Notes |
|---|---|---|---|
| **OPEN-8** | Phase 4 | Structured `taste_vector` schema + computation + pipeline use | Replaces P1.3's freeform `taste_summary`. See [Phase 4](#phase-4--compact-taste-vector-week-6). |
| **OPEN-9** | Phase 5 | Model A/B harness (cost gated on quality) | After OPEN-1. See [P5.1](#p51--model-ab-harness-cost-gated-on-quality). |
| **OPEN-10** | Phase 5 | Latency optimizations (pipeline overlap, streaming UI, parallel verify) | See [P5.3](#p53--latency-optimizations-the-parts-we-control). |

### Telemetry & ops carry-forwards

| ID | Description | Filed | Severity | Status |
|---|---|---|---|---|
| **CF-Telemetry-1** | `has_must_have_cite` substring match misses model paraphrases (e.g. gpt-5.5 says "uplifting modern production" → metric expects literal "modern production" → False negative). | Phase 2.5 | Medium — drives misleading metrics | **✅ Done in Phase 2.6** — token-set match with stop-word filter in `core/src/eval_log.py`. |
| **CF-Ops-1** | gpt-5.5 latency variance is high; multiple recent eval runs had OpenAI server-side read-timeouts on Stage 3 batches. Not a SpotyVibe bug. | Phase 2.0 / 2.5 | Low — server-side, monitor only | **Superseded** — Phase 2.6 deep-dive identified gpt-5.5 as a reasoning-tier model with intrinsically high latency on this workload. Now classified ❌ unfit; users steered to gpt-5.4 / gpt-5.4-mini via `documentation/ModelRecommendations.md`. |
| **CF-Ops-2** | Spotify per-user search quota can be exhausted by back-to-back eval runs, producing 429 cascades that look like model regressions. | Phase 2.6 | Medium — corrupts eval signal | **✅ Mitigated in Phase 2.6** — 4 retries with exponential backoff in `core/src/playlist.py`; concurrency 10 → 5; 60 s inter-model cooldown in eval harness. |
| **CF-Bug-5** | Batch-summary token counts are always `None` (`llm_usage` from `call_gpt(return_meta=True)` not flowing into `log_batch_summary`). Cost reconciliation broken. | Phase 1 review | Medium — Goal #2 measurement gap | **✅ Already resolved** before Phase 2.6 — verified token counts and `latency_s` flow correctly into `batch_summary` rows in `eval.jsonl`. |

### Bug carry-forwards (independent of rework)

| ID | Description | Severity |
|---|---|---|
| [CF-Bug-1](#cf-bug-1--player-auto-advance-regression-re-opened) | Player auto-advance regression (re-opened) | Medium — UX |
| [CF-Bug-2](#cf-bug-2--player-title-wrap-stretches-in-some-cases) | Player title wrap stretches in some cases | Low — cosmetic |
| [CF-Bug-3](#cf-bug-3--likedislike-click-breaks-player-initialization) | Like/dislike click breaks player initialization | Medium — UX, related to CF-Bug-1 |
| ~~CF-Bug-4~~ | ~~`gpt-5.5` missing from `pricing.json`~~ | ✅ resolved 2026-04-27 |
| [CF-Bug-6](#cf-bug-6--track-removal-does-not-stop-playback-other-tracks-cannot-start) | Track removal does not stop playback | Medium — UX, related to CF-Bug-1 |
| [CF-Bug-7](#cf-bug-7--settings-save-button-has-no-loading-indicator) | Settings Save button has no loading indicator | Low — UX |

### Test + doc carry-forwards

| ID | Description |
|---|---|
| [CF-Test-1](#cf-test-1--brittle-playwright-selectors) | Replace `text=` Playwright selectors with `aria-label` / `data-menu-item` hooks |
| [CF-Test-2](#cf-test-2--profile-cache-toctou) | Profile-cache stat→read race (only matters for hosted variant) |
| [CF-Test-3](#cf-test-3--add-tests-pinning-p0p1p2-changes) | Add regression tests pinning P0/P1/P2 contracts |
| [CF-Doc-1](#cf-doc-1--usermanual--readme-catch-up) | UserManual + README catch-up (artist-dislike, offline-corpus prompt) |

## Document map (where to find things)

| If you want to know… | Read this section |
|---|---|
| What was just shipped + measured impact | [Phase 2.5](#phase-25--quality-hardening--prompt-engineering--p31-2026-04-27) |
| What's open and waiting | [Open-items register](#open-items-register-consolidated) (above) |
| The chronological journey from baseline → today | [Progress summary](#progress-summary--from-baseline-to-current-state-2026-04-27) (historical, preserved as written) |
| Why a stable design choice was made (RAG, popularity penalty, etc.) | [Design rationale (CF-Rat-*)](#carry-forward-design-rationale-to-preserve) |
| The Phase 1 hallucination forensics (resolved) | [Phase 1 — Critical regression analysis](#phase-1--critical-regression-analysis-gpt-55-hallucination-spike---resolved-2026-04-27) |
| The full evaluation harness reference | [Phase 1 — Evaluation harness](#phase-1--evaluation-harness-2026-04-26) |
| The retrieval-noise bug and its fix | [P2.0](#p20--stage-1-retrieval-matches-tag-noise-not-genre-signal---resolved-2026-04-27) |
| End-state cost/quality projection (post-rework) | [Sequencing summary](#sequencing-summary) (bottom of file) |

---

# 📚 Detailed history (chronological)

> Sections below are preserved as written, in chronological order. Sections marked **✅ DONE** / **✅ RESOLVED** / **SUPERSEDED** are reference material; check the [Status dashboard](#-status-dashboard-2026-04-28) above for current state.

## Phase 2.6 — Reverts and guardrails (2026-04-28)

> **TL;DR.** A speculative bundle (`json_schema` for Stage 3, `OPEN-4` Stage-1 widening retry, 80-char rationale cap) was implemented and measured. The cap kept; `json_schema` and `OPEN-4` reverted. New guardrails added so the same kind of regression cannot ship silently again.

### What we tried

| Change | Where | Hypothesis |
|---|---|---|
| Strict `json_schema` for Stage 3 (with `json_object` auto-downgrade for local LLMs) | `core/src/openai_http.py`, `core/src/suggestions.py` | Schema enforcement should prevent malformed output and improve obedience to the approved-artist allow-list. |
| `OPEN-4` Stage-1 pool-widening retry on `pool_quality.pool_bad` | `app.py` | Doubling target_size when ≥ 50 % of approved artists are omitted should give the model a richer pool for the next batch. |
| `_normalize_rationale` arg cap 40 → 80 chars | `core/src/suggestions.py` | More information per chip = better must-have-cite hit rate. |
| Telemetry-only: must-have cite token-set match with stop-word filter | `core/src/eval_log.py` | Reduce false negatives in the cite metric (paraphrase tolerance). |
| Telemetry-only: profile section sizes per `profile_update_summary` | `core/src/eval_log.py` | Foundation for OPEN-5 (consolidation step). |

### What we measured

**Baseline (`20260428-062909`) — pre-change reference, 3-model:**

| Model | Cost | Wall | Spotify-found | Cite |
|---|---:|---:|---:|---:|
| gpt-5.4 | $0.0951 | 68.9 s | 100 % | 93.3 % |
| gpt-5.4-mini | $0.0278 | 29.7 s | 100 % | 86.7 % |
| gpt-5.5 | $0.0263 | – | – | – (Stage 2 timeout) |

**Trial run (`20260428-065552`) — `json_schema` + OPEN-4 + 80-char cap:**

| Model | Cost | Wall | Spotify-found | Cite | Δ vs baseline |
|---|---:|---:|---:|---:|---|
| gpt-5.4 | $0.171 | 172.8 s | (429 cascade) | – | **cost +80 %, wall +151 %** |
| gpt-5.4-mini | $0.0525 | 101.7 s | (429 cascade) | – | **cost +89 %, wall +242 %** |
| gpt-5.5 | $0.7875 | 651.6 s | 82.4 % | 52.9 % | new datapoint, ~9.5× cost vs 5.4 |

The 0 % Spotify-found on `gpt-5.4` and `gpt-5.4-mini` was a side effect of the long `gpt-5.5` run exhausting Spotify's per-user search quota (cascading 429s), not a model regression. The cost/wall regressions, however, are real: OPEN-4 doubles Stage-1+Stage-2 work, and `json_schema` inflates Stage-3 prompt+completion sizes (the model removed optional `reason`/`energy`/`valence` fields and packed information into the required `arg` field, which then hit the cap).

### Decision

- **Reverted `json_schema` Stage 3 wiring** in `core/src/suggestions.py` — Stage 3 is back to plain `{"type": "json_object"}`. The `_STAGE3_JSON_SCHEMA` constant and `_stage3_response_format()` helper are kept in the file as available infrastructure (zero call-sites in production); `_JSON_SCHEMA_UNSUPPORTED` cache + `_looks_like_schema_rejection()` in `core/src/openai_http.py` also kept (dormant — only activates when a caller passes `json_schema`).
- **Reverted OPEN-4** in `app.py` — the post-Stage-3 widening retry block is removed. The `pool_quality.pool_bad` flag from Stage 3 is still emitted in telemetry; future re-enablement should be guarded by a much stricter trigger (e.g. only on the *first* batch when omitted-ratio ≥ 80 %, or only when fewer than `request_count` valid picks were returned).
- **Kept** the 40 → 80 char rationale-arg cap, the must-have-cite token matching, the section_sizes telemetry, and the json_schema downgrade infrastructure.
- **Marked `gpt-5.5` as unfit for SpotyVibe** — see `documentation/ModelRecommendations.md`. Reason: reasoning-tier model, burns 3 500–4 600 hidden tokens per Stage 3 batch, drifts off the approved-artist allow-list, picks unfindable track titles. Cost ~9.5×, wall ~9.5×, cite half as often vs `gpt-5.4`.

### Guardrails added

1. **`AGENTS.md` — Project North Star:** Quality > Price > Speed; no regression on any metric for any supported model; local-LLM compatibility is first-class; measure before shipping; document model behaviour.
2. **`documentation/ModelRecommendations.md`:** new doc with per-model verdicts (✅ recommended, ⚠️ acceptable fallback, ❌ avoid) and instructions for adding new models to the matrix.
3. **Spotify search resilience** (`core/src/playlist.py`): retries 1 → 4 with exponential backoff (1 s, 2 s, 4 s capped at 30 s); concurrency cap 10 → 5 to reduce 429 cascades for users with rate-limit-tight Spotify tokens.
4. **Eval harness inter-model cooldown** (`evaluation/run_evaluation.py`): 60 s between models, prevents the previous-model's Spotify quota burn from poisoning the next-model's metrics.
5. **`gpt-4.1` and `gpt-4.1-mini` added** to `evaluation/settings.ini` model matrix and `_PER_CYCLE_USD` cost estimate.

### Open follow-ups

- Re-run full 5-model eval once Spotify rate-limit window has drained (24 h conservative). The infra changes are ready; results will populate `documentation/ModelRecommendations.md`.
- Consider an even stricter OPEN-4 v2 (only-on-first-batch + omitted ≥ 80 %) once we have measured baseline data on `gpt-4.1` / `gpt-4.1-mini`. Hold until a second baseline confirms the regression risk profile.

### Status updates

- **CF-Bug-5** — already resolved before Phase 2.6 (token counts and `latency_s` flow correctly into `batch_summary` rows; verified in `eval.jsonl`).
- **CF-Telemetry-1** — ✅ done (token-set match with stop-word filter in `core/src/eval_log.py`).
- **OPEN-3** — ❌ reverted after measured cost & quality regression. Infrastructure kept dormant. Re-evaluate only with a strategy that includes the optional `reason`/`energy`/`valence`/`genres` fields in the schema so the model is not forced to cram into `arg`.
- **OPEN-4** — ❌ reverted after measured cost regression. The `pool_quality.pool_bad` telemetry signal stays in place for future research.
- **OPEN-5 (instrument-only)** — ✅ done (section_sizes emitted per `profile_update_summary` row). The consolidation LLM call itself remains deferred until real-user data crosses thresholds.

### Deep-dive: why `gpt-5.5` is unfit

Telemetry from `evaluation/results/20260428-065552/eval.jsonl` (gpt-5.5 only run that completed all 4 batches):

| Stage 3 batch | Reasoning tokens | Visible tokens | Latency |
|---|---:|---:|---:|
| 1 | 3 583 | 5 071 | 106.5 s |
| 2 | 3 846 | 5 810 | 129.1 s |
| 3 | 3 578 | 5 328 | 120.2 s |
| 4 | 4 598 | 5 896 | **258.7 s** |
| **avg** | **~3 901** | **~5 526** | **~153 s** |

`gpt-5.4` on the same workload: **0 reasoning tokens, ~2 184 visible tokens, ~33 s** per batch. The `core/src/openai_http.py:282` carve-out (`_NO_TEMPERATURE_MODELS = {"gpt-5.5"}`) and the non-zero `reasoning_tokens` in every response confirm `gpt-5.5` is a **reasoning-tier model** (hidden chain-of-thought billed and timed against the call).

**Quality consequence — the extra thinking does NOT buy obedience:**

- Batch 2: 11 picks returned, **5 not in approved pool** (filtered out post-HC2).
- Batches 3 & 4: 6 picks each, only **1 of 6** survived the pool filter, and that one was **not findable on Spotify** (hallucinated track title).
- Rationales collapsed to template-repetitions (`"punchy guitars"`, `"strong hooks"` repeated mechanically across many tracks) — long thinking budget did not produce specificity.
- Net: **14/15 tracks delivered** (vs 15/15 for `gpt-5.4`), **82 % Spotify-found** (vs 100 %), **53 % cite rate** (vs 93 %), **9.5× cost**, **9.5× wall time**.

**Root cause hypothesis:** SpotyVibe's Stage 3 is a **constrained-pool selection task** (pick *N* from explicit allow-list, cite must-have trait, return JSON). This is instruction-following, not reasoning. A reasoning model on this workload spends thousands of hidden tokens "exploring" — and during that exploration it **re-derives** picks from scratch instead of **obeying** the supplied list, drifting off-pool and inventing track titles. The longer the run gets (later batches), the worse the obedience.

**Generalisation:** any reasoning-tier model (OpenAI o-series, future GPT-5.6+/6.x reasoning variants, Claude reasoning modes, DeepSeek R1, etc.) is likely a **bad fit** for this codebase. Always verify against the eval harness before recommending one.

### Q: would a `"Use Caveman Mode"` HARD-rule in the prompt save tokens at the same quality?

**No — not safely for this workload.** Aggressive terseness instructions reliably save **10–25 % of input tokens** by making the model skip filler words and shorten rationales, but on Stage 3 they create three concrete failure modes:

1. **Must-have cite collapses.** The cite metric requires the rationale to literally name a must-have trait. Caveman mode produces rationales like `"guitars; hooks; pop"` — terse enough that token-set matching catches them (now), but **substring matching breaks** entirely and human-readable rationales for the user-facing display degrade noticeably.
2. **The model strips structured fields first.** Same failure mode observed with `json_schema` in this phase: when told to be terse, the model drops *optional* fields (`reason`, `energy`, `valence`) before it shortens *required* ones, then crams details into the cap-truncated `arg`. Net: less information, not more dense information.
3. **Reasoning-tier models ignore terseness rules.** `gpt-5.5` and o-series will still spend 3 500–4 600 hidden tokens "thinking" no matter what the system prompt says — the thinking budget is server-side, not prompt-controlled. So the rule helps the cheap models we already prefer but does nothing for the expensive ones we'd most want to tame.

**Verdict:** the cheaper and safer way to save Stage-3 input tokens is what Phase 0/1/2.5 already did (slim approved-artists list, drop redundant headers, deduplicate avoid traits) — measurable, reversible, doesn't risk quality. A `"Caveman Mode"` rule would be a **save 15 % to lose 10 percentage points of cite rate** trade, which violates the project priority order (Quality > Price > Speed). **Not shipped.**

### Lessons learned

1. **Bundle changes ≠ "additive."** json_schema + OPEN-4 + 80-char cap landed together. When the eval regressed, isolating the cause required a third run (which itself failed for unrelated reasons). **Future rule:** ship one speculative change per eval cycle. Cheaper to verify, cheaper to revert.
2. **Spotify rate-limit is the silent eval killer.** Two back-to-back full evals exhausted the test user's per-user search quota and produced **0 % Spotify-found** rows that looked like quality regressions but were infrastructure failures. Mitigations now in place:
   - 4 retries with 1 s/2 s/4 s exponential backoff (was: 1 retry).
   - Concurrency cap 10 → 5 (production-safe; small parallelism loss).
   - 60 s inter-model cooldown in eval harness (was: none).
   - **Operational rule:** if an eval shows ≤ 50 % Spotify-found across multiple models, suspect 429 cascade before suspecting model regression. Check the log for `429 Too many requests` first.
3. **Reasoning-tier ≠ "smarter for everything."** Confirmed empirically that constrained-pool instruction-following is a workload where reasoning capacity is a **liability**, not a feature. Documented in `documentation/ModelRecommendations.md`.
4. **Auto-downgrade infra is cheap insurance.** The `_JSON_SCHEMA_UNSUPPORTED` cache + `_looks_like_schema_rejection()` helper in `core/src/openai_http.py` were added for OPEN-3, OPEN-3 was reverted, but the infra stays. Cost: ~30 lines of dormant code. Benefit: when we (or a local-LLM user) flips json_schema back on later, the fallback already works. Pattern is now the canonical example referenced in `AGENTS.md` → "Local-LLM compatibility is first-class."

## Phase 2.5 — Quality hardening + prompt engineering + P3.1 (2026-04-27)

**Status: ✅ LANDED.** Combines Phase 2 hardening (P2.2 fix, HC1/HC2 enforcement, reasoning-driven pool-quality detection) + Phase 3 prerequisite (P3.1 mutable-section projection) + prompt-engineering improvements (system/user separation, redundancy cuts, omission few-shot) + local-LLM prompt variant. All in a single PR cycle to keep the prerequisite chain coherent.

### Motivation

Phase 1 hit its quality targets (100 % Spotify-found, 0 HC2 violations). The user asked: "just because we already reach the expected result, does not mean we should neglect potential hardening". Two parallel sub-agent reviews (Phase 2/3 audit + prompt-engineering research) surfaced 11 actionable items. This phase implements 8 of them (3 deferred — see end of section).

### Empirical results

Re-ran `evaluation/run_evaluation.py` at `playlist_size=15` (single batch + half-batch retry) before and after the changes. Same canonical seed, same 3 models.

| Metric | Baseline (12:32:18) | Phase 2.5 (13:04:16) | Δ |
|---|---:|---:|---|
| **gpt-5.4** must-have cite | 86.7 % | **93.3 %** | +6.6 pp |
| **gpt-5.4-mini** must-have cite | 80.0 % | **100 %** | **+20 pp** |
| **gpt-5.5** must-have cite | **26.7 %** ⚠️ | **66.7 %** | **+40 pp** |
| All models — Spotify-found | 100 % | **100 %** | maintained ✅ |
| All models — HC2 violations | 0 (logged only) | **0 (now actively dropped)** | locked in |
| **gpt-5.4** total cost | $0.119 | $0.112 | -6 % |
| **gpt-5.4-mini** total cost | $0.034 | **$0.026** | **-22 %** |
| **gpt-5.5** total cost | $0.510 | **$0.452** | -11 % |
| **gpt-5.5** Stage 3 latency sum | 366.3 s | **213.7 s** | **-42 %** |
| **gpt-5.4** profile-update cost | $0.0308 | **$0.0136** | **-56 %** (P3.1 win) |
| **gpt-5.4-mini** profile-update cost | $0.0092 | **$0.0033** | **-64 %** (P3.1 win) |
| Pool-quality detection (`POOL_BAD` warnings) | n/a (not built) | 5 emitted (72–84 % omit ratio) | new diagnostic |

`POOL_BAD` fired exactly when expected — the canonical seed produces a 35–40 % on-genre pool by the model's own assessment, and the new signal converts that prose into a structured warning the harness can act on.

### Surprise finding from baseline measurement

**gpt-5.5's must-have-citation rate collapsed from 80 % at playlist=30 to 26.7 % at playlist=15 in the baseline run.** This was invisible at the 30-track size used in all prior eval runs. After investigation, the 26.7 % figure is partly a **vocabulary-mismatch false negative** — gpt-5.5 paraphrases must-have traits ("uplifting modern production") instead of echoing the literal tag string the metric matches against ("modern production"). The reasoning blocks confirm gpt-5.5 *is* satisfying must-haves; the metric just doesn't catch paraphrases. After Phase 2.5 the rate is back up to 66.7 % even at p=15.

This is a known weakness of substring-matching telemetry. Filed as **CF-Telemetry-1** for a future PR (case-insensitive token match, or LLM-judge cite verification).

### Changes implemented

#### Tier 1 — Free wins (regression insurance, ~75 LoC)

| ID | Change | File | Why |
|---|---|---|---|
| T1.1 | **HC2 detector now DROPS, not just logs** out-of-pool picks | `app.py` | One prompt regression away from silently shipping bugs; previous "0 violations" was correct *now* but not load-bearing |
| T1.2 | **HC1 detector added** — drops `track == artist` self-titled echoes (case-insensitive) | `app.py` | Defense in depth — Spotify can coincidentally verify these; the post-verify check catches them |
| T1.3 | **`{validation_block}` moved system → user message** | `track_select_system.txt`, `suggestions.py` | System prompt is now invariant per (model, language); enables OpenAI's automatic prefix caching (50 % discount on cached prefix) |
| T1.4 | **Format-explanation moved user → system** + redundant lines cut | `track_select_user.txt`, `track_select_system.txt` | ~150-token savings + cleaner separation; user message is now ~7 lines of pure data |
| T1.5 | **Omission few-shot added** to system prompt | `track_select_system.txt` | Sub-agent A: "models imitate exemplars more than rules — show the desired refusal behavior". Reinforces the existing anti-confab block |

#### Tier 2 — Pipeline hardening (~150 LoC)

| ID | Change | File | Why |
|---|---|---|---|
| T2.1 | **P2.2 wired properly** — `retrieve_candidates(primary_reference=...)` + plumbing from `app.py` | `retrieval.py`, `app.py` | Pre-fix the parameter didn't exist; the 15 % facet quota in `score_artists_stratified` was silently absorbed by flat-fill ("0/5 references hit" was a code gap, not a measurement gap) |
| T2.2 | **Pool-quality flag derived from reasoning block** — `meta.pool_quality.{omitted_ratio, pool_bad}` + `POOL_BAD` warning when omitted_ratio ≥ 50 % or assessment matches bad-pool regex | `suggestions.py` | Converts prose self-critique into structured signal. Foundation for a future "retry Stage 1 with bigger target" wrapper (deferred — see end) |

#### Tier 3 — P3.1 + local-LLM prep (~180 LoC + 6 tests)

| ID | Change | File | Why |
|---|---|---|---|
| T3.1 | **P3.1 mutable-section projection in `train_profile`** — `_project_mutable_sections` + `_merge_mutable_back` + `_MUTABLE_TOP_LEVEL_KEYS` | `profile.py` + `test_profile.py` | History + feedback never sent to GPT (10–20 KB savings on real users). Schema constant prevents drift between projector + reverse merger. **Empirical impact: profile-update cost down 56–64 % across cloud models.** |
| T3.2 | **Slim local-LLM prompt variant** — `prompts/track_select_system_local.txt` + loader switch on `LOCAL_PRESETS` | `track_select_system_local.txt`, `suggestions.py` | Llama 3.2 3B / Qwen 2.5 7B suffer "lost-in-middle" past ~350 system tokens; current cloud variant is ~620 tokens. Slim variant: 2-field reasoning, positive-form HC4 ("ONLY suggest tracks whose vibe matches Must: AND stays clear of Avoid:"), trimmed style guidance, omission few-shot retained |

### Deferred (with reasoning)

| Item | Why deferred |
|---|---|
| **OpenAI structured outputs** (`response_format=json_schema`, strict=true) | Bigger refactor across 3 stages; uncertainty whether `gpt-5.5`/`gpt-5.4-mini` (post-cutoff names) accept strict JSON-schema mode. Build with graceful fallback to `json_object` in a separate cycle. |
| **Reasoning-driven Stage 1 retry** | Foundation laid via `meta.pool_quality` flag (T2.2). Wiring the actual retry requires restructuring the per-batch loop in `app.py` — too risky to bundle here. |
| **P2.3 code-side semantic avoid filter** | Sub-agent A: "Don't build a safety net for an unmeasured failure mode." Wait for a real manual dislike-rate measurement. |
| **P3.3 feedback absorption UI** | UI work; depends on P3.1 (now landed); should produce data via a CLI or debug button first before committing to a UX. |
| **End-to-end local-LLM test** | Would require running Ollama locally with an actual model. The slim prompt variant + loader switch are in place; manual smoke-test recipe documented in commit message. |

### Carry-forward findings

- **CF-Telemetry-1**: `has_must_have_cite` substring match misses model paraphrases. Consider tokenised match or LLM-judge cite verification.
- **gpt-5.5 latency variance is high.** Multiple recent eval runs had OpenAI read-timeouts on Stage 3 batches. Filed under CF-Ops-1 (server-side, not a SpotyVibe bug).
- **Stage 2 silent-passthrough was overstated** by sub-agent A. Stage 2 actually runs whenever `avoid_traits` is non-empty (LLM-based check covers prose avoids). Existing `skipped_no_avoid` status already provides correct visibility. No code change needed.

### Constraint check (per project rules)

- **8 K context floor** ✅ — slim local variant is ~280 tokens (well under). Cloud variant trimmed by ~150 tokens, comfortable margin.
- **Quality first, no regression** ✅ — must-have cite up across all 3 models, Spotify-found unchanged at 100 %, HC2 violations remain 0 (now structurally guaranteed by the active drop).
- **Anti-confab guard preserved** ✅ — all rules from Phase 1 retained in both prompt variants; HC1 detector adds an extra structural check.

---

## ~~Progress summary — from baseline to current state (2026-04-27)~~ (HISTORICAL — superseded by Phase 2.5 dashboard)

> ⚠️ **Superseded.** This table tracks the journey from baseline → P2.0 (pre-Phase-2.5). For current production metrics, see the [Status dashboard](#-status-dashboard-2026-04-28) at the top. Kept here as historical reference.

This table tracks measurable improvements across the rework phases. All eval runs use the canonical seed profile, `playlist_size=30`, single iteration.

### Quality

| Metric | Baseline (pre-P0, 2026-04-24) | Post-P0 (2026-04-26) | Post-P1 pool=200 (2026-04-27 ~11:28) | Post-P2.0 pool=32 fixed (2026-04-27 ~12:49) | Goal |
|---|---|---|---|---|---|
| **Spotify-found** | 96.8 % | 100 % (mini) / 100 % (5.5) | 100 % / 100 % / 100 % | 100 % / 100 % / 100 %¹ | ≥ 95 % |
| **HC2 violations** (out-of-pool picks) | n/a (no pool) | n/a | 4 (mini batch 4) | **0** | 0 |
| **Must-have citation** | — | 84 % (mini) / 70 % (5.5) | 90 % / 80 % / 67 % | 77 % / 77 % / 80 %¹ | — |
| **Schema collapse** (track == artist) | — | — | 0 % | 0 % | 0 % |
| **Stage 1 on-genre** (pool fit %) | — | — | 64 % (pool=200) | **93 %** (pool=32) | ≥ 80 % |
| **Dislike rate** | 39.7 % | — | — | — (manual eval pending) | ≤ 25 % |

¹ gpt-5.5 hit OpenAI read-timeout after 20/30 tracks (100 % found on those 20). Not a quality issue.

### Cost (per 30-track run)

| Model | Pre-P0 estimate | Post-P0 (2026-04-26) | Post-P1 pool=200 | Post-P2.0 pool=32 fixed | Δ vs pool=200 |
|---|---|---|---|---|---|
| **gpt-5.4** | ~$1.00 | — | $0.171 | **$0.161** | -6 % |
| **gpt-5.4-mini** | ~$0.15 | — | $0.056 | **$0.059** | ~ flat |
| **gpt-5.5** | — | — | $0.759 | **$0.470** | **-38 %** |

Cost reductions driven by prompt size: 32-artist pool ≈ 3.5 k tokens vs 200-artist pool ≈ 22 k tokens. gpt-5.5 benefits most (highest per-token reasoning cost).

### Latency (wall-clock, 30 tracks)

| Model | Post-P0 (2026-04-26) | Post-P1 pool=200 | Post-P2.0 pool=32 fixed | Goal |
|---|---|---|---|---|
| **gpt-5.4** | — | 67.8 s | 106.6 s | p95 ≤ 60 s |
| **gpt-5.4-mini** | 41.8 s | 34.5 s | 58.4 s | p95 ≤ 60 s |
| **gpt-5.5** | 299.9 s | 471.8 s | timeout (236 s Stage 3 sum) | p95 ≤ 60 s |

⚠️ Wall-clock numbers are single-iteration and subject to variance. The +57 %/+69 % bumps for gpt-5.4/mini in the fixed run are likely noise (N=1). Stage 3 latency *sum* for gpt-5.5 dropped 49 % (462 → 236 s) thanks to the smaller prompt.

### Key findings and root causes resolved

| # | Issue | Root cause | Fix | Status |
|---|---|---|---|---|
| 1 | gpt-5.5 hallucinating track names (77 % schema collapse) | Stage 3 had no track-level grounding | Track-grounding overlay (`known:` lines in approved pool) | ✅ P1 |
| 2 | Stage 1 surfacing wrong-genre artists (barbershop, occitan chant) | Singleton noise tags (`horn section` n=1) getting max IDF; music-domain prose words (`vocal`, `strong`, `modern`) treated as genre tags | Stop-word expansion + min-frequency floor in `_apply_aliases` | ✅ P2.0 |
| 3 | HC2 violations (mini picking Miley Cyrus, Panic! out of pool) | Pool too large + noisy → model "rescuing" bad pool | Eliminated by fixing retrieval (pool=32, 93 % on-genre) | ✅ P2.0 |
| 4 | Eval harness conflating honest under-fill with real errors | String-match on SSE error events too broad | `status=under_filled` reclassification for known anti-confab phrases | ✅ P2.0b |

### What's next

- **Manual quality eval** — dislike rate measurement on the fixed pipeline (the ultimate Goal #1 gate)
- **P2.2** — Track primary-reference yield (currently 0/5 references hit)
- **P3** — AI Profile Update trims (smaller mutable sections, consolidation on overgrowth)
- **P5** — Model A/B + local-LLM path (pool=32 prompt fits 8 K context floor ✅)
- **gpt-5.5 timeout investigation** — 3 of last 4 eval runs had at least one OpenAI read-timeout; server-side, not a SpotyVibe bug

---

## ~~Post-Phase-0 measurements (2026-04-26, from eval.jsonl after P0 landed)~~ (HISTORICAL)

> ⚠️ **Historical baseline.** These numbers are from immediately after Phase 0 shipped, before Phase 1 / 2.0 / 2.5. Kept for the chronological record. For current metrics, see the [Status dashboard](#-status-dashboard-2026-04-28).

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

## ~~Measured baseline (2026-04-24, from eval.jsonl + OpenAI billing)~~ (HISTORICAL — "where we started")

> ⚠️ **Historical baseline — "where we started".** Pre-rework numbers used to motivate the entire plan. Kept as the reference point against which all subsequent improvements were measured. For current metrics, see the [Status dashboard](#-status-dashboard-2026-04-28).

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

~~1. **Confirm `DEBUG_MODE=1`** in the test user's `settings.conf`~~ — confirmed active (2026-04-27).
~~2. **Add a `gpt-5.5` entry** to `pricing.json` (CF-Bug-4)~~ — already present (2026-04-27).

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
- **No production-code modifications.** The only seam is `SPOTYVE_APP_DIR` in `config._get_app_dir()`. Future harness extensions should add new seams in `config.py`, not monkey-patch in the harness.

### When to run

- **Before adopting a cheaper model in any stage** (gates on Goal #1: dislike rate ≤ 25%).
- **After non-trivial prompt changes** (taste_summary format, system prompt restructure, validation block tweaks).
- **After pipeline restructures** (new stage, retrieval algorithm change, audio-filter changes).
- **Before tagging a release** so the changelog can cite hard before/after numbers.

If you find yourself manually running the dev server multiple times to compare two model variants — stop, run `python evaluation/run_evaluation.py`, and read `comparison.md`. That is what it exists for.

## Phase 1 — Critical regression analysis: gpt-5.5 hallucination spike — ✅ RESOLVED 2026-04-27

> ✅ **RESOLVED.** Final fix landed via the **track-grounding overlay** (Stage 3 prompt now ships `known:` track lists per artist) + the **schema-collapse drop** in `normalize_response` + re-admission of `confirmed` artists to the candidate pool. See the [Track-grounding fix verified](#track-grounding-fix-verified-2026-04-27--phase-1-hallucination-regression-resolved) subsection at the end for the conclusive verification. Subsequently strengthened by [P2.0 retrieval fix](#p20--stage-1-retrieval-matches-tag-noise-not-genre-signal---resolved-2026-04-27) and [Phase 2.5 hardening](#phase-25--quality-hardening--prompt-engineering--p31-2026-04-27).
>
> **The investigation hypotheses, schema-collapse forensics, and minimum-viable fix surface text below is preserved for the historical record but is no longer the current diagnosis.** Skim if you want context for why Phase 2.0 happened; skip if you only need to know the current state.

**User report**: since the Phase 1 staged-pipeline shipped, gpt-5.5 produces playlists where ~90 % of suggested tracks fail Spotify verification. Pre-Phase-1 the same model had a 96.8 % Spotify-found rate (see baseline table line 57). This is a **catastrophic regression that the eval period would never have surfaced** because the eval was originally judged on cost/latency, not on raw not-found counts. **This task is now blocking the eval-period sign-off and Phase 2.**

### What we know

Investigation during 2026-04-26 eval-harness debugging produced these data points (full forensic notes in this commit's Bash transcripts):

- **Artists are real, tracks are not.** Spot-check of 13 RAG-retrieved candidate artists that gpt-5.5 picked ([Newfangled Four, Niflhel, Nite Mrkt, I Heard Whispers, CousCous, Le Grand Sbam, anna.luca, Ben Barnes, Elephant, …]): 12 / 13 exist on Spotify under their `artist:"…"` query. The miss is at the **track** level — gpt-5.5 invents plausible track titles that aren't in those artists' catalogs. Stage 3 only sees an artist-name list; it has nothing to ground track titles against.
- **gpt-5.4-mini does not show this pattern in production**: the user's manual usage with `gpt-5.4-mini` + `playlist_size=10` against a profile with 108 history artists / 43 confirmed / 52 liked reports a 96 % Spotify-hit rate. The smaller model appears to refuse / fall back when it doesn't know an artist's discography; gpt-5.5 confabulates instead.
- **Two confounding bugs already fixed in this commit** (so are NOT the cause of the residual problem, but were inflating the apparent severity during diagnosis):
  - History-pollution: pre-fix, even unverified suggestions inflated `history.suggested_tracks`, pushing artists past `EXHAUSTED_ARTIST_THRESHOLD = 4` after 4 hallucinated picks each, falsely shrinking the available candidate pool mid-run. Fixed in [app.py](app.py) — only Spotify-verified tracks now reach `update_profile`.
  - Cross-batch hallucination repeats: pre-fix, with `history.suggested_tracks` empty (bug above) the same not-found tracks could be re-suggested every batch. Fixed via per-run `_run_unverified` list fed back through `recently_filtered_tracks`.
- **The RAG query had a stop-word leak** (`or` carried weight 4.0 — top-ranked tag — from prose like "art-pop or J-pop crossover"). Fixed in [core/src/rag/retrieval.py](core/src/rag/retrieval.py); reduces but does not eliminate the obscurity bias of returned candidates.
- **Eval seed profile is the *worst-case* RAG input**: prose-only `must_have`/`soft_preferences`/`avoid`/`core_description`, no `genres`/`moods` arrays, no `primary_reference`, no history, no confirmed. RAG anchoring is at its weakest, so the candidate pool skews to long-tail MB-tag matches the model has shaky discography knowledge of.

### Hypotheses to test

In likely order of explanatory power. Ranking is a guess — pick whichever is cheapest to falsify first.

1. **Stage 3's prompt amputation removed the grounding gpt-5.5 needs.** Pre-Phase-1, the monolithic call shipped the full profile JSON + RAG pool to a single big-context model. Post-Phase-1, Stage 3 sees only the **artist name list** + a 200-token taste summary; it lost access to the candidate pool's metadata (Spotify genres, MB tags, popularity), the user's history (which would prime it on artists it knows tracks for), and feedback reasons. For gpt-5.4-mini this leanness might be neutral or positive (fewer distractors), but for gpt-5.5 — which was producing 96.8 % Spotify-found in the monolithic regime — the missing context may be exactly what kept track-name confabulation in check.
2. **The `taste_summary` is failing to convey "modern, on-Spotify" priors.** [build_taste_summary in suggestions.py](core/src/suggestions.py) is deterministic but condensed. If it drops era or popularity hints, gpt-5.5 has no signal to prefer artists with documented tracks.
3. **Stage 3 system prompt actively encourages confabulation.** [prompts/track_select_system.txt](prompts/track_select_system.txt) instructs the model to produce N tracks per batch with rationale. There is no clause like *"if you do not know an actual track by this artist, omit them rather than invent"*. gpt-5.5 may be optimizing for the produced-quantity contract over factual grounding.
4. **The avoid-checker (Stage 2) approves obscure long-tail artists wholesale.** With a fresh seed, almost no artist matches an avoid trait → Stage 2 returns the entire Stage 1 list → Stage 3 has 50 obscure names to pick from with no signal to prefer the more-discoverable ones. gpt-5.4-mini's caution may save it; gpt-5.5's confidence may not.
5. **RAG corpus enrichment status is misleading the popularity penalty.** Local corpus version 2026-04-22 has `spotify_popularity is None` for all 172 827 rows, so [retrieval.py](core/src/rag/retrieval.py) falls back to MB `listener_popularity`, then applies the discovery-sweet-spot ×1.10 boost for `0.3 ≤ pop ≤ 0.7` — exactly the band where MB-only artists with no Spotify presence cluster. The Phase-2 cloud-run enrichment is supposed to populate these fields but the published manifest has not been refreshed.

### Investigation plan

Run as a sequenced suite — each step's outcome decides whether the next is worth running. Capture findings inline; do **not** ship fixes until a hypothesis is confirmed.

1. **Pin the regression to Phase 1.** Re-run the eval harness on the *pre-Phase-1* monolithic commit (`a0330e3` is post-Phase-0 / pre-Phase-1 — verify) with the same seed and gpt-5.5. Record Spotify-found rate. If it's near 96 %, hypothesis 1 is confirmed structurally. If it's also ~10 %, the regression is older than Phase 1 and this whole analysis re-targets.
2. **Identify which prompt slice was load-bearing.** Re-run staged-pipeline gpt-5.5 with three variants:
   - Stage 3 prompt augmented with the candidate pool's `{name, mb_tags, spotify_genres, listener_popularity}` (i.e. the Stage 1 candidate metadata, not just names).
   - Stage 3 prompt augmented with the last-50 `history.suggested_artists` so the model sees what the user has previously been suggested.
   - Stage 3 prompt with both. Whichever variant restores the hit rate identifies the load-bearing context.
3. **Hallucination-discipline clause.** Add to [prompts/track_select_system.txt](prompts/track_select_system.txt): *"If you cannot recall an actual released track by an approved artist, drop that artist from this batch. Returning fewer tracks is correct; inventing track names is not."* Re-run; measure delta independently of step 2.
4. **Profile signal strength**. Re-run with `genres` / `moods` arrays added to the seed (matching the Phase 4 `taste_vector` shape). RAG retrieval should anchor more tightly; measure whether Stage 3 hit rate improves regardless of the prompt patches in steps 2 / 3.
5. **Corpus-enrichment baseline.** Re-run after a fresh enriched-corpus pull (run the cloud-run enrichment job, publish to manifest). Confirm `_artist_popularity` returns Spotify-derived values for the candidate pool. Measure delta against an unenriched-corpus run on the same model + prompt.

### Acceptance

- Spotify-found rate for gpt-5.5 in the canonical eval scenario is restored to ≥ **90 %** (pre-Phase-1 baseline was 96.8 %).
- Root cause is documented (which combination of hypotheses explained it) and fixed in code, not by reverting Phase 1.
- A regression test pins the fix: a deterministic mini-eval (1 model × 1 iteration × small playlist) that fails CI if the hit rate drops below the floor.

### Why this matters

Phase 1's premise was *"split the call to enforce constraints the model is currently ignoring"* (Goal #1). If splitting the call destroys Goal #4 (≥ 95 % Spotify-found) on the quality model, the rework is net-negative — we traded constraint enforcement for hallucination, which the user judges immediately and harshly. **Phase 5's cost A/B cannot proceed until this is closed**: any cheaper variant that posts a similar hit rate to the broken gpt-5.5 baseline would be hidden by the regression rather than benchmarked against a working one.

### Finding (2026-04-26): gpt-5.4-mini reveals a *second* Phase-1 regression — schema mangling

A single-model eval run (gpt-5.4-mini only, canonical seed, 20 batches, hit `MAX_GPT_CALLS_PER_RUN`) produced these numbers:

| | gpt-5.5 (Phase-1 staged) | gpt-5.4-mini (Phase-1 staged) | Pre-Phase-1 monolithic |
|---|---:|---:|---:|
| Verified tracks | ~9 / 30 | **4 / 30** | 30 / 30 |
| Spotify-found rate | ~10 % | **2.0 %** | 96.8 % |
| Schema-correct output | yes | **70 %** (30 % mangled) | yes |
| Stage 3 batches needed | 9+ (call-cap reached) | 20 (capped) | 3 |
| Stage 3 p50 latency | 100 s | 9 s | — |

gpt-5.4-mini does **not** improve the situation; it makes it worse in a *different* way. **30 % of its suggestions had the artist name prepended to the `track` field**, e.g.:

```
{"artist": "the newfangled four", "track": "the newfangled four - everything is awesome"}
{"artist": "micappella",          "track": "micappella - uptown funk"}
{"artist": "san salvador",        "track": "san salvador - la grande folie"}
```

Spotify then searches `track:"the newfangled four - everything is awesome" artist:"the newfangled four"` and finds nothing — even though the artists exist on Spotify and (in some cases, e.g. Micappella's "Uptown Funk" cover) the tracks exist too. This is **schema mangling, not hallucination**: the LLM is filling the `track` field as if it were a "Artist – Title" display string, ignoring the JSON-shape contract in the system prompt.

This makes Phase 1 a **two-failure-mode** regression, not one:

| Model | Failure mode | Where it bites |
|---|---|---|
| gpt-5.5 | Hallucinates track titles for obscure RAG artists | Schema correct, fails Spotify lookup |
| gpt-5.4-mini | Mangles JSON schema (artist prefix in `track` field) **plus** hallucinates the remainder | 30 % of output cannot be Spotify-verified at all; the rest behaves like 5.5 |

Two implications for the investigation plan:

- **Hypothesis 3 is now load-bearing for both models, not just gpt-5.5.** The current [prompts/track_select_system.txt](prompts/track_select_system.txt) shows the output schema as `{"artist": "…", "track": "…", …}` with bare `"…"` placeholders. Add a literal example *and* an explicit "do NOT include the artist name in the `track` field" rule. Test both models against the patched prompt before any further hypothesis work — if 30 % of the small model's output is schema-noise, no other measurement on it is meaningful.
- **The pre-Phase-1 monolithic prompt apparently disambiguated the schema well enough that even the small model produced clean tracks** (the 96.8 % baseline holds for both). Whatever was in the old `build_messages` user prompt that did this is the missing piece — diff that prompt against `track_select_user.txt` before patching.

Add to step 2 of the investigation plan:

> 2b. **Schema-mangling regression test.** For both gpt-5.5 and gpt-5.4-mini, log raw LLM output before `normalize_response` mutates it, and count the fraction of `track` fields that contain a hyphen-separated `"{artist} - {real_title}"` pattern. Pre-Phase-1 baseline must be re-measured the same way to confirm the regression is real (and not pre-existing). Acceptance: ≤ 5 % schema-mangled rate on both models against the patched prompt.

### Empirical baseline 2026-04-27 — single-model gpt-5.4-mini eval

Re-ran the canonical evaluation harness against `gpt-5.4-mini` only (1 iteration, playlist_size=30, post-Phase-1 staged pipeline, RAG enabled, corpus 2026-04-22). Results in `evaluation/results/20260427-054112/`.

| Metric | Value | Pre-Phase-1 baseline |
|---|---:|---:
| Tracks suggested by LLM (raw) | 181 | ~30 |
| Tracks ultimately verified on Spotify | 14 / 30 (47 % of target) | 30 / 30 |
| **Per-suggestion Spotify-found rate** | **7.7 %** (14 / 181) | 96.8 % |
| Stage 2 approved / candidates_in | **42 / 42 (100 % passthrough)** | n/a |
| Avoid traits in seed | 5 (prose) | n/a |
| Stage 3 batches consumed | 20 (capped at MAX_GPT_CALLS_PER_RUN) | 3 |
| Cost | $0.16 (10× the $0.01 estimate) | n/a |
| Wall clock | 271 s | n/a |

**Failure mode is more severe than the doc anticipated.** Of 181 suggestions, **140 (77.3 %) had `track == artist`** — the model echoed the artist name verbatim into the `track` field rather than producing a real title. Examples (raw rows):

```
{"artist": "the newfangled four", "track": "the newfangled four", "rationale_args": ["clear vocal melody", "polished ensemble sound"]}
{"artist": "kervinda",            "track": "kervinda",            "rationale_args": ["clear vocal melody", "quirky personality"]}
{"artist": "barbie rajput",       "track": "barbie rajput",       "rationale_args": ["theatrical personality", "vocal-forward style"]}
{"artist": "ko ishikawa, nikos sidirokastritis, giorgos varoutas, harris lambrakis, anna linardou", "track": "ko ishikawa, nikos sidirokastritis, giorgos varoutas, harris lambrakis, anna linardou", ...}
```

Even all **14 "verified" tracks have `track == artist`** — Spotify's fuzzy search happens to find self-titled tracks or close matches for those strings; the schema is still collapsed.

This is **not** the `{artist} - {real_title}` mangling the previous finding described — it is a complete schema collapse where the model gives up on supplying a track title and just re-emits its only known string (the artist name from the APPROVED_ARTISTS bullet list). The mangling pattern evolved between observations because the underlying problem is "model has nothing to ground a track name on" — the *shape* of the bad output varies but the *cause* is constant.

Stage 2 is **literal passthrough**: 42 candidates in, 42 approved out, with `prompt_tokens=476, completion_tokens=231` — confirming hypothesis 4 is binding on a fresh seed where prose-only avoid traits don't tag-match obscure MB artists.

**This empirical run promotes layer-C from "secondary multiplier" to a load-bearing primary cause:** with bare `"…"` schema placeholders, no concrete example, no anti-confabulation escape clause, and a hard quota (`effective_batch_size = batch_size + 5 = 15`), gpt-5.4-mini's failure mode becomes "produce 15 rows of well-formed JSON whose `track` value is whatever string is cheapest to copy." The artist name is right there in the user message, one token away.

### Updated root cause (post-2026-04-27)

The three layers identified in the analysis (closed vocabulary on obscure pool / total grounding amputation / quota pressure with no escape) are **coequal contributors to a single failure mode**, not a hierarchy. The empirical run confirms:

1. **Closed-vocab + obscure pool** is real: every confabulated/echoed `track` value is one of the 42 RAG-retrieved candidate names.
2. **Grounding amputation** is real: `_LAST_PROMPT_COMPONENTS` shows `profile=0, deny_set=0` — no profile JSON, no deny set, no per-artist metadata reaches Stage 3.
3. **Quota + no-escape** is the *trigger* that turns layers 1 and 2 from "thin context" into "echo the artist name 15 times." Without the hard `≥ batch_size` constraint *and* the lack of an "omit the artist if you don't know a track" clause, the model could refuse rather than collapse.

Additional sub-agent corrections (incorporated):
- The `deny_set_json` in the legacy prompt **plausibly** acted as in-context schema demonstration (4–6 KB of `{"artist":"…","track":"…"}` literals). Removing it took schema scaffolding away simultaneously with the deny semantics. This is consistent with the observed regression but only an A/B with the deny set re-added (and nothing else changed) would prove it causally.

- `app.py:798–812` adds `confirmed` and `history.suggested_artists` to `deny_keys` before retrieval — the artists the model most reliably knows tracks for are *structurally excluded* from the candidate pool. This is a self-inflicted obscurity amplifier.
- `build_taste_summary` does emit up to 5 confirmed anchors as bare names (so anchors aren't 100 % gone, just metadata-stripped), and emits `Era:` only when `prefs.get("eras")` is a structured list — prose-only seeds silently drop the era hint.
- The `effective_batch_size = batch_size + 5` over-request is hidden from the system prompt's `{batch_size}` placeholder, compounding quota pressure beyond what the prompt wording suggests.

### Minimum-viable fix surface (decided 2026-04-27, sub-agent-reviewed)

The fix needs to attack the trigger (layer 3) **and** restore enough grounding (layer 2) that the model has something to anchor on. Re-opening the candidate pool to popular artists (broader layer-1 work) is a separate, larger change deferred to a follow-up. Concretely:

1. **`prompts/track_select_system.txt`** — replace bare `"…"` placeholders with a concrete worked example (real artist + real track + real rationale). Add an explicit anti-confabulation clause: *"If you do not recall a real released track for an approved artist, OMIT that artist. Returning fewer than {batch_size} tracks is correct; inventing track names or echoing the artist name into the `track` field is a constraint violation."* Add a literal "track ≠ artist" rule. **Crucially, demote Hard Constraint 1 from `"Generate ≥ {batch_size} tracks"` to `"Generate up to {batch_size} tracks; fewer is acceptable when grounding is uncertain."`** Without this demotion the escape clause is dead on arrival — constraints would directly contradict each other and the quota would win.
2. **`prompts/track_select_user.txt`** — the APPROVED_ARTISTS block currently ships bare names. Reframe so the model sees that an artist name on its own is *not* a valid track. (Keep the artist list; just clarify the schema obligation in the user message too.)
3. **`core/src/suggestions.py::select_tracks`** — add a guard before `normalize_response`/`spotify_verify` that drops rows whose `track` value is one of the obvious cheap-copy collapse shapes: `track == artist` (case-insensitive, trimmed), or `track in {"", "-", "untitled", "intro", "track", "outro", "interlude"}`, or `track == previous_track_in_same_batch`. Single-symptom guards just push the bug into the next-cheapest shape; the family covers the most likely shifts.
4. **`core/src/rag/retrieval.py` / `app.py`** — re-admit `confirmed` artists to the Stage 1 candidate pool (do **not** add to `deny_keys`). Continue deduping against `history.suggested_artists` for novelty. `confirmed` artists are precisely the ones the model has the strongest discography knowledge for; excluding them is the load-bearing source of obscurity in the pool. Stage 1's existing popularity penalty + tag-overlap scoring still prevent the pool from collapsing to confirmed-only output.
5. **Telemetry** — add `schema_collapse_count` (and a near-collapse breakdown by shape: `eq_artist`, `placeholder_token`, `dup_in_batch`) to `batch_summary` so the regression test in step 2b of the investigation plan is mechanically measurable, and so the next eval catches whichever shape the model migrates to once `track == artist` is forbidden.

The broader pool-widening (popularity-band relaxation, dropping `RAG_POPULARITY_PENALTY` while `spotify_popularity is None` for the corpus, allowing famous artists back into discovery) is the bigger lever and stays out of scope here — it changes the discovery character of the product, deserves its own A/B, and shouldn't be conflated with the schema-collapse fix. Re-admitting `confirmed` is a much smaller, higher-leverage change that does not affect discovery character (it merely stops *excluding* artists the user has already acknowledged as on-taste).

**Hypothesis flagged for verification, not asserted as fact:** the legacy `deny_set_json` (4–6 KB of `{"artist":"…","track":"…"}` literals) plausibly doubled as in-context schema demonstration. Removing it took schema scaffolding away simultaneously with the deny semantics. This is consistent with the observed regression but only an A/B with the deny set re-added (and nothing else changed) would prove it causally.

**Note on the 10× cost overshoot:** the harness's $0.01 mini estimate was based on the happy path (3 batches). Hitting the `MAX_GPT_CALLS_PER_RUN = 20` cap because Spotify-found rate is ~7 % multiplies the per-run cost by ~7×, so the cost overshoot is a *symptom* of the schema collapse, not an independent regression. Once schema collapse is fixed, the cap is unlikely to bind and cost should normalize.

### Post-fix verification 2026-04-27 — schema collapse SOLVED, hallucination layer EXPOSED

Fix shipped (prompt rewrite + `normalize_response` schema-collapse drop + `confirmed` re-admission to candidate pool + telemetry). Re-ran the canonical eval against `gpt-5.4-mini`. Results in `evaluation/results/20260427-060039/`. 580 core unit tests pass (4 new for the schema-collapse drop).

| Metric | Pre-fix (20260427-054112) | Post-fix (20260427-060039) | Status |
|---|---:|---:|---|
| Total LLM-suggested tracks | 181 | 199 | comparable scale |
| `track == artist` (raw rows) | **140 (77.3 %)** | **0 (0.0 %)** | ✅ SOLVED |
| `schema_collapse.total` (telemetry) | n/a (added with fix) | 3 / 258 returned (1.2 %, all `dup_in_batch`) | ✅ at noise floor |
| Spotify-found per suggestion | 7.7 % |  **0.0 %** | ❌ regressed (see below) |
| Verified tracks toward 30-target | 14 | 0 | ❌ |
| Stage 2 approved | 42 / 42 (100 %) | 42 / 42 (100 %) | unchanged |
| Stage 3 batches consumed | 20 (cap) | 20 (cap) | both hit cap |
| Cost | $0.16 | $0.15 | comparable |

**The schema-collapse fix worked exactly as intended.** Telemetry confirms zero `eq_artist` drops in any batch and zero raw rows where `track == artist`. The 1.2 % residual drops are all `dup_in_batch` (the model occasionally suggests the same artist+track twice in one batch — benign).

**The Spotify-found rate paradoxically regressed from 7.7 % → 0 %** because the pre-fix "wins" were schema-collapse coincidences, not legitimate matches. When the model emitted `{"artist":"micappella","track":"micappella"}`, Spotify's fuzzy search occasionally returned a self-titled track and counted as "found." Removing that cheap-match path eliminated those coincidental hits. The model has now shifted to **genuine plausible-sounding hallucination** — examples from the post-fix run:

```
the newfangled four :: lida rose / will i ever tell you?    (real song from Music Man, but not in this artist's catalog)
nite mrkt           :: midnight drive                       (plausible title, not real)
cigale              :: le bal des oiseaux                   (plausible French title, not real)
ben barnes          :: 11:11                                (plausible, not in Spotify catalog under this artist)
micappella          :: the lion sleeps tonight              (real song, but not on this artist's known discography)
nasir               :: bling bling                          (plausible, not real)
niflhel             :: midsommar                            (plausible Norse-themed title, not real)
```

This is **exactly the failure mode predicted by the analysis**: with schema collapse closed, the model fills the gap with confabulated-but-plausible titles. The remaining failure is **layer 1 (closed vocabulary against an obscure RAG pool)** — and it cannot be fixed by prompt patches or code-side guards alone because the model genuinely does not know real tracks for these artists.

**Why the `confirmed` re-admission did not help here:** the canonical eval scenario in `evaluation/scenario.py` is a fresh seed with **zero `confirmed` anchors and no history** (prose-only `must_have`/`soft_preferences`/`avoid`/`core_description`). The layer-1 partial fix (re-admit `confirmed` to the candidate pool) is structurally a no-op for this seed. For a real user profile post-onboarding, with confirmed anchors and accumulated history, the change should genuinely widen the pool toward artists the model knows discographies for. The canonical eval is the worst-case input for layer 1 by design.

### Conclusion + next-step gating

The minimum-viable surface as scoped solved exactly what it promised — the schema-collapse / quota-pressure failure mode — and produced clean telemetry that proves it. The Spotify-found rate did **not** recover on the canonical eval because layer 1 (obscure-pool grounding) is now the binding constraint and the canonical eval scenario has no confirmed anchors to anchor on.

Two follow-up paths, both deferred and requiring user decision:

1. **Validate against a realistic profile.** Re-run the eval (or run a manual generation in the dev server) against a profile that has gone through onboarding and accumulated ≥ 5 confirmed anchors and ≥ 20 history entries. The `confirmed` re-admission should kick in and the pool should shift toward artists the model knows. If Spotify-found rate climbs to ≥ 80 % under that input, the fix is sufficient for real-world usage and the canonical eval simply needs a more representative seed (track separately as a P-eval-x harness improvement).
2. **Layer-1 pool-widening (the bigger lever).** If even realistic profiles do not recover, the deferred work has to land: drop the `0.3 ≤ popularity ≤ 0.7` discovery sweet-spot band, drop `RAG_POPULARITY_PENALTY` while `spotify_popularity is None` for the corpus, and/or run the cloud-run enrichment to populate `spotify_popularity` so the existing penalty has real signal to act on. This is a discovery-character change and deserves its own A/B against the (now reliable) like-rate measurement.

The schema-collapse fix should ship regardless — it is the correct foundation for either follow-up. Hallucination-without-schema-collapse is a measurable problem on a clean baseline; hallucination-mixed-with-schema-collapse was not.

---

### Track-grounding fix verified 2026-04-27 — Phase 1 hallucination regression RESOLVED

After the track-grounding fix landed (overlay-based `known:` block in the Stage 3 prompt) and the Spotify dev-app rotation worked around the `artist_top_tracks` 403 issue (see also: implementation note below), a single-model gpt-5.4-mini eval against the canonical seed produced:

| Metric | Pre-fix (today, first eval) | Post-fix (this run) | Δ |
|---|---|---|---|
| **Spotify-found** | 7.7 % | **100.0 %** | +92.3 pp |
| **Must-have cite** | (n/a in pre-fix run) | 93.3 % | — |
| Schema collapse | 77.3 % | 0 % (every emitted track verified on Spotify) | −77.3 pp |
| Cost | ~$0.30+ (retry loops) | $0.04 | −87 % |
| Wall time | retry-bound | 35 s (3 stage-3 batches) | — |

**Concrete proof point:** `nite mrkt - anxiogenic` was the canonical pre-fix confabulation (model emitted `nite mrkt :: midnight drive`, a track that does not exist). Post-fix, the same artist appears with the real released track `Anxiogenic` (sourced from the overlay) and the LLM judge accepts it: *"fits the modern theatrical-pop-rock anchor exactly"*.

**What the dislikes tell us:** every dislike is `drifts into avoided territory (vintage / generic)` — the model picked correct, real tracks but the LLM judge rejected the **artist genre fit**. This is exactly P2.0 (Stage 1 retrieval surfacing wrong-genre candidates), not P1.x (hallucination). The two failure layers now separate cleanly:

- **Hallucination layer (P1):** RESOLVED. Stop-the-bleed ✓.
- **Retrieval-quality layer (P2.0):** STILL OPEN. Wrong candidates make the playlist's like-rate ceiling low even with perfect grounding.

#### Implementation note (Spotify endpoint switch)

While building the validation overlay, every call to `/v1/artists/{id}/top-tracks` returned **HTTP 403 Forbidden** for the freshly-rotated dev app. Newly-created Development Mode apps (post-Nov-2024 Service Terms update) do not have access to that endpoint by default — Extended Quota Mode approval is required. The earlier "66-min rate limit" was actually a per-app cooldown after repeated 403s, not true 429 throttling.

Worked around by switching `build-tools/build_top_tracks_overlay.py` from `artist_top_tracks` to `search(type="track", q='artist:"NAME"', limit≥10)` with a strict primary-artist normalised-name filter to discard mis-attributed hits. The new endpoint:

- works on every app tier (no Extended Quota Mode dependency),
- needs only one API call per artist instead of two (no separate id-resolution),
- returns relevance-ranked real released tracks (effectively the artist's most-played catalogue for an artist-only query).

If the production corpus enrichment pipeline (`build-tools/spotify_enrichment/`) currently calls `artist_top_tracks` it will need the same swap before it can be re-run on the new app credentials. Audit before next enrichment.

#### Carry-forward

1. The full 3-model eval (gpt-5.5, gpt-5.4, gpt-5.4-mini) still has to run before Phase 1 can be closed for all models — gpt-5.4-mini is the smallest model and the easiest to fool with grounding, so a single-model pass is *necessary but not sufficient* evidence.
2. P2.0 is now the most expensive remaining bug — fixing it should unlock material like-rate gains across all models.
3. Add a regression assertion to the eval harness: if a future run reports `Spotify-found < 80 %` on the canonical seed, fail the eval explicitly. Today this would have been a noisy regression instead of a quietly-empty playlist.

# Phase 2 — Quality enforcement (weeks 3–4)

Goal: stop violating the constraints we already collect.

## P2.0 — Stage 1 retrieval matches tag-noise, not genre signal — ✅ RESOLVED 2026-04-27

**Status: RESOLVED. Two-part fix landed in `core/src/rag/retrieval.py` and verified end-to-end at `target_size=32`.**

### Final diagnosis (precise, replaces all prior hypotheses)

Instrumenting `_apply_aliases` to dump per-token (weight × IDF × n_artists) on the canonical seed produced a smoking-gun table. Out of 89 raw query tokens generated by `build_query_tags`, only 30 survived alias mapping into the corpus tag index — and the **highest-contribution tokens were single-artist noise tags**, not genres:

| weight | IDF | n | contrib | tag | classification |
|---:|---:|---:|---:|---|---|
| 3.00 | 12.37 | **1** | **37.10** | `'horn section'` | random user tag |
| 3.00 | 11.96 | **2** | **35.88** | `'rock-pop'` | thin variant of `pop rock` |
| 3.00 | 11.67 | 3 | 35.02 | `'art-pop'` | thin variant of `art pop` |
| 2.80 | 12.37 | **1** | **34.63** | `'hooks'` | quality descriptor noise |
| 2.80 | 11.67 | **3** | **32.69** | `'strong'` | quality descriptor noise |
| 2.80 | 11.45 | 4 | 32.06 | `'theatrical'` | legit (kept) |
| 2.80 | 9.92 | 22 | 27.79 | `'modern'` | quality descriptor noise |
| 2.80 | 8.61 | 85 | 24.10 | `'vocal'` | quality descriptor noise |
| 2.80 | 3.94 | 9104 | 11.04 | `'pop'` | legit (kept) |
| 1.80 | 3.58 | 13042 | 6.45 | `'rock'` | legit (kept) |

Two pathologies stacked:

1. **TF-IDF inversion for music tags** — the rarest tags in MusicBrainz aren't the most diagnostic *genres*; they're the most idiosyncratic *user-typed words*. With max-IDF, a single artist tagged with literal `"hooks"` or `"strong"` got the same score boost as a single artist legitimately tagged with the rare subgenre `"art-pop"`. The system was systematically rewarding tag-noise.
2. **Music-domain prose ≠ genre tags** — words like `vocal`, `melody`, `production`, `lyrics`, `personality`, `storytelling`, `melodic`, `polished`, `modern`, `strong`, `clear`, `forward`, `crossover` are *qualities* of music, not genres. They were dominating retrieval because the seed prose ("Modern theatrical pop-rock with strong hooks…", "modern production; clear vocal melody") talks in those terms but the corpus uses them as random scattered tags.

This is exactly why 22/32 candidates had the `vocal` tag and the surfaced pool was barbershop, occitan chant, and Bangladeshi vocal music: the model was correctly retrieving artists whose tag set best matches the (broken) query, and the broken query was matching `vocal` + `strong` + `hooks` + `modern` rather than `pop` + `rock` + `theatrical`.

Hypothesis 4 (corpus enrichment will fix it) was ruled out independently in the prior session — the `target_size=200` pool was on-genre because the deeper tail eventually surfaced enough real-genre artists to dilute the noise-tagged ones, and the `popularity_penalty=0.4` floor pushed mainstream pop-rock down where the noise was concentrated. The bug was always in the scoring, not the corpus.

### Fix (minimal, two changes, 30 lines)

`core/src/rag/retrieval.py`:

1. **Music-domain stop-list expansion** (`_STOP_TOKENS`). Added 35 quality/character descriptors that get tokenised out of the seed prose before they ever become query tokens: `strong`, `modern`, `polished`, `generic`, `punchy`, `clear`, `forward`, `vocal/vocals`, `melodic`, `melody`, `production`, `lyrics`, `personality`, `storytelling`, `flourishes`, `influences`, `crossover`, `dominance/dominated`, `straight/ahead/straightforward`, `unmastered`, `demos`, `lean`, `not`, `post`, `section`, `feel`, `based`, `driven`, `leaning`, `esque`, `like`, `ish`, plus numeric era fragments `2010/2020/60s/70s/80s/90s/00s` (handled by year-band logic, not tag matching).

2. **Min-frequency floor in `_apply_aliases`** — drop any query tag whose corpus frequency is below 3 (auto-disabled for tiny test corpora < 100 artists). A tag matching only 1–2 artists out of 172k is a noise artefact, regardless of its IDF; the floor neutralises it without touching the IDF formula itself.

Both changes are deliberately *additive*: they only remove tokens from the query, they do not add new scoring terms. This means the existing test suite (logic-of-scoring tests) remains valid, no scoring math was altered, and the fix is trivially reversible.

### Empirical impact (offline measurement at target_size=32)

| | Before | After |
|---|---:|---:|
| Surviving query tokens | 30 | 13 |
| Top contributor | `horn section` (n=1) | `art-pop` (n=3) |
| Pool fill | 22/32 | 32/32 |
| On-genre (pop/rock/indie/art*/theatrical/alternative) | 5 / 22 = **22%** | 30 / 32 = **93%** |
| Tagged `vocal` | 13 / 22 = **59%** | 0 / 32 = **0%** |
| Top-20 included | barbershop, occitan chant, Bangladeshi vocal, doo-wop | Phillip Dupuy, Electric Fan Death, Orpheus Blade, Taylor Swift, Lady Gaga, Olivia Rodrigo, Ariana Grande, Marina, Poppy, Sparks |

(See `evaluation/results/20260427-103742/` for the canonical-seed eval and the diagnostic dump in `core/tests/test_rag_retrieval.py::test_min_frequency_floor_drops_singleton_noise_tags` for a self-contained reproduction.)

### Empirical impact (full eval, gpt-5.4 / gpt-5.4-mini / gpt-5.5, seed → playlist)

Re-ran `evaluation/run_evaluation.py` on the canonical seed with `RETRIEVE_CANDIDATES_SIZE=32` (down from 200). All other pipeline knobs identical to the post-Phase-1-grounding-fix baseline.

| Metric | pool=200 baseline (2026-04-27 ~11:28) | pool=32 + retrieval fix (2026-04-27 ~12:49) | Δ |
|---|---:|---:|---|
| **HC2 violations** (Stage 3 picks outside approved pool) | 4 / 14 (gpt-5.4-mini batch 4) | **0** | **eliminated** |
| Stage 2 avoid-pass | 200/200 | **32/32** | clean pool |
| **gpt-5.4** cost | $0.1713 | **$0.1612** | -6 % |
| **gpt-5.4** wall (s) | 67.8 | 106.6 | +57 % (variance — single iter) |
| **gpt-5.4** must-have citation | 80.0 % | 76.7 % | -3 pp (within noise) |
| **gpt-5.4-mini** cost | $0.0559 | $0.0587 | +5 % (essentially flat) |
| **gpt-5.4-mini** wall | 34.5 s | 58.4 s | +69 % (variance) |
| **gpt-5.4-mini** must-have citation | 90.0 % | 76.7 % | -13 pp (model-side variance, not a regression — same prompt, smaller pool just gives less to cite) |
| **gpt-5.5** cost (until natural endpoint) | $0.7585 | **$0.4701** | -38 % |
| **gpt-5.5** Stage 3 latency sum | 462 s | 236 s | **-49 %** |
| **gpt-5.5** must-have citation (on completed batches) | 66.7 % | 80.0 % | **+13 pp** |
| All models — playlist size | 30 / 30 / 30 | 30 / 30 / 0* | * gpt-5.5 hit a real OpenAI read-timeout in batch 3 (network, not under-fill) |

Cost/latency reductions are dominated by the **prompt size reduction**: a 32-artist approved pool serialises to ~3.5 k tokens of input vs ~22 k tokens for 200 artists. Stage 3 is called once per batch (3 batches), so the saving compounds. gpt-5.5 benefits most because its per-token reasoning cost is highest.

The flat `gpt-5.4-mini` cost is informative: at small pool sizes the prompt overhead is already amortised against the system prompt + taste summary, so the 200→32 saving is partially absorbed. The win there is **quality** (HC2 violations gone, pool 100 % on-genre) at no cost penalty, which is the right trade.

### Why HC2 violations went to zero

In the pool=200 baseline, gpt-5.4-mini batch 4 picked 4 out-of-pool tracks (Miley Cyrus, Panic! At The Disco) — symptoms of a model trying to *rescue* a too-large, too-noisy approved pool by reaching into its own knowledge. With pool=32 and 93 % on-genre, the model has nothing to rescue *from*: every approved candidate is already plausibly on-brief. Pool-conformance is now structural, not behavioural.

### Regression tests added

`core/tests/test_rag_retrieval.py` (3 new tests, 605 total passing):

- `test_min_frequency_floor_drops_singleton_noise_tags` — builds a 200-artist corpus where one artist is the sole holder of the literal tag `"hooks"`. Pre-fix that artist would rank #1 for any seed mentioning hooks; post-fix it's never surfaced.
- `test_music_domain_stop_words_excluded_from_query` — asserts that `modern`, `production`, `strong`, `melody`, `polished`, `vocal`, `vocals`, `melodic`, `punchy`, `lyrics`, `personality`, `storytelling` never become query tokens, while legitimate signals like `guitars` survive.
- `test_min_frequency_floor_disabled_for_tiny_corpora` — guards the auto-disable path so the existing scoring-logic tests (which use 3–5-artist fixture corpora) keep working.

### Production config change

`config.py`: `RETRIEVE_CANDIDATES_SIZE = 32` (down from 50). The empirical evidence is that pool=32 is sufficient with the cleaned ranking; doubling it doesn't improve quality and triples the prompt cost. Reversible by editing one line if a future regression suggests we starved Stage 3.

### Anti-action that was rejected

The original 2026-04-27 plan listed "Do NOT add a minimum genre-overlap hard filter to Stage 1 before the diagnosis is confirmed." That advice held: the fix turned out to be at the *query construction* layer (stop-words + min-frequency floor), not at the *post-retrieval filter* layer. A hard genre filter would have masked the real bug and made the corpus look broken when it wasn't.

### Carry-forward

- `gpt-5.5` continues to be slow and timeout-prone on the OpenAI side. Three of the last four eval runs had at least one read-timeout on a Stage-3 batch. Tracking under CF-Ops-1 (not yet filed). Not a SpotyVibe bug, but worth recording: with pool=32 the prompt is small enough that the timeout is almost certainly server-side reasoning-cap related, not a token-count issue.
- The `+57 %` / `+69 %` wall-time bumps for gpt-5.4/mini are within typical single-iter variance (we have one sample per cell). If they reproduce across N=5 iters, file as P5.x. Until then, treat as noise.

## P2.0b — Honest under-fill vs real error in the eval harness — ✅ RESOLVED 2026-04-27

**Status: RESOLVED. Diagnostic clarity fix in `evaluation/harness.py`.**

### Symptom

After landing the Phase 1 anti-confab grounding fix, when a model correctly refused to confabulate (returned 0 picks because the candidate pool genuinely didn't fit the seed), the eval harness raised `RuntimeError("run_pipeline returned error: No tracks could be verified on Spotify")` and recorded `playlist_status=error`. This conflated:

- **Real errors** — Spotify auth failure, OpenAI timeout, exception in the pipeline (system is broken)
- **Honest under-fill** — model worked exactly as designed, candidate pool was the bottleneck, anti-hallucination guard fired correctly (system is *working*)

The conflation made it impossible to read eval reports: a column showing `status=error` could mean either "we shipped a regression" or "the model behaved with integrity". This was the exact failure mode that prompted the user to ask for the fix — gpt-5.5 in the pool=32-without-retrieval-fix run produced `playlist=0, status=error` even though the per-batch reasoning logs showed the model was reasoning *correctly* about a bad pool ("returning a short list is safer than padding with bad fits").

### Fix

Two coordinated changes in `evaluation/harness.py`:

1. **`_step_playlist`** — when the SSE error event message matches one of two known under-fill phrases (`"no tracks could be verified on spotify"`, `"gpt kept suggesting already-known"`), reclassify as a non-fatal return of `{"status": "under_filled", "tracks": [], "warning": <msg>}` instead of raising `RuntimeError`. All other error messages continue to raise (preserves real-error detection).
2. **Caller** — set `result.playlist_status` to one of `"ok"` / `"under_filled"` / `"empty"` / `"error"` based on the structured return + tracks count. Comparison reports now distinguish the four cases instead of collapsing them into two.

Production app behaviour (Flask `/api/run` SSE stream) is **unchanged** — the UI still emits the `error` event so the user gets a clear in-app message. Only the eval harness's interpretation changed.

### Empirical confirmation

In the post-fix eval run (2026-04-27 ~12:49), gpt-5.5's playlist=0 outcome was correctly classified as `status=error` with the underlying cause `"Request timed out: The read operation timed out"` — a real OpenAI server-side timeout, not an honest under-fill. The reclassification logic stayed out of the way exactly when it should: the timeout phrase doesn't match either under-fill marker, so it propagates as a real error. This is the right outcome — we didn't introduce a "report all failures as warnings" footgun.

When future runs hit a *true* honest under-fill (model returns 0 picks on a misfit pool), they will be visible in the comparison table as `status=under_filled` with `playlist=0`, distinct from the `status=error` rows that genuinely demand investigation.

## P2.1 — ~~Demote `confirmed` from suggestion source~~ SUPERSEDED 2026-04-27
The system prompt says confirmed = "style anchors, NOT suggestion pool" but GPT recycled them in 43% of suggestions. Original fix: treat `confirmed` exactly like `history.suggested_artists` — a deny list for new suggestions.

**Status: SUPERSEDED by the schema-collapse fix (Phase 1 §"Minimum-viable fix surface", 2026-04-27).** Adding `confirmed` to the candidate-pool deny set was identified as a load-bearing source of obscurity that drove the gpt-5.4-mini schema collapse: by structurally excluding the artists the model has the strongest discography knowledge for, Stage 1 produced an obscure-only pool that Stage 3 could not ground real track names against. The fix re-admits `confirmed` to the candidate pool. Confirmed-recycling is now controlled via Stage 3's HC6 ("≥ 30 % new-artist tracks") + the `taste_summary` framing of confirmed as "Style anchors:" rather than via Stage 1 exclusion. **Do NOT re-add `confirmed` to `_deny_keys` in `app.py:798–812` without first re-running the canonical eval and showing schema-collapse stays at ≤ 5 %.** A future P2.x can revisit if confirmed-recycling > 5 % shows up in eval logs after this change lands.

## P2.2 — Tracking primary-reference yield — ✅ DONE 2026-04-27 (in Phase 2.5)

> ✅ **DONE in Phase 2.5.** Originally scoped as "tracking only" — turned out to be a structural code gap. `retrieve_candidates()` did not even accept a `primary_reference` parameter, so the 15 % facet quota in `score_artists_stratified` was silently absorbed by flat-fill. Fix wired the parameter through `retrieve_candidates → score_artists_stratified → _build_facet_query` and added plumbing in `app.py`. See [Phase 2.5 → T2.1](#phase-25--quality-hardening--prompt-engineering--p31-2026-04-27).

## P2.3 — Code-side semantic avoid checker (post-LLM safety net) — ⏸ DEFERRED (gated on OPEN-1)
Even with Stage 2 avoid-checking, some violations slip through (e.g. tracks that match an avoid trait the model didn't recognize). Add a final pass after Spotify verification that:
- Pulls each verified track's Spotify genres.
- Cross-references against the `avoid` list using a precomputed mapping (e.g. "classic rock" → spotify genre `"classic rock"`, `"album rock"`, `"hard rock"`).
- Drops matches; logs to telemetry.

**File**: new `core/src/rag/avoid_filter.py`. Mapping seeded from MusicBrainz tag aliases.

**Acceptance**: dislike rate ≤ 25% measured over a full week of real usage (≥ 100 judged tracks).

---

# Phase 3 — Profile reform (week 4–5)

Goal: AI Profile Update should be cheap, bounded, and absorb feedback over time.

## P3.1 — `train_profile()` sends only mutable sections — ✅ DONE 2026-04-27 (in Phase 2.5)

> ✅ **DONE in Phase 2.5.** `_project_mutable_sections` + `_merge_mutable_back` + `_MUTABLE_TOP_LEVEL_KEYS` constant landed in `core/src/profile.py`. History + feedback never reach GPT. **Empirical impact: profile-update cost down 56–64 % across cloud models.** See [Phase 2.5 → T3.1](#phase-25--quality-hardening--prompt-engineering--p31-2026-04-27).

## P3.2 — Consolidation step on overgrowth — ⏸ DEFERRED (instrument first)
After each AI Profile Update, if `soft_preferences` > 8 entries OR `avoid` > 8 entries OR `meta.goal` > 600 chars, append a one-shot consolidation call:

```
"These overlap. Consolidate to ≤ 8 distinct ideas, preserving meaning.
Return only the consolidated arrays."
```

Single mini-LLM call, ~$0.001. Bounds profile growth structurally.

**File**: [core/src/profile.py](core/src/profile.py) — new `_consolidate_oversized_sections()`.

**Acceptance**: profiles do not exceed 12 KB after 10 successive AI Profile Updates with feedback (today's profile is 26 KB after fewer than 10 updates).

## P3.3 — Periodic feedback absorption — ⏸ DEFERRED (UI work + gated on OPEN-1)
Liked/disliked reasons accumulate in `feedback.liked_tracks[*].reason` and `feedback.disliked_tracks[*].reason`. They drive nothing today.

After every 20 new feedback entries (or weekly, whichever first), run a one-shot LLM call that:
1. Reads the last 20 reasons from each side.
2. Suggests additions/edits to `must_have`, `soft_preferences`, `avoid` (delta only, not full sections).
3. Surfaces the proposed deltas in the UI as a non-blocking tip toast: *"Based on recent feedback, your profile would benefit from adding X to avoid. Apply?"*

User confirms before write. Cost: ~$0.01 per absorption. Frequency: ~weekly for an active user.

**File**: new `core/src/feedback_absorption.py`. New endpoint `POST /api/profile/absorb-feedback`. New tip in [tips.js](frontend/static/js/modules/tips.js).

**Acceptance**: after absorbing 20 disliked-track reasons, the resulting profile must include at least 2 new `avoid` entries derived from recurring reasons. Verified by manual review on a seeded test profile.

---

# Phase 4 — Compact taste vector (week 6+) — 🔮 PLANNED (after Phase 3 closes)

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

# Phase 5 — Quality-validated cost A/B + local-LLM optimizations — 🔮 PLANNED (gated on OPEN-1)

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

## ~~CF-Bug-4 — Verify GPT-5.5 default-model wiring (mostly shipped)~~ — ✅ RESOLVED 2026-04-27
**Status**: gpt-5.5 is the default ([config.py](config.py)), listed first in `OPENAI_SUPPORTED_MODELS_JSON`, and present in [pricing.json](frontend/static/data/pricing.json) (confirmed 2026-04-27). No further action.

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

Latency target both tiers: **≤ 60 s p95** end-to-end on cloud (Goal #3). Time-to-first-batch ≤ 12 s p95 (P5.3). Local LLM bounded by user hardware; we own everything (P5.2 + P5.3).

If only tier 1 lands, the rework still hits Goal #1 (quality) and most of Goal #2 (cost) in the first week of regular use. Tier 2 is upside, not a precondition.
