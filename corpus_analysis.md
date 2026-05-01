# RAG Corpus Coverage Analysis

Analysis date: 2026-05-01  
Corpus inspected: `context/artists.enriched.jsonl`  
Diagnostic script: `evaluation/analyze_rag_corpus_coverage.py`

Generated reports:

- Text: `evaluation/results/rag_corpus_coverage.txt`
- JSON: `evaluation/results/rag_corpus_coverage.json`

## Executive summary

The corpus can mechanically return candidate pools of artists, but it does **not** currently contain enough reliable information to prove that the evaluation scenarios are semantically covered.

The corpus is numerically large:

- Artists: `173,476`
- Indexed tags: `47,511`
- Retrieval can return candidate pools of `20`, `50`, and `100` for both shipped evaluation scenarios.

However, `artists.enriched.jsonl` is not actually enriched in the way the production RAG code expects:

- Spotify-enriched artists: `0` / `173,476` (`0.0%`)
- Artists with Spotify genres: `0` (`0.0%`)
- Artists with country metadata: `0` (`0.0%`)
- Artists with top tracks: `0` (`0.0%`)

So the current corpus cannot reliably support:

- found-on-Spotify assumptions,
- Spotify genre matching,
- country / nationality constraints such as Japanese-only or no American artists,
- track-level grounding,
- popularity based on real Spotify popularity.

## Why this matters

The RAG corpus is used to suggest artists to the AI agent. It is also used by the evaluation harness. Therefore, the evaluation scenarios need to be covered by the corpus. If the corpus cannot represent a test's required traits, then failures may be caused by corpus coverage rather than model behaviour.

In short: before spending money on model evaluations, we need a cheap corpus preflight check that answers: "Can the corpus even provide a valid candidate pool for this scenario?"

## Corpus enrichment status

Despite the filename `artists.enriched.jsonl`, the rows currently only contain the legacy MusicBrainz-derived fields:

- `mbid`
- `name`
- `begin_year`
- `tags`
- `tag_weights`
- `listener_popularity`

There are no rows containing Spotify enrichment fields such as:

- `spotify_id`
- `spotify_popularity`
- `spotify_followers`
- `spotify_genres`
- `top_tracks`

This means retrieval falls back entirely to MusicBrainz tags and the `listener_popularity` proxy.

That is a major limitation because current retrieval code is designed to benefit from Spotify genres and Spotify popularity, but this corpus provides neither.

## Special term frequencies

The corpus does contain some relevant tags, but coverage is uneven:

| Term | Artist frequency |
|---|---:|
| `j-pop` | `1,310` |
| `j-rock` | `362` |
| `japanese` | `359` |
| `japan` | `315` |
| `anime` | `146` |
| `anime soundtrack` | `1` |
| `theatrical` | `4` |
| `cinematic` | `139` |
| `uplifting` | `52` |
| `harmonized vocals` | `0` |
| `american` | `752` |
| `80s` | `124` |
| `classic rock` | `463` |
| `edm` | `1,798` |
| `synthwave` | `992` |
| `electronic` | `9,517` |

The most important warning signs are:

- `theatrical` has only `4` artists.
- `harmonized vocals` has `0` artists.
- `uplifting` has only `52` artists.
- nationality constraints rely on tags, not structured country metadata.

## Default evaluation scenario coverage

Scenario: `default`  
Theme: broad theatrical pop-rock.

### Query coverage

- Raw query token coverage: `19/35` (`54.29%`)
- Mapped usable tokens after aliasing / production floor: `14`
- Mapped token artist frequency range:
  - min: `3`
  - median: `16.5`
  - max: `13,073`

### Reference artist

- Analysis reference artist: `Bear Ghost`
- Present in corpus: `True`

### Avoid coverage

- Avoid traits covered: `4/5`
- Fully covered: `False`

Resolved avoid tags include:

- `rock` (`13,073`)
- `lo-fi` (`4,712`)
- `indie` (`2,363`)
- `edm` (`1,798`)
- `synthwave` (`992`)
- `classic rock` (`463`)
- `guitar` (`287`)
- `arena rock` (`44`)
- `classic` (`21`)
- `vintage` (`18`)

The avoid trait `unmastered demos` does not resolve to useful corpus tags.

### Facet support

| Facet | Mapped tokens | Matching artist union | Notes |
|---|---:|---:|---|
| `must_have` | `3` | `30` | Very thin support: `guitars`, `quirky`, `theatrical` |
| `soft_preferences` | `12` | `22,630` | Dominated by broad `rock` / `pop` tags |
| `primary_reference` | `1` | `4` | Only `ghost` resolves |
| `tags` | `0` | `0` | No structured genre/mood tags in the scenario profile |

The must-have facet is the key weakness. It has only 30 unique artists, and the strongest relevant terms are rare.

### Candidate pool results

The retriever can fill requested pools:

| Target size | Broad pool before filters | Returned after filters |
|---:|---:|---:|
| `20` | `60` | `20` |
| `50` | `150` | `50` |
| `100` | `300` | `100` |

But semantic quality is mixed. For target `100`, marker counts after filters were:

| Marker group | Count in returned pool |
|---|---:|
| `theatrical_quirky` | `9` |
| `japanese_or_j_music` | `1` |
| `electronic_edm_synthwave` | `14` |
| `american` | `6` |
| `uplifting` | `1` |
| `classic_vintage_arena` | `0` |
| `80s` | `0` |

Even though the default scenario avoids EDM/synthwave, electronic markers still remain in the final pool. This suggests the RAG stage is not cleanly enforcing all avoid constraints.

### Default scenario conclusion

The default scenario is **partially covered**, but not robustly.

The pool fills numerically, but it relies heavily on broad fallback terms like `pop`, `rock`, and `pop rock`, while the important must-have terms have very small artist support.

## Japanese regression scenario coverage

Scenario: `regression_japanese_theatrical`  
Theme: uplifting Japanese theatrical music, no electronic/synthesizer excess, no 80s production style, no American artists.

### Query coverage

- Raw query token coverage: `18/55` (`32.73%`)
- Mapped usable tokens after aliasing / production floor: `15`
- Mapped token artist frequency range:
  - min: `3`
  - median: `139`
  - max: `13,073`

This is weak coverage for a regression test that is supposed to assert fairly specific taste constraints.

### Reference artist

- Analysis reference artist: `One Ok Rock`
- Present in corpus: `True`

### Avoid coverage

- Avoid traits covered: `5/5`
- Fully covered: `True`

Resolved avoid tags include:

- `electronic` (`9,517`)
- `american` (`752`)
- `music` (`348`)
- `electronic music` (`117`)
- `uplifting` (`52`)
- `songs` (`14`)
- `artists` (`5`)
- `synthesizers` (`5`)
- `american artists` (`1`)
- `style` (`1`)

This looks better numerically than it is semantically. Some resolved tags are noisy or overly broad:

- `music`
- `songs`
- `artists`
- `style`

Also, `Songs that are not uplifting` resolves to `uplifting`, which is dangerous: at artist-tag level, this does not actually mean the system can identify "not uplifting" songs.

### Facet support

| Facet | Mapped tokens | Matching artist union | Notes |
|---|---:|---:|---|
| `must_have` | `4` | `758` | `japanese`, `music`, `uplifting`, `no` |
| `soft_preferences` | `13` | `23,428` | Dominated by broad `rock`, `pop`, `pop rock` |
| `primary_reference` | `3` | `13,081` | Badly diluted by `rock`; `One Ok Rock` tokenizes poorly |
| `tags` | `0` | `0` | No structured genre/mood tags |

The primary reference is especially problematic. The placeholder analysis text `One Ok Rock Wherever you are` contributes broad tokens like `rock`, `you`, and `one`, rather than useful Japanese rock adjacency.

### Candidate pool results

The retriever can fill requested pools:

| Target size | Broad pool before filters | Returned after filters |
|---:|---:|---:|
| `20` | `60` | `20` |
| `50` | `150` | `50` |
| `100` | `300` | `100` |

But marker counts reveal poor semantic coverage.

For target `100`, returned pool marker counts were:

| Marker group | Count in returned pool |
|---|---:|
| `japanese_or_j_music` | `9` |
| `uplifting` | `0` |
| `theatrical_quirky` | `0` |
| `classic_vintage_arena` | `30` |
| `80s` | `1` |
| `electronic_edm_synthwave` | `1` |
| `american` | `0` |

This is not adequate for a test requiring uplifting Japanese theatrical music.

The top candidates start with Japanese artists, but the pool quickly drifts into generic Western pop/rock artists such as:

- The Beatles
- Queen
- Taylor Swift
- Coldplay
- Fleetwood Mac
- Miley Cyrus
- Avril Lavigne
- Paramore
- Imagine Dragons
- Red Hot Chili Peppers

This means the RAG pool can be filled numerically, but not with enough artists matching the hard Japanese/theatrical/uplifting constraints.

### Japanese scenario conclusion

The Japanese regression scenario is **not adequately covered** by the current corpus/retrieval combination.

The corpus has some Japanese and J-music tags, but the current retrieval pipeline does not reliably turn the profile prose into those exact tags, and it does not hard-filter Japanese-only constraints.

## Tokenization problem: J-pop / J-rock

The corpus contains useful tags:

- `j-pop`: `1,310`
- `j-rock`: `362`

But the current tokenizer splits phrases like `J-pop` and `J-rock` into broad terms:

- `pop`
- `rock`
- `pop rock`
- `pop-rock`

The `j` part is single-character and gets dropped. So the retriever often misses the exact high-value corpus tags `j-pop` and `j-rock`.

This is one reason the Japanese regression pool drifts into generic Western pop/rock.

## Constraints not represented well by artist-level tags

Some evaluation requirements are not reliably representable in the current corpus:

| Requirement | Corpus support |
|---|---|
| Japanese-only music | Partially via tags like `japanese`, `j-pop`, `j-rock`; no structured country field |
| No American artists | Only via `american` tag; no structured country field |
| Uplifting music | Weak; `uplifting` has only `52` artists |
| Theatrical music | Very weak; `theatrical` has only `4` artists |
| Harmonized vocals | Not present; `0` artists |
| No 80s production style | Weak; `80s` tag exists but does not mean production style |
| Songs that are not uplifting | Not enforceable from artist-level tags |
| Track-level factuality | Not supported; no `top_tracks` |

## Answer to the pool-size question

Can we provide a pool size of artists?

- **Mechanically yes.** The retriever can fill pools of 20, 50, and 100 for the evaluation scenarios.
- **Semantically no.** The current corpus does not provide enough reliable metadata to guarantee that those pools satisfy the scenario constraints.

Therefore, pool size alone is a misleading metric. We need pool quality / coverage checks before evaluation.

## Recommended next steps

1. Regenerate or repair the enrichment file.

   `artists.enriched.jsonl` should actually include:

   - `spotify_id`
   - `spotify_popularity`
   - `spotify_followers`
   - `spotify_genres`
   - `top_tracks`
   - ideally `country`

2. Add tokenizer aliases or normalization for Japanese genre terms.

   Recommended aliases:

   - `j pop` → `j-pop`
   - `j-pop` → `j-pop`
   - `jpop` → `j-pop`
   - `j rock` → `j-rock`
   - `j-rock` → `j-rock`
   - `jrock` → `j-rock`

3. Treat some profile requirements as hard filters, not soft scoring terms.

   Examples:

   - Japanese-only
   - no American artists
   - no electronic / EDM / synthwave
   - no 80s / vintage / classic-rock drift

4. Add a corpus preflight gate to evaluation.

   Before running paid model evaluations, use `evaluation/analyze_rag_corpus_coverage.py` or a stricter derivative to assert that the scenario has enough candidate support.

5. Reconsider the regression scenario until the corpus is upgraded.

   The current Japanese regression test asks for constraints that the current corpus cannot reliably represent. If the goal is to evaluate model behaviour, the corpus first needs enough grounded candidates that satisfy the scenario.

## Diagnostic commands

```shell
$env:PYTHONIOENCODING='utf-8'; python evaluation/analyze_rag_corpus_coverage.py --output evaluation/results/rag_corpus_coverage.txt
```

```shell
$env:PYTHONIOENCODING='utf-8'; python evaluation/analyze_rag_corpus_coverage.py --json --output evaluation/results/rag_corpus_coverage.json
```

```shell
python -m py_compile evaluation/analyze_rag_corpus_coverage.py
```

## Follow-up: realistic ways to bridge user language and MusicBrainz

User-facing music descriptors often do not match MusicBrainz tags directly. A good example is Bear Ghost: users may describe the style as `theatrical`, `musical`, or `Broadway-like`, while MusicBrainz describes the artist with tags such as `adventure rock`, `rock`, and `progressive rock`.

This is a fundamental vocabulary mismatch. It should not be solved by manually curating artists. Manual curation is not feasible for a small application, and if large public music databases cannot fully maintain this layer, it is unrealistic for this project to do so by hand.

The realistic goal is therefore:

> Use MusicBrainz as a factual identity and tag backbone, automatically derive better semantic bridges, and verify final artists/tracks against Spotify before the AI can output them.

This gives the best of both worlds:

1. MusicBrainz provides real artist identities, aliases, tags, and relationships.
2. Automated semantic expansion maps user language to corpus vocabulary.
3. Spotify verification prevents final hallucinated artists/tracks.
4. The LLM reasons over evidence-backed candidates instead of inventing candidates.

### What MusicBrainz can help with

MusicBrainz can help more than the current corpus uses today. The current corpus appears to rely mostly on artist-level tags, which are sparse and uneven.

#### 1. Roll up release-group, release, recording, and work tags to artists

MusicBrainz has tags on more entities than just artists:

- artists,
- release groups,
- releases,
- recordings,
- works.

The corpus builder should aggregate these into an artist semantic profile:

```text
artist tags
+ release-group tags
+ release tags
+ recording tags
+ work tags
→ artist semantic profile
```

Suggested weighting:

| Source | Suggested weight |
|---|---:|
| Artist tag | high |
| Release-group tag | medium/high |
| Release tag | medium |
| Recording tag | medium |
| Work tag | medium |
| One-off rare tag | low unless repeated |

This can improve coverage without manual curation. An artist may not be artist-tagged `theatrical`, but albums/tracks may carry related terms such as `rock opera`, `cabaret`, `progressive rock`, `art rock`, `musical`, `soundtrack`, or `comedy rock`.

#### 2. Use MusicBrainz area/country fields for nationality constraints

Constraints like `Music must be Japanese` or `No American artists` should not rely on tags like `japanese` or `american`. Those are incomplete and inconsistent.

The corpus should include structured MusicBrainz fields such as:

- `country`,
- `area`,
- `begin_area`,
- potentially artist area / life-span area data.

Then Japanese-only can become a hard filter over structured metadata, rather than a soft tag match.

#### 3. Use MusicBrainz aliases for artist matching

MusicBrainz aliases can improve:

- detecting reference artists in user text,
- resolving romanized vs native-script names,
- deduplicating candidates,
- matching MusicBrainz candidates to Spotify search results.

This is especially useful for Japanese artists and artists with alternate spellings.

#### 4. Use MusicBrainz relationships and external links as enrichment anchors

MusicBrainz can link artists to:

- Wikidata,
- Wikipedia,
- Discogs,
- official websites,
- Bandcamp,
- SoundCloud,
- YouTube,
- other external identifiers.

These can be used automatically, with MusicBrainz as the identity anchor. For example:

```text
MBID → Wikidata QID → country / genre / language
MBID → Wikipedia summary → short text document for semantic retrieval
MBID → external IDs → better Spotify matching
```

This is still not manual artist curation; it is automated enrichment.

### What MusicBrainz cannot solve alone

MusicBrainz will probably never fully encode subjective descriptors such as:

- theatrical,
- musical,
- uplifting,
- quirky,
- emotionally intense,
- Disney-villain energy,
- anime-opening feeling,
- villain musical rock,
- modern Broadway rock,
- not generic,
- no 80s production feel.

These are taste and semantic descriptors, not stable factual metadata. They require an automated semantic layer above MusicBrainz.

### Recommended semantic bridge

#### 1. Build a tag co-occurrence graph from MusicBrainz

Instead of manually writing aliases such as `theatrical → progressive rock`, derive expansion candidates from the corpus itself.

For each artist/release/recording/work, collect tags and compute which tags occur together. Then build a tag graph using signals such as:

- co-occurrence count,
- pointwise mutual information (PMI),
- log-likelihood ratio,
- cosine similarity over artist-tag vectors.

If the few artists tagged `theatrical` also tend to have `adventure rock`, `progressive rock`, `art rock`, `cabaret`, `comedy rock`, or `rock opera`, the system can learn a weighted expansion:

```text
theatrical
→ adventure rock: 0.72
→ rock opera: 0.68
→ cabaret: 0.61
→ progressive rock: 0.55
→ art rock: 0.52
```

This is safer than a hard alias because it preserves uncertainty.

Broad tags such as `rock`, `pop`, and `music` must be heavily downweighted, otherwise every query collapses into generic popular music.

#### 2. Build tag embeddings before full artist embeddings

A practical middle ground is to build embeddings or vector representations for tags, not artists first.

Process:

1. Build tag co-occurrence vectors.
2. Find nearest tags for each tag/concept.
3. At query time, expand unknown or rare descriptors to nearby corpus tags.

This is cheaper and simpler than full document embeddings, while still addressing vocabulary mismatch.

#### 3. Use LLMs for query interpretation, not artist invention

The LLM can help translate user prose into search concepts, but it should not invent the final artists or tracks.

Example input:

```text
modern theatrical pop-rock like Bear Ghost
```

Potential concept extraction:

```json
{
  "style_concepts": [
    "theatrical rock",
    "musical theatre influence",
    "adventure rock",
    "progressive pop rock",
    "art rock",
    "comedy rock",
    "rock opera",
    "quirky vocals",
    "modern production"
  ],
  "reference_artists": ["Bear Ghost"]
}
```

The extracted concepts are then mapped to MusicBrainz/Spotify corpus evidence. The LLM is used as a semantic parser, not as a database.

#### 4. Use reference artists as automatic translators

Reference artists are very valuable because they ground ambiguous user descriptors.

If the user says:

```text
theatrical rock like Bear Ghost
```

And the corpus has Bear Ghost tagged as:

```text
adventure rock, rock, progressive rock
```

Then the system can infer that, in this context, `theatrical` should be searched near Bear Ghost's corpus neighborhood, not globally mapped to all Broadway/show-tunes/musical-theatre material.

This can be automated:

1. Detect reference artists from user profile, analysis target, liked tracks, or confirmed artists.
2. Resolve them in the MusicBrainz corpus.
3. Pull their tags and related tags.
4. Expand through the tag co-occurrence graph.
5. Retrieve artists near that tag neighborhood.
6. Verify candidates on Spotify.

### Spotify's role

The current `artists.enriched.jsonl` contains no Spotify fields. That is a major gap.

Spotify should be used as a second source for:

- artist existence on Spotify,
- Spotify artist ID,
- genres,
- popularity,
- followers,
- top tracks,
- market availability,
- final artist/track verification.

Spotify genres are not perfect, but they are often closer to user vocabulary than MusicBrainz artist tags. They also provide the strongest anti-hallucination benefit: the app can require final artists/tracks to be verified before they reach the user.

MusicBrainz should remain the identity and metadata backbone. Spotify should be the availability and verification layer.

### Anti-hallucination retrieval pipeline

The app should avoid asking the AI to invent a playlist from a vibe. Instead, it should ask the AI to choose from evidence-backed candidates only.

Recommended pipeline:

#### Stage 0: interpret profile into concepts

Inputs:

- user prose,
- must-have constraints,
- avoid constraints,
- soft preferences,
- confirmed artists,
- liked tracks,
- analysis artist.

Output:

```json
{
  "hard_constraints": {
    "country_or_language": ["Japanese"],
    "exclude_regions": ["United States"],
    "exclude_genres": ["edm", "synthwave", "electronic"]
  },
  "style_concepts": [
    "theatrical rock",
    "musical theatre influence",
    "adventure rock",
    "progressive pop rock",
    "quirky rock"
  ],
  "reference_artists": ["Bear Ghost"]
}
```

The LLM may help produce this, but code should validate and normalize the result.

#### Stage 1: expand concepts through corpus-derived semantics

For every concept, combine:

1. direct tag matches,
2. literal aliases,
3. co-occurrence expansion,
4. reference-artist tag projection,
5. Spotify genre expansion, if available.

#### Stage 2: retrieve a broad artist pool

Retrieve a larger candidate pool, e.g. `300–1000` artists, using:

- exact tag matches,
- expanded tag matches,
- reference artist overlap,
- Spotify genre overlap,
- area/country constraints,
- popularity/availability,
- penalties for broad-only matches.

#### Stage 3: verify candidates on Spotify

For each candidate artist:

1. resolve to Spotify artist ID,
2. require a reasonable name/alias match,
3. fetch top tracks,
4. require at least one playable/top track,
5. attach Spotify genres/popularity/followers.

Artists that cannot be verified on Spotify should normally be removed before the final LLM selection step.

#### Stage 4: LLM rerank/filter with evidence only

The LLM should receive candidate evidence, not just artist names.

Example candidate shape:

```json
{
  "artist": "The Dear Hunter",
  "spotify_id": "...",
  "evidence": {
    "mb_tags": ["progressive rock", "art rock"],
    "spotify_genres": ["progressive rock", "modern rock"],
    "top_tracks": ["..."],
    "matched_concepts": ["theatrical rock", "progressive pop rock"],
    "reference_overlap": ["Bear Ghost-like progressive/adventure-rock neighborhood"]
  }
}
```

The instruction should be strict:

> Select from these candidates only. Do not introduce new artists. Do not invent tracks. If too few candidates fit, return fewer.

#### Stage 5: final Spotify verification

Before returning results to the user:

- verify every artist-track pair on Spotify,
- reject non-matches,
- retry with remaining verified candidates if needed.

This is the anti-hallucination loop.

### Shift from artist pool to evidence-backed candidate pool

The system should not only answer:

> Which artists might fit?

It should answer:

> Which verified artists fit, and what evidence can the AI use to safely select tracks?

The final LLM should not receive only this:

```text
Artist names:
- Artist A
- Artist B
- Artist C
```

It should receive evidence:

```text
Artist A
- verified Spotify ID
- top tracks
- MusicBrainz tags
- Spotify genres
- matched because: progressive rock + adventure rock + Bear Ghost reference overlap
```

Without evidence, the LLM must rely on memory, which is where hallucinated or weak tracks appear.

### What not to do

Do **not** solve this by manually curating artist-level descriptors. It is not scalable.

Do **not** create broad static aliases such as:

```text
theatrical → progressive rock
```

That will produce many false positives.

Do **not** rely on MusicBrainz artist tags only. They are too sparse.

Do **not** let the LLM invent missing artists/tracks. It should choose from verified candidates.

Do **not** evaluate a scenario until the corpus preflight says the corpus can support it.

### Prioritized implementation path

#### Phase 1: extract more value from MusicBrainz

1. Roll up release-group, release, recording, and work tags to artist profiles.
2. Add MusicBrainz area/country fields.
3. Add MusicBrainz aliases.
4. Build a tag co-occurrence graph.
5. Add automatic weighted tag expansion.
6. Downweight broad tags such as `rock`, `pop`, and `music`.

#### Phase 2: add Spotify verification/enrichment

1. Resolve candidate artists to Spotify IDs.
2. Store Spotify genres, popularity, and followers.
3. Store top tracks.
4. Require Spotify verification before candidates are sent to the LLM.

#### Phase 3: change the LLM contract

Move from:

```text
Suggest songs matching this profile.
```

to:

```text
Choose songs only from this verified evidence-backed candidate list.
```

This is likely the single biggest hallucination reduction.

#### Phase 4: add evaluation preflight gates

Before paid model evaluations, assert that the corpus has enough verified candidates satisfying the scenario.

For the Japanese scenario, for example:

- at least N verified Japanese/J-music artists,
- at least N with top tracks,
- at least N not electronic/EDM/synthwave,
- at least N not American,
- enough style overlap after semantic expansion.

If the preflight fails, the evaluation is invalid because it is measuring corpus failure, not model quality.

### Main recommendation

Use MusicBrainz as the factual identity and tag backbone, but add an automatically generated semantic bridge:

1. roll up more MusicBrainz tags,
2. compute tag co-occurrence expansions,
3. use reference artists as translators,
4. verify candidates through Spotify,
5. send only evidence-backed candidates/tracks to the AI.

This avoids manual curation while addressing the real issue: user language and MusicBrainz tags do not use the same vocabulary.

## Implementation plan — surgical bridge before corpus rebuild

Date added: 2026-05-01

### Problem restatement

The AI semantic layer (`theatrical`, `uplifting`, `Disney-villain energy`) is disjoint from the corpus tag layer (MusicBrainz factual: `adventure rock`, `progressive rock`, `rock`). Retrieval scores corpus tags only, so any AI-inferred attribute that is not also a corpus tag is invisible to candidate selection.

Concrete example: the AI classifies Bear Ghost as `theatrical`. The corpus tags Bear Ghost as `adventure rock, rock, progressive rock`. A user query `theatrical pop-rock` cannot retrieve Bear Ghost via the current path, even though the AI would correctly identify Bear Ghost as a fit for that prose.

### Sequence decision

The full corpus rebuild proposed in earlier sections of this document (Spotify enrichment, MusicBrainz tag rollup, tag co-occurrence graph, Stage 0 concept extraction) is multi-week work and depends on:

- regenerating `artists.enriched.jsonl` with Spotify fields, country, and top-tracks,
- rebuilding the corpus index format,
- adding a Stage 0 LLM step to the production request path.

Several smaller fixes are corpus-agnostic or schema-precursors and should ship first. They harden the pipeline before the bridge plugs in:

| ID | Description | Corpus dependency | Reason it ships first |
|---|---|---|---|
| F8.3 | Deterministic decade fit-check | None — uses Spotify `release_year` already on each track | Already half-written; cheap finish |
| F9 | Per-run trace bundle | None — diagnostic infrastructure | Debugging unblocker for every later step |
| F5 | Plumb feedback into `train_profile` | None — uses dislike reasons | Corpus-agnostic feedback-loop closure |
| F2 | Avoid tokenizer (era stops, aliases, negation) | Partial — adds corpus-tag aliases | Stabilises avoid pipeline before bridge touches it |
| F1 | Hard must-have gate in Stage 1 | Partial — enforces existing corpus tags | Designs the `must_have_tags` schema the bridge writes into |

After F1 lands, the bridge has somewhere to write its output and a tracing surface to verify it.

### Surgical bridge — AI tag-hints in `train_profile`

Single change, scoped to a profile schema field plus retrieval read:

1. **LLM output extension.** `train_profile` already calls the LLM to parse user prose. Extend the prompt to also emit `corpus_tag_hints: [adventure rock, progressive rock, rock opera, art rock, ...]` — for each `must_have` and `soft_preference` prose entry, the LLM translates the descriptor into a short list of corpus-vocabulary tags drawn from its parametric knowledge of MusicBrainz/genre taxonomy.
2. **Profile persistence.** Store `corpus_tag_hints` under `profile.preferences`. Cached at profile-train time, no per-request LLM cost.
3. **Retrieval consumption.** `build_query_tags` reads `corpus_tag_hints` as an additional weighted token source, weight `1.5` (between `must_have=2.0` and `soft=1.0`). Tokens still alias-resolve against the corpus, so unknown hints silently drop.
4. **Observability.** F9 trace bundle records which hints actually resolved to corpus tags and how many artists each hint promoted. This is the verification surface for whether the bridge is working.

### Why this is safe to ship before the full rebuild

- Pays the LLM expansion cost once at profile-train time, not per generation.
- Falls back gracefully: empty hints → existing tokeniser path unchanged.
- LLMs are reliably good at this specific translation (descriptor → genre taxonomy) because the MusicBrainz vocabulary is well-represented in their training data.
- Stage 2 LLM avoid-check still filters semantically downstream, so over-broad hint expansion (e.g. `theatrical → progressive rock` pulling non-theatrical prog rock) is bounded.
- Compatible with the eventual co-occurrence graph: that graph supersedes parametric LLM expansion when corpus enrichment lands. Both write into the same `corpus_tag_hints` field.

### Known false-positive surface

LLM-driven expansion will produce false positives. Examples expected:

- `theatrical` → `progressive rock` matches Yes / Genesis / Marillion as well as Bear Ghost.
- `uplifting` → `worship` / `gospel` matches.
- `Disney-villain energy` → `dark cabaret` matches that drift outside the user's actual taste.

Mitigations on the bridge alone:

- Hint weight strictly less than `must_have` — bridge candidates can be outscored by direct must-have matches.
- Stage 2 LLM check runs on the resulting pool — semantic prose like `Disney-villain energy` is the LLM's strength, not the corpus's.
- F9 trace records the exact tag-hint expansion per run so a regression can be diagnosed deterministically.

The proper long-term mitigation is the tag co-occurrence graph + reference-artist projection from the main recommendation above. It replaces parametric LLM expansion with corpus-grounded expansion and removes the false-positive class.

### Deferred until corpus rebuild

The following remain blocked on the multi-week enrichment effort:

- Country-based hard filters (`No American artists`, `Music must be Japanese`) — require structured `country` / `area` fields, not tags.
- Track-level grounding (anti-confab) — requires `top_tracks` per artist.
- Subjective descriptor fits (`harmonized vocals`, `not uplifting` negation, `theatrical production`) — require either richer MB tag rollup (release-group / recording / work tags promoted to artist) or external descriptor sources.
- Spotify-popularity-aware retrieval — requires `spotify_popularity` and `spotify_followers` fields.

These constraints stay in the GPT-5.5 phased plan above. The eval harness's preflight gate is the safety net: scenarios that depend on these fields are marked `corpus_readiness=blocked` and refused before any paid request fires.
