# TODO — Deferred Code-Review Items (2026-04-28)

Items identified during the code-review pass but deferred. Pick these up in a future session.

---

## 🔴🔴 Phase 6.0 follow-ups (2026-04-29) — pick up here when resuming cost work

Context: 5-block pool-size sweep landed (`evaluation/results/sweep-merged-5blocks/report.md`).
The L1+L8+L11+L16 cost-reduction bundle was implemented and unit-tested (1121 / 1121 core
tests pass), but the **validation eval was not run** before the session ended.
Full lever analysis lives in `cost-speed-research.md` (26 levers scored).
Phase summary in `result-improvement.md` §"Phase 6.0".

### P6-EVAL — Bundle validation eval (REQUIRED before any further L-work)

**What:** confirm L1+L8+L11+L16 didn't regress quality on the canonical seed.

**Run:**
```bash
cd /c/git/spotyvibe/evaluation
POOLS="50" BLOCKS=5 bash run_pool_sweep.sh
```
Expected wall-clock: ~75 min (5 runs × ~7 min eval + 8-min cooldowns). Produces a new
`evaluation/results/sweep-<UTC-ts>/` with `report.md` + `summary.csv`.

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

### P6-INV13-25 — L13 + L25 combined investigation sweep (queued 🟡)

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

### P6-FRONTEND-CORRUPTION — Restore broken frontend test files

Two files are still in a corrupted state from a previous AI session (orphan paste +
inter-method line scrambling — same pattern that broke `suggestions.py` and
`eval_log.py`, but those were fixed surgically). Diff stats prove it's working-tree
garbage that doesn't parse:

| File | Diff size | Status |
|---|---|---|
| `frontend/tests/test_edge_cases.py` | 59 lines changed | does not parse |
| `frontend/tests/test_page_load.py` | 55 lines changed | does not parse |

**Fix (one command):**
```bash
git checkout HEAD -- frontend/tests/test_edge_cases.py frontend/tests/test_page_load.py
```

**Why deferred from session 2026-04-29:** project rule forbids destructive git
commands (`restore`, `checkout --`, `reset`, `clean`) without per-message permission.
The user must execute or explicitly authorise.

**After fix:** run `bash build-tools/run_frontend_tests.sh` to confirm; expected
~233 tests pass (matching `bash build-tools/run_tests.sh frontend` baseline).

### P6-DOC-SCRIPT-MIDRUN-EDIT — Don't edit `run_pool_sweep.sh` while a sweep is running

**Lesson learned 2026-04-29:** mid-run edits to `evaluation/run_pool_sweep.sh` cause the
running bash process to misread byte offsets when control returns to the loop end (bash
reads the script lazily for some constructs). This crashed an otherwise-successful sweep
right before the post-processing step.

**Fix:** add a one-line note to the top of `evaluation/run_pool_sweep.sh`:
```
# WARNING: do NOT edit this script while a sweep is running. Bash re-reads
# the file on loop exit; line-offset shifts cause "syntax error near unexpected
# token" failures during post-processing. Apply edits between sweeps only.
```

### P6-DOC-RECOVERY — Document the manifest-merge recovery procedure

The session recovered an aborted sweep by hand-merging two `manifest.tsv` files into
`evaluation/results/sweep-merged-5blocks/manifest.tsv`, then re-running the existing
aggregator/renderer. This is a recoverable pattern that's currently undocumented.

**Add to `evaluation/README.md`:** a 10-line "Recovering from an aborted sweep" section
showing the awk-filter command (`awk -F'\t' 'NR>1 && NF==7 {print}'` for the older
"0\n0" bug), header preservation, and the two-step aggregate+render commands. Reference
implementation: see git log for `evaluation/results/sweep-merged-5blocks/` creation.

---

## 🔴 Needs a decision before fixing

### D1 — `spotify_metadata.py` violates "Spotify in playlist.py only"
**Rule:** `AGENTS.md` / `CLAUDE.md` both mandate all Spotify API calls in `core/src/playlist.py` only.
`core/src/spotify_metadata.py` hits `https://accounts.spotify.com/api/token` and
`https://api.spotify.com/v1/...` via `urllib` independently.

**Options:**
- Move the module's public helpers (`search_*`, `get_*_metadata`, `get_client_credentials_token`)
  into `playlist.py` (or an explicitly allowed sibling). ← recommended
- Document the deviation as an authorised exception in `CLAUDE.md` / `AGENTS.md`.

---

### D2 — `TechnicalManual.md` + `UserManual.md` describe removed RAG config constants
Several docs claim config constants that do **not** exist in `config.py`:
`RAG_ENABLED`, `RAG_CORPUS_PATH`, `RAG_POOL_SIZE`, `RAG_POPULARITY_PENALTY`,
`RAG_STRATIFIED`, `RAG_FACET_WEIGHTS`, `RAG_MANIFEST_URL`, `BATCH_SIZE_WITH_RAG`,
`get_effective_batch_size()`.

The same false claim appears in:
- `documentation/TechnicalManual.md` lines ~254–292 ("RAG candidate-pool feature" section)
- `documentation/UserManual.md` lines 174–178 ("Local LLM note")
- `documentation/help.en.md` line ~607
- `documentation/help.de.md` line ~610

**Question:** Were these constants intentionally removed (docs are wrong → rewrite to match
staged-pipeline reality) or accidentally lost (code is wrong → restore constants)?
Only `RETRIEVE_CANDIDATES_SIZE = 40` survives in `config.py`.

---

## 🟡 Should-fix — no decision needed, just work

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

### S3 — `eval_log.py`: `_profile_section_sizes` — `meta.goal` never populated
`meta_goal_chars` will always be 0 because nothing in the codebase sets `meta.goal`.
Either remove the field from the telemetry row, or implement the `meta.goal` concept
(requires a product decision on what "goal" means).

### S4 — Hardcoded English error strings raised to the UI (i18n sweep)
Backend exceptions whose messages surface directly in the UI:
- `playlist.py:840` — 403 reconnect message
- `openai_http.py:94–97, 275–278` — config + unsupported-model errors
- `suggestions.py:433, 438` — empty/invalid AI response messages
- `analysis.py:38` — "Artist name is required."

These should carry an i18n key so the frontend can translate them.
Pattern: raise a structured error with a `key` attribute + English fallback;
frontend looks up `i18n(error.key, error.message)`.

### S5 — `dislike_track`: track-level duplicate check missing (only artist-level was fixed)
Track-level dislikes (`profile["feedback"]["disliked_tracks"]`) have no dedup guard;
a user can press "dislike" on the same track multiple times and get N identical entries.
Add the same case-insensitive normalisation used for artist-level rejections.

### S6 — `openai_http.py`: `_NO_TEMPERATURE_MODELS` set is empty — dead branch
`core/src/openai_http.py` lines ~286–292: the set is always empty (noted in comment).
The branch is unreachable code. Either remove or move to config so it can actually
be populated when the next reasoning-tier model arrives.

### S7 — `suggestions.py`: 80-line `_STAGE3_JSON_SCHEMA` is dead code
Lines ~100–183: the json_schema variant was reverted; the schema and
`_stage3_response_format()` helper are unreachable. Either delete (use git history
to retrieve) or add a unit test proving consistency with the live prompt.

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

### S12 — `_migrate_flat_profiles` runs on every `load_profile` call
`core/src/profile.py` lines ~76–146: `ensure_profile()` is called on every request;
it calls `_migrate_flat_profiles()` which globs all `PROFILES_DIR/*.json` each time.
Add a module-level "already migrated this process" flag.

### S13 — Consolidate `EMPTY_PROFILE` / `TRAINED_PROFILE` constants into one shared module
`frontend/tests/helpers.py:174–198` and `helpers_integration.py:81–105` define these
twice with subtle drift risk. Move to `frontend/tests/_shared.py`.

---

## 🟢 Nice-to-have / polish

### N1 — `_auth_status_cache` doesn't cache the negative result
`core/src/playlist.py` lines ~198–204: on failure the cache slot is set to `None`,
so every failed status poll re-validates the token. With 1 req/sec polling from the
frontend this is unnecessary network traffic. Cache `"not_authenticated"` with the
same TTL.

### N2 — JS `addEventListener` leak in `quickstart-demo.js`
`frontend/static/js/modules/quickstart-demo.js`: `_openLightbox` adds a `keydown`
listener on every open call. Verify that the matching `removeEventListener` fires on
close; add it if not.

### N3 — Onboarding i18n: several hardcoded English strings / aria-labels not yet wired
`frontend/templates/onboarding.html` has ~10 hardcoded strings/aria-labels that have
matching or close-enough i18n keys but lack `data-i18n*` wiring. See full list in the
2026-04-28 frontend code-review report.

### N4 — `help.de.md` uses localised anchor IDs; `help.en.md` / `help.jp.md` use English ones
`/api/help/section/<anchor>` deep-links will 404 in German because the German file
uses `#erste-schritte` while the UI may request `#getting-started`. Normalise all
three files to use English anchors for stable cross-language deep-linking (`help.jp.md`
already does this correctly).

### N5 — `analysis.md` is pre-rework (2026-04-21) and superseded by `result-improvement.md`
Add a one-line banner at the top of `analysis.md`:
> _Status (2026-04-28): superseded by `result-improvement.md` Phase 2.6 / Scenario decisions. Kept as historical reference._

### N6 — `evaluation/README.md` line 20 says "30-track playlist" but baseline is 15 tracks
Update to: "Generates a 15-track playlist (configurable via `evaluation/scenario.py`)."

### N7 — `SKILL.md` `SKILL: git-commit-and-push` section should note the no-auto-commit rule
Add a prefix: "This procedure is invoked **only** when the user explicitly says 'commit and push'.
The agent must never initiate it autonomously."

