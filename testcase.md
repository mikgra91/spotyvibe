# Testcase — Manual quality eval against real local profiles

**Created:** 2026-05-23
**Owner:** user runs the testcases manually; Claude analyses the resulting trace bundles.
**Why this exists:** the synthetic eval scenarios produced 96.8% / 93.8% Spotify-found rates and 15/15 fill in 4 batches, yet the user reports that on the real production profile in `%LOCALAPPDATA%\spotyvibe` "after 7 batches we could still not fill 30 suggestions." This testcase ships two deliberately-shaped profiles + explicit pass criteria so the eval-vs-prod gap becomes diagnosable, not just complained-about.

---

## 0. Preconditions — do this ONCE before any test

> **The test data is worthless if these aren't followed.** Each step is a hard gate.

### 0.1 Settings
Set in the app (Settings modal) AND verify the values in `%LOCALAPPDATA%\spotyvibe\settings.conf`:

| Setting | Required value | Why |
|---|---|---|
| `DEBUG_MODE` | `true` | Enables `trace.json` per-run bundles. Without this, the diagnostic data Claude needs DOES NOT EXIST. |
| `PLAYLIST_SIZE` | `30` | Matches the user's reported failure (7 batches couldn't fill 30). |
| `RAG_ENABLED` | `true` | Production path. Disable for a control run only. |
| `PROVIDER_PRESET` | whatever you actually use | Document which provider you tested. Provider quirks may matter. |
| `OPENAI_MODEL` | whatever you actually use | Document which model. Model is the #1 variable in our quality numbers. |

After saving the settings, **restart the app** so config reloads cleanly.

### 0.2 Clean the logs
Delete or move aside the following so the test data is uncontaminated:

```
%LOCALAPPDATA%\spotyvibe\debug.log            ← delete or rename
%LOCALAPPDATA%\spotyvibe\eval.jsonl           ← delete or rename
%LOCALAPPDATA%\spotyvibe\perf_log.sqlite      ← delete or rename
%LOCALAPPDATA%\spotyvibe\debug\               ← DELETE THE WHOLE FOLDER
```

The `debug\` folder is where `trace.json` files land — one subfolder per run. After each test run, the folder you need is named after the `run_id` of THAT run; if old runs are still in there, please tell Claude which subfolders correspond to which testcase (timestamp on the folder is the easiest cue).

### 0.3 Spotify
Make sure you are connected to Spotify in the app (Settings → Spotify Connect). Without OAuth, Stage 3 picks cannot be verified and the run dies with `error.run.no_tracks_verified` — that's not the failure mode we're testing.

### 0.4 Network
Use a reliable connection. A 429 from OpenRouter or a transient Spotify failure looks like a quality failure in the trace; we want to be sure we're measuring the recommender, not the network.

---

## 1. Test profiles — what they are and what they prove

Two new profile folders have been written into `%LOCALAPPDATA%\spotyvibe\profiles\`:

| Profile dir UUID | `name` field | Archetype | Stresses |
|---|---|---|---|
| `f583bcf6-d7e6-4e63-a78e-9c85a57b8e05` | `TC-A_niche_japanese_rock` | **Niche genre starvation** | Narrow regional/language constraint (Japanese rock/metal). Mirrors the user-reported failure pattern. Tests whether the RAG corpus + Stage 1 retrieval can find 30 unique Spotify-resolvable tracks within ≤ 4 batches when the must-have is a regional language + a non-mainstream subgenre. |
| `0fe0e591-4eb8-49bb-97a8-2f22ba559169` | `TC-B_mainstream_rock_control` | **Mainstream rock CONTROL** | Broad western rock with deep corpus coverage (Foo Fighters / Pearl Jam / Green Day seeds). Should fill easily. **This is the baseline.** If TC-B also fails, the bug is system-wide (Stage 3 / Spotify verify / batch loop); if only TC-A fails, the bug is corpus/retrieval coverage for niche genres. |

**Important:** Claude has NOT touched your existing profile folders:
- `0593bce6-9265-4761-9016-1ce1777b4890` (your `japanese_theatrical`)
- `0d98de30-e93f-424b-916b-d1ab2e51619d`
- `e57dace0-63bc-429e-ad35-7e1c0e4413c3`
- `eea2867b-16fb-4785-9572-9d009db17780`

These are untouched. The two new ones are additive.

---

## 2. The testcases

For each testcase: switch the active profile in the app, do the steps in order, capture the data described in §3, then move on.

### TC-A — Niche genre starvation (the user's reported failure)

**Active profile:** `TC-A_niche_japanese_rock` (UUID `f583bcf6-…`).

**Setup once per test:** before running, manually re-import the profile JSON via the app's import-profile flow (or restart the app after switching active-profile-id) so the profile is in a clean state with `history.suggested_tracks = []` and `feedback.disliked_tracks = []`. Without this, dedupe state from a prior run will distort the result.

**Steps:**

1. Set active profile to TC-A.
2. Trigger a normal "Generate" run with `PLAYLIST_SIZE=30`. Do NOT touch the exploration slider — leave at default.
3. Wait for the run to finish (success, partial fill, or error).
4. **Do not** click "Use X tracks now" — that creates a Spotify playlist and is irrelevant to diagnosis.
5. Record what you saw (see §3 "What to report").

**Pass criteria (each is binary — yes/no):**

| ID | Criterion | Pass = |
|---|---|---|
| A.1 | Playlist filled to 30 tracks. | `verified_tracks == 30` at the end. |
| A.2 | Filled in ≤ 4 batches. | `batches_run ≤ 4`. |
| A.3 | No disliked or rejected artist appeared. | (Profile has none — gate vacuous; will matter on TC-A2 below.) |
| A.4 | Spotify-found rate ≥ 60 % across all batches. | `sum(spotify_found) / sum(stage3_returned) ≥ 0.60`. |
| A.5 | No artist appears more than 2 times in the final playlist. | Code enforces this; just check the playlist visually. |
| A.6 | At least 80 % of artists in the final playlist are actually Japanese / Japanese-language. | Manual check — open Spotify, glance at each artist. Note any that are clearly NOT Japanese (e.g. a German metal band slipped in). |

**Expected failure modes (what to look for):**

- **Pool starvation:** trace `run_pool_initial.stage2_approved_size` is small (< 15 artists). Stage 3 then exhausts the pool by batch 2-3, every subsequent batch is filtered to empty, and `run_exit.reason == "gpt_exhausted"`.
- **Confabulation:** trace `run_batches[*].hc2_violations` is non-empty — Stage 3 invented artists outside the approved pool.
- **Spotify miss cascade:** `run_batches[*].spotify_not_found` is consistently > 50 % of picks — Stage 3 picks tracks the corpus says exist but Spotify doesn't.
- **Loss to dedupe:** by batch 4+, `run_batches[*].filter_dropped` is dominated by `reason: "already_suggested_or_disliked_track"` — pool effectively exhausted.

### TC-A2 — Niche genre + already-dirty profile (run AFTER TC-A)

**Active profile:** TC-A (same one). **Do NOT re-import / reset.**

After TC-A runs once, the profile has 30 or fewer `history.suggested_tracks` entries from the first generation. Now:

**Steps:**

1. In the UI, dislike at least 3 tracks from the first run's result (any 3 — Claude does NOT need to know which).
2. Reject at least 1 artist from the first run (use the "block artist" / equivalent UI).
3. Trigger a second "Generate" run with `PLAYLIST_SIZE=30`.
4. Record the result.

**Pass criteria:**

| ID | Criterion | Pass = |
|---|---|---|
| A2.1 | Playlist filled to 30. | `verified_tracks == 30`. |
| A2.2 | No disliked track re-appears. | None of the disliked tracks from step 1 appear in the new playlist. |
| A2.3 | No rejected artist re-appears. | The rejected artist from step 2 contributes zero tracks. |
| A2.4 | Filled in ≤ 5 batches. | `batches_run ≤ 5` (slightly higher tolerance because the dedupe set is larger). |

**This test isolates the dedupe / feedback-loop quality** — the classic "evals pass while production fails" pattern flagged in CLAUDE.md, where the synthetic eval doesn't simulate post-feedback regeneration on the same profile.

### TC-B — Mainstream rock CONTROL

**Active profile:** `TC-B_mainstream_rock_control` (UUID `0fe0e591-…`).

**Setup:** ensure clean state (see TC-A setup note).

**Steps:**

1. Switch active profile to TC-B.
2. Generate with `PLAYLIST_SIZE=30`. Default slider.
3. Record.

**Pass criteria (these are TIGHT — this profile is well within the corpus' sweet spot):**

| ID | Criterion | Pass = |
|---|---|---|
| B.1 | Playlist filled to 30. | `verified_tracks == 30`. |
| B.2 | Filled in ≤ 3 batches. | `batches_run ≤ 3`. |
| B.3 | Spotify-found rate ≥ 85 %. | `sum(spotify_found) / sum(stage3_returned) ≥ 0.85`. |
| B.4 | No artist >2 times. | Code enforced. |
| B.5 | All artists are recognisably rock / alt-rock acts (no jazz, no rap, no country). | Manual glance. |

**If TC-B fails (any of B.1-B.3), the bug is system-wide and not corpus-coverage related.** That's the most important single data point this whole testcase produces.

### TC-B2 — Mainstream rock + emerging-only

**Active profile:** TC-B (same one). **Reset first** so this is a fresh-state run.

**Steps:**

1. Reset TC-B profile state.
2. **Turn the exploration slider all the way to "emerging only"** (or whatever the UI calls the most-niche end).
3. Generate with `PLAYLIST_SIZE=30`.
4. Record.

**Pass criteria:**

| ID | Criterion | Pass = |
|---|---|---|
| B2.1 | Playlist filled to ≥ 20 tracks. | Lower bar than B.1 — emerging-only filters out the long-tail majority. |
| B2.2 | At least 80 % of returned tracks are by artists you don't recognise from the top-40. | Manual judgement. Indicates emerging-only is doing its job. |
| B2.3 | No "Foo Fighters" / "Pearl Jam" / "Green Day" / "The Killers" tracks in the result. | The seed artists themselves should be filtered out as "not emerging." |

---

## 3. What to report back to Claude

For each testcase (TC-A, TC-A2, TC-B, TC-B2), write a short report with:

### 3.1 The headline numbers
```
TC-A:  verified=__/30,  batches=__,  exit_reason=__
TC-A2: verified=__/30,  batches=__,  exit_reason=__,  disliked_track_appeared=Y/N,  rejected_artist_appeared=Y/N
TC-B:  verified=__/30,  batches=__,  exit_reason=__
TC-B2: verified=__/30,  batches=__,  exit_reason=__
```

### 3.2 The trace bundle paths
Each run writes `%LOCALAPPDATA%\spotyvibe\debug\<run_id>\trace.json`. After all 4 testcases, you should have at least 4 `<run_id>` subfolders (more if you re-ran any). **Tell Claude the `run_id` of each testcase**, e.g.:

```
TC-A:  run_id = <copy from the folder name>
TC-A2: run_id = <copy from the folder name>
TC-B:  run_id = <copy from the folder name>
TC-B2: run_id = <copy from the folder name>
```

Sort the `debug\` folder by Date Modified; the timestamps should match the order you ran them.

### 3.3 Subjective notes
- Anything that looked weird (UI hangs, error toasts, unexpected message in the progress log).
- Any time you had to retry because of a network blip — flag the affected `run_id` so Claude can ignore it.
- For TC-A and TC-A2: **list any non-Japanese artists** that appeared in the playlist. Don't have to be exhaustive — even one example is useful.
- For TC-B: **list anything that isn't recognisably rock/alt-rock.** Same — one example is enough.

### 3.4 (Optional but high-value) full debug log
`%LOCALAPPDATA%\spotyvibe\debug.log` — attach the whole thing, or paste the last ~500 lines. Cross-references with the trace bundle to fill in any gaps the trace doesn't capture (HC violation INFO logs, Stage 1 retrieval meta, etc.).

---

## 4. What logging was added for this testcase

So the analysis later actually has the data it needs, the following per-run trace sections were added (only emit when `DEBUG_MODE=true`):

| Trace key | What it captures | Why |
|---|---|---|
| `run_pool_initial` | Stage 1 size, Stage 2 approved size, the approved artist names, top-tracks coverage, avoid traits, primary reference. | Lets the post-mortem answer "did the pool have enough material before the loop even started?" |
| `run_batches[*]` (`outcome: verified`) | Per-batch: requested count, Stage 3 raw picks (before HC), HC1/HC2 violations, filter dropouts WITH REASON (`already_suggested_or_disliked_track`, `exhausted_artist`, `rejected_or_disliked_artist`, `duplicate_in_batch`, `max_2_per_artist_exceeded`), Spotify found/not-found, verified total after, temperature, effective new-artist %. | Walks the batch loop step-by-step. Diagnoses pool starvation vs. confabulation vs. Spotify cascade. |
| `run_batches[*]` (`outcome: empty_after_filter`) | Same shape as `verified` but for batches where every Stage 3 pick was filtered out. | Diagnoses dedup-driven exhaustion. |
| `run_exit` | Why the loop stopped: `target_hit` / `gpt_exhausted` / `cancelled` / `max_calls_reached`, plus batches_run, fill_ratio, whether A6 re-retrieve fired. | Single source of truth for "what stopped this run." |
| `stage3_batches[*]` *(existed before)* | Stage 3 system + user prompts, raw response, latency, usage tokens, temperature. | Already captured. Unchanged. |
| `stage1_candidates`, `stage1_query`, `stage2_prompt/response` *(existed before)* | Stage 1 + 2 inputs and outputs. | Already captured. Unchanged. |

Also: `filter_duplicate_suggestions` now tags each dropped item with a `reason` field so the trace can group losses by cause. This was a code change in `core/src/suggestions.py`.

---

## 5. After the user reports back — Claude's analysis plan

This section is for Claude, but the user can read it to know what's coming.

For each testcase:
1. Open the trace bundle for that run_id.
2. Read `run_pool_initial.stage2_approved_size`. If < `PLAYLIST_SIZE * 1.5`, the run was doomed before batch 1 — Stage 1 / corpus failure.
3. Walk `run_batches[*]`. For each batch:
   - `stage3_returned == 0` and HC violations present → Stage 3 hallucinating outside the pool (model issue).
   - `spotify_not_found / stage3_returned > 0.5` → Spotify-verify cascade (corpus has unresolvable titles).
   - `filter_dropped` dominated by `already_suggested_or_disliked_track` → pool depleted.
   - `filter_dropped` dominated by `exhausted_artist` → 2-per-artist cap hitting (need more unique artists).
4. Read `run_exit.reason`. Cross-reference with the verified count.
5. Compare TC-A vs TC-B side-by-side. Same model, same Spotify, same code — different result = corpus/retrieval coverage. Same poor result on both = system-wide.
6. File the diagnosis as an update to [`evaluation/model-performance-result.md`](evaluation/model-performance-result.md). If the synthetic eval should have caught the failure, file a new scenario that does — anonymise the failing profile into a `seed_profile_path` fixture.

The end goal: stop the eval from lying. Either the synthetic scenarios pick up these failure modes, or they get retired as misleading. The user's quality complaint is the only ground truth that matters.
