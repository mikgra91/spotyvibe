# TODO — Deferred Code-Review Items (2026-04-28; refreshed 2026-04-30 PM)

Items identified during the code-review pass but deferred. Pick these up in a future session.

---

## 🔴🔴 Phase 6.0 follow-ups (2026-04-29) — pick up here when resuming cost work

Context: 5-block pool-size sweep landed (`evaluation/results/sweep-merged-5blocks/report.md`).
The L1+L8+L11+L16 cost-reduction bundle was implemented and unit-tested (1121 / 1121 core
tests pass). **Validation eval was attempted on 2026-04-30 but failed before producing
data** — see "Needs user action / decision" section at the bottom of this file for what
is blocked and why. Full lever analysis lives in `cost-speed-research.md` (26 levers
scored). Phase summary in `result-improvement.md` §"Phase 6.0".

### P6-INV13-25 — L13 + L25 combined investigation sweep (queued 🟡)

**Blocked on:** P6-EVAL (must validate the bundle before queuing further L-work) AND
on a working Spotify auth in `evaluation/`. See user-action section.

**What:** verify the variance-failed levers under the new variance-as-regression rule
(block-to-block cite Δ ≥ 13 pp = "must be measured over ≥ 5 blocks × 2 seeds before adoption").

**Predicted savings if validated:**
- L13 (default model `gpt-5.4-mini → gpt-4.1-mini`): $13/1k playlists
- L25 (default pool `50 → 30`): $5–8/1k playlists

**Why deferred:** at n=1 seed in the merged sweep, gpt-4.1-mini shows Δ 26.6 pp (pool 50)
and gpt-5.4-mini @ pool 30 shows Δ 16.2 pp — both fail the 13 pp threshold. The flip
between blocks could be (a) genuine model non-determinism (rules out adoption) or
(b) seed-specific noise (rules in adoption with caveats). 2-seed × 5-block matrix
distinguishes the two hypotheses.

**Eval matrix:** 4 models × {pool 30, 50} × {seed A, seed B} × 5 blocks ≈ 5–6 hours wall.

**Blocker:** `evaluation/run_pool_sweep.sh` does not currently support multi-seed.
Two options:
1. **Code change** (~30 LOC, recommended): add `SEEDS="A B"` env var. Loop the existing
   block-loop one level deeper, swapping `evaluation/scenario.py` (or `settings.ini`)
   between iterations. Inspect what defines "the seed" first — likely the music-profile
   the harness loads in `evaluation/run_evaluation.py` (search for "scenario" / "seed").
2. **Manual** (no code): run the sweep twice with different `evaluation/settings.ini`
   contents, then merge the resulting `manifest.tsv` files (use the same approach as
   `sweep-merged-5blocks/manifest.tsv`, which was hand-merged from two earlier sweeps).

**Run command (after code change, option 1):**
```bash
cd /c/git/spotyvibe/evaluation
POOLS="30 50" BLOCKS=5 SEEDS="A B" bash run_pool_sweep.sh
```

**Pass criteria for L13 (default → gpt-4.1-mini):**
- Mean cite ≥ 86% across both seeds AND no single block < 70%
- Per-seed B↔B Δ < 13 pp (one of the two seeds must show stable behaviour)

**Pass criteria for L25 (default pool → 30):**
- Mean cite Δ ≥ −2 pp on `gpt-5.4-mini` AND `gpt-5.4` (these are the two production-default
  candidates — gpt-4.1 isn't recommended at all)
- Per-seed B↔B Δ < 13 pp on those two models

If both pass → ship; update `config.py` defaults + `documentation/ModelRecommendations.md`.
If only one passes → ship that one alone.
If neither passes → close as "not pursuable", document in Phase 6.1 of `result-improvement.md`.

### P6-RELY — L20 + L21 Spotify reliability bundle (queued, after P6-INV13-25)

**What:** speed + 429-resilience bundle, $0 LLM cost.
- **L20** Persistent Spotify search cache per `(artist, track, market)`, 7-day TTL.
- **L21** Skip Spotify `search` for tracks already in the `approved_top_tracks` overlay
  (those came from prior Spotify search → already verified).

**Why now:** the merged 5-block sweep observed **5 200 × HTTP 429 errors** and one full
sweep run was aborted by the 429-cascade safety guard. Phase 2.6 added retries+backoff
but no caching — these two levers attack the root cause.

**Predicted impact:** speed −3 to −9 s wall-clock per playlist; 429 surface area down
50–80% (overlay-skip alone); cost Δ $0.

**Implementation sketch:**
- L20: new `core/src/cache/spotify_search_cache.py`; wrap `search` call in
  `core/src/playlist.py`. Persist to `%LOCALAPPDATA%/spotyvibe/spotify_search_cache.json`
  with key = `f"{artist.lower()}::{track.lower()}::{market}"`. TTL = 7 days.
- L21: plumb `track_id` through `_format_approved_artists_block` →
  `select_tracks` output → playlist-build short-circuit. The overlay tracks already
  carry `track_id` (built by `build-tools/build_top_tracks_overlay.py`) — currently
  thrown away when rendered into the prompt as `known: "title"` strings only.

**Eval:** 5-block at pool=50 + a stress test (10 back-to-back full eval cycles to
trigger 429s without cache, then with cache). Pass = (a) `cache_hit_rate > 0.8` after
warmup, (b) zero 429s in the warmed run.

---

## 🟡 Should-fix — no decision needed, just work

### S14 — "Connect to Spotify" should clear stale cache before OAuth round (2026-04-30)
`get_spotify_auth_url()` / the callback handler (`core/src/playlist.py:267-279`) do
not call `disconnect_spotify()` before kicking off a new OAuth flow. If a stale
`.spotify-cache` exists (e.g. minted under a different client_id, or a revoked
refresh_token), spotipy reads it and prefers `grant_type=refresh_token` over
exchanging the new `authorization_code` — Spotify returns `400 invalid_client`
and the user sees "Authentication Failed" with no recovery path short of
manually deleting `%LOCALAPPDATA%/spotyvibe/.spotify-cache`.

Observed 2026-04-30 after a client_id change: every "Connect to Spotify" click
silently swallowed the fresh auth code because the old cache shadowed it.

**Fix:** call `CACHE_FILE.unlink(missing_ok=True)` at the top of
`get_spotify_auth_url()` (or expose a "Reconnect" path in the UI that wraps
`disconnect_spotify()` + `get_spotify_auth_url()`). Add a unit test that
constructs a fake stale cache, triggers the auth URL, and asserts the cache
is gone.

**Also fix in code-review pass that introduced this:** `save_credentials()`
in `config.py` had an undetected `NameError` on the keychain-reload branch
(line 652: `CREDENTIALS_KEYS` typo, since renamed). The keychain branch had
zero test coverage. Add a test that calls `save_credentials({"OPENAI_API_KEY":
"sk-x"})` with `_KEYRING_AVAILABLE=True` and a mocked `_keyring` to exercise
lines 651-658.

### S1 — Pre-existing frontend test flake: `ragUpdateTip` toast intercepts pointer events
Several modal tests fail non-deterministically because the "New artist database available"
RAG-update toast appears on top of modal buttons and blocks clicks.

Affected tests (flaky, not always failing):
- `test_modals.TestHelpModal::test_closes_on_close_button`
- `test_modals.TestHelpModal::test_closes_on_overlay_click`
- `test_modals.TestSettingsModal::test_shows_model_dropdown`

**Recommended fix:** add an autouse Playwright fixture that dismisses / hides the
`#ragUpdateTip` element before each modal test, e.g.:
```python
@pytest.fixture(autouse=True)
def dismiss_rag_tip(page):
    page.add_init_script("document.addEventListener('DOMContentLoaded', () => { const t = document.getElementById('ragUpdateTip'); if (t) t.style.display = 'none'; });")
    yield
```
Or add `pointer-events: none` to the toast container when running under test.

### S2 — Pre-existing frontend test flake: `test_toggle_opens_and_closes_editor`
`frontend/tests/test_profile.py::TestProfileEditor::test_toggle_opens_and_closes_editor`
fails intermittently on baseline (confirmed pre-existing). The `close_profile_editor`
helper clicks `#trainToggleBtn` but `#trainBody` remains visible. Likely a CSS animation
not completing before the `to_be_hidden` assertion. Add a CSS transition override
in `conftest.py` (`page.add_style_tag(content="* { transition: none !important; animation: none !important; }")`)
or wait for the animation to complete before asserting.

### S4 — Hardcoded English error strings raised to the UI (i18n sweep)
Backend exceptions whose messages surface directly in the UI:
- `playlist.py:840` — 403 reconnect message
- `openai_http.py:94–97, 275–278` — config + unsupported-model errors
- `suggestions.py:433, 438` — empty/invalid AI response messages
- `analysis.py:38` — "Artist name is required."

These should carry an i18n key so the frontend can translate them.
Pattern: raise a structured error with a `key` attribute + English fallback;
frontend looks up `i18n(error.key, error.message)`.

### S8 — Cover the local-LLM auto-downgrade path with a direct unit test
`openai_http._looks_like_schema_rejection` + `_JSON_SCHEMA_UNSUPPORTED` cache is
the canonical local-LLM compatibility pattern called out in `AGENTS.md` as a P0
product rule. It currently has no dedicated test — a regression here would silently
break every local-LLM user.

### S9 — Cover `validate_profile_schema` / `import_profile_dict` with unit tests
Profile import/export and schema validation (`core/src/profile.py`) have no direct
tests. Risk: silent profile corruption on save/import. These are P0 data-integrity paths.

### S10 — Hardcoded ARIA labels with interpolated artist/track names (i18n)
`frontend/templates/generate_section.html` lines 305–306:
`aria-label="Feedback on {{ track.artist|e }} — {{ track.title|e }}"` is untranslatable
server-side. Use a JS post-process step: store `data-track-artist` + `data-track-title`
attributes and update `aria-label` from the locale template string at render time in JS.

### S11 — `profile.py:swap_profile_with_history` is not crash-safe
Lines ~295–305: three sequential `rename` calls. If the process is killed between
step 2 and step 3, the backup copy is unrecoverable. Add a startup recovery path
that detects an orphan `*.swap.tmp` and either restores it or warns the user.

---

## 🟢 Nice-to-have / polish

### ~~N2 — JS `addEventListener` leak in `quickstart-demo.js`~~ ✅ False positive
Verified 2026-05-04: the lightbox `keydown` listener is added only inside the
`if (!lb)` guard (line 555) when the element is first created, and properly
removed in `_closeLightbox` (line 502) via the stored `lb._onKey` reference.
No leak exists.

### ~~N3 — Onboarding i18n: several hardcoded English strings / aria-labels not yet wired~~ ✅ False positive
Verified 2026-05-04: the `obProviderBadge` text is dynamically set via
`obI18n('ob.step6_provider_note', ...)` in `onboarding.js` (lines 56-61 and
628-634). The key exists in all three i18n files. The HTML fallback is just
pre-render content before JS hydration — standard practice.

### ~~N4 — `help.de.md` uses localised anchor IDs; `help.en.md` / `help.jp.md` use English ones~~ ✅ Done 2026-05-04
Normalised all `<a id="...">` anchors and `href="#..."` links in `help.de.md`
to use the same English IDs as `help.en.md` and `help.jp.md`. All three files
now use identical anchors, so `/api/help/section/<anchor>` deep-links work
cross-language.

---

## 🟠 Needs user action / decision (skip during agent runs — escalate to user)

These items cannot be progressed by the agent alone: they require either a credentials
action only the user can perform, or a product-level call between two equally-valid
options. The agent should **not** pick a default; surface them and wait.

### P6-EVAL — Bundle validation eval — BLOCKED on Spotify reconnect & settings.ini update

**Status (2026-04-30):** Eval was run via `POOLS="50" BLOCKS=5 bash run_pool_sweep.sh`
and produced `evaluation/results/sweep-20260430T112359Z/`, but **every block produced
0 tracks** — see `report.md` (all `cite_pct = 0`, all `tracks = 0`). Root causes:

1. **Spotify auth is broken.** Every block log (`run_p50_b*.log`) shows
   `POST /api/token HTTP/1.1 400` with `{error: invalid_client, "Failed to get client"}`
   followed by `RuntimeError: run_pipeline returned error: Spotify is not connected`.
   The harness shares the user's real `.spotify-cache`; the refresh token has expired
   or the client_id/secret pair is no longer accepted.
2. **`evaluation/settings.ini` is stale.** It still lists
   `models = gpt-5.5,gpt-5.4,gpt-5.4-mini`. `gpt-5.5` was removed from the supported
   model list in Phase 2.6 (2026-04-28) and now raises `OpenAIUnsupportedModelError`.
   The pass criteria below mention 4 models; the current config only attempts 3 and
   never gpt-4.1 / gpt-4.1-mini.

**Required user actions before re-running:**

1. **Reconnect Spotify.** Run `python app.py`, click "Connect to Spotify",
   complete the OAuth handshake. This refreshes `%LOCALAPPDATA%/spotyvibe/.spotify-cache`
   which the eval harness reuses. (See `evaluation/README.md` § "First-run prerequisites".)
2. **Decide the model set for this validation run** and update
   `evaluation/settings.ini` `[evaluation] models = ...` accordingly. The pass criteria
   below assume **4 models**: `gpt-5.4,gpt-5.4-mini,gpt-4.1,gpt-4.1-mini` (drop gpt-5.5).

After both, re-run the validation:
```bash
cd /c/git/spotyvibe/evaluation
POOLS="50" BLOCKS=5 bash run_pool_sweep.sh
```
Expected wall-clock: ~75 min (5 runs × ~7 min eval + 8-min cooldowns).

**Pass criteria** (compare against `sweep-merged-5blocks/summary.csv` for `gpt-5.4-mini @ pool=50`):
- Mean `cite_pct` Δ ≥ −1 pp on every model (baseline: gpt-5.4-mini 88.0%, gpt-5.4 98.7%, gpt-4.1-mini 82.7%, gpt-4.1 62.7%)
- `found_pct` ≥ 95% every cell (baseline: 100% on 58/60 rows)
- Playlist completion ≥ 95% of `playlist_size` (15)
- Total `cost` $/playlist ≈ $0.018 for `gpt-5.4-mini @ pool 50` (baseline $0.0288, predicted ~37% reduction)
- New `cached_tokens / prompt_tokens` ≥ 0.4 in `eval.jsonl` for cloud models (validates Phase 2.5 §T1.3 prefix caching survived L8's template-line strip)

**Fail handling:**
- If cite-rate drops > 1 pp on any model → check L8 first (template strip may have broken prefix-cache invariance — `cached_tokens` will be < expected).
- If completion < 95% → revert L11 by setting `STAGE3_OVER_REQUEST = 5` in `config.py:51` and re-run.
- If Stage 2 starts approving fewer artists → check `app.py:862` is correctly passing `pool_avoid_overlap`; in `eval.jsonl` look for rows with `kind: "stage2_summary"` and `status: "skipped_no_overlap"` (should appear on every run).

**Where the bundle changes are** (for revert if needed):
- `core/src/eval_log.py` — L16 `cached_tokens` extraction (~line 372)
- `core/src/suggestions.py` — L8 template-line strip (~line 1235), L11 `STAGE3_OVER_REQUEST` (~line 1185), L1 `skipped_no_overlap` status (~line 1058)
- `core/src/rag/retrieval.py` — L1 `_LAST_RETRIEVAL_META` + `get_last_retrieval_meta()` (top + ~line 605)
- `app.py` — L1 wires `pool_avoid_overlap` into `check_avoid_compliance` (~line 862)
- `config.py:51` — L11 `STAGE3_OVER_REQUEST = 2`

---

## ✅ Completed in session 2026-04-30

- **D1** — deleted `core/src/spotify_metadata.py` (~470 LOC) and `core/tests/test_spotify_metadata.py` (~330 LOC) after confirming zero production callers. Cleaned the two doc references in `TechnicalManual.md:229` and `ProjectLayout.md:36`. Test count drops from 626 → 597 (29 spotify_metadata tests removed). Restores the single-chokepoint rule (all live Spotify calls now go through `core/src/playlist.py`).
- **P6-FRONTEND-CORRUPTION** — verified: `test_edge_cases.py` and `test_page_load.py` already match `HEAD` and parse cleanly. Likely fixed in a prior session; no checkout needed.
- **D2** — investigation found the original TODO was inaccurate: most listed constants (`RAG_ENABLED`, `RAG_CORPUS_PATH`, `RAG_POOL_SIZE`, `RAG_POPULARITY_PENALTY`, `RAG_STRATIFIED`, `RAG_FACET_WEIGHTS`, `RAG_MANIFEST_URL`) DO exist in `config.py` and are used; only `BATCH_SIZE_WITH_RAG` and `get_effective_batch_size()` are truly dead (per `result-improvement.md` they were never shipped). Removed dead-name references and fixed `RAG_POOL_SIZE` value drift (docs claimed 100, code has 60) across `TechnicalManual.md`, `UserManual.md`, `help.en.md`, `help.de.md`, `help.jp.md`.
- **S3** — judgement call: `meta.goal` IS populated end-to-end (the LLM training prompt instructs the model to set it; `profile.py:440` validates it as a string). The `meta_goal_chars` telemetry was already correctly removed in the 2026-04-28 fix. Cleaned up stale comments in `eval_log.py` that still implied the field was broken.
- **S7** — removed the dead `_STAGE3_JSON_SCHEMA` constant (~50 LOC) and `_stage3_response_format()` helper from `core/src/suggestions.py`; tightened the call-site comment. Updated `result-improvement.md` to note the removal (recover via git history if a future experiment needs them).
- **P6-DOC-SCRIPT-MIDRUN-EDIT** — added warning header to `evaluation/run_pool_sweep.sh`.
- **P6-DOC-RECOVERY** — added "Recovering from an aborted sweep" section to `evaluation/README.md`.
- **N5** — superseded banner added to `analysis.md`.
- **N6** — `evaluation/README.md` 30-track → 15-track fix.
- **N7** — `SKILL.md` git-commit-and-push: prefixed with no-auto-commit reminder.
- **S5** — `dislike_track`: case-insensitive (artist, track) dedup on track-level dislike.
- **S6** — `_NO_TEMPERATURE_MODELS` moved to `config.OPENAI_NO_TEMPERATURE_MODELS`.
- **S12** — `_migrate_flat_profiles`: path-keyed `_MIGRATED_DIRS` cache; one glob per process per profiles dir.
- **S13** — `EMPTY_PROFILE` / `TRAINED_PROFILE` consolidated into `frontend/tests/_shared.py`; helpers re-export.
- **N1** — `_auth_status_cache` now caches negative results (`not_configured`, `not_authenticated`) with the same TTL.


## A1. User feedback of current implementation state

Results are unacceptable. Multiple improvement iterations failed. See C:\Users\micha\AppData\Local\spotyvibe\debug. Hitrate is abysmal. A full rework is required.

RAG severely degraded recommendation quality. Prompt changes and prompt engineering did not fix it. Evaluation benchmarks are misleading. OpenAI GPT-5.4-mini scored best in tests but failed in production: only 5 songs returned, poor profile matching, multiple instructions ignored.

Current quality is not viable. We invested significant time and effort and the system still fails at a fundamental level.

Removing RAG, Cloud Run, and the entire current infrastructure/workflow must be considered. If quality and cost remain at this level, the product is unusable and should be scrapped. The current system has no viable future.

The provided folder contains:

- user profile
- prompts
- disliked tracks

More than 99% of recommendations failed to match the profile or user taste. After profile updates, the next run still recommended previously disliked bands. This is a critical failure in memory, filtering, or retrieval logic.

We need a complete diagnosis of the pipeline:

- retrieval
- ranking
- profile handling
- memory updates
- prompt injection flow
- filtering
- instruction adherence

Collect more data. Add full tracing and observability. Log every stage of the pipeline. Identify exactly where degradation occurs. If possible, capture reasoning/traces from model clients to understand why outputs are failing so severely.

## found bugs

- [] playback stuck. Removed track, but it keeps playing. Other tracks cannot be played because of that. 
- [] clicking the save button in the settings sometimes takes a while. But the user has no indication that something is happening. Provoking multiple clicks on Save due to that. 
