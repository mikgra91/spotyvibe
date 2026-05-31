# Analysis — why is suggestion quality so bad?

> **Audience:** the next session (yours or mine). I went away to think
> hard about your frustration: "RAG is in place, models are trained on
> music, instructions are clear — this should be easy. Why is it not?"
> The receipts below answer that.
>
> **Bottom line up front:** I found a smoking-gun root cause in the
> Haiku 1/30 failure. It is not a fundamental design problem with RAG
> or the prompt — it is a one-line config bug in how we cap output
> tokens on OpenRouter. Fix it and Haiku's catastrophic refusal
> probably disappears. The deeper "should this even be hard?"
> framing question is *no*, and I have a hypothesis about why the
> current architecture still struggles when nothing should be in
> the way.

---

## 1. The diagnostic chain you should follow next session

These are the breadcrumbs. Each item points to a file + finding so a
future session can pick up without re-deriving.

1. **PRIMARY ROOT CAUSE — output-token truncation.**
   - File: [`core/src/openai_http.py`](core/src/openai_http.py)
     `SPOTYVIBE_MAX_OUTPUT_TOKENS` block (history: commit `c7a7e43`).
   - File: [`evaluation/benchmark/runner.py`](evaluation/benchmark/runner.py)
     `os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "4000")`.
   - File: same env var also set in
     [`evaluation/run_evaluation.py:531`](evaluation/run_evaluation.py#L531).
   - **Evidence:** Haiku's aged_japanese_session5 trace_A.json
     (`benchmark-20260523-173726-anthropic_claude-haiku-4.5/`)
     batches 2-4 all have `tokens_out == 4000` (exact cap), and the
     raw_response is truncated JSON ("Unterminated string"). Batch 1
     used 2450 tokens, parsed cleanly, returned 12 picks. Cap = bug.
   - **Why the cap exists:** OpenRouter's `:free` tier rejects
     requests that don't include `max_tokens`. The 4000 value was a
     safety pick to stay inside the free-tier ~8k credit budget.
   - **Why it bites paid Haiku:** the cap was applied to ALL
     OpenRouter routes, including paid models with much higher
     output budgets. Haiku's verbose reasoning block + 12 picks +
     long `omitted_artists` list trivially exceeds 4000 output tokens.
   - **Fix (small, safe, high-leverage):**
     - In both `runner.py` and `run_evaluation.py`, only set the
       4000 cap when the model id contains `:free`. Otherwise set
       `SPOTYVIBE_MAX_OUTPUT_TOKENS=8000` (Anthropic Haiku 4.5
       default is 8192).
     - One-line change. No new tests required because the existing
       benchmark's `aged_japanese_session5` scenario will flip
       Haiku from FAIL → expected WARN/PASS after the cap is fixed.
   - **Confidence: HIGH.** Token counts in the trace are unambiguous.

2. **SECONDARY ROOT CAUSE — reasoning-block size in the prompt.**
   - File: [`prompts/track_select_system.txt`](prompts/track_select_system.txt)
     lines 38-44 (the `reasoning` block).
   - The block requires `seed_interpretation`, `pool_assessment`,
     `selection_strategy`, `omitted_artists`, `constraints_evaluated`.
     Each is "1-3 sentences" but models routinely write longer.
     Combined they consume ~1000-2000 output tokens before the
     playlist even starts.
   - The original purpose was diagnostic: tell us *why* the model
     picked or omitted (filed under "F9 trace bundles" in
     `next-steps.md`). Useful for offline analysis, expensive for
     production.
   - **Fix (medium, requires re-eval):** keep `selection_strategy`
     + `omitted_artists` (we use these for the bad-pool detection
     in `meta["pool_quality"]`); drop the other three fields.
     Estimated saving: 500-1000 tokens per batch.
   - **Confidence: MEDIUM.** The diagnostic value is real;
     removing has to be balanced against retaining post-mortem
     ability. Could move them behind a `DEBUG_MODE`-only flag.

3. **TERTIARY — the "OMIT unless certain" framing is biased toward
   refusal.**
   - File: [`prompts/track_select_system.txt`](prompts/track_select_system.txt)
     lines 11, 15, 28 — the SAME instruction appears three times:
     "OMIT that artist unless you are sure".
   - Repetition strengthens it. Cautious models (Haiku, Gemini)
     interpret it as "default = OMIT, exception = PICK".
   - This contradicts the user's correct mental model: the model
     is **given** a `known:` list of Spotify-verified tracks per
     artist. There is no confabulation risk in picking from that
     list — Spotify verified those titles exist.
   - **Fix (medium-risk, needs eval validation):** invert the
     polarity. Frame it as **"PICK from `known:` lines by default;
     OMIT only when no `known:` line is shown for that artist."**
     The current wording leaves room for "model recalls something
     better → use that"; that flexibility is the failure surface.
   - **Confidence: MEDIUM.** Hypothesis from prompt reading +
     trace pattern, not yet eval-validated. Could regress
     confabulation rates on edge cases.

4. **QUATERNARY — `_run_unverified` already prunes the overlay.**
   - File: [`app.py`](app.py) `_prune_dead_tracks_from_overlay`
     (the Q2 fix I shipped 2026-05-23).
   - This works correctly for tracks that fail Spotify resolution
     during the run. But Q2 only fires when there IS something
     to prune — empty Stage 3 batches don't trigger it.
   - Composition with fix #3: if fix #3 lands and models reliably
     pick from `known:` lines, Q2's overlay pruning becomes more
     load-bearing (cross-batch novelty within the same `known:`
     list). Already tested.

---

## 2. The deeper "why should this even be hard?" answer

You asked the right question. With the corpus + the prompt + the
RAG hand-off, **the model's task is constrained selection**, not
open-ended generation. It's literally:

> Here are 50 artist names. Here are 5 Spotify-verified track titles
> per artist. Pick 12 of them that match the taste summary.

Nothing about this requires music knowledge. The corpus has done the
domain work. The model's job is filtering.

So why isn't it trivial? Three reasons, in order of impact:

### A. We don't TRUST the corpus enough in the prompt
The system prompt says (line 10) `known:` lines "are GROUNDING — pick
one of those titles **unless you confidently recall another real
released track**". That "unless" clause is the trap. It invites the
model to leave the safe path of picking from the verified list and
generate from its training data. Cautious models read "unless you're
confident" as a high bar and OMIT. Less cautious models read it as
license to confabulate. **Either failure mode comes from the same
escape hatch.** Close the hatch: pick from `known:` PERIOD, deviate
only when the user/scenario flags emerging-only / discovery mode
explicitly.

### B. The reasoning block invites talking instead of picking
A model told to "explain your selection in 4 prose fields before
emitting JSON" will burn budget on the explanation. We see this in
Haiku's traces: 80% of the truncated output is reasoning prose, 20%
is the playlist. The reasoning block was designed to help us debug;
its production cost is that the playlist itself competes with the
prose for output tokens. Once tokens run out, the playlist (which
comes LAST in JSON order) is what gets clipped.

### C. We inherited B-11's confabulation safeguards even when they
no longer apply

The omission rule + "Returning FEWER is correct" rule were added
when the corpus had thin or no `top_tracks` coverage and Stage 3
genuinely had to recall titles from parametric memory. Confabulation
was a real risk back then.

But the 2026-05-19 corpus rebuild changed the world: 83.4% of
artists now ship with 5 Spotify-verified `top_tracks` baked in.
The B-11 problem is largely solved at the data layer. The safeguards
in the prompt are now over-fitted to a world that no longer exists,
and they cause the OPPOSITE failure (refusal) on cautious models.

This explains the eval discrepancy: probes like B-11 measure
confabulation rate. They show "confabulation low → ship it." They
do NOT measure refusal rate. So the prompt got tuned increasingly
hard against confabulation while refusal silently rose.

---

## 3. What the receipts say across the two completed benchmarks

| Model | aged_japanese_session5 | Mechanism |
|---|---|---|
| gpt-5.4-mini | 30/30 verified, 47% found, WARN | Survived the 4000 cap by being terse |
| claude-haiku-4.5 | 1/30 verified, 25% found, FAIL | Hit cap on 3 of 4 batches → empty |

| Model | broad_mainstream_clean (playlist A) | Mechanism |
|---|---|---|
| gpt-5.4-mini | 20/30 verified | Stage 3 returned 0 picks on batches 2-3 (also token-cap clipping; mini also has the issue, just less often than haiku) |
| claude-haiku-4.5 | 30/30 verified, 80% found, WARN | First scenario, no carry-over state, fits comfortably under 4000 |

The pattern is consistent across both models: **whenever a batch
emits a large reasoning block, the playlist gets clipped.** It's not
a model-specific quality issue. It's a token-budget issue that
manifests as random "empty Stage 3" failures.

---

## 4. Ranked fix proposal — quality / speed / cost

Your three meta-questions answered together:

### Quality wins (in expected impact order)

1. **Raise `SPOTYVIBE_MAX_OUTPUT_TOKENS` to 8000 for paid OpenRouter
   routes; keep 4000 only for `:free`.** Smallest possible change,
   highest expected lift. Estimated effect: Haiku aged_japanese
   1→25+ verified; mini broad_mainstream 20→27+. Cost: zero
   (we pay for output tokens we actually generate; the cap was
   only ever a safety check).

2. **Slim the reasoning block** to `selection_strategy` +
   `omitted_artists`. Saves 500-1000 output tokens per batch,
   reduces clipping risk further. Cost: lose 3 diagnostic fields
   (gate behind `DEBUG_MODE` to keep them for analysis).

3. **Invert the omission framing**: PICK from `known:` by default,
   OMIT only when no `known:` line exists. Eliminates the "trust
   parametric memory" escape hatch. Risk: needs eval validation
   on a confabulation probe (B-11) to ensure we don't regress.

### Cost wins

1. **Reasoning-block slimming (item Q2 above)** also reduces output
   tokens you pay for. Estimated saving: 0.3-0.5¢ per playlist on
   Haiku, less on cheaper models.

2. **Single Stage 3 call per playlist instead of multi-batch** — the
   current 3-4 batches per playlist costs 3-4× system-prompt tokens
   you pay for repeatedly. Could be one larger call with
   `batch_size=30`. Cost trade-off: lose adaptive retries on
   filter failures. Open question — would need eval.

3. **Drop the model-tailored validation block** for models we don't
   actually serve (anything outside the 3 currently-recommended).
   The branching adds prompt bytes for no benefit when the model
   isn't in the strict list.

### Speed wins

1. **Same as cost win #2** — one Stage 3 call removes the per-batch
   round-trip + Spotify-verify pipeline overhead. Could halve
   wall time per playlist.

2. **Parallelize Spotify verify**. Already exists (10 workers) but
   tightening per-call timeouts would help on the tail.

3. **Lighter reasoning block** (item Q2) → fewer output tokens →
   faster end-to-end on streaming.

---

## 5. What I think you should do next session

In order:

1. **Apply fix #1** (raise the token cap for paid routes). Single-
   commit change. Then re-run `python -m evaluation.benchmark
   --model anthropic/claude-haiku-4.5` after the Spotify cooldown
   drains. Expectation: Haiku's aged_japanese flips FAIL → WARN
   or PASS. **This is the load-bearing experiment.** If it does,
   the project is no longer in jeopardy and we can move to fix
   #2 and #3 calmly. If it doesn't, my diagnosis is wrong and
   we need to dig deeper.

2. If fix #1 works, **ship fix #2** (slim reasoning block) and
   re-benchmark. Expectation: WARN → PASS on aged scenarios for
   both models.

3. If fix #2 works, **propose fix #3** (invert omission framing)
   to me for review. This is the highest-risk one — it changes
   behavioural defaults — and deserves a manual gut-check before
   shipping.

4. **Decide on the "single Stage 3 call vs multi-batch"
   architectural question** separately. That's a real
   restructure and should not happen in the same week as
   fixes 1-3.

---

## 6. Open questions I couldn't answer this session

- Is there a way to ask OpenRouter for the model's max-output limit
  programmatically? If so, we could remove the env-var cap entirely
  and just use whatever the model supports.
- Does Gemini Flash Lite have the same truncation behaviour at
  4000 tokens? Couldn't test today (Spotify cooldown). Strong
  prior: yes.
- The contradictory_facets scenario passed cleanly on mini at
  28/18 → is the gate threshold too soft, or is the model
  legitimately handling the contradiction well? Manual ear test
  required.

---

## 7. Reading list for next session (in order)

These are the files that contain the meat. Skip the rest.

1. [`prompts/track_select_system.txt`](prompts/track_select_system.txt)
   — lines 10, 11, 15, 24-28, 38-44. The omission/reasoning core.
2. [`core/src/suggestions.py:_format_approved_artists_block`](core/src/suggestions.py)
   — line ~1604. How `known:` lines get rendered.
3. [`core/src/suggestions.py:select_tracks`](core/src/suggestions.py)
   — line ~1641. The Stage 3 orchestrator.
4. [`core/src/openai_http.py`](core/src/openai_http.py)
   — `SPOTYVIBE_MAX_OUTPUT_TOKENS` block. The single-line bug.
5. [`evaluation/benchmark/runner.py`](evaluation/benchmark/runner.py)
   — `os.environ.setdefault("SPOTYVIBE_MAX_OUTPUT_TOKENS", "4000")`.
6. The trace bundle that proves it:
   `evaluation/results/benchmark-20260523-173726-anthropic_claude-haiku-4.5/aged_japanese_session5__anthropic_claude-haiku-4.5-iter1/trace_A.json`
   — open the `stage3_batches[i].usage.completion_tokens` field.

---

## 8. One sentence each, the meta-questions you asked me

- **"How can I provide the best quality?"** → Stop letting Stage 3
  recall titles from parametric memory; force it to pick from the
  Spotify-verified `known:` list. The corpus already did the work;
  the prompt undoes it.
- **"How can I save money?"** → Slim the reasoning block to two
  fields (`selection_strategy`, `omitted_artists`). 500-1000
  output tokens saved per batch. Bonus: faster.
- **"What is the cause of inconsistency?"** → Output-token truncation
  randomly clips the JSON, randomly emptying the playlist. We
  thought it was model variance. It is a deterministic config bug
  hidden by appearing random.
- **"Should this be a hard task for AI models?"** → No. We made it
  hard by writing safeguards for a world (sparse corpus, models
  hallucinating titles) that no longer exists. The 2026-05-19
  corpus rebuild ended that world; the prompt hasn't caught up.

---

*Generated 2026-05-23. The diagnosis is hypothesis-backed by trace
evidence; it is NOT eval-validated because Spotify is on a 3-hour
rate-limit cooldown. Validate fix #1 first, then proceed.*
