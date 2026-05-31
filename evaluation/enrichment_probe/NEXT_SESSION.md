# AI enrichment — session handoff / runbook

> **Continue-from state. Last updated: 2026-05-30 (evening).**
> Two jobs ran to completion this session; nothing is committed (working
> tree only). Tomorrow: run the **next ~50k batch**, then assess data quality.

## Where we are

| Artifact | State |
|---|---|
| `ai_tags_overlay.json` | **176,564 artists — FULL CORPUS, 100% coverage** · model `gpt-4o-mini` · vocab **v3** (364 terms) |
| Enrichment | ✅ COMPLETE (2026-05-31) · 0 errors · 1.7% empty |
| Spend | ~**€25** total |
| Cloud Run merge/update | **Deployed + published**: corpus version `2026-05-30`, 176,560 rows, incremental seeding worked (146,493 carried / ~30,067 fetched), 0 failures |

### Quality at full corpus (final)

- Production metric (global IDF, `union_disc`): **MAP 0.887 · margin +0.331 · NN 3/3** (baseline corpus = 0.844).
- Connectivity: **100%** have neighbour ≥0.30 · **mean top-1 sim 0.933** · top-5 0.904.
- Scaling trend (mean top-1 sim): 2k 0.772 → 5k 0.795 → 10k 0.834 → 45k 0.886 → 80k 0.915 → **176k 0.933** (monotonic to the end — full coverage gave the tightest clusters).

### Model decision (settled)
gpt-4o-mini chosen over gpt-5.4-mini. Probe (`compare_models.py` /
`compare_quality.py`, artifact `compare_gpt-5.4-mini_results.json`):
gpt-5.4-mini was 6.3× cost for a within-noise edge (MAP 0.896 vs 0.843 on
31-artist disc set; both NN 3/3; `reasoning_tok=0`). Full corpus only
affordable on gpt-4o-mini (~€25 vs €158). **Do not revisit unless quality
regresses.**

## Enrichment — ✅ COMPLETE (full corpus, 176,564 artists)

Done as of 2026-05-31. To **re-enrich after a corpus refresh** (skip-gate
re-does only changed artists), or to enrich a future vocab bump, use
`--sample 400000` (the tail-heavy corpus needs n≥~400k for full coverage;
smaller n silently caps the tail — head 9,937 / mid 48,332 / tail 118,291).

```bash
PYTHONIOENCODING=utf-8 python evaluation/enrichment_probe/enrich_ai_layer.py \
    --sample 400000 --workers 8
```

**THE BIG NEXT STEP — wire + release (see item 1 in "Still open").**

Safe to launch in the background: atomic writes, checkpoints every 100,
idempotent skip-gate (a crash/stop just resumes; re-running skips done).

## TOMORROW — step 2: assess "is the data good?"

```bash
PYTHONIOENCODING=utf-8 python evaluation/enrichment_probe/production_metric.py
PYTHONIOENCODING=utf-8 python evaluation/enrichment_probe/cluster_connectivity.py
PYTHONIOENCODING=utf-8 python evaluation/enrichment_probe/verify_overlay.py
```

**Good outcome looks like:** errors ≈ 0 · empty ≈ 1% · `union_disc` MAP
holds ~0.87-0.88 (3-seed ceiling) and margin ≥ +0.33 · **connectivity
mean top-1 sim ≥ 0.886** (should hold or keep rising — a drop would be the
red flag) · OOV ~11%.

## Still open (not started)
1. **Retrieval wiring + release** — the real app fix (code-grounded plan,
   from reading `corpus.py` + `retrieval.py` 2026-05-31). Today retrieval
   scores via `corpus.tag_index`, built in `_build_indices` from MB tags +
   Spotify genres + Last.fm tags ONLY; `ArtistRow` has no `ai_tags` and
   `_artist_tag_weight` never reads them — so the overlay is **inert in the
   live path**. To wire it:
   1. `RagCorpus.load()` — auto-merge `ai_tags_overlay.json` sibling (same
      pattern as `top_tracks_overlay.json`) → new `ArtistRow.ai_tags`.
   2. `_build_indices` — index **only DISCRIMINATIVE** AI tags
      (genre/scene/vocal) into `tag_index` + `tag_idf`. **Exclude** generic
      mood/rhythm/era/instrumentation AI tags (FINDINGS: they dilute
      precision + bloat posting lists). Needs a shipped generic-exclusion
      constant in core (copy from `vocabulary.py` GENERIC categories).
   3. `_artist_tag_weight` — add an `ai_tags` branch (constant weight).
   4. (bigger, optional) seed-artist neighbourhood expansion via the
      `primary_reference` facet — the deeper "similar to band X is ignored"
      fix.
   **GATE: this changes the score of every artist → must pass
   `evaluation/run_evaluation.py` across cloud + local models with NO
   regression BEFORE releasing.** Release = upload `ai_tags_overlay.json`
   to the GCS bucket next to `artists.jsonl.gz` (survives Cloud Run
   rebuilds) + ensure the client download flow fetches/merges it. Do NOT
   release until the eval is green.
2. **Taste dashboard ("Your taste at a glance") bugs** — ✅ FIXED 2026-05-31.
   Root cause: `aggregate_taste()` read only run history (0 runs) and the
   "genres" were a profile must_have/soft_preferences fallback (vibe phrases).
   Fixes:
   - `core/src/taste.py`: now merges `profile["feedback"]` liked/disliked
     (authoritative sentiment) so feedback shows with 0 runs; removed the
     misleading profile-pref genre fallback. Tests in `core/tests/test_taste.py`
     (11 pass).
   - Frontend: added a **Top Artists** card (`taste_dashboard.html` ×3 grids,
     `taste_dashboard.js` `renderArtists` + visibility wiring, i18n
     `dashboard.card_artists` in en/de/jp) — the one dimension feedback data
     carries, so liked/disliked slices are now visible.
   - **Remaining follow-ups:** (a) feedback-only tracks still lack
     genres/energy/release_year, so those 3 charts stay empty for them —
     enrich feedback tracks via a lookup (RAG corpus by artist for genres is
     a natural tie-in); (b) docs: UserManual/help mention the dashboard —
     add the Top Artists chart + feedback note (rule 4).
3. Screenshot/docs refresh (62 changed PNGs; `test_20`, `test_62` selector
   breakages from real UI changes).
4. Nothing committed — merge module + tests, Cloud Run wiring, doc updates,
   enrichment/compare scripts all uncommitted.

## Key files
- Producer: `enrich_ai_layer.py` · Vocab: `vocabulary.py` (v3)
- Verifiers: `production_metric.py`, `cluster_connectivity.py`, `verify_overlay.py`
- Model A/B: `compare_models.py`, `compare_quality.py`
- Merge/update: `build-tools/rag/merge_corpus.py` + `core/tests/test_merge_corpus.py`
- Findings: `FINDINGS.md`
