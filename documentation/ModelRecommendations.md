# Model Recommendations

> **Project priorities (in order):** **1. Quality → 2. Price → 3. Speed.**
>
> SpotyVibe's track-selection task is **constrained-pool instruction-following**, *not* multi-step reasoning. The model receives an explicit allow-list of artists, must-have/avoid traits, and a JSON schema, and must return picks that obey all three. **Models that follow instructions verbatim outperform models that "think harder."**

This document records measured model behaviour on the canonical evaluation scenario (modern theatrical pop-rock seed, `playlist_size=15`). Re-run with `python evaluation/run_evaluation.py`.

> **Orthogonal axis — verify mode:** how the harness confirms a GPT suggestion is real (`spotify` vs `l0_l1` vs `null`) is independent of model choice. See **[`VerifyModes.md`](VerifyModes.md)** for the measured comparison and the current recommendation (`spotify` is the production default; `l0_l1` is parked due to a −1.7 pp must-have-cite regression).

## TL;DR Recommendation

| Model | Verdict | When to pick it |
|---|---|---|
| `gpt-5.4-mini` | ✅ **Project default (best value)** | The default since 2026-04-29. 88.0% mean must-have-cite at $0.0288/playlist (~4× cheaper than `gpt-5.4`) and ~42 s wall-clock. Best price/quality ratio. |
| `gpt-5.4` | ✅ **Best quality** | Switch to this when cite-rate accuracy matters more than cost. 98.7% mean cite at pool=50 — the only model × pool combo with stable B1↔B2 determinism (Δ 0.0 pp) across the 5-block sweep. ~4× the cost of `gpt-5.4-mini`. |
| `gpt-4.1-mini` | ⚠️ Cheapest viable | $0.0125/playlist, 82.7% mean cite. Use only if cost is the single hard constraint — quality is noisy block-to-block (one block dropped to 40%). |
| `gpt-4.1` (full) | ❌ **Not recommended** | 60-73% mean cite across all pools — measurably *worse* than its own mini variant. Stop using. |
| `gpt-5.5` | ❌ **Not recommended** | Reasoning-tier model — wrong tool for this workload. See "Why not gpt-5.5" below. |
| Other reasoning-tier models (o-series) | ❌ Avoid for the same reason | — |

## Measured baseline — 5-block pool-size sweep (2026-04-29)

Source: `evaluation/results/sweep-merged-5blocks/report.md` (60 rows = 5 blocks × 3 pools × 4 models). All numbers are means over the 5 blocks at the recommended pool size (`RETRIEVE_CANDIDATES_SIZE=50`).

| Model | Pool | Mean cite % | Mean cost $ | Mean wall s | Stage 2 approved | B1↔B2 determinism |
|---|---:|---:|---:|---:|---|---|
| `gpt-5.4` | 50 | **98.7 %** | $0.1190 | 94.0 s | 48/50 | ✅ stable (Δ 0.0 pp) |
| `gpt-5.4-mini` | **50** | **88.0 %** | **$0.0288** | 41.8 s | 48/50 | 🔴 noisy (Δ 13.4 pp) |
| `gpt-4.1-mini` | 50 | 82.7 % | $0.0125 | 86.6 s | 48/50 | 🔴 noisy (Δ 26.6 pp) |
| `gpt-4.1` | 30 | 73.0 % | $0.0654 | 197.1 s\* | 30/30 | 🔴 noisy (Δ 21.7 pp) |

\* `gpt-4.1 @ pool=30` wall-time is inflated by a 1300-hit Spotify rate-limit cascade in block 2; other blocks ran in ~50 s. Cost numbers per cell are still trustworthy.

### Why `gpt-5.4-mini` is the project default

`gpt-5.4` is the highest-quality model and the *only* combination in the sweep with stable run-to-run determinism, but the 4× cost premium over `gpt-5.4-mini` does not justify itself for the average user. `gpt-5.4-mini` clears the 85 %-cite quality bar at one quarter of the price and three quarters of the latency. Users for whom cite-rate is critical (e.g., curators, content creators) should switch explicitly via `Settings → Model`.

### Caveats from the 5-block sweep

1. **Pool 30 carries operational risk:** all 4 × 1300-hit Spotify 429 cascades in the sweep happened on pool 30 (smaller pool → more candidate cycles → more Spotify calls per pick). Pool 50 is operationally safer.
2. **Metric noise floor is ≈13 pp** (≈2 of 15 tracks). Cite-% deltas ≤ 13 pp between configurations are noise.
3. **`gpt-5.4-mini`'s noisiness is real**: block-to-block cite varies 73 %–93 %. The 88.0 % mean is correct, but individual playlists may fluctuate. If consistent quality matters more than cost, switch to `gpt-5.4`.

### Historical baseline (run `20260428-062909`, pre-Phase-2 code, n=1)

Kept for trend reference. Superseded by the 5-block sweep above.

| Model | Cost | Wall | Tracks | Spotify-found | Must-have cite | Notes |
|---|---:|---:|---:|---:|---:|---|
| `gpt-5.4` | $0.0951 | 68.9 s | 15/15 | 100 % | 93.3 % | Top quality. |
| `gpt-5.4-mini` | $0.0278 | 29.7 s | 15/15 | 100 % | 86.7 % | Best $/quality ratio. |
| `gpt-5.5` | $0.0263 | – | – | – | – | **HTTP read-timeout on batch 1** — never finished. |


## Why not `gpt-5.5`?

GPT-5.5 is a **reasoning-tier model**: it spends thousands of hidden "thinking" tokens before answering (telemetry confirms — every Stage 3 call returns ~3 500–4 600 `reasoning_tokens`; gpt-5.4 returns zero). It also rejects the `temperature` parameter, which is the canonical signal of a reasoning-class model.

SpotyVibe's track-selection stage is **not** a reasoning task. The model receives an explicit allow-list and must obey it. Reasoning models, given thinking budget, **drift off the allow-list** and **invent track titles that don't exist on Spotify**.

Measured comparison (eval run `20260428-065552`, gpt-5.5 vs the same harness):

| Metric | gpt-5.4 (baseline) | gpt-5.5 |
|---|---:|---:|
| Stage-3 cost | $0.077 | **$0.736** (~9.5×) |
| Stage-3 wall time | 65 s | **614 s** (~9.5×) |
| Tracks delivered | 15 / 15 | **14 / 15** |
| Spotify-found | 100 % | **82 %** |
| Must-have cite | 93 % | **53 %** |
| Off-pool picks (late batches) | 0 / 6 | **5 / 6** |
| Behaviour on first-batch | finishes | sometimes **times out** |

The longer the model runs (batches 3-4), the **worse** its obedience: batch 4 spent 4 598 reasoning tokens and 258 s producing **one** usable track.

**Rule of thumb:** for SpotyVibe, **prefer non-reasoning models**. Reasoning capacity is a liability here, not a feature.

## How to switch model

Edit `Settings → Model` in the app, or set in `.credentials`:

```ini
[openai]
model = gpt-5.4-mini
```

Or via env var: `OPENAI_MODEL=gpt-5.4-mini`.

## How to add a new model to the recommendation matrix

1. Confirm the model is in `frontend/static/data/pricing.json` (input/output $ per 1M tokens).
2. Confirm it is in `config.py` → `OPENAI_SUPPORTED_MODELS_JSON`.
3. Add it to `evaluation/settings.ini` → `models = …`.
4. Add a per-cycle USD estimate to `evaluation/run_evaluation.py` → `_PER_CYCLE_USD`.
5. Run `python evaluation/run_evaluation.py --no-confirm`.
6. Update this file with the measured numbers.

## Local LLM compatibility

SpotyVibe supports local LLMs via OpenAI-compatible endpoints (Ollama, llama.cpp, vLLM, etc.). The codebase auto-downgrades cloud-only features (`json_schema` → `json_object`) on a per-model basis (see `_JSON_SCHEMA_UNSUPPORTED` in `core/src/openai_http.py`). When running a local model:

- Expect lower quality on average — local models in the 7-13B range typically score 30-50 percentage points lower on must-have cite vs. `gpt-5.4-mini`.
- Larger local models (70B+ class, e.g. Llama-3.3-70B-Instruct) approach `gpt-4.1-mini` quality but at much higher hardware cost.
- **Always** measure your local model against the eval harness before relying on it in production.

