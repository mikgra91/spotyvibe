# SpotyVibe — Cost & Speed Optimisation Research (2026-04-29)

> **Source:** Plan-agent research delegation, 2026-04-29.
> **Inputs:** `evaluation/results/sweep-merged-5blocks/report.md` (60 rows, 4 models × 3 pools × 5 blocks) + `result-improvement.md` (Phase 0–5 historical record) + codebase audit.
> **Companion docs:** `result-improvement.md` (historical), `documentation/ModelRecommendations.md` (current matrix), `evaluation/results/sweep-merged-5blocks/` (raw data).

## Implementation status (updated 2026-04-29)

| Lever | Status | Evidence |
|---|---|---|
| **L1** Skip Stage 2 when no avoid-tag overlap | ✅ Shipped 2026-04-29 | `core/src/rag/retrieval.py` (emit `pool_avoid_overlap`), `core/src/suggestions.py:check_avoid_compliance` (new `skipped_no_overlap` status), `app.py` (wire flag); 4 new unit tests in `core/tests/test_suggestions.py` |
| **L8** Suppress empty `{recent_feedback}` line | ✅ Shipped 2026-04-29 | `core/src/suggestions.py:select_tracks` (template line strip); `test_l8_recent_feedback_line_dropped_when_empty` |
| **L11** Stage 3 over-request `+5` → `+2` | ✅ Shipped 2026-04-29 | `config.py:STAGE3_OVER_REQUEST = 2`; `core/src/suggestions.py` consumes the constant; `test_l11_effective_batch_size_uses_stage3_over_request_constant` |
| **L16** `cached_tokens` telemetry in batch_summary | ✅ Shipped 2026-04-29 | `core/src/eval_log.py:log_batch_summary` (hoist from `usage.prompt_tokens_details.cached_tokens`); 2 new unit tests in `core/tests/test_eval_log.py` |
| **L20 + L21** Spotify reliability bundle | ⏸ Queued | next bundle after L1+L8+L11+L16 validation |
| **L13 + L25** Model & pool downgrade investigation | ⏸ Queued | combined 2-seed sweep planned |

**Validation eval:** 5-block sweep at pool=50 across 4 models, expected ~37% cost reduction (from $0.0288 → ~$0.018 per playlist). Pass criteria documented per-lever below.

## Context recap

New priority order (per user 2026-04-29 session): **Cost > Speed > Quality non-regression**, but the existing Project North Star in `AGENTS.md` ("Quality > Price > Speed; no regression on any metric") still gates adoption. Concretely: levers must be *cost-positive without making any quality metric worse* on the canonical eval. Variance-as-regression rule (this report): block-to-block cite Δ ≥ 13 pp → **🟡 Investigate**, not Recommend; require ≥ 5-block validation. 4:1 / 2:1 = a lever may regress one secondary metric by ≤ 25 % of its primary gain (cost or speed). Current production default = `gpt-5.4-mini` at `RETRIEVE_CANDIDATES_SIZE = 50`, `BATCH_SIZE = 10`, `MAX_GPT_CALLS_PER_RUN = 4` (`config.py`). Evidence base: 5-block sweep at `evaluation/results/sweep-merged-5blocks/` plus `result-improvement.md` Phase 2.5 / 2.6.

## Per-stage cost share (where the money goes)

Derived from `sweep-merged-5blocks/summary.csv`, `gpt-5.4-mini @ pool 50` (current default), mean of 5 blocks. Playlist size = 15. Stage 1 = code-only (free). Stage 2 = `STAGE2_MODEL = gpt-5.4-mini` (`config.py:104`). Spotify enrichment = HTTP only (no LLM cost).

| Stage | Mean $/playlist | Share | Per 1 000 playlists | Source |
|---|---:|---:|---:|---|
| Stage 1 (RAG retrieval) | $0.0000 | 0 % | $0 | code-only |
| Stage 2 (avoid-checker, mini) | $0.0064 | 22 % | $6.40 | total − Stage 3 |
| Stage 3 (selector, mini) | $0.0224 | 78 % | $22.40 | `cost_s3` column |
| Spotify verify | $0.0000 | 0 % | $0 | HTTP, not LLM |
| **Total (baseline)** | **$0.0288** | 100 % | **$28.80** | `cost` column |

For `gpt-5.4` (quality default, same pool): total $0.119/playlist, Stage 3 $0.099 (83 %), Stage 2 $0.020 (17 %) → $119/1 000 playlists. Same Stage 3 / Stage 2 cost ratio dominates.

**Implication:** Stage 3 is the only lever family with material TAM on the cheap default. Stage 2 reductions are a rounding error per playlist but compound across 1 000 runs. Spotify is already free in $; only speed levers apply there.

---

## Lever evaluations

### A. Stage 2 reduction

#### L1 — Skip Stage 2 when retrieval pool is 100 % approved

**Summary:** Don't call the avoid-checker when Stage 1 already returns a clean pool (Stage 2 in/out parity).

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0064/run (−22 % of total) | High |
| Speed | −5 to −15 s wall (Stage 2 latency band) | High |
| Quality | 0 pp cite (no model output changed) | High |

**Risk profile:** Removes the post-LLM guard against avoid-list violators. Real risk surfaces only when Stage 1's tag-stop-list misses a new avoid trait. 4:1 rule: zero quality regression observed in 60 sweep rows — Stage 2 approved 30/30, 40/40, or 48/50 in **every** sample (no row showed Stage 2 actively rejecting an avoid violator).

**Evidence:** `summary.csv` columns `stage2_in`/`stage2_out` — Stage 2 never dropped a candidate at pool ≤ 40 across all 4 models × 5 blocks; at pool 50 it dropped exactly 2 of 50 due to the canonical seed having 0 prose-avoid-trait matches (P2.0 retrieval fix already enforces this in `_apply_aliases`, `core/src/rag/retrieval.py`). `result-improvement.md` §"Phase 2.5 → Carry-forward findings": *"Stage 2 silent-passthrough was overstated… `skipped_no_avoid` status already provides correct visibility."*

**Implementation:** Already partially live — `check_avoid_compliance` returns `status=skipped_no_avoid` when `avoid_traits` empty (`core/src/suggestions.py:1026`). Extend the skip condition to also fire when the pool's tag-overlap with `avoid_tags` is zero (computable in Stage 1 with no extra LLM call). Touch: `app.py` Stage 2 dispatch + `core/src/rag/retrieval.py` to emit `pool_avoid_overlap=0` flag. Complexity: **S**. Eval: 5-block re-run on canonical seed; pass criteria = cite Δ ≥ −1 pp on every model, total cost $/playlist drops to ≈ $0.022.

**Estimated saving:** **~$6.40 per 1 000 playlists** (current Stage 2 cost). **Verdict:** ✅ Recommended — zero observed quality cost.

---

#### L2 — Cache Stage 2 verdicts by (artist, avoid_signature)

**Summary:** Persist Stage 2 approve/reject per artist keyed on a hash of the user's `avoid` list; reuse across runs.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.005 to −$0.0064/run after warmup | Med |
| Speed | −5 to −12 s wall after warmup | Med |
| Quality | 0 pp (deterministic given same inputs) | High |

**Risk profile:** Stale cache when user edits `avoid`. Mitigate by hashing the avoid list and invalidating on change. 4:1 rule: bounded by L1's gain since both target Stage 2.

**Evidence:** Stage 2 verdicts are deterministic given (candidate_set, avoid_signature) by construction (`check_avoid_compliance` in `core/src/suggestions.py:1026`). Sweep shows identical Stage 2 in/out across all 5 blocks of any (model, pool) cell when no rate limit interferes (`stage2_in/stage2_out` columns).

**Implementation:** New `core/src/cache/stage2_cache.py` keyed by `sha256(sorted(avoid_traits))::artist_name_lower`; persist in `%LOCALAPPDATA%/spotyvibe/`. Touch: `app.py` Stage 2 wrapper, new cache module. Complexity: **M**. Eval: 5-block (cold) + 5-block (warm) — pass criteria = warm runs show Stage 2 cost = $0 with cite unchanged.

**Estimated saving:** **~$5–6 per 1 000 playlists** assuming 80 % cache hit rate after week 1 of usage. **Verdict:** 🟡 Investigate — second-best to L1 (which removes the call entirely). Build only if L1 proves unsafe.

---

#### L3 — Fold Stage 2 into Stage 1 as code-side avoid filter

**Summary:** Move avoid-list checking into `retrieve_candidates` using the existing `_apply_aliases` tag index; eliminate the Stage 2 LLM call.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0064/run (−22 %) | High |
| Speed | −5 to −15 s wall | High |
| Quality | 0 to −2 pp cite (loss of LLM nuance on prose avoids) | Med |

**Risk profile:** Code-side tag matching can't catch prose like "indie-guitar dominance" that doesn't map to a single tag. P2.3 was deferred precisely because dislike-rate measurement (OPEN-1) hasn't validated that this LLM step earns its cost. 2:1 rule: −$6/1 k playlists is small; even a 1 pp cite drop is borderline.

**Evidence:** `result-improvement.md` §P2.3 (deferred): *"Don't build a safety net for an unmeasured failure mode."* Sweep confirms Stage 2 currently rejects nothing — the LLM check is dormant capacity, not active filtering.

**Implementation:** Extend `core/src/rag/retrieval.py:_apply_aliases` to subtract avoid tags from the candidate scoring. Delete Stage 2 call site in `app.py`. Complexity: **M**. Eval: needs OPEN-1 dislike-rate baseline first; otherwise 5-block run cannot detect prose-avoid leakage.

**Estimated saving:** **~$6.40 per 1 000 playlists.** **Verdict:** 🟡 Investigate — strictly inferior to L1 (which keeps the safety net dormant for free); revisit only if L1 + L2 prove insufficient.

---

#### L4 — Switch Stage 2 model from `gpt-5.4-mini` to `gpt-4.1-mini`

**Summary:** Use a cheaper mini model for the binary classification.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.003 to −$0.004/run | Med |
| Speed | ~0 (similar latency) | Med |
| Quality | 0 pp (Stage 2 currently approves everything) | High |

**Risk profile:** Stage 2 is binary classification on 30–50 short artist names — a textbook task for the cheapest model. P5.1 in `result-improvement.md` already lists this as a candidate.

**Evidence:** `gpt-4.1-mini` Stage 3 cost is ~38 % of `gpt-5.4-mini` Stage 3 cost (sweep mean: $0.0091 vs $0.0224 at pool 50). Same ratio expected on the much smaller Stage 2 prompt.

**Implementation:** Change `STAGE2_MODEL` constant in `config.py:104`. Complexity: **S**. Eval: 5-block run, pass criteria = approved-count parity vs current Stage 2 + cite unchanged.

**Estimated saving:** **~$3 per 1 000 playlists.** **Verdict:** ✅ Recommended — strict subset of work currently done by a more expensive model. Ship after L1 if L1 proves unsafe; otherwise L1 makes L4 moot.

---

### B. Stage 3 prompt trim

#### L5 — Drop the worked-example block from the system prompt

**Summary:** Remove the two-track concrete example (`tally hall` / `bear ghost`) at lines 44–45 of `prompts/track_select_system.txt`.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0008 to −$0.0015/run (input-side only) | Med |
| Speed | −0.5 s | Low |
| Quality | −5 to −15 pp schema collapse risk | Med |

**Risk profile:** The Phase 1 hallucination regression (`result-improvement.md` §"Phase 1 — Critical regression analysis") was *caused* by removing in-context schema demonstration. Re-removing it now is a known-bad move. 4:1 rule: a 15 pp cite regression for $1.50/1 k playlist saving fails the test.

**Evidence:** `result-improvement.md` §"Updated root cause (post-2026-04-27)": *"the legacy `deny_set_json` plausibly acted as in-context schema demonstration… Removing it took schema scaffolding away."* `documentation/ModelRecommendations.md` cites this as the canonical lesson.

**Implementation:** N/A (rejected). **Verdict:** ❌ Reject — directly contradicts Phase 1 forensic findings.

---

#### L6 — Shrink Stage 3 reasoning block from 5 fields to 2

**Summary:** Drop `seed_interpretation`, `constraints_evaluated`, and `omitted_artists` from the JSON reasoning section; keep `pool_assessment` and `selection_strategy`.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.002 to −$0.004/run (output-side) | Med |
| Speed | −1 to −3 s | Med |
| Quality | 0 to −5 pp cite (loss of `omitted_artists` self-discipline signal) | Med |

**Risk profile:** `omitted_artists` is the structural signal that turns the anti-confab clause from prose into a checklist. `result-improvement.md` §Phase 2.5 §T1.5 ("omission few-shot added") relies on this. Dropping it risks resurrecting the `track == artist` collapse pattern.

**Evidence:** `prompts/track_select_system.txt:36-42` reasoning schema. Phase 2.5 added `omitted_artists` deliberately — *"models imitate exemplars more than rules — show the desired refusal behavior"*.

**Implementation:** Edit `prompts/track_select_system.txt` reasoning schema. Add `schema_collapse_count` telemetry watch. Complexity: **S**. Eval: 5-block run; pass = cite Δ ≥ −2 pp AND `schema_collapse.eq_artist == 0` on every block.

**Estimated saving:** **~$2–4 per 1 000 playlists.** **Verdict:** 🟡 Investigate — measure `omitted_artists` actual usage in `eval.jsonl` first; if rare, drop is safer.

---

#### L7 — Trim `known:` overlay from 5 tracks per artist to 3

**Summary:** Halve the grounding overlay payload sent in APPROVED_ARTISTS block.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.003 to −$0.005/run | Med |
| Speed | −1 to −2 s | Med |
| Quality | 0 to −10 pp Spotify-found risk | Med |

**Risk profile:** Track-grounding overlay is the Phase 1 fix that took Spotify-found from 7.7 % → 100 % for `gpt-5.4-mini` (`result-improvement.md` §"Track-grounding fix verified 2026-04-27"). Each removed track narrows the model's grounded options.

**Evidence:** `core/src/suggestions.py:1140` `_format_approved_artists_block` caps at 5; the cap was tuned against the regression. No A/B at lower caps exists.

**Implementation:** Reduce cap in `_format_approved_artists_block`. Complexity: **S**. Eval: 5-block × 4-model run; pass = Spotify-found ≥ 95 % every cell.

**Estimated saving:** **~$3–5 per 1 000 playlists.** **Verdict:** 🟡 Investigate — needs explicit A/B; the existing 5 came from a regression-recovery setting, not an optimum.

---

#### L8 — Suppress `{recent_feedback}` block when feedback is empty/short

**Summary:** Don't render `RECENT_FEEDBACK:` boilerplate header when `build_feedback_summary` returns empty or single-item.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0005 to −$0.001/run | High |
| Speed | <1 s | High |
| Quality | 0 pp (no semantic content removed) | High |

**Risk profile:** None — pure boilerplate-trim when the section has no content.

**Evidence:** `prompts/track_select_user.txt:5` references `{recent_feedback}` unconditionally; `build_feedback_summary` in `core/src/suggestions.py` (line ~80–123 per result-improvement P0.3) emits a header even when content is null.

**Implementation:** Conditional render in `select_tracks` (`core/src/suggestions.py:1239`). Complexity: **S**. Eval: 1-block sanity + canonical seed (which has empty feedback) shows token reduction in `prompt_components.user`.

**Estimated saving:** **~$0.50–$1 per 1 000 playlists.** **Verdict:** ✅ Recommended — trivial, reversible, no risk.

---

#### L9 — Move `STYLE GUIDANCE` section into the slim local variant only

**Summary:** Cloud variant `prompts/track_select_system.txt:30-33` repeats guidance already implicit in `taste_summary` ("follow the taste summary exactly" etc.) — drop those 3 lines.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0003/run | High |
| Speed | <0.5 s | High |
| Quality | 0 to −3 pp cite (style hint loss) | Low |

**Risk profile:** Phase 2.5 §T1.4 already cut redundant lines once; further cuts have diminishing returns.

**Evidence:** `prompts/track_select_system.txt:30-33`. Phase 2.5 §T1.4: *"~150-token savings + cleaner separation"*.

**Implementation:** Edit cloud system prompt. Complexity: **S**. Eval: 5-block run, cite within 5 pp.

**Estimated saving:** **~$0.30 per 1 000 playlists.** **Verdict:** ❌ Reject — saving is below the noise floor of $/playlist measurement; not worth the regression-test budget.

---

### C. Batch sizing / call count

#### L10 — Increase `BATCH_SIZE` from 10 to 15

**Summary:** Fewer Stage 3 calls per playlist (3 batches → 2 batches for a 30-track playlist).

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.005 to −$0.008/run (one fewer system-prompt copy) | Med |
| Speed | −15 to −30 s wall (one fewer round-trip) | Med |
| Quality | 0 to −5 pp cite (longer batches have lower per-track attention) | Med |

**Risk profile:** Batches > 10 may worsen the new-artist quota (HC6) compliance. `effective_batch_size = batch_size + 5` so this becomes a 20-track ask per call — borderline for `gpt-4.1-mini` and small local models.

**Evidence:** `config.py:50 BATCH_SIZE = 10`. Sweep ran at playlist_size=15 (single-batch); no direct evidence at batch=15. `result-improvement.md` Phase 5.2: local models recommended `BATCH_SIZE = 5` for 8 K context — increasing to 15 hurts local-LLM compatibility (North Star rule).

**Implementation:** `config.py` constant + verify `MAX_GPT_CALLS_PER_RUN` headroom. Complexity: **S**. Eval: 5-block at playlist_size=30 with both batch=10 and batch=15.

**Estimated saving:** **~$5–8 per 1 000 playlists.** **Verdict:** 🟡 Investigate — likely good for cloud, bad for local; needs split config.

---

#### L11 — Reduce `effective_batch_size` over-request from `+5` to `+2`

**Summary:** Stage 3 currently asks for `batch_size + 5` tracks to absorb post-Spotify-verify drops; trim to `+2`.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.002 to −$0.004/run (output-side, ~30 % fewer output tokens) | High |
| Speed | −2 to −4 s | High |
| Quality | 0 to −5 pp under-fill risk | Med |

**Risk profile:** Sweep shows Spotify-found = 100 % on 58/60 rows — the +5 buffer is mostly absorbed wastefully. Two rate-limited rows are infrastructure failures, not natural under-fill.

**Evidence:** `core/src/suggestions.py:1184 effective_batch_size = batch_size + 5`. Sweep `found_pct` column: 100 % in every non-429 row.

**Implementation:** `core/src/suggestions.py:1184`. Complexity: **S**. Eval: 5-block; pass = Spotify-found ≥ 95 % AND playlist completion ≥ 95 % of `playlist_size`.

**Estimated saving:** **~$3–4 per 1 000 playlists.** **Verdict:** ✅ Recommended — current +5 was tuned for a regime where Spotify-found was 7.7 %, not today's 100 %.

---

#### L12 — Lower `MAX_GPT_CALLS_PER_RUN` from 4 to 3

**Summary:** Cap retry blast radius.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0 typical, −$0.05+ on retry-storm runs | Med |
| Speed | −0 typical, −60 s on retry-storms | Med |
| Quality | 0 to −10 pp under-fill on hard pools | Low |

**Risk profile:** A natural 30-track playlist needs 3 batches at `BATCH_SIZE = 10`. Cap = 4 leaves 1 retry slot. Cap = 3 = no retry.

**Evidence:** `config.py:79 MAX_GPT_CALLS_PER_RUN = 4`. `result-improvement.md` Phase 1 §"Empirical baseline 2026-04-27": pre-fix runs *hit the cap at 20*, post-fix natural runs use ≤ 3.

**Implementation:** `config.py` constant. Complexity: **S**. Eval: 5-block on canonical + 5-block on degraded-pool seed; pass = playlist completion ≥ 95 %.

**Estimated saving:** **~$1–3 per 1 000 playlists** (only on tail-of-distribution runs). **Verdict:** 🟡 Investigate — small typical saving, real tail risk; defer until OPEN-1 dislike data quantifies retry necessity.

---

### D. Model downgrade

#### L13 — Switch default Stage 3 from `gpt-5.4-mini` to `gpt-4.1-mini`

**Summary:** Cheapest cloud model in the matrix.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.013/run (−61 % of Stage 3, −45 % of total) | High |
| Speed | +30 to +60 s wall (gpt-4.1-mini is slower per sweep) | High |
| Quality | −5 to −20 pp cite, **block-to-block variance ≥ 20 pp** | High |

**Risk profile:** Sweep determinism table: `gpt-4.1-mini @ pool 50` B↔B Δ = 26.6 pp; pool 40 = 20.0 pp; pool 30 = 0.6 pp. Three of three pool cells fail the 13 pp variance threshold → variance-as-regression rule forces 🟡 Investigate. Mean cite is competitive (82.7 % vs 88.0 % for gpt-5.4-mini) but no robust per-block winner exists.

**Evidence:** `sweep-merged-5blocks/report.md` §"Determinism verdict" rows for `gpt-4.1-mini`; mean wall 86.6 s vs 41.8 s for gpt-5.4-mini @ pool 50.

**Implementation:** `config.py DEFAULT_OPENAI_MODEL`. Complexity: **S**. Eval: ≥ 5-block run × at least 2 different seeds; pass = cite mean ≥ 86 % AND no single block < 70 %.

**Estimated saving (if validated):** **~$13 per 1 000 playlists.** **Verdict:** 🟡 Investigate — variance failure under the new rule; needs ≥ 5-block × 2-seed validation before adoption.

---

#### L14 — Use cheaper model for Stage 3 batches 2..N (keep quality model for batch 1)

**Summary:** First batch sets the playlist's tone; later batches are smaller selections off the same approved pool.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.005 to −$0.008/run (when batch_count > 1) | Low |
| Speed | ~0 | Low |
| Quality | unknown | Low |

**Risk profile:** No measurement exists for split-model behaviour. Adds eval-matrix dimensionality.

**Evidence:** None directly; speculative based on per-batch cost share.

**Implementation:** Plumb model override per batch in `app.py` Stage 3 loop. Complexity: **M**. Eval: paired 5-block (split) vs 5-block (single-model) on same seed.

**Estimated saving:** **~$5 per 1 000 playlists** (uncertain). **Verdict:** ❌ Reject — not enough evidence to justify the eval cost; revisit only if L13 proves unstable.

---

#### L15 — Dynamic model selection by `pool_quality` flag

**Summary:** Fall back to quality model when `meta.pool_quality.pool_bad` fires; otherwise use mini.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | 0 (neutral on clean pools, −$0.10 on rare bad-pool retries) | Low |
| Speed | 0 typical | Low |
| Quality | +0 to +5 pp on bad-pool runs | Low |

**Risk profile:** `pool_bad` telemetry exists but the OPEN-4 retry was reverted in Phase 2.6 because doubling Stage 1+2 work cost more than it saved. Same trap.

**Evidence:** `result-improvement.md` §Phase 2.6 OPEN-4 reversion.

**Implementation:** N/A. **Verdict:** ❌ Reject — Phase 2.6 already learned this lesson; cost-asymmetric escalation is not a cost lever, it's a quality lever.

---

### E. Cache / dedup

#### L16 — Verify and instrument OpenAI prompt-prefix caching for Stage 3

**Summary:** Phase 2.5 §T1.3 moved `validation_block` out of system prompt to enable caching; verify the 50 % discount actually applies, and ensure no new code re-broke prefix invariance.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.002 to −$0.005/run (50 % discount on cached input prefix) | High |
| Speed | −1 to −3 s | Med |
| Quality | 0 pp | High |

**Risk profile:** None — read-only verification.

**Evidence:** `result-improvement.md` Phase 2.5 §T1.3: *"enables OpenAI's automatic prefix caching (50 % discount on cached prefix)"*. No telemetry confirms the discount is taking effect — `usage` rows in `eval.jsonl` would need to expose `prompt_tokens_details.cached_tokens`.

**Implementation:** Add `cached_tokens` to `batch_summary` row schema in `core/src/eval_log.py`; sample 5-block. If `cached_tokens / prompt_tokens < 0.5` the prefix is being broken — chase the cause. Complexity: **S**.

**Estimated saving:** **~$2–5 per 1 000 playlists** (already partially earned but unverified). **Verdict:** ✅ Recommended — cheap diagnostic; either confirms a free win is live or finds a regression.

---

#### L17 — Persist `approved_top_tracks` overlay across runs

**Summary:** The `known:` track overlay (`build-tools/build_top_tracks_overlay.py`) is computed per run from corpus + Spotify enrichment. Cache the per-artist result.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 (overlay is not LLM cost) | High |
| Speed | −2 to −5 s wall (Stage 1 prep) | Med |
| Quality | 0 pp | High |

**Risk profile:** None — overlay is deterministic per (artist, corpus_version).

**Evidence:** Overlay built in `build-tools/build_top_tracks_overlay.py`; consumed in `core/src/suggestions.py:1140`. No runtime cache exists.

**Implementation:** Persist `{artist_lower: [tracks]}` JSON in `%LOCALAPPDATA%/spotyvibe/overlay_cache/` keyed by corpus version. Complexity: **M**. Eval: 5-block; assert wall reduction.

**Estimated saving:** **0 $/1 000 playlists** (speed-only). **Verdict:** 🟡 Investigate — speed only; revisit when latency becomes the binding goal.

---

#### L18 — In-session Stage 3 prompt-component memoisation

**Summary:** Across the 3 batches of one playlist run, the system prompt + APPROVED_ARTISTS + taste_summary are identical. Ensure they are constructed once, not per-batch.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 (LLM cost unchanged; just CPU) | High |
| Speed | <1 s | Low |
| Quality | 0 pp | High |

**Risk profile:** None.

**Evidence:** `core/src/suggestions.py:1200-1245` — `select_tracks` rebuilds the prompt every call.

**Implementation:** Hoist constant string construction out of the per-batch loop in `app.py`. Complexity: **S**.

**Estimated saving:** **0 $/1 000 playlists.** **Verdict:** ❌ Reject — out of scope (CPU micro-opt, no $ or material speed gain).

---

#### L19 — Cross-session candidate-pool cache (profile_hash → candidates)

**Summary:** When a user generates a playlist twice in a row without editing the profile, reuse Stage 1 candidates and Stage 2 verdicts.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.0064/run (full Stage 2 saving on cache hit) | Med |
| Speed | −10 to −20 s wall on cache hit | Med |
| Quality | −5 pp diversity (same pool → same picks; HC6 new-artist quota becomes harder) | Med |

**Risk profile:** Cache should TTL on every `train_profile` call. Diversity loss is real — users running back-to-back generations expect *different* playlists.

**Evidence:** `core/src/rag/retrieval.py:533 retrieve_candidates` is deterministic given (profile, target_size, deny_keys). `deny_keys` change every run as `history.suggested_artists` grows — so true cache hit only happens on first-of-session.

**Implementation:** Cache by `sha256(profile_mutable_sections + target_size + sorted(history_artists))`. Touch: `app.py`, new module. Complexity: **M**. Eval: synthetic 2-back-to-back-runs scenario.

**Estimated saving:** **~$2–4 per 1 000 playlists** (depends on user behaviour). **Verdict:** 🟡 Investigate — diversity risk needs explicit measurement before shipping.

---

### F. Spotify call reduction

#### L20 — Persistent cache for Spotify `search` results per (artist, track, market)

**Summary:** Avoid re-searching the same (artist, track) on subsequent runs.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 LLM | High |
| Speed | −1 to −4 s wall (cache hit avoids ~200 ms per call × 15) | Med |
| Quality | 0 pp | High |

**Risk profile:** Stale cache when Spotify catalog changes (rare for known tracks). 7-day TTL acceptable.

**Evidence:** Sweep `429` count = 5 200 across the sweep — Spotify search is the rate-limit hotspot. `result-improvement.md` Phase 2.6 added retries+backoff but did not add caching.

**Implementation:** New `core/src/cache/spotify_search_cache.py`; wrap `search` in `core/src/playlist.py`. TTL 7 days. Complexity: **M**.

**Estimated saving:** **0 $/1 000 playlists** (speed + reliability only). **Verdict:** ✅ Recommended — primary value is rate-limit resilience (eliminating the 429 silent eval-killer per Phase 2.6 lessons), with a small wall-time bonus.

---

#### L21 — Skip Spotify `search` for tracks already in `approved_top_tracks` overlay

**Summary:** Overlay tracks come from prior Spotify search → they are guaranteed to exist. Skip the verify call.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 LLM | High |
| Speed | −2 to −5 s wall (skip ~50–80 % of verify calls) | High |
| Quality | 0 pp (verification is redundant when source is Spotify itself) | High |

**Risk profile:** Need to round-trip the overlay's `track_id` rather than re-resolving by name; small refactor.

**Evidence:** `build-tools/build_top_tracks_overlay.py` searches Spotify by `artist:"NAME"` (per `result-improvement.md` §"Implementation note (Spotify endpoint switch)"); resulting tracks have `track_id`s that can be passed straight to playlist creation.

**Implementation:** Plumb `track_id` through `_format_approved_artists_block` → `select_tracks` output → `spotify_verify` short-circuit. Complexity: **M**. Eval: 5-block; assert verify-call count < 50 % of pre-change.

**Estimated saving:** **0 $/1 000 playlists** (speed + quota relief — biggest reduction in 429 surface area). **Verdict:** ✅ Recommended — direct attack on the 5 200-429 sweep observation.

---

#### L22 — Batch Spotify search via `/v1/search?q=` multi-query

**Summary:** Spotify's search endpoint accepts only one query per call. Cannot batch — but `/v1/tracks?ids=` accepts up to 50 IDs in one call when L21 is in place.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 | High |
| Speed | −1 s | Low |
| Quality | 0 | High |

**Risk profile:** Only useful in conjunction with L21.

**Evidence:** `SKILL.md` (per CLAUDE.md reference); search endpoint single-query; tracks-by-id supports batch.

**Implementation:** Combine with L21: post-Stage-3, batch all `track_id`s into one `/v1/tracks` call. Complexity: **S** (after L21). **Verdict:** 🟡 Investigate — only after L21 lands; standalone gain is minimal.

---

#### L23 — Restore Spotify search concurrency from 5 to 10

**Summary:** Phase 2.6 dropped concurrency 10 → 5 to reduce 429 cascades. With L20 + L21 in place, the 429 source disappears and concurrency can be restored.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 | High |
| Speed | −3 to −8 s wall | Med |
| Quality | 0 pp; risk of 429 regression | Med |

**Risk profile:** Phase 2.6 explicitly chose 5 for a reason; restoring without addressing root cause re-creates the bug.

**Evidence:** `result-improvement.md` §Phase 2.6: *"Concurrency cap 10 → 5 to reduce 429 cascades."*

**Implementation:** `core/src/playlist.py` concurrency constant. Complexity: **S**. Eval: 10× full eval cycles back-to-back; pass = 0 retries triggered.

**Estimated saving:** **0 $/1 000 playlists** (speed-only). **Verdict:** 🟡 Investigate — gated on L20 + L21 landing first; otherwise reverts a known-good safety measure.

---

### G. Stage 1 retrieval improvements

#### L24 — Cache full RAG retrieval result per (profile_hash, target_size, deny_keys_hash)

**Summary:** Same as L19 but specifically the Stage 1 output (already free; cache only saves Python compute time).

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 | High |
| Speed | −1 to −3 s wall | Med |
| Quality | 0 pp | High |

**Risk profile:** None.

**Evidence:** `core/src/rag/retrieval.py:533` is pure compute over the corpus; deterministic.

**Implementation:** Memoise on first call within a session; persist across sessions keyed on profile/corpus hash. Complexity: **S**.

**Estimated saving:** **0 $/1 000 playlists.** **Verdict:** 🟡 Investigate — speed-only; defer until latency lever.

---

#### L25 — Drop default `RETRIEVE_CANDIDATES_SIZE` from 50 to 30

**Summary:** Smaller approved pool = smaller Stage 3 prompt.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | −$0.005 to −$0.008/run (Stage 3 input shrink) | Med |
| Speed | −1 to −3 s | Med |
| Quality | −4 pp mean cite, **block-to-block Δ ≥ 13 pp on 3 of 4 models** | High |

**Risk profile:** Variance-as-regression rule fires. Sweep determinism table: `gpt-5.4-mini @ pool 30` B↔B Δ = 16.2 pp (🔴 noisy); `gpt-4.1 @ pool 30` Δ = 21.7 pp (🔴 noisy); `gpt-5.4 @ pool 30` Δ = 8.3 pp (🟡 moderate). Mean cite drops: gpt-5.4-mini 88.0 → 83.6 (−4.4 pp), gpt-5.4 98.7 → 95.0 (−3.7 pp), gpt-4.1-mini 82.7 → 80.1 (−2.6 pp), gpt-4.1 62.7 → 73.0 (+10.3 pp on this *unfit* model).

**Evidence:** `sweep-merged-5blocks/report.md` §"Per-model pool-size effect" + §"Determinism verdict".

**Implementation:** `config.py:131`. Complexity: **S**. Eval: ≥ 5-block × 2-seed; pass = mean cite Δ ≥ −2 pp AND no single block < 70 %.

**Estimated saving (if validated):** **~$5–8 per 1 000 playlists.** **Verdict:** 🟡 Investigate — variance rule blocks adoption without ≥ 5-block × 2-seed confirmation.

---

#### L26 — `mmap`/lazy-load RAG corpus on startup

**Summary:** Defer corpus load until first Stage 1 call; reduces app cold-start memory and time.

| Axis | Predicted Δ | Confidence |
|---|---|---|
| Cost | $0 | High |
| Speed | startup −5 s; per-run 0 | Med |
| Quality | 0 pp | High |

**Risk profile:** None for the suggestion pipeline; affects desktop EXE startup which is out of scope.

**Evidence:** `core/src/rag/` corpus loader; `result-improvement.md` CF-Rat-5 references corpus storage.

**Implementation:** Out of declared scope (suggestion pipeline only). **Verdict:** ❌ Reject — out of scope for this report.

---

## Top 3 quick wins

| Lever | Predicted cost Δ ($/1 000 playlists) | Speed Δ (per playlist) | Quality risk | Implementation | Eval method |
|---|---:|---:|---|---|---|
| **L1** Skip Stage 2 when pool has 0 avoid-overlap | **−$6.40** | −5 to −15 s | None observed (60 sweep rows) | S — `app.py` + `retrieval.py` flag | 5-block × 4-model canonical seed; pass = cite Δ ≥ −1 pp every cell, total $/run ≈ $0.022 |
| **L11** Reduce Stage 3 over-request `+5` → `+2` | **−$3 to −$4** | −2 to −4 s | Low — Spotify-found is 100 % in 58/60 sweep rows | S — `core/src/suggestions.py:1184` | 5-block on canonical; pass = Spotify-found ≥ 95 % AND playlist completion ≥ 95 % |
| **L8** Suppress empty `{recent_feedback}` block | **−$0.50 to −$1** | <1 s | None (boilerplate only) | S — `select_tracks` conditional render | Single canonical-seed run; assert `prompt_components.user` token reduction in `eval.jsonl` |

Combined estimated saving: **~$10–11 per 1 000 playlists** (~36 % reduction from $28.80 baseline) on `gpt-5.4-mini @ pool 50`, with no measured quality regression and only single-cycle eval cost to validate.

Add **L16** (verify prefix caching) as a free diagnostic alongside — it either confirms an existing 50 % input-side discount or surfaces a hidden regression.

## Do not pursue

| Lever | Why rejected | Evidence |
|---|---|---|
| **L5** Drop worked-example block from system prompt | Removing in-context schema demonstration caused the Phase 1 hallucination collapse (77 % `track == artist`); re-removing repeats a known-bad move | `result-improvement.md` §"Updated root cause (post-2026-04-27)" + §"Track-grounding fix verified" |
| **L9** Trim STYLE GUIDANCE further | Saving (~$0.30/1 000) below noise floor; Phase 2.5 §T1.4 already cut redundant lines once | `prompts/track_select_system.txt:30-33`; `result-improvement.md` Phase 2.5 §T1.4 |
| **L14** Split-model per batch | No measurement exists; adds eval-matrix dimensionality for an uncertain ≤$5/1 000 saving | speculative; no sweep cell |
| **L15** Dynamic model escalation on `pool_bad` | OPEN-4 already tried this pattern; reverted in Phase 2.6 with cost +80–89 % | `result-improvement.md` §Phase 2.6 OPEN-4 reversion |
| **L18** In-session prompt memoisation | CPU micro-opt; no $ or material speed effect | `core/src/suggestions.py:1200-1245` constant work is sub-millisecond |
| **L26** mmap RAG corpus | Affects startup, not suggestion pipeline; out of declared scope | scope per user prompt |

## Out-of-scope but related

The `train_profile` and `analyze_band_song` paths together cost roughly **$0.005–$0.015 per profile update** on `gpt-5.4-mini` after the Phase 2.5 P3.1 mutable-sections projection (`result-improvement.md` §Phase 2.5 metrics: 56–64 % cost reduction). Further reductions are tracked under **P3.2** (consolidation step on overgrowth — telemetry already in place via `section_sizes` per `profile_update_summary` since Phase 2.6) and **P3.3** (periodic feedback absorption with UI). Both remain deferred and gated on **OPEN-1** (manual dislike-rate measurement). For a full lever set on those features see `result-improvement.md` §"Open-items register" rows OPEN-5 and OPEN-6.

