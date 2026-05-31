# Automation analysis — what to measure without humans in the loop

> **Premise.** You are one developer. Manual cross-model testing is
> not sustainable. The benchmark is a one-shot snapshot. We need a
> continuous, automatic signal that catches regressions and proposes
> improvements without you having to think about it. This document
> is a ranked menu of what to add and what each costs.

---

## Guiding principles

1. **Reality first.** Every automated check must measure something
   that *correlates with what the user actually experiences*. A
   metric that's easy to compute but unrelated to UX is noise.
2. **Catch regressions, don't grade quality.** Subjective "is this
   playlist good?" is not automatable today. Objective failure modes
   (truncation, refusal, leakage, decay, recycling) ARE.
3. **Make the cheap signals always-on; gate the expensive ones.**
   Telemetry from production runs is essentially free. LLM-as-judge
   calls cost money — reserve them for the narrow questions where
   they pay off.
4. **The benchmark is for "is this model production-ready"; the
   continuous signal is for "did anything just regress."** Two
   different tools, two different cadences.

---

## Tier 1 — free signals we already collect but don't act on

These are computed from `eval.jsonl` and the trace bundle that the
production code ALREADY writes. Zero new infrastructure; just
new aggregations.

### 1.1 — Output-token saturation ratio
**What:** per batch, `completion_tokens / max_tokens_cap`.
**Why:** > 0.90 means the model is on the edge of truncation. Today's
Haiku 1/30 failure would have shown 1.00 on three batches days
before it bit. Pure leading indicator.
**Where:** add to per-batch `eval.jsonl` rows; surface in the
benchmark scorecard as a hard gate ("any batch ≥ 0.95 → WARN; any
batch == 1.00 → FAIL").
**Cost:** 0.

### 1.2 — Refusal rate
**What:** % of batches where `stage3_returned == 0`.
**Why:** Direct measurement of the "model gave up" failure. Should
be < 5 % per run in healthy state. If it climbs, prompt has
drifted toward refusal.
**Where:** `run_summary` row in `eval.jsonl`; benchmark scorecard
new column.
**Cost:** 0.

### 1.3 — Pool utilization
**What:** unique artists that contributed ≥ 1 verified track ÷
`approved_pool_size`.
**Why:** Catches the "Stage 3 recycles 6 of 50 artists" pattern.
Below 0.30 = degenerate; above 0.60 = healthy.
**Where:** derive from `run_pool_initial` + per-batch
`spotify_found`. Add to scorecard.
**Cost:** 0.

### 1.4 — Per-batch Spotify-found-rate trend (slope)
**What:** linear regression slope of `spotify_found / requested`
across batches in one run.
**Why:** **Negative slope = dedup collapse in progress.** Captures
the run-over-run quality decay the user reported as the symptom of
the production failure. Slope > -0.05/batch = acceptable; <
-0.15/batch = degenerate.
**Where:** computed at run end, added to `run_summary`. Plot in
the scorecard.
**Cost:** 0.

### 1.5 — JSON-parse failure rate
**What:** `parse_failed_batches / total_batches`.
**Why:** Until today this was hidden — the parser silently
substituted an empty playlist. Now that we know it's a vector,
surface it. Should be exactly 0 in steady state.
**Where:** instrument `select_tracks` to emit a `parse_failed: bool`
field per batch.
**Cost:** 0.

### 1.6 — A6 / Q3 trigger rate
**What:** how often the pool-widening fallback fires.
**Why:** A6 firing IS a quality signal — it means Stage 1 misjudged
the pool size. Healthy = fires < 10 % of runs. Climbing = Stage 1
needs tuning.
**Where:** already in `run_exit.a6_reretrieve_triggered`; aggregate.
**Cost:** 0.

### 1.7 — Must-have cite-rate on rationale
**What:** % of picks where ≥ 1 rationale entry's `arg` quotes a
"Must:" trait verbatim.
**Why:** The most reliable relevance proxy we have. Probe B-4 already
computes this; promote it to a benchmark scorecard column so it's
visible on every run, not just probe runs.
**Where:** `core/src/suggestions.py` — already validated per
rationale; just emit per-batch.
**Cost:** 0.

**Implementation suggestion:** ship all seven as a single PR that
extends `_emit_batch_summary` in `app.py` and grows the scorecard's
per-scenario row. None of these require an extra LLM call. They turn
the benchmark from "did it pass the gate" into "did it pass AND is
it producing the patterns we expect."

---

## Tier 2 — cheap LLM-as-judge for narrowly scoped questions

LLM-as-judge has known biases (preference for verbosity, recency,
its own model family). They are unsuitable for SUBJECTIVE quality
("is this a good playlist?"). They are useful for SPECIFIC
yes/no questions where the criterion is concrete.

### 2.1 — Per-scenario "must_have compliance" pass
**What:** at the end of each scenario, send a CHEAP model
(gpt-4o-mini, gemini-flash) the playlist + the must_have list and
ask: "For each must_have, did ≥ 70 % of the tracks plausibly
satisfy it? Answer YES/NO per must_have."
**Why:** This is the missing signal between "the model cited the
trait" (we measure) and "the picks actually fit the trait" (we
don't). Bridges the objective→relevance gap cheaply.
**Constraint:** ONLY use for binary, criterion-driven judgments.
Never for "is the playlist good."
**Cost:** ~$0.001 per scenario × 6 scenarios × 3 models =
~$0.018 per full benchmark cycle. Negligible.
**Implementation:** new module `evaluation/benchmark/llm_judge.py`,
single-call protocol with deterministic structured output.

### 2.2 — "Does the rationale match the track?" sanity check
**What:** for a random 10 % sample of picks per scenario, ask the
judge model: "Track X by artist Y is rationalized as 'matches
Z'. Plausible? YES/NO."
**Why:** Catches "model writes plausible-sounding rationale but the
track doesn't actually match." Lower-priority than 2.1.
**Cost:** ~$0.005 per scenario.

### 2.3 — STRICTLY NOT to be done
- "Rate this playlist 1-10" — biased, unstable, useless.
- "Compare model A vs model B output side by side" — confounded by
  judge model's training.
- "Is this artist the best fit for the seed?" — open-ended,
  no ground truth.

---

## Tier 3 — scheduled / periodic automation

These are jobs that run on a clock without you triggering them.

### 3.1 — Nightly shadow eval
**What:** every night at 03:00 local, run the benchmark with the
CURRENT production model on a single scenario (`aged_japanese_session5`
— the most regression-sensitive). Write the scorecard to
`evaluation/results/nightly-{date}/`. Compare to the previous
night; alert (email, push notification, file) on any verdict
regression.
**Why:** Catches:
- Prompt edits that look fine in unit tests but regress quality.
- Corpus rebuilds that drop coverage on a sensitive area.
- OpenRouter model updates (silent model rolls).
**Cost:** ~$0.01 per night = ~$3.50 / year. Per-month cost less
than one paid lunch.
**Implementation:** GitHub Actions cron OR Windows Task Scheduler
calling `python -m evaluation.benchmark --scenarios aged_japanese_session5 --no-confirm`.
Combined with the Spotify pre-flight check, safe to run unattended.

### 3.2 — Weekly cross-model snapshot
**What:** every Sunday, run the full 6-scenario benchmark across
all 3 documented models. Auto-write the diff to
`evaluation/model-performance-result.md` (today the file is
manually edited; making this automatic ends the staleness problem).
**Why:** Keeps "which model is best?" verdict current without you
having to think about it.
**Cost:** ~$0.20/week = ~$10/year.

### 3.3 — On-PR probe battery
**What:** any PR that modifies `prompts/*.txt`, `core/src/suggestions.py`,
or `core/src/rag/` triggers the 8-probe Track B battery on
gpt-5.4-mini.
**Why:** Catches prompt regressions in 5 minutes for $0.10.
Specifically: the kind of "well-intentioned edit accidentally
breaks B-11" failure that the eval missed historically.
**Cost:** ~$0.10 per relevant PR.
**Implementation:** GitHub Actions; `evaluation/probes/cli.py`
already runs in non-interactive mode.

---

## Tier 4 — new measurement infrastructure

These need new code to be built.

### 4.1 — Profile-shape sweep generator
**What:** a script `evaluation/sweep/generate_profiles.py` that
varies the seven dimensions that empirically matter:
1. must_have count (1, 5, 10, 15)
2. avoid count (0, 3, 7, 12)
3. history depth (0, 10, 25, 50)
4. dislike count (0, 3, 8)
5. rejected-artist count (0, 1, 3)
6. genre breadth (single-genre, dual-genre, polyglot)
7. language constraint (English-only, regional)

Produces a Cartesian-product (or LHC sample) of profile fixtures.
The benchmark runs against them in parallel.
**Why:** Replaces hand-crafted scenarios with a continuous
parameter sweep. Discovers failure-mode edges that hand-picked
scenarios miss.
**Cost (setup):** half-day of work.
**Cost (run):** linear in number of profiles × scenarios.

### 4.2 — Production-trace mining → eval fixture
**What:** a script that scans `%LOCALAPPDATA%\spotyvibe\debug\*/trace.json`
for runs that meet a "real-usage" predicate (filled to ≥ 24, no
errors, profile has ≥ 5 history entries). For each, anonymize +
serialize as a `seed_profiles/realmine-{hash}.json` fixture.
Add to the benchmark scenario list automatically.
**Why:** The eval drifts toward synthetic taste. Real users have
weirder profiles. Mining production traces continuously expands
the eval's realism for free.
**Cost:** half-day of work; storage is negligible.
**Privacy:** strip `meta.goal` free text, normalize artist names
to lowercase, drop run_id metadata.

### 4.3 — Per-model output-budget calibrator
**What:** a one-time script `evaluation/calibrate_budget.py` that
sends each documented model a max-out prompt and records the actual
limit OpenRouter applies. Writes `evaluation/model_budgets.json`
the runner reads instead of the hard-coded 4000/8000 split.
**Why:** Today's bug was a hard-coded value. A calibrated table
makes the cap automatic and self-correcting when OpenRouter changes
its budgets.
**Cost:** ~$0.01 per calibration × 3 models = $0.03. Run once,
re-run after model rolls.

### 4.4 — Real-failure replay queue
**What:** an endpoint `/api/eval/flag-run` the production UI calls
when the user manually rates a run as bad (a thumbs-down on the
WHOLE playlist, not individual tracks). Stores the trace +
anonymized profile in `evaluation/sandbox/flagged/`. A weekly job
materializes them as eval scenarios.
**Why:** Today, the user complains in chat. Future, the user
clicks a button and the failure is automatically queued for
regression testing.
**Cost:** day of frontend work (already in T1 ScopeAudit).

---

## Tier 5 — observability dashboard (optional, high-value if you
have ~1 day)

A single HTML page that reads `perf_log.sqlite` + `eval.jsonl` and
plots the Tier 1 metrics over time. Static — generated by a script,
no server needed. Catches "drift over weeks" patterns no single
benchmark can.

Key plots:
- Refusal rate per model, weekly average.
- Pool utilization distribution per scenario.
- Per-batch found-rate slope (negative = dedup decay accumulating).
- Cost variance per scenario (high variance = unpredictable).
- Token saturation percentile (95th percentile creeping toward 1.00
  = truncation risk rising).

Lives at `evaluation/dashboard.html`, regenerated by a `make dash`
target. Read it on Friday afternoon; if anything is bending the
wrong way, investigate before the weekend.

---

## How I would prioritize next session

If you have **2 hours**: ship Tier 1 items 1.1, 1.2, 1.5. They are
single-PR additions to existing telemetry, they directly capture
the failure modes we already know exist, and they make the
benchmark a real regression detector.

If you have **half a day**: add 1.3 + 1.4 + 1.7 (full Tier 1) and
wire item 3.1 (nightly shadow eval). After that, the system is
self-monitoring within the bounds of objective metrics.

If you have **a full day**: add 4.3 (budget calibrator) and 4.2
(production-trace mining). These pay off on a multi-month horizon
because they end two recurring sources of staleness.

If you have **two days**: add tier 5 (dashboard). Visualizing the
above signals over time is what catches the slow drifts that
single runs miss.

LLM-as-judge (Tier 2) is the LAST thing I'd add. It's expensive,
biased, and only valuable when the cheap signals can't isolate the
issue. Save it for when objective metrics say "something is wrong"
but can't say WHAT.

---

## What about the question "how to evaluate music suggestions"
without humans?

You can't evaluate *taste*. You CAN evaluate every objective property
of a playlist that humans care about indirectly:

- **Completeness** (does it fill to N tracks) — direct, easy.
- **Resolvability** (do the picks exist on Spotify) — direct, easy.
- **Constraint compliance** (does it avoid the avoid-list) — direct, easy.
- **Diversity** (unique artists, decade span, genre span) — direct,
  easy.
- **Era / language compliance** (when seed specifies) — direct,
  requires metadata lookup.
- **Discovery quality** (new vs known artist ratio) — direct.
- **Stability** (does the same input produce similar quality) —
  direct, requires repeat runs.

All of these are automatable. The only thing that requires a human
ear is "do these specific 30 tracks delight ME" — and even that
can be APPROXIMATED via the "thumbs down on the whole run" capture
in 4.4.

**Bottom line:** with the Tier 1 metrics + a nightly shadow eval
+ a real-failure replay queue, you have ~80 % of the signal a
team with a full QA function would have. The remaining 20 % is
subjective taste and is genuinely a human-only signal. Don't try
to automate it; just make it as cheap as possible for the human
(one click → captured fixture).

---

## Open question I keep coming back to

The corpus is the source of truth for *what tracks exist*. The
prompt is the source of truth for *which tracks fit the user*.
Today, the prompt asks the model to do BOTH (recall + filter). The
recall part is what causes most failures.

Question worth exploring next: **what if Stage 3 were not an LLM
call at all?** We have:
- 50 approved artists with 5 known: tracks each = 250 candidate
  tracks.
- A `taste_summary` with must_have + avoid + soft_preferences.
- A vector embedding of each candidate track (we don't compute it
  today, but cheap to add).

A non-LLM scoring function over the 250 candidates against the
taste_summary's traits could pick the top 30 deterministically.
No truncation, no hallucination, no refusal, no token cost.

This is a research question, not a fix. But it points at the
direction: **the LLM is the most expensive component in the
pipeline AND the most failure-prone. Every metric we automate
should also be asked of "could we do this without the LLM at all?"**

---

*Written 2026-05-23. Pair this with `analysis.md` (the diagnosis of
the immediate failures) and `next-steps.md` (the running ledger).*
