# Evaluation history — fix ↔ result map

## 2026-05-16 — Top-tracks source switched from Spotify to Last.fm

**Root cause finding (2026-05-15):** verify_mode=spotify under-fill was caused by an empty `top_tracks` field on every corpus row (RAG corpus had 0/174k populated). Stage 3 prompts told models "known tracks: (no examples available)" for every approved artist, so DS / Llama / mini all correctly refused to confabulate.

**Diagnostic fix (2026-05-15):** 213-artist overlay built from eval traces → DS default re-ran clean at 30/30 tracks, 100 % Spotify-found, 90-100 % cite. Confirmed root cause.

**Production fix attempted (2026-05-15 → 2026-05-16):**
1. Hardened SpotifyClient (adaptive throttle, daily-budget abort, smoke pre-flight).
2. Built separate `spotivibe-rag-enricher` Cloud Run job (split from monolithic builder).
3. Both old + new Spotify credentials hit the same ~700-1000 call/day ceiling before a 24 h ban — **proved Spotify Dev Mode is structurally incompatible with bulk enrichment** (escalation system also correlates at developer-account level, not just client_id).

**Final fix (2026-05-16):** Top-tracks source switched to Last.fm. Adds `artist.getTopTracks` to existing Last.fm Phase B; same enricher, one extra API call per artist. Local smoke confirmed real playcount-ranked titles matching Spotify catalog (Radiohead → Creep, Beatles → Here Comes the Sun, etc.). Spotify enricher job + image deleted; Spotify env stripped from builder. Spotify Secret Manager retained for user-facing app + eval verify path.

---



> **Purpose.** Chronological record of every prompt / pipeline / config fix
> tested against the evaluation harness or the Track B probe battery,
> with the headline metric impact for each. Use this file when asking
> "which change produced which delta?" before re-running an expensive
> eval. Generated 2026-05-13.
>
> **Sources.** `evaluation/baselines/*/summary.md` (full evals),
> `evaluation/probes/fingerprints/*.v1.json` (probe cards),
> `next-steps.md` change log.
>
> **Cost convention.** `~$N` = real OpenAI billing in the run.
> Spotify quota cost is operational (rate-limit risk), not dollar cost.
>
> **Validity flags.** Runs marked ⚠️ INVALID have a known-bad Tier-0 /
> Tier-1 issue documented in the source `summary.md`; their numbers
> should not be used for cross-model design decisions but the
> mini-on-mini deltas may still be informative.

---

## Headline timeline

| Date | Fix / Change | Mini A | Mini B | Mini cite | GPT-5.4 A | GPT-5.4 B | GPT-5.4 cite | Run cost | Validity |
|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| 2026-05-08 | B1 baseline (Stage 3 downgrade probe; production defaults) | 14.3 | 3.7 | — | 11.0 | 8.3 | — | ~$0.40 | ✅ |
| 2026-05-10 | C1-C4 cost levers (post B1) | 13.7 | 6.3* | — | 11.0* | 4.7* | — | — | ⚠️ INVALID — STAGE3_MODE bug; rows are mini-on-mini |
| 2026-05-11 06:04 | Tier-1 logging (`system_fingerprint`, `prompt_hashes`, `stage3_mode`) added | — | — | — | — | — | — | ~$0.81 | ⚠️ INVALID — Tier-0 bug v2 (`load_dotenv(override=True)` defeats env override) |
| 2026-05-11 08:17 | Tier-0 v2 fix (force STAGE3_MODE post-load) + cache-prefix fix (`{batch_size}` out of system prompt) | 13.0 (87 %) | 4.3 (29 %) | 86 % | 13.7 (91 %) | 9.3 (62 %) | 96 % | ~$0.90 | ✅ FIRST valid mini-vs-gpt-5.4 since L5 shipped |
| 2026-05-11 12:06 | R1.1 (cite REMINDER at end of user msg) + R1.2 (tighter no-known rule) + R1.3-strict (force `omitted_artists ≥ N−M`) | — n=1 — | — | — | — | — | — | — | ⚠️ n=1 only; R1.2 rejected (40/40 artists omitted → 0 tracks) |
| 2026-05-12 05:29 | R1.1 + R1.3-strict (no R1.2) | **8.0 (−38 %)** | 3.0 | 85.6 % | 11.7 | **1.3 (2 of 3 EMPTY)** | 86.8 % | ~$0.62 | ✅ — strict variant **REJECTED** |
| 2026-05-12 06:34 | R1.1 + R1.3-softened (transparency hint, no quota) | 12.0 (parity, one 15/15 perfect) | 3.7 | 81.5 % | not re-run | — | — | ~$0.48 | ✅ — shipped variant |
| 2026-05-12 ~07 | B-1…B-11 v1 probe fingerprints captured (3 models × 8 probes) | n/a (probe) | n/a | n/a | n/a | n/a | n/a | ~$0.11 total | ✅ — see `evaluation/probes/fingerprints/*.v1.json` |
| 2026-05-13 | **N1 — A6 pool-starvation refusal gate** in `select_tracks` (code, NOT prompt) | — | — | — | — | — | — | (no eval cost) | ✅ — unit + probe smoke: no probe-path regression |
| 2026-05-13 | **N2 — `iterations` 3 → 5 default + `--iterations` CLI override** | — | — | — | — | — | — | (no eval cost) | ✅ — config-only |
| 2026-05-13 | Probe smoke (post-N1+N2) — gpt-5.4-mini full battery | n/a | n/a | n/a | n/a | n/a | n/a | $0.004 | ✅ — 0 true regressions; 2 noise-flags (B-1 soft −0.125 single-run, B-6 n_required 85 → 97 ±tolerance); **2 IMPROVED** (B-1 `quota_preserved_under_hard` 0.0 → 1.0 ✨, B-1 `secondary_quota_met` 0.0 → 1.0) |
| 2026-05-13 | Probe smoke (post-N1+N2) — gpt-5.4 full battery | — | — | — | — | — | — | $0.061 | ✅ — **0 regressions**, n_required improved 19 → 13 |
| 2026-05-13 | **N3a — `prepare_sandbox(require_spotify_cache=False)`** + harness wires it on non-spotify verify modes | n/a | n/a | n/a | n/a | n/a | n/a | (no eval cost) | ✅ — 4 new tests; unblocks probe-style evals on machines without Spotify OAuth |
| 2026-05-13 | **N3b — `app.py /api/run` env-var seam** (`SPOTYVIBE_SKIP_SPOTIFY_CONNECT=1`) | n/a | n/a | n/a | n/a | n/a | n/a | (no eval cost) | ✅ — 2 new tests; harness sets it automatically when `--verify-mode != spotify` |
| 2026-05-13 | **N3c — `iter_search_tracks` verifier-precedence bug-fix** in `core/src/playlist.py` | n/a | n/a | n/a | n/a | n/a | n/a | (no eval cost) | ✅ — 2 regression tests. The Track-A verifier swap was dead code: token-fetch ran BEFORE the `_VERIFIER` check, so a missing Spotify cache + `--verify-mode null` returned `not_found` for every track instead of routing through `NullVerifier` |
| 2026-05-13 | **starved_pool_a6 synthetic scenario** (`evaluation/scenario.py`) | n/a | n/a | n/a | n/a | n/a | n/a | (no eval cost) | ✅ — registered in `SCENARIOS`; `verify_mode="null"` default; 1 contract-test exemption added |
| 2026-05-13 | **starved_pool_a6 run** — mini, n=1, `--verify-mode null` (FIRST cache-less eval on this machine) | 1 (under) | empty | 100 % | — | — | — | $0.058 | ✅ — Pipeline ran. A6 did **NOT** fire (pool was 29-31 artists, never ≤ 1). Surfaced **HC2 confab pattern**: model repeatedly picked "dalriada", "sear bliss", "aetherius obscuritas" (real Hungarian-language metal acts) **outside** the approved pool — 4 HC2 violations dropped 13 picks total. Scenario design exercises out-of-pool confabulation, not pool-starvation. |

\* Asterisked rows come from a run with a known Tier-0 invalidation.

---

## Per-fix detail

### B1 baseline — 2026-05-08 (`2026-05-08_b1_stage3_downgrade/`)
**What shipped.** Stage 3 downgrade probe — production defaults, no
prompt changes. Snapshot before any L5 / Tier-1 work.

**Result.** Established the canonical mini-vs-gpt-5.4 split:
- mini wins Playlist A (14.3 vs 11.0), wall clock (~½), and cost
  (~10× cheaper at $0.01 vs $0.10 / cycle).
- gpt-5.4 wins Playlist B (8.3 vs 3.7) — the "mini collapses on
  post-feedback regeneration" finding.
- niche_only_strict aborted by Spotify 429 cascade (Retry-After ≈ 14 h).

**Carried forward.** Mini's B-collapse hypothesis (later confirmed at
n=3 in 2026-05-11_post_fix_validation; A3 niche-bias fix and L5
two-tier Stage 3 designed off this data).

---

### Tier-0 v2 + cache-prefix fix — 2026-05-11 (`2026-05-11_post_fix_validation/`)
**What shipped.** Two fixes:
1. `STAGE3_MODE` env-override now survives `config.init_config()`'s
   `load_dotenv(override=True)` reset.
2. `{batch_size}` moved out of the system prompt into a per-request
   user-message prepend → system prompt is now invariant per
   `(model, language)` so OpenAI's prompt-prefix cache lands.

**Result (n=3 each model, scenario=default).**

| metric | gpt-5.4-mini | gpt-5.4 | gap |
|---|---:|---:|---:|
| Playlist A | 13.0 (87 %) | 13.7 (91 %) | +0.7 |
| Playlist B | 4.3 (29 %) | 9.3 (62 %) | +5.0 (+33 pp) |
| must-have cite | 86 % (range 24 pp) | 96 % (range 4 pp) | +10 pp |
| Spotify-found | 40 % | 68 % | +28 pp |
| cost / run | $0.079 | $0.219 | +178 % |
| wall / run | 66 s | 95 s | +44 % |

**Verdict.** First valid cross-model comparison since L5 shipped.
Reproduces B1 within iteration variance. Mini-B-collapse confirmed
at n=3. System prompt now stable (1 unique md5 across 48 batches, was 5).

---

### R1 prompt spike — 2026-05-12 (`2026-05-12_r1_full/`)

Three sub-changes tested independently:

| ID | Change | Verdict |
|---|---|---|
| **R1.1** | Cite-rule re-stated as a `REMINDER` block at the END of the user message | ✅ KEPT — cite parity (81.5 % vs 86 % baseline; within variance) |
| **R1.2** | Tightened no-known rule from "OMIT … unless you are sure" to "OMIT — Do NOT attempt to recall" | 🛑 REJECTED — n=1 trial omitted 40/40 artists → 0 tracks |
| **R1.3-strict** | Force `omitted_artists ≥ N − M` quota | 🛑 REJECTED — mini A −38 %, gpt-5.4 B: **2 of 3 EMPTY** (unprecedented) |
| **R1.3-softened** | Same idea reframed as a transparency hint, explicit "do NOT pad" + "Prefer FILLING the playlist over inflating omitted_artists" | ✅ SHIPPED — mini A=12.0 (parity), one 15/15 perfect playlist |

**Key insight.** mini does not compensate for B-pool thinning after
dislikes prune the candidate set — the structural fix for B-collapse
is **A6 (RAG re-retrieve on consecutive empty Stage-3 batches)**,
not more prompt-engineering.

---

### Track B v1 fingerprints — 2026-05-12 (`evaluation/probes/fingerprints/`)
**What shipped.** 8-probe battery (B-1 constraint, B-2 over-constraint,
B-3 confabulation, B-4 omission, B-5 format, B-6 self-consistency,
B-10 cite, B-11 empty-pool) captured against gpt-4.1, gpt-5.4,
gpt-5.4-mini.

**Two structural findings that directly motivated N1 + N2:**

1. **B-1 `quota_preserved_under_hard`:** mini = 0.0 vs gpt-5.4 / gpt-4.1 = 1.0
   — retroactively predicts R1.3-strict's collapse on mini.
2. **B-11 `single_artist_no_known`:** **bucket_c (confabulates) on ALL
   THREE models** — directly motivated widening A6 to
   `len(approved_artists) <= 1 AND no known: tracks`.
3. **B-6 `n_required_for_5pp_signal`:** gpt-4.1=5, gpt-5.4=19,
   gpt-5.4-mini=85 — exposed the static `iterations=3` as below every
   model's variance floor (motivates N2).

**Cost.** ~$0.11 total — replaced what would have been a multi-$ full
eval, demonstrating the value of the probe-first workflow.

---

### N1 — A6 pool-starvation refusal — 2026-05-13
**What shipped.** Early refusal gate at the top of `core/src/suggestions.py::select_tracks()`. When `len(approved_artists) == 0` OR
`len(approved_artists) == 1 AND zero known: tracks anywhere in the
overlay`, the function returns the standard empty result + meta with
`refusal_reason ∈ {"empty_pool", "single_artist_no_known"}` **without
calling the LLM**. Logged at WARNING.

**Why.** B-11 v1 fingerprints showed every model confabulates at the
single-artist-no-known boundary; the system prompt's "OMIT that
artist unless you are sure" rule is unreliable there. Better to skip
the call and let `app.py`'s `consecutive_empty_batches` counter
handle retry / abort.

**Validation.** Unit-level only (5 new tests in
`TestSelectTracksA6PoolStarvationRefusal` + 5 existing single-artist
tests updated). Probe path is bypassed (B-11 calls the LLM directly
and so does not exercise `select_tracks`); the post-fix probe smoke
on gpt-5.4-mini and gpt-5.4 confirms no incidental regression.

**Result.** 1037 core tests green (was 1032 pre-N1). Production impact
only visible on starved-pool scenarios — not part of any current
eval scenario.

**Pending validation.** A scenario where Stage 1 + Stage 2 leave
`len(approved) <= 1` (e.g. a contradictory profile that prunes the
pool to 1 candidate) would let us measure the in-pipeline impact.
None of the canonical scenarios reliably reach that boundary; would
need a dedicated synthetic scenario (~$0.05 to build + measure).

---

### N2 — `iterations` 3 → 5 default + `--iterations` override — 2026-05-13
**What shipped.**
- `evaluation/settings.ini` and `settings.ini.example`: default
  iterations bumped from 3 → 5 (clears gpt-4.1's variance floor).
- `evaluation/run_evaluation.py`: new `--iterations <n>` CLI flag
  overrides the static default for a single run.
- `evaluation/README.md`: per-model recommendation table sourced from
  the v1 fingerprints (gpt-4.1=5, gpt-5.4=19, gpt-5.4-mini=85) + the
  "re-run B-6 to refresh" pointer.

**Why.** B-6 `n_required_for_5pp_signal` showed every model's
run-to-run variance is well above the previous default of 3, so any
prompt A/B delta < 5 pp was indistinguishable from noise.

**Option (b) deferred** (auto-scale iterations per model by reading
fingerprint): would push mini runs to 85× = ~$8.50 per scenario.
The manual override delivers the same control without locking the
cost in by default.

**Result.** 1037 core tests green. No probe-path regression (full
battery on gpt-5.4-mini + gpt-5.4 verified 2026-05-13).

---

### N3a — `prepare_sandbox` conditional `.spotify-cache` requirement — 2026-05-13
**What shipped.**
- `evaluation/harness.py::prepare_sandbox()` gained
  `require_spotify_cache: bool = True` kwarg. When True (default,
  back-compat), missing cache still raises `RuntimeError`. When
  False, missing cache is logged as a WARNING and sandbox setup
  proceeds.
- `evaluation/run_evaluation.py` computes
  `_needs_spotify = any(s.verify_mode == "spotify" for s in
  active_scenarios)` and passes that to `prepare_sandbox`. Also
  guards the 429 pre-flight on the same flag — no Spotify calls = no
  429 risk worth paying a pre-flight for.
- 4 new tests in
  `TestPrepareSandboxRequireSpotifyCache` (cache-missing+require-True
  raises, cache-missing+require-False logs+proceeds, cache-present
  copies regardless, default keeps require-True).

**Why.** The OP2 issue ("Spotify cache disappears between sessions")
recurred during this session — the cache was present at session
start, gone by the time the first eval kicked off (3rd confirmed
occurrence). Without this fix, every null/overlay eval is gated on a
live Spotify OAuth even though the actual verification path doesn't
need it.

---

### N3b — `app.py /api/run` Spotify-connect env-var seam — 2026-05-13
**What shipped.**
- `app.py::run_pipeline()` now checks
  `SPOTYVIBE_SKIP_SPOTIFY_CONNECT` (truthy values: `1`, `true`,
  `yes`) BEFORE the `spotify_status != "authenticated"` short-circuit.
  When set, the pipeline proceeds even without a live Spotify
  connection — Stage 1+2+3 + analysis still run; only the push step
  would fail (and that's already gated on `verify_mode == spotify`).
- `evaluation/run_evaluation.py` sets the env var automatically when
  no active scenario uses `verify_mode="spotify"`. Same scope as the
  prior `SPOTYVIBE_APP_DIR` / `RAG_ENABLED` / `DEBUG_MODE` env
  injections, set BEFORE `import app`.
- 2 new tests in `test_app.py::TestRunEndpoint`: the bypass DOES skip
  the connect-gate when the env var is truthy; falsy / unset values
  preserve production behaviour.

**Why.** Found while running the first cache-less null-verify eval:
sandbox setup succeeded (thanks to N3a) but the pipeline aborted
with "Spotify is not connected" before any LLM call. The env-var
seam matches the existing eval-harness pattern of passing through
side-channels rather than monkey-patching production code.

---

### N3c — `iter_search_tracks` verifier-precedence bug-fix — 2026-05-13
**What shipped (1 production code change, 2 regression tests).**
`core/src/playlist.py::iter_search_tracks()`: reorder so the
`_VERIFIER` check happens FIRST. Only fall through to the
`get_spotify_oauth() + validate_token()` branch when no alternative
verifier is installed. `shared_session` is constructed lazily and
the `finally` close-call is now guarded with `is not None`.

**Why.** Discovered while debugging why the first cache-less eval
returned 0 verified tracks despite `--verify-mode null` being active.
Trace: token lookup ran before the verifier check, yielded
`("not_found", ...)` for every track on missing token, and bypassed
the installed `NullVerifier` entirely. The Track-A abstraction was
effectively dead code under the exact conditions it was designed for
(CI / cache-less environment). This is **structurally a 2026-05-12
regression** in the verifier-swap rollout that no prior eval caught
because every prior run had a working Spotify cache.

**Regression tests.** Two pytest-level tests pin the fix:
1. `NullVerifier` installed → `get_spotify_oauth()` MUST NOT be
   called (sentinel raises `AssertionError` if touched); every track
   yields `"found"`.
2. No verifier installed + no token → production path still yields
   `"not_found"` (back-compat).

---

### starved_pool_a6 synthetic scenario — 2026-05-13
**What shipped.**
- New `STARVED_POOL_SCENARIO` in `evaluation/scenario.py`
  (registered as `starved_pool_a6`). Narrow `must_have` (Hungarian-
  language extreme metal) + broad `avoid` (English vocals, Western
  artists, mainstream metal) designed to drive Stage 1 + Stage 2 to
  an empty / single-artist approved pool so A6 has the opportunity
  to fire in-pipeline.
- `verify_mode="null"` default so the scenario is usable on a
  machine without Spotify OAuth. `test_verify_mode_defaults_to_spotify`
  in the contract suite gained an explicit exemption for this name.

**First run result (mini, n=1, `--verify-mode null`).** $0.058,
wall 23 s, status=`ok`, completion_a=`under` (1/15 tracks).
**A6 did NOT fire** — Stage 1 retrieved 41 candidates and Stage 2
approved 29-31 of them across batches, well above the
`len ≤ 1` threshold. **Instead the scenario exposed a different
production behaviour**: 4 `[HC2 VIOLATION]` events dropped 13 picks
total — the model insisted on picking real Hungarian-language metal
artists (`dalriada`, `sear bliss`, `aetherius obscuritas`,
`mrbid carnage`) that are NOT in the approved pool. HC2 enforcement
caught them all.

**Caveats / next iterations.**
- The corpus contains 174 200 artists; the Hungarian-extreme-metal
  intersection is still ~30 even under the narrowest prose this
  scenario carries. To reliably reach `len ≤ 1` we'd need either an
  even more extreme intersection (era + region + language + label
  size, etc.) or a `seed_profile_path` fixture that bypasses
  Stage 1+2 entirely.
- For deterministic A6 unit-level coverage the
  `TestSelectTracksA6PoolStarvationRefusal` suite remains
  authoritative.

**Bonus side-finding.** The repeated HC2 violations on `dalriada`
suggest a corpus-naming mismatch: the model knows the band exists
but the Stage 1 retrieval keys differ (probably accent stripping or
alias miss). Worth a future spike if HC2 violations on the same
artist persist across iterations.

---

## Open validation runs (cost-gated)

| Item | Required to validate | Estimated cost | Estimated wall |
|---|---|---:|---:|
| **N1 in-pipeline (A6 firing in production scenario)** | Tighten `starved_pool_a6` further OR build a `seed_profile_path` fixture that injects a 1-artist-no-known profile directly | ~$0.05 + dev time | ~30 min |
| **N3 Track A Step 7** — verifier drift | `--verify-mode spotify` vs `--verify-mode l0_l1` side-by-side on `default` scenario | ~$0.50 | ~90 min |
| **N3 Track B Step 5** — R1.4 probe-first | ✅ DONE 2026-05-13 — gpt-5.4 + gpt-5.4-mini probe batteries vs v1 baseline returned 0 true regressions; R1.4 (model-conditional omission rule) ships unchanged | — | — |
| **N4 Multi-scenario overlay rebuild** | `build_top_tracks_overlay.py --scenarios all --resume --throttle-ms 2000` — **BLOCKED** by OP2: `.spotify-cache` missing again as of 2026-05-13 09:15 | $0 (Spotify quota, no $) | 1-3 sessions × ~3 h |
| **~~N5~~ Local-LLM v1 fingerprint** | (User decision: skipped this session) | — | — |
| **OP2 — `.spotify-cache` disappearance** | Reproduce + locate which process is deleting the file (3rd confirmed occurrence). N3a/N3b/N3c make many evals survive the disappearance, but the root cause should still be tracked. | $0 | ~30 min spike |

---

## How to update this file

After each evaluation run or probe-battery capture:

1. Add a row to the headline timeline (date, fix label, headline metric).
2. Add a "Per-fix detail" section if the change is non-trivial (i.e. it
   warrants a paragraph of context, not just a table cell).
3. If the run **REGRESSED** any metric outside its tolerance, mark the
   verdict 🛑 REJECTED and link back to the source summary.
4. Keep the cost convention (`~$N`) — round to two significant figures.
5. Keep cells aligned (`right` for numbers, `centre` for status icons).




