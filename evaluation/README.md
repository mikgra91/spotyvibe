# Evaluation harness

End-to-end evaluation runs against real OpenAI + real Spotify, used to compare model variants (gpt-5.4, gpt-5.4-mini, gpt-4.1, gpt-4.1-mini) on cost, latency, and quality. `gpt-5.5` was removed in Phase 2.6 (2026-04-28) — see `documentation/ModelRecommendations.md`.

**Not part of the unit test suite** — never runs on `pytest`. Invoked explicitly:

```bash
python evaluation/run_evaluation.py
```

Tell the agent **"call the evaluation tests"** and it will run this script. Do not invoke it as a side effect of any other command.

## What it does

For each model in `[evaluation] models` (settings.ini):

1. Creates a fresh profile in an isolated sandbox app dir.
2. Trains the profile from the canonical seed in `scenario.py`.
3. Runs Band/Song Analysis on a fixed target.
4. Generates a 30-track playlist (Stage 1 retrieval → Stage 2 mini-LLM → Stage 3 selection → Spotify verify).
5. Pushes the result to a `[EVAL] {model} {ts}` Spotify playlist.
6. Applies a deterministic 5-likes / 3-dislikes pattern.
7. Re-runs `train_profile` to absorb the feedback.
8. **Always** deletes the Spotify playlist and the sandbox profile in a `finally` block.

The production code paths write per-feature telemetry rows to `eval.jsonl` (`batch_summary`, `stage2_summary`, `profile_update_summary`, `analysis_summary`, `run_summary`). The harness snapshots that file per run and aggregates into `comparison.md`.

## First-run prerequisites

1. **Authorize Spotify once via the dev server.** The harness re-uses your real `.spotify-cache` so OAuth doesn't have to run from a non-interactive script. If you've never authorized, do this first:
   ```bash
   python app.py
   # open http://127.0.0.1:5000, click "Connect to Spotify", authorize.
   # then close the server.
   ```
2. **Confirm DEBUG_MODE works.** The harness sets it inside the sandbox automatically — no manual step needed. If you want telemetry from the dev server too, set `DEBUG_MODE=1` in `%LOCALAPPDATA%\spotyvibe\settings.conf`.
3. **Copy the settings template:**
   ```bash
   cp evaluation/settings.ini.example evaluation/settings.ini
   ```
   Then fill in `[openai] api_key`, `[spotify] client_id`, `[spotify] client_secret`. `evaluation/settings.ini` is gitignored.
4. **Pricing entries in `pricing.json`** — the harness logs a warning if any supported model is missing and reports `—` for cost in that case. (CF-Bug-4 — original gap closed 2026-04-27.)

## Running

```bash
python evaluation/run_evaluation.py
```

Standard run prints the plan, asks `Continue? [y/N]`, and proceeds. The full matrix takes roughly 8–15 minutes depending on which models you include and how chatty Spotify verification is.

Flags:

| Flag | Effect |
|---|---|
| `--no-confirm` | Skip the cost prompt. Use in scripts. |
| `--cleanup-only` | Sweep orphaned `[EVAL] …` playlists from your Spotify account and exit. Useful after a hard kill. |

## Pool-size sweep (multi-config / multi-block runs)

To compare a sequence of `RETRIEVE_CANDIDATES_SIZE` values across multiple repeat blocks (for determinism analysis), use the sweep driver instead of calling the harness directly:

```bash
bash evaluation/run_pool_sweep.sh
```

What it does:

1. For each `(block, pool)` in the configured sequence: cooldown → patch `config.py` → run the eval → scan the run log for Spotify `429` errors.
2. **If any single run logs ≥ `RATE_LIMIT_THRESHOLD` (default 3) `429` errors, the sweep aborts immediately** with a banner telling you to wait ≥ 30 min before retrying. Partial results are still aggregated.
3. After all runs (or on early abort), aggregates every `eval.jsonl` into `summary.csv` and renders `report.md`.

Everything is written under `evaluation/results/sweep-<UTC-timestamp>/`:

| File | Purpose |
|---|---|
| `report.md` | Human-readable comparison — start here. |
| `summary.csv` | One row per `(block, pool, model)` for further analysis. |
| `manifest.tsv` | Pointers to the per-run eval directories. |
| `sweep.log` | High-level timeline. |
| `run_p<pool>_b<block>.log` | Full per-eval debug output (large). |

Configuration via env vars:

| Variable | Default | Meaning |
|---|---|---|
| `COOLDOWN` | `300` | Seconds to wait before each eval (Spotify rate-limit safety). |
| `POOLS` | `"30 40 50"` | Space-separated pool sizes to sweep. |
| `BLOCKS` | `2` | How many times to repeat the pool sequence (for determinism). |
| `RATE_LIMIT_THRESHOLD` | `3` | Number of `429` errors in a single run that triggers abort. |

Example: a quick 3-pool single-block run with a 3-min cooldown:

```bash
COOLDOWN=180 BLOCKS=1 POOLS="32 40 48" bash evaluation/run_pool_sweep.sh
```

After the sweep completes, point an AI agent at `<sweep-dir>/report.md` and `summary.csv` to drill into per-model patterns or noise floors.

## Output

```
evaluation/results/{ts}/
  harness.log
  comparison.md          ← read this first
  gpt-5.4-iter1/
    eval.jsonl           ← raw rows for pandas analysis
    summary.json         ← per-run rollup
  gpt-5.4-mini-iter1/...
  gpt-4.1-iter1/...
  gpt-4.1-mini-iter1/...
```

`comparison.md` carries: per-run cost / wall-clock / p50 / p95 / Spotify-found rate / must-have-cite rate / Stage 2 status, plus a feature-level cost breakdown (Stage 3 vs Stage 2 vs Profile Update vs Analysis), plus an eval-log row-count sanity check (telemetry must fire for every feature — if a column shows 0 the harness or the production code regressed).

## Cost

Approximate per full run (4 models, 1 iteration each, playlist_size=15):

| Model         | Per cycle |
|---|---:|
| gpt-5.4       | ~$0.10    |
| gpt-5.4-mini  | ~$0.01    |
| gpt-4.1       | ~$0.04    |
| gpt-4.1-mini  | ~$0.01    |
| **Total**     | **~$0.16**|

These are rough estimates kept in `_PER_CYCLE_USD` in `run_evaluation.py`. The harness re-prices from `frontend/static/data/pricing.json` after the run, so the report shows actual usage-based cost — the up-front estimate is a budgeting hint, not the final bill.

## Safety

- **Sandbox isolation.** `SPOTYVIBE_APP_DIR` is set before any production import, so the harness writes to `evaluation/sandbox/{ts}/` instead of `%LOCALAPPDATA%\spotyvibe\`. Your real profile, eval log, and settings are never touched.
- **Tagged playlists.** Every harness-created playlist starts with `[EVAL] ` so `--cleanup-only` can sweep the account safely.
- **Cleanup in `finally`.** Each model run's cleanup runs even on uncaught exception or `KeyboardInterrupt`. If the process is `kill -9`'d, use `--cleanup-only`.
- **No real-account state.** Likes / dislikes are persisted to the **sandbox profile JSON**, not to the user's Spotify Saved Library. The dev app behaves the same way — there is no Spotify-side like API in this app.

## Extending

- **New scenario** — edit `scenario.py`. Keep one canonical scenario per harness invocation; do not branch by model.
- **New per-feature row kind** — add a new `kind: "<feature>_summary"` writer in `core/src/eval_log.py`, emit it from the production code path, then update `reporting.py::summarise_run` to aggregate it. The comparison table picks up new feature columns automatically as long as they live under `feature_costs_usd` / `feature_latency_s`.
- **More iterations** — set `[evaluation] iterations = 3` to run each model 3× and average. The reporting layer still produces one row per `(model, iteration)`; you can group by model in pandas.
- **Different model set** — `[evaluation] models = gpt-5.4,gpt-5.4-mini` to skip a model. List order is preserved in the report.

## Architecture

```
run_evaluation.py            entry point; CLI; sandbox setup; orchestration loop
  └─ harness.py              one ModelRunResult per (model, iteration)
       ├─ scenario.py        deterministic seed + like/dislike rule (do not parametrise)
       └─ (production code)  config, profile, analysis, suggestions, playlist, feedback
  └─ reporting.py            eval.jsonl → summary.json + comparison.md
```

Production code is **not** modified by the harness; the only seam is `SPOTYVIBE_APP_DIR` (added in `config._get_app_dir()`). If you find yourself reaching for monkey-patches in the harness, that is a sign the production code needs another seam — extend `config.py`, do not kludge in the harness.
