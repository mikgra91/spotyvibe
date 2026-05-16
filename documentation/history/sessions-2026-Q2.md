# Sessions archive — 2026 Q2 (May)

Chronological record of completed sessions, gated experiments retired, and Tracks A/B research. Migrated from the bottom of `../../next-steps.md` on 2026-05-16 — kept for traceability of "which change produced which delta". For active work see `../../next-steps.md`; for per-fix headline log see `../../evaluation/baselines/HISTORY.md`.

---

## Historical context — finished work below

The remainder of this file is the chronological record of completed
items (✅), gated experiments retired (🛑), and the original 2026-05-04
plan structure. Kept for traceability of "which change produced which
delta?". For new work, start from OPEN-1 above and consult
`evaluation/baselines/HISTORY.md` for per-fix detail.

## 🎯 Next logical steps (post-2026-05-12 — Tracks A+B fully shipped)

Tracks A (verifier decoupling) and B (synthetic probes) are functionally
complete: probe runner + 8 probes + fingerprint diff + `--probe-check`
gate; `Spotify` / `Null` / `Overlay` / `l0_l1` verifier modes with the
push-step gated per S.6 #1; SQLite-cached MB + Last.fm verifiers;
`evaluation/late_verify.py`; multi-scenario resume-aware overlay
rebuild script. 1032 core tests green. **The remaining work is
operational (real budget spend), validation runs (Phase 3), and two
production-code follow-ups that the captured fingerprints made
obvious.** Pick the next item by what investigation you're running.

### ✅ N1 — A6 trigger condition widening (production fix, surfaced by B-11) — DONE 2026-05-13
The B-11 fingerprints captured 2026-05-12 showed **every model
confabulates** when `len(approved_artists) == 1` and that artist has
no `known:` tracks (bucket_c on mini / gpt-5.4 / gpt-4.1 alike). The
system prompt's "OMIT that artist unless you are sure of a real
released track" rule was being ignored at the single-artist boundary.
**Shipped:** [core/src/suggestions.py](core/src/suggestions.py)
`select_tracks()` now refuses early — without an LLM call — when
`len(approved_artists) == 0` OR `len(approved_artists) == 1 AND no
`known:` tracks anywhere in the overlay`. Returns the standard empty
result + meta with `refusal_reason ∈ {"empty_pool",
"single_artist_no_known"}`. Logs at WARNING. Coverage: 5 new tests in
`TestSelectTracksA6PoolStarvationRefusal` (empty pool refusal,
single-no-known refusal, single + empty-list-overlay refusal,
single + known tracks NOT refused, two artists no overlay NOT
refused). Five existing single-artist tests updated to two artists
or to pass overlay so they exercise the LLM path (no behavior loss).
1037 core tests green. **Validation pending (real budget):**
`python -m evaluation.probes --model gpt-5.4-mini --probes B-11
--confirm` should now show `bucket_a` on the
`single_artist_no_known` variant; ~$0.001 estimated.

### ✅ N2 — `iterations` default bump (config fix, surfaced by B-6) — DONE 2026-05-13
B-6 `n_required_for_5pp_signal` per model: gpt-4.1 = 5, gpt-5.4 = 19,
gpt-5.4-mini = 85. Previous `iterations = 3` in
[evaluation/settings.ini](evaluation/settings.ini) was below every
model's variance floor. **Shipped (option a + override seam):**
default bumped 3 → 5 in `settings.ini` and `settings.ini.example`
(clears gpt-4.1; explicit comment block documents the higher floors
for the other models). New `--iterations <n>` CLI flag on
[evaluation/run_evaluation.py](evaluation/run_evaluation.py) lets an
investigator override per-run (e.g. `--iterations 19` for a tight
gpt-5.4 signal). `evaluation/README.md` gained a per-model
recommendation table sourced from the v1 fingerprints with a refresh
note pointing at the B-6 probe. **Option (b) deferred:** wiring the
fingerprint into the harness to auto-scale would push mini runs to
85× = ~$8.50 per scenario; not worth the implicit cost — the manual
override gives the same control with a one-line CLI argument.
1037 core tests green.

### 🟠 N3 — Phase 3 validation runs (per §S.5 items 9-10)
**Status (2026-05-13):**
- ✅ **Track B Step 5 DONE** — gpt-5.4-mini + gpt-5.4 probe batteries
  vs v1 baseline showed **0 true regressions** (gpt-5.4-mini: 2
  noise-flags within tolerance + 2 improvements on B-1; gpt-5.4:
  improved B-6 `n_required_for_5pp_signal` 19 → 13). R1.4 (model-
  conditional omission rule) ships unchanged. See
  `evaluation/baselines/HISTORY.md`.
- ✅ **N3a / N3b / N3c — infrastructure unblocked** —
  `prepare_sandbox(require_spotify_cache=False)` +
  `SPOTYVIBE_SKIP_SPOTIFY_CONNECT=1` env-seam + `iter_search_tracks`
  verifier-precedence bug-fix. The harness now runs end-to-end
  on a machine without `.spotify-cache` when verify_mode is
  null / overlay / l0_l1. 1045 core tests green.
- ✅ **N3d — null-uri dedup bug-fix (2026-05-13)** — Track-A
  verifier-swap surfaced a second latent bug: [app.py
  run_pipeline()](app.py#L1412-L1432) deduped accumulated tracks by
  `t["uri"]`, but `NullVerifier` (and any future verifier that does
  not resolve a Spotify URI) returns `uri=None` for every track. The
  set-of-URIs then contained a single `None` after the first track
  and every subsequent track was silently dropped — a cache-less Null
  eval reported `playlist=1` for every iter regardless of how many
  picks Stage 3 produced. Fix: fall back to a case-folded
  `(artist, track)` dedup key when the URI is falsy. Production path
  with `SpotifyVerifier` is unchanged (URIs are unique). Regression
  test in [test_app.py
  TestNullUriDedupeRegression](core/tests/test_app.py): 10 distinct
  picks with `uri=None` must all survive the dedup pass. **Post-fix
  cache-less eval (10 iters, 2 models, `--verify-mode null`,
  `evaluation/results/20260513-081434/`):** mean playlist size 13.6
  (vs 1.0 pre-fix); `gpt-5.4` averaged 15/15 on A and 11/15 on B,
  `gpt-5.4-mini` averaged 14.8/15 on A and 11/15 on B; B-leakage
  pass=10/10 (no rejected-artist / disliked-track / dislike-pattern
  hits); decade-avoid fit-check pass=10/10. Total wall: 762.9 s,
  total cost: $1.43. 1046 core tests green.
- ✅ **Track A Step 7 DONE 2026-05-13** — three-mode side-by-side
  baseline ran at n=5 × 2 models per mode:
  `null` → `evaluation/results/20260513-081434/`,
  `spotify` → `evaluation/results/20260513-090518/`,
  `l0_l1` → `evaluation/results/20260513-110357/`. Verdict:
  **keep `verify_mode=spotify` as production default; park `l0_l1`**
  (regresses must-have-cite by −1.7 pp despite +6.5 pp Spotify-found
  and −30 % wall time). Full rationale, headline table, and "what to
  fix instead" recommendations are in
  [documentation/VerifyModes.md](documentation/VerifyModes.md) (new).
  Locked sqlite verify-cache from the run was cleaned up manually.

### 🟠 N4 — Multi-scenario overlay rebuild (operations, S.6 #4)
Code is shipped (`build_top_tracks_overlay.py --scenarios all --resume
--throttle-ms 2000`). **Trigger needed:** estimated ~5 000 Spotify
calls over 1-3 sessions; ≥ 2.0 s/call throttle keeps you under the
rolling-window quota. Without this, `--verify-mode overlay` and the
L0 leg of `--verify-mode l0_l1` have lower hit rates on niche
scenarios. No deadline; spread across multiple sessions as quota
permits.

### 🟡 N5 — Coverage of the local-LLM fingerprint slot
Track B's Step 3 captured cards for the three OpenAI models. The
locked plan calls out "plus one local LLM (Ollama)" as the fourth
baseline. Skipped because no local model is currently part of the
eval roster. Land this **only** when a local model lands in
`evaluation/settings.ini`.

### 🟢 N6 — Documentation refresh
Each of the above leaves user-facing docs untouched. Once N3 lands
(validation numbers in hand), refresh
[documentation/TechnicalManual.md](documentation/TechnicalManual.md)
with the verifier-mode matrix, the probe-gate workflow, and the
recommended-n table. Out of scope until validation data exists.

---

> **Documentation cleanup (2026-05-04):** Six working documents were consolidated
> into `documentation/TechnicalManual.md` and this file, then deleted. See
> TechnicalManual.md §"Documentation Cleanup Log" for the full list. All deleted
> files are recoverable via git history.

## Active priorities

### 🔴 P0 — Unblock eval & ship enrichment Phase A

These have no enrichment dependency and gate everything else.

1. ~~**S14 — Spotify OAuth cache hardening.**~~ ✅ Done 2026-05-02.
   `get_spotify_auth_url()` now calls `CACHE_FILE.unlink(missing_ok=True)`
   before generating the authorize URL ([core/src/playlist.py:267-276](core/src/playlist.py#L267-L276)),
   eliminating the `400 invalid_client` reconnect failure. Coverage:
   `test_clears_stale_cache_before_authorize` + `test_no_cache_does_not_raise`
   in [core/tests/test_playlist.py](core/tests/test_playlist.py); three new
   keychain-branch tests in [core/tests/test_config.py](core/tests/test_config.py)
   (`test_keyring_branch_stores_secret_and_writes_empty_placeholder`,
   `test_keyring_branch_deletes_on_empty_value`,
   `test_keyring_failure_falls_back_to_dotenv`). 687 core tests green.
2. ~~**Update [evaluation/settings.ini](evaluation/settings.ini).**~~
   ✅ Done 2026-05-02. `models = gpt-5.4,gpt-5.4-mini,gpt-4.1,gpt-4.1-mini`.
   `gpt-5.5` was already absent (removed Phase 2.6); `gpt-4o` dropped
   pending fresh post-enrichment baseline. Same change mirrored in
   [evaluation/settings.ini.example](evaluation/settings.ini.example) so
   the template stays in sync. Cost-estimate table in
   [evaluation/run_evaluation.py:139-145](evaluation/run_evaluation.py#L139-L145)
   left intact — `gpt-4o` row is harmless reference data and the lookup
   falls back to `0.05` if a user re-adds it.
3. ~~**Phase A — fix Spotify enrichment**~~ ✅ Done 2026-05-02.
   Replaced removed batch `GET /artists` with per-id
   `GET /artists/{id}` in
   [build-tools/spotify_enrichment/client.py](build-tools/spotify_enrichment/client.py);
   dropped dead `popularity` / `followers` from `SpotifyArtist`,
   `MatchCandidate`, `score_candidate`, `pick_best_match`,
   [enrich_with_spotify.py](build-tools/enrich_with_spotify.py),
   `ArtistRow` / `RagCorpus._iter_rows` in
   [core/src/rag/corpus.py](core/src/rag/corpus.py), and the
   `spotify_popularity` branch of `_artist_popularity()` in
   [core/src/rag/retrieval.py:402-410](core/src/rag/retrieval.py#L402-L410)
   (now returns the MB `listener_popularity` proxy alone until Phase B
   Last.fm `listeners`/`playcount` lands). Tests rewritten:
   `test_spotify_popularity_overrides_proxy` deleted (no signal left),
   `test_mixed_legacy_and_enriched_corpus` regrounded on the proxy,
   `test_spotify_enrichment.py` + `test_rag_corpus.py` updated for the
   slimmed schema. Docs synced:
   [TechnicalManual.md](documentation/TechnicalManual.md) §RAG schema
   row + Cloud Run pipeline step 2,
   [cloud-run-rag-setup.md](documentation/guides/cloud-run-rag-setup.md)
   §9.4. 686 core tests green (was 687, minus the deleted Spotify
   popularity test).

### 🟠 P1 — Eval workflow rework (independent of corpus)

Eval gap: current eval does **not** test the production failure path
(disliked-band re-recommendation after profile update). This is the
single biggest reason "evals pass while production fails" per
the user feedback note (formerly TODO.md A1).

4. ~~**Add post-feedback regression pass to eval harness.**~~
   ✅ Done (F8, commit 7f0c6af + earlier).
   [evaluation/harness.py:551-590](evaluation/harness.py#L551-L590)
   generates playlist B on the post-feedback profile;
   [evaluation/leakage.py compute_leakage()](evaluation/leakage.py)
   audits playlist B against `artists.rejected` (rejected_artist),
   `feedback.disliked_tracks` (disliked_track), and the
   ≥3-distinct-tracks dislike-pattern rule.
   [evaluation/fit_checks.py](evaluation/fit_checks.py) adds the
   independent `decade_avoid` oracle. Both report into
   `summary.json`. Pass/fail surfaces in
   [reporting.py](evaluation/reporting.py). Completion-< 95 %
   tracking moves to item #5.
5. ~~**Hard completion gate.**~~ ✅ Done 2026-05-02.
   New `COMPLETION_THRESHOLD = 0.95` + `_completion_status()` helper
   in [evaluation/harness.py](evaluation/harness.py); two new
   `completion_a_status` / `completion_b_status` fields on
   [ModelRunResult](evaluation/harness.py#L46) classify each playlist
   as `ok` / `under` / `empty` / `skipped` independent of the
   semantic `playlist_status` (which still records the production
   `under_filled` anti-confab signal). Surfaced as a new "playlist
   completion" table in [reporting.py](evaluation/reporting.py)
   `comparison.md`. 8 unit tests in
   [test_evaluation_harness.py](core/tests/test_evaluation_harness.py)
   pin the threshold + boundary + zero-target cases.
6. ~~**Stateful profile eval.**~~ ✅ Done 2026-05-02.
   `Scenario` gained an optional `seed_profile_path: Path | None`
   field ([evaluation/scenario.py](evaluation/scenario.py)); when
   set, the harness skips `train_profile(seed_sections)` and instead
   imports the JSON file via `import_profile_dict()` (new
   `_step_seed_profile()` in
   [evaluation/harness.py](evaluation/harness.py); status surfaces as
   `imported_fixture` so a stateful run isn't confused with a fresh
   train). New CLI flag `--seed-profile <path>` on
   [evaluation/run_evaluation.py](evaluation/run_evaluation.py)
   overrides any scenario's path at invocation time, so a real
   anonymised production profile can be swapped in without scenario
   changes — file-not-found fails before any OpenAI/Spotify quota is
   burned.
   Also added six coverage scenarios in the recommended priority order:
   `ambient_instrumental_focus` (S05), `boom_bap_90s` (S04),
   `brazilian_samba_funk` (S03), `club_techno_strict` (S12),
   `original_recordings_only` (S16), `contradictory_profile` (S19).
   Each is pure-data (no fixture file required) so the existing
   leakage + fit gates immediately apply. 7 unit tests in
   [test_evaluation_harness.py](core/tests/test_evaluation_harness.py)
   cover the new field default, replace() override,
   `_step_seed_profile()` happy-path + missing-file, registry
   completeness, required-field schema, and disjoint feedback
   indices on every new scenario. 735 core tests green (was 728).
7. ~~**Full per-stage trace snapshot per eval run.**~~ ✅ Done 2026-05-02.
   F9 [core/src/trace.py](core/src/trace.py) already records Stage 1
   candidates + reject reasons, Stage 2 in/out, Stage 3 raw +
   reasoning, Spotify verify, and profile snapshots into
   `<sandbox>/debug/<run_id>/trace.json` per generation. The harness
   now copies those bundles into the per-run results dir as
   `trace_A.json` / `trace_B.json` via `_copy_trace_bundle()` in
   [evaluation/harness.py](evaluation/harness.py); paths surface on
   `ModelRunResult.trace_a_path` / `trace_b_path` and as a new
   "F9 trace bundles" table in
   [reporting.py](evaluation/reporting.py) `comparison.md`. Returns
   `None` when DEBUG_MODE was off, so the eval never fails on a
   missing diagnostic. 4 unit tests in
   [test_evaluation_harness.py](core/tests/test_evaluation_harness.py)
   cover the existing-bundle, missing-bundle, falsy-run-id, and
   A/B-distinct-filename cases.

### 🟡 P2 — Phase B+ enrichment (after Phase A validates)

8. ~~**Phase B — Last.fm enrichment**~~ ✅ Code shipped 2026-05-03 (data
   refresh pending the next Cloud Run job execution).
   New [build-tools/lastfm_enrichment/client.py](build-tools/lastfm_enrichment/client.py)
   `LastfmClient` w/ `get_artist_info(mbid)` + `get_top_tags(mbid)` +
   exp-backoff + budget abort + dedicated `LastfmAuthError` /
   `LastfmRateLimitedError` exception types. New driver
   [build-tools/enrich_with_lastfm.py](build-tools/enrich_with_lastfm.py)
   adds `lastfm_listeners` / `lastfm_playcount` /
   `lastfm_tags: list[[name, weight]]` (weight ≥ 30 default cutoff)
   to each row, sorted by MB proxy popularity, with passthrough
   when `LASTFM_API_KEY` is unset or `DISABLE_LASTFM_ENRICHMENT=1`.
   Distinct exit codes: 43 (rate-limit → halt.flag) / 44 (auth-error
   → loud fail, no halt). `ArtistRow` in
   [core/src/rag/corpus.py](core/src/rag/corpus.py) gained
   `lastfm_listeners`, `lastfm_playcount`, `lastfm_tags`,
   `lastfm_tag_weights` fields; `_build_indices` now indexes Last.fm
   tags into `tag_index` alongside MB tags + Spotify genres.
   Retrieval helpers in [core/src/rag/retrieval.py](core/src/rag/retrieval.py):
   `_artist_tag_weight()` reads Last.fm 0-100 weights; new
   `_lastfm_popularity()` log10-scales raw listeners to 0..1 and
   `_artist_popularity()` prefers it over the MB proxy.
   Cloud Run integration: new `LASTFM_API_KEY` secret bound to the
   `spotivibe-rag-builder` job (Secret Manager → env var) on
   2026-05-03; [cloud_run_publish.py](build-tools/cloud_run_publish.py)
   runs `enrich_with_lastfm.py` between the Spotify enrichment step
   and the manifest assembly, wiring rate-limit (43) and auth-error
   (44) exits back to the circuit breaker. Dockerfile updated to
   COPY the new package + driver. **Out of scope this PR:**
   `getSimilar` similarity facet (deferred until Phase B data is
   validated in production), the runtime-time eval validation
   (gated on the next Cloud Run rebuild + new manifest).
   Tests: 19-test [test_lastfm_enrichment.py](core/tests/test_lastfm_enrichment.py)
   covers client init, both endpoints, 429 / 5xx / Retry-After
   safety cap / cumulative-budget abort, single-tag-dict
   normalisation, weight clamping, error-code routing.
   10-test [test_enrich_with_lastfm.py](core/tests/test_enrich_with_lastfm.py)
   covers the driver: passthrough on no key / DISABLE flag,
   max-enrich slicing, min-popularity skip, min-tag-weight CLI
   override, all three exit-code paths (rate-limit, budget, auth).
   Extended `test_rag_corpus.py` (4 tests) +
   `test_rag_retrieval.py` (4 tests) for the new fields +
   popularity precedence + tag-weight passthrough. 780 core tests
   green (was 723).
9. **Phase D — Wikidata structured facts** (rag_enrichment_plan.md §D (deleted; see git history)).
   Highest-value next layer because it directly fixes the F1 must-have
   gate failure for "Japanese music" / "American artists" documented in
   corpus_analysis.md (deleted; see git history). Order C↔D is flexible —
   take D first if eval scenarios remain country-constrained.
10. **Phase C — Discogs styles** (rag_enrichment_plan.md §C (deleted; see git history)).
    Broadens tag vocab where MB is sparse (electronic, hip-hop, niche).

### 🟢 P3 — Should-fix (independent of enrichment)

From next-steps.md:

11. ~~**S11 — `swap_profile_with_history` crash safety.**~~ ✅ Done 2026-05-02.
    Added `recover_orphaned_swap_tmps()` in
    [core/src/profile.py:292-340](core/src/profile.py#L292-L340) that
    scans `PROFILES_DIR/*/profile.json.swap.tmp` and rolls back (tmp →
    profile) or completes (tmp → history) the swap based on which
    siblings are present; ambiguous (both present) preserves tmp as
    `.bak` for inspection. Wired into startup at
    [app.py:173-179](app.py#L173-L179) wrapped in `try/except` so a
    corrupt profile dir never blocks boot. 5 unit tests cover step-1
    rollback, step-2 completion, ambiguous, no-op, and
    missing-PROFILES_DIR. 691 core tests green.
12. ~~**S4 — i18n sweep on backend errors**~~ ✅ Done 2026-05-03.
    New [core/src/errors.py](core/src/errors.py) with
    `TranslatableError(key, message, *, params, status_code)` +
    `as_response_payload(exc)` helper that builds
    `{error, error_key, error_params}` JSON. `OpenAIConfigError` /
    `OpenAIUnsupportedModelError` in
    [core/src/openai_http.py](core/src/openai_http.py) gained class-level
    `key` attrs so the existing exception types route through the same
    payload helper without behaviour change. Refactored sites:
    [core/src/playlist.py:849-859](core/src/playlist.py#L849-L859) 403
    reconnect path raises `TranslatableError("error.spotify.reconnect_required")`,
    [core/src/analysis.py:39-43](core/src/analysis.py#L39-L43) raises
    `TranslatableError("error.analysis.artist_required")`. Flask plumbing in
    [app.py](app.py): new `_sse_error()` helper + `as_response_payload`
    wired into `/api/run` SSE error events (5 keyed sites:
    `error.profile.not_trained`, `error.spotify.not_connected`,
    `error.run.gpt_exhausted`, `error.run.no_tracks_verified`, plus
    catch-all via `_sse_error`), `/api/analyze` and `/api/feedback`
    handlers. Frontend: new `localizedError(data, fallback)` helper in
    [frontend/static/js/modules/i18n.js](frontend/static/js/modules/i18n.js)
    that returns `i18n(error_key, error)` with `{name}` param
    interpolation; threaded through
    [analysis.js](frontend/static/js/modules/analysis.js#L66),
    [review.js](frontend/static/js/modules/review.js#L60),
    [pipeline.js](frontend/static/js/modules/pipeline.js) SSE error
    handler. 9 new i18n keys added across en/de/jp; parity test green.
    Tests: 7-test [test_errors.py](core/tests/test_errors.py) covers the
    helper happy-path, params propagation, plain-exception passthrough,
    OpenAI subclass key attrs, and blank-key omission;
    `test_analysis.py` + `test_playlist.py` updated to assert the new
    `TranslatableError` types and keys. 723 core tests green (was 716).
13. ~~**S10 — i18n on hardcoded ARIA labels with interpolated artist/track
    names**~~ ✅ Done 2026-05-02.
    Added the missing `data-i18n-attr` applier in
    [frontend/static/js/modules/i18n.js](frontend/static/js/modules/i18n.js)
    (parses `attr1:key1,attr2:key2` form). Dropped per-track artist/title
    interpolation from the SSR `aria-label` fallback in
    [frontend/templates/generate_section.html:305-310](frontend/templates/generate_section.html#L305-L310)
    so the SSR string matches the i18n key (the visible button text in
    the same row already carries the artist/title context for screen
    readers).
14. ~~**S8/S9 — Test coverage gaps**~~ ✅ Done 2026-05-02.
    **S8** — added `TestLooksLikeSchemaRejection` to
    [core/tests/test_openai_http.py](core/tests/test_openai_http.py)
    (7 direct tests over the heuristic itself: empty body, OpenAI-style
    "is not supported", LM Studio "does not support", invalid
    response_format, case-insensitivity, three unrelated 400s, bare
    "invalid"/"unsupported" without schema/format keyword). Locks the
    auto-downgrade gate that protects every Ollama / LM Studio / Groq
    user.
    **S9** — added `TestValidateProfileSchema` (12 tests) +
    `TestImportProfileDict` (5 tests) to
    [core/tests/test_profile.py](core/tests/test_profile.py) covering
    type rejection, unknown-key stripping, length caps, list-of-string
    enforcement, history truncation, and the import round-trip with
    template merging + control-char sanitisation. 716 core tests green
    (was 691, +25).
15. ~~**S1/S2 — Frontend flake fixes**~~ ✅ Done 2026-05-02.
    Extended the autouse `_reduce_timeouts` fixture in
    [frontend/tests/conftest.py](frontend/tests/conftest.py) to inject a
    persistent test-overrides `<style>` tag on every page load that
    (a) hides `#ragUpdateTip` with `display:none !important` so the
    dynamically-injected toast never intercepts modal-button clicks
    (S1), and (b) zeroes all CSS transitions + animations so toggle
    tests asserting visibility right after a click no longer race the
    slide animation (S2). Verified by running the three previously
    flaky tests
    (`test_modals.TestHelpModal::test_closes_on_close_button`,
    `test_modals.TestSettingsModal::test_shows_model_dropdown`,
    `test_profile.TestProfileEditor::test_toggle_opens_and_closes_editor`)
    — all pass.

### 🟢 P4 — Nice-to-have polish (formerly in TODO.md)

18. ~~**N2 — JS addEventListener leak in quickstart-demo.js**~~ ✅ False positive
    (2026-05-04). Lightbox keydown listener is guarded by `if (!lb)` and
    properly cleaned up in `_closeLightbox`. No leak.
19. ~~**N3 — Onboarding i18n hardcoded strings**~~ ✅ False positive (2026-05-04).
    Provider badge is dynamically set via `obI18n('ob.step6_provider_note')`.
20. ~~**N4 — help.de.md localised anchor IDs**~~ ✅ Done 2026-05-04.
    All `<a id>` anchors and `href="#"` links in `help.de.md` normalised to
    English IDs matching `help.en.md` and `help.jp.md`. Cross-language
    deep-linking now works.

### 🐛 Found bugs

16. ~~**Playback stuck after track removal**~~ ✅ Done 2026-05-02 (CF-Bug-6).
    Added `onExternalTrackRemoved(idx, source)` in
    [frontend/static/js/modules/preview.js](frontend/static/js/modules/preview.js)
    and call it from `animateRemove` ([feedback.js](frontend/static/js/modules/feedback.js))
    + `animateReviewRemove` ([review.js](frontend/static/js/modules/review.js))
    BEFORE their state splices. When the removed idx matches the
    currently-previewed track: pause SDK / clear iframe src / stop
    ticker / reset `_sdkAdvanceFiredFor` / close overlay if visible —
    fixes the "preview keeps playing + new tracks won't start" lockup
    caused by the SDK's stuck "owns this track" state. When the
    removed idx is below the previewed one: decrement
    `currentPreviewIndex` so it keeps pointing at the same logical
    track post-splice.
17. ~~**Settings Save needs busy state.**~~ ✅ Done 2026-05-02 (CF-Bug-7).
    `saveSettings()` in
    [frontend/static/js/modules/modals.js:197-260](frontend/static/js/modules/modals.js#L197-L260)
    now disables the `.btn-save` element, sets `aria-busy="true"`, and
    swaps the label to `i18n('btn.saving', '⏳ Saving…')` immediately
    on click; a `finally` block restores the previous label + enables
    the button on success, error, and network failure. New i18n key
    `btn.saving` added to en/de/jp; `test_i18n_parity` green.

## 🚀 Phase B Cloud Run / operational state — 2026-05-04

First Phase B run (x4v5b, 2026-05-03) failed: Spotify enrichment got
0% matches (wrong credentials in Secret Manager — `400` on every token
request), Last.fm enrichment was uncapped (170k instead of intended
50k due to `--max-enrich` not being wired from env var to CLI).
Execution cancelled 2026-05-04.

### Fixes applied 2026-05-04

1. **Spotify credentials rotated** in Secret Manager — `spotify-client-id`
   v2 + `spotify-client-secret` v2 now match the working credentials
   from `settings.ini`. Verified locally via Client Credentials flow.
2. **`--max-enrich` env-var wiring** — `cloud_run_publish.py` now passes
   `SPOTIFY_MAX_ENRICH` and `LASTFM_MAX_ENRICH` env vars as `--max-enrich`
   CLI args to both enrichment scripts. When unset, the scripts use their
   defaults.
3. **Default changed to enrich ALL artists** — both `enrich_with_spotify.py`
   and `enrich_with_lastfm.py` now default `--max-enrich=0` (= all), not
   50k/170k. Partial enrichment biases toward mainstream and leaves the
   long tail (where RAG adds value) unenriched.
4. **Throttle reduced** — Spotify: 0.21s → 0.17s (~176 req/30s, within
   180-300 range). Last.fm: 0.21s → 0.18s (~5.5 req/s, within 5 req/s
   guideline). Saves ~6h per full run.
5. **Job downsized to free tier** — 2 vCPU / 8 GiB → 1 vCPU / 512 MiB.
   Enrichment scripts are I/O-bound (99% time in throttle sleep), not
   CPU/memory-bound.
6. **Scheduler changed to monthly** — `0 23 1 * *` Europe/Vienna (1st of
   each month at 23:00). `MIN_REBUILD_DAYS=25`. Free tier budget:
   ~29h × 1 vCPU = 29 vCPU-hours/month (of 50 free) + ~29h × 0.5 GiB
   = 14.5 GiB-hours/month (of 100 free). Zero cost.

**Cloud Run Job — `spotivibe-rag-builder` (region us-central1):**
- 1 vCPU, 4 GiB RAM, 24h timeout, max-retries 1.
- Env vars: `GCS_BUCKET=spotivibe-rag-corpus`, `CORPUS_TOP_N=350000`,
  `MIN_REBUILD_DAYS=25`, `DISABLE_SPOTIFY_ENRICHMENT=1`.
- Secrets: `LASTFM_API_KEY` v1.
- Image: `sha256:4106fd54…` (deployed 2026-05-04, includes all fixes).

**Cloud Scheduler — `spotivibe-rag-weekly`:**
- Schedule: `0 23 1 * *` Europe/Vienna (monthly, 1st at 23:00).
- Resumed 2026-05-04.

**Estimated run time (Last.fm only, all ~174k artists):**
- MB dump + build: ~13 min
- Last.fm: ~17h (348k calls at 0.18s throttle)
- Total: ~17.5h — well within 24h timeout and free tier (17.5 vCPU-hours
  of 50 free + 70 GiB-hours of 100 free at 4 GiB RAM).

### ✅ Corpus verified — 2026-05-06

Manifest `corpus_version=2026-05-06`, built `2026-05-06T10:43:54Z` from
execution `spotivibe-rag-builder-ctwgm`. No `halt.flag`. `gs://spotivibe-rag-corpus/artists.jsonl.gz`
(13.2 MB gz) → 174,200 artists. Phase B enrichment landed:

| Signal | Coverage |
|---|---|
| `lastfm_listeners` | 145,627 / 174,200 (83.6 %) |
| `lastfm_tags` (≥30 weight) | 116,007 / 174,200 (66.6 %) |
| Avg `lastfm_tags` per enriched row | 2.6 |
| Listener distribution | 16.4 % zero · 31.8 % <1k · 23.6 % 1k-10k · 19.7 % 10k-100k · 7.6 % 100k-1M · 0.9 % 1M+ |

Sample rows (Beatles 6.5M / Metallica 5.2M listeners) carry full
weighted tag vectors. **No Spotify fields by design** —
`DISABLE_SPOTIFY_ENRICHMENT=1` was respected. Schema field name is
`tags` (MB) + `tag_weights` (MB) + `lastfm_tags` (Last.fm name+weight
pairs). Listener proxy `listener_popularity` is present on every row.

App pickup: still on whatever local corpus the dev box last fetched.
Next app launch on a fresh Cloud Run-backed deploy will hydrate the
2026-05-06 manifest. Re-verify smoke after dev box pulls (`/api/rag/refresh`
or app restart that hits the manifest URL).



## 🚧 Active implementation handoff — 2026-05-06

> **For the next agent picking this up.** This section is
> self-contained: everything you need to continue is below. The full
> agenda is in the `## 🆕 Post-Phase B agenda` section further down;
> consult that for the rationale and ordering decisions.

### Session context — what the user asked for

The Last.fm-enriched corpus shipped 2026-05-06 (manifest
`corpus_version=2026-05-06`, 174 200 artists, 83.6 % Last.fm listener
data, 66.6 % weighted tag data — see "Corpus verified" section above).
With that unblocked, the user kicked off a session with these goals:

> **Continue analysis using new Last.fm corpus. Goal: harden app +
> significantly improve quality. Actions: design robust, repeatable
> evaluation tests → collect large-scale performance data; optimize UX
> + system performance.**
>
> **End goals:**
> - High-relevance recommendations.
> - Minimize perceived user cost (costs negligible / unnoticed).
> - Low-latency delivery (no user frustration).
> - Maximize responsiveness (optimize internal performance; mitigate
>   external LLM delays).
>
> **Process:** add newly identified tasks to next-steps.md for later
> evaluation.

The session triaged the agenda into "quick wins + E1 + E7" and the
user confirmed that scope. Work below is the result.

### Session deliverables — code shipped (2 commits)

All 820 core unit tests + 2 i18n parity tests green.

**Commit `4856de1`** — E1 per-stage telemetry + L2 search cache + L3
streaming generator (backend half).

**Commit `51b66fd`** — L3 SSE wire-up (app.py + pipeline.js + i18n) +
U1 focus/visibility re-check.

#### E1 — per-stage telemetry
[core/src/trace.py](core/src/trace.py) now exposes
`stage_metrics: {stage_name: {duration_s, calls, tokens_in,
tokens_out}}` on the bundle, plus four named-constant stage keys
(`STAGE_RAG_RETRIEVE`, `STAGE_STAGE2_AVOID`, `STAGE_STAGE3_SELECT`,
`STAGE_SPOTIFY_VERIFY`) and three helpers:

- `time_stage(stage)` — `with`-context wall-clock timer.
- `add_tokens(stage, tin, tout)` — accumulator.
- `stage_metrics_record(stage, duration_s, tokens_in, tokens_out)`
  — one-shot for sites that already measured locally.

Instrumentation:
- [app.py](app.py) wraps the `retrieve_candidates(...)` call in
  `time_stage(STAGE_RAG_RETRIEVE)`.
- [app.py](app.py) wraps the `iter_search_tracks(...)` consumer in
  `time_stage(STAGE_SPOTIFY_VERIFY)`.
- [core/src/suggestions.py](core/src/suggestions.py)
  `check_avoid_compliance` calls `stage_metrics_record(STAGE_STAGE2_AVOID,
  duration_s, tokens_in, tokens_out)` after the LLM call.
- [core/src/suggestions.py](core/src/suggestions.py) Stage 3 inside
  the per-batch trace block calls `stage_metrics_record(STAGE_STAGE3_SELECT,
  ...)` per batch — duration/tokens accumulate across all batches.

Surface:
- [evaluation/harness.py](evaluation/harness.py) gained
  `_extract_stage_metrics(trace_path)` and
  `ModelRunResult.stage_metrics_a/b` fields, populated immediately
  after each `_copy_trace_bundle` call.
- [evaluation/reporting.py](evaluation/reporting.py) renders a new
  `## Per-stage breakdown (E1)` table in `comparison.md`, split by
  playlist A / B, with stage rows for any of the four canonical stages
  the run actually exercised.

Tests: 7 in `TestStageMetrics` ([test_trace.py](core/tests/test_trace.py))
+ 6 in `TestExtractStageMetrics` + 2 in `TestStageMetricsFieldsOnResult`
([test_evaluation_harness.py](core/tests/test_evaluation_harness.py)).

#### L2 — per-run Spotify search-result cache
[core/src/playlist.py](core/src/playlist.py) gained
`_RUN_SEARCH_CACHE` module-level state, plus
`start_run_search_cache()` / `end_run_search_cache()` lifecycle
hooks. The cache key is `f"{artist.lower().strip()}|{track.lower().strip()}"`
(same shape as the in-call dedup). Caches both `found` (just the
Spotify-derived enrichment fields, *not* caller-supplied fields like
GPT genres) and `not_found`. Bracketed in [app.py](app.py) around the
SSE generation try/finally so cancellations / errors never leave
stale state.

Tests: 6 in `TestSearchTracksRunCache` ([test_playlist.py](core/tests/test_playlist.py)).

#### L3 — streaming SSE per-track verify
[core/src/playlist.py](core/src/playlist.py) refactor:

- New module-level `_dedup_tracks_for_search(tracks)` (one source of
  truth for the dedup shape).
- New module-level `_do_spotify_search(t, sp)` — the per-track
  search body extracted from the old `search_one` closure. Carries
  L2 cache check + populate, 429 retry, and the `found`/`not_found`
  return contract.
- New `iter_search_tracks(tracks)` generator — fans out across the
  same `ThreadPoolExecutor`, yields `("found", enriched_with_release_year)`
  / `("not_found", label)` per `as_completed` future.
- `search_tracks(tracks, on_progress=None)` is now a thin wrapper:
  consumes `iter_search_tracks`, accumulates into `(found, not_found)`
  lists, fires `on_progress(completed, total)` per yield, calls
  `_enrich_tracks_with_metadata(found)` as a no-op safety net at end
  (idempotent — sets `release_year` only if absent).

[app.py](app.py) per-batch verify path now consumes
`iter_search_tracks(...)` directly inside the
`time_stage(STAGE_SPOTIFY_VERIFY)` block. For each `("found", track)`
yield it emits `_sse("track_verified", track={artist, track, uri,
cover_url, preview_url, spotify_url, release_year}, count=<cumulative>,
total=<playlist_size>)`. The existing `batch_verified` SSE still
fires at end of batch so the "Use X tracks now" counter increments
per batch (frontend uses this).

[frontend/static/js/modules/pipeline.js](frontend/static/js/modules/pipeline.js)
`handleStreamEvent` gained `case 'track_verified':` that:
- Calls `updateUseTracksButton(event.count)` so the counter ticks
  per match.
- Renders an "⏳ Verifying… {count} of {total} tracks confirmed"
  status via the new i18n key `pipeline.verifying_progress`
  (en/de/jp all updated).

Test mocks in [test_app.py](core/tests/test_app.py) updated:
`@patch("app.search_tracks")` → `@patch("app.iter_search_tracks")`,
return value swapped from a `(found, not_found)` tuple to a
`side_effect=lambda *_a, **_kw: iter([("found", {...}), ...])`.

#### U1 — focus/visibility auth re-check
[frontend/static/js/main.js](frontend/static/js/main.js) gained
`_recheckAuthIfStale()` (30 s throttled) bound to
`visibilitychange` and `window.focus`. It calls `checkSpotifyAuth()
+ checkCredentialStatus() + renderComponentWarnings()`. The Generate
button is already gated by `warnings.js` on `State.spotifyAuthStatus`
— the new wiring just makes sure the auth state stays fresh while
the user has the tab open.

Click-time pre-flight (`runPipeline` line 81) and DOMContentLoaded
pre-flight (line 228) were already present in the codebase — they
did not need changes.

### What still remains

#### E7 — baseline run (BLOCKED on user go-ahead)

The reason E7 was scoped in but not executed: it costs real money
and burns real Spotify call quota. The user must explicitly say
"run E7" / "go E7" before kickoff.

**Command:** `python evaluation/run_evaluation.py`

**Cost & timing:** 4 models × 8 scenarios × 1 iter ≈ $3-8 OpenAI +
real Spotify rate budget, ~30-60 min wall clock. 1 iter (not 3) is
the minimum-cost variant — bump iterations in
[evaluation/settings.ini](evaluation/settings.ini) line 33 if
averaging is wanted.

**Output handling:** the harness writes to
`evaluation/results/<timestamp>/`. After completion, copy / rename
that run's `summary.csv` to
`evaluation/baselines/2026-05-06_lastfm.csv` (create the dir
first). The whole `<timestamp>/` dir also contains per-run trace
bundles — those carry the new E1 `stage_metrics` data needed to
size further L* / Q* optimisations.

**Pre-flight gates the user will likely want first** (suggested,
not blocking):

1. `python app.py` — generate a playlist locally and watch the SSE
   stream. Confirm `track_verified` events tick the counter
   visually instead of jumping batch-by-batch. Confirm the
   `comparison.md`-style trace bundle exists at
   `%LOCALAPPDATA%/spotyvibe/debug/<run_id>/trace.json` and
   contains `stage_metrics` populated for all four stages.
2. Disconnect Spotify in another tab while the app is open. Switch
   back to the app tab. Generate button should auto-disable within
   ~one tick of focus (U1 re-check).
3. Run the frontend Playwright suite if a UI regression worry
   warrants it: `bash build-tools/run_frontend_tests.sh`. Backend
   regressions are already covered by core tests.

If kicking off E7, monitor for:
- `LASTFM_API_KEY` rate-limit errors (shouldn't fire — eval doesn't
  call Last.fm at runtime).
- Spotify 429 cascade (L2 cache helps but isn't a guarantee under
  multi-model parallel workload — eval iterates models serially so
  this should be fine).
- Any new `error` SSE events that the harness might not yet
  recognise.

#### Items NOT touched this session (still queued in agenda)

The full Post-Phase B agenda below covers the rest. Specifically
these were scoped in but not executed (and don't block E7):
- **E2 / E3 / E4 / E5 / E6** — Last.fm-tag coverage metric, listener
  popularity distribution, three new scenarios. Recommend landing
  these BEFORE bumping E7 from 1 iter to 3 iters — otherwise the
  baseline misses the new corpus's load-bearing signals.
- **L4 / L5 / Q* / U2 / U3 / U4 / U5 / U6 / M2 / M3** — see agenda
  for prioritisation. None are blocked by the work this session
  shipped.

## 🆕 Session 2 deliverables — 2026-05-07

E2/E3/E4/E5/E6/L4 all landed before kicking off E7. Code summary:

#### E4 / E5 / E6 — three Last.fm-aware scenarios
[evaluation/scenario.py](evaluation/scenario.py) gained
`LASTFM_TAG_WEIGHTING_SCENARIO`, `NICHE_ONLY_STRICT_SCENARIO`,
`POST_FEEDBACK_TAG_REGRESSION_SCENARIO`. Each is pure-data; the
existing leakage + fit gates apply, and the new E2/E3 metrics surface
the Last.fm-specific acceptance signals in `comparison.md`.
Settings template ([evaluation/settings.ini.example](evaluation/settings.ini.example))
documents all three. Tests: 4 in `TestLastfmAwareScenarios`
([test_evaluation_harness.py](core/tests/test_evaluation_harness.py))
pin registry membership and load-bearing prose vocabulary; the
existing `test_each_scenario_has_required_seed_fields` and
`test_feedback_indices_are_disjoint` cover schema + disjoint-index
on every new scenario automatically.

#### E2 / E3 — Last.fm coverage + listener distribution
New module [evaluation/corpus_metrics.py](evaluation/corpus_metrics.py)
with `compute_corpus_metrics(tracks, corpus) → CorpusMetricsReport`.
Computes (a) Last.fm-tag coverage % over corpus-matched tracks
(gate: `LASTFM_TAG_COVERAGE_GATE = 0.75`), (b) listener-count median
+ p95 over enriched rows. `_FakeArtistRow`-shape lookup keeps the
public surface narrow so future field renames stay isolated.

Wired into [evaluation/harness.py](evaluation/harness.py): new
`_extract_corpus_metrics(tracks)` helper reads `suggestions.get_rag_corpus()`
(zero extra disk I/O — the production code already loaded the
corpus at app startup), populates `ModelRunResult.corpus_metrics_a` /
`corpus_metrics_b`. Surface in
[evaluation/reporting.py](evaluation/reporting.py): new
"Phase B coverage — Last.fm tags + listener distribution (E2/E3)"
section in `comparison.md`, split A/B with a ⚠ marker on rows below
the 75 % gate. Tests: 7 in `TestCorpusMetrics` + 2 in
`TestCorpusMetricsFieldsOnResult` + 2 in `TestExtractCorpusMetrics`
([test_evaluation_harness.py](core/tests/test_evaluation_harness.py))
cover empty/no-corpus/full-coverage/partial-coverage/unmatched-rows/
zero-listener-exclusion/JSON round-trip + `ModelRunResult` field
defaults + the `get_rag_corpus`-returns-None path.

#### L4 — prompt-template memoisation
[core/src/suggestions.py](core/src/suggestions.py) `load_text_file()`
now wraps a private `@functools.lru_cache(maxsize=32)` helper keyed
on the stringified path. `cache_clear()` / `cache_info()` are
re-exposed on the public name so a developer iterating on
`prompts/*.txt` in a long-lived process can force a re-read without
reaching into a private symbol. 1 new test in `TestLoadTextFile`
([test_suggestions.py](core/tests/test_suggestions.py)) verifies
the cache holds across a mid-session file mutation and `cache_clear`
forces the reload.

#### Multi-scenario support for E7
[evaluation/run_evaluation.py](evaluation/run_evaluation.py) gained a
`scenarios` (plural) settings field. Comma-separated list OR the
special value `all` (expands to every registry entry, default first).
Loop order: scenarios → models → iterations. Cost estimate scales
by `len(active_scenarios)`. Inter-model cooldown still fires between
consecutive runs (any scenario boundary). The per-run results
directory becomes `{scenario}__{model}-iter{n}/` for non-default
scenarios so multi-scenario runs don't collide on the same
`gpt-5.4-iter1/` slot ([evaluation/harness.py](evaluation/harness.py)).
[evaluation/settings.ini](evaluation/settings.ini) flipped to
`scenarios = all` for the E7 baseline; legacy single-scenario
runs work via the existing `scenario =` field.
[evaluation/reporting.py](evaluation/reporting.py) "Per-run rollup"
table gained a leading `Scenario` column.

#### Items NOT touched this session (still queued in agenda)

The full Post-Phase B agenda below covers the rest:
- **L5 / Q* / U2 / U3 / U4 / U5 / U6 / M2 / M3** — see agenda
  for prioritisation. None are blocked by the work this session
  shipped.

#### E7 attempt #1 aborted — Spotify rate-limit hardening (2026-05-07)

E7 was kicked off after the user re-authenticated Spotify; within the
first batch the parallel search pool burst-saturated the per-token
sliding-window quota and Spotify returned hard 429s past the
3-attempt back-off cap (max sleep 30 s). The user flagged the risk
that repeated bursty behaviour could get the account flagged. Run was
killed, lock released, orphan playlists swept.

**Root cause.** `_do_spotify_search` uses 5 parallel workers per
batch with no per-call delay. For one user during normal app use that
is fine; for a multi-scenario eval that fans out hundreds of searches
in close succession against the same token, it tips the rolling-window
guard within seconds.

**Code shipped:**

[core/src/playlist.py](core/src/playlist.py) gained two env-var hooks
(eval-only, default off — production users see no change):

- `SPOTIVIBE_SPOTIFY_SEARCH_SERIAL=1` → `_resolve_search_pool_size`
  forces `max_workers=1` so the `ThreadPoolExecutor` runs serially.
- `SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S=0.5` → `_post_search_throttle`
  sleeps after every search call (cache hit OR miss). Steady-state
  rate ≈ 2 calls/s, well under Spotify's documented ≤ 6/s per-token
  guidance.
- 429 back-off cap in `_do_spotify_search` raised from 30 s → 90 s
  when serial mode is on, so Retry-After headers up to 90 s are
  honoured before the per-call retry budget exhausts.

[evaluation/run_evaluation.py](evaluation/run_evaluation.py) sets both
env vars via `os.environ.setdefault` before importing the production
modules. Also added a 120 s **inter-scenario** cool-down (in addition
to the existing 60 s inter-model cool-down) so a multi-scenario run
gets a real "rolling window has fully drained" pause between
scenarios.

Tests: 9 in `TestSerialSearchModeResolvers`
([test_playlist.py](core/tests/test_playlist.py)) cover env-var
resolution (truthy / falsy / empty / unknown), pool-size resolver
(default cap, capped by track count, never zero, serial forces 1),
and throttle behaviour (no-op when unset / invalid / zero / negative;
sleeps for positive). 845 core tests green (was 836).

**Cost of the change at full E7 scope:**
- Serial: 5× slower wall clock vs parallel (each search waits for
  the previous to return).
- 0.5 s/call delay: ≈ 0.5 s × N_searches additional per run.
- 120 s inter-scenario gap × 10 boundaries: ≈ 20 min added.
- For 4 models × 11 scenarios × ~30 searches per run × ~0.5 s:
  ≈ 11 min of pure throttle delay + ~20 min cool-downs +
  ~2 h serial Spotify time → **3-4 h total wall clock** (vs the
  original 2-3 h estimate). Worth it to keep the account safe.

**Status — E7 ready to retry after Spotify cool-down.** The eval
was attempted twice on 2026-05-07; both times Spotify returned hard
429s despite increasingly conservative throttling. The issue is
likely a penalty window on the user token from the burst of searches
earlier in the day (manual app testing + first unthrottled eval
attempt). Current throttle settings after iterating:
- Serial mode: `SPOTIVIBE_SPOTIFY_SEARCH_SERIAL=1` (1 worker)
- Per-call delay: `SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S=1.5` (≤ 0.67 calls/s)
- Inter-model cooldown: 90 s
- Inter-scenario cooldown: 120 s
- 429 back-off cap: 90 s (up from 30 s)

**Next attempt:** wait ≥ 1 hour from the last 429 (≈ 11:00 UTC
2026-05-07), then re-run:
```bash
python evaluation/run_evaluation.py --no-confirm
```
If 429s persist even after a 1-hour cool-down, the remaining lever
is to increase `SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S` further (e.g. 2.0)
or reduce the eval scope to fewer scenarios (`scenarios = default`
in `settings.ini` instead of `all`).

## 🆕 Session 3 deliverables — 2026-05-07 (Spotify-blocked work)

User token blocked till 2026-05-08. Took the gap to land all
Spotify-independent agenda items: U2, U4, U5, U6, Q4, M2, M3 plus doc
sync. 876 core tests green (was 845, +31). 2 i18n parity tests green.

#### U4 — Use-X-tracks-now busy state during finalize
[pipeline.js](frontend/static/js/modules/pipeline.js) `useCurrentTracks()`
now sets `aria-busy="true"` + saves the previous label, and restores both
on fetch failure. `setGenerating(false)` clears any leftover
busy/disabled state so the next run starts clean.

#### U5 — Better GPT-exhaustion message
Dropped the verbose technical fallback in [app.py](app.py)
(`error.run.gpt_exhausted`); new copy: "Couldn't find more matching
tracks. Try a smaller playlist or adjust the exploration slider."
en/de/jp keys updated. Eval harness `_UNDER_FILL_PHRASES` retargeted to
the new fallback.

#### U2 — Transient vs permanent error classification
`TranslatableError` and `as_response_payload()` in
[core/src/errors.py](core/src/errors.py) gained `error_class:
"transient"|"permanent"` (default permanent).
[openai_http.py](core/src/openai_http.py) `OpenAIRateLimitError` /
`OpenAITimeoutError` carry class-level `error_class = "transient"` +
i18n keys.
[app.py](app.py) `_classify_unknown_exception()` injects transient
class for `SpotifyException` http_status 429 / 502-504. Frontend SSE
error handler renders transient with ⏳ + `info` level, permanent with
❌ + `error` level. 4 new i18n keys per language. 13 new tests
(`TestErrorClass` in `test_errors.py` + `TestSseErrorClassification` in
`test_app.py`).

#### U6 — Live Spotify status pill
New `<button id="spotifyStatusPill">` in
[settings_gear.html](frontend/templates/settings_gear.html) between the
language toggle and burger menu. Coloured-dot CSS in
[components.css](frontend/static/css/components.css) (Spotify-green when
authenticated, red when not, grey when unknown). State refreshed inside
`renderComponentWarnings()` ([warnings.js](frontend/static/js/modules/warnings.js))
which is already called by every auth-state path including the U1
focus/visibilitychange re-check. Click toggles `toggleSpotifyConnection()`
(re-using the existing menu handler). 4 new i18n keys per language.

#### Q4 — Tag-precedence audit
New [build-tools/audit_tag_precedence.py](build-tools/audit_tag_precedence.py).
Loads the local Last.fm-enriched corpus, spot-checks 5 known mainstream
artists, then sweeps all 174,200 rows. **Result on 2026-05-07 corpus
(corpus_version=2026-05-06, 145,627 enriched rows): 145,627 / 145,627
resolve via `_lastfm_popularity()`; 0 precedence-bug rows.** Mainstream
artists (Beatles 6.5M listeners → 0.963; Drake 6.7M → 0.966) all clear
the MB-proxy ceiling clamp at 1.0 — Phase B precedence wiring
([core/src/rag/retrieval.py:431](core/src/rag/retrieval.py#L431) is
fix-confirmed.

Side note: the local `artists.jsonl.gz` was a non-gzipped JSONL written
under the `.gz` suffix. Audit script handles via magic-byte detection +
sibling-copy fallback (non-destructive). The runtime corpus loader
should probably learn the same trick — filed as a follow-up.

#### M2 — Local perf-baseline test
New [test_perf_baseline.py](core/tests/test_perf_baseline.py) with 3
budget tests on a frozen, deterministic 5,000-artist synthetic corpus
(seeded `random.Random(20260507)`). `pytest.mark.perf` registered in
[pytest.ini](pytest.ini); deselected by default via `addopts -m "not
screenshots and not perf"`. Run with `pytest -m perf`. Budgets are 5×
observed wall-clock — they catch O(n²) regressions, not micro-tuning.

#### M3 — Per-run perf summary persisted to sqlite
New [core/src/perf_log.py](core/src/perf_log.py): one row per
generation, schema documented in
[TechnicalManual.md](documentation/TechnicalManual.md) §"Per-run perf
log". sqlite path: `<APP_DIR>/perf_log.sqlite`.
[trace.py](core/src/trace.py) gained an always-on `_METRICS` accumulator
(populated regardless of `DEBUG_MODE`) plus `current_stage_metrics()` /
`current_run_id()` accessors. The heavy trace bundle (`stages` /
disk-write) is still gated on `DEBUG_MODE`. Wired into the
`/api/run` finally block in [app.py](app.py) — fires before
`finalize_trace()` so the metrics are still in memory. 12 perf-log
tests + 6 always-on-metrics tests.

#### Doc sync
- [UserManual.md](documentation/UserManual.md) — Spotify status pill
  paragraph in §"5. Connect Spotify"; troubleshooting table updated for
  the new exhaustion message + transient-error rendering.
- [help.en.md](documentation/help.en.md) /
  [help.de.md](documentation/help.de.md) /
  [help.jp.md](documentation/help.jp.md) — status pill mention.
- [TechnicalManual.md](documentation/TechnicalManual.md) — new
  §"Per-run perf log" + §"SSE error classification".

#### Files NOT touched (still queued in agenda)

- **E7** baseline run — still gated on Spotify cool-down.
- **U3** track-progress ETA, **Q2** Last.fm `getSimilar` similarity
  facet — both Spotify-independent, queued for a follow-up session.
- **L5 / Q1 / Q3 / OPEN-*** — gated on E7 results.

#### Artist-suggestion backend wiring — 2026-05-07

Added `search_top_tracks_by_name(sp, name, max_tracks)` to
[core/src/playlist.py](core/src/playlist.py) (between
`filter_emerging_artists` and `get_user_playlists`). Mirrors
`_search_top_tracks_by_name` in
[build-tools/build_top_tracks_overlay.py:98-147](build-tools/build_top_tracks_overlay.py#L98-L147)
— pure `sp.search(q='artist:"NAME"', type="track")` + normalised-name
filter on the primary artist. Reuses canonical
`core.src.rag.corpus.normalise_name` (no duplicated normaliser).
`limit` clamped to ≤ 10 per SKILL.md (Feb-2026 search-limit
reduction).

**Note on approach:** Original recommendation was to *import* from
build-tools. Not viable — `build-tools/` has no `__init__.py` and
`build_top_tracks_overlay.py` already imports from
`core.src.playlist` (would be circular). Settled on a thin in-place
copy with a doc-link back to the build-tool original.

**🔴 Deferred — live MCP verification of search response shape.**
Spotify MCP returned 429 (app-wide rate-limit) twice during the
2026-05-07 verification attempt. The implementation is grounded in:
1. SKILL.md (Track `popularity` removed Feb 2026 — no field is read).
2. The known-good build-tool reference impl shipped 2026-04-27.

When the MCP quota resets, run these three live checks before merging
the artist-suggestion feature end-to-end:

1. `mcp__spotify__searchSpotify(query='artist:"radiohead"', type='track', limit=10)`
   — confirm 2026 returns current tracks with usable URIs and the
   `artists` array (we filter on `artists[*].name`).
2. Inspect one track item — confirm `popularity` field is absent
   (already documented; live confirmation is the safety net). Note any
   surviving relevance signal in case we want a tie-break beyond
   search-rank order.
3. (Already done from README scan, no MCP call needed.) The Spotify
   MCP exposes **no** artist-scoped "top tracks" tool — search +
   filter is the only path. Confirmed against
   `C:/Users/micha/.claude/mcp-servers/spotify-mcp-server/README.md`.

**Resolved 2026-05-07:** Artist suggestions reuse the track-suggestion
RAG pool — same `retrieve_candidates` invocation, same APPROVED_ARTISTS
block fed into [prompts/artist_select_user.txt](prompts/artist_select_user.txt).
No separate niche-biased pool.

**Mirror the existing emerging-only RAG skip rule.** When `emerging_only=True`
the corpus is bypassed for tracks today
([core/src/suggestions.py:587-631](core/src/suggestions.py#L587-L631)) —
the quarterly MusicBrainz dump cannot contain artists who debuted in
the last ~3-6 months, and `filter_emerging_artists` post-filters
factually anyway. Artist suggestions follow the same rule: **RAG fed
when `emerging_only=False`; bypassed when `True`.**

Wiring TODO when the backend lands: the artist prompt's hard constraint
#2 ("ONLY suggest artists in the APPROVED_ARTISTS list") must be
relaxed in emerging mode, parallel to how the track prompt swaps in
the "debut within 6 months" constraint when the pool is absent.
Spec the swap before implementing — don't ship contradictory
constraints to the model.

### Files touched at handoff

Backend:
- [core/src/trace.py](core/src/trace.py) (E1)
- [core/src/playlist.py](core/src/playlist.py) (L2 + L3)
- [core/src/suggestions.py](core/src/suggestions.py) (E1 stage 2/3)
- [app.py](app.py) (E1 stage 1/verify, L2 lifecycle, L3 stream wire-up)
- [evaluation/harness.py](evaluation/harness.py) (E1 surface)
- [evaluation/reporting.py](evaluation/reporting.py) (E1 table)

Frontend:
- [frontend/static/js/main.js](frontend/static/js/main.js) (U1)
- [frontend/static/js/modules/pipeline.js](frontend/static/js/modules/pipeline.js) (L3)
- [frontend/static/i18n/en.json](frontend/static/i18n/en.json),
  [de.json](frontend/static/i18n/de.json),
  [jp.json](frontend/static/i18n/jp.json) (L3 i18n key)

Tests:
- [core/tests/test_trace.py](core/tests/test_trace.py) (E1, +7 tests)
- [core/tests/test_evaluation_harness.py](core/tests/test_evaluation_harness.py) (E1, +8 tests)
- [core/tests/test_playlist.py](core/tests/test_playlist.py) (L2, +6 tests)
- [core/tests/test_app.py](core/tests/test_app.py) (L3 mock surface
  swap — no new tests, only retargeted)

Doc: this file (`next-steps.md`) — handoff section + agenda updates.

## 🆕 Session 4 deliverables — 2026-05-08

E7 baseline executed (commit `cd15d8b`). 4 scenarios × 4 models × 1 iter,
all on `corpus_version=2026-05-06` Last.fm-enriched corpus. Results
copied to `evaluation/baselines/2026-05-08_lastfm/` (16 summary.json +
`comparison.md`). Trace bundles consumed for analysis but not yet
copied alongside the baseline (the source `evaluation/results/`
timestamped dir was not preserved).

### E7 headline outcomes

| Gate | Result |
|---|---|
| Leakage (B vs feedback) | **PASS 16/16** — Phase B + harness rework working as intended |
| Phase B coverage (Last.fm tags ≥ 75 %) | **PASS** on 12/13 rows (1 row at 50 % with n=2 — sample-size noise, not a regression) |
| Completion (≥ 95 % requested) | **FAIL 30/32** playlists `under` or `empty` |
| niche_only_strict p95 listeners < 100 k (Playlist A) | **FAIL 3/3** models (215 k / 215 k / 891 k) |
| lastfm_tag_weighting Spotify-found rate | **collapsed 7-27 %** (Stage 3 picks tracks not on Spotify) |
| Fit-check (decade_avoid) | **1 fail**: gpt-5.4 post_feedback_tag_regression B → 3× bardeux 1988 |
| `gpt-4.1-mini` Playlist A | **3/4 scenarios returned 0 tracks** — model effectively dead at this corpus scale |

Latency dominator: **Stage 3 (track select) = 30-180 s** per playlist,
3-4 orders of magnitude above RAG retrieve (0.1 s) and 1 order above
Spotify verify (10-50 s). Cost: gpt-5.4 ≈ 3× gpt-5.4-mini ≈ 30×
gpt-4.1-mini. gpt-4.1-mini is cheap because it returns nothing.

### Plan reconciliation

Walking remaining open items in the original "Suggested execution
order" against E7 data:

- ~~**Q1 — cost-bundle re-baseline**~~ **strikethrough.** The decision
  gate ("if `gpt-5.4-mini` for Stage 3 holds quality, Q1's cost-bundle
  work is largely moot") is already satisfied by E7: gpt-5.4-mini
  matches gpt-5.4 on completion + leakage, lags 5-15 pp on must-have
  cite, costs 30 % as much. Running another full baseline burns Spotify
  quota for an answer the data already gives. Replaced by **B1** below.
- ~~**Q3 — Wikidata Phase D (country / era facts)**~~ **strikethrough
  until data demands it.** The decision gate ("if country-constrained
  scenarios pass on enriched corpus, Phase D may be unnecessary") is
  satisfied — none of the failures observed (under-fill, niche bias,
  off-Spotify tracks) are country / era shaped. Phase D is a wrong-key
  fix for the locks we have.
- **L5 — Stage 3 model downgrade probe** retained but flipped to
  data-driven: the answer is largely visible already; B1 below confirms
  it on a focused sample before a default-flip lands.
- **U3 — track-progress UI** retained, unaffected by eval failures
  (independent UX win — the L3 SSE backend it depends on is shipped).
- **Q2 — Last.fm `getSimilar` similarity facet** retained but stays
  gated; not a fix for the failures we see.

### New A-series priorities (surfaced by E7) — 🔴 P0

These eclipse the remaining agenda on ROI. Each is independently
grabbable.

- **A1 — Under-fill root cause: `MAX_GPT_CALLS_PER_RUN = 4` is the
  binding constraint at `playlist_size = 30`.** ✅ Diagnosed 2026-05-08.
  - [config.py:88](config.py#L88) caps Stage 3 calls at 4. Eval runs
    target 30 tracks ([evaluation/settings.ini](evaluation/settings.ini#L36)).
    Theoretical max output: 4 × (BATCH_SIZE 10 + STAGE3_OVER_REQUEST 2)
    = 48 raw candidates. Observed Spotify-found rate: 7-67 %. Even at
    100 % Spotify-found this barely clears the 95 % completion gate
    (29 tracks needed); at the observed rates it cannot.
  - The cap's existing comment ("Bump back to 20 once the canonical
    seed reliably hits ≥ 80 % Spotify-found on the first 1-2 batches")
    pre-dates Phase B. Phase B did not lift Spotify-found above 80 %
    in tag-weighted scenarios (E7 lastfm_tag_weighting: 7-27 %), so
    the precondition the cap waits on is still not met.
  - Confirmed via summary.json: gpt-4.1 default Playlist A → 4 Stage 3
    calls, only 2 Spotify-verify calls fired (two batches were entirely
    filtered as already-known); gpt-4.1-mini default → 3 Stage 3 calls
    yielded 1547 output tokens total (~515/call) → schema collapse,
    not retrieval starvation.
  - **Resolution split:** the *real* problem is upstream (Stage 3 must
    pick Spotify-resolvable tracks → that's A4). For eval-measurement
    integrity, two free eval-only knobs unblock the completion-gate
    signal:
    1. Lower `playlist_size` to 15 in [evaluation/settings.ini](evaluation/settings.ini)
       (matches the cap's design assumption).
    2. OR introduce an eval-only env-var override
       (`SPOTIVIBE_MAX_GPT_CALLS_PER_RUN`) plumbed through
       [config.py](config.py) so eval can run with `=10` while
       production stays at `=4`.
    Recommend (1) for B1 — keeps prod config unchanged, keeps the
    guardrail honest, surfaces the real Spotify-found problem instead
    of masking it with more retries.
- **A2 — Drop `gpt-4.1-mini` from the eval models list.** Returns 0
  tracks 3/4 scenarios; either the prompt size exceeds its context for
  this corpus or it fails Stage 3 schema. Either way it's not a viable
  default and it currently inflates the "models tested" count without
  producing data. Single-line edit to
  [evaluation/settings.ini](evaluation/settings.ini) +
  [evaluation/settings.ini.example](evaluation/settings.ini.example).
  Re-add later if a separate triage proves it salvageable.
- **A3 — niche_only_strict bias fix.** Three Playlist A's hit p95
  215 k-891 k listeners despite explicit avoid prose ("avoid Billboard
  chart, avoid radio rotation, avoid > 1 M monthly listeners"). The
  Last.fm popularity precedence in `_artist_popularity()` ranks
  popular artists *higher* in the RAG pool — but nothing in Stage 1 /
  Stage 2 inverts that ranking when avoid prose explicitly names a
  popularity ceiling. Likely needs either a Stage 1 popularity filter
  triggered by avoid-vocabulary detection, or a Stage 2 prompt
  enhancement that surfaces listener counts to the avoid LLM.
- **A4 — lastfm_tag_weighting Spotify-found collapse.** Stage 3 picked
  tracks (cite OK) but only 7-27 % verified on Spotify. Likely RAG
  returned niche / regional artists whose tracks aren't on the
  user's market or whose names don't normalise cleanly to Spotify's
  catalogue. Mitigation candidates:
  1. Pre-verify-on-Spotify gate during retrieval (expensive).
  2. Spotify-presence score baked into the corpus build (cheap, one
     pre-compute pass).
  3. Stage 3 prompt: bias toward high-listener-count artists when
     `lastfm_tag_weighting`-class scenarios fire. Risks contradicting
     A3's direction; resolve before implementing.

### B-series — measurement before code

- ~~**B1 — Acceptance test for Stage 3 default switch.**~~ ✅ Executed
  2026-05-08 (8 of 12 planned runs landed before a Spotify token
  penalty cascade — Retry-After ≈ 14 h — forced a kill). Results in
  [evaluation/baselines/2026-05-08_b1_stage3_downgrade/](evaluation/baselines/2026-05-08_b1_stage3_downgrade/)
  including a hand-written `summary.md`. Verdict:
  - **Playlist A (generation):** gpt-5.4-mini wins decisively — mean
    14.3/15 tracks vs gpt-5.4's 11.0/15, ~50 % faster, ~10× cheaper.
  - **Playlist B (post-feedback regen):** gpt-5.4-mini *collapses* —
    mean 3.7/15 vs gpt-5.4's 8.3/15. The post-feedback profile prose
    is too nuanced for mini to generalise.
  - **Quality gates** (leakage, fit): no regression on either model.
  - **niche scenario:** only gpt-5.4 collected (2 iters); both fail
    the p95 < 100 k listener gate (215 k twice). A3 confirmed needed.
  → **L5 cannot default-flip unconditionally.** Two viable paths:
  (1) two-tier Stage 3 — mini on initial generation, gpt-5.4 once
  the profile carries non-trivial feedback weight; (2) keep gpt-5.4
  default + expose mini as optional fast/cheap mode. Spec before
  implementing.
  → **Operational note:** next eval kickoff blocked until the
  Spotify user token clears (≥ 14 h from 2026-05-08T18:54 UTC →
  not before 2026-05-09T08:54 UTC). The 1.5 s/serial throttle in
  place is not enough to prevent burst penalties under multi-iter
  runs; consider raising inter-iter cooldowns or moving to a
  service-account token before the next baseline.

### Revised execution order (post-E7)

1. ✅ **A1** — under-fill root-cause analysed 2026-05-08 (cap is
   `MAX_GPT_CALLS_PER_RUN = 4`).
2. ✅ **A2** — gpt-4.1-mini dropped from `evaluation/settings.ini`.
3. ✅ **B1** — Stage 3 model comparison run 2026-05-08 (8/12 runs;
   Spotify token-penalty kill on the rest). Verdict: A wins for mini,
   B wins for gpt-5.4 — see strikethrough above.
4. **L5 spec — two-tier Stage 3.** Cheap to spec, no eval cost. Switch
   Stage 3 model based on a profile-feedback-weight heuristic (e.g.
   `len(profile.feedback.disliked_tracks) > N` → gpt-5.4, else mini).
   Lock in the threshold from B1 data. Implement after the spec is
   reviewed.
5. **A3 — niche-bias fix.** Stage 1 popularity-aware filter triggered
   by avoid-vocabulary detection; OR Stage 2 prompt enhancement that
   surfaces listener counts. Decide direction from a one-shot manual
   experiment before coding.
6. **A4 — Spotify-resolvability lift.** Cheapest direction: bake a
   Spotify-presence score into the corpus build so RAG ranks it.
   Confirm against the Last.fm tag-weighting scenario (current
   Spotify-found 7-27 %).
7. **U3** — track-progress UI (no eval cost, parallelisable).
8. **L5 implementation** — only after step 4 spec lands.
9. **Q2 / OPEN-*** — re-evaluate against the post-A3/A4 baseline; only
   pursue if a measurable gap remains.

### Cost-control programme — 2026-05-08

End goal: a 30-track suggestion stays under **$0.10 consistently**,
and never *skyrockets* as the user's profile grows. E7 + B1 data shows
mini already lands ~$0.04/playlist and gpt-5.4 ~$0.08-0.15/playlist;
the latter is the failure mode to fix. Six levers, ranked. Items
marked C* are the active ordering the user signed off 2026-05-08.

- ~~**C1 — L5 two-tier Stage 3 default**~~ ✅ Shipped 2026-05-10 as
  Path 3 (UI + selector machinery, no behaviour change for existing
  users). Settings modal exposes `Fast / Best / Auto / Custom`;
  default = `fast` (= today's behaviour, always mini). Auto escalates
  to `gpt-5.4` once `feedback.disliked_tracks` ≥ 1. Custom respects
  the existing `OPENAI_MODEL` field (local LLMs unaffected).
  Picking a preset greys the model dropdown but preserves its value
  (Q3 = option 2, user-confirmed).
  - Selector: `core.src.suggestions._resolve_stage3_model`
    ([core/src/suggestions.py](core/src/suggestions.py)).
  - Config: `STAGE3_FAST_MODEL`, `STAGE3_BEST_MODEL`,
    `STAGE3_MODE_DEFAULT`, `STAGE3_MODES`, `get_stage3_mode`,
    `set_stage3_mode` ([config.py](config.py)).
  - UI: 4-radio group in
    [settings_modal.html](frontend/templates/modals/settings_modal.html);
    enable/disable wiring + persistence in
    [modals.js](frontend/static/js/modules/modals.js).
  - Tests: 8 selector unit tests + 4 config getter/setter unit tests
    + 3 Playwright settings-modal tests
    ([test_modals.py](frontend/tests/test_modals.py)).
  - **Telemetry deferred.** Per-run perf-log column for
    `stage3_mode` / `stage3_model` was scoped but skipped — the app
    isn't in production, so the telemetry would not accumulate; add
    when there are real users to learn from.
  - **Default-flip to `auto` deferred** until C3 + C4 land. With
    today's gpt-5.4 cost ($0.08-0.15 per playlist), `auto` would
    push post-feedback runs above the user's $0.10 ceiling. R1
    (mini-quality research) may eliminate the need for the flip
    entirely.
- ~~**C2 — Per-run cost preview UI**~~ ✅ Shipped 2026-05-10. Most of
  the cost-estimator widget already existed (`cost_estimate.js`,
  `costEstimateCard` in
  [settings_modal.html](frontend/templates/modals/settings_modal.html)
  + the popover under Generate); the gap was that it read the model
  from the dropdown — wrong for L5 preset modes (Fast / Best / Auto)
  which ignore the dropdown at request time.
  - Backend: `/api/profile/prompt-size` now returns `stage3_mode`
    + `stage3_resolved_model` ([app.py:2181-2243](app.py#L2181-L2243)).
    The resolver runs against the *active profile*, so when Auto
    escalates after a dislike the API returns `gpt-5.4` and the cost
    figure jumps from ~$0.04 to ~$0.10 visibly *before* the user
    clicks Generate.
  - Frontend:
    [cost_estimate.js](frontend/static/js/modules/cost_estimate.js)
    `_getModel(sizes)` and `estimate(...)` now prefer the resolved
    model over the dropdown when mode ≠ `custom`.
  - Tests: 3 endpoint tests (`TestProfilePromptSize`) in
    [test_app.py](core/tests/test_app.py) cover the cold-untrained,
    auto-with-dislikes, and custom-mode paths.
  - **Hard cost gate deferred** — the "Switch to fast mode for $0.04?"
    prompt above a configurable cap is not yet wired. The estimator
    surfacing the right number is the load-bearing fix; the gate is
    UX polish on top of it. Re-open if user testing shows people
    still clicking Generate when the estimate is high.
- ~~**C3 — OPEN-5 profile consolidation on overgrowth**~~ ✅ Shipped
  2026-05-10. Verbatim `forbidden_tracks` block now caps at the most
  recent `RECENT_VERBATIM_TRACKS = 100` entries; older history is
  represented via a new per-artist aggregate `artist_track_counts`
  (full-history scope, within `GPT_HISTORY_LIMIT`). `[EXHAUSTED]`
  threshold unchanged at 4 — but driven by the broader aggregate, so
  artists buried beyond the verbatim window still surface as exhausted.
  - **Scope (corrected from initial claim):** `_build_deny_set_json`
    is consumed by the **legacy `build_messages` path only** —
    fires when RAG is disabled OR `emerging_only` mode is on. The
    production Stage 3 (`select_tracks` + `track_select_*.txt`)
    works on a pre-approved artist list and never sees DENY_LIST;
    its per-track dedup is post-hoc via `filter_duplicate_suggestions`.
    So C3's token saving applies to the legacy path; for the
    dominant Stage 3 path the structural win is reuse of
    `_compute_exhausted_artists` (which `filter_duplicate_suggestions`
    calls — and which now derives from the aggregate, so artists
    buried beyond a hypothetically-shrunken verbatim slice still
    get filtered out). C4 is the load-bearing cost win for Stage 3.
  - New `_aggregate_artist_track_counts` helper in
    [core/src/suggestions.py](core/src/suggestions.py); both
    `_compute_exhausted_artists` and `_build_deny_set_json` route
    through it.
  - Aggregate sorted desc by count so highest-signal entries surface
    first under context-budget pressure.
  - `system_prompt.txt` (legacy-path system prompt) gains one
    descriptive line about the new `artist_track_counts` field.
  - Tests: 4 new (aggregate present / sorted-desc / verbatim-trim /
    exhaust-from-aggregate) in `TestBuildDenySetJson`. Existing
    tests unchanged.
  - Token saving on the **legacy path** at saturation: ~1.8 k tokens
    per call (~$0.001 mini, ~$0.018 gpt-5.4 per playlist). Structural
    win = bounded growth: verbatim block fixed at 100 forever,
    regardless of profile age.
- ~~**C4 — Stage 3 prompt-cache routing key**~~ ✅ Shipped
  2026-05-10. Investigation finding: OpenAI auto-caches eligible
  prefixes (≥ 1024 tokens) but the cache is per-host. Without a
  routing hint the load balancer sprays requests across hosts and
  hits sporadically — B1 trace inspection 2026-05-10 showed 0 % on
  most batches and 71-76 % on the few that landed.
  - `chat_completions_create` ([core/src/openai_http.py](core/src/openai_http.py))
    gains optional `prompt_cache_key` parameter; routed to the
    OpenAI payload only when the configured provider IS OpenAI
    (compatibility-mode endpoints like Ollama may 400 on unknown
    fields, so the field is gated on `_is_openai_provider()`).
  - Stage 3 (`select_tracks` in
    [core/src/suggestions.py](core/src/suggestions.py)) sends
    `f"sv-stage3:{model}:{language}:{int(emerging_only)}"` —
    constant per (model, language, emerging-only) triple, which
    matches the system-prompt's invariance dimensions exactly.
  - Tests: 3 new in `TestChatCompletionsCreate` covering
    pass-through, omission when unset, omission on local providers.
  - **Verification deferred to next eval.** The win shows up as a
    higher and more *consistent* `cached_tokens / prompt_tokens`
    ratio in the eval-log batch_summary records. R1's protocol can
    measure this as a side-benefit when its sweep runs.
- ~~**C5 — Compact JSON Stage 3 schema**~~ ❌ Deferred 2026-05-10
  after risk assessment. Re-baselined estimate:
  - Real saving on the dominant model (mini): ~$0.001 / playlist
    (output tokens are a small share of total; rationale array is
    the only field where compaction has meaningful weight).
  - Touch points: `normalize_response`, `_strip_gpt_annotation`,
    `update_profile`, `filter_duplicate_suggestions`, every test
    that assembles a fake Stage 3 response, plus the prompt
    template itself.
  - Failure mode: the model returns a mixed shape (some entries
    long, some short) under temperature noise — parser must accept
    both, doubling the surface area of `normalize_response`.
  - Cost-benefit: ~$0.001 saved vs days of prompt-engineering risk
    is a bad ratio. Re-open only if R1 surfaces a different angle
    (e.g. compact schema *also* improves mini's quality, not just
    cost), in which case the change becomes load-bearing for a
    quality fix and the parser surface-area cost is justified.

#### R1 — Research spike: lift mini quality on deeper profiles

**Why this matters.** B1 (2026-05-08) showed mini collapses on
Playlist B (mean 3.7/15 vs gpt-5.4's 8.3/15) once the profile carries
non-trivial feedback. C1 (L5 Auto) reacts to that by escalating to
gpt-5.4 — which pushes post-feedback runs past the user's $0.10
budget ($0.08-0.15/playlist on gpt-5.4 vs $0.04 on mini). If a
*prompt-side* or *data-preparation-side* change can keep mini
viable on deeper profiles, the escalation in C1 becomes unnecessary
or moves later in the profile-maturity timeline → the cost cap
holds without quality regression.

**Scope.** Not a feature ticket — a research spike. The "how" is
deliberately open. Likely directions to test:

- Prompt restructuring: shrink + sharpen the Stage 3 system prompt
  so mini spends less context on instructions and more on the
  candidate pool / profile signal.
- Profile-shape transformation: reformulate the post-refine profile
  prose into a structure mini handles better (e.g. bullet-form
  taste anchors vs free prose; explicit positive/negative signal
  separation; weighted tag list vs narrative).
- Few-shot examples: inject 1-2 worked examples into the Stage 3
  prompt so mini has a concrete pattern to match.
- Decomposition: split Stage 3 on deeper profiles into "draft" +
  "refine" sub-calls with mini, total still cheaper than a single
  gpt-5.4 call.
- Avoid-block compression: today's `forbidden_tracks` block is the
  largest non-system input (see C3); a more compact representation
  may free model capacity for the actual selection task.

**Verification protocol.** Hold model fixed at `gpt-5.4-mini`. For
each candidate change:

1. Run the existing eval scenarios + the B1-equivalent post-feedback
   scenario, **multiple iterations** (≥ 3, ideally 5) to smooth
   single-run variance — the B1 mini variance was 1-7 tracks on B,
   averaging matters.
2. Measure: completion rate (Playlist B), must-have cite, fit-check,
   leakage, total cost. The **B-playlist completion uplift** is
   the headline metric — that's the bug R1 is trying to fix.
3. Threshold for declaring success: mini Playlist B mean ≥ 80 % of
   gpt-5.4's mean *and* leakage / fit gates still pass. Anything
   short reopens C1 default-flip.
4. Run baseline (current prompt) alongside each variant in the
   same eval session so the comparison isn't time-confounded.

**Operational considerations.** Each run burns Spotify quota; the
B1 attempt hit a 14 h Retry-After block at run 7/12. For an R1
sweep with 5 prompt variants × 4 scenarios × 5 iter = 100 runs,
the Spotify token will need either a longer cooldown stack
(≥ 15 min inter-iter), a separate eval-only Spotify app credential,
or a prompt-only sub-experiment that bypasses Spotify verification
entirely (Stage 3 output → leakage / fit checks only, no playlist
creation). Decide between these before starting R1.

**Output.** A short report (`evaluation/research/2026-MM-DD_mini_quality.md`)
that either (a) recommends a prompt / data change to ship + an
updated C1 default-flip threshold, or (b) rules out prompt-side
fixes and confirms C1 escalation is the correct path. R1 is
*finished* when one of those two is decided — not when every
candidate has been exhausted.

**Status.** Spec'd 2026-05-08. Execution gated on the cost
programme (C1-C4) reaching a usable baseline first — R1 needs
prompt-caching / consolidation already landed so the variant
experiments aren't measuring the wrong baseline.

#### Deferred — `GPT_HISTORY_LIMIT` 200 → 100 (kept in mind)

The "lower the suggested-tracks history cap" lever was scoped 2026-05-08
and **not landed**. Reasons:

- 100 tracks ≈ 3 × 30-track playlists; on the 4th run a user could see
  re-surfaced tracks already in their playlist. Disliked tracks are not
  affected (separate bucket — `feedback.disliked_tracks`, governed by
  `MAX_SONG_LIST_SIZE = 100`), but routine "we already suggested this
  to you" memory does shrink.
- Cost win on mini is small (~$0.0016/playlist); win on gpt-5.4 is
  ~$0.028/playlist but L5 makes that path rare.
- The aggregation mechanism (per-artist counts) **better solves the
  same scaling problem** without dropping per-track memory — but
  belongs in C3, not standalone.

Re-open if a user-visible "spend ceiling" forces structural cuts that
C3 alone doesn't deliver.

#### Adjacent concern — `MAX_SONG_LIST_SIZE = 100` (dislike persistence)

Out-of-scope for the cost programme but flagged 2026-05-08. The
persistent disliked-tracks list is capped at 100 entries. Power users
with hundreds of dislikes would see oldest dislikes drop off, raising
the "we re-suggested a song you actively disliked" risk. Worth a
separate look once the cost programme stabilises.

### Validation eval (2026-05-10) — Tier-0 root-cause + Tier-1 logging

#### What surfaced

A focused B2-style validation run was kicked off 2026-05-10 to verify
C1-C4 had not regressed quality. 7 of 12 iters landed before the
Spotify access token expired mid-run (1 h TTL, eval ran ~1.5 h).
Initial analysis flagged a **−25 pp drop in `gpt-5.4` must-have-cite**
vs B1 (B1: 97 % → validation: 71.8 %). After investigation this
turned out to be a measurement artefact, not a real regression.

#### Tier-0 root cause — settings persistence + setdefault no-op

Trace bundles for the validation `gpt-5.4-iter*` runs all show
`model: gpt-5.4-mini` in their per-batch records. The validation
**never ran gpt-5.4** at all. Cause chain:

1. Earlier on 2026-05-10 the Settings POST was exercised end-to-end
   (Auto → Best → Fast). The final POST persisted
   `STAGE3_MODE='fast'` to `~/AppData/Local/spotyvibe/settings.conf`.
2. The eval harness imports production code on startup;
   `config.ensure_env()` runs `load_dotenv(SETTINGS_FILE)` and seeds
   `os.environ["STAGE3_MODE"] = "fast"` before any harness code runs.
3. The eval-side guard
   `os.environ.setdefault("STAGE3_MODE", "custom")` no-oped because
   the key was already set.
4. Stage 3 fired → `_resolve_stage3_model(...)` returned
   `STAGE3_FAST_MODEL` (mini) regardless of the harness's per-iter
   `OPENAI_MODEL=gpt-5.4` override.

Fix shipped same day in
[evaluation/run_evaluation.py](evaluation/run_evaluation.py):
`setdefault` replaced with explicit assign + a long comment
explaining why the eval needs unconditional `custom` semantics.

**What survives from the validation analysis:**
- mini default cite mean ≈ 73.9 % over n=6 (n=3 from each "model
  group", both actually mini). Stable vs B1's 77.3 %.
- No leakage / fit regression on any of the 7 successful iters.
- B1's "mini collapses on Playlist B" finding remains the only
  data point on the gpt-5.4 vs mini quality axis. Validation
  cannot speak to it because both rows are mini-on-mini.

**What does NOT survive:**
- The "−25 pp gpt-5.4 cite drop" was mini being measured as gpt-5.4.
- The "Playlist B mini-collapse not reproduced" claim is also void —
  both groups in validation were mini, so neither could refute the
  collapse hypothesis.

#### Tier-1 logging — shipped 2026-05-10 alongside the analysis

Three new diagnostic fields surface in every `batch_summary` row of
`eval.jsonl` and on every `stage3_batches` entry of `trace_A.json`:

- **`system_fingerprint`** (string, OpenAI-only) — the model snapshot
  identifier OpenAI returns alongside `usage`. When this changes
  between runs, OpenAI rolled a model update silently. Today's
  codebase NEVER captured this value, so the "did the model drift?"
  hypothesis was unanswerable. Now it is.
- **`prompt_hashes`** (`{system_md5, user_md5}`, both 16 hex chars) —
  short MD5 prefixes of the system + user message strings. Lets
  post-mortem analysis confirm "the prompts were byte-identical
  between runs" without diffing whole trace bundles. Also useful
  for grouping calls by cache-eligibility — same `system_md5` =
  same OpenAI prompt-cache key on the auto-cache side.
- **`stage3_mode`** (string) — the L5 selector's mode at call time.
  Direct readout to detect the same setdefault-bug class of mistake:
  if eval rows show `stage3_mode='fast'` instead of `'custom'`, the
  comparative model is wrong before any further analysis happens.

Helper: `_hash_messages_for_audit` in
[core/src/suggestions.py](core/src/suggestions.py); 5 unit tests in
`TestHashMessagesForAudit`. `chat_completions_create` already
returned `system_fingerprint` in its response dict — Tier 1 just
plumbs it through `meta` → `_emit_batch_summary` →
`log_batch_summary` so the eval log captures it. Two new tests in
`TestCallGpt` cover the meta-propagation + the local-LLM
"no fingerprint" fallback.

#### Further investigation — how to study OpenAI prompt handling

Once a fresh eval lands with Tier-1 logging in place, several
investigation paths open up. Recipes below.

- **Detect a model roll.** `jq -r '.system_fingerprint' eval.jsonl |
  sort -u`. If the set grows from one run to the next, OpenAI rolled
  a snapshot mid-run or between runs. Cross-reference with cite-rate
  changes per fingerprint to attribute quality drift correctly.

- **Verify prompt invariance across batches in one /api/run.** `jq
  -r '.prompt_hashes.system_md5' eval.jsonl | uniq -c`. The system
  prompt for Stage 3 is invariant under (model, language,
  emerging_only); the user-message hash should change per batch
  (deny set + accepted-tracks block grow). If `system_md5` differs
  within one run something corrupts the prompt-prefix and OpenAI's
  auto-cache cannot hit. C4's `prompt_cache_key` only helps when the
  prefix itself is stable.

- **Audit the L5 selector at call time.** `jq -r
  '.model + " " + .stage3_mode' eval.jsonl | sort -u`. Surface the
  (resolved-model, mode) pairs the eval actually exercised.
  `stage3_mode='fast'` in a comparative eval is the bug Tier 0
  caught — fail fast next time.

- **Group calls by cache-prefix and inspect hit rates per group.**
  `jq -r '[.prompt_hashes.system_md5, .cached_tokens // 0,
  .usage.prompt_tokens // 0] | @csv' eval.jsonl`. If the same
  `system_md5` shows ≥ 1 call with `cached_tokens=0` AND ≥ 1 call
  with `cached_tokens > 0`, OpenAI's routing flipped the request
  to a different host within the eligibility window. That's the
  primary failure mode C4's `prompt_cache_key` is supposed to fix —
  we can now measure whether it does.

- **Attribute cite-rate drift to (model, fingerprint, prompt_hash).**
  Combine the per-batch `rationale_stats.must_have_cite_rate` field
  with `system_fingerprint` + `prompt_hashes.user_md5`. If cite
  varies wildly within a single (fingerprint, system_md5) bucket,
  the variance is in the model's stochastic output — not in the
  prompt or model snapshot. That's the temperature-sensitivity
  baseline R1's Tier-3 experiment would formalise.

- **Read OpenAI's published model spec / system card.** The
  `system_fingerprint` returned alongside each call maps to a
  documented snapshot. When something unexpected happens, look up
  the snapshot in OpenAI's release notes — there may be a public
  changelog explaining the behaviour change. The codebase doesn't
  need to encode this; it's a manual investigation step that the
  fingerprint capture finally enables.

- **Capture per-track rationale text (deferred, not in Tier 1).** Today `rationale_stats` aggregates type counts and a binary
  must-have-cite flag. The full `arg` text per rationale entry is
  in `trace_A.json` per batch, but absent from the eval-log row.
  If R1's prompt-engineering work needs to inspect WHAT the model
  cited (e.g. is it citing soft_preferences when must_have was
  available?), surface a `rationale_args` array on `batch_summary`
  too. ~1-2 KB / batch, gated on `debug_mode`.

- **Determinism floor experiment (Tier 3, eval cost).** Issue
  10-20 identical Stage 3 calls at `temperature=0` (or via the
  `seed` parameter on gpt-5.x) against the SAME pool. Variance
  floor on cite rate sets the n threshold for any future
  measurement. If the floor variance is > 5 pp, B1's n=3 mean of
  97 % was lucky — and we should never have shipped a design
  decision on n=3 cite numbers.

#### Operational lessons

1. **Never use `setdefault` for env vars that are pre-seeded by
   `load_dotenv`.** Production code's settings.conf can pin the
   key before harness code runs. Force-override or refuse to start.
2. **Persisted settings are toxic for eval reproducibility.** The
   harness should snapshot `~/AppData/Local/spotyvibe/settings.conf`
   at start and either restore it post-run OR refuse to run if it
   contains anything other than the eval's expected baseline.
   Filed as a follow-up.
3. **Trace bundles are the source of truth for "what model
   actually ran".** `summary.json`'s `model` field reflects the
   *configured* model; `trace_A.json` per-batch `model` field
   reflects what was actually sent. When in doubt, trust the trace.

### Operational gates — Spotify user-token health

B1 (2026-05-08) hit a 14-hour Retry-After penalty after only the 7th
of 12 planned runs, despite the serial+1.5 s+90 s cooldown stack
already in place. The next eval kickoff must:

1. Wait ≥ 14 h from 2026-05-08T18:54 UTC (i.e. not before
   2026-05-09T08:54 UTC).
2. Consider a longer inter-iter cooldown (≥ 15 min) or a service-
   account / app-credentials token to keep the user token off the
   penalty list.
3. If a third consecutive run hits a Retry-After > 1 h, abandon eval
   on the user token and use a separate Spotify app credential for
   the harness.

## 🆕 Post-Phase B agenda — 2026-05-06

Corpus is now Last.fm-enriched (see verification above). End goals from
this point: (a) **harden** by capturing the quality lift in repeatable
evals, (b) **optimise UX** so perceived cost (waiting / confusion) drops
to near-zero, (c) **optimise system perf** so internal latency is small
and the unavoidable LLM latency is masked by streaming + responsiveness.
Each item below is independently grabbable; ordering reflects ROI not
hard dependency.

### E — Eval hardening (Last.fm-aware) 🔴 P0

The current harness pre-dates the enriched corpus. It will not detect
the quality lift Phase B is supposed to deliver because it (a) lacks
scenarios that exercise tag-weight + listener-popularity signals, and
(b) reports per-feature aggregates only — no per-stage latency/cost
breakdown to size optimisation wins.

- **E1 — Per-stage latency + cost telemetry.** Today
  [evaluation/reporting.py:111-164](evaluation/reporting.py#L111-L164)
  rolls latency up by feature (`batch_summary`, `stage2_summary`,
  `profile_update_summary`). Add a per-stage breakdown so Stage 1
  (RAG retrieve), Stage 2 (avoid compliance), Stage 3 (track select),
  and Spotify verify are individually surfaced. Required to size L*
  perf wins (below) before/after measurement is meaningful. Plumb
  through new `stage_timings: dict[str, float]` on `ModelRunResult`.
- **E2 — Last.fm-tag coverage metric.** New column in `comparison.md`:
  for each playlist, % of source candidates that had `lastfm_tags`
  populated. Gate: ≥ 75 % expected (matches corpus-level 66.6 %
  + popularity-weighted retrieval bias toward enriched rows). Catches
  silent corpus regressions where the enrichment field is dropped or
  never populated for selected candidates.
- **E3 — Listener-popularity distribution.** Median + p95 of
  `lastfm_listeners` per playlist. Cheap signal for the "all-mainstream
  vs all-niche" axis. Surface as a column.
- **E4 — Scenario `lastfm_tag_weighting`** (new). Profile prose with
  prominent weighted tags ("post-rock instrumental, slowcore, math
  rock"). Asserts that Stage 1 candidate pool is ≥ 70 % populated by
  artists whose `lastfm_tags` overlap the prose tokens — directly
  exercises [retrieval._artist_tag_weight()](core/src/rag/retrieval.py).
- **E5 — Scenario `niche_only_strict`** (new). Profile prose explicitly
  avoids mainstream ("avoid Billboard chart, avoid radio rotation,
  avoid >1M monthly listeners"). Asserts that p95 `lastfm_listeners`
  on the playlist stays below 100k. Direct test of whether the
  retrieval can de-bias from popularity proxy.
- **E6 — Scenario `post_feedback_tag_regression`** (new). Seeds a
  profile, generates A, dislikes 3 tracks all sharing one Last.fm tag
  (e.g. `synthwave`); asserts B-playlist contains 0 tracks where the
  matched Last.fm tag overlaps the dislike-tag set. Locks in the
  "tags are how avoid actually propagates" assumption.
- **E7 — Smoke baseline run.** Before anything else lands, run all
  existing + new scenarios 3× per model on the new corpus and commit
  the `summary.csv` baseline as `evaluation/baselines/2026-05-06_lastfm.csv`.
  Every later optimisation diffs against this, not the pre-enrichment
  baseline `sweep-merged-5blocks/summary.csv` (deprecated — note in
  the file header).

### Q — Quality (uses new corpus directly) 🟠 P1

- ~~**Q1 — Re-baseline cost-bundle**~~ ✅ Superseded 2026-05-08 by E7 +
  the new **B1** focused probe (see Session 4 deliverables above). E7
  already shows gpt-5.4-mini matches gpt-5.4 on completion + leakage at
  ~30 % cost; gpt-4.1-mini is non-viable (0 tracks, 3/4 scenarios). No
  separate cost-bundle re-baseline needed.
- **Q2 — Last.fm `getSimilar` similarity facet.** Deferred from Phase B
  shipping. Adds a per-artist similarity vector, useful for "expand
  pool around liked artists" without an LLM call. Cost: ~1 extra
  Last.fm call per enriched artist (~145k extra calls — re-uses
  Phase B's cumulative-budget abort). Gate behind Q1 unless E7 shows
  retrieval recall is the binding constraint.
- ~~**Q3 — Wikidata Phase D — country + era facts.**~~ Strikethrough
  2026-05-08. Decision gate satisfied: none of the E7 failures
  (under-fill, niche bias, off-Spotify rate) are country / era shaped.
  Phase D would be a wrong-key fix. Re-open only if a future scenario
  surfaces a country / era miss that A3 / A4 don't address.
- **Q4 — Tag-precedence audit.** `_artist_popularity()` now prefers
  `_lastfm_popularity()` over the MB proxy. Confirm with a 1-shot
  query that the precedence is observable on a known mainstream-vs-
  niche pair. If MB proxy still wins for any non-trivial slice of the
  corpus, the precedence wiring has a bug.

### L — Latency / cost levers (system perf) 🟡 P2

- **L1 — ✅ Stage 2 skip when avoid filter applied.** Already in
  production via the L1 path — no action required, listed for
  completeness.
- **L2 — Spotify artist-metadata cache (per run).** Deduplicate
  Spotify search calls when the same artist recurs across batches.
  Today [playlist.py:518-525](core/src/playlist.py#L518-L525) dedupes
  `(artist, track)` but not `artist`. Memoise `artist_id`/`market_ok`
  per `(run_id, artist_name_normalised)` in a request-scoped dict.
  Estimated win: 1-2 s saved on multi-batch runs, zero quality cost.
- **L3 — Stream Spotify search results via SSE.** Today the SSE stream
  only advances on `batch_verified` (per N tracks). Emit one
  `track_verified` event per successful Spotify match — the user
  sees individual tracks appear as they're confirmed instead of a
  batch landing in one chunk. Expected perceived-latency reduction:
  1-2 s on the first batch (huge mobile/slow-network UX win).
  Touches [app.py /api/run](app.py) + [pipeline.js SSE handler](frontend/static/js/modules/pipeline.js).
- **L4 — Prompt-template memoisation.** [suggestions.py:103-112](core/src/suggestions.py#L103-L112)
  `load_text_file()` re-reads `prompts/*.txt` every batch. Cache once
  at module import. Saves ~5 ms × 10 batches per run; tiny but free.
- **L5 — Stage 3 model downgrade probe.** Compare `gpt-5.4` vs
  `gpt-5.4-mini` for Stage 3 on the new corpus (E7 baseline as
  reference). If quality delta < 5 pp on cite/found and feedback
  leakage stays clean, default Stage 3 to `mini` and save ~20 % cost
  + ~500 ms / batch. Decision is data-only; do not pre-commit.

### U — UX friction reduction (perceived cost) 🟡 P2

- **U1 — Pre-flight Spotify session check.** Currently the
  "Spotify not connected" failure surfaces ~5 s after the user clicks
  Generate (post-`/api/run` auth check). Move the check to a
  non-blocking `/api/session` ping on page load + on focus, gate the
  Generate button on `spotifyAuthStatus === 'authenticated'`. Show a
  prominent "🔗 Reconnect Spotify" button when expired. Eliminates a
  recurring confusion-source.
- **U2 — Distinguish transient vs permanent errors.** Today every
  upstream failure renders as "❌ Network error". Split:
  Spotify 429 → "⏳ Spotify rate-limited, retrying in 30 s…" with
  one auto-retry. OpenAI timeout → "⏳ Model slow, retrying…" with one
  auto-retry. Hard 4xx → "❌ <specific>" with no retry. Touches
  the `_sse_error` helper in [app.py](app.py) and the SSE error
  branch in [pipeline.js:153](frontend/static/js/modules/pipeline.js#L153).
- **U3 — Track-progress UI.** "X / Y tracks verified — est. Z s"
  during generation, refreshed on every `track_verified` event from
  L3. Today only batch-level "starting batch 3" is visible; mobile
  users perceive a stall.
- **U4 — Disable "Use X tracks now" while finalize is in flight.**
  [pipeline.js:73](frontend/static/js/modules/pipeline.js#L73) — set
  `aria-busy="true"` and `disabled` until the finalize SSE returns,
  matching the Settings Save fix from CF-Bug-7.
- **U5 — Better GPT-exhaustion message.** [app.py:1184-1187](app.py#L1184-L1187)
  emits a verbose technical phrase ("GPT suggested only already-known
  tracks for 3 consecutive batches"). Replace with: "Couldn't find
  more matching tracks. Try a smaller playlist or adjust the
  exploration slider." + an actionable button. New i18n key.
- **U6 — Live "Spotify connected" badge.** Status pill in the header
  (green ●  / red ●), refreshed by U1's session check. Eliminates the
  whole class of "I clicked Generate but nothing happened" confusions.

### M — Measurement infrastructure (foundation) 🟢 P3

Required before Q1 / L5 land — any tuning without measurement is
guessing.

- **M1 — Stage spans in `core/src/trace.py`.** Already records
  per-stage candidate sets (F9). Add wall-clock timing + LLM-token
  counters per stage on the same trace bundle. Nothing else has to
  change for E1 to pick this up — the harness already copies the
  bundle into per-run results.
- **M2 — Local perf-baseline test.** New `core/tests/test_perf_baseline.py`
  with millisecond budgets per stage on a frozen corpus subset
  (~5 k artists). Marker `@pytest.mark.perf` so CI excludes by default
  — run only when an `L*` lever lands. Catches regressions like
  `_build_indices` accidentally being O(n²).
- **M3 — Persist per-run perf summary to local sqlite.** One row per
  generation: `run_id, stage_timings_json, token_counts, found_rate,
  exhausted, model`. Lets a longitudinal trend ("did quality / latency
  drift over 3 weeks?") be answered with one SQL query instead of
  re-running the harness. Optional but cheap.

### Suggested execution order

1. **M1** (5-min change to trace bundle) → unlocks E1.
2. **E1, E2, E3** (telemetry surface) → unlocks E7.
3. **E4, E5, E6** (new scenarios) → unlocks E7.
4. **E7 baseline run** — frozen reference for everything that follows.
5. **L2, L3, L4** (free latency wins, no quality risk) — measure
   delta against E7.
6. **U1, U2, U3** (UX wins, parallelisable with L*) — measure
   subjective by trying the app, but L3 is a hard prerequisite for U3.
7. **Q1** (cost-bundle re-baseline) → decide L5.
8. **U4, U5, U6** (UX polish, anytime).
9. **Q2, Q4, Q3** in that order, gated on E7 + Q1 outcomes.

### Decision gates

- After E7: if dislike-rate / leakage didn't drop materially vs
  pre-enrichment baseline, the open product question (bottom of file)
  re-fires before any further investment.
- After L5: if `gpt-5.4-mini` for Stage 3 holds quality, Q1's
  cost-bundle work is largely moot (the lever is bigger than the
  bundle).
- After U1+U6: if the "Spotify not connected" friction class goes
  silent in informal usage, U2's auto-retry investment may be
  premature for production. Keep transient-error labelling, drop the
  retry loop.

## Further research required (gated on enrichment outcome)

These items had concrete plans before the enrichment research; their
relevance, scope, or pass criteria all change once Phase B/D land.
**Do not pursue blindly.** Re-evaluate after enrichment ships and a
fresh canonical eval is collected.

- **P6-EVAL — Phase 6.0 cost-bundle validation** (next-steps.md).
  Originally targeted ~36 % cost reduction on the unenriched corpus.
  Pass criteria (cite/found/cost) all baseline against
  `sweep-merged-5blocks/summary.csv` which is pre-enrichment. Re-run
  **after** Phase B Last.fm enrichment so the validated baseline
  reflects production-relevant retrieval quality.
- **P6-INV13-25 — Pool-size + model-downgrade sweep** (next-steps.md).
  L25 (pool 50 → 30) variance was 16-22 pp on the unenriched corpus.
  Enriched corpus changes pool composition entirely; the sweep must be
  re-run on enriched data, not just multi-seeded on the old one.
- **P6-RELY — L20+L21 Spotify search cache** (next-steps.md).
  Speed/429 lever; still relevant but de-prioritised — Phase A's
  single-GET enrichment changes the Spotify call profile, may shift
  the 429 hotspot.
- **OPEN-2 / P2.3 — Semantic avoid filter** (result-improvement.md (deleted; see git history)).
  Predicated on the LLM-Stage-2 dropping nothing today. Phase B's
  weighted Last.fm tags may close enough of the avoid-vocab gap that
  the semantic post-filter is unnecessary. Decide after enrichment +
  OPEN-1 dislike-rate measurement.
- **OPEN-1 — Manual dislike-rate measurement** (result-improvement.md (deleted; see git history)).
  Still blocking but the measurement target itself shifts: pre- vs
  post-enrichment dislike rates must be measured separately.
- **OPEN-5 / P3.2 — Profile consolidation on overgrowth** (result-improvement.md (deleted; see git history)).
  Independent of enrichment, but acceptance threshold (12 KB after 10
  updates) was set against current profile shape. Re-confirm threshold
  is still binding.
- **OPEN-6 / P3.3 — Periodic feedback absorption** (result-improvement.md (deleted; see git history)).
  Independent of enrichment. Still queued behind OPEN-1.
- **OPEN-8 / Phase 4 — Structured `taste_vector`** (result-improvement.md (deleted; see git history)).
  Replacement for freeform `taste_summary`. Tag vocabulary the vector
  uses depends on the enriched corpus's tag inventory; design only
  after Phase B+D land.
- **Surgical bridge — `corpus_tag_hints`** (corpus_analysis.md (deleted; see git history)
  §"Implementation plan — surgical bridge"). LLM-driven user-prose →
  corpus-vocab translation. Phase B's Last.fm tags + Phase D's Wikidata
  genres may close enough of the vocab gap to make the bridge
  redundant. Re-examine after enrichment.
- **Tag co-occurrence graph** (corpus_analysis.md (deleted; see git history)
  §"Recommended semantic bridge"). Long-term solution to vocab
  mismatch. Phase B's Last.fm tag-weight vectors are a cheaper
  approximation; build the co-occurrence graph only if Phase B fails
  to lift retrieval quality.
- **MB tag rollup (release-group / recording / work → artist)**
  (corpus_analysis.md (deleted; see git history) §"What MusicBrainz can
  help with"). Phase B's Last.fm tags partly substitute. Defer until
  enrichment numbers prove this layer is still needed.

## Dropped / obsolete

- **Spotify corpus enrichment (Phase A)** — disabled 2026-05-04. After
  Feb 2026 API changes, `genres` returns empty for all artists. The only
  field retrieved is `spotify_id`, which has no current consumer. The
  enrichment costs ~12h of API time, carries the highest rate-limit risk
  (21h temp-bans), and adds a failure mode that blocks the entire
  pipeline. `DISABLE_SPOTIFY_ENRICHMENT=1` set on Cloud Run job. Code
  retained in repo for future re-enablement if Spotify restores genres.

- **AcousticBrainz audio features** — service shut down 2022; static
  dump irrelevant for new artists. Permanently out of scope.
- **Spotify `/recommendations` and `/related-artists`** — removed in
  Feb 2026. Phase B's Last.fm `getSimilar` covers the use case.
- **Spotify `popularity` / `followers` ranking signal** — fields
  removed at the API. Replaced by Last.fm `listeners` / `playcount`
  in Phase B.
- **gpt-5.5 model recommendation** — classified unfit
  (result-improvement.md (deleted; see git history) Phase 2.6); already
  removed from defaults.
- **Stage 3 `json_schema` strict mode** — reverted in Phase 2.6;
  do not re-attempt without a new schema strategy.
- **OPEN-4 Stage 1 pool widening on `pool_bad`** — reverted in Phase 2.6.
- **Re-adding `confirmed` artists to `_deny_keys`** — do not pursue
  without canonical eval showing schema-collapse ≤ 5 %.

## Open product question (unanswered)

the user feedback note (formerly TODO.md A1) records a user-stated possibility of scrapping
RAG / Cloud Run / current infrastructure entirely. The enrichment plan
implicitly bets that better corpus data will close the production
quality gap. If Phase B + the eval workflow rework above do **not**
materially improve dislike rate and instruction adherence, the rework
question reopens — at that point the call is a product decision, not a
technical one.

## 🆕 Session 2026-05-11 PM — R1 spike (partial, Spotify 429-blocked)

Full analysis: [`evaluation/baselines/2026-05-11_r1_partial/summary.md`](evaluation/baselines/2026-05-11_r1_partial/summary.md).
Trace bundles: `evaluation/results/20260511-120655/gpt-5.4-mini-iter1/`
(R1 iter 1) and `evaluation/results/20260511-120118/` (R1.2-rejection).

### Prompt edits shipped (`prompts/track_select_{system,user,system_local}.txt`)

- **R1.1** ✅ Must-have cite rule re-stated as a `REMINDER` block at the
  END of `track_select_user.txt` (most-recent instruction at output
  time). Effect at n=1: cite_rate 1.0 on high-confidence batches.
- **R1.3** ✅ `omitted_artists` REQUIRED non-empty with ≥ (N − M)
  entries whenever any APPROVED_ARTISTS entry was skipped. Effect at
  n=1: mini produced its first-ever ≥ 5-entry omission block (28 of 40
  artists per batch with concrete reasons).
- **R1.2** ❌ REJECTED. Tightening "no known: examples" from "OMIT
  unless you recall" to "ALWAYS OMIT" collapsed playlist to 0 / 15 in
  iter 0 (40 / 40 artists omitted). Reverted before iter 1. Re-open
  only after `top_tracks_overlay` coverage expansion.

### UI fix (carried in unstaged working tree)

`frontend/static/css/components.css` had a stray `i` at the top from
the previous session that broke CSS parsing — fixed. The header
`#spotifyStatusPill` removal + body `provider-pills.js` "Spotify
connected" restore from the previous session is correct as shipped.

### Iter-1 numbers (gpt-5.4-mini, n=1, do NOT base design on these)

| Metric | post_fix baseline (n=3) | R1 iter 1 (n=1) | Δ |
|---|---|---|---|
| Playlist A | 13.0 / 15 | 12 / 15 | -7 pp |
| Playlist B | 4.3 / 15 | **6 / 15** | **+11 pp** |
| Cite-rate mean | 86 % | 82 % | -4 pp (within variance) |
| Spotify-found | 40 % | 31 % | -9 pp ⚠️ |
| Cache hit (total) | 53 % | 48 % | -5 pp (REMINDER shifts boundary by 1 chunk) |
| `system_md5` unique | 1 | 1 | ✅ stable |
| `stage3_mode` | custom | custom | ✅ stable |

### Why iter 2 / iter 3 did not land

Spotify 429 on iter 2 batch 2 with `Retry-After=5199 s` (87 min). The
harness 90 s back-off cap cannot recover. Eval killed at 14:31 UTC per
[Operational gates](#operational-gates---spotify-user-token-health)
rule 3. The post_fix run earlier the morning (70 min wall) + this
run's first iter exhausted the user-token's daily/hourly burst budget.
No further evals possible today.

### What we learned about how mini reads the prompt

R1.3's forced `omitted_artists` block gave us the first scaled view of
mini's omission reasoning. From iter 1 batch 1: *"The pool is only a
partial fit, roughly 30-40 % usable … The clearest matches are
Charlotte Sands, Kenny Holland, Fiuk, and SB19; several others look
like they may be wrong-genre, too niche to ground confidently, or not
recallable enough to avoid confabulation."* Five confirmed behaviours:

1. Mini parses `known:` annotations correctly; treats absence as a
   strong omission signal.
2. It self-assesses pool quality realistically (~35 % usable).
3. With the R1.1 REMINDER in place it prefers omission over
   confabulation — 8 well-grounded picks instead of 12 weak ones.
4. It cites Must: traits verbatim when R1.1 is binding (cite 1.0 on
   high-confidence batches).
5. It does **not** compensate for B-pool thinning after dislikes prune
   the candidate set — so the structural fix for B-collapse is **A6
   (RAG re-retrieve on empty batches)**, not more prompt-engineering.

### Next-session execution order (when Spotify quota recovers)

1. **R1 re-baseline at n≥3** — `default × gpt-5.4-mini × 3 iter`
   (~35 min, ~$0.40). Confirm / reject the +11 pp B-completion and
   −9 pp Spotify-found hypotheses. Ship R1.1+R1.3 if cite ≥ 86 % AND
   Spotify-found within ±5 pp of baseline (40 %).
2. **R1 verification on gpt-5.4 at n=3** (~35 min, ~$0.70). Expected
   no-op (gpt-5.4 already did what R1.3 demands per post_fix); verify
   empirically.
3. **OP1 (new, P1)** — provision separate Spotify dev-app credential
   for the eval harness; isolate eval token from interactive session.
   Removes the "two evals per day max" ceiling that blocked this run.
4. **OP2 (new, P2)** — `.spotify-cache` disappears between sessions
   (2nd confirmed occurrence). Investigate harness teardown +
   AV / OS interaction. ~20 min spike.
5. **A6 (P1)** — RAG re-retrieve on consecutive empty Stage-3 batches.
   This run's iter 1 reinforces that B-pool starvation is the dominant
   Playlist-B failure mode on mini.
6. **R1.4 — model-conditional R1.3 strictness.** P2 follow-up.
   Mini gets soft (current), gpt-5.4 gets middle ("ideally list each
   skipped artist — empty list is fine"). Re-run after A6 to see if
   gpt-5.4 found-rate recovers without sacrificing mini's gains.
7. **Cite-rate investigation (P2).** R1-softened cite is −4.5 pp vs
   baseline. May be interaction effect; n=6 across A6 + R1-softened
   should disambiguate.
8. **OP1 / OP2 closed for now** — no rate-limit issues across 4 evals
   today. Reopen only if 429s return.
9. **R1.2 still deferred on top_tracks_overlay coverage**.

---

# 🔬 Research Spike — 2026-05-12 — Faster, cheaper, deeper evaluation

> **Origin.** User asked: *"Spotify rate limit is the real bottleneck.
> Is my developer app really needed just to verify a song exists?
> Could we ask the models unrelated/synthetic things and learn how
> each one reacts much faster?"*
>
> **Method.** Two independent Plan sub-agents researched complementary
> angles in parallel; neither saw the other's output. Their plans are
> reproduced verbatim below (Tracks A and B), followed by a synthesis
> section that identifies the cross-track synergies and recommends a
> single sequenced execution order.
>
> **Status.** Research only. No code changes yet. User review and
> decision needed on the highlighted open questions before any
> implementation work begins.

## Research Track A — Spotify-decoupled evaluation

> **Author:** Research agent A (planning spike, 2026-05-12).
> **Question:** "Do we really need the user's Spotify developer app
> just to verify that a recommended song exists? Can we verify cheaper,
> defer it, or skip it entirely so we can run MORE evals MORE often
> without burning the rate limit?"
> **TL;DR:** Yes — for ~85 % of eval signal we don't need Spotify at
> all. Spotify is only load-bearing for **two** things: (a) `release_year`
> on each track (used by `fit_checks.decade_avoid` — and we can derive
> this from MusicBrainz / Last.fm / iTunes for free), and (b) the
> playlist-push leg (which the eval can skip entirely; pushing is
> cleanup theatre, the eval doesn't read playlists back). The
> Spotify-found rate IS a real signal, but it's a *production-readiness*
> signal, not a model-quality signal — it should be measured separately
> on a single late "ground-truth pass", not on every iter.

### A.1 — What the eval actually consumes from Spotify today

Trace the live code path:

1. **[`evaluation/run_evaluation.py:198-222`](evaluation/run_evaluation.py#L198-L222)** — `check_spotify_not_rate_limited()` fires
   one cheap `sp.search()` pre-flight. **1 call per session.**
2. **[`core/src/playlist.py:695-769` `iter_search_tracks`](core/src/playlist.py#L695-L769)** — invoked from `app.py` inside the
   SSE `/api/run` per batch. **One `sp.search(limit=1, type=track,
   market=from_token)` per deduped (artist, track).** L2 cache
   ([`_RUN_SEARCH_CACHE`](core/src/playlist.py#L612-L692)) dedupes
   *within* a run only.
3. **[`evaluation/harness.py:489-506` `_step_push_to_spotify`](evaluation/harness.py#L489-L506)** —
   `playlist_mod.add_to_playlist(...)`: creates an empty playlist (1
   call), then adds tracks in batches of ≤100 (1-2 calls per playlist).
   **~3 calls / playlist × 2 playlists/run = ~6 calls/run.**
4. **[`evaluation/harness.py:542-577` `_cleanup`](evaluation/harness.py#L542-L577)** — deletes both playlists. **2 calls/run.**

The signals downstream consumers actually read from Spotify responses:

| Field | Used where | Eval-critical? |
|---|---|---|
| `uri`, `track_id` | `add_to_playlist` (push step) | No — eval doesn't read playlists back |
| `cover_url`, `preview_url`, `spotify_url`, `album_url`, `artist_url` | Frontend display only | **No** |
| `artist_id` | Push step (sorting, dedup) | No |
| `release_date` → `release_year` | [`fit_checks.compute_fit` → `decade_avoid`](evaluation/fit_checks.py) | **Yes** — but derivable from MB / Last.fm / iTunes |
| existence (track found at all) | `playlist_track_count`, completion gate, Spotify-found % column | **Yes** — but answerable from cheaper sources |

**Bottom line:** Of the seven Spotify-derived fields, **six are dead
weight for evaluation**. Only `release_year` and "does it exist" carry
eval signal, and both have cheaper sources.

### A.2 — Rate-limit budget model (current vs proposed)

Per `run_for_model` (one model × one scenario × one iter):

| Stage | Calls | Source |
|---|---:|---|
| Playlist A — Stage 3 verify | ~30-40 | `_PLAYLIST_SIZE=15-30`, 2-4 batches × ~10 deduped tracks, L2 cache helps cross-batch (~20 % hit rate observed in B1 traces) |
| Playlist A — push (create + add) | 2-3 | `add_to_playlist` |
| Playlist B — Stage 3 verify | ~30-40 | Same shape; L2 cache larger overlap with A |
| Playlist B — push | 2-3 | |
| Cleanup (A + B delete) | 2 | |
| **Total per run** | **~65-90** | |

For typical E7 scope (4 models × 11 scenarios × 1 iter = 44 runs):
**~3,000-4,000 search calls / session**. At the current
`SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S=1.5` + serial mode that's **75-100
min of pure throttle wall time, plus 4 h+ of serial Spotify latency,
plus the 10 min inter-run cooldown × 43 boundaries = 7 h of cooldown
alone**. The 14 h Retry-After 429 hit on 2026-05-08 (B1) and the 87 min
Retry-After hit on 2026-05-11 (R1 partial) both fell inside this
envelope.

**Proposed L0/L1/L2 architecture (see A.4)** drops eval Spotify calls
to **3-10 per session** total (one pre-flight + an optional batched
ground-truth sample on the final playlist). That's **~99.8 % reduction**.

### A.3 — Alternative existence-verification sources

#### MusicBrainz `recording` search — **PRIMARY for L1**
- Verifies: artist + recording (title) exists in the canonical music
  metadata DB.
- Auth: none. Free.
- Rate limit: **1 req/s per IP** for the public server (hardcoded; will
  return 503 if exceeded). Self-hosted mirror = unlimited.
- Coverage vs Spotify: MB is the *upstream* metadata source most
  streaming services license from. Effective coverage for any track
  >30 days old is ≥ 98 %. Recent (<30 d) drops to ~70-80 %. The
  artists we recommend come from the corpus itself, which IS a MB
  dump — so the artist side is by definition 100 %.
- Latency: 200-400 ms per query in EU; cacheable.
- Endpoint: `GET https://musicbrainz.org/ws/2/recording/?query=artist:"X"%20AND%20recording:"Y"&fmt=json&limit=1`
- **Recommendation: PRIMARY L1.** Accuracy on titles is highest of any
  free source; the 1 req/s limit is fine when an entire eval session
  needs ≤ 200 fallback queries (L0 absorbs the rest).

#### Last.fm `track.getInfo` — **FALLBACK for L1**
- Verifies: artist + track string match in Last.fm's scrobble graph.
- Auth: `api_key` only (already provisioned for Phase B enrichment in
  the Cloud Run job).
- Rate limit: 5 req/s recommended, generous burst. No daily cap.
- Coverage vs Spotify: Last.fm has ~150M+ tracks; for popular artists
  ≥ 99 %, for niche/non-Western artists noticeably weaker than MB.
- Latency: 100-200 ms.
- Endpoint: `?method=track.getInfo&artist=X&track=Y&api_key=...&format=json`
- **Recommendation: FALLBACK to MB.** Faster (no 1 req/s ceiling) but
  string matching is fuzzier (Last.fm normalises titles aggressively
  and reports false positives for similar-titled different tracks).
  Useful when MB returns 503 / 1 req/s saturated.

#### iTunes Search API — **FALLBACK / cross-check**
- Verifies: artist + track in Apple Music catalogue.
- Auth: none.
- Rate limit: ~20 req/min undocumented soft cap (returns 403 if abused).
- Coverage: ≥ 95 % overlap with Spotify (similar licensing). Stronger
  on Western mainstream, weaker on Asian indie / Bandcamp-tier.
- Latency: 150-300 ms.
- Endpoint: `https://itunes.apple.com/search?term=X+Y&entity=song&limit=1`
- **Recommendation: REJECT as PRIMARY** (rate limit too tight),
  **ACCEPT as cross-check** for "does this exist on a streaming
  service" when MB+Last.fm both miss. Useful sanity-check pass.

#### Deezer public search — **REJECT**
- No auth, no documented rate limit, but coverage skews heavily
  Western European and undocumented. Adds a third moving part for
  marginal gain over iTunes.

#### Local RAG corpus + `top_tracks_overlay.json` — **PRIMARY for L0**
- The corpus already ships [`artists.jsonl.gz`](data/rag_corpus/)
  (174 200 artists, 66.6 % Last.fm-tagged) + a `top_tracks_overlay.json`
  produced by [`build-tools/build_top_tracks_overlay.py`](build-tools/build_top_tracks_overlay.py).
- Verifies: artist + ≥1 known released track per artist (up to 5).
- Auth: none. Local file lookup.
- Latency: < 1 ms (in-memory hash).
- Coverage vs Spotify: the overlay is *itself* built from Spotify
  search, so every entry is by definition Spotify-resolvable. **This
  is the highest-confidence existence signal we have, and it's free.**
  Coverage is the open question — current overlay was built for the
  default scenario's retrieval pool only.
- **Recommendation: PRIMARY L0.** Resolves any (artist, track) where
  the track string matches an overlay entry (with fuzzy/normalised
  matching). The Stage 3 prompt already biases toward overlay
  tracks ("known: examples"), so eval hit rate should be high.
- **Coverage extension path:** expand `build_top_tracks_overlay.py`
  to cover the full eval scenario set — one offline Spotify-budget run
  primes a cache that lasts months. Estimated ~5 000 artists ×
  1 call each = 5 000 Spotify calls, done once.

#### Wikipedia / Wikidata — **REJECT for track-level**
- Wikipedia covers ~5 % of recorded tracks, mostly chart hits.
  Wikidata `P175` (performer) coverage is similar. Useful for
  artist-level country/era facts (deferred Phase D in next-steps.md)
  but not track existence.

#### Pure offline normalisation (no verification) — **PRIMARY for "deferred" mode**
- Don't verify at all. Run Stages 1-3, capture model output verbatim,
  let `fit_checks` and `leakage` audit do their work on the
  GPT-emitted (artist, track) strings + RAG metadata.
- **Recommendation: PRIMARY for the new "skip-verify" eval mode** (A.5).
  Gives up Spotify-found % as a quality signal — which the data
  already shows is dominated by *retrieval* quality, not Stage 3
  quality (E7 lastfm_tag_weighting collapsed to 7-27 % despite
  reasonable Stage 3 picks).

### A.4 — Tiered verification architecture

```
┌─────────────────────────────────────────────────────────────┐
│ L0  Local overlay + corpus fuzzy match              < 1 ms  │
│     - corpus.by_name_normalised → artist exists             │
│     - top_tracks_overlay → track exists for artist          │
│     Hit-rate target: ≥ 80 % on typical eval pools           │
├─────────────────────────────────────────────────────────────┤
│ L1  MusicBrainz recording search (1 req/s)        ~300 ms   │
│     fallback → Last.fm track.getInfo (5 req/s)              │
│     fallback → iTunes search                                │
│     Hit-rate target: lift L0+L1 combined to ≥ 95 %          │
├─────────────────────────────────────────────────────────────┤
│ L2  Spotify search (production path)              ~200 ms   │
│     ONLY for: (a) production playlist creation,             │
│               (b) optional eval ground-truth sample.        │
└─────────────────────────────────────────────────────────────┘
```

**Production unchanged.** `core/src/playlist.iter_search_tracks` still
hits Spotify; that's load-bearing for `uri`/`cover_url` which the user
sees in the playlist. Production cannot run on L0/L1.

**Eval split.** A new `verify_mode` setting on `Scenario` (or a CLI
flag on `run_evaluation.py`) selects:

- `verify_mode = "spotify"` (current behaviour, default for the
  manual ground-truth-sample run).
- `verify_mode = "l0"` (overlay-only; fastest, lowest coverage).
- `verify_mode = "l0_l1"` (overlay → MB → Last.fm fallback chain).
- `verify_mode = "deferred"` (no per-run verify; Spotify batch at the
  end across all runs).
- `verify_mode = "none"` (skip verify entirely; rely on fit + leakage
  + corpus metrics).

**How this slots into `iter_search_tracks` without breaking production:**
introduce a verifier interface, not a code path branch. New module
`core/src/verify.py`:

```
class Verifier(Protocol):
    def verify(self, artist: str, track: str) -> VerifyResult | None: ...
```

Implementations: `SpotifyVerifier` (today's logic, wrapping
`_do_spotify_search`), `OverlayVerifier`, `MusicBrainzVerifier`,
`LastfmVerifier`, `ChainVerifier(*verifiers)` (first hit wins),
`NullVerifier` (always returns "found" with stub metadata).

Production wires `SpotifyVerifier` only. Eval wires
`ChainVerifier(OverlayVerifier, MusicBrainzVerifier, LastfmVerifier)`
based on `verify_mode`. The verifier interface returns the same
`VerifyResult` shape (artist, track, release_year, optional
source_uri) so downstream code (`fit_checks`, `leakage`, harness
metric collection) is unchanged.

### A.5 — Deferred verification mode (eval-only)

**Design.** Stages 1-3 run normally. Verifier returns a synthetic
"found" result with `release_year=None`. Eval completes in ~5-10 min
per run instead of ~15-30 min, and burns **zero Spotify quota**.

**What signal we LOSE:**
- Per-iter Spotify-found % (today's dominant production-readiness
  signal).
- `release_year` → `decade_avoid` fit check (one of two fit checks
  in the harness; the other is leakage which is fully offline).
- Honest under-fill detection — if Stage 3 picks ghost tracks, we
  won't know without a ground-truth pass.

**What signal we KEEP:**
- **Cite-rate** (must-have / soft-pref / avoid citations in Stage 3
  rationales) — pure model behaviour signal, no Spotify needed.
- **Leakage** ([`evaluation/leakage.py`](evaluation/leakage.py))
  — compares (artist, track) strings against profile artists /
  feedback. No Spotify needed.
- **Completion shape** (raw Stage 3 yield count vs target). Slightly
  inflated vs reality (some picks won't exist) but tracks the
  *Stage 3* completion behaviour cleanly — which IS the model-quality
  question.
- **Omission discipline** (R1.3-softened: `omitted_artists` shape +
  reasoning content).
- **A/B prompt regression** (post-feedback Playlist B vs A) —
  unaffected by Spotify presence.
- **Corpus coverage metrics (E2/E3)** — Last.fm tag % and listener
  distribution. Pure corpus lookup.
- **Stage timing + cost telemetry (E1)** — `stage_metrics_a/b`
  from the trace bundle. Pure model-side data.

**Ground-truth pass.** Once a week (or after a meaningful Stage 3
change), run ONE eval with `verify_mode = "spotify"` across the full
matrix to re-baseline Spotify-found % and the decade fit check. With
L2 cache + reasonable batching this is the 3-4 h run we have today —
unchanged. The other ~20 evals per week run in 5-10 min each on L0/L1
or deferred mode.

**Batched late-verification (alternative to skip-entirely).** A new
script `evaluation/late_verify.py` reads every run's `summary.json`
under `evaluation/results/{ts}/`, extracts the verbatim Stage 3
output, dedupes (artist, track) pairs across ALL runs in the session,
and fires Spotify search ONCE per unique pair (with the existing L2
cache amortising across runs). For a typical session with ~600 unique
pairs across 20 runs, this is a ~600-call single batch instead of
3 000-4 000 spread across 20 runs — **~6× reduction even when full
ground-truth is wanted**. Then `late_verify.py` patches
`summary.json` files with the Spotify-found numbers.

### A.6 — Concrete implementation steps

1. **New module `core/src/verify.py`** — Protocol + implementations:
   - `SpotifyVerifier` — wraps current `_do_spotify_search`.
   - `OverlayVerifier` — reads `RagCorpus.by_name_normalised` +
     `top_tracks` per row + fuzzy title match (uses
     `corpus.normalise_name` + a new `normalise_title` helper).
   - `MusicBrainzVerifier` — one HTTP call, 1 req/s throttle,
     persistent disk cache at `<APP_DIR>/.mb_verify_cache.sqlite`.
   - `LastfmVerifier` — reuses `build-tools/lastfm_enrichment/client.py`
     `LastfmClient` style; `getInfo` endpoint.
   - `ChainVerifier` — first-hit-wins composite.
   - `NullVerifier` — for deferred mode.
2. **Refactor [`core/src/playlist.py:612-769`](core/src/playlist.py#L612-L769)** —
   extract the Spotify search logic into `SpotifyVerifier`. Keep
   `iter_search_tracks` and `search_tracks` as the production
   entry points; they receive the verifier as a parameter
   (default `SpotifyVerifier` so production behaviour is identical).
3. **Plumb verifier selection from eval harness:**
   - Add `verify_mode: str = "spotify"` to
     [`Scenario`](evaluation/scenario.py#L40).
   - Add `--verify-mode` CLI flag to
     [`run_evaluation.py`](evaluation/run_evaluation.py) overriding
     the scenario value.
   - Build the verifier in [`harness.run_for_model`](evaluation/harness.py#L582-L632)
     based on `scn.verify_mode`, monkey-patch
     `playlist_mod._VERIFIER` (or pass through as a kwarg to
     `iter_search_tracks`) before the SSE generator consumes it.
4. **Skip the push step in deferred / L0 / L1 modes.** The push leg
   ([`harness._step_push_to_spotify`](evaluation/harness.py#L489-L506))
   only exists so the user can audit; if we don't have Spotify URIs
   we can't push anyway. Gate it on `verify_mode == "spotify"`.
5. **Adapt `fit_checks.decade_avoid`** to accept a `None`
   `release_year` (current behaviour: rule skipped per track) — already
   does this; verify with a test.
6. **Optional: `evaluation/late_verify.py`** — reads
   `results/<ts>/*/summary.json` and fires the batched
   ground-truth pass.
7. **Expand `top_tracks_overlay.json`** — generalise
   [`build_top_tracks_overlay.py:_build_seed_profile`](build-tools/build_top_tracks_overlay.py#L54-L72)
   to iterate over all scenarios (`evaluation/scenario.SCENARIOS`),
   union the retrieval pools, and run one comprehensive
   Spotify-fed overlay build. This is a one-shot operation that
   primes the L0 cache for every future eval. Estimated ~5 000 search
   calls, run once during off-hours.
8. **Tests:**
   - Unit tests for each verifier (with mocked HTTP).
   - `ChainVerifier` fallback behaviour.
   - Eval harness with `NullVerifier` produces correct
     `playlist_status="ok"` + skipped push + non-empty leakage report.
   - Existing tests assume `SpotifyVerifier` default — should pass
     unchanged.

### A.7 — Risks & open questions

1. **Overlay coverage on niche scenarios.** The current overlay was
   built for the `default` scenario. Niche scenarios
   (`brazilian_samba_funk`, `club_techno_strict`,
   `niche_only_strict`) will have lower L0 hit rates → more L1
   fallbacks → MB's 1 req/s ceiling matters again. *Mitigation:*
   step #7 above primes overlay across all scenarios.
2. **MB rate limit is per-IP, not per-app.** Persistent disk cache
   means each unique (artist, track) is queried only once across all
   eval sessions, so the practical ceiling is much higher than it
   looks.
3. **String matching is fuzzier than Spotify.** As long as L0/L1
   confirm existence under SOME normalisation, leakage/fit audits
   (which compare on Stage-3-emitted strings) are unaffected.
4. **`release_year` from MB.** MB recordings carry
   `first-release-date` which is more accurate than Spotify's
   per-release date. Free upgrade.
5. **🔴 Decision needed: keep playlist-pushes alive in `verify_mode =
   "spotify"` only?** Three options:
   - **A.** Push only when `verify_mode == "spotify"`. (Recommended —
     preserves current audit workflow on ground-truth runs, drops
     the cost on fast runs.)
   - **B.** Add `push_playlist: bool` to Scenario, decoupled from
     verify mode.
   - **C.** Never push from eval; rely on the eval-log slice + trace
     bundle for audit.
6. **Eval-mode "found %" reporting.** Report BOTH numbers in
   `comparison.md` when a ground-truth pass exists; make the
   "official" quality signal explicit in the header.
7. **`niche_only_strict` scenario benefits most** from decoupling —
   its acceptance criterion is already a pure corpus metric.

### A.8 — Expected impact

| Mode | Spotify calls/session | Wall clock (44-run E7) | OpenAI cost |
|---|---:|---:|---:|
| Today (`spotify` everywhere) | ~3 500 | ~10 h (incl. cooldowns) | ~$3-8 |
| `l0_l1` everywhere | ~5 | ~2-3 h (no cooldowns needed) | ~$3-8 |
| `deferred` everywhere | 0 | ~2 h | ~$3-8 |
| `deferred` + late batched verify | ~600 (single batch) | ~3-4 h | ~$3-8 |
| Mixed: `l0_l1` for 19/20 runs, `spotify` for 1 | ~85 | ~4 h | ~$3-8 |

**Operational unlock:** the "two evals per day max" ceiling
disappears in every mode except today's. R1 can run with n=10 instead
of n=3 in the same session, settling the variance question that
B1 and R1 partial runs both flagged.

## Research Track B — Synthetic model-behaviour probes

> **Author:** Research agent B (planning spike, 2026-05-12).
> **Question:** "Can we ask the models unrelated/synthetic things to
> see HOW each one reacts, learn faster and cheaper, and use that to
> predict full-eval outcomes before burning a 40-min Spotify-gated run?"
> **TL;DR.** The 2026-05-11/12 R1 baselines surfaced a phenomenon we
> cannot afford to keep discovering through full evals: *the same
> prompt edit produces opposite reactions across models.* R1.3-strict
> lifted gpt-5.4, collapsed mini. R1-softened reversed it. We burned
> **~$1.90 + ~2.5 h + 12 Spotify-token bursts** to discover one
> structural fact a 30-second probe would have predicted. This track
> designs a battery of synthetic, Spotify-free, mostly fixed-prompt
> micro-probes that fingerprint *how a model reads instructions*
> before we spend a single token on a full eval. Probes do not
> replace the full eval (they cannot measure Spotify-found or
> real-pool diversity), but they should become the **primary
> regression gate for prompt edits**, with the full eval reserved
> for pre-release confirmation.

### B.0 — Motivation: what we paid to learn the hard way

| Run | Cost | Wall | Finding (in one line) |
|---|---|---|---|
| R1.3-strict mini (n=3, 2026-05-12) | ~$0.18 | ~30 min | Mini collapses on `MUST contain N−M` quota wording. |
| R1.3-strict gpt-5.4 (n=3, 2026-05-12) | ~$0.74 | ~40 min | gpt-5.4 ALSO collapses (2/3 empty B) — contradicts prior prediction. |
| R1-softened mini (n=3, 2026-05-12) | ~$0.24 | ~35 min | Soft wording recovers mini. |
| R1-softened gpt-5.4 (n=3, 2026-05-12) | ~$0.74 | ~40 min | Soft wording *regresses* gpt-5.4 (`found` -10 pp). |

A static, deterministic probe against fixed JSON inputs can answer
that question in **3 OpenAI calls and ~30 s** per model.

### B.1 — Taxonomy of measurable model-behaviour properties

For each property: (a) what it predicts about production, (b) cheap
synthetic probe(s), (c) scoring rubric. Ranked by predictive value
for failure modes we have actually observed.

#### B-1. Constraint-grammar sensitivity (MUST vs SHOULD vs MAY)
- **Predicts.** Whether a prompt switching from SHOULD to MUST will
  surprise-collapse the model into satisfying the secondary
  constraint at the expense of the primary task — the R1.3 finding.
- **Probe.** Same minimal task, three modal-verb variants. Task:
  "Return a JSON list of 8 colours, each a single English word."
  Secondary variants: `SHOULD avoid colours containing 'e'` /
  `MUST avoid colours containing 'e'` / `MUST contain ≥ 6 colours
  avoiding 'e'`.
- **Rubric.** `soft_compliance`, `hard_compliance`,
  `quota_preserved_under_hard` (load-bearing column — mini gets 0
  on the strict variant).
- **Cost.** 3 calls × ~300/300 tokens ≈ $0.001 mini / $0.01 gpt-5.4.

#### B-2. Over-constraint collapse (output-shape inflation)
- **Predicts.** Direct analogue of R1.3-strict: mini inflated
  `omitted_artists` to (N−M) and dropped picks.
- **Probe.** "Return 10 song-title suggestions for a hypothetical
  'cyberpunk lo-fi' playlist. Also return `rejected_candidates`;
  AIM for at least 20 with reasons." Strict variant: "MUST contain
  ≥ 20 rejected_candidates."
- **Rubric.** `playlist_length / requested_length` ×
  secondary-quota-met.
- **Cost.** ~$0.002 mini / $0.02 gpt-5.4.

#### B-3. Confabulation pressure / calibration
- **Predicts.** Whether the model invents fake-but-plausible
  content under quota pressure. Directly predicts Spotify-found
  regressions.
- **Probe.** "List 12 real published novels by the (fictional)
  author 'Olwen Marrick'. JSON only. **Must be real published
  novels.**" A calibrated model returns 0 or refuses.
- **Rubric.** `omission_rate = (12 − returned) / 12`;
  `well_calibrated` = 1 if ≥ 0.8 AND any returned entries flag
  uncertainty.
- **Cost.** ~$0.001 / $0.008.

#### B-4. Omission discipline
- **Predicts.** Whether the model can produce an honest "I cannot
  ground these" list without padding.
- **Probe.** JSON array of 25 fictitious-sounding artist names
  mixed with 5 real famous ones; "For each artist you cannot
  confidently name a real released track of, add to
  `unknown_artists`."
- **Rubric.** `omission_precision`, `omission_recall`,
  `padding_rate`.
- **Cost.** ~$0.002 / $0.02.

#### B-5. Format adherence under content contradiction
- **Probe.** Unsatisfiable constraint: "Return JSON with 5 entries.
  Every artist must be Japanese. Never include any artist whose
  name uses katakana/hiragana/kanji/romaji."
- **Rubric.** 5-bucket: `(a)` empty valid JSON, `(b)` JSON+prose,
  `(c)` invented entries, `(d)` malformed JSON, `(e)` content
  violation. Want `a`/`b`.
- **Cost.** ~$0.001 / $0.008.

#### B-6. Self-consistency floor (variance, not mean)
- **Predicts.** Minimum n for any other measurement. If σ on a
  fixed prompt is 15 pp, n=3 means lie.
- **Probe.** Re-issue B-2 5× with `seed=N`, temperature 0. σ of
  primary + secondary lengths.
- **Rubric.** `n_required_for_5pp_signal`. Surfaces on every
  fingerprint card.
- **Cost.** ~$0.008 / $0.06.

#### B-7. Era / genre parametric awareness (no retrieval)
- **Probe.** "List 15 ambient music artists active 1990–1999.
  JSON `[{name, peak_year}]`. Only real artists." Repeat for
  math rock 2000–2010, Brazilian samba-funk 1970–1985.
- **Rubric.** LLM-judge or hand-curated allowlist `accuracy`.
  ≥ 60 % → RAG is quality lift; < 30 % → RAG load-bearing.
- **Cost.** ~$0.005 / $0.04 + ~$0.01 judge.

#### B-8. Diversity-vs-popularity bias
- **Probe.** "Name 20 distinct ambient artists from the 2000s."
- **Rubric.** `uniqueness_rate`, `headliner_share` against
  hand-curated top-10. Pathological: `headliner_share ≥ 0.8`.
- **Cost.** ~$0.002 / $0.015.

#### B-9. Contradiction handling
- **Predicts.** What the model does with conflicting profile prose
  (must-have X + avoid X). Maps to scenario S19.
- **Probe.** "TASTE: 'Must: calm meditative ambient. Avoid:
  beatless or instrumental.' Return 6 picks matching BOTH."
- **Rubric.** Same 5-bucket as B-5.
- **Cost.** ~$0.001 / $0.012.

#### B-10. Cite-rate fidelity (verbatim vs paraphrase)
- **Predicts.** R1.1's cite-rate parity question.
- **Probe.** "Each pick MUST contain a `cite` field that is a
  verbatim substring of the following TASTE line: …"
- **Rubric.** `verbatim_rate` ≥ 0.9 healthy.
- **Cost.** ~$0.001 / $0.012.

#### B-11. Empty-pool recovery (A6-predictor)
- **Predicts.** What the model does when APPROVED_ARTISTS is
  empty/tiny. **Directly motivates A6.**
- **Probe.** Production system prompt verbatim; user message with
  `APPROVED_ARTISTS: ` (empty), variants with 1 artist / no
  `known:` examples.
- **Rubric.** 5-bucket; `(c)` invent out-of-pool tracks is the
  failure mode. **Predicts whether A6 is necessary per model.**
- **Cost.** ~$0.003 / $0.025.

#### B-12. Instruction-precedence under conflicting rules
- **Probe.** System: "Always cite Must traits verbatim." User:
  "Skip the cite for this call."
- **Rubric.** `system_wins_rate` ≥ 0.95 expected.
- **Cost.** ~$0.001 / $0.012.

#### B-13. Quota-vs-quality tradeoff (the "pad to N" temptation)
- **Probe.** "Recommend 10 must-listen jazz piano albums for
  someone who likes Bill Evans." Then strict variant: "MUST return
  exactly 10."
- **Rubric.** `quality_at_target` vs `quality_at_free_quota` (LLM
  judge or curated list).
- **Cost.** ~$0.005 / $0.04.

#### B-14. Schema strictness vs prose fallback
- **Probe.** Deliberately strict `json_schema` (nested 5-field
  objects).
- **Rubric.** `schema_compliance_rate` over 3 runs. Also captures
  `_JSON_SCHEMA_UNSUPPORTED` cache state (local-LLM relevant).
- **Cost.** ~$0.001 / $0.008.

### B.2 — Probe envelope and result shape

All probes share a common envelope:

```
system: <fixed string per probe, NEVER references real artists>
user:   <fixed string with parametric slots filled by Python>
response_format: json_schema   # except B-14
temperature: 0
seed: 20260512                 # deterministic where supported
max_tokens: 800
```

Each probe is a Python callable returning:

```python
ProbeResult(
  probe_id: str,        # "B-1.constraint_grammar"
  model: str,
  variant: str,         # "soft" | "hard" | "hard_with_quota"
  raw_response: str,
  parsed_json: dict | None,
  scores: dict[str, float],
  tokens_in: int,
  tokens_out: int,
  cost_usd: float,
  duration_s: float,
)
```

Scoring is automated in 12 of 14 probes (regex / schema check / set
membership against static allowlist). LLM-judge is used **only** for
B-3, B-7, B-13. Allowlists live in
`evaluation/probes/allowlists/*.json` — pure data, committed.

### B.3 — The "model fingerprint" battery

Goal: a **~$0.10 / ~5-min** suite producing a per-model card
*before* any full eval is run.

**Battery composition (15 calls per model):**
B-1×3, B-2×2, B-3×1, B-4×1, B-5×1, B-6×5, B-10×2.
(B-7/B-8/B-11/B-13 diagnostic; opt-in via `--full`.)

**Cost per model.**
- gpt-5.4-mini: ~$0.009.
- gpt-5.4: ~$0.23 (consider quarterly cadence, or n=3 not 5 on B-6).
- Local LLMs: free.

**Output card (one YAML/JSON per model):**

```yaml
model: gpt-5.4-mini
captured_at: 2026-05-13T08:00:00Z
fingerprint_version: 1
system_fingerprint: <openai snapshot id>
properties:
  constraint_grammar:
    soft_compliance: 0.7
    hard_compliance: 1.0
    quota_preserved_under_hard: 0.4   # ← would have predicted R1.3-strict collapse
  over_constraint_collapse:
    primary_length_ratio: 0.55
    score: COLLAPSES
  confabulation_pressure:
    omission_rate: 0.83
    score: WELL_CALIBRATED
  omission_discipline:
    precision: 1.0
    recall: 0.72
    padding_rate: 0.36
    score: VERBOSE
  variance_floor:
    primary_entries_sigma: 0.6
    secondary_entries_sigma: 2.1
    n_required_for_5pp_signal: 5
  cite_fidelity:
    verbatim_rate_strict: 0.95
    paraphrase_contamination: 0.04
verdict:
  fit_for_strict_quota_wording: NO
  fit_for_soft_quota_wording: YES
  fit_for_zero-shot_genre_recall: PARTIAL
  recommended_n_for_eval: 5
```

The `recommended_n_for_eval` field alone closes the door on the
"B1 n=3 might have been lucky" determinism worry.

### B.4 — Where probes slot into the eval workflow

**Current workflow:** edit prompt → 40-min full eval → analyse →
iterate.

**Proposed workflow:**
1. Edit prompt.
2. Run probe battery for affected models (~5 min, ~$0.25).
3. Inspect fingerprint diff vs the baseline card committed alongside
   the prompt.
4. If a fingerprint regresses on a known-load-bearing property →
   reject change, iterate from (1).
5. If fingerprint OK → run a **single scenario × 1 iter** smoke
   (~5 min, ~$0.10).
6. If smoke OK → run full eval **only at PR-merge time**.

**Mapping to existing scenarios** in
[`evaluation/scenario.py`](evaluation/scenario.py):
- B-9 ↔ `CONTRADICTORY_PROFILE_SCENARIO`
- B-8 ↔ `NICHE_ONLY_STRICT_SCENARIO`
- B-1/B-2 ↔ no scenario yet — probes are the only way we measure
  this property
- B-7 ↔ `BOOM_BAP_90S_SCENARIO`, `BRAZILIAN_SAMBA_FUNK_SCENARIO`
- B-11 ↔ no scenario — would be A6's acceptance test

Probes are a **predictor** of scenario outcomes, not a replacement.

### B.5 — Worked feedback-loop examples

**Example A — would R1.3-strict have shipped?**
1. Edit `prompts/track_select_system.txt` to require
   `omitted_artists ≥ N−M`.
2. Run battery for gpt-5.4-mini.
3. B-1 `quota_preserved_under_hard` drops 0.9 → 0.4. **Red flag.**
4. B-2 `primary_length_ratio` drops to 0.55. **Confirmed.**
5. **Reject the strict edit without spending a full-eval dollar.**

Total cost of catching the regression: **$0.01**. Actual cost paid
on 2026-05-12: **$1.90 + 2.5 h + Spotify burn**.

**Example B — should we have known A6 was needed?**
1. Run B-11 against gpt-5.4-mini.
2. Empty-pool variant returns 5 invented tracks (bucket `c`).
3. **Fingerprint flags `pool_starvation_recovery: BAD`** →
   directly motivates A6 without a full eval.

### B.6 — Implementation plan

**Location.** New package `evaluation/probes/`.

```
evaluation/probes/
  __init__.py
  runner.py             # ProbeRunner, ProbeResult, fingerprint aggregation
  probe_b1_constraint.py
  probe_b2_overconstraint.py
  probe_b3_confabulation.py
  probe_b4_omission.py
  probe_b5_format.py
  probe_b6_consistency.py
  probe_b7_era.py
  probe_b8_diversity.py
  probe_b9_contradiction.py
  probe_b10_cite.py
  probe_b11_empty_pool.py     # uses production system prompt verbatim
  probe_b12_precedence.py
  probe_b13_quota_quality.py
  probe_b14_schema.py
  allowlists/
    ambient_2000s.json
    jazz_piano_bill_evans_neighbours.json
    famous_artists.json
  fingerprints/                # one file per (model, fingerprint_version)
    gpt-5.4-mini.v1.json
    gpt-5.4.v1.json
  cli.py                # `python -m evaluation.probes ...`
```

**Reuse of existing infra:**
- OpenAI calls via `core.src.openai_http.chat_completions_create`
  (handles JSON-schema auto-downgrade, telemetry).
- Probe results flow through `core.src.trace.log_batch_summary`-
  compatible events so they land in `eval.jsonl` with `kind: "probe"`.
- Cost computation via the same dict in
  `evaluation/run_evaluation.py`.
- Reporting: extend `evaluation/reporting.py` with
  `render_fingerprint_diff(old, new)`.

**Versioning.** Fingerprints committed at
`evaluation/probes/fingerprints/<model>.v<N>.json`. A prompt PR is
expected to include either (a) the post-change fingerprint with no
regression, or (b) an explanation of why a regression is acceptable.

### B.7 — What probes DO NOT measure (be honest)

Probes are **proxies**, not production. They will disagree with the
full eval in these directions:

- **Spotify-found rate.** Probes never call Spotify. Always run a
  full eval before a release.
- **RAG-augmented behaviour.** Probes use minimal or absent
  APPROVED_ARTISTS blocks. Production has 40–80 grounded candidates.
- **Feedback-loop / profile-evolution effects.** Playlist B failures
  are partly about how profile refinement reshapes prose.
- **Tail-end cost.** Probes use ~500-token prompts; production
  ~3 000-token with cache hits.
- **Cross-stage interactions.** R1.3-strict gpt-5.4 (productive
  constraint) is visible only because `pool_assessment` reasoning
  fed back into Stage 3 selection.
 
**Rule of thumb.** A probe regression is a *strong reason to
investigate*; a probe pass is a *necessary but not sufficient*
condition for shipping. Final acceptance is always the full eval.
### Track B — Recommended sequencing
1. ~~**Step 1 — Skeleton + B-1 + B-6 only.**~~ ✅ Done 2026-05-12
   (shipped as part of the combined Step 1+2 push below).
2. ~~**Step 2 — Add B-2, B-3, B-4, B-5, B-10, B-11.**~~ ✅ Done 2026-05-12.
   New package [evaluation/probes/](evaluation/probes/) with `runner.py`
   (ProbeResult / Fingerprint / `run_probe` / `run_battery` /
   `aggregate_fingerprint` / pricing table / lenient JSON parser with
   code-fence stripping), all 8 probe modules
   (`probe_b1_constraint.py` through `probe_b11_empty_pool.py`), the
   B-4 allowlist at `allowlists/famous_artists.json` (5 famous + 25
   fictitious), and a CLI at `python -m evaluation.probes` (dry-run by
   default; `--confirm` required for real billing; `--battery default`
   = all 8 probes, `--battery minimal` = B-1 + B-6,
   `--probes B-1,B-6` for ad-hoc selection). B-6 reuses B-2's strict
   prompt and adds a custom `aggregate()` that emits sigma + an
   `n_required_for_5pp_signal` field for the fingerprint card. B-11
   loads the production system prompt verbatim and tests two pool
   shapes (`empty_pool`, `single_artist_no_known`). Zero touch to
   production code — runner accepts an injectable `openai_call` so
   tests never reach OpenAI; default uses
   `core.src.openai_http.chat_completions_create`. 35-test suite in
   [core/tests/test_evaluation_probes.py](core/tests/test_evaluation_probes.py)
   covers runner envelope + token/cost bookkeeping + call-failure
   isolation + code-fence parse + each probe's success/failure rubric
   + fingerprint custom-aggregator routing + CLI dry-run path +
   unknown-probe-prefix exit. Default-battery dry-run reports 16 calls
   / ~$0.004 estimated for gpt-5.4-mini. 962 core tests green (was
   927). **Out of scope (Step 4 / Step 6):** `--probe-check` gate on
   `run_evaluation.py` and the diagnostic-only probes (B-7, B-8, B-12,
   B-13, B-14).
3. ~~**Step 3 — Capture baseline fingerprints**~~ ✅ Done 2026-05-12.
   Three v1 cards captured live and committed under
   [evaluation/probes/fingerprints/](evaluation/probes/fingerprints/):
   `gpt-5.4-mini.v1.json` ($0.004 / 84 s), `gpt-5.4.v1.json` ($0.060
   / 105 s), `gpt-4.1.v1.json` ($0.049 / 56 s) — ~$0.11 total. **Two
   structural findings already returned more value than the
   $1.90 R1.3 spike:** (a) B-1 `quota_preserved_under_hard` =
   mini 0.00 vs gpt-5.4 / gpt-4.1 1.00 — retroactively predicts the
   R1.3-strict collapse; (b) B-11 `single_artist_no_known` =
   **bucket_c (confabulates) on ALL THREE models** — directly motivates
   widening A6's trigger condition to `len(approved_artists) <= 1`,
   not `== 0`. B-6 `n_required_for_5pp_signal` differs 17× across
   models (gpt-4.1=5, gpt-5.4=19, mini=85), demonstrating that the
   static `iterations=3` in `evaluation/settings.ini` understates
   noise on the mini and gpt-5.4 rows of every full eval. Ollama
   local-LLM baseline deferred — no eval-relevant local model
   currently in use.
4. ~~**Step 4 — Wire `render_fingerprint_diff` + `--probe-check` gate.**~~
   ✅ Done 2026-05-12. New [evaluation/probes/diff.py](evaluation/probes/diff.py)
   ships `render_fingerprint_diff(baseline, new)` (markdown table:
   probe / variant / baseline / new / Delta / Direction / Flag) and
   `detect_regressions(baseline, new, *, extra_tolerance=0.0)`
   returning `Regression` objects. Direction-of-improvement is
   hard-coded in `DIRECTION` per (probe_id, score) — 32 directional
   scores covering all 8 probes; counts (`returned_count`,
   `declared_count`, etc.) are intentionally informational. Default
   tolerance 0.05 with per-score overrides for B-6's count metrics
   (e.g. `n_required_for_5pp_signal` tolerates a ±5-run drift, not
   ±0.05). [run_evaluation.py](evaluation/run_evaluation.py) gained
   `--probe-check` + `--no-probe-gate` flags and a `run_probe_gate()`
   helper invoked AFTER scenario validation but BEFORE
   `confirm_or_exit`; missing baseline → informational warning, no
   abort. Aborts with exit code 7 on regression unless override.
   ASCII-only output (no Δ / ❌ / ✅) so Windows cp1252 consoles
   don't UnicodeEncodeError. 10 new tests in
   [test_evaluation_probes.py](core/tests/test_evaluation_probes.py)
   cover directional regress + tolerance + informational-skip + B-6
   count-tolerance override + markdown rendering + baseline-path
   conventions. Smoke-tested: self-diff of all three captured
   baselines yields 0 regressions; injected R1.3-style regression
   on gpt-5.4's `quota_preserved_under_hard` is detected exactly.
   972 core tests green (was 962).
5. **Step 5 — Adopt on the next prompt PR (R1.4).** Expect
   fingerprints to confirm the model-conditional split before any
   full eval is spent.
6. **Step 6 — Ship the remaining diagnostic probes** (B-7, B-8,
   B-12, B-13, B-14). Per the user decision (S.6 #5) these land in
   the catalogue from day one, even though they are NOT in the
   default fingerprint battery — available for on-demand deep dives.
---
## 🔀 Synthesis — Where Tracks A and B fit together
The two tracks attack the same root problem ("evals are expensive,
slow, and rate-limit-bound") from two complementary angles:
| | **Track A (verifier decoupling)** | **Track B (synthetic probes)** |
|---|---|---|
| **Removes** | Spotify rate-limit ceiling | Need to run full evals to learn model personality |
| **Cost saving** | ~99 % fewer Spotify calls; wall-clock 10 h → 2 h | ~$0.01 to catch what cost $1.90 last week |
| **Coverage** | Same scenarios as today, run faster | New axis of measurement (model fingerprint) |
| **Risk** | Possible found-% drift between L1 and Spotify | Probes are proxies, not ground truth |
| **Production touch** | Refactors `core/src/playlist.py` (verifier abstraction) | Zero — additive new package only |
| **Decision needed** | Push-step policy (S.6 #1 — RESOLVED option A) | None — purely additive |
### S.1 — Strong synergy: probes RUN ON Track A's NullVerifier
Probes are *exactly* the workload that wants `verify_mode = "none"`
from Track A. If we land Track A's verifier abstraction first, then
Track B's probes naturally use `NullVerifier` (or no verifier at all,
since probes call `chat_completions_create` directly). Conversely,
several Track B probes — B-7 (era awareness), B-8 (diversity bias),
B-11 (empty pool) — can be viewed as **degenerate evaluations** that
don't need Spotify, which is exactly the new Track-A capability.
Both tracks introduce *abstraction over the Spotify dependency*.
Track A abstracts at the *verifier* level (does this track exist?).
Track B sidesteps the dependency entirely by asking *different
questions* that don't require verification. Layers of the same
defence in depth, not competing approaches.
### S.2 — Strong synergy: fingerprints inform scenario selection
Once Track B's fingerprint card carries `recommended_n_for_eval` and
`fit_for_<X>` verdicts, the harness can:
- Skip scenarios where a model's fingerprint says it's structurally
  unfit (e.g. don't run `niche_only_strict` on a model with
  `headliner_share ≥ 0.8`).
- Auto-scale iterations per scenario based on `variance_floor`.
This compounds Track A's wall-clock win: not just *cheaper per run*
but *fewer runs needed*.
### S.3 — Weak overlap: B-11 (empty pool probe) and A's deferred mode
B-11 uses the production system prompt and an empty
APPROVED_ARTISTS list — but does NOT push to Spotify. It is
technically a probe (Track B) that uses Track A's deferred /
NullVerifier infrastructure. **Recommendation: ship as a probe in
Track B** to keep the catalogue versioning consistent. The scenario
route remains available later if we want to re-test under realistic
post-feedback profile prose.
### S.4 — No overlap: alternative verifiers vs LLM-judge
Track A's MusicBrainz/Last.fm/iTunes verifiers and Track B's
LLM-judge scoring (used only in B-3/B-7/B-13) operate on entirely
different inputs and answer different questions. No conflict.
### S.5 — Merged execution order (locked 2026-05-12)
Per S.6 #2 (user-confirmed): Phase 1 fully ships before Phase 2
starts. No parallelisation.
**Phase 1 — Track B probes (additive, zero production risk):**
1. ~~**Track B Step 1+2**~~ ✅ Done 2026-05-12 — probe runner +
   B-1, B-2, B-3, B-4, B-5, B-6, B-10, B-11 shipped in
   [evaluation/probes/](evaluation/probes/) with 35-test coverage
   ([core/tests/test_evaluation_probes.py](core/tests/test_evaluation_probes.py)).
   Captures every probe that retroactively explains R1.3, pool
   starvation, variance-floor, confabulation, and cite-fidelity
   concerns. Zero touch to production code. CLI:
   `python -m evaluation.probes --model <m> --battery default --confirm`.
2. **Track B Step 3** — capture fingerprints for `gpt-5.4-mini`,
   `gpt-5.4`, `gpt-4.1`, plus one local LLM. Total OpenAI cost
   ~$0.30. **This single output already answers the user's "how do
   models react to unrelated things" question.**
3. **Track B Step 6** — ship the remaining diagnostic probes (B-7,
   B-8, B-12, B-13, B-14). Per S.6 #5 the full 14-probe catalogue
   lands; the 7-probe fingerprint subset remains the default
   invocation shape, with the diagnostic probes available for
   on-demand deep dives.
4. ~~**Track B Step 4**~~ ✅ Done 2026-05-12 — `render_fingerprint_diff` +
   `detect_regressions` in [evaluation/probes/diff.py](evaluation/probes/diff.py),
   `--probe-check` / `--no-probe-gate` flags wired into
   [run_evaluation.py](evaluation/run_evaluation.py) (exit code 7 on
   regression). Probes ARE now the regression gate for prompt PRs.
   Phase 1 complete.
**Phase 2 — Track A verifier decoupling (refactors production code):**
5. ~~**Track A Steps 1–3**~~ ✅ Done 2026-05-12. New
   [core/src/verify.py](core/src/verify.py) ships the `Verifier`
   `Protocol` + `SpotifyVerifier` (thin wrapper around
   `_do_spotify_search` — zero Spotify-behaviour change) + `NullVerifier`
   (synthesises `("found", track)` with all Spotify-shaped enrichment
   keys as `None` so downstream `release_year` parsing + SSE-event
   builder never KeyError). [playlist.py](core/src/playlist.py) gained
   module-level `_VERIFIER = None` + `set_verifier()` / `get_verifier()`
   / `clear_verifier()`; `iter_search_tracks` picks the worker function
   via a single `if _VERIFIER is None` branch so the production
   Spotify path stays byte-for-byte identical when no verifier is
   installed. [scenario.py](evaluation/scenario.py) gained
   `verify_mode: str = "spotify"` (default preserves current behaviour
   across all 11 scenarios — pinned by a new test).
   [run_evaluation.py](evaluation/run_evaluation.py) gained
   `--verify-mode {spotify,null}` flag applied via
   `dataclasses.replace` after `--seed-profile` so the two compose.
   [harness.run_for_model](evaluation/harness.py) now (a) installs
   the scenario-selected verifier on `playlist_mod` before the first
   Stage-3 call, (b) gates BOTH `_step_push_to_spotify` invocations
   (playlist A + playlist B) on `scn.verify_mode == "spotify"` per
   S.6 #1, (c) `clear_verifier()`s in the outer `finally` so a leaked
   verifier can never bleed into the next model's run. `app.py` is
   untouched — the production SSE endpoint never sees the new path.
   14 new tests across [test_verify.py](core/tests/test_verify.py) +
   [test_evaluation_scenario.py](core/tests/test_evaluation_scenario.py)
   cover Protocol satisfaction (`runtime_checkable`), NullVerifier
   passthrough + key shape + non-mutation, SpotifyVerifier delegation,
   the playlist module slot + clear alias, end-to-end
   `iter_search_tracks` with NullVerifier proving the Spotify path is
   NOT called, and `verify_mode` field default + replace-override
   contract. 986 core tests green (was 972). **Out of scope (S.5 #6-7
   queued next):** OverlayVerifier + MusicBrainzVerifier + LastfmVerifier
   + ChainVerifier + late_verify.py + overlay rebuild across all 11
   scenarios.
6. ~~**Track A Step 4**~~ ✅ Done 2026-05-12 (`OverlayVerifier` + rebuild script).
   [verify.py](core/src/verify.py) now ships `OverlayVerifier` +
   `normalise_title` helper (lowercases, strips diacritics, drops
   trailing parenthetical / bracketed annotations like
   ``"(Remastered 2024)"``, collapses punctuation + whitespace).
   Lookup is O(1) on `RagCorpus.by_name_normalised` then equality OR
   either-side substring match against the artist's `top_tracks`. On
   hit, returns Spotify-shaped enrichment with all keys `None` plus
   audit breadcrumbs `verified_by="overlay"` and `overlay_match=<the
   matched overlay title>`. `--verify-mode overlay` wired through
   [run_evaluation.py](evaluation/run_evaluation.py) →
   [scenario.verify_mode](evaluation/scenario.py) →
   [harness.run_for_model](evaluation/harness.py) (overlay mode pulls
   the live corpus via `suggestions.get_rag_corpus()` and falls back
   to `NullVerifier` with a warning when no RAG corpus is loaded).
   Push step skipped in overlay mode (S.6 #1 — `verify_mode ==
   "spotify"` gate already covers every non-spotify mode). 15 new
   tests in [test_verify.py](core/tests/test_verify.py) covering
   `normalise_title` (lowercase / parens-stripping / punctuation /
   diacritics / whitespace / empty), `OverlayVerifier` exact match /
   remaster suffix / case + punctuation insensitivity / artist-missing
   / empty-top-tracks / title-missing / empty fields / Protocol
   satisfaction / non-mutation. 1001 core tests green (was 986).
   **S.6 #4 rebuild script — code shipped 2026-05-12, execution
   deferred.** [build_top_tracks_overlay.py](build-tools/build_top_tracks_overlay.py)
   gained `--scenarios all|<comma-list>` (unions
   `retrieve_candidates` pools across multiple scenarios, deduped by
   mbid), `--resume` (reads existing overlay and skips fetched
   mbids — multi-session safe), and `--checkpoint-every N` (flush
   overlay to disk every N successful fetches; default 25 so a crash
   loses ≤ 25 artists). The per-artist loop catches
   `SpotifyException(429)`, checkpoints + exits with code 5 when
   `Retry-After > 3600 s`, and prints the exact `--resume` command
   for the next session. Default `--throttle-ms 210` preserved for
   single-scenario back-compat; help text steers multi-scenario runs
   toward `≥ 2000 ms`. **Operations task still pending user
   trigger:** actually run
   `python build-tools/build_top_tracks_overlay.py --scenarios all
   --resume --throttle-ms 2000` and let the multi-session build
   complete. Today's overlay (built for `default` scenario) remains
   the data source `OverlayVerifier` reads until the rebuild lands;
   niche scenarios will see lower L0 hit rates in the meantime.
7. ~~**Track A Step 5**~~ ✅ Done 2026-05-12.
   [verify.py](core/src/verify.py) now ships `MusicBrainzVerifier`
   (one `/ws/2/recording` HTTP call per (artist, track) miss; 1 req/s
   throttle with slack; persistent SQLite cache at
   `<APP_DIR>/.verify_cache.sqlite`; clean abort on `Retry-After > 90 s`
   to honour MB's polite-API contract), `LastfmVerifier` (track.getInfo
   via `LASTFM_API_KEY`; short-circuits to not_found when the key is
   unset so the chain falls through cleanly), and `ChainVerifier`
   (first-hit-wins composite, exception-tolerant per constituent so a
   misbehaving verifier never breaks the chain). The shared
   `_SqliteVerifyCache` namespaces rows by verifier name + lowercases
   the (artist, title) key for case-insensitive cache hits. New
   `--verify-mode l0_l1` choice wires
   `Overlay → MusicBrainz → Lastfm` in
   [run_evaluation.py](evaluation/run_evaluation.py) and
   [harness.py](evaluation/harness.py); L0 short-circuit means
   second-and-later eval sessions on the same scenario pay zero
   MusicBrainz quota. 18 new tests cover SQLite cache round-trip /
   verifier-namespacing / cross-instance persistence; MB hit + miss +
   cache-skip + Retry-After abort; Last.fm no-key path + hit + error-6
   cache; Chain first-hit / fall-through / all-miss / exception
   isolation / empty rejection / Protocol satisfaction.
8. ~~**Track A Step 6**~~ ✅ Done 2026-05-12. New
   [evaluation/late_verify.py](evaluation/late_verify.py) walks a
   completed session's per-run dirs, extracts every unique
   `(artist, track)` from each `eval.jsonl`'s `batch_summary` rows
   (case-insensitive dedup), runs `SpotifyVerifier` against the
   deduped set, and writes `late_verify.json` next to the slice
   with `{total, found, not_found, errors, results: [...] }`.
   Idempotent (skip when `late_verify.json` exists); `--force`
   re-verifies. CLI accepts either a session root or a single per-run
   dir. 13 new tests in
   [test_late_verify.py](core/tests/test_late_verify.py) cover
   batch-summary extraction + case-insensitive dedup + non-batch-row
   skipping + malformed-JSON skipping + empty-field skipping +
   verify_tracks success/exception bookkeeping + writeback +
   idempotence + force + discover_run_dirs (session root vs per-run
   dir).
**Phase 3 — Validation (single session):**
9. **Track A Step 7** — side-by-side `spotify` vs `l0_l1` baseline
   to characterise found-% delta. Document offset in
   `documentation/TechnicalManual.md`.
10. **Track B Step 5** — adopt probe-first workflow on R1.4
    (model-conditional R1.3 strictness). Expect the fingerprints to
    confirm the model split before any full eval is spent.
### S.6 — User decisions (locked 2026-05-12)
All five open questions resolved by the user in the same session the
research spike was delivered. Locked answers below; treat as
authoritative for the implementation phases.
1. **✅ Track A push-step policy = Option A.** Push only when
   `verify_mode == "spotify"`. In every other mode the harness skips
   `_step_push_to_spotify` and the cleanup-delete pair entirely.
   Unblocks Track A Step 4 (A.6 #4).
2. **✅ Phasing = Phase 1 (Track B) first, then Phase 2 (Track A).**
   No parallelisation. Probes are additive (no production touch) and
   produce the fingerprint cards the user most directly asked for.
   Track A's refactor of `core/src/playlist.py` ships *after* probes
   are available to validate the refactor doesn't change model
   behaviour.
3. **✅ No default eval mode.** The user explicitly opted out of any
   "everyday vs weekly" cadence. Every eval is **on-demand and
   investigation-driven**; the user picks `--verify-mode` per
   invocation based on what question that specific run is answering.
   No timeline, no scheduled runs, no implicit default flip. The
   `verify_mode = "spotify"` value remains the code-default (zero
   behaviour change for any unspecified call) until the user says
   otherwise on a specific run. **Implementation note:** do NOT add
   scheduling, cron, or "auto-promote to ground-truth" logic. Ship
   the CLI flag and stop.
4. **✅ Overlay one-shot rebuild approved — but throttle hard.** OK
   to spend ~5 000 Spotify calls to prime L0 across all 11
   scenarios, **subject to the Spotify rate-limit reality**. The
   B1 / R1 sessions taught that bursty traffic on the user token
   triggers multi-hour Retry-After penalties. Treat the overlay
   build as a **slow background pass**:
   - Re-use the `SPOTIVIBE_SPOTIFY_SEARCH_SERIAL=1` +
     `SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S=2.0` (or higher) settings
     already proven safe for serial eval runs.
   - Persist progress to disk after every N artists so a 429-kill
     resumes from the last checkpoint instead of restarting.
   - Spread across multiple sessions if needed. There is no
     deadline.
   - Abort cleanly on the first Retry-After > 1 h and surface the
     resume command, mirroring the eval harness behaviour.
   Spec the build script's resume + throttle behaviour before
   kicking off; do NOT just blast 5 000 sequential calls.
5. **✅ Ship all 14 probes (B-1 through B-14).** The 7-probe
   "fingerprint battery" subset (B.3) remains the *default
   invocation shape* — the smaller suite that runs on every prompt
   PR — but the full catalogue lands in code so the diagnostic
   probes (B-7 era awareness, B-8 diversity bias, B-12 instruction-
   precedence, B-13 quota-vs-quality, B-14 schema strictness) are
   available for on-demand deep dives without further development.
   Track B Step 2 absorbs B-2 through B-11; Step 6 closes out B-12,
   B-13, and B-14 in the same shipping push.
### S.7 — Estimated combined impact
If both tracks land:
- **Eval iteration loop:** prompt edit → fingerprint diff (5 min,
  $0.25) → smoke (5 min, $0.10) → optional full eval at PR-merge
  (~2 h, ~$3, ~5 Spotify calls). Compare to today: prompt edit →
  full eval (40 min, $0.25–$0.74, ~70 Spotify calls).
- **Discovery latency for "this prompt regresses model X":**
  ~30 seconds (probe) vs ~40 minutes (full eval).
- **Spotify rate-limit ceiling:** effectively eliminated for eval
  workloads. Reopen OP1/OP2 only when production traffic itself
  scales.
- **Variance floor:** measured, not guessed. `recommended_n_for_eval`
  per model replaces the current static `n=3`.


---

## 📸 Appendix — Screenshot capture checklist (2026-05-14)

The agent cannot capture screenshots. For each row below, log into the
listed dashboard with a non-production browser profile, navigate to the
described view, then save the screenshot at the target path (overwrite
the existing 800×450 placeholder). Keep the same dimensions (~800×450)
for visual consistency.

### G0 — OpenRouter API key (NEW — default provider)

| # | Target path | What to capture |
|---|---|---|
| 1 | `documentation/assets/guides/openrouter/step1_signin.png` | [openrouter.ai](https://openrouter.ai) landing page with the **Sign In** button visible in the header. |
| 2 | `documentation/assets/guides/openrouter/step2_keys.png` | [openrouter.ai/keys](https://openrouter.ai/keys) — the Keys list page (after sign-in). |
| 3 | `documentation/assets/guides/openrouter/step3_create.png` | The "Create Key" modal with the name field visible (mock a name like `SpotyVibe`; do NOT capture an actual key value). |
| 4 | `documentation/assets/guides/openrouter/step4_credits.png` | [openrouter.ai/credits](https://openrouter.ai/credits) — the credit balance + deposit page (blur or mask the actual €/$ balance). |

### G1 — OpenAI API key (still placeholders)

| # | Target path | What to capture |
|---|---|---|
| 1 | `documentation/assets/guides/openai/step1_signin.png` | [platform.openai.com](https://platform.openai.com) sign-in / landing page. |
| 2 | `documentation/assets/guides/openai/step2_sidebar.png` | OpenAI dashboard with the **API keys** entry highlighted in the left sidebar. |
| 3 | `documentation/assets/guides/openai/step3_create.png` | The "Create new secret key" modal with the name field visible. |

### G2 — Spotify developer app (still placeholders)

| # | Target path | What to capture |
|---|---|---|
| 1 | `documentation/assets/guides/spotify/step1_dashboard.png` | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) — empty or populated dashboard with **Create app** button visible. |
| 2 | `documentation/assets/guides/spotify/step2_create.png` | Spotify "Create app" form — name `SpotyVibe`, description any text, **Web API** + **Web Playback SDK** checkboxes ticked. |
| 3 | `documentation/assets/guides/spotify/step3_redirect.png` | The same form scrolled to the **Redirect URIs** field with `http://127.0.0.1:5000/callback` filled in. |
| 4 | `documentation/assets/guides/spotify/step4_secret.png` | Created-app settings page with **Client ID** + **View client secret** visible (mask the actual values). |

### G3 — Python install macOS (still placeholders)

| # | Target path | What to capture |
|---|---|---|
| 1 | `documentation/assets/guides/python-macos/step1_homebrew.png` | Terminal showing `brew --version` output (proves Homebrew installed). |
| 2 | `documentation/assets/guides/python-macos/step2_install.png` | Terminal output of `brew install python@3.12`. |
| 3 | `documentation/assets/guides/python-macos/step3_verify.png` | Terminal showing `python3 --version` returning `Python 3.12.x`. |
| 4 | `documentation/assets/guides/python-macos/step4_venv.png` | Terminal showing `python3 -m venv venv && source venv/bin/activate` with the prompt prefix change. |

### G4 — Python install Linux (still placeholders)

| # | Target path | What to capture |
|---|---|---|
| 1 | `documentation/assets/guides/python-linux/step1_update.png` | Terminal output of `sudo apt update`. |
| 2 | `documentation/assets/guides/python-linux/step2_install.png` | Terminal output of `sudo apt install python3 python3-pip python3-venv`. |
| 3 | `documentation/assets/guides/python-linux/step3_verify.png` | Terminal showing `python3 --version` returning `Python 3.10+`. |

### Help-page screenshots (`/docs/screenshots/*.png`)

Separately, `documentation/help.{en,de,jp}.md` references 44
in-app-UI screenshots under `docs/screenshots/01_…44_…`. Those are
captured automatically by the screenshot test suite — run:

```bash
python -m pytest frontend/tests/test_documentation_screenshots.py -m screenshots
```

(The `screenshots` marker is excluded by default — the suite only runs
on explicit invocation. See CLAUDE.md.) No manual capture needed.

