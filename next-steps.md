# Next Steps — 2026-05-04

Consolidated forward plan. Open tasks, decisions, and gated research items.

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
- **C2 — Per-run cost preview UI.** Before generation: show
  estimate based on profile size + chosen model + playlist size
  (e.g. "≈ $0.04"). If the estimate exceeds a configurable cap
  (default $0.15) prompt "Switch to fast mode for $0.04?".
  Touches [generate_section.html](frontend/templates/generate_section.html)
  + a new `/api/cost_estimate` route in [app.py](app.py).
  Goal is *predictability* of spend; the structural fixes (C1, C3)
  do the actual saving.
- **C3 — OPEN-5 profile consolidation on overgrowth.** When profile
  JSON exceeds a threshold (originally proposed 12 KB; revisit
  against current shape), summarise older history into a per-artist
  aggregate digest ("Beatles — 24 tracks suggested") that replaces
  verbatim long-tail entries while keeping the recent ~60-100 tracks
  verbatim for dedup safety. Caps prompt growth at saturation.
  Design note 2026-05-08 (user-proposed): the per-artist count form
  is the right replacement for the current 4-in-200 `[EXHAUSTED]`
  binary — gives the model a finer "this artist is heavily explored"
  signal than the binary tag, at significantly lower token cost
  than the verbatim list. Pair the count with a threshold (e.g. ≥ 8
  tracks → `[EXHAUSTED]`) so the exhaust signal stays binary at the
  prompt level.
- **C4 — Stage 3 prompt slimming + OpenAI prompt caching investigation.**
  System prompt is ~5 KB and identical across batches in one /api/run.
  Caching the cached portion at ~10 % of normal input cost is a
  ~30 % Stage 3 input win **if** the OpenAI 2026 API tier exposes it.
  First step: read the current Anthropic / OpenAI provider docs for
  caching support on the gpt-5.x family. Touches
  [prompts/song_user.txt](prompts/song_user.txt) /
  [openai_http.py](core/src/openai_http.py).
- **C5 — Compact JSON Stage 3 schema.** Verbose JSON (~80 tokens
  per track) → single-line schema (`{"a":"X","t":"Y"}`, ~25 tokens).
  Output side win ~60 %, but output is only ~30 % of total →
  ~18 % overall. Risk: schema fragility / parser brittleness.
  Lower priority than C1-C4.

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
