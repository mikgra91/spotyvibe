# RAG corpus enrichment plan — multi-source

Status: draft 2026-05-02. Author: research handoff from `claude` session.

Goal: replace the broken Spotify enrichment with a layered, fault-tolerant
multi-source pipeline that strictly improves Stage 1 retrieval quality.

## Context

- Current pipeline: `refresh_rag_corpus.py` → `build_rag_corpus.py` (MB only)
  → `enrich_with_spotify.py` (genres + popularity + followers).
- Spotify Web API February 2026 broke the enrichment:
  - `GET /artists` (batch 50) **removed** → `client.get_artists()` fails today
  - `popularity` and `followers` **removed from artist objects** → stored as
    null/0 even when batch is replaced with single GET
  - `genres` still returned on `GET /artists/{id}` — the only field worth
    keeping from Spotify
- Enrichment data consumed at runtime by [retrieval.py](../core/src/rag/retrieval.py):
  - `spotify_genres` → tag index (high signal)
  - `spotify_popularity` → ranking penalty + 0.3-0.7 boost (high signal,
    now broken)
  - `spotify_followers` → unused
  - `spotify_id` → unused at runtime; useful for future top-tracks overlay

## Phase A — fix the existing enrichment (smallest viable change)

Rewrite [enrich_with_spotify.py](../build-tools/enrich_with_spotify.py) to
the post-Feb-2026 surface so the next Cloud Run rebuild does not regress.

1. `client.get_artists()` — replace batch with sequential
   `GET /artists/{id}`. Throughput drops 50× (50 IDs/req → 1) but the
   enrichment slice is `--max-enrich 50000` so total wall-clock at the
   210ms throttle is ≈3h, still inside the Cloud Run 24h budget.
2. Drop `spotify_popularity` and `spotify_followers` from the
   `SpotifyArtist` dataclass and from the JSONL output. Keep
   `spotify_id` and `spotify_genres`.
3. Drop the `spotify_popularity` branch from
   [_artist_popularity()](../core/src/rag/retrieval.py#L402-L410). Fall
   back to either:
   - the MB proxy `listener_popularity` (legacy, low quality), OR
   - **(preferred)** Last.fm playcount/listeners injected by Phase B.

## Phase B — Last.fm enrichment (highest single quality lever)

Last.fm is the cleanest replacement: free, no rate-limit cliff, MBID-keyed.

New file: `build-tools/lastfm_enrichment/client.py` mirroring the
shape of `spotify_enrichment/client.py` (single-process, exp backoff,
abort on cumulative budget).

Endpoints:
- `artist.getInfo` (mbid lookup) → `playcount`, `listeners`, `tags[]`,
  bio summary
- `artist.getTopTags` → 100 weighted tags 0-100 (much richer than MB
  community tags)
- `artist.getSimilar` → top-10 similar MBIDs with match scores

New `ArtistRow` fields (additive — backward compatible):
```python
lastfm_listeners: int | None = None
lastfm_playcount: int | None = None
lastfm_tags: list[tuple[str, int]] = []   # (tag, weight 0-100)
lastfm_similar_mbids: list[str] = []      # for the similarity facet
```

Index integration in [corpus.py:99-130](../core/src/rag/corpus.py#L99-L130):
- Index `lastfm_tags` alongside `spotify_genres` and MB tags
- Honour the per-tag weight (already supported by the index — pass the
  Last.fm 0-100 directly)

Index integration in [retrieval.py](../core/src/rag/retrieval.py):
- `_artist_popularity()` reads `lastfm_listeners` (log-scaled to 0-1)
  before falling back to MB proxy
- Optional new facet `similar_to_reference` (ListenBrainz-style) using
  `lastfm_similar_mbids` to seed retrieval from the user's primary
  reference artist — closes the gap left by removed Spotify
  `related-artists`

Cloud Run env vars (additive):
```
LASTFM_API_KEY              # required to enable Phase B
DISABLE_LASTFM_ENRICHMENT=1 # force-skip
LASTFM_MAX_ENRICH=170000    # all of MB by default; Last.fm has no
                            # 50k temp-ban risk like Spotify
```

## Phase C — Discogs styles (offline dump, complementary breadth)

Discogs CC0 monthly XML dump (`data.discogs.com/data/2026/`). Adds
genres + styles for artists where MB tags are sparse (especially
electronic, hip-hop, niche scenes).

New script: `build-tools/discogs_enrichment/build_index.py` — one-off
per Cloud Run invocation, reads
`discogs_<YYYYMMDD>_artists.xml.gz`, joins on MBID via the `urls/url`
elements that link out to MusicBrainz.

New fields:
```python
discogs_genres: list[str] = []
discogs_styles: list[str] = []
```

Index alongside other tags in [corpus.py:_build_indices](../core/src/rag/corpus.py#L99).

Cloud Run env vars:
```
DISCOGS_DUMP_URL            # explicit URL of the monthly dump to use
                            # (we pick one once a month, manifest-pin it)
DISABLE_DISCOGS_ENRICHMENT=1
```

## Phase D — Wikidata structured facts (must_have_tags coverage)

Solves the F1 must-have gate gap: today
[_resolve_must_have_tags()](../core/src/rag/retrieval.py#L687-L737)
silently under-filters when the user writes "Japanese music" or
"American artists" because MB tags rarely carry country/language.

Wikidata SPARQL via `query.wikidata.org/sparql`. One offline query
per build extracts for each artist MBID (P434):
- Country of origin (P495 / P27) → ISO code
- Language(s) of works (P407)
- Genres (P136) — Wikidata genres are well-curated
- Era / start year (P571 / P2031)

New fields:
```python
country_iso: str | None = None
languages: list[str] = []   # ISO 639-1 codes
wikidata_genres: list[str] = []
```

Update [build_query_tags()](../core/src/rag/retrieval.py#L220) and the
must-have resolver to recognise canonical synonyms:
- `japanese` / `j-pop` / `japan` → match artists with `country_iso=JP` OR
  `languages contains ja`
- `american` → `country_iso in {US, CA}` (configurable)

This is the only phase that requires a small **schema-aware**
match step rather than a literal tag intersection — mark the
plan-implementation milestone explicitly.

## Phase E — ListenBrainz similarity dataset (later, optional)

ListenBrainz publishes a Similarity dataset (artist-artist scored
edges, MBID-keyed, Parquet). Use case: replace the per-artist
`lastfm_similar_mbids` (which is a 10-deep list) with a denser, more
recent graph.

Defer until Phase B is shipped and we have data on whether
similar-artist seeding measurably helps Stage 1.

## Cloud Run integration

[cloud_run_publish.py](../build-tools/cloud_run_publish.py) currently
runs **two** sequential steps:

```
build_rag_corpus.py  →  enrich_with_spotify.py  →  upload
```

Proposed pipeline (each step optional, env-flag gated, halt-flag aware):

```
build_rag_corpus.py
  ↓ artists.jsonl.gz  (MB-only)
enrich_with_spotify.py             [SPOTIFY_CLIENT_ID/SECRET]
  ↓ adds spotify_id + spotify_genres
enrich_with_lastfm.py              [LASTFM_API_KEY]              ← Phase B
  ↓ adds lastfm_*
enrich_with_discogs.py             [DISCOGS_DUMP_URL]            ← Phase C
  ↓ adds discogs_*
enrich_with_wikidata.py            [WIKIDATA_USER_AGENT]         ← Phase D
  ↓ adds country_iso, languages, wikidata_genres
                                                                                                              
upload  →  gs://$GCS_BUCKET/artists.jsonl.gz + manifest.json
```

### Reuse the circuit-breaker pattern

Each enrichment step gets its own rate-limit exit code (Spotify=42 today;
Last.fm=43, Discogs=44 reserved). The
[_run_allow_exit_codes()](../build-tools/cloud_run_publish.py#L73-L79)
helper already takes a set — extend it once and add per-source halt
flags (`halt.lastfm.flag`, `halt.discogs.flag`) so a Last.fm temp-ban
does not freeze Spotify and vice versa.

### Manifest changes

Add a `sources` block so clients can detect which enrichment layers
made it into the published corpus:

```json
{
  "corpus_version": "2026-05-09",
  "sources": {
    "musicbrainz_dump": "20260418-001002",
    "spotify_enrichment": {"enriched": 47823, "fields": ["spotify_id","spotify_genres"]},
    "lastfm_enrichment":  {"enriched": 168112, "fields": ["lastfm_listeners","lastfm_playcount","lastfm_tags"]},
    "discogs_enrichment": {"enriched": 91204,  "fields": ["discogs_genres","discogs_styles"]},
    "wikidata_enrichment": {"enriched": 102331, "fields": ["country_iso","languages","wikidata_genres"]}
  }
}
```

Used by the runtime to log "missing layer" warnings and by the eval
harness to detect leakage between corpus refreshes.

### Build-time cost

Per refresh (rough estimates, MB corpus ~170k artists):

| Phase | Wall clock | Notes |
|---|---|---|
| A: Spotify (single-GET) | ~3 h    | for the top-50k slice; same as today |
| B: Last.fm              | ~6 h    | 3 endpoints × 170k × ~150ms throttle |
| C: Discogs (offline)    | ~15 min | XML stream + MBID join |
| D: Wikidata SPARQL      | ~30 min | batched 100 artists/query |
| **Total**               | **~10 h** | within the 24h Cloud Run Job ceiling |

If wall clock becomes a concern: B and C can run in parallel inside
the same job (different processes, different rate-limit pools).

## Migration & rollout

1. Land Phase A (Spotify fix) standalone — ships a working enrichment
   on the next scheduled rebuild. PR-sized.
2. Land Phase B (Last.fm) — biggest quality win; gate behind
   `LASTFM_API_KEY` so the build stays green even before the secret is
   provisioned in Cloud Run.
3. Bake an evaluation pass between Phases B and C: rerun the leakage
   gate + scenario evals to confirm Phase B is a net positive before
   layering more sources. Roll back Phase B if recall drops.
4. Land Phase C (Discogs) and Phase D (Wikidata) in either order — they
   write disjoint fields and don't depend on each other.
5. Defer Phase E (ListenBrainz similarity) until there's evidence the
   Last.fm similar list is the bottleneck.

## Risks

- **Last.fm tag noise** — community tags include junk (`my favourite`,
  `seen live`). Filter at enrichment time using a min-weight cutoff
  (e.g. weight ≥ 30) and the existing
  [_STOP_TOKENS](../core/src/rag/retrieval.py#L67) list.
- **Wikidata coverage** — not every MBID has a Wikidata sitelink; the
  must_have_tags gate must still pass when `country_iso is None`
  (treat missing as "unknown", not "no").
- **Schema bloat** — JSONL line size grows ~3-4× after all phases.
  Worth re-checking the Cloud Run upload size and the runtime memory
  footprint of `RagCorpus.load()` once each phase lands.
- **Spotify enrichment may not be worth keeping** — if Phase B's
  Last.fm tags subsume `spotify_genres`, drop Phase A entirely on the
  next iteration. Decide after a side-by-side eval.

## Out of scope

- Audio-features replacement for AcousticBrainz (shut down 2022).
  Possible future direction: Essentia self-hosted on a slice of top-N
  artists. Not in this plan.
- Spotify `/recommendations` and `/related-artists` (both removed/broken
  in 2024-2026). Phase B's Last.fm `getSimilar` is the equivalent.
- Real-time enrichment at suggestion time. All enrichment stays at
  build time so the runtime stays cache-friendly and offline-capable.
