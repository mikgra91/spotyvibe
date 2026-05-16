# Next Steps — 2026-05-04 (last refresh 2026-05-15)

Consolidated forward plan. Open tasks, decisions, and gated research items.

---

## 🟢 RESOLVED 2026-05-15 — RAG corpus was missing top_tracks (root cause of verify=spotify under-fill)

**The under-fill regression flagged on 2026-05-14 was NOT a DeepSeek bug, NOT a Llama bug, NOT a model-comparison problem.** It was a missing-anchor in the RAG corpus.

### Diagnosis chain

1. DS trace inspection showed Stage 3 returning valid JSON saying *"All approved artists lack known: tracks, so I omitted all of them. No real released tracks can be confidently recalled for any of these artists."* — three batches in a row. Source: `evaluation/results/20260514-154934/deepseek_deepseek-v4-flash-iter2/trace_A.json`.
2. Corpus sampling confirmed: zero of 2000 sampled artists have a `top_tracks` field. Boot log shows `RagCorpus loaded: 174200 artists, 0 enriched (0.0%), 0 with top_tracks (0 from overlay)`.
3. `verify_mode=l0_l1` was hiding the problem by accepting MusicBrainz partial-matches as "found" (yesterday's 78-95 % was a 3× overstatement of real Spotify-found rate).

### Diagnostic fix shipped

- New `--top-by-popularity N` flag in `build-tools/rag/build_top_tracks_overlay.py` (working tree, uncommitted)
- New diagnostic builder `evaluation/build_overlay.py` (sources candidates from eval traces — used for the initial 213-artist diagnostic overlay)
- DS re-run with the 213-artist diagnostic overlay populated: **Tracks A 20, Tracks B 30/30, Spotify-found 100 %, cite 90-100 %, leakage 0, fit-check 0 fails**. Source: `evaluation/results/20260515-100512/comparison.md`.
- Full-corpus overnight build running (`bh3ue7qs2`) — top 80 K artists by listener_popularity, ETA ~04:00 2026-05-16. Will write a complete-enough `top_tracks_overlay.json` to the user's app dir.

### Production fix (TODO — needs CP ALLOWED + image rebuild)

`build-tools/rag/run_spotify_enrichment.py` **already has Pass 4 (top-tracks fetching) implemented** in the working tree but never committed. To activate it on the cloud-run weekly cycle:

| Step | Action | Who |
|---|---|---|
| 1 | `CP ALLOWED` commit of the working-tree changes (`build_top_tracks_overlay.py`, `run_spotify_enrichment.py`, `spotify_enrichment/client.py`) | User must approve |
| 2 | Re-enable Spotify enrichment in `cloud_run_publish.py` — currently gated off (commit `be71571`) because genres were emptied post-Feb-2026. The new top_tracks logic is the value-add even with empty genres. | User / future agent |
| 3 | Rebuild + push Docker image: `gcloud builds submit --tag gcr.io/spotivibe-rag/builder build-tools/` (or whatever the existing build command is) | User — agent cannot do this without CI auth |
| 4 | Manually trigger the rebuilt job: `gcloud run jobs execute spotivibe-rag-builder --region us-central1`. The Cloud Run job has a 60-min timeout — Pass 4 adds ~1 search call per matched artist (~0.17 s with throttle). At ~30 K matched artists × 0.17 s ≈ 85 min, **the existing timeout will need to be raised** (`gcloud run jobs update spotivibe-rag-builder --task-timeout=2h`). | User |
| 5 | Verify the next published `artists.jsonl.gz` carries the new `top_tracks` field on enriched rows | Agent (next session) |

### Implications for OPEN-0 (DS default ship)

The DS default flip on 2026-05-14 was the right call. Yesterday's "under-fill" was the missing-overlay problem, not a DS quality issue. **Re-validation no longer blocking** — DS + populated overlay = 30/30 tracks at 100 % Spotify-found.

Test A (mini sequential run) is no longer the critical decision: mini wouldn't have done better than DS under verify=spotify without the overlay either. We can still run Test A for the per-$ comparison, but it's now lower-priority than getting the overlay into production.

---

## 🧪 Local-LLM evaluation log — tested candidates (2026-05-15)

Single source of truth for which local models have been tried, with what parameters, and how they performed. Append new rows as models are tested. Used for the "best local LLM for SpotyVibe" decision.

### Llama-3.1-8B-Instruct Q4_K_M ✅ first viable candidate

- **Source**: `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` (HuggingFace), file `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf` (~4.9 GB)
- **Runtime**: llama-server (llama.cpp), exposed at `http://127.0.0.1:8080/v1`
- **llama-server flags**:
  ```
  --ctx-size 8192
  --n-gpu-layers 99
  --cache-type-k q4_0 --cache-type-v q4_0
  --temp 0.3 --top-p 0.9
  --jinja
  ```
- **VRAM measured**: ~5.2 GB on RTX 5060 8 GB (~3 GB headroom for OS+VSCode).
- **App config**: `PROVIDER_PRESET=llamacpp`, `LLM_BASE_URL=http://127.0.0.1:8080/v1`, model id = filename. Stage 3 uses the **minimal local prompt** (`prompts/track_select_system_local_minimal.txt`) — reasoning wrapper dropped; validation prefix gated off for `LOCAL_PRESETS`.
- **Eval run**: `evaluation/results/20260515-115615/` — 3 scenarios × 3 iter, verify_mode=null.

#### Positives
- **Completion: 17/18 playlists hit 30 tracks** (the one short run delivered 20). Schema stable, no prose collapses.
- **Corpus match (≈ Spotify-found proxy): 100 % every iter** under verify=null.
- Leak gate: 0 leaks across 9 B-playlists. Fit-check: 0 fails.
- Cite rate on `post_feedback_tag_regression`: 65-70 % (best of the three scenarios).
- Wall: 103-176 s/iter (down from 107-255 s at ctx=4096 — the ctx upgrade is what unlocked it).

#### Negatives
- **4-6× slower than DS** on the same scenarios (DS reference ~10-30 s wall).
- **Stage 3 reasoning field still MISSING** from every response — harness warns, pipeline accepts; means we lose the audit trail (`MISSING from response — model did not follow the new schema`).
- **Cite rate weak on default + niche**: 16-42 % vs DS 90-100 %. Model fills the playlist but doesn't anchor to must-have artists as well as DS.
- **Not yet validated against `verify_mode=spotify`** — Spotify quota was drained by the morning overlay build. The 100 % "Spotify-found" is corpus-match, not real grounding. Re-run when quota resets (~17:00 today or later).
- At ctx=4096 the model collapsed (2/9 complete, frequent under-fill). ctx≥8192 is mandatory.

#### Status
Production-acceptable for a local-only / privacy-first user; not the default. Keep as a tested alternative. Pending: spotify-verify re-run for true grounding number.

### {Next model — pending download by user}

(Document model, params, positives, negatives here after run.)

---

## 🚧 OPEN — Start here (2026-05-13, updated 2026-05-15)

> If you are the next agent: read this section first. Everything below
> "Historical context" is finished work kept for traceability.

### 🟡 OPEN-0 — Provider strategy: DeepSeek + OpenRouter SHIPPED but needs re-validation (2026-05-14)

**Status: defaults shipped this morning; afternoon eval revealed `verify_mode=l0_l1` was overstating real-world performance ~3×. Re-validation required before locking in.**

### 🚧 NEXT (2026-05-15 — TOMORROW) — Test 5A + the pipeline-math finding

**🔴 BLOCKING DECISION before test 5A runs:** today's evals revealed `playlist_size=30` is mathematically unreachable under `verify_mode=spotify` for ALL models (DS, mini implied, Llama tested):

| Constant | Value | Source |
|---|---:|---|
| Spotify-found rate (DS, mini, all measured models) | ~30 % | VerifyModes.md May-13 + test 5 today (29.2 % measured) |
| `MAX_GPT_CALLS_PER_RUN` | 4 | `config.py:97` (lowered from 20 during Phase 2.6) |
| `BATCH_SIZE` | 10 | `config.py:50` |
| `STAGE3_OVER_REQUEST` | 2 | `config.py:59` |
| Max suggestions per run | **48** | (BATCH_SIZE + over-request) × MAX_CALLS = 12 × 4 |
| Max verified tracks per run | **~14** | 48 × 0.30 |
| `playlist_size` in eval settings | **30** | UNREACHABLE — needs ~100 suggestions @ 30 % verify |

Phase 3 `l0_l1` numbers (15-26 tracks) only worked because MusicBrainz fakely "verified" ~90 %. With real Spotify, ceiling is ~14 tracks for any model.

**Local Llama harness eval today** (`evaluation/results/20260514-203231/`) confirmed it's universal: Llama 3.1 8B local also under-filled, not a model-specific issue. Llama additionally needs `--ctx-size 16384` (not 8192) — Stage 3 prompt overflows the smaller window. Updated server params:

```bash
llama-server --model Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --ctx-size 16384 --cache-type-k q4_0 --cache-type-v q4_0 \
  --n-gpu-layers 99 --temp 0.4 --top-k 40 --top-p 0.9 \
  --repeat-penalty 1.1 --jinja
```

**Fix one before running 5A** (recommend option A):

| Option | Change | Impact |
|---|---|---|
| **A (recommend)** | Drop eval `playlist_size` 30 → 10 (production default) | Matches what users actually run; realistic comparison |
| B | Bump `MAX_GPT_CALLS_PER_RUN` 4 → 10 | More batches per run; 4× cost on under-filling runs |
| C | Run as-is, accept "≥ 14 tracks" as new completion target | Comparison still works but throws off VerifyModes.md baselines |

**Then test 5A: DS vs mini head-to-head on verify=spotify.**

```ini
# evaluation/settings.ini
models = gpt-5.4-mini
iterations = 3
playlist_size = 10        # option A — production default
scenarios = default,niche_only_strict,post_feedback_tag_regression
```

```bash
# Switch keychain back to OpenAI key first, then:
python -m evaluation.run_evaluation --no-confirm --verify-mode spotify
```

**Expected cost:** ≈ $0.15-0.20 (cheaper at playlist_size=10), **wall:** ≈ 1.5 h.
Output: `evaluation/results/<ts>/comparison.md`. Compare against DS test 5 (`evaluation/results/20260514-154934/`) — if mini fills the 10-track target consistently while DS doesn't, the default-flip needs to revert.

**Holding decisions until 5A complete:**
- Whether `DEFAULT_OPENAI_MODEL` / `DEFAULT_PROVIDER_PRESET` stay as DS+OR or revert to mini+OpenAI
- Whether the `KNOB_AUTO_ON_PRESETS={openrouter}` auto-enable of lean+adaptive stays (test 5B today: lean prompt is NOT the regression — same under-fill with lean OFF)
- Whether to bump `MAX_GPT_CALLS_PER_RUN` 4 → 10 to support larger playlist sizes under verify=spotify (separate from 5A — could ship if 5A reveals real-world quality is good but ceiling is binding)

---

**Earlier today (2026-05-14): defaults switched.**

After analysis of Phase 2 + Phase 3 + large_profile data, defaults were
flipped to **DeepSeek V4 Flash via OpenRouter** on 2026-05-14:

- `DEFAULT_OPENAI_MODEL = "deepseek/deepseek-v4-flash"`
- `DEFAULT_PROVIDER_PRESET = "openrouter"`
- `DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"`
- `SPOTYVIBE_LEAN_PROMPT=1` + `SPOTYVIBE_ADAPTIVE_ASK=1` auto-on for OR route
- gpt-5.4 (premium) + STAGE3_MODE switch ripped out — DS matches gpt-5.4
  cite at ~1/10 cost, the cost-vs-quality trade-off is gone
- Existing installs unaffected (defaults only kick in when settings empty)
- New OpenRouter setup guide added: `documentation/guides/openrouter_api_key.{en,de}.md`
- Docs updated: README, UserManual, TechnicalManual, help.en.md
- All 1030 core tests pass after the rip

Below is the data summary that motivated the switch (kept for traceability).

Phase 2 paid eval (`evaluation/results/openrouter_phase2/SUMMARY.md`)
compared 3 OpenRouter models × 4 scenarios × n=3 = 36 runs against
the gpt-5.4-mini baseline. Headline:

| Model | ≥15 hits / 12 | Best scenario | Cost / run |
|---|---:|---|---:|
| **DeepSeek V4 Flash** | **2** | default (mean 16.7) | $0.008-0.012 |
| OpenAI gpt-oss-20b | 1 | niche (one 19-track hit, σ high) | $0.005-0.008 |
| Gemma 4-26b-it | 2 | post_feedback (mean 15.3) | $0.003-0.007 |
| gpt-5.4-mini (reference) | 3 (default only tested) | default (mean 15.3) | $0.13 |

**Key DeepSeek wins:**
- Cite **96-98 %** on post_feedback (highest of any model on any scenario)
- 0 leakage, 0 fit-check failures across all runs
- ~13× cheaper per run than gpt-5.4-mini (paid OR pricing)
- 1M context window — addresses the profile-growth concern raised
  during the May-13 strategy discussion
- Confirmed via real eval harness end-to-end (Task B 2026-05-14)

**Decision shipped 2026-05-14:** all four bullets above implemented + gpt-5.4 path ripped out (see new top of OPEN-0).

**Tests DONE 2026-05-14 evening** (Phase 3 — `evaluation/results/openrouter_phase3/SUMMARY.md`):

1. ✅ **DeepSeek × lean+adaptive on default/niche/post_feedback × n=5.**
   Niche jumped 0/3 → 3/5 ≥15 (mean 8.0 → 14.2). Post_feedback jumped
   0/3 → 2/5 (mean 9.0 → 13.6). Default unchanged. Lean+adaptive
   should be enabled-by-default for OR routes.
2. ✅ **n=5 variance reduction** — confirmed Phase 2 rankings hold.
3. ✅ **Profile-growth stress** — new `large_profile_stress` scenario.
   Neither DeepSeek nor mini dominates; both have high variance under
   30-artist-mention profiles. DeepSeek hit 26 tracks one iteration
   (highest of any test) but skipped 2/5 with transient API errors.
   Mini was more consistent (no skips) but lower average. **Conclusion:
   the "small model breaks under big profile" fear is NOT supported.**
4. ✅ **Adaptive ask on niche/post_feedback** — included in #1.

**Tests still open (low priority — defaults already shipped):**

5. ⚠️ **REGRESSION DISCOVERED 2026-05-14.** `verify_mode=spotify` real-world
   eval on DS (lean+adaptive ON, default+niche+post_FB × n=3):
   only **2 of 9 runs produced any playlist**. Spotify-found rate was
   29-100 % on the 2 valid runs, vs 78-95 % we measured under `l0_l1`.
   The `l0_l1` mode was over-stating found-rate by ≈ 3×. The DS-default
   ship decision was made on l0_l1 evidence — needs re-validation.
   Source: `evaluation/results/20260514-154934/comparison.md`.

   **NEXT (tomorrow, 2026-05-15):**
   - **Test A — mini sequential run.** Same 3 scenarios × n=3 ×
     `verify_mode=spotify`, model `gpt-5.4-mini` via OpenAI native.
     ~$0.45, ~2 h wall (~80 min in cooldown). Apples-to-apples comparison
     against today's DS spotify-verify numbers. Decide on DS-vs-mini default
     after this lands. Settings.ini sketch:
     ```
     models = gpt-5.4-mini
     iterations = 3
     scenarios = default,niche_only_strict,post_feedback_tag_regression
     ```
     Run with `python -m evaluation.run_evaluation --no-confirm --verify-mode spotify`.
   - **Test B (done 2026-05-14, 22:09)** — DS with lean prompt OFF on
     `verify_mode=spotify`, default × n=3.
     Result: **same under-fill pattern as lean ON.** Iter 1 errored,
     iter 2/3 status=ok but produced 0 tracks. Stage 2 reported
     `skipped_empty_input` — Stage-3 picks have no overlap with the
     candidate pool. **Lean prompt absolved.** The DS-under-fill is
     structural to DS + real Spotify verify, not a lean-prompt artifact.
     Source: `evaluation/results/20260514-193832/comparison.md`.
   - **Local Llama 3.1 8B smoke (done 2026-05-14, evening).**
     `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf` via llama-server at
     127.0.0.1:8080, `ctx=8192 + q4_0 KV cache + ngl=99 + temp=0.3 + jinja`.
     - 46 tok/s output, ~20 s for a 12-track batch
     - 12/12 valid JSON, 0 forbidden-artist hits, 0 forbidden-track hits,
       2/12 reference artists (≤ 70 % cap)
     - **Concern: lazy rationale** — all 12 entries returned the IDENTICAL
       rationale array (verbatim copy-paste of all 4 must_have items),
       i.e. Llama isn't reasoning about *why this specific track* fits.
       Same failure mode that hurt gpt-4.1 historically. The
       must-have-cite metric still passes but per-track differentiation
       is poor.
     - Server params confirmed correct: no tweaks needed.
     - First full-eval attempt **failed all 3 iters** with `OpenAIAuthError`.
       Root cause: harness `prepare_sandbox` only wrote `PROVIDER_PRESET`
       to the sandbox `settings.conf` when the model id contained `/`.
       Llama's filename-style id (no `/`) fell through → sandbox loaded
       the new `DEFAULT_PROVIDER_PRESET=openrouter` → calls went to
       openrouter.ai with the real OpenAI key from `[openai] api_key` →
       401. Fix shipped: `prepare_sandbox` now respects caller-supplied
       `PROVIDER_PRESET` / `LLM_BASE_URL` env vars when the model id
       isn't an OR `provider/model` form. See
       [evaluation/harness.py:247-269](evaluation/harness.py#L247-L269).
     - **Second attempt failed schema compliance.** Llama returned prose
       ("After verifying the approved artists…") instead of JSON across
       all 3 iters. Two-fix chain landed:
       1. New minimal Stage-3 prompt without the `reasoning` wrapper
          (`prompts/track_select_system_local_minimal.txt`, wired in
          [core/src/suggestions.py:114-119](core/src/suggestions.py#L114) +
          [:1481-1500](core/src/suggestions.py#L1481)). Routed to
          `LOCAL_PRESETS` only; cloud lean path keeps the reasoning
          variant for telemetry.
       2. Validation-prefix gated off for local presets
          ([core/src/suggestions.py:1561-1578](core/src/suggestions.py#L1561)) —
          the "Before output, verify each track…" framing was the
          dominant trigger for Llama's prose mode.
     - Stand-alone curl confirms the fix: 49.7 tok/s, 6/6 valid JSON,
       all required schema keys. Third eval run started + cancelled
       (scope expanded for 2026-05-15). No production-real Tracks A /
       Spotify-found numbers yet for Llama.

### 🧪 NEXT (2026-05-15) — extended local-LLM eval matrix

Goal: get a real measurement of local 8B-class models on SpotyVibe's
production pipeline now that the prompt-emission bugs are fixed. Single
seed scenario (default), n=3 per model, `verify_mode=spotify`. Sequential
runs (run.lock mutex). Local LLM = free; only cost is wall-clock + GPU.

**Settings.ini sketch** (rotate the `models =` line per run):

```ini
[evaluation]
models = <one model id at a time>
iterations = 3
scenarios = default
playlist_size = 30
```

**Launch command** (same env for every model):

```bash
PROVIDER_PRESET=llamacpp LLM_BASE_URL=http://127.0.0.1:8080/v1 \
SPOTYVIBE_SKIP_KEYRING=1 OPENAI_API_KEY=not-needed \
python -m evaluation.run_evaluation --no-confirm --verify-mode spotify
```

Restart `llama-server` between models with the matching `--model` flag.
Same base flags (`--ctx-size 8192 --cache-type-k q4_0 --cache-type-v q4_0
--n-gpu-layers 99 --temp 0.3 --top-k 40 --top-p 0.9 --jinja`) work for
every 8B-class Q4_K_M model below — all fit 8 GB VRAM at this ctx.

#### Models to test (recommendations, ranked)

| # | Model | Why | GGUF source (Q4_K_M direct download) |
|---|---|---|---|
| 1 | **Meta-Llama-3.1-8B-Instruct** (baseline, already pulled) | Today's baseline. Schema-compliance fixed but lazy-rationale + RAG-pool-quality limits known. | `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` → [Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf](https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf) |
| 2 | **Hermes-3-Llama-3.1-8B** | Llama 3.1 8B **fine-tuned for structured output + function calling**. Best schema-compliance per param-count in the 8B class. Same chat template as Llama 3.1 → identical llama-server flags. Most likely winner for SpotyVibe's workload. | `bartowski/Hermes-3-Llama-3.1-8B-GGUF` → [Hermes-3-Llama-3.1-8B-Q4_K_M.gguf](https://huggingface.co/bartowski/Hermes-3-Llama-3.1-8B-GGUF/resolve/main/Hermes-3-Llama-3.1-8B-Q4_K_M.gguf) |
| 3 | **Qwen2.5-7B-Instruct** | 7B (not 8B) — leaves ~1 GB more VRAM headroom for context. **Non-reasoning by default** (unlike Qwen3 which would need `/no_think` plumbing). Known strong JSON-mode behavior. | `bartowski/Qwen2.5-7B-Instruct-GGUF` → [Qwen2.5-7B-Instruct-Q4_K_M.gguf](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf) |
| 4 | **Mistral-7B-Instruct-v0.3** | EU provider (data-residency bonus), 7B, native `response_format` support. Solid floor option. | `bartowski/Mistral-7B-Instruct-v0.3-GGUF` → [Mistral-7B-Instruct-v0.3-Q4_K_M.gguf](https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf) |
| 5 | **Phi-4-mini-instruct (3.8 B)** | Microsoft, very small → can run Q5_K_M (better quality) and ctx=16k+ in 8 GB. Risk: smaller params → may hallucinate more on niche artists. Stretch-goal candidate. | `bartowski/Phi-4-mini-instruct-GGUF` → [Phi-4-mini-instruct-Q5_K_M.gguf](https://huggingface.co/bartowski/Phi-4-mini-instruct-GGUF/resolve/main/Phi-4-mini-instruct-Q5_K_M.gguf) |

**Models explicitly DESELECTED:**
- **Qwen3-8B** — has thinking-mode ON by default; same reasoning-tier
  failure mode that hurt gpt-5.4. Would need `/no_think` token plumbed
  into every request → fragile. Use Qwen2.5-7B instead.
- **Gemma 2 9B** — 9B Q4_K_M is bigger than 8B; tighter VRAM budget.
  Risk of OOM at ctx=8192 without dropping `--n-gpu-layers`.
- **DeepSeek-V3 distilled** — DS publishes smaller models, but local
  quants aren't as good as the cloud V4 Flash; not worth the extra
  download.

**What to measure per model:**

| Metric | Why it matters |
|---|---|
| Tracks A (mean over n=3) | Pipeline-completion under real Spotify verify |
| Spotify-found rate | Whether the model produces real, findable tracks |
| Must-have cite rate | Schema discipline / per-track rationale quality |
| Tokens/sec output | Throughput on this machine |
| Wall time / iter | User-facing latency on 30-track playlist |
| Schema-parse failure count | Robustness to the production prompt |

**Decision after the matrix:** pick a default *local* model recommendation
to publish alongside the cloud DS / mini defaults. Update
`documentation/UserManual.md` and `documentation/guides/llamacpp_setup.en.md`
with the winner. Local LLM use is opt-in (no API cost, full privacy) but
should ship with a known-good model choice.
6. (Infra) Per-model provider tag in harness — needed to compare OAI
   native gpt-5.4-mini against OR DeepSeek in one matrix at same n.
   ~2-3 h dev.
7. ✅ **RESOLVED 2026-05-14.** Root-cause for DeepSeek's transient skips
   on `large_profile_stress` (2/5 runs ended in <10 s with
   `status=skipped`): summary.json error was
   `seed_train: AI returned an empty response (Profile Training)`.
   The skip was NOT in Stage 3 / large-prompt handling — it was the
   pre-run `train_profile()` call hitting an empty 200-OK response
   from DeepSeek. Source: `evaluation/results/20260514-135951/
   large_profile_stress__…-iter4/summary.json`.
   Fix shipped: `call_gpt_json_with_meta()` in
   [core/src/openai_http.py:428-481](core/src/openai_http.py#L428-L481)
   now retries **once** on an empty 200-OK content before raising —
   `chat_completions_create()` already retries 429/5xx; this layer
   covers the empty-content-but-no-error path that DS occasionally
   takes on big prompts. Affects Band/Song Analysis, AI Profile
   Update / Training, and Stage 2 avoid-check (all `call_gpt_json`
   callers).

### 📸 OPEN — Documentation screenshots (user-side task)

The setup guides under `documentation/guides/*.md` reference 18 PNGs
under `documentation/assets/guides/` that are currently 800×450
placeholder images (14 carried over from the previous guides + 4 new
ones for the OpenRouter guide added 2026-05-14). Screenshots cannot be
captured by the agent — the user needs to walk through each dashboard
and snap the relevant view. See the "Screenshot capture checklist"
appendix at the bottom of this file for the exact dashboard state +
filename mapping.

### 🧪 OPEN — Local custom LLM quality (user-side task)

User has flagged validating local-LLM quality (Ollama / LM Studio /
llama.cpp) for the workload as an open item. No agent-side action —
the user needs to run a few playlists through the harness on the
local route and compare against the DS baseline.

**OpenRouter free-tier capacity for end-users** (informational):
~12-15 playlist generations/day on the 200-RPD aggregate free cap
(each run ≈ 15-17 LLM calls). With even $5 OpenRouter credit topup
on a paid route like DeepSeek V4 Flash, a user gets ~500-1000 runs
before refill. This is the "single subscription → many models" lever
the user flagged on 2026-05-13 as desirable.

### 🟡 OPEN-1 — Fix playlist under-fill (partially shipped)
**Exp 1 DONE 2026-05-13.** Conditional batch-budget bump (4 → 6)
shipped to `app.py`. Eval: l0_l1, n=5 baseline vs n=3 bump, 4 scenarios.

| Scenario | Baseline ≥15 rate | Bump ≥15 rate | Delta |
|---|---:|---:|---:|
| **default** | 20 % (2/10) | **50 % (3/6)** | +30 pp |
| niche_only_strict | 0 % | 0 % | 0 (pool-starvation) |
| post_feedback | 0 % | 0 % | 0 (pool-starvation) |
| lastfm_tag_weighting | 0 % | 0 % | 0 (zero pool) |

Mean Playlist-A (all scenarios): 6.9 → 7.9 tracks (+14 %). Leakage: 0
both legs. Budget: $6.78 total. See `evaluation/results/open1/SUMMARY.md`.

**Exp 2 DONE 2026-05-13 — Adaptive ask size: REJECTED.** Implemented
`SPOTYVIBE_ADAPTIVE_ASK=1` env-gate in `app.py` (ask `ceil(remaining/0.4)`
capped at 20 when prev batch found-rate <40%). Eval: l0_l1, n=3 control
vs n=3 adaptive, niche + post_feedback scenarios.

| Scenario × model | Control mean | Adaptive mean | Δ |
|---|---:|---:|---:|
| niche × gpt-5.4 | 11.0 | 9.7 | -1.3 |
| niche × gpt-5.4-mini | 10.7 | 12.7 | +2.0 |
| post_feedback × gpt-5.4 | 9.0 | 7.0 | -2.0 |
| post_feedback × gpt-5.4-mini | 7.3 | 8.7 | +1.4 |
| **Aggregate (n=12)** | **9.5** | **9.6** | **+0.1** |

Mixed signal: helps mini, hurts gpt-5.4 (likely Stage-3 pool dilution under
ask=20). Net flat. 1/12 ≥15 vs 0/12 — within noise. Cost +6%. Decision:
do NOT ship by default. Env-gate stays. See
`evaluation/results/open1_exp2/SUMMARY.md`.

**Gates.** Must non-regress on must-have-cite (vs 83.4 % spotify baseline),
leakage, and fit-check. See `documentation/VerifyModes.md`.

**Possible Exp 3 (not run today, budget exhausted).** Raise
MAX_GPT_CALLS_PER_RUN to 8 when bump+adaptive both fire. Or per-model
gate: enable adaptive only for gpt-5.4-mini.

### 🟡 OPEN-1a — OpenRouter integration (Stage 3 only)
**Driver.** Exp 2 confirmed gpt-5.4 (reasoning-tier) hurts on this workload.
Mini matches or beats it for ¼ cost. Hypothesis: instruction-following
non-reasoning models are a structural better fit. Strategy: integrate
**OpenRouter** as a meta-provider — one API key, ~300 models accessible,
OpenAI-compatible API (likely a base-URL + key swap on existing
`core/src/openai_http.py`). Existing provider selection already supports
OpenAI + Local LLM, so OpenRouter is a third option with low integration
cost. Existing model allow-list gates which models eval/app can call.

**Scope:** Stage 3 (suggestion engine) only. Stage 2 (audit/avoid pass) stays
on OpenAI mini — it is ~5 % of bill, not worth re-routing yet. Revisit
Stage 2 model selection ONLY if Stage 3 win is confirmed.

**Dual value:**
- Internal: cheap survivor-selection funnel across many models.
- User-facing: one-subscription, multi-model choice is a competitive
  product feature (parity with Copilot, Cursor).

**Acknowledged risk:** OpenRouter becomes a new single point of failure
for all routed models. Mitigation deferred — if a winner emerges, add
native direct integration in Phase 3 as production path; OpenRouter
stays as fallback / experimentation lane.

#### Phase 1 — Wire OpenRouter (4-8h, €0)

1. **Sign-up.** Free OpenRouter account → API key. Store in
   `evaluation/settings.ini` and (for runtime) `.credentials` (both
   gitignored). 15 min.
2. **Provider plumbing.** Extend existing provider abstraction with
   `openrouter` option. Likely:
   - Base URL: `https://openrouter.ai/api/v1` (OpenAI-compatible).
   - Same chat-completion shape → minimal `openai_http.py` change.
   - Add per-model alias map (e.g. `openrouter/google/gemini-2.5-flash-lite`).
   - Token-count normalization (verify against OpenRouter `usage` field).
   - i18n keys: en/de/jp entries for new provider strings.
3. **Allow-list.** Extend existing allow list with the candidates below.
4. **Tests.** Mock OpenRouter responses in `core/tests/`. Never hit real
   API in unit tests.
5. **Cost telemetry.** Add OpenRouter pricing rows to `eval_log.py` and
   `evaluation/results/open1/cost.py`. Use OpenRouter's reported `usage`
   field as source of truth.

#### Phase 2 — Smoke + free-tier eval (1-2h, €0)

Use free models on OpenRouter where available; cheap paid models otherwise.
Smoke = 1 Stage-3 call per model, verify JSON schema honored. Drop
failures. Then n=1 single-scenario eval on niche_only_strict.

#### Phase 3 — €5 paid eval per survivor

- Full 4-scenario × 3-iter matrix per surviving model.
- Gates: must-have-cite ≥ 70 %, leakage 0, tracks A mean ≥ mini.
- Winner(s) → consider native direct integration as production path
  (separate task, not blocking).

#### Candidates (initial allow-list extension)

| Rank | OpenRouter model id (approx) | $/M in | $/M out | Why |
|---|---|---:|---:|---|
| 1 | `google/gemini-2.5-flash-lite` | 0.10 | 0.40 | Cheapest viable non-reasoning |
| 2 | `deepseek/deepseek-chat` (V4 Flash) | 0.14 | 0.28 | 1M context — addresses profile-growth risk |
| 3 | `mistralai/mistral-small-3.1-24b-instruct` | 0.20 | 0.60 | Designed for instruction-following |
| 4 | `google/gemini-2.5-flash` | 0.30 | 2.50 | Step up if Flash-Lite too dumb |
| 5 | `mistralai/ministral-3b` | 0.04 | 0.04 | Long-shot, 25× cheaper than mini |
| 6 | `qwen/qwen3-32b-instruct` | 0.10 | 0.30 | Strong benchmarks; review data-residency before user-facing exposure |

Free-routed models (DeepSeek V3, Llama, Nemotron) optional for smoke test;
skip for paid eval unless one of the above fails.

#### Explicitly out of scope

- Reasoning-tier models (Gemini 3.1 Pro, DeepSeek V4 Pro, gpt-5.5): same
  overthink failure mode as gpt-5.4.
- Claude Haiku 4.5: 4× output cost vs mini, no quality edge.
- Local-LLM (Qwen3-8B failed already, others parked): tracked in OPEN-5.

#### Why test gpt-5.4 knobs in parallel

5.4 knob test (OPEN-1b) is so cheap (~€1, 1-2h) that running it alongside
OpenRouter wiring closes the question definitively. If 5.4 stays bad
even with tightened knobs, the OpenRouter investment is fully justified;
if 5.4 with knobs flipped matches mini, we have a no-integration-needed
fallback.

### 🟢 OPEN-1b — gpt-5.4 reasoning-knob tuning (small test, in parallel with OPEN-1a)
**Cheap test** (~€1, 1-2h). Run before or alongside OpenRouter
integration — does not block OPEN-1a.

**Knobs to flip:**
- Temperature 0.7 → 0.2-0.3 in `app.py` Stage-3 call (around line 1136).
- Audit `prompts/*.txt` for "explain carefully", "consider", "reason about"
  phrasing → strip.
- Stage-3 JSON schema: drop any `reason`/`justification`/`explanation`
  field if present. Keep `artist`, `track`, optionally `tags`.
- Cap `max_tokens=800` on Stage-3 call for 5.4.
- (Optional) If 5.4 exposes a `reasoning_effort` knob: set to minimum.

**Eval:**
- Single scenario (`default` — where 5.4 currently performs best, signal
  is cleanest) × n=3 × verify_mode=l0_l1 (cache-less).
- Compare must-have-cite, tracks A, wall-time, cost vs current 5.4
  baseline.

**Decision gates:**
- If tightened 5.4 matches or beats current mini on tracks A AND
  must-have-cite — keep 5.4 with tightened config as a premium tier.
- If tightened 5.4 still underperforms mini — park 5.4 permanently;
  OpenRouter winner takes its slot.

**Budget guard:** if total day spend (this + OPEN-1a smoke) crosses €5,
stop and document where we are.

### 🟠 OPEN-2 — `.spotify-cache` disappearance (OP2, recurring)
3rd confirmed occurrence on 2026-05-13. N3a/N3b/N3c make most evals
survive without the cache, but the root cause is unresolved. ~30 min
spike: instrument the path (`%LOCALAPPDATA%\spotyvibe\.spotify-cache`)
with a `WatchService` or simple polling-logger to capture which
process unlinks it. No budget cost.

### 🟠 OPEN-3 — N4: Multi-scenario overlay rebuild (operational)
Code shipped (`build_top_tracks_overlay.py --scenarios all --resume
--throttle-ms 2000`). Needs ~5 000 Spotify calls spread across 1–3
sessions at ≥ 2.0 s/call. **Without this**, `--verify-mode overlay`
and the L0 leg of `l0_l1` have lower hit rates on niche scenarios.
Blocked by OP2 today.

### 🟡 OPEN-4 — Documentation refresh (N6)
`documentation/VerifyModes.md` shipped 2026-05-13 (new). Still owed
in `documentation/TechnicalManual.md`: verifier-mode matrix,
probe-gate workflow, recommended-n-iterations table. Trigger after
OPEN-1 lands so the recommended-config block reflects the new batch
budget.

### 🟢 OPEN-5 — Local-LLM v1 fingerprint (N5, parked)
Track B's Step 3 captured fingerprints for the three OpenAI models.
Land the 4th (local Ollama) only when a local model is added to
`evaluation/settings.ini`. Skipped by user this session.

### ⛔ NOT-DOING — `verify_mode=l0_l1` promotion
Decided 2026-05-13 on the strength of the step-7 three-mode
comparison: l0_l1 regresses must-have-cite by −1.7 pp vs
`spotify` (81.7 % vs 83.4 %). The "no regression — ever" rule
(`AGENTS.md`) blocks promotion regardless of the +6.5 pp Spotify-found
and −30 % wall-time wins. Experiment parked; rationale in
[documentation/VerifyModes.md](documentation/VerifyModes.md).
Revisit only after tightening the MB gate (require non-empty
`lastfm_tags` or `release-id`, not just a recording hit).

---

## 📈 Executive summary — improvement trajectory

Distilled from `evaluation/baselines/HISTORY.md`. Numbers are
playlist-A track count and must-have-cite % (gpt-5.4-mini unless
noted), with cost-per-run for context. The story is one of
**measurement maturity first, structural fixes second, prompt work
last** — the biggest wins came from making the harness honest, not
from re-tuning the prompt.

### Phase 1 — Establishing a valid baseline (2026-05-08 → 2026-05-11)

| Date | Change | Mini A / cite | gpt-5.4 A / cite | Cost / run | What it taught us |
|---|---|---|---|---|---|
| 05-08 | B1 baseline | 14.3 / — | 11.0 / — | ~$0.40 | mini wins A, gpt-5.4 wins B (the **B-collapse** finding). |
| 05-10 | C1–C4 cost levers | (invalid: Tier-0 bug) | (invalid) | — | Discovered `STAGE3_MODE` env-override was being defeated by `load_dotenv(override=True)`. Three runs of data thrown out. |
| 05-11 06:04 | Tier-1 logging added | (invalid: Tier-0 v2) | (invalid) | ~$0.81 | Spent ~$0.81 on a run we then had to invalidate. **Lesson: instrumentation has to land before — not with — the change you want to measure.** |
| 05-11 08:17 | **Tier-0 v2 fix + cache-prefix fix** | 13.0 / 86 % | 13.7 / 96 % | ~$0.90 | First valid cross-model comparison since L5. mini's B-collapse confirmed at n=3. System prompt finally cache-stable (1 md5, was 5). |

**Net of Phase 1:** ~$2.10 spent before we had one trustworthy row.
The runnable-vs-measurable gap was the dominant blocker; not the
model and not the prompt.

### Phase 2 — Prompt spike, mostly negative (2026-05-12)

| Variant | Outcome |
|---|---|
| **R1.1** — cite REMINDER at end of user msg | ✅ Shipped (cite parity, 81.5 %). |
| **R1.2** — "do NOT attempt to recall" | 🛑 Rejected — n=1 trial omitted 40/40 artists → 0 tracks. |
| **R1.3-strict** — force `omitted_artists ≥ N−M` quota | 🛑 Rejected — mini A −38 %, gpt-5.4 B: **2 of 3 EMPTY**. |
| **R1.3-softened** — transparency hint, "prefer FILLING over inflating" | ✅ Shipped — mini A=12.0 (parity), one 15/15 perfect playlist. |

**Net:** 4 prompt variants, 1 kept, 1 cite-neutral, 2 outright
regressions. Confirmed the structural insight: **mini does not
recover from B-pool thinning after dislikes via prompt pressure**.
The fix has to be in the pipeline (A6 / RAG re-retrieve), not in
the words.

### Phase 3 — Probe-first methodology (2026-05-12 → 2026-05-13)

Replacing the multi-$ full eval with an 8-probe synthetic battery
(B-1…B-11) for **~$0.11 total** across 3 models.

| Probe | Finding | Action taken |
|---|---|---|
| B-1 `quota_preserved_under_hard` | mini = 0.0 vs gpt-5.4/4.1 = 1.0 | Retroactively predicted R1.3-strict's mini collapse. |
| B-11 `single_artist_no_known` | **All 3 models confabulate** | Motivated **N1** (early A6 refusal gate). |
| B-6 `n_required_for_5pp_signal` | gpt-4.1=5, gpt-5.4=19, mini=85 | Motivated **N2** (iterations 3 → 5 default + `--iterations` CLI). |

**Net:** The probe battery turned every prompt change from a
~$0.50 gamble into a $0.01–0.06 hypothesis test. This is the
single biggest workflow improvement in the timeline.

### Phase 4 — Structural / infrastructure fixes (2026-05-13)

| Item | Impact |
|---|---|
| **N1** A6 pool-starvation refusal gate (`select_tracks`) | Production fix: skips LLM call when pool ≤ 1 and no `known:` tracks. **0 added cost** (saves a call). 5 new tests. |
| **N2** iterations 3 → 5 default + `--iterations` CLI | Eval signal: deltas < 5 pp are now distinguishable from noise on gpt-4.1; manual override for tighter signals on bigger models. |
| **N3a** `prepare_sandbox(require_spotify_cache=False)` | Unblocks evals on machines without a live Spotify OAuth. |
| **N3b** `SPOTYVIBE_SKIP_SPOTIFY_CONNECT=1` env-seam in `app.py` | Pipeline runs end-to-end without a Spotify connection when verify-mode ≠ spotify. |
| **N3c** `iter_search_tracks` verifier-precedence bug-fix | Latent regression — verifier-swap was dead code; token-fetch ran before `_VERIFIER` check. 2 regression tests. |
| **N3d** null-uri dedup bug-fix in `run_pipeline()` | Cache-less Null eval reported playlist=1 for every iter because `set(uri)` collapsed every `None`. Mean playlist size **1.0 → 13.6** after fix. |

**Net of Phase 4:** Six infrastructure fixes, **0 added budget**,
1046 core tests green (was 1032 at start of phase). The cache-less
null-verify eval went from impossible → routine.

### Phase 5 — Verify-mode comparison (2026-05-13)

The three-mode side-by-side at n=5 × 2 models per mode finally
isolated **verify-mode choice** as a single axis:

| Mode | Spotify-found | Must-have-cite | Wall | Verdict |
|---|---:|---:|---:|---|
| null | 100 % (fake) | 85.4 % | 36 s | dev only |
| **spotify** | 31.2 % | **83.4 %** | 64 s | ✅ production default |
| l0_l1 | 37.7 % (+6.5 pp) | 81.7 % (**−1.7 pp**) | 45 s (−30 %) | 🛑 parked — quality regression |

The trade-off is real but asymmetric: l0_l1 buys speed and
Spotify-hit-rate at the cost of cite-rate, and the project's
North-Star rule says quality wins ties. Documented in
[documentation/VerifyModes.md](documentation/VerifyModes.md).

### Aggregate picture

- **Cost-to-validate** dropped from ~$0.90 / cross-model eval → ~$0.11
  / probe battery — an order of magnitude, and the probes are
  better-targeted.
- **Test coverage** climbed from 687 → 1046 core tests over the
  trajectory, with the largest jump (1032 → 1046) coming from the
  N1+N2+N3a/b/c/d wave that landed the harness-robustness fixes.
- **Quality (must-have-cite, mini)** has held roughly flat around
  **80–88 %** across all valid measurement points. The headline
  finding is that quality is **bounded by the upstream pool and
  the model's compliance ceiling**, not by prompt tuning — every
  prompt variant that tried to push above this band regressed.
- **Open frontier:** completion rate (currently 1/10 reaching ≥ 15
  tracks on real-verify modes) is the next metric the trajectory
  has not yet moved. OPEN-1 above targets exactly that.

---

---

## Archive

Pre-2026-05-12 sessions, Tracks A+B research, post-Phase B agendas, and the screenshot capture checklist have been moved to [`documentation/history/sessions-2026-Q2.md`](documentation/history/sessions-2026-Q2.md) to keep this file scannable. The per-fix headline log lives in [`evaluation/baselines/HISTORY.md`](evaluation/baselines/HISTORY.md).
