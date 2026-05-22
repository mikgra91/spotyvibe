# Evaluation harness

End-to-end evaluation runs against real OpenAI + real Spotify, used to compare model variants on cost, latency, and quality.

**Current model verdicts live in [`evaluation/model-performance-result.md`](model-performance-result.md)** — the single source of truth for which models are recommended, removed, or pending evaluation. Read it before picking a model or interpreting a run.

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
4. Generates a 15-track playlist, configurable via `evaluation/scenario.py` (Stage 1 retrieval → Stage 2 mini-LLM → Stage 3 selection → Spotify verify).
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

Approximate per cycle (1 iteration, playlist_size=15):

| Model         | Per cycle |
|---|---:|
| gpt-5.4       | ~$0.10    |
| gpt-5.4-mini  | ~$0.002 (OpenRouter) |

Estimates are kept in `_PER_CYCLE_USD` in `run_evaluation.py`. The harness re-prices from `frontend/static/data/pricing.json` after the run, so the report shows actual usage-based cost — the up-front estimate is a budgeting hint, not the final bill. See [`model-performance-result.md`](model-performance-result.md) for the full cost/quality comparison.

## Safety

- **Sandbox isolation.** `SPOTYVIBE_APP_DIR` is set before any production import, so the harness writes to `evaluation/sandbox/{ts}/` instead of `%LOCALAPPDATA%\spotyvibe\`. Your real profile, eval log, and settings are never touched.
- **Tagged playlists.** Every harness-created playlist starts with `[EVAL] ` so `--cleanup-only` can sweep the account safely.
- **Cleanup in `finally`.** Each model run's cleanup runs even on uncaught exception or `KeyboardInterrupt`. If the process is `kill -9`'d, use `--cleanup-only`.
- **No real-account state.** Likes / dislikes are persisted to the **sandbox profile JSON**, not to the user's Spotify Saved Library. The dev app behaves the same way — there is no Spotify-side like API in this app.

## Extending

- **New scenario** — edit `scenario.py`. Keep one canonical scenario per harness invocation; do not branch by model.
- **New per-feature row kind** — add a new `kind: "<feature>_summary"` writer in `core/src/eval_log.py`, emit it from the production code path, then update `reporting.py::summarise_run` to aggregate it. The comparison table picks up new feature columns automatically as long as they live under `feature_costs_usd` / `feature_latency_s`.
- **More iterations** — set `[evaluation] iterations = 5` (the current default since N2, 2026-05-13) to run each model 5× and average, or pass `--iterations <n>` on the command line to override per-run. The reporting layer still produces one row per `(model, iteration)`; you can group by model in pandas.

  **Per-model variance floors (B-6 fingerprint, v1 2026-05-12).** The B-6 `n_required_for_5pp_signal` probe measures how many iterations are needed to detect a 5-pp prompt-change effect above the model's own run-to-run noise:

  | Model         | `n_required_for_5pp_signal` | Recommended `--iterations`                    |
  |---------------|----------------------------:|-----------------------------------------------|
  | gpt-4.1       |                           5 | 5 (default — sufficient)                      |
  | gpt-5.4       |                          19 | 19 for prompt A/B; 5 OK for cost-only changes |
  | gpt-5.4-mini  |                          85 | 85 only when investigating mini specifically — full sweep is ~17× the default cost |

  Refresh these numbers by re-running `python -m evaluation.probes --model <m> --probes B-6 --confirm` and inspecting `evaluation/probes/fingerprints/<m>.v1.json`.
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
