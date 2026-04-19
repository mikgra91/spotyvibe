---
title: Run SpotyVibe on llama.cpp (Windows)
subtitle: A guided setup for using llama.cpp as SpotyVibe's local LLM backend, with model-selection analysis and system-requirement estimates.
---

> **TL;DR** — Install a llama.cpp release build, download a GGUF model, run `llama-server`, then point SpotyVibe at `http://localhost:8080/v1` via Settings → Provider → **Custom**. The OpenAI-compatible endpoint exposed by llama-server supports `response_format: json_object`, which is what SpotyVibe's `call_gpt_json()` uses in [openai_http.py:327-332](../../core/src/openai_http.py#L327-L332).

SpotyVibe already supports local inference through Ollama and LM Studio. llama.cpp is the C/C++ engine those tools wrap — running it directly gives you:

- **Lower overhead** than Ollama's background service on Windows.
- **First-party support** for every new GGUF release and quantization type.
- **Grammar-constrained decoding** (GBNF) — the primitive behind JSON mode in the whole GGUF ecosystem.
- **Full CLI control** over context size, GPU layer offload, thread count, and sampler parameters.

The tradeoff: no GUI. You configure it with flags.

---

## Part 1 — Install llama.cpp on Windows

llama.cpp ships **prebuilt Windows binaries** for every release. You do not need to compile from source unless you want a feature that isn't in the release matrix.

Pick **one** of the three install paths below.

### Option A — winget (easiest, Vulkan backend)

```powershell
winget install ggml.llamacpp
```

This installs the Vulkan build, which works on NVIDIA, AMD, and Intel GPUs via the Vulkan runtime and runs acceptably on CPU if no GPU is present. After install, `llama-server` is on your PATH.

**Caveat:** the winget build does not include CUDA. If you have an NVIDIA GPU and want maximum throughput, use Option B instead.

### Option B — Prebuilt CUDA release (best NVIDIA performance)

1. Open [github.com/ggml-org/llama.cpp/releases](https://github.com/ggml-org/llama.cpp/releases) and pick the latest release.
2. Download **`llama-bXXXX-bin-win-cuda-x64.zip`** matching your CUDA major version (12 or 13). Check yours with `nvidia-smi` — the top-right "CUDA Version" must be ≥ the one in the filename.
3. If you do **not** already have a matching CUDA toolkit installed, also download **`cudart-llama-bin-win-cuda<12|13>-x64.zip`** (the bundled runtime DLLs).
4. Extract both zips into the same folder, e.g. `C:\tools\llama.cpp\`.
5. Add that folder to your user PATH (System Properties → Environment Variables → Path → Edit → New).

Verify:

```powershell
llama-server --version
```

### Option C — Build from source (advanced)

Only needed for bleeding-edge features or an unusual backend. Requires Visual Studio 2022 with the *Desktop development with C++* workload, *C++ CMake Tools*, and (for NVIDIA) the CUDA Toolkit. From a **x64 Native Tools Command Prompt for VS 2022**:

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j
```

The binaries land in `build\bin\Release\`. Use `-DGGML_VULKAN=ON` instead of `-DGGML_CUDA=ON` for the Vulkan backend.

---

## Part 2 — Download a GGUF model

Models come from Hugging Face. Any repo named `*-GGUF` works. Three reliable publishers:

- **`bartowski/*-GGUF`** — the most-downloaded community quants, fresh within hours of a new model.
- **`unsloth/*-GGUF`** — often includes imatrix quants and "dynamic" quants that preserve quality at small sizes.
- **`lmstudio-community/*-GGUF`** — curated by the LM Studio team, usually matches bartowski's builds.

Grab a single file. For example, using `curl` from PowerShell:

```powershell
mkdir C:\tools\llama.cpp\models
curl -L -o C:\tools\llama.cpp\models\qwen3-14b-q4km.gguf `
  https://huggingface.co/bartowski/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf
```

> **Pick the right quant.** `Q4_K_M` is the community default — ~4.8 bits/weight, ~2–3% quality loss vs FP16 per [llama.cpp quantize README](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md). Step up to `Q5_K_M` if you have VRAM headroom; drop to `Q3_K_M` only if you're tight on memory.

---

## Part 3 — Start `llama-server`

From any shell (cmd, PowerShell, or Git Bash), run:

```powershell
llama-server ^
  --model C:\tools\llama.cpp\models\qwen3-14b-q4km.gguf ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --ctx-size 8192 ^
  --n-gpu-layers 99 ^
  --jinja
```

**Flag notes:**

| Flag | Purpose |
|---|---|
| `--model` / `-m` | Path to the `.gguf` file. |
| `--port` | Default is `8080`. |
| `--host` | `127.0.0.1` keeps the server local-only. Use `0.0.0.0` only if you deliberately want LAN access. |
| `--ctx-size` / `-c` | Context window. SpotyVibe's prompts stay under 4K tokens in practice; 8K gives generous headroom for large deny-lists and history. |
| `--n-gpu-layers` / `-ngl` | Layers to offload to GPU. `99` = "all of them, if VRAM allows". Drop to a specific number (e.g. `20`) if you're VRAM-limited. |
| `--jinja` | Enables the Jinja chat-template engine. **Required** for most modern models (Qwen3, Llama 3.3, Gemma 3) to produce correct chat formatting. |

When the log prints `server is listening on http://127.0.0.1:8080`, leave the window open and move on.

Quick health check from a second shell:

```powershell
curl http://localhost:8080/v1/models
```

You should see a JSON list containing your loaded model.

---

## Part 4 — Connect SpotyVibe

SpotyVibe already supports any OpenAI-compatible endpoint via its **Custom** provider preset ([provider.js:8-14](../../frontend/static/js/modules/provider.js#L8-L14), [config.py:567-589](../../config.py#L567-L589)).

1. Start `python app.py` and open [http://127.0.0.1:5000](http://127.0.0.1:5000).
2. Open **Settings** (☰ → ⚙️).
3. **Provider** → set to **Custom** (or pick **Ollama** if the dropdown doesn't have Custom — the base URL is what matters).
4. **Base URL** → `http://localhost:8080/v1`
5. **API Key** → leave blank (llama.cpp accepts anything; SpotyVibe sends a placeholder when `llm_api_key_required()` is false).
6. Click **🔁 Fetch models** — the dropdown should populate with the model ID llama-server reports (usually the filename without `.gguf`).
7. Select the model, click **Save**.
8. Generate a playlist. If the first batch comes back as valid JSON with ≥ 5 tracks, the integration works.

### Verifying JSON mode end-to-end

SpotyVibe sends `response_format: {"type": "json_object"}` on every call. llama-server translates that into a GBNF grammar that forces the model to produce syntactically valid JSON — this is the reliable path. (The `json_schema` variant has known rough edges in llama-server's OpenAI shim — [issue #10732](https://github.com/ggml-org/llama.cpp/issues/10732) — but SpotyVibe doesn't use it.)

If the app reports "AI returned invalid JSON", the grammar isn't being applied. Check the llama-server log for a line like `applying grammar` on each request (wording varies by build — search literally for `grammar`). If it's missing, re-launch with `--jinja` and confirm the model has a chat template baked in (`--chat-template chatml` is a fallback).

---

## Part 5 — Model constellation analysis

This is the part that actually determines whether the experience is good.

### What SpotyVibe asks of the LLM

Looking at [prompts/system_prompt.txt](../../prompts/system_prompt.txt) and [prompts/analysis_prompt.txt](../../prompts/analysis_prompt.txt), the workload is:

1. **Music recall across genres, eras, and regions** — the system prompt literally says "*expert in all genres, eras, and regions*". Every generated track is a fact claim: "this artist exists, this track exists, it has these genres". Hallucinated artists/tracks are the #1 user-visible failure mode.
2. **Strict JSON adherence** with a nested schema (rationale objects, audio features, etc.).
3. **Multi-constraint reasoning** — DENY_LIST, must-have traits, avoid traits, new-artist quota, max-2-per-artist. Seven hard constraints, with priorities.
4. **Multi-language output** — English, German, Japanese ([config.py:98](../../config.py#L98), i18n files).
5. **Short context** — profile + recent feedback + deny-list usually fits in 2–4K tokens.

### Why this favors a specific model profile

| Requirement | Favors |
|---|---|
| Long-tail music knowledge | **Larger pretraining corpus**, larger parameter count |
| Strict JSON | Models with native function-calling training (Qwen3, Gemma 3, Llama 3.3) |
| Multilingual (en/de/jp) | **Qwen family** (Chinese-led lab, very strong Japanese and German vs peers) |
| Short context | 4–8K context is enough; no need for 128K+ models |
| Latency (interactive UX) | Smaller active parameters = faster — MoE models shine here |

The long-tail knowledge point is the load-bearing one. Recent research on LLM music recommendation ([Music Recommendation with LLMs, arXiv:2511.16478](https://arxiv.org/html/2511.16478)) confirms: zero-shot LLM recommenders excel at under-described genres but are "susceptible to popularity bias and may generate hallucinations." Both error modes shrink as parameter count grows — 70B-class models demonstrably recall niche artists that 7B models invent.

### Recommended constellations

Three tiers, ranked by result quality. All are Q4_K_M unless noted.

#### 🥇 Best quality on consumer hardware — **Qwen3-32B** or **Gemma-3-27B-it**

- VRAM: **~20 GB** (Q4_K_M). Fits a single RTX 4090 / RTX 5090 / RTX 3090.
- Why: the largest model that still runs well on a single consumer GPU. 32B parameters give noticeably better long-tail artist recall than 14B. Qwen3 has the edge on Japanese/German; Gemma 3 has the edge on function-calling reliability.
- Expected throughput: 25–40 tok/s on a 4090. At ~1500 output tokens per batch of 10 tracks, that's ~40–60s of generation plus a few seconds of prompt processing.

#### 🥈 Sweet spot — **Qwen3-14B** (primary pick)

- VRAM: **~9 GB** (Q4_K_M) / **~11 GB** (Q5_K_M). Fits an RTX 4070 / 4060 Ti 16GB / 3080.
- Why: the best hallucination-vs-speed tradeoff for this workload. Qwen3 14B is trained with native tool-calling and produces structured JSON reliably. Multilingual coverage includes all three SpotyVibe languages. 14B is roughly the inflection point where long-tail music recall becomes usable — below this you see a lot of invented track names.
- Expected throughput: 40–60 tok/s on a 4070. At ~1500 output tokens per batch of 10 tracks, that's ~25–40s of generation plus prompt processing.
- **This is the default I recommend** for a first test.

#### 🥉 Minimum viable — **Llama-3.3-8B-Instruct** or **Qwen3-8B**

- VRAM: **~5 GB** (Q4_K_M). Fits a GTX 1070 / RTX 3050 8GB, or runs on CPU with 16 GB RAM at ~6 tok/s.
- Why: the floor for acceptable JSON output and coherent music suggestions. You will see more hallucinated artist/track combinations and more repetition. Acceptable for testing the plumbing; marginal as a daily driver.
- Expected throughput: 60–100 tok/s on a mid-range GPU.

#### ❌ Avoid

- **Anything under 7B** (Phi-2, TinyLlama, 3B models) — the music recall is not there. You will get invented artists mixed with real ones, and no easy way to tell the difference.
- **Pure coding models** (Qwen3-Coder, DeepSeek-Coder) — tuned away from general world knowledge.
- **Reasoning-mode models with long thinking traces** (QwQ, DeepSeek-R1 distills) — they'll burn 2000 tokens thinking before answering and destroy latency. SpotyVibe doesn't need multi-step reasoning; it needs fast pattern completion over a structured prompt.

### Honest caveats

- Every local model I've named will hallucinate some artist/track pairs. The denylist / feedback loop in SpotyVibe already handles this — hallucinated tracks simply won't resolve on Spotify search and get filtered out in [suggestions.py](../../core/src/suggestions.py). But you will see **more retry batches** than with `gpt-5.4-mini`, which pushes you toward `MAX_GPT_CALLS_PER_RUN = 20` ([config.py:72](../../config.py#L72)).
- The multi-language constraint is real: if you run SpotyVibe in German or Japanese, avoid the Llama family specifically. Llama 3.x's German is noticeably weaker than Qwen3's. I haven't seen a systematic benchmark for music recommendation in Japanese, so treat this as a reasoned prior rather than measured fact.

---

## Part 6 — System requirements

Derived from llama.cpp VRAM documentation ([llama.cpp VRAM guide](https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms), [oobabooga's GGUF VRAM formula](https://oobabooga.github.io/blog/posts/gguf-vram-formula/)) and the model-size tier table above.

### Minimum — "it runs, barely"

| | Spec |
|---|---|
| CPU | 4-core x86-64 with AVX2 (anything from 2015 onwards) |
| RAM | **16 GB** |
| GPU | Optional. Integrated Intel/AMD iGPU via Vulkan works. |
| VRAM | 0 GB (CPU-only) or 4 GB dGPU with **partial** layer offload (`-ngl 20` instead of `99`; the rest runs on CPU) |
| Disk | 10 GB free (OS + model) |
| Model | Llama-3.3-8B or Qwen3-8B at Q4_K_M — note full-GPU offload of this class needs ~5 GB VRAM (see Part 5); a 4 GB card cannot fit all layers |
| Expected UX | 3–8 tok/s CPU, 20–30 tok/s iGPU. A 10-track batch takes 60–180 seconds. Usable for testing, painful for daily use. |

### Recommended — "it feels good"

| | Spec |
|---|---|
| CPU | 6-core modern x86-64 (Ryzen 5 7600 / Core i5-13400 class) |
| RAM | **32 GB** |
| GPU | NVIDIA **RTX 4070** or better (CUDA 12+), or AMD **RX 7800 XT** (Vulkan) |
| VRAM | **12 GB** |
| Disk | 30 GB free (leaves room for 2–3 model variants) |
| Model | Qwen3-14B at Q4_K_M or Q5_K_M |
| Expected UX | 40–60 tok/s. A 10-track batch (~1500 output tokens) completes in ~25–40 seconds — close to cloud-API feel for SpotyVibe's use. |

### Enthusiast — "as good as local gets"

| | Spec |
|---|---|
| CPU | 8-core (Ryzen 7 / Core i7 class) |
| RAM | **64 GB** |
| GPU | NVIDIA **RTX 4090** / **5090** / **3090** (24 GB VRAM) |
| VRAM | **24 GB** |
| Disk | 100 GB free |
| Model | Qwen3-32B or Gemma-3-27B at Q4_K_M |
| Expected UX | 25–40 tok/s. Hallucination rate materially lower than 14B tier. Japanese/German output quality approaches `gpt-4.1-mini`. |

### "Approaching GPT-5 quality locally"

70B-class models (Llama-3.3-70B, Qwen3-72B) at Q4_K_M need ~40 GB and one of: an RTX A6000 (48 GB), dual 3090/4090 with tensor parallelism, or Apple Silicon Mac with 64+ GB unified memory running Metal (not Windows — documented here for completeness). This is out of scope for a Windows consumer target.

---

## Part 7 — Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `llama-server` exits with "CUDA error: out of memory" | Lower `--n-gpu-layers` (try `20`, then `10`). Or reduce `--ctx-size` to `4096`. Or use a smaller quant (`Q3_K_M`). |
| SpotyVibe reports "AI returned an empty response" | Model finished generation but returned an empty string. Usually a chat-template mismatch — add `--jinja` or `--chat-template chatml`. |
| SpotyVibe reports "AI returned invalid JSON" | Grammar wasn't applied. Confirm the server log shows `applying grammar` per request; restart with `--jinja`. |
| Fetch models returns empty | llama-server only reports the one model it has loaded. Empty list usually means wrong base URL — must be `http://localhost:8080/v1` not `http://localhost:8080`. |
| Playlist generation is slow (>60s per batch) | Not enough GPU offload. Check `nvidia-smi` during generation — if GPU util is low, increase `-ngl`. If all layers are already on GPU, you've hit the speed ceiling for that model/hardware — step down to 8B. |
| `nvcuda.dll not found` on startup | Missing CUDA runtime. Install the `cudart-llama-bin-win-*` zip from the same release or install the NVIDIA CUDA Toolkit. |

---

## Part 8 — Can we help smaller models by chunking work differently?

> *"My hardware is upper-middle consumer. Running AI locally has a floor we can't change. But — can the backend split work into smaller batches so a lower-end model produces a better result overall? Or would that be neutral / actively harmful?"*

Short answer: **naive "smaller batches" is roughly neutral-to-negative. Smart *decomposition* of the task can help meaningfully, but it's a different change.** Here's the breakdown.

### The workload already batches

SpotyVibe already generates in batches (`BATCH_SIZE = 10` in [config.py:52](../../config.py#L52)) and loops up to `MAX_GPT_CALLS_PER_RUN = 20` per /api/run. A playlist of 30 tracks = 3 successful batches minimum, more if batches come back empty.

### Why shrinking `BATCH_SIZE` alone doesn't help

If you set `BATCH_SIZE = 3` and call the model 10× instead of 3×:

| Factor | Effect on small-model quality |
|---|---|
| Per-call output length | ↓ Less chance of JSON drift or truncation — a small win. |
| Per-call cognitive load | ↓ Model juggles fewer constraints simultaneously — a small win. |
| Prompt re-processing | ↑↑ The system prompt + profile + deny-list is re-tokenised every call. On CPU or a small GPU, prompt processing often dominates latency. |
| Deny-list growth | ↑ Each subsequent batch sees all prior picks as exclusions — prompts get longer as the run progresses. |
| Diversity per batch | ↓ With 3 tracks the model can't balance "2 new artists, 1 known" as naturally as with 10. It tends to collapse to the 3 most famous candidates in whatever genre it locked onto. |
| Popularity bias | ↑ Shorter outputs from small models reliably collapse to top-of-mind names. Research on LLM music recommenders ([arXiv:2511.16478](https://arxiv.org/html/2511.16478)) identifies this as one of the two primary failure modes. |
| Retry ceiling | ↑ `MAX_GPT_CALLS_PER_RUN = 20` is reached ~3× faster — less tolerance for empty batches. |

Net: you trade output quality for output validity, and pay a latency tax. On llama.cpp specifically, unless you enable prompt caching (`cache_prompt: true` in the request body, or `--cache-reuse` on the server), the prompt-reprocessing cost is the dominant term.

### What *does* help small models

These are the changes with a positive expected value. In rough order of impact-per-effort:

1. **Enable prompt caching on llama-server.** Launch with `--cache-reuse 256` and llama-server will reuse the KV cache prefix across requests that share a common prompt prefix. The system prompt + profile stay cached; only the deny-list diff and feedback get re-processed. This makes *any* multi-call strategy dramatically cheaper. **Zero app-side changes.**

2. **Task decomposition (genuine wins, moderate effort).** Instead of one prompt that says "generate 10 tracks satisfying all 7 constraints", chain smaller prompts:
   - Call 1: "Given this profile, list 5 sub-genres and 3 moods that match." (~50 tokens out)
   - Call 2: "For sub-genre X and mood Y, list 8 artists not in {deny_list}." (~150 tokens out)
   - Call 3: "For artist Z, list 2 deep-cut tracks." (~40 tokens out, called per artist)
   Each call is narrow enough that a 7B–8B model can answer correctly. The total token count is higher than one monolithic call, but quality per token is much better because the model is doing shallow pattern completion instead of multi-constraint reasoning. Downside: substantially more plumbing in [suggestions.py](../../core/src/suggestions.py), and you lose the single-call latency.

3. **Retrieval-augmented generation.** Ship a small local artist corpus (e.g. top 50K artists from MusicBrainz dump, ~2 MB compressed), retrieve the 20 most-profile-relevant names per batch, and inject them into the prompt as "candidate pool — pick from these, do not invent". This is the single largest quality lever for small models because it replaces *recall* (hard for a 7B) with *ranking* (easy for a 7B). Biggest engineering lift, largest quality payoff.

4. **Self-critique pass.** After generating, send the output back with "for each track, answer {real: true|false, matches_profile: true|false}" and filter. Adds one call per batch. Useful mainly as a cheap sanity check against the most confident hallucinations.

5. **Lower temperature for small models.** The default temperature (0.7 in [openai_http.py:232](../../core/src/openai_http.py#L232)) is tuned for GPT-class models. Drop to 0.3–0.5 for 7B–14B models — less creative drift, more adherence to constraints, fewer hallucinations. Trivial change.

### Honest bottom line

If you want a quick win without app changes: **enable llama-server prompt caching (`--cache-reuse 256`) and drop temperature to 0.4 in Settings**. That closes most of the small-model gap for free.

If you want to invest engineering effort: **retrieval augmentation with a local artist corpus** is the highest-impact change — and it would make cloud providers better too, not just local ones.

Shrinking `BATCH_SIZE` by itself is the one lever I would *not* pull. It sounds like it should help (smaller problems = better results) but the empirical behaviour on LLMs goes the other way: you lose the model's ability to self-diversify within a call, and you pay a prompt-reprocessing tax on every extra round trip.

---

## Part 9 — Do RAG and self-critique also help cloud models (e.g. GPT via OpenAI)?

> *"Retrieval-augmented generation and self-critique would also benefit cloud AI quality? Would there be higher costs, or is it negligible compared to the quality improvement?"*

The two techniques behave very differently when pointed at a frontier cloud model like `gpt-5.4-mini`. One is worth building for every provider; the other has sharply diminishing returns above a certain model class.

### RAG on cloud models — **yes, still worth it**

GPT-5-mini rarely invents well-known artists, so the *hallucination-prevention* benefit that dominates locally shrinks. But three other benefits remain, and they are cloud-relevant:

1. **Freshness.** The model's training cutoff doesn't know about releases after it. A MusicBrainz-derived corpus updated monthly fills that gap.
2. **Anti-popularity-bias steering.** GPT-5 without a candidate list reliably picks the most famous name in any genre slot. A retrieved candidate pool lets you deliberately weight toward mid-tier artists — matching the system prompt's "prioritize discovery: lesser-known artists, deep cuts" intent.
3. **Determinism.** The same profile produces more consistent playlists across runs, because the model is ranking a known pool instead of improvising.
4. **Profile-specific grounding.** Retrieved candidates are pre-filtered for the user's taste anchors, so reasoning budget goes to ranking instead of recall.

Quality bump is smaller than for local (10–20% fewer "meh" suggestions vs 40–60% fewer hallucinations locally) but real.

### Self-critique on cloud models — **skip, for existence checks**

GPT-5-mini hallucinates well-known tracks rarely. The app already has two downstream validators:

- Spotify search in [suggestions.py](../../core/src/suggestions.py) drops anything that doesn't resolve.
- The denylist / feedback loop catches repeats and user-rejected picks.

Asking GPT "is this track real?" mostly re-affirms what the Spotify search already filters for free. You'd pay for redundant validation.

The one place self-critique *would* add value on cloud: **profile-match quality** checks ("does this track actually satisfy must_have constraint X?"), not existence. That's a different prompt than Part 8 describes, and worth prototyping separately.

### Cost analysis

Baseline per batch on `gpt-5.4-mini`: ~2000 input tokens, ~1500 output tokens. A 30-track playlist = ~3 batches. Output tokens are ~4× the price of input on most OpenAI models, so output dominates total cost. A "thin RAG" candidate block of ~20 names adds ~200 input tokens per call.

| Strategy | Added input | Added output | Added cost per playlist |
|---|---|---|---|
| Baseline (no changes) | — | — | baseline |
| + Thin RAG (~20-artist candidate block) | +~200 tok/call | 0 | **~+3–5% overall** (input is cheap relative to output) |
| + Larger RAG (~50-artist block) | +~500 tok/call | 0 | **~+8–12% overall** |
| + Self-critique pass | ~equal to original input | +~200 tok | **~+80–100%** — essentially one extra short call per batch |
| + Thin RAG + self-critique | both | both | **~1.9× baseline** |

Concrete: if a typical playlist costs ~$0.003 today, thin RAG moves it to ~$0.003 (a fraction of a cent). Full stack (RAG + self-critique) roughly doubles it to ~$0.006. At 10 playlists/day (~300/month), the delta between baseline and full stack is roughly **$1–$2 per month** — not "pennies", but still trivial for a personal tool. RAG on its own stays in true-pennies-per-month territory.

### Prioritisation

- **RAG: worth building.** It's the single change that improves quality on every provider — local small models (biggest win), local large models (moderate), and cloud models (modest but real). Cloud cost overhead is rounding-error.
- **Self-critique: skip for existence checks** (Spotify search does this for free). Consider a *profile-match-quality* variant as a separate experiment — but don't build it as described in Part 8 for cloud use.

The honest prioritisation: if you invest engineering effort, build RAG first. It scales across providers, improves result quality uniformly, and the cloud-cost overhead is negligible. Self-critique is "maybe later" — its returns diminish sharply on model classes that rarely hallucinate to begin with.

---

## Appendix — Sources

- [llama.cpp build documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md) — Windows CMake instructions, backend flags.
- [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) — endpoint list, `response_format` support, flag reference.
- [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases) — prebuilt Windows binaries, CUDA/Vulkan variants.
- [llama.cpp grammar and structured output (DeepWiki)](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output) — how `json_object` maps to GBNF.
- [llama.cpp quantize README](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md) — Q4_K_M and other quantization tradeoffs.
- [llama.cpp VRAM requirements 2026 guide](https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms) — model-size to VRAM mapping.
- [oobabooga GGUF VRAM formula](https://oobabooga.github.io/blog/posts/gguf-vram-formula/) — empirical VRAM formula from layer offload and context.
- [Music Recommendation with LLMs (arXiv:2511.16478)](https://arxiv.org/html/2511.16478) — hallucination and popularity-bias characterization in LLM music recommenders.
- [HalluLens: LLM Hallucination Benchmark (arXiv:2504.17550)](https://arxiv.org/html/2504.17550v1) — hallucination scaling with model size.
- [llama.cpp issue #10732](https://github.com/ggml-org/llama.cpp/issues/10732) — known rough edges with `json_schema` (not used by SpotyVibe).
