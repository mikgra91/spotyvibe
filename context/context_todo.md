# TODO.md Condensed State — 2026-04-30
Source: TODO.md 

## Critical product state
- Recommendation quality is currently unacceptable.
- RAG degraded recommendation quality; prompt changes did not fix it.
- Eval benchmarks are misleading: `gpt-5.4-mini` scored best but failed in production.
- Production failures observed:
  - Only 5 songs returned.
  - Poor profile match.
  - Instructions ignored.
  - Previously disliked bands re-recommended after profile updates.
  - >99% recommendations failed user taste/profile match.
- Required: full diagnosis of retrieval, ranking, profile handling, memory updates, prompt injection, filtering, instruction adherence.
- Add full pipeline tracing/observability; log every stage and locate degradation point.
- Consider removing RAG, Cloud Run, and current workflow/infrastructure if quality/cost remain nonviable.

## Implemented / completed
- D1: Removed dead Spotify metadata module/tests:
  - Deleted `core/src/spotify_metadata.py` (~470 LOC).
  - Deleted `core/tests/test_spotify_metadata.py` (~330 LOC).
  - Confirmed zero production callers.
  - Updated docs: `TechnicalManual.md`, `ProjectLayout.md`.
  - Test count changed 626 → 597.
  - Live Spotify calls now centralized through `core/src/playlist.py`.
- P6-FRONTEND-CORRUPTION:
  - `test_edge_cases.py` and `test_page_load.py` already matched `HEAD` and parsed cleanly.
  - Likely fixed earlier.
- D2:
  - Original TODO was mostly wrong: most listed RAG constants exist and are used.
  - Truly dead: `BATCH_SIZE_WITH_RAG`, `get_effective_batch_size()`.
  - Removed dead-name references.
  - Fixed docs drift: `RAG_POOL_SIZE` docs said 100, code is 60.
  - Updated `TechnicalManual.md`, `UserManual.md`, `help.en.md`, `help.de.md`, `help.jp.md`.
- S3:
  - `meta.goal` is populated end-to-end.
  - Training prompt instructs model to set it.
  - `profile.py:440` validates it as string.
  - `meta_goal_chars` telemetry was already correctly removed.
  - Cleaned stale `eval_log.py` comments.
- S7:
  - Removed dead `_STAGE3_JSON_SCHEMA` (~50 LOC).
  - Removed `_stage3_response_format()`.
  - Updated `result-improvement.md`.
- P6 docs:
  - Added warning header to `evaluation/run_pool_sweep.sh`.
  - Added aborted-sweep recovery section to `evaluation/README.md`.
- N5/N6/N7:
  - Added superseded banner to `analysis.md`.
  - Fixed `evaluation/README.md`: 30-track → 15-track.
  - Added no-auto-commit reminder to `SKILL.md`.
- S5:
  - `dislike_track` now dedups track-level dislikes case-insensitively by `(artist, track)`.
- S6:
  - `_NO_TEMPERATURE_MODELS` moved to `config.OPENAI_NO_TEMPERATURE_MODELS`.
- S12:
  - `_migrate_flat_profiles` now uses path-keyed `_MIGRATED_DIRS`; one glob per profiles dir per process.
- S13:
  - Consolidated `EMPTY_PROFILE` / `TRAINED_PROFILE` into `frontend/tests/_shared.py`; helpers re-exported.
- N1:
  - `_auth_status_cache` now caches negative results (`not_configured`, `not_authenticated`) with same TTL.

## Phase 6.0 cost bundle state
- Implemented and unit-tested L1 + L8 + L11 + L16 cost-reduction bundle.
- Core tests passed: 1121/1121.
- Bundle change locations:
  - `core/src/eval_log.py`: L16 `cached_tokens` extraction.
  - `core/src/suggestions.py`: L8 template-line strip, L11 `STAGE3_OVER_REQUEST`, L1 `skipped_no_overlap`.
  - `core/src/rag/retrieval.py`: `_LAST_RETRIEVAL_META`, `get_last_retrieval_meta()`.
  - `app.py`: wires `pool_avoid_overlap` into `check_avoid_compliance`.
  - `config.py:51`: `STAGE3_OVER_REQUEST = 2`.
- Validation eval attempted 2026-04-30 but produced no valid data.
- Eval output path: `evaluation/results/sweep-20260430T112359Z/`.
- All blocks produced 0 tracks / `cite_pct = 0`.

## Phase 6.0 blockers
- Spotify auth broken:
  - Logs show `POST /api/token HTTP/1.1 400`.
  - Spotify returns `invalid_client`, `Failed to get client`.
  - Pipeline errors: `Spotify is not connected`.
  - Likely expired/revoked refresh token or client_id/secret mismatch.
- `evaluation/settings.ini` stale:
  - Still lists `models = gpt-5.5,gpt-5.4,gpt-5.4-mini`.
  - `gpt-5.5` is no longer supported.
  - Pass criteria assume 4 models: `gpt-5.4,gpt-5.4-mini,gpt-4.1,gpt-4.1-mini`.

## Required user actions before eval
1. Reconnect Spotify:
   - Run `python app.py`.
   - Click "Connect to Spotify".
   - Complete OAuth.
   - Refreshes `%LOCALAPPDATA%/spotyvibe/.spotify-cache`.
2. Update `evaluation/settings.ini`:
   - Drop `gpt-5.5`.
   - Decide final model set.
   - Expected validation set: `gpt-5.4,gpt-5.4-mini,gpt-4.1,gpt-4.1-mini`.
3. Re-run:
   - `cd /c/git/spotyvibe/evaluation`
   - `POOLS="50" BLOCKS=5 bash run_pool_sweep.sh`
   - Expected wall-clock: ~75 min.

## Phase 6.0 validation pass criteria
- Compare against `sweep-merged-5blocks/summary.csv`.
- Baseline `cite_pct`:
  - `gpt-5.4-mini`: 88.0%
  - `gpt-5.4`: 98.7%
  - `gpt-4.1-mini`: 82.7%
  - `gpt-4.1`: 62.7%
- Pass if:
  - Mean `cite_pct` drop ≤ 1 pp on every model.
  - `found_pct` ≥ 95% every cell.
  - Playlist completion ≥ 95% of `playlist_size` 15.
  - `gpt-5.4-mini @ pool=50` cost ≈ $0.018/playlist vs baseline $0.0288.
  - `cached_tokens / prompt_tokens` ≥ 0.4 in `eval.jsonl` for cloud models.

## Phase 6.0 fail handling
- If cite-rate drops >1 pp:
  - Check L8 template strip.
  - Expected symptom: `cached_tokens` below expected.
- If completion <95%:
  - Revert L11: set `STAGE3_OVER_REQUEST = 5` in `config.py:51`.
  - Re-run.
- If Stage 2 approves fewer artists:
  - Check `app.py:862` passes `pool_avoid_overlap`.
  - In `eval.jsonl`, expect `kind: "stage2_summary"` rows with `status: "skipped_no_overlap"`.

## Queued: P6-INV13-25
- Blocked by P6-EVAL and working Spotify auth.
- Purpose:
  - Validate variance-failed levers under rule: block-to-block cite Δ ≥13 pp must be measured over ≥5 blocks × 2 seeds before adoption.
- Levers:
  - L13: default model `gpt-5.4-mini → gpt-4.1-mini`; predicted savings $13/1k playlists.
  - L25: default pool `50 → 30`; predicted savings $5–8/1k playlists.
- Prior n=1 results unstable:
  - `gpt-4.1-mini` Δ 26.6 pp at pool 50.
  - `gpt-5.4-mini @ pool 30` Δ 16.2 pp.
- Eval matrix:
  - 4 models × pools {30,50} × seeds {A,B} × 5 blocks.
  - Estimated wall-clock: 5–6 h.
- Current blocker:
  - `evaluation/run_pool_sweep.sh` lacks multi-seed support.
- Recommended implementation:
  - Add `SEEDS="A B"` env.
  - Loop existing block loop one level deeper.
  - Swap `evaluation/scenario.py` or `settings.ini` per seed.
  - First inspect seed source in `evaluation/run_evaluation.py`.
- Command after change:
  - `cd /c/git/spotyvibe/evaluation`
  - `POOLS="30 50" BLOCKS=5 SEEDS="A B" bash run_pool_sweep.sh`
- L13 pass:
  - Mean cite ≥86% across both seeds.
  - No single block <70%.
  - Per-seed B↔B Δ <13 pp for at least one stable seed.
- L25 pass:
  - Mean cite Δ ≥−2 pp on `gpt-5.4-mini` and `gpt-5.4`.
  - Per-seed B↔B Δ <13 pp on those models.
- Outcome rule:
  - If both pass: ship both; update `config.py` defaults and `documentation/ModelRecommendations.md`.
  - If one passes: ship only that one.
  - If neither passes: close as not pursuable; document in `result-improvement.md` Phase 6.1.

## Queued: P6-RELY Spotify reliability
- Depends on P6-INV13-25.
- Goal: speed + 429 resilience; no LLM cost impact.
- Implement:
  - L20: persistent Spotify search cache by `(artist, track, market)`, 7-day TTL.
  - L21: skip Spotify `search` for tracks already in `approved_top_tracks` overlay.
- Motivation:
  - 5-block sweep saw 5 HTTP 429 errors.
  - One full sweep aborted by 429-cascade guard.
  - Retries/backoff exist; caching does not.
- Expected impact:
  - Wall-clock −3 to −9 s/playlist.
  - 429 surface area −50–80%.
  - Cost Δ $0.
- Implementation sketch:
  - Add `core/src/cache/spotify_search_cache.py`.
  - Wrap Spotify `search` in `core/src/playlist.py`.
  - Persist to `%LOCALAPPDATA%/spotyvibe/spotify_search_cache.json`.
  - Key: `artist.lower()::track.lower()::market`.
  - TTL: 7 days.
  - Plumb `track_id` through `_format_approved_artists_block` → `select_tracks` output → playlist-build short-circuit.
- Eval:
  - 5-block pool=50.
  - Stress test: 10 back-to-back full eval cycles without cache, then with cache.
  - Pass: `cache_hit_rate > 0.8` after warmup and zero 429s in warmed run.

## Should-fix
- S14: Spotify reconnect must clear stale cache.
  - Problem: stale `.spotify-cache` can shadow fresh OAuth code.
  - Spotipy may use stale refresh token and return `400 invalid_client`.
  - Fix: call `CACHE_FILE.unlink(missing_ok=True)` at top of `get_spotify_auth_url()` or add UI Reconnect path wrapping `disconnect_spotify()` + auth.
  - Test: create fake stale cache, trigger auth URL, assert cache removed.
- Config credential test gap:
  - `save_credentials()` keychain branch had undetected `NameError` from `CREDENTIALS_KEYS` typo.
  - Add test with `_KEYRING_AVAILABLE=True` and mocked `_keyring`.
- S1: frontend modal flake.
  - `ragUpdateTip` toast intercepts pointer events.
  - Affects help/settings modal tests.
  - Fix via autouse Playwright fixture hiding `#ragUpdateTip` or disable pointer events under test.
- S2: frontend profile editor flake.
  - `test_toggle_opens_and_closes_editor` intermittently fails.
  - `#trainBody` remains visible after clicking toggle.
  - Likely animation timing.
  - Fix by disabling CSS transitions/animations in tests or waiting for animation completion.
- S4: backend English errors surface directly in UI.
  - Files: `playlist.py`, `openai_http.py`, `suggestions.py`, `analysis.py`.
  - Replace raw messages with structured error key + fallback.
- S8: add direct unit test for local-LLM schema auto-downgrade.
  - Cover `openai_http._looks_like_schema_rejection`.
  - Cover `_JSON_SCHEMA_UNSUPPORTED` cache.
- S9: add direct tests for profile import/export integrity.
  - Cover `validate_profile_schema`.
  - Cover `import_profile_dict`.
- S10: hardcoded ARIA labels with artist/track names.
  - `frontend/templates/generate_section.html` lines 305–306.
  - Move to JS locale template using data attrs.
- S11: `profile.py:swap_profile_with_history` not crash-safe.
  - Three sequential renames can lose backup if killed between steps.
  - Add startup recovery for orphan `*.swap.tmp`.

## Found bugs
- Playback stuck:
  - Removed track keeps playing.
  - Other tracks cannot be played while stuck.
- Settings Save UX:
  - Save sometimes takes a while.
  - No busy/progress indication.
  - Users may click Save repeatedly.

## Nice-to-have
- N2: verify/fix possible `keydown` listener leak in `frontend/static/js/modules/quickstart-demo.js`.
- N3: wire remaining onboarding hardcoded English strings/ARIA labels to i18n.
- N4: normalize help anchor IDs across languages.
  - German localized anchors can break `/api/help/section/<anchor>` deep-links.
  - Use stable English anchors across `help.en.md`, `help.de.md`, `help.jp.md`.

## Main learned constraints
- Current eval success does not predict production quality; add production-like traces and failure observability.
- RAG can actively degrade taste matching; do not assume retrieval improves quality.
- Prompt engineering alone has not solved instruction adherence/profile alignment.
- Memory/filtering likely broken because disliked artists reappear after updates.
- Cost work is blocked until functional validation works.
- Spotify auth/cache fragility blocks reliable eval and needs reconnect-hardening.
- Variance is high enough that single-seed decisions are unsafe.