# Next Steps — 2026-05-02

Consolidated forward plan after the RAG enrichment research pass. Drops
items the multi-source enrichment work supersedes; flags items whose
relevance is now contingent on enrichment results.

## Reference documents

- [documentation/rag_enrichment_plan.md](documentation/rag_enrichment_plan.md) — multi-source enrichment plan (Spotify fix + Last.fm + Discogs + Wikidata + ListenBrainz)
- [corpus_analysis.md](corpus_analysis.md) — corpus coverage diagnosis, vocab-mismatch findings, surgical bridge
- [cost-speed-research.md](cost-speed-research.md) — 26-lever cost/speed audit
- [result-improvement.md](result-improvement.md) — phase-by-phase implementation history
- [TODO.md](TODO.md) — full deferred-items register

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
[TODO.md A1](TODO.md).

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
9. **Phase D — Wikidata structured facts** ([rag_enrichment_plan.md §D](documentation/rag_enrichment_plan.md)).
   Highest-value next layer because it directly fixes the F1 must-have
   gate failure for "Japanese music" / "American artists" documented in
   [corpus_analysis.md](corpus_analysis.md). Order C↔D is flexible —
   take D first if eval scenarios remain country-constrained.
10. **Phase C — Discogs styles** ([rag_enrichment_plan.md §C](documentation/rag_enrichment_plan.md)).
    Broadens tag vocab where MB is sparse (electronic, hip-hop, niche).

### 🟢 P3 — Should-fix (independent of enrichment)

From [TODO.md](TODO.md):

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

### 🟢 P4 — Nice-to-have polish (from TODO.md)

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

### Current execution — `spotivibe-rag-builder-ltrfp` (2026-05-04)

Started 2026-05-04 ~07:45 UTC. MB build completed at 07:58, Last.fm
enrichment started at 07:58 with all 174,200 artists (no cap). Spotify
enrichment skipped (`DISABLE_SPOTIFY_ENRICHMENT=1` confirmed in logs).

**Expected completion: ~01:15 UTC 2026-05-05 (~03:15 Vienna).**

### ⏰ VERIFY on 2026-05-05 morning

```bash
# 1. Execution status
gcloud run jobs executions describe spotivibe-rag-builder-ltrfp \
  --region=us-central1 \
  --format='value(status.completionTime,status.conditions[0].type)'

# 2. New manifest? built_at should be 2026-05-04 or 2026-05-05
gcloud storage cat gs://spotivibe-rag-corpus/manifest.json

# 3. No halt flag?
gcloud storage ls gs://spotivibe-rag-corpus/halt.flag  # should be NotFound

# 4. Spot-check Last.fm fields in the new corpus
gcloud storage cp gs://spotivibe-rag-corpus/artists.jsonl.gz /tmp/c.jsonl.gz
zcat /tmp/c.jsonl.gz | head -100 | grep -c '"lastfm_listeners"'  # > 0
zcat /tmp/c.jsonl.gz | head -100 | grep -c '"lastfm_tags"'       # > 0

# 5. Full enrichment stats
zcat /tmp/c.jsonl.gz | python -u -c "
import sys, json
total=0; lf=0
for l in sys.stdin:
    r=json.loads(l); total+=1
    if r.get('lastfm_listeners'): lf+=1
print(f'Total: {total}, Last.fm enriched: {lf} ({100*lf/total:.1f}%)')
"
```

If successful: download the new corpus locally, verify in the app,
then set the fixed monthly schedule (1st of each month). If failed:
check logs with
`gcloud logging read "labels.\"run.googleapis.com/execution_name\"=spotivibe-rag-builder-ltrfp" --limit=30 --order=desc`.

## Further research required (gated on enrichment outcome)

These items had concrete plans before the enrichment research; their
relevance, scope, or pass criteria all change once Phase B/D land.
**Do not pursue blindly.** Re-evaluate after enrichment ships and a
fresh canonical eval is collected.

- **P6-EVAL — Phase 6.0 cost-bundle validation** ([TODO.md](TODO.md) P6-EVAL).
  Originally targeted ~36 % cost reduction on the unenriched corpus.
  Pass criteria (cite/found/cost) all baseline against
  `sweep-merged-5blocks/summary.csv` which is pre-enrichment. Re-run
  **after** Phase B Last.fm enrichment so the validated baseline
  reflects production-relevant retrieval quality.
- **P6-INV13-25 — Pool-size + model-downgrade sweep** ([TODO.md](TODO.md) P6-INV13-25).
  L25 (pool 50 → 30) variance was 16-22 pp on the unenriched corpus.
  Enriched corpus changes pool composition entirely; the sweep must be
  re-run on enriched data, not just multi-seeded on the old one.
- **P6-RELY — L20+L21 Spotify search cache** ([TODO.md](TODO.md) P6-RELY).
  Speed/429 lever; still relevant but de-prioritised — Phase A's
  single-GET enrichment changes the Spotify call profile, may shift
  the 429 hotspot.
- **OPEN-2 / P2.3 — Semantic avoid filter** ([result-improvement.md](result-improvement.md)).
  Predicated on the LLM-Stage-2 dropping nothing today. Phase B's
  weighted Last.fm tags may close enough of the avoid-vocab gap that
  the semantic post-filter is unnecessary. Decide after enrichment +
  OPEN-1 dislike-rate measurement.
- **OPEN-1 — Manual dislike-rate measurement** ([result-improvement.md](result-improvement.md)).
  Still blocking but the measurement target itself shifts: pre- vs
  post-enrichment dislike rates must be measured separately.
- **OPEN-5 / P3.2 — Profile consolidation on overgrowth** ([result-improvement.md](result-improvement.md)).
  Independent of enrichment, but acceptance threshold (12 KB after 10
  updates) was set against current profile shape. Re-confirm threshold
  is still binding.
- **OPEN-6 / P3.3 — Periodic feedback absorption** ([result-improvement.md](result-improvement.md)).
  Independent of enrichment. Still queued behind OPEN-1.
- **OPEN-8 / Phase 4 — Structured `taste_vector`** ([result-improvement.md](result-improvement.md)).
  Replacement for freeform `taste_summary`. Tag vocabulary the vector
  uses depends on the enriched corpus's tag inventory; design only
  after Phase B+D land.
- **Surgical bridge — `corpus_tag_hints`** ([corpus_analysis.md](corpus_analysis.md)
  §"Implementation plan — surgical bridge"). LLM-driven user-prose →
  corpus-vocab translation. Phase B's Last.fm tags + Phase D's Wikidata
  genres may close enough of the vocab gap to make the bridge
  redundant. Re-examine after enrichment.
- **Tag co-occurrence graph** ([corpus_analysis.md](corpus_analysis.md)
  §"Recommended semantic bridge"). Long-term solution to vocab
  mismatch. Phase B's Last.fm tag-weight vectors are a cheaper
  approximation; build the co-occurrence graph only if Phase B fails
  to lift retrieval quality.
- **MB tag rollup (release-group / recording / work → artist)**
  ([corpus_analysis.md](corpus_analysis.md) §"What MusicBrainz can
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
  ([result-improvement.md](result-improvement.md) Phase 2.6); already
  removed from defaults.
- **Stage 3 `json_schema` strict mode** — reverted in Phase 2.6;
  do not re-attempt without a new schema strategy.
- **OPEN-4 Stage 1 pool widening on `pool_bad`** — reverted in Phase 2.6.
- **Re-adding `confirmed` artists to `_deny_keys`** — do not pursue
  without canonical eval showing schema-collapse ≤ 5 %.

## Open product question (unanswered)

[TODO.md A1](TODO.md) records a user-stated possibility of scrapping
RAG / Cloud Run / current infrastructure entirely. The enrichment plan
implicitly bets that better corpus data will close the production
quality gap. If Phase B + the eval workflow rework above do **not**
materially improve dislike rate and instruction adherence, the rework
question reopens — at that point the call is a product decision, not a
technical one.
