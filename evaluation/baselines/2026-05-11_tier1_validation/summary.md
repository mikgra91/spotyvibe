# Tier-1 logging validation eval — 2026-05-11

**Run:** `evaluation/results/20260511-060407/`
**Scope:** scenario `default`, models `gpt-5.4-mini` + `gpt-5.4`, 3 iter each (planned 6 / completed 6).
**Wall:** 65 min (08:04 → 09:09).
**Real cost:** ~$0.81 (see correction below — labelled costs are wrong).
**Purpose:** validate Tier-1 diagnostics shipped 2026-05-10 (`system_fingerprint`,
`prompt_hashes`, `stage3_mode`) and re-test the B1 mini-collapse-on-Playlist-B
hypothesis with C1-C4 cost levers in place.

> ## 🚨 KNOWN INVALID FOR CROSS-MODEL COMPARISON — Tier-0 bug RECURRED
>
> Every iter — both labelled `gpt-5.4` AND labelled `gpt-5.4-mini` — actually
> ran `gpt-5.4-mini` in `fast` mode. The 2026-05-10 fix in
> `evaluation/run_evaluation.py:421` (`os.environ["STAGE3_MODE"] = "custom"`)
> is **defeated by a downstream `load_dotenv(SETTINGS_FILE, override=True)`**
> in `config.py:487` (called via `init_config()` during the production-module
> import chain after the harness sets the env). User's `settings.conf` has
> `STAGE3_MODE=` (empty); `load_dotenv(override=True)` overwrites
> `os.environ["STAGE3_MODE"]="custom"` with `""`, then `get_stage3_mode()`
> falls back to `STAGE3_MODE_DEFAULT="fast"`, then `_resolve_stage3_model()`
> ignores `OPENAI_MODEL` and returns `STAGE3_FAST_MODEL=gpt-5.4-mini`.
>
> **Reproduction (3-line test):**
> ```python
> os.environ["STAGE3_MODE"] = "custom"
> load_dotenv(SETTINGS_FILE, override=True)   # called in config.init_config()
> assert get_stage3_mode() == "custom"        # FAILS — value is "fast"
> ```
>
> Cross-model rows in this report (gpt-5.4 vs mini) are **mini-vs-mini**
> comparisons. Mini-only aggregates (n=6 default-scenario observations)
> remain trustworthy.

---

## Headline findings

### 1. 🔴 Tier-0 bug v2 — `load_dotenv(override=True)` defeats the explicit env override

The 2026-05-10 fix (`os.environ["STAGE3_MODE"]="custom"` instead of
`setdefault`) is **not durable** because `config.py:487` runs `load_dotenv`
with `override=True`, which clobbers any prior `os.environ` value with the
file value (including empty strings). Two complementary fixes are needed:

- **Short-term (eval-only):** monkey-patch `config.get_stage3_mode` to
  return `"custom"` for the duration of the eval, so no downstream
  `load_dotenv` reset matters.
- **Long-term:** `config.init_config()` (or wherever `load_dotenv(SETTINGS_FILE,
  override=True)` is called) should **skip the `STAGE3_MODE` key** when its
  file value is empty, OR call `load_dotenv(override=False)` and rely on
  the explicit pre-seed.

This bug means the validation eval (2026-05-10) AND today's eval both
produce mini-on-mini data when comparing models. **Every comparative eval
done after L5 shipped is suspect** until this is fixed.

### 2. ✅ Tier-1 logging mostly works — but `system_fingerprint` is always null

Per-batch row in `eval.jsonl`:
```json
"prompt_hashes": {"system_md5": "c3d8663ec2876f91", "user_md5": "254de325c083ce05"},
"stage3_mode": "fast",
"system_fingerprint": null,
"cached_tokens": 0,
"usage": {"prompt_tokens": 2166, "completion_tokens": 1417, ...}
```

| Field | Status | Notes |
|---|---|---|
| `prompt_hashes.system_md5` | ✅ populated | Stable per-batch within a single iter; varies across batches (see Finding 3). |
| `prompt_hashes.user_md5` | ✅ populated | Unique per batch (8/8 distinct in every iter — expected, deny set + accepted block grow). |
| `stage3_mode` | ✅ populated | Caught the Tier-0 bug — every batch shows `"fast"` while we asked for `"custom"`. |
| `system_fingerprint` | ❌ always `null` | Either (a) `gpt-5.4-mini` doesn't return it on this endpoint, or (b) our http wrapper drops it. The wrapper just returns the raw OpenAI JSON, so most likely (a). Needs a side-test against `gpt-5.4` (cloud) or `gpt-4.1` to confirm. |

**Action:** plumbing is fine. Either accept the gap or run a one-off
side-test with a different model to verify (a). Logging code in
`core/src/suggestions.py:1545,1554` already pulls the field correctly.

### 3. 🔴 Cache-prefix instability — `batch_size` is in the SYSTEM prompt

Discovery from inspecting `system_md5` per batch: **5 unique
`system_md5` values across 3 iters per "model"** (should be 1).

Diff between batch 1 and batch 3 (same iter, same playlist):
```
- 1. Generate UP TO 12 tracks. Returning FEWER is correct...
+ 1. Generate UP TO 7 tracks. Returning FEWER is correct...

- 6. ...target: ≥ 4 new-artist tracks when you return the full 12...
+ 6. ...target: ≥ 3 new-artist tracks when you return the full 7...
```

**Source:** `prompts/track_select_system.txt:15,20` interpolates
`{batch_size}` and `{min_new_artists}` directly into the SYSTEM prompt.
The harness shrinks `batch_size` per batch as the playlist fills (12 → 7
→ smaller). Result:

- The system prompt prefix **changes every batch** (2-4 byte difference).
- OpenAI's auto-prompt-cache requires byte-identical prefixes ≥ 1024 tokens.
- Even with C4's `prompt_cache_key` correctly routing to the same host,
  **the first batch can never hit and middle batches often miss** because
  the prefix shifts.

This is the **single largest** explanation for why C4's effect was
"inconclusive at n=6" in the 2026-05-10 validation. C4 fixes routing;
it cannot fix prefix instability.

**Recommended fix (one prompt edit + one helper):** Move `{batch_size}`
and `{min_new_artists}` from `track_select_system.txt` into
`track_select_user.txt` (which is already per-batch dynamic — line 7
has `Suggest UP TO {batch_size} tracks.`). The system prompt becomes
truly invariant; the cache prefix stabilises; cache hits become
deterministic on every batch after the first.

Estimated cache-hit-rate uplift: from current ~25-50% per-iter
(0% on most non-trailing batches) to ~75-85% per-iter (only batch 1
misses). At ~$0.075/playlist with mini, this saves ~$0.02-0.03/playlist
on the largest cost line. On gpt-5.4 (~$0.25/playlist if it actually
ran) the saving would be closer to ~$0.08/playlist.

### 4. 🟠 R1 mini-collapse hypothesis — REPRODUCED (loosely, n=6)

n=6 mini observations on `default`:

| iter | A (target 15) | B (target 15) |
|---|---:|---:|
| labelled gpt-5.4 i1 | 8 | 4 |
| labelled gpt-5.4 i2 | 14 | 2 |
| labelled gpt-5.4 i3 | 9 | 1 |
| labelled mini i1 | 13 | **— (empty)** |
| labelled mini i2 | 11 | 3 |
| labelled mini i3 | 11 | 2 |

- Playlist A mean: **11.0** (range 8-14, σ ≈ 2.3) — 73% completion of 15-track target.
- Playlist B mean: **2.4** (over 5 non-empty; one fully empty) — **16% completion**.
- The **B-collapse is real, severe, and consistent** under mini in `fast` mode:
  - Best B run: 4 tracks (27%).
  - Worst: empty (no tracks survived dedup).
  - Compares with 2026-05-10 validation's mini-B mean of 6.3 (which was
    also mini-on-mini under the same Tier-0 bug). Variance between sessions
    is huge — but the *failure mode itself* (post-feedback collapse) is
    stable across both runs.

**Interpretation for R1:** the load-bearing observation that mini
struggles on Playlist B once feedback applies is **not n=3 noise** — it
reproduces across two independent sessions (n=6 + n=6). R1's prompt
engineering / data-prep work has a real target to optimise against.

What we **still cannot say** because of the Tier-0 bug: how big the
gpt-5.4-vs-mini gap actually is on Playlist B. Until the Tier-0 fix
ships and a clean comparative eval lands, the L5 default-flip decision
(escalate to gpt-5.4 on Playlist B) is **uncalibrated**.

### 5. 🟢 No quality-gate regression from C1-C4

All 12 playlists (6 × A + 6 × B): leakage **pass**, fit-check **pass**,
0 violations. C3 (history aggregate) and C4 (cache routing) introduce
no quality regression — confirmed for the third eval in a row.

### 6. 🟡 Cache hit rates — pattern dominated by Finding 3

| iter | per-batch hit % (8 batches A+B combined) | total cached / prompt |
|---|---|---:|
| labelled gpt-5.4 i1 | 0,79,0,75,0,71,70,69 | 8960/19330 = **46%** |
| labelled gpt-5.4 i2 | 0,70,0,0,0,67,67,66 | 7168/20917 = **34%** |
| labelled gpt-5.4 i3 | 0,80,0,76,0,75,74,71 | 8960/18702 = **48%** |
| labelled mini i1 | 0,72,0,0,0,70,69,69 | 7168/20413 = **35%** |
| labelled mini i2 | 75,71,70,0,0,69,66,65 | 10752/20647 = **52%** |
| labelled mini i3 | 0,0,0,0,0,68,65,65 | 5376/21454 = **25%** |

- Mean total hit rate: **40%** over 6 mini-runs.
- B1 baseline (2026-05-08, also mini-on-mini under the bug): **~30%**.
- 2026-05-10 validation (also mini-on-mini): comparable.
- **Modest improvement attributable to C4** (~10 pp), but Finding 3
  caps it. After the system-prompt fix, expect ~75-85% sustained.

The first batch always misses (cold prefix), and the middle batches that
miss are precisely those where `batch_size` has changed from the previous
call (e.g. mini-iter3 batches 1-5 all miss because the prefix shifted
4 times in a row). Batches 6-8 all hit because the playlist has nearly
filled and `batch_size` settles.

---

## Per-iter rollup

| iter (label) | actual model | mode | A | B | A status | B status | reported $ | actual $ (mini-priced) |
|---|---|---|---:|---:|---|---|---:|---:|
| gpt-5.4 i1 | gpt-5.4-mini | fast | 8 | 4 | under | under | $0.247 | ~$0.075 |
| gpt-5.4 i2 | gpt-5.4-mini | fast | 14 | 2 | under | under | $0.249 | ~$0.075 |
| gpt-5.4 i3 | gpt-5.4-mini | fast | 9 | 1 | under | under | $0.238 | ~$0.072 |
| mini i1 | gpt-5.4-mini | fast | 13 | — | under | empty | $0.069 | $0.069 |
| mini i2 | gpt-5.4-mini | fast | 11 | 3 | under | under | $0.082 | $0.082 |
| mini i3 | gpt-5.4-mini | fast | 11 | 2 | under | under | $0.085 | $0.085 |

**Reported $** uses the *labelled* model's per-token rate against the
*actual* token usage — over-estimates for the gpt-5.4 rows by ~3.3×.
**Actual $** is the corrected estimate using mini's rate.

Real total spend on this eval: **~$0.46** (not $0.81 as the report
suggests). Cost tracking is broken for the same reason as the rest of
the data — it trusts the labelled model.

---

## Recommended next actions (in order)

### Immediate (gates everything else)

1. **🔴 Fix Tier-0 bug v2 — `STAGE3_MODE` clobber.** Two-line change:
   either monkey-patch `get_stage3_mode` for the eval, or skip
   `STAGE3_MODE` when its file value is empty in `config.init_config`.
   Add a startup assertion in `run_evaluation.py` that fails fast if
   `get_stage3_mode() != "custom"` after harness import. This must ship
   before any further comparative eval is run.
2. **🔴 Move `{batch_size}` / `{min_new_artists}` from
   `prompts/track_select_system.txt` into `prompts/track_select_user.txt`.**
   Single-file prompt edit. Verify with one mini-only smoke run that
   `system_md5` collapses to a single value across all batches in an iter.

### Once 1+2 ship — re-run this same scope

3. Re-run the `default × {mini, gpt-5.4} × 3 iter` matrix with both
   fixes in place. Expected outcomes:
   - `stage3_mode='custom'` everywhere; `model='gpt-5.4-mini'` on mini
     iters and `model='gpt-5.4'` on gpt-5.4 iters in `trace_*.json`.
   - `system_md5` is single-valued per (model, language, emerging_only)
     triple across all 8 batches × 3 iters.
   - Cache hit rate jumps to ~75-85% on every iter after the first.
   - **Real** mini-vs-gpt-5.4 quality gap on Playlist B finally measurable.

### After re-run lands clean

4. **R1 prompt-engineering spike** can finally start with a real
   measurement baseline. The B-collapse target is reproducible (Finding
   4); R1's verification protocol (n≥5 per variant) becomes meaningful.
5. **Re-evaluate C1 default-flip.** If the cache fix knocks
   gpt-5.4 cost down ~30%, the $0.10/playlist ceiling on Auto becomes
   reachable without R1, and the default flip from `fast` to `auto`
   may ship sooner.

### Do NOT do until 1+2 ship

- Any cross-model comparison.
- Any cost optimisation downstream of Stage 3 (everything's mis-attributed).
- Any R1 prompt experiment (the mini-collapse magnitude is correct, but
  the gpt-5.4 *baseline* it's optimising toward isn't measured yet).

---

## Operational notes

- **Spotify token survived the run** (65 min wall vs 60 min nominal TTL).
  Last iter started at minute 62 and completed cleanly. The known
  follow-up "Spotify auth refresh in eval" is still open but didn't bite
  this time.
- **No 429s, no Retry-After.** Cooldown stack (10 min between runs +
  serial search + 1.5s per-call) is working as designed.
- **All 6 cleanups OK.** Sandbox + test playlists deleted.

