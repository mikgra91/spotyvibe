# Model Performance Results — SpotyVibe

> **Single source of truth for model choice.** This file replaces the
> retired `evaluation/baselines/` directory and `HISTORY.md`. It records
> which models are recommended, which are removed, and the evidence
> behind each verdict. Update it after every evaluation that changes a
> verdict — see [How to update](#how-to-update) at the bottom.
>
> **Last updated:** 2026-05-20 · **Active corpus:** `2026-05-19` rebuild
> (175,578 artists, 83.4 % carrying baked-in `top_tracks`).

## North Star reminder

Model choice is judged in this strict priority order (from `CLAUDE.md`):

1. **Quality** — recommendation relevance, must-have-cite rate,
   Spotify-found rate, playlist completion, post-feedback leakage.
2. **Price** — cost per generated playlist.
3. **Speed** — wall-clock latency.

A model that wins price/speed but regresses quality on *any* supported
scenario does **not** ship. Quality always wins ties.

---

## 🏆 Best current model — `gpt-5.4-mini`

**`gpt-5.4-mini` is the best model for SpotyVibe** as of 2026-05-20,
confirmed at n=3 against `gemini-3.1-flash-lite` on the rebuilt corpus.
It wins the North Star's #1 priority (quality): an **80.6 % must-have
cite rate vs Gemini's 58.9 %**, with far tighter run-to-run variance.
Both models tie on completion (15/15 every run), Spotify-found (≈ 100 %),
and leakage (0). Gemini wins price and speed — but quality wins ties,
so `gpt-5.4-mini` is the default and `gemini-3.1-flash-lite` is the
documented cheap/fast alternative.

## TL;DR — current recommendations

| Role | Model | Status | Cost/run* | Evidence |
|---|---|---|---:|---|
| **Default (best quality)** | `openai/gpt-5.4-mini` | ✅ Recommended | ~$0.045 | n=3, 2026-05-20 |
| **Cheap / fast** | `google/gemini-3.1-flash-lite` | ✅ Recommended | ~$0.015 | n=3, 2026-05-20 |
| **Top cite-rate** | `anthropic/claude-haiku-4.5` | 🔬 Candidate — gated on A6 | ~$0.075 | n=3, 2026-05-20 |
| Quality escalation | `gpt-5.4` | ⚠️ Superseded by Haiku 4.5 | ~$0.11/playlist | n=3, pre-rebuild |
| Bulk/cheap | `deepseek/deepseek-v4-flash` | ❌ Removed from suggestions | — | See [removed](#removed--no-go-models) |
| Offline/private | Local LLMs (Llama/Mistral/Qwen 7-8B) | ⚠️ Opt-in only | $0 | Unfit for quality bar |

\* *Cost per harness **run** = one full cycle (2 playlists generated +
2 profile-train calls + analysis). Per-playlist is roughly half.*

**Per-provider defaults** (first entry = the default shown in the UI):

| Provider | Default model | Second choice |
|---|---|---|
| OpenAI | `gpt-5.4-mini` | `gpt-5.4` |
| OpenRouter | `openai/gpt-5.4-mini` | `google/gemini-3.1-flash-lite` |

`DEFAULT_OPENAI_MODEL` is `openai/gpt-5.4-mini` ([config.py](../config.py)).
Provider suggested-model lists live in
[frontend/static/js/modules/provider.js](../frontend/static/js/modules/provider.js).

---

## Recommended models

### `openai/gpt-5.4-mini` — default (best current model)

The quality winner. On the current corpus it produces complete,
well-grounded playlists with the most reliable must-have citation of
any cloud model measured.

**Evidence — 2026-05-20 cross-model run** (corpus `2026-05-19`,
verify mode `l0_l1`, 2 scenarios × **n=3**; means across all 6 runs):

| Metric | `default` (n=3) | `lastfm_tag_weighting` (n=3) | Overall |
|---|---:|---:|---:|
| Playlist A/B completion | 15/15 every run | 15/15 every run | 6/6 perfect |
| Spotify-found (l0_l1) | 100.0 % | 100.0 % | **100.0 %** |
| Must-have cite rate | 82.2 % (80.0-86.7) | 78.9 % (76.7-83.3) | **80.6 %** |
| Post-feedback leakage | 0 | 0 | **0** |
| Fit-check | pass | pass / n/a | pass |
| Cost / run | ~$0.041 | ~$0.049 | **~$0.045** |
| Wall / run | 33.2 s | 38.9 s | 36.0 s |

**Strengths.** Best must-have cite rate (80.6 %) and — critically —
the most *stable* one: every run landed inside a tight 76.7-86.7 %
band. Full 15/15 completion on all 6 runs, 100 % Spotify-found, zero
leakage.

**Weaknesses.** ~3× the cost and ~2.4× the wall-clock of
`gemini-3.1-flash-lite`. Two of six runs (iteration 3 of each
scenario) showed a Stage-3 latency/token spike (55-73 s wall, ~6.5 k
output tokens vs ~2.7 k typical) — occasional generation instability,
not a quality failure. Degrades under large profiles — see
[facet-scaling](#facet-scaling-context-rot).

**Confidence.** High. n=3 across two scenarios; completion, found-rate
and leakage are all at ceiling; the cite-rate lead over Gemini
(+21.7 pp) is far above run-to-run noise.

### `google/gemini-3.1-flash-lite` — cheap / fast alternative

A genuinely viable budget option: ~3× cheaper and ~2.4× faster than
`gpt-5.4-mini`, with no failure on completion, grounding, or leakage.
It is *not* the default only because its must-have citation is weaker
and more volatile — and the North Star ranks quality first.

**Evidence — 2026-05-20 cross-model run** (same corpus / verify mode /
n=3 as the `gpt-5.4-mini` table above):

| Metric | `default` (n=3) | `lastfm_tag_weighting` (n=3) | Overall |
|---|---:|---:|---:|
| Playlist A/B completion | 15/15 every run | 15/15 every run | 6/6 perfect |
| Spotify-found (l0_l1) | 98.0 % | 98.9 % | **98.5 %** |
| Must-have cite rate | 55.0 % (43.3-61.8) | 62.9 % (41.9-80.0) | **58.9 %** |
| Post-feedback leakage | 0 | 0 | **0** |
| Fit-check | pass | pass / n/a | pass |
| Cost / run | ~$0.017 | ~$0.014 | **~$0.015** |
| Wall / run | 15.7 s | 13.9 s | 14.8 s |

**Strengths.** Cheapest and fastest cloud model measured. Perfect
completion, near-perfect Spotify-found, zero leakage — the hard
quality gates all pass.

**Weaknesses.** Must-have cite rate is **21.7 pp below `gpt-5.4-mini`
(58.9 % vs 80.6 %)** and far more volatile — individual runs ranged
41.9 % to 80.0 % (a 38 pp spread vs mini's 10 pp). Low cite rate means
the rationale often does not explicitly ground a pick in a `Must:`
trait; the playlists still pass the deterministic gates, but the
project counts cite rate as a first-class quality metric.

**Confidence.** High that it is a sound *cheap* tier (n=3, all hard
gates pass). The cite-rate deficit is real and reproducible — do not
promote it to default unless a prompt change closes that gap without
regressing mini.

### `anthropic/claude-haiku-4.5` — top cite-rate (candidate, gated on A6)

The **highest must-have cite rate of any model measured** — 92.8 %
overall, 98.9 % on the `default` scenario — at a price that still
clears the single-digit-cent-per-playlist bar. One reliability caveat
keeps it out of the default slot: see weaknesses.

**Evidence — 2026-05-20 cross-model run** (corpus `2026-05-19`,
verify mode `l0_l1`, 2 scenarios × **n=3**):

| Metric | `default` (n=3) | `lastfm_tag_weighting` (n=3) | Overall |
|---|---:|---:|---:|
| Playlist A completion | 15/15 every run | 15/15 every run | 6/6 perfect |
| Playlist B completion | **2/3** (1 empty) | 3/3 | **5/6** |
| Spotify-found (l0_l1) | 100.0 % | 100.0 % | **100.0 %** |
| Must-have cite rate | 98.9 % (96.7-100) | 86.7 % (76.7-93.3) | **92.8 %** |
| Post-feedback leakage | 0 | 0 | **0** |
| Cost / run | ~$0.081 | ~$0.070 | **~$0.075** |
| Wall / run | 45.2 s | 36.1 s | 40.7 s |

**Strengths.** Best-in-class must-have citation (+12 pp over
`gpt-5.4-mini`, +34 pp over Gemini Flash Lite). 100 % Spotify-found,
zero leakage. ~$0.038/playlist — comfortably single-digit-cent.

**Weaknesses.** **One of six runs returned an empty playlist B**
(`default` iter 1). The trace shows the classic anti-confabulation /
pool-starvation pattern: after feedback prunes the candidate pool,
a high-discipline model returns empty Stage-3 batches rather than
invent tracks — the *same* signature `gpt-5.4` shows. This is an
upstream pipeline gap (**A6 — RAG re-retrieve on consecutive empty
batches**, still unshipped), not a model defect, but it is a real
product failure: the user sees an empty playlist. Also chattier than
mini (~4.5-7.7 k Stage-3 output tokens/run vs ~2.7 k) → ~1.7× the
cost and slightly slower.

**Confidence.** High on the cite-rate lead (n=3, far above noise).
The empty-B is 1/6 — reproducible enough to take seriously, not
frequent enough to call the model broken. **Verdict: do not displace
`gpt-5.4-mini` as default until A6 ships.** Once empty Stage-3 batches
trigger a pool re-retrieve, re-run this matrix — Haiku 4.5 is the
strongest default candidate on the table.

### `gpt-5.4` — quality escalation tier (superseded)

Formerly the `auto`-mode escalation target. **`claude-haiku-4.5` now
supersedes it**: Haiku posts a higher cite rate (92.8 % vs gpt-5.4's
~96 % pre-rebuild is comparable, but Haiku is measured on the *current*
corpus), costs less (~$0.038 vs ~$0.11 per playlist), and stays inside
the single-digit-cent budget gpt-5.4 breaches. No reason to spend eval
budget re-testing gpt-5.4 — see the note in
[Candidate models](#candidate-models--worth-evaluating).

**Pre-rebuild reference numbers** (n=3, *before* the corpus rebuild —
kept only as a historical quality ceiling): gpt-5.4 scored ~96 % cite
/ 68 % Spotify-found / 62 % playlist-B completion vs mini's 86 % / 40 %
/ 29 %. The corpus rebuild has since lifted *every* model's
found-rate to ≈100 %, which erased gpt-5.4's main advantage.

**Why it is no longer worth evaluating.** gpt-5.4 costs ~$0.11/playlist
— it breaches the single-digit-cent budget. It is also slower and
chattier (B-12 probe: 37 s vs mini's 18 s for the same battery). Its
one differentiator — disciplined anti-confabulation on thin pools — is
now matched by `claude-haiku-4.5` at a third of the cost. There is no
quality, price, or speed axis on which gpt-5.4 is the right pick for
this workload today.

---

## Removed / no-go models

### `deepseek/deepseek-v4-flash` — removed 2026-05-20

**Removed from the OpenRouter `suggested_models` list** (still usable
via free-text model entry).

**Why.** 60-80 % of its output tokens are *hidden reasoning tokens*.
This makes it 5-10× slower than alternatives at comparable quality and
inflates output-token cost. The B-12 probe (2026-05-19) measured it
directly: 95.9 s wall and 9,578 output tokens for 4 calls, versus
17.8 s / 2,250 tokens for `gpt-5.4-mini` on the identical battery.

**Quality was never the problem.** On the 2026-05-19 corpus-rebuild
baseline DeepSeek hit 96.8 % / 93.8 % Spotify-found and full 15/15
playlists — it works. It is removed purely on the **speed** and
**token-economy** axes (North Star priorities 2 and 3). A user who
explicitly wants it can still add it manually.

### Local LLMs (Llama 3.1 8B, Mistral 7B, Qwen 2.5 7B — Q4_K_M) — opt-in only

**Not fit for the default workload.** Measured 2026-05-14/15:

- **Meta-Llama-3.1-8B-Instruct Q4_K_M:** ~836 s (14 min) per playlist,
  3-10 verified tracks against a target of 30. Cannot reliably emit
  the nested-JSON-with-reasoning-wrapper schema; falls back to
  markdown prose that fails parsing.
- Mistral 7B / Qwen 2.5 7B Q4_K_M: same class of problem.

The codebase keeps a **minimal prompt variant**
(`prompts/track_select_system_local_minimal.txt`) and an 8 K-context
path so these models *run*, but they remain unfit for the quality bar.
Supported as an opt-in for fully-offline / private use only — never a
recommendation.

### `gpt-4.1` / `gpt-4.1-mini` — superseded

Tested 2026-05-08 as part of the early baseline matrix. Superseded by
the gpt-5.4 series on every axis; not removed from any list, simply
not recommended. No reason to evaluate them again.

---

## Candidate models — worth evaluating

OpenRouter exposes 300+ models. None is adopted without a harness run;
this is the shortlist worth the eval budget, with the rationale.

### For *better quality* than `gpt-5.4-mini`

| Candidate | Status | Finding |
|---|---|---|
| `anthropic/claude-haiku-4.5` | ✅ **Evaluated 2026-05-20, n=3** | Best cite rate measured (92.8 %); see its section above. Gated on A6 (1/6 empty playlist B). |
| `google/gemini-3.1-flash` | ❌ Not available | The full-Flash variant does **not** exist on OpenRouter — the 3.1 family ships only `gemini-3.1-flash-lite`. The closest sibling is `google/gemini-3-flash-preview` (prior-gen full Flash, $0.50/$3.00) — but OpenRouter labels it a *"thinking model"*, so it carries the same hidden-reasoning-overhead risk that got DeepSeek V4 Flash removed. Evaluate only with that caveat in mind. |
| `gpt-5.5` / `gemini-3.1-pro` / `claude-sonnet` | Not evaluated | Frontier tier — quality-ceiling test only; far too expensive for a default. Low priority. |

The cheap probe-battery first-pass is still the recommended workflow
for any *new* candidate: run `python -m evaluation.probes --model
<id> --battery compaction --confirm` (~$0.02-0.05) before committing
to a full 2-scenario n=3 harness run.

### For a *cheaper* tier

`gemini-3.1-flash-lite` is already the measured cheap option (~$0.015
/run, ~3× cheaper than mini). If an even cheaper OpenAI-native model is
wanted, the genuine budget tier is the **nano** class — `gpt-4.1-nano`
(~$0.10 / $0.40 per M) and `gpt-5.4-nano` (~$0.20 / $1.25 per M).
Both are unevaluated for this workload; nano-class models often
struggle with the nested-JSON reasoning schema, so they need a probe
run before any recommendation.

### ⚠️ The original GPT-4 is *not* a cheap option

A common assumption — "old model = cheap" — is wrong here. The
original **GPT-4** (released May 2023) is still callable on the OpenAI
API but is priced at **~$30 / M input, ~$60 / M output** — roughly
**40× the input cost and 13× the output cost of `gpt-5.4-mini`**
($0.75 / $4.50). It is also an 8 K-context model, far too small for
this pipeline's prompts. Old frontier models stay expensive; the cheap
tier is *modern small* models (mini / nano / flash-lite), not
yesterday's flagships. **Do not add GPT-4 as a "cheap" suggested
model** — it would be the most expensive and least capable option in
the list.

---

## Critical caveat — model verdicts are corpus-dependent

The single biggest lesson from the evaluation history: **model choice
cannot be separated from corpus quality.**

Before the 2026-05-19 corpus rebuild, `gpt-5.4-mini` had only ~40 %
Spotify-found rate and collapsed on post-feedback playlists. The root
cause was *not* the model — it was an empty `top_tracks` field on
every corpus row, so Stage 3 had nothing to ground on and (correctly)
refused to confabulate. The rebuilt corpus bakes 5 Spotify-resolvable
top tracks into 83.4 % of artist rows; the same model then jumped to
100 % found-rate.

**Implication.** Any model verdict in this file is valid only for the
corpus version named in the header. After a corpus rebuild, re-run the
2-scenario harness for the default model before trusting these
numbers. A model that looks bad may just be starved of grounding data.

---

## Facet-scaling / context-rot

The B-12 `facet_scaling` probe measures cite-rate as a profile grows
from 2 → 20 facets (must_have + avoid items), holding the candidate
pool and schema fixed. **All three cloud models degrade** — the
"lost in the middle" effect (Liu et al. 2024 TACL; Chroma 2025
"context rot").

Cite-rate of the load-bearing first must_have:

| Model | facets_2 | facets_6 | facets_12 | facets_20 |
|---|---:|---:|---:|---:|
| gpt-5.4-mini | 1.00 | 0.50 | 0.20 | 0.25 |
| gpt-5.4 | 1.00 | 0.00 | 0.50 | 0.25 |
| deepseek-v4-flash | 1.00 | 0.33 | 0.25 | 0.25 |

(2026-05-19 run, n=1. A 2026-05-20 follow-up added a
`facets_20_focused` variant testing `build_focused_taste_summary`;
the focused compactor reduced token count but did **not** recover
cite-rate — the degradation begins at ≥ 6 facets regardless. Open
problem (the P-compact / taste-summary compaction work).)

**Takeaway for model choice.** No model is immune to large-profile
degradation. This is a *pipeline* problem (taste-summary compaction),
not a model-selection problem — do not pick a model hoping to dodge it.

---

## How the harness measures models

For anyone re-running these evaluations:

- **`evaluation/run_evaluation.py`** — the end-to-end harness. Runs the
  full pipeline (profile train → Stage 1 retrieve → Stage 2 avoid →
  Stage 3 select → verify) per scenario per model per iteration.
- **Scenarios** (`evaluation/scenario.py`) — `default`,
  `lastfm_tag_weighting`, `niche_only_strict`,
  `post_feedback_tag_regression`, `starved_pool_a6`, plus a
  large-profile stress scenario.
- **Verify modes** — `spotify` (live, ground truth, rate-limited),
  `l0_l1` (Overlay → MusicBrainz → Last.fm, no Spotify quota),
  `overlay`, `null`. `l0_l1` is the standard cheap mode.
- **B-probes** (`evaluation/probes/`) — synthetic single-call probes
  that fingerprint model behaviour (constraint-following,
  confabulation, omission, cite fidelity, empty-pool recovery,
  facet-scaling) for ~$0.01-0.05 instead of a multi-dollar full eval.
- **Iteration count** — model run-to-run variance is high; a 5 pp A/B
  delta needs n≥5 on mini, n≥3 on gpt-5.4 to clear noise. Single-iter
  runs confirm *direction*, not absolute thresholds.

---

## Change log

| Date | Change | Models affected |
|---|---|---|
| 2026-05-20 | **n=3 run of `claude-haiku-4.5`.** Best cite rate measured (92.8 %), single-digit-cent (~$0.038/playlist) — but 1/6 empty playlist B. Added as a candidate gated on A6; supersedes `gpt-5.4` as the quality/escalation pick. `google/gemini-3.1-flash` found not to exist on OpenRouter. | claude-haiku-4.5, gpt-5.4 |
| 2026-05-20 | **n=3 cross-model run (`gpt-5.4-mini` vs `gemini-3.1-flash-lite`).** gpt-5.4-mini confirmed best (cite 80.6 % vs 58.9 %); Gemini promoted from pending → recommended cheap/fast tier. Both 100 %/15-of-15 on the hard gates. | gpt-5.4-mini, gemini |
| 2026-05-20 | DeepSeek V4 Flash removed from suggested models (reasoning-token overhead). Default → `gpt-5.4-mini`. Gemini 3.1 Flash Lite added as suggested. | deepseek-v4-flash, gpt-5.4-mini, gemini |
| 2026-05-20 | Cross-model confirmation run — `gpt-5.4-mini` lands 100 % found on the rebuilt corpus. A4 closed. | gpt-5.4-mini |
| 2026-05-19 | Corpus rebuild (83.4 % `top_tracks` coverage). DeepSeek V4 Flash baseline: 96.8 %/93.8 % found. B-12 facet-scaling probe added. | all |
| (pre-2026-05-19) | Detailed per-fix history retired with `HISTORY.md`. Pre-rebuild numbers are a quality floor only — corpus was the bottleneck. | — |

## How to update

After any evaluation that changes a verdict:

1. Update the [TL;DR table](#tldr--current-recommendations) if a model
   moved between roles.
2. Add/replace the model's section under
   [Recommended](#recommended-models) or
   [Removed](#removed--no-go-models) with the new evidence table.
3. Add a row to the [change log](#change-log).
4. Update the header `Last updated` date and `Active corpus` if it
   changed.
5. Keep evidence tables terse — headline metrics only. Raw per-run
   JSON does not belong in this file.
