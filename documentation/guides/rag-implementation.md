---
title: RAG service implementation plan
subtitle: A concrete plan for adding a retrieval-augmented candidate pool to SpotyVibe's suggestion pipeline, derived from llamacpp_setup.en.md Parts 8–9.
---

> **Scope.** This is a design plan, not a change log. It describes how to add a local artist-corpus retrieval service that injects a ranked candidate pool into the LLM prompt. Goal: replace *recall* (hard for 7B–14B models, biased on GPT-5-mini) with *ranking* (easy for any model). Applies to every provider — Ollama, LM Studio, llama.cpp, OpenAI, Groq, OpenRouter.
>
> **Prerequisite reading:** [llamacpp_setup.en.md](llamacpp_setup.en.md) Parts 8 and 9 — the motivation and cost analysis this plan is built on.

---

## 1. Goal and non-goals

**Goal.** Before each suggestion batch, retrieve ~20 artists from a local corpus that best match the user's profile + primary reference, and inject them as a "candidate pool — prefer these, but you may name others if clearly better" block in the system prompt.

**Non-goals (out of scope for v1).**

- Track-level retrieval (v1 is artist-level only — tracks are still the model's job; Spotify search validates them).
- Embeddings / vector DB. v1 uses sparse (TF-IDF / BM25) + tag matching. See §7 for why.
- Self-critique pass. Separate experiment per Part 9.
- Replacing the LLM. Model still generates; RAG only *steers*.

**Success criteria.**

1. Hallucinated-artist rate on 8B local models drops ≥ 30% in a manual A/B test (10 playlists each).
2. Popularity bias on `gpt-5.4-mini` drops — measured by median artist listener count on Spotify going down, not up.
3. Latency overhead per batch: ≤ 150 ms on a cold cache, ≤ 20 ms warm.
4. Extra LLM tokens per batch: ≤ 250 input tokens (thin-RAG profile from Part 9).
5. Works offline (no internet required once corpus is built).

---

## 2. Data source — MusicBrainz

**Why MusicBrainz.** Open, licensed CC0, has artist-level tags (genres, moods, eras), updated continuously, downloadable as a nightly PostgreSQL dump or JSON exports. No API rate limits if we ship a local snapshot.

**What we need per artist.**

| Field | Source | Used for |
|---|---|---|
| `mbid` (UUID) | MusicBrainz | Stable primary key |
| `name` | MusicBrainz `artist.name` | Prompt injection + Spotify search |
| `sort_name` | MusicBrainz `artist.sort_name` | Disambiguation |
| `country` | MusicBrainz `artist.country` | Geographic diversity signal |
| `begin_year`, `end_year` | MusicBrainz `artist.begin_date_year` | Era matching |
| `tags` (list of strings) | MusicBrainz `artist_tag` joined on tag id | Genre / mood matching — the main retrieval signal |
| `tag_weights` (list of ints) | MusicBrainz `artist_tag.count` | Tag relevance ranking |
| `listener_popularity` (int 0–100) | Derived — see §2.3 | Anti-popularity-bias re-ranking |

### 2.1 Corpus size

**Top-N cut.** Full MusicBrainz has ~2M artists. Most are noise (one-release local bands with no tags). We cut to the **top 100K** by number of releases + tag count. File size on disk after packing (see §3): ~8–12 MB gzipped. Acceptable for bundling with the repo or downloading once on first run.

Rationale: 100K covers every artist any SpotyVibe user is realistically going to encounter. Going to 500K triples the file size for artists no one searches for.

### 2.2 Build pipeline

A one-off script `build-tools/build_rag_corpus.py`:

1. Download MusicBrainz JSON dump (`mbdump.tar.bz2` from `data.metabrainz.org`).
2. Stream-parse artists, keep only those with ≥ 1 release and ≥ 1 tag.
3. For each kept artist, compute `listener_popularity` (§2.3).
4. Rank by popularity, take top 100K.
5. Emit `data/rag_corpus/artists.jsonl.gz` (newline-delimited JSON, one artist per line).

Script runs manually, not at build time — the corpus is a versioned data artifact, refreshed quarterly. Check the `.jsonl.gz` into a separate git-LFS path or a GitHub Release asset, not the main repo.

### 2.3 Popularity signal

MusicBrainz doesn't ship listener counts. Two options:

- **Option A — Use MusicBrainz's internal `release_group.rating` + `artist_tag.count` as a proxy.** Fully offline, good enough for relative ranking, imperfect absolute scale.
- **Option B — Enrich with Spotify `/v1/artists/{id}/followers` in a one-time crawl.** Best data, but requires a Spotify app token and a ~6-hour crawl respecting rate limits.

**v1 decision: Option A.** Ship offline-pure. Option B is a later optimisation if the popularity signal proves too noisy.

---

## 3. Storage format

**Artists:** `data/rag_corpus/artists.jsonl.gz` — one JSON object per line, gzipped. ~8–12 MB.

**Inverted index:** `data/rag_corpus/tag_index.json.gz` — `{tag_normalised: [artist_row_idx, ...]}`. Built once at server startup from the JSONL, cached in memory. ~2–4 MB on disk.

**In-memory structures (loaded once at app start):**

```python
# core/src/rag/corpus.py
class RagCorpus:
    artists: list[ArtistRow]                # ~100K rows, indexed by row_idx
    by_mbid: dict[str, int]                  # mbid → row_idx
    by_name_normalised: dict[str, int]       # "the beatles" → row_idx, for deny-list filtering
    tag_index: dict[str, list[int]]          # "post-punk" → [row_idx, ...]
    tag_vocab: dict[str, int]                # tag string → tag_id (for TF-IDF)
    tag_idf: np.ndarray                      # shape (n_tags,), log(N/df) per tag
```

Memory footprint: ~80 MB resident for 100K artists with ~10 tags each. Acceptable.

**Why not SQLite / DuckDB.** Tempting, but the read pattern is 100% full-scan-over-small-tag-set. An in-memory inverted index is simpler and faster. Revisit if the corpus grows past ~500K.

---

## 4. Retrieval algorithm (v1)

Given the user's `profile`, `primary_reference`, and a batch's `deny_list`:

### 4.1 Build the query

```python
query_tags = (
    profile.must_have_tags                           # genre, mood, era — structured
    + profile.soft_preferences                       # weighted lower
    + extract_tags(primary_reference.analysis)       # from analysis_prompt output
)
```

Tag extraction from free-text profile hints uses a simple keyword→tag lookup table (`data/rag_corpus/tag_aliases.json`, hand-curated, ~200 entries covering common synonyms like "electronic" → `electronica`, "hip hop" → `hip-hop`).

### 4.2 Score candidates

For each tag in `query_tags`, walk `tag_index[tag]`, accumulate a score per artist:

```
score(artist) = sum(tag_idf[t] * tag_weight[artist, t] * query_weight[t]
                    for t in query_tags if t in artist.tags)
```

This is textbook TF-IDF over artist-tag matrices. Fast because `query_tags` is tiny (5–15 tags) and each posting list is bounded.

### 4.3 Filter

Drop any artist whose normalised name appears in `deny_list` or `artists.confirmed` (the anchors — we don't want to suggest an artist the user already listens to).

### 4.4 Re-rank for anti-popularity-bias

Re-rank the top 100 by TF-IDF score with a popularity penalty:

```
final_score = tf_idf_score * (1 - 0.4 * popularity_normalised)
```

The 0.4 coefficient is a starting knob. If results lean too obscure, lower it; too popular, raise it. Expose as `config.py: RAG_POPULARITY_PENALTY = 0.4` so it's tunable without a code change.

### 4.5 Return

Top **20** artists after re-rank. Always 20, even if some are weak matches — the LLM still has the option to ignore them.

---

## 5. Prompt integration

### 5.1 New prompt fragment

Add to `prompts/system_prompt.txt` (or as a separate injected block to avoid breaking existing prompt caching):

```text
CANDIDATE_POOL (20 artists ranked by profile match, mid-popularity-weighted):
1. Artist A — tags: [post-punk, 1980s, UK]
2. Artist B — tags: [dream pop, shoegaze, US]
...

GUIDANCE:
- Prefer artists from CANDIDATE_POOL when a suggestion fits. You do not have to pick all 20.
- You MAY suggest artists outside the pool if you believe they match the profile strictly better. Do NOT invent artists.
- CANDIDATE_POOL does NOT override DENY_LIST or must_have/avoid constraints — those still win.
```

### 5.2 Token budget

20 artists × ~12 tokens per line (name + 2–3 tags) ≈ 240 input tokens. Within the Part 9 "thin RAG" budget.

### 5.3 KV-cache friendliness

Place the `CANDIDATE_POOL` block **after** the stable system prompt + profile but **before** the deny-list and feedback. Rationale: profile is stable across a single playlist run, so everything before the pool stays cached on llama.cpp's `--cache-reuse`. The pool itself changes per batch (deny-list grows, re-ranking shifts), so cache resets there and onward — which is already the case with the current deny-list.

---

## 6. Code surface

**New files:**

```
core/src/rag/
  __init__.py
  corpus.py              # RagCorpus class, load/persist
  retrieval.py           # score_artists(profile, deny_list) -> list[ArtistRow]
  prompt.py              # format_candidate_pool_block(artists) -> str
  tag_aliases.py         # load tag alias map
core/tests/
  test_rag_corpus.py
  test_rag_retrieval.py
  test_rag_prompt.py
build-tools/
  build_rag_corpus.py    # one-off corpus builder
data/rag_corpus/
  artists.jsonl.gz       # versioned artifact
  tag_aliases.json
```

**Modified files:**

- [core/src/suggestions.py](../../core/src/suggestions.py) — call `retrieval.score_artists(...)` before constructing the prompt; pass candidate block to prompt assembly.
- [core/src/openai_http.py](../../core/src/openai_http.py) — no change; the candidate block is just extra prompt text.
- [config.py](../../config.py) — add `RAG_ENABLED = True`, `RAG_CORPUS_PATH`, `RAG_POOL_SIZE = 20`, `RAG_POPULARITY_PENALTY = 0.4`.
- [app.py](../../app.py) — load `RagCorpus` once at startup (not per request); inject into the suggestions module.
- [frontend/static/js/modules/settings.js] + i18n files — expose a "Use candidate pool (RAG)" toggle in Settings → Advanced.

**Rough LOC estimate:** ~400 lines of new Python (corpus + retrieval + prompt + tests), ~20 lines of config glue, ~30 lines of frontend toggle + i18n. Plus the one-off ~150-line corpus builder.

---

## 7. Why not embeddings / vector DB in v1?

A fair question, since semantic search with a small embedding model (e.g. `all-MiniLM-L6-v2`, ~90 MB) would be more semantically flexible than tag-TF-IDF.

**Reasons to defer:**

1. **Offline-first discipline.** Tag TF-IDF has zero runtime ML dependencies; embedding retrieval pulls in `sentence-transformers` or ONNX Runtime.
2. **Tag data is already structured.** MusicBrainz tags are human-curated — we'd be running embeddings over text that's *already* categorised. Diminishing returns.
3. **Workload is short-tail filtering, not fuzzy similarity.** The profile already names specific genres/moods. Tag matching is a strong signal.
4. **Ease of iteration.** TF-IDF scores are debuggable by reading the query; embedding scores are opaque.

If v1 retrieval proves insufficient — specifically if the main failure mode is "profile says 'cinematic synthwave' and no artist has that exact tag" — swap in embeddings then. Design the `retrieval.py` interface so it's replaceable: one function `score_artists(profile, deny_list) -> list[ArtistRow]`.

---

## 8. Rollout plan

1. **Spike (half day).** Prototype corpus builder against a 10K-artist MusicBrainz subset. Confirm score quality on 5 hand-crafted profiles. No UI, no integration — just print top-20 to stdout.
2. **Corpus build (half day).** Full 100K build, ship the `.jsonl.gz` as a GitHub Release asset. Add a one-time download step in `app.py` startup (check for file presence, download if missing).
3. **Integration (1 day).** Wire retrieval into `suggestions.py` behind a feature flag `RAG_ENABLED` defaulting to `False`. No prompt change yet — just populate candidate pool, log it.
4. **Prompt + UI toggle (half day).** Add the `CANDIDATE_POOL` block to the prompt assembly. Expose toggle in Settings.
5. **A/B measurement (1 day).** Generate 10 playlists with RAG off, 10 with RAG on, same profile. Measure: hallucination rate (tracks that don't resolve on Spotify), artist novelty, median popularity. Report back.
6. **Decision.** Ship behind `RAG_ENABLED = True` default if metrics improve; keep flag for opt-out.

Total: ~3–4 focused days.

---

## 9. Testing strategy

**Unit tests (fast, no corpus):**

- `test_rag_corpus.py` — load a 10-artist fixture, assert indices populate.
- `test_rag_retrieval.py` — hand-crafted fixtures, assert scoring formula and deny-list filtering.
- `test_rag_prompt.py` — candidate-pool formatting, token-count bound.

**Integration tests (slow, skipped in CI unless flagged):**

- Load the real 100K corpus, run retrieval against 5 golden profiles, assert the top result matches a snapshot. Snapshot refreshed on corpus rebuilds.

**Not tested:**

- End-to-end LLM quality. That's the manual A/B from the rollout plan — automated metrics are too noisy at playlist size.

Mock all external APIs as usual per CLAUDE.md rule #4. The corpus file is a local fixture, not an API.

---

## 10. Open questions — defer until spike

1. **Track-level retrieval, later.** Is artist-level sufficient, or do we need track-level candidates too? Wait for v1 metrics.
2. **Profile schema evolution.** Current `profile.must_have` is loosely typed text. Should we tighten it to structured tags to improve retrieval? Probably yes, eventually — but not a blocker for v1; the tag alias map absorbs most of the looseness.
3. **Multilingual tag matching.** MusicBrainz tags are mostly English. A German/Japanese profile's tag aliases should map to English tags for retrieval. Tag alias map extension is additive; no architectural change.

---

## Appendix — Sources and cross-references

- [llamacpp_setup.en.md Part 8](llamacpp_setup.en.md) — motivation for RAG as the highest-ROI local-model intervention.
- [llamacpp_setup.en.md Part 9](llamacpp_setup.en.md) — motivation for applying the same retrieval to cloud providers; cost modelling.
- [MusicBrainz Database](https://musicbrainz.org/doc/MusicBrainz_Database) — schema reference.
- [MusicBrainz Data Download](https://data.metabrainz.org/) — nightly dumps.
- [Music Recommendation with LLMs (arXiv:2511.16478)](https://arxiv.org/html/2511.16478) — empirical support for retrieval mitigating popularity bias.

---

## 11. Implementation status (2026-04-19) — **v1 landed**

The code side of the plan is in place. What changed vs. the plan:

### Shipped

- **`core/src/rag/` package** — `corpus.py`, `retrieval.py`, `prompt.py`, `__init__.py`. Pure-Python TF-IDF with a smoothed IDF (``log((N+1)/(df+1)) + 1``); no numpy dependency.
- **Alias map** — `data/rag_corpus/tag_aliases.json` seeded with ~180 entries (covers major genre/mood/era synonyms — electronic/hip-hop/trip-hop/synthwave/city-pop/k-pop/etc.).
- **Query extraction** — bigram + hyphenated compound tokens get a ×3 boost over unigrams (a fix discovered during testing — "dream pop" is far more diagnostic than "pop").
- **Config** — `RAG_ENABLED` persisted in `settings.conf`; `RAG_CORPUS_PATH`, `RAG_POOL_SIZE`, `RAG_POPULARITY_PENALTY` are constants in [config.py](../../config.py). The flag is gated on corpus file presence — a missing corpus is silently a no-op.
- **Startup wiring** — [app.py](../../app.py) calls `_load_rag_corpus_if_enabled()` before the Flask app is built. The corpus handle is swapped hot when the user toggles the setting; no restart needed.
- **Prompt integration** — [core/src/suggestions.py](../../core/src/suggestions.py) appends the `CANDIDATE_POOL` block to the user message when a corpus is loaded. Deny keys feed both `forbidden_artists` and the user's `artists.confirmed` anchors into the retriever.
- **Frontend** — toggle in `frontend/templates/modals/settings_modal.html`, wired through `frontend/static/js/modules/modals.js`, with en/de/jp i18n keys. Disabled and labelled "Corpus file not installed" when the `.jsonl.gz` is absent.
- **Builder** — `build-tools/build_rag_corpus.py`. Accepts either a MusicBrainz JSON dump directory or a pre-flattened JSONL file; writes gzipped JSONL with a 0..1 popularity score derived from release count + tag total (§2.3 Option A).
- **Tests** — `core/tests/test_rag_{corpus,retrieval,prompt}.py`, 16 tests total, gzipped fixture artists. Full suite (490 tests) green.

### How to build and use the corpus

```bash
# 1. Download the MusicBrainz JSON dump (once, ~3 GB compressed).
#    Browse to https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/
#    and open the most recent dated folder (e.g. 20260418-001002/).
#    The top-level index only lists dump *dates* — the per-entity
#    tarballs live one level down. Download these two:
#      - artist.tar.xz          (~2 GB, required)
#      - release-group.tar.xz   (~1 GB, recommended — gates the ≥1-
#                                release filter and feeds popularity)
#    You do NOT need area / event / instrument / label / place /
#    recording / release / series / work, nor the MD5SUMS/SHA256SUMS
#    signature files.
# 2. Extract both tarballs into the same directory, e.g.
#      mkdir -p /tmp/mb && cd /tmp/mb
#      tar -xf /path/to/artist.tar.xz
#      tar -xf /path/to/release-group.tar.xz
#    They both produce an `mbdump/` subfolder containing `artist` and
#    `release-group` (newline-delimited JSON). Tags are embedded inline
#    inside each artist record — no separate tag file is needed.
# 3. Run the builder (point --source at the parent directory or at
#    mbdump/ directly; the script accepts either):
python build-tools/build_rag_corpus.py \
       --source /tmp/mb/ \
       --output data/rag_corpus/artists.jsonl.gz \
       --top-n 100000
# 4. Enable the toggle in Settings → "Candidate pool (RAG)".
```

For a quick manual test, feed it a small JSONL you wrote by hand (same schema as the fixtures in `test_rag_corpus.py`) — the builder will accept that too.

### Corpus hosting & auto-update (v1.1 — 2026-04-19)

The corpus ships as a GitHub Release asset on a rolling
`rag-corpus-latest` tag at this repo. The release holds two assets:

- `artists.jsonl.gz` — the corpus itself.
- `manifest.json` — `{corpus_version, built_at, sha256, size_bytes, corpus_url}`.

**Client flow** — [core/src/rag/distribution.py](../../core/src/rag/distribution.py) is called once at startup from [app.py](../../app.py#L132) (`_check_rag_corpus_update`). It fetches the manifest with a 5-second timeout (best-effort; offline boots are fine) and compares it to the sidecar `data/rag_corpus/artists.meta.json`. The result is exposed via `/api/settings` as `rag_update` and rendered as a banner in the Settings modal (see `renderRagUpdateBanner` in [frontend/static/js/modules/modals.js](../../frontend/static/js/modules/modals.js)). Clicking **Download now** POSTs to `/api/rag/download-corpus`, which streams into `artists.jsonl.gz.part`, sha256-verifies, atomically renames, and hot-swaps the in-memory corpus.

**Publisher flow** — after `build_rag_corpus.py` produces a fresh corpus:

```bash
python build-tools/publish_rag_corpus.py            # uses mtime as version
# or pin a version explicitly:
python build-tools/publish_rag_corpus.py --version 2026-04-19
```

The publisher script uses `gh release upload --clobber` to replace both assets in place, so existing clients pick up the update on their next startup.

### Open tasks / v1.1 follow-ups

~~1. **Corpus distribution**~~ — done (2026-04-19). Hosted on GitHub Releases via `build-tools/publish_rag_corpus.py`.
~~2. **Update-available notification**~~ — done (2026-04-19). Manifest + startup check + Settings banner + sha256-verified download.
3. ~~**Option B popularity enrichment**~~ — **dropped (2026-04-19).** 100K-artist Spotify crawl deemed too expensive to maintain; sticking with Option A (release-count + tag-total proxy). Known bias: 300-year-old composers rank at pop=1.0. Acceptable trade-off since suggestions are guided by tag matches, not popularity alone.
4. **A/B measurement (§8 step 5)** — run 10 playlists with / without RAG on the same profile, measure hallucination rate + median popularity. No code change; needs an afternoon of manual testing.
5. **Default-on** — once §11.4 shows improvement, flip `DEFAULT_RAG_ENABLED` in [config.py](../../config.py) to `True` (keep the opt-out toggle).
6. **Multilingual tag matching** — the alias map is English-centric. Extending to German/Japanese genre vocab is additive (just append to `tag_aliases.json`).
7. **v2 — embedding-based retrieval** — only if the main failure mode turns out to be "profile mentions a specific vibe no one has tagged". `retrieval.score_artists()` is the replacement seam.

### Decision points deferred to real-data measurement

- **`RAG_POPULARITY_PENALTY = 0.4`** — placeholder. Tune after A/B.
- **`RAG_POOL_SIZE = 20`** — placeholder. If hallucinations still happen, try 40; if the prompt feels too directive, try 10.
- **`_COMPOUND_BOOST = 3.0`** in `retrieval.py` — found empirically while fixing a test; may need to come down once the corpus is real and `pop`/`rnb` are properly weighted by IDF.

