# Model Recommendations

> **Project priorities (in order):** **1. Quality → 2. Price → 3. Speed.**
>
> SpotyVibe's track-selection task is **constrained-pool instruction-following**, *not* multi-step reasoning. The model receives an explicit allow-list of artists, must-have/avoid traits, and a JSON schema, and must return picks that obey all three. **Models that follow instructions verbatim outperform models that "think harder."**

This document records measured model behaviour on the canonical evaluation scenario (modern theatrical pop-rock seed, `playlist_size=15`). Re-run with `python evaluation/run_evaluation.py`.

## TL;DR Recommendation

| Model | Verdict | When to pick it |
|---|---|---|
| `gpt-5.4` | ✅ **Best quality** | Default for users who care most about cite rate / Spotify-found accuracy. |
| `gpt-5.4-mini` | ✅ **Best value** | Default for cost/speed-sensitive users. ~3-4× cheaper than 5.4 with only modest quality drop. |
| `gpt-4.1` | ⚠️ Acceptable fallback | Use if `gpt-5.4` quota is unavailable. Older but follows instructions reliably. |
| `gpt-4.1-mini` | ⚠️ Acceptable fallback | Use if `gpt-5.4-mini` quota is unavailable. Cheap and fast. |
| `gpt-5.5` | ❌ **Not recommended** | Reasoning-tier model — wrong tool for this workload. See "Why not gpt-5.5" below. |
| Other reasoning-tier models (o-series) | ❌ Avoid for the same reason | — |

## Measured baseline (run `20260428-062909`, pre-Phase-2 code)

| Model | Cost | Wall | Tracks | Spotify-found | Must-have cite | Notes |
|---|---:|---:|---:|---:|---:|---|
| `gpt-5.4` | $0.0951 | 68.9 s | 15/15 | 100 % | **93.3 %** | Top quality. |
| `gpt-5.4-mini` | $0.0278 | 29.7 s | 15/15 | 100 % | **86.7 %** | Best $/quality ratio. |
| `gpt-5.5` | $0.0263 | – | – | – | – | **HTTP read-timeout on batch 1** — never finished. |

> The 4.1 row will be added once the next eval run completes (Spotify rate-limit cooldown in progress at time of writing). Update this file with the measured numbers — do not leave it blank.

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

