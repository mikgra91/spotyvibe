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
- [context/context_todo.md](context/context_todo.md) — condensed TODO state
- [context/context_potential-issues.md](context/context_potential-issues.md) — eval-workflow gap analysis
- [context/context_implementation-state.md](context/context_implementation-state.md) — compressed phase summary

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
3. **Phase A — fix Spotify enrichment** ([rag_enrichment_plan.md](documentation/rag_enrichment_plan.md) §A).
   Replace removed `GET /artists` batch with sequential `GET /artists/{id}`;
   drop dead `popularity` / `followers` fields. Without this, the next
   scheduled Cloud Run rebuild produces a corpus missing all Spotify
   genres.

### 🟠 P1 — Eval workflow rework (independent of corpus)

From [context_potential-issues.md](context/context_potential-issues.md):
current eval does **not** test the production failure path
(disliked-band re-recommendation after profile update). This is the
single biggest reason "evals pass while production fails" per
[TODO.md A1](TODO.md).

4. **Add post-feedback regression pass to eval harness.** Generate
   playlist A → apply dislikes → refine train → generate playlist B →
   fail on disliked `(artist, track)` reappearance, avoid-trait leakage,
   completion < 95 %.
5. **Hard completion gate.** Treat under-fill < 95 % of `playlist_size`
   as failure, not `under_filled` non-error status.
6. **Stateful profile eval.** Run against an anonymized copy of the
   production debug profile (large/aged), not just clean-room sandbox.
7. **Full per-stage trace snapshot per eval run.** Stage 1 candidates +
   reject reasons, Stage 2 in/out, Stage 3 raw + normalized output,
   Spotify verify results, profile diff before/after refine, dislike
   store diff.

### 🟡 P2 — Phase B+ enrichment (after Phase A validates)

8. **Phase B — Last.fm enrichment** ([rag_enrichment_plan.md §B](documentation/rag_enrichment_plan.md)).
   Biggest single quality lever; replaces dropped Spotify popularity +
   adds weighted tags + `getSimilar` graph. Gate behind `LASTFM_API_KEY`.
9. **Phase D — Wikidata structured facts** ([rag_enrichment_plan.md §D](documentation/rag_enrichment_plan.md)).
   Highest-value next layer because it directly fixes the F1 must-have
   gate failure for "Japanese music" / "American artists" documented in
   [corpus_analysis.md](corpus_analysis.md). Order C↔D is flexible —
   take D first if eval scenarios remain country-constrained.
10. **Phase C — Discogs styles** ([rag_enrichment_plan.md §C](documentation/rag_enrichment_plan.md)).
    Broadens tag vocab where MB is sparse (electronic, hip-hop, niche).

### 🟢 P3 — Should-fix (independent of enrichment)

From [TODO.md](TODO.md):

11. **S11 — `swap_profile_with_history` crash safety.** Three sequential
    renames; orphan `*.swap.tmp` recovery on startup.
12. **S4 — i18n sweep on backend errors** surfacing in UI
    (`playlist.py:840`, `openai_http.py`, `suggestions.py`,
    `analysis.py`). Use structured-error keys.
13. **S10 — i18n on hardcoded ARIA labels with interpolated artist/track
    names** (`generate_section.html:305-306`).
14. **S8/S9 — Test coverage gaps** for local-LLM auto-downgrade and
    `validate_profile_schema`/`import_profile_dict`.
15. **S1/S2 — Frontend flake fixes** (`ragUpdateTip` pointer-blocking;
    `test_toggle_opens_and_closes_editor` animation timing).

### 🐛 Found bugs

16. **Playback stuck after track removal** — removed track keeps playing,
    blocks others. Likely related to CF-Bug-6 in [result-improvement.md](result-improvement.md).
17. **Settings Save needs busy state.** Slow save without UI feedback
    causes repeat-click. CF-Bug-7.

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
