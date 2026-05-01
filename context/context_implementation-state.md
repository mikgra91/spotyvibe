# result-improvement.md — compressed implementation state

Source file reviewed: `result-improvement.md`. Key claims below cite source chunks inline for traceability.

## Current state

- Core architecture is now a staged recommendation pipeline:
  - Stage 1: code-side `retrieve_candidates()`; tag match must-have, hard-filter avoid, primary-reference tag overlap, popularity band, dedupe. Cost $0. 
  - Stage 2: `check_avoid_compliance()` mini/local LLM avoid-checker. 
  - Stage 3: `select_tracks()` main LLM compact prompt: approved artists + taste summary; no full profile JSON / deny list / RAG pool. 
  - `run_pipeline` wired to `candidates → approved → tracks → spotify_verify`. 
- Current latest stable dashboard in file is Phase 2.6 baseline, with later Phase 6.0 cost bundle appended.
- Stable production baseline used for Phase 2.6 gating (`playlist_size=15`, canonical seed):
  - `gpt-5.4`: Spotify-found 100%, must-have cite 93.3%, HC2 0, cost $0.0951, wall 68.9s.
  - `gpt-5.4-mini`: Spotify-found 100%, must-have cite 86.7%, HC2 0, cost $0.0278, wall 29.7s.
  - `gpt-5.5`: Stage 2 timeout; no quality metrics. 
- Phase 6.0 cost bundle shipped after dashboard:
  - L1: skip Stage 2 LLM if Stage 1 avoid-tag filter proves no avoid overlap.
  - L8: strip empty `recent_feedback` / `audio_filters_block` lines from Stage 3 prompt.
  - L11: Stage 3 over-request reduced `+5 → +2` via `STAGE3_OVER_REQUEST`.
  - L16: hoist `cached_tokens` telemetry to `batch_summary`.
  - Predicted saving: ~$10–11 / 1,000 playlists, ~36% vs $28.80 baseline at `gpt-5.4-mini @ pool=50`; validation eval queued separately; 5 tests added, 1,121 core tests passing. 

## Implemented phases / outcomes

### Phase 0 — bleed stop + measurement

Implemented:
- Cost estimator fixed: accounts for batch count and live prompt-size endpoint.
- Eval telemetry wired: `batch_summary`, `run_summary`, p50/p95 latency.
- Prompt/profile trims: compact JSON, stripped liked/disliked feedback from GPT profile input, capped recent feedback.
- Process rule: “shipped” claims require grep-verifiable artifact/test. 

Outcome:
- Before fix: estimator undercounted ~10×; per-batch latency unmeasured. 
- After Phase 0: profile prompt ~1.6–1.8k tokens instead of ~7k; telemetry existed, but later CF-Bug-5 found token counts were still not flowing correctly. 
- CF-Bug-5 later resolved before Phase 2.6: token counts and `latency_s` now reach `batch_summary`. 

### Phase 1 — staged pipeline

Implemented:
- Replaced monolithic mega-call with 3-stage pipeline.
- `retrieve_candidates()` in `retrieval.py`.
- `check_avoid_compliance()` in `suggestions.py`.
- `select_tracks()` in `suggestions.py`.
- `build_taste_summary()` ≤800 chars.
- Staged path enabled when RAG + corpus loaded; legacy path retained as fallback.
- 20 tests added; 564 core tests passing. 

Initial outcome:
- Prompt size dropped by design, but regression appeared:
  - `gpt-5.5` hallucinated track names for obscure RAG artists.
  - `gpt-5.4-mini` schema-mangled track field / echoed artist into track. 

Resolved causes:
- Stage 3 saw only artist names; no track grounding / metadata.
- Prompt used bare `"..."` examples and hard quota with no “omit if uncertain” escape.
- Canonical eval seed was worst-case: prose-only, no confirmed anchors/history. 
- Schema collapse verified: 140/181 suggestions had `track == artist` pre-fix. 

Fixes:
- Added concrete examples and anti-confab clause.
- Allowed fewer than batch size when grounding uncertain.
- Added `track != artist` rule.
- Added `normalize_response` schema-collapse drops.
- Re-admitted `confirmed` artists to candidate pool.
- Added schema-collapse telemetry. 

### Phase 1 regression final resolution

Final documented resolution:
- Track-grounding overlay shipped: Stage 3 prompt includes `known:` track lists per artist.
- Schema-collapse drop added.
- Confirmed artists re-admitted.
- Hallucination spike resolved; later strengthened by P2.0 and P2.5. 

### Phase 2.0 — retrieval quality fix

Problem:
- Stage 1 surfaced wrong-genre artists because singleton noise tags got high IDF and music-domain prose words were treated as tags.

Fix:
- Stop-word expansion.
- Minimum-frequency floor in query/tag application.
- Rejected hard genre-overlap filter; root bug was query construction, not post-filtering. 

Outcome:
- Stage 1 on-genre improved to 93% with pool=32.
- HC2 violations went to 0.
- Spotify-found remained 100% across measured models.
- `RETRIEVE_CANDIDATES_SIZE = 32`; pool=32 gave enough quality with far less prompt cost. 
- Historical P2.0 metrics:
  - Spotify-found: 100%.
  - HC2: 0.
  - Schema collapse: 0%.
  - Stage 1 on-genre: 93%.
  - Dislike rate still pending manual eval. 

### Phase 2.0b — eval harness clarity

Problem:
- Eval harness treated honest under-fill as fatal error.

Fix:
- Known anti-confab under-fill messages now map to `status=under_filled`.
- Result status split into `ok` / `under_filled` / `empty` / `error`.
- Production UI unchanged. 

Outcome:
- Eval reports no longer conflate “model refused to hallucinate” with “system error.”

### Phase 2.5 — hardening + prompt engineering + P3.1

Implemented:
- HC2 detector now drops out-of-pool picks, not just logs.
- HC1 detector drops `track == artist`.
- `{validation_block}` moved system → user for invariant system prompt / OpenAI prefix caching.
- Format explanation moved user → system; ~150-token savings.
- Omission few-shot added. 
- Primary-reference plumbing fixed: `retrieve_candidates(primary_reference=...)`; 15% facet quota had previously been silently absorbed by flat-fill. 
- `meta.pool_quality.{omitted_ratio,pool_bad}` derived from Stage 3 reasoning.
- P3.1 landed: `train_profile()` sends only mutable sections via `_project_mutable_sections`, `_merge_mutable_back`, `_MUTABLE_TOP_LEVEL_KEYS`; history/feedback never sent to GPT.
- Slim local-LLM prompt variant added (`track_select_system_local.txt`), ~280 tokens; loader switch on `LOCAL_PRESETS`. 

Outcome:
- Profile-update cost down 56–64% across cloud models. 
- Must-have cite improved across models; Spotify-found unchanged at 100%; HC2 remains 0. 
- 8K context floor satisfied; local prompt under budget. 

### Phase 2.6 — speculative trial, reverts, guardrails

Tried:
- Strict Stage 3 `json_schema`.
- OPEN-4 Stage 1 pool-widening retry on `pool_bad`.
- Rationale arg cap 40 → 80 chars.
- Telemetry-only token-set must-have cite match.
- Telemetry-only profile section sizes. 

Measured trial (`20260428-065552`):
- `gpt-5.4`: cost +80%, wall +151%.
- `gpt-5.4-mini`: cost +89%, wall +242%.
- `gpt-5.5`: $0.7875, 651.6s, Spotify-found 82.4%, cite 52.9%. 

Decision:
- Reverted Stage 3 `json_schema`; back to `json_object`.
- Reverted OPEN-4 widening retry.
- Kept 80-char rationale cap, token-set cite matching, section-size telemetry, json_schema downgrade infra.
- Later S7 removed dead `_STAGE3_JSON_SCHEMA` / `_stage3_response_format()` call-sites; dormant rejection/downgrade cache remains in `openai_http.py`. 

Guardrails added:
- `AGENTS.md` North Star: Quality > Price > Speed; no regression; local LLM first-class; measure before shipping.
- `documentation/ModelRecommendations.md`.
- Spotify search resilience: retries 1 → 4, exponential backoff, concurrency 10 → 5.
- Eval harness cooldown 60s between models.
- Added `gpt-4.1`, `gpt-4.1-mini` to eval matrix. 

Important model finding:
- `gpt-5.5` classified unfit:
  - Burns ~3,500–4,600 reasoning tokens per Stage 3 batch.
  - Drifts off approved artist allow-list.
  - Picks unfindable track titles.
  - ~9.5× cost and wall time vs `gpt-5.4`, with worse cite/Spotify-found. 
- Reasoning-tier models are likely bad fit for constrained-pool selection; always eval before recommending. 

### Phase 6.0 — cost reduction bundle

Priority changed:
- Cost > Speed > Quality non-regression.
- Improvements must outweigh regressions 2:1.
- Quality regressions weighted 4:1.
- Cite Δ ≥13pp treated as variance/regression until validated over ≥5 blocks. 

Shipped:
- L1 Stage 2 skip if Stage 1 avoid overlap is zero.
- L8 strip empty prompt lines.
- L11 over-request `+5 → +2`.
- L16 cached-token telemetry.
- 5 tests added; 1,121 core tests pass. 

Outcome:
- Predicted ~36% cost reduction.
- No measured quality regression yet, but validation eval still queued. Treat as implemented but not fully validated. 

## Key learned facts

- Original issue was architecture, not simply model choice:
  - One mega-call with large profile/deny/RAG context caused cost and constraint problems.
  - Staged pipeline makes each step measurable and enforceable. 
- RAG pool quality matters more than pool size:
  - Pool=200 was noisy and led models to rescue from outside pool.
  - Pool=32 after retrieval cleanup gave 93% on-genre and HC2=0. 
- Prompt “rules” were not enough:
  - HC2/HC1 must be code-enforced drops, not just logged.
  - Schema collapse can look like Spotify success if fuzzy search finds self-titled tracks; telemetry must inspect raw rows. 
- Stage 3 must be grounded at track level:
  - Bare artist lists cause plausible title hallucination.
  - `known:` track overlay is the load-bearing fix. 
- Hard quotas trigger hallucination:
  - “Generate ≥ batch_size” without omit escape caused artist-name echo/schema collapse.
  - Safer contract: up to N tracks; omission is correct when uncertain. 
- `confirmed` artists should not be denied by default:
  - They are the artists the model knows best.
  - Do not re-add `confirmed` to `_deny_keys` unless eval proves schema-collapse ≤5%. 
- Substring cite telemetry was weak:
  - Model paraphrases caused false negatives.
  - Fixed with token-set match + stop-word filter in Phase 2.6. 
- `json_schema` was not a free win:
  - Increased cost/wall time; reduced quality/cite behavior.
  - Optional-field pressure caused information cramming into capped `arg`. 
- Reasoning-tier models are wrong for this workload:
  - Task is constrained selection, not reasoning.
  - `gpt-5.5` overthinks, drifts off-list, costs/latency explode. 
- Stage 2 skip is probably safe for canonical workload:
  - Sweep showed Stage 2 never dropped candidates at pool ≤40 when Stage 1 avoid tag filter already cleared pool.
  - Phase 6 L1 now skips only when mathematically no overlap exists. 
- Spotify evals can be corrupted by quota burn:
  - Long `gpt-5.5` run caused 429 cascade for following models.
  - Mitigated by lower concurrency, more retries, inter-model cooldown. 

## Current measured quality/cost summary

| Area | Current best known state |
|---|---|
| Spotify-found | 100% for `gpt-5.4` and `gpt-5.4-mini` in Phase 2.6 baseline.  |
| Must-have cite | 93.3% `gpt-5.4`; 86.7% `gpt-5.4-mini` in Phase 2.6 baseline.  |
| HC2 out-of-pool | 0 in Phase 2.6 baseline; now structurally dropped.  |
| Stage 1 on-genre | Historical fixed pool=32: 93%.  |
| Profile-update cost | Down 56–64% from P3.1 mutable-section projection.  |
| Phase 6 cost | Predicted ~36% lower per 1,000 playlists; validation pending.  |
| Dislike rate | Still not re-measured on fixed pipeline; OPEN-1 blocker.  |
| `gpt-5.5` | Avoid/unfit for SpotyVibe.  |

## Open items / still needs update

### Blocking

- OPEN-1: manual dislike-rate measurement on fixed pipeline.
  - Need ≥100 judged tracks over real usage / ~1 week.
  - Target: dislike rate ≤25%.
  - This gates P2.3, P3.3, P5, and most cost/model decisions. 

### High-value deferred

- OPEN-2 / P2.3: code-side semantic avoid filter after Spotify verification.
  - Pull verified track Spotify genres.
  - Map avoid traits to genre aliases.
  - Drop/log matches.
  - Build only if OPEN-1 proves avoid leakage is real. 
- OPEN-5 / P3.2: profile consolidation on overgrowth.
  - Section-size telemetry is done.
  - LLM consolidation call still deferred until profiles cross thresholds.
  - Acceptance: profiles ≤12KB after 10 AI Profile Updates; current example was 26KB before this work. 
- OPEN-6 / P3.3: periodic feedback absorption.
  - Liked/disliked reasons accumulate but do not yet update profile.
  - Build CLI/debug button first, then UI tip-toast.
  - Acceptance: 20 disliked reasons produce ≥2 recurring avoid entries. 
- OPEN-7: end-to-end local LLM verification.
  - Slim prompt + loader switch exist.
  - Needs Ollama run with Llama 3.2 3B / Qwen 2.5 7B. 
- OPEN-8 / Phase 4: structured `taste_vector`.
  - Replace freeform `taste_summary`.
  - Feed Stage 1/2/3 with deterministic compact vector.
  - Target Stage 3 prompt ≤1.5k tokens. 
- OPEN-9 / Phase 5: model A/B harness, gated by OPEN-1.
- OPEN-10 / Phase 5: latency optimizations: pipeline overlap, streaming UI, parallel Spotify verification. 
- OPEN-11: rerun full 5-model eval including `gpt-4.1` / `gpt-4.1-mini`; apply no-regression gate vs `20260428-062909`; update `ModelRecommendations.md`. 
- OPEN-12: classify any future reasoning-tier model before default/recommendation. 

### Reverted / do not blindly re-add

- Do not re-enable Stage 3 `json_schema` without a new schema strategy including optional fields; previous trial regressed cost/wall/quality. 
- Do not re-enable OPEN-4 pool widening as previously implemented; retry only under stricter trigger, e.g. first batch + omitted ≥80%. 
- Do not re-add `confirmed` to deny keys without canonical eval showing schema-collapse ≤5%. 
- Do not treat `gpt-5.5` as default quality model; it is classified unfit for this constrained-pool task. 

### Carry-forward bugs / docs / tests

- CF-Bug-1: player auto-advance regression; investigate Web Playback SDK state and add timeout fallback. 
- CF-Bug-2: player title wrap still stretches; tighten CSS. 
- CF-Bug-3: like/dislike click breaks player initialization; likely related to CF-Bug-1. 
- CF-Bug-6: track removal does not stop playback; player gets stuck. 
- CF-Bug-7: Settings Save needs disabled state/spinner. 
- CF-Test-1: replace brittle Playwright text selectors with aria/data hooks. 
- CF-Test-2: profile cache TOCTOU; defer unless hosted/multiprocess. 
- CF-Test-3: add regression tests pinning P0/P1/P2 contracts. 
- CF-Doc-1: update UserManual + README for artist dislike and offline-corpus prompt. 

## Practical next actions

1. Validate Phase 6.0 bundle with eval; confirm predicted ~36% cost reduction and no quality regression.
2. Run OPEN-1 real-user dislike-rate measurement: ≥100 judged tracks; target ≤25%.
3. Re-run 5-model eval after Spotify quota drain; update model recommendations.
4. If OPEN-1 passes:
   - Build P3.2 consolidation if section thresholds are hit.
   - Prototype P3.3 feedback absorption via CLI/debug button.
   - Start P5 A/B only after quality gate holds.
5. If OPEN-1 fails:
   - Inspect dislikes by avoid leakage vs retrieval mismatch vs track choice.
   - Build P2.3 semantic avoid filter only if avoid leakage is measured.
6. Keep `gpt-5.5` out of default/recommended path unless future eval contradicts current unfit classification.