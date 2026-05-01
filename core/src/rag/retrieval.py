"""TF-IDF + popularity-penalised artist retrieval.

The retrieval contract is a single function — ``score_artists`` — so that
v2 can swap the implementation for embedding-based retrieval without
touching any caller. See documentation/TechnicalManual.md §"RAG design
reference" → Retrieval scoring formula and Sparse retrieval over embeddings.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Iterable

from .corpus import ArtistRow, RagCorpus, normalise_name, normalise_tag

logger = logging.getLogger(__name__)

# Max candidates promoted from the posting lists before popularity re-rank.
# Keeps the re-rank step O(small) even if a tag has a huge posting list.
_RERANK_POOL = 200

# L1 (2026-04-29): per-call retrieval metadata exposed for the Stage 2
# dispatcher in app.py to decide whether the avoid-compliance LLM call can
# be skipped. Populated at the end of every `retrieve_candidates` call;
# read via `get_last_retrieval_meta()`. Keys:
#   - avoid_tags_count: int — how many distinct avoid tags Stage 1 derived
#   - avoid_filter_applied: bool — True iff the tag-based avoid filter ran
#     successfully (didn't bypass due to over-aggressive shrinkage)
#   - pool_avoid_overlap: int — count of returned candidates that still
#     match any avoid tag (always 0 when avoid_filter_applied is True)
#   - avoid_traits_total: int — count of prose entries in
#     preferences.avoid the user wrote
#   - avoid_traits_covered: int — how many of those produced ≥1
#     corpus-resolved tag (i.e. were enforceable by tag filtering)
#   - avoid_traits_fully_covered: bool — True iff every avoid prose
#     entry produced ≥1 corpus-resolved tag. Required before the
#     Stage-2 skip is safe (F3, 2026-05-01).
#   - candidates_returned: int — len(result)
_LAST_RETRIEVAL_META: dict | None = None


def get_last_retrieval_meta() -> dict | None:
    """Return the most recent `retrieve_candidates` metadata, or None.

    Used by app.py's Stage 2 dispatcher to decide whether the LLM avoid-check
    can be skipped (lever L1 in `cost-speed-research.md`). Returns a fresh
    snapshot per call; not thread-safe — same single-flight assumption as
    the rest of the suggestion pipeline.
    """
    return dict(_LAST_RETRIEVAL_META) if _LAST_RETRIEVAL_META else None


# Common English stop words that pollute the query if a user writes prose
# like "art-pop or J-pop crossover" or "punchy guitars and strong hooks".
# Without filtering, "or" / "and" / "the" accumulate the highest weights and
# overwhelm legitimate genre tags. Bigrams that contain a stop word are also
# meaningless ("strong or", "hooks and") so we drop them too.
_STOP_TOKENS = frozenset({
    # English grammatical stop words
    "or", "and", "but", "the", "a", "an", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "as", "is", "it", "be", "are", "was", "were",
    "this", "that", "these", "those",
    # ── Music-domain quality descriptors (added 2026-04-27) ──
    # These describe a track's QUALITY or CHARACTER, not a GENRE. They
    # appear in user-written taste prose ("strong hooks, modern production,
    # clear vocal melody, polished but not generic, vocal-forward,
    # storytelling lyrics, orchestral horn-section flourishes…") but they
    # do NOT discriminate between artists. Worse: when 1-3 random artists
    # in MusicBrainz happen to be tagged with these literal words, those
    # artists get an enormous IDF-weighted score boost and dominate the
    # candidate pool — which is exactly the P2.0 bug that surfaced
    # barbershop a-cappella for a "modern theatrical pop-rock" seed.
    # Empirical proof: see the diagnostic dump in result-improvement.md
    # (Phase 1 / 2026-04-27). Each entry below is documented as either
    # "quality" (track property) or "noise" (random tag fragment from
    # the seed prose decomposition).
    "strong", "modern", "polished", "generic", "punchy", "clear", "forward",
    "vocal", "vocals", "melodic", "melody", "production", "lyrics",
    "personality", "storytelling", "flourishes", "influences", "crossover",
    "dominance", "dominated", "straight", "ahead", "straightforward",
    "unmastered", "demos", "lean", "not", "post", "section", "feel",
    "based", "driven", "leaning", "esque", "like", "ish",
    # Numeric era fragments — handled by year-band logic in score_artists,
    # not by literal tag matching.
    "2010", "2020", "60s", "70s", "80s", "90s", "00s",
})


def _extract_text_tokens(text: str) -> list[str]:
    """Crude tokeniser used to harvest extra tag hints from free-text fields.

    Splits on non-word characters, lowercases, drops 1-char tokens and
    common stop words, and emits 2-grams because genre names like
    "post punk" or "dream pop" are commonly written without a hyphen
    in user prose. Bigrams containing a stop word on either side are
    skipped — a phrase like "strong hooks" survives, but "strong or"
    gets dropped.
    """
    if not text:
        return []
    words = [
        w.lower()
        for w in re.split(r"\W+", str(text))
        if len(w) > 1 and w.lower() not in _STOP_TOKENS
    ]
    # Unigrams first, then bigrams — callers weight the second half higher
    # because compound genre names are more specific than their unigrams.
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]} {words[i + 1]}")
        tokens.append(f"{words[i]}-{words[i + 1]}")
    return tokens


# Extra multiplier for multi-word tokens: compound genre matches are more
# diagnostic than their unigrams (e.g. "dream pop" ≫ "pop").
_COMPOUND_BOOST = 3.0


def build_query_tags(profile: dict,
                     primary_reference: dict | None = None) -> dict[str, float]:
    """Extract a ``{tag: weight}`` query from a profile + optional reference.

    The profile schema in SpotyVibe is loosely typed, so we harvest tags
    from every place a user might have put them:

    - ``preferences.must_have`` / ``.soft_preferences`` — prose lists.
    - ``preferences.genres`` / ``.moods`` — structured lists, if present.
    - *primary_reference.analysis* free text — from analysis_prompt output.

    Weights: must-have 2.0, soft 1.0, analysis 0.8. The caller can then
    fold these into the TF-IDF score linearly.
    """
    weights: dict[str, float] = defaultdict(float)

    prefs = (profile or {}).get("preferences", {}) or {}

    def _ingest(source, weight: float):
        if source is None:
            return
        def _add(tok: str, w: float):
            norm = normalise_tag(tok)
            if not norm:
                return
            # Bigram / hyphenated-compound tokens get a boost — they name
            # a more specific genre than either of their unigrams.
            mult = _COMPOUND_BOOST if (" " in norm or "-" in norm) else 1.0
            weights[norm] += w * mult

        if isinstance(source, list):
            for item in source:
                if isinstance(item, str):
                    for tok in _extract_text_tokens(item):
                        _add(tok, weight)
                elif isinstance(item, dict):
                    for v in item.values():
                        _ingest(v, weight)
        elif isinstance(source, str):
            for tok in _extract_text_tokens(source):
                _add(tok, weight)

    _ingest(prefs.get("must_have"), 2.0)
    _ingest(prefs.get("must_have_tags"), 2.0)
    _ingest(prefs.get("genres"), 1.5)
    _ingest(prefs.get("moods"), 1.5)
    _ingest(prefs.get("eras"), 1.2)
    _ingest(prefs.get("soft_preferences"), 1.0)
    _ingest(prefs.get("core_description"), 0.8)

    if primary_reference:
        _ingest(primary_reference.get("analysis"), 0.8)
        _ingest(primary_reference.get("genres"), 1.5)
        _ingest(primary_reference.get("moods"), 1.5)

    weights.pop("", None)
    return dict(weights)


def _apply_aliases(corpus: RagCorpus, query: dict[str, float],
                   min_artist_frequency: int | None = None) -> dict[str, float]:
    """Rewrite query keys through the alias map and drop tags the corpus
    doesn't know about — they can't possibly match anything anyway.

    Also drops tags whose corpus frequency is below *min_artist_frequency*
    (default 3 for production-sized corpora). Rationale (added 2026-04-27
    as P2.0 fix): a tag matching only 1-2 artists out of 172k is almost
    certainly a random user-tagging artefact (someone literally typed
    "hooks" or "strong" in the free-form tag field), not a discriminating
    genre signal. With TF-IDF, these single-artist tags get the maximum
    IDF weight, meaning a single noise-tagged artist can dominate the
    candidate pool. The min-frequency floor neutralises this without
    touching the IDF computation itself.

    The floor is auto-disabled for tiny corpora (< 100 artists) so unit
    tests built on hand-crafted 3-5-artist fixtures still pass — those
    test the scoring LOGIC not the noise-floor heuristic.
    """
    if min_artist_frequency is None:
        min_artist_frequency = 3 if len(corpus.artists) >= 100 else 1
    mapped: dict[str, float] = defaultdict(float)
    dropped_lowfreq = 0
    for tag, w in query.items():
        canon = corpus.resolve_alias(tag)
        if canon not in corpus.tag_index:
            continue
        if len(corpus.tag_index.get(canon, ())) < min_artist_frequency:
            dropped_lowfreq += 1
            continue
        mapped[canon] += w
    if dropped_lowfreq:
        logger.debug("RAG: dropped %d query tags with corpus frequency "
                     "< %d (likely noise).", dropped_lowfreq, min_artist_frequency)
    return dict(mapped)


def score_artists(corpus: RagCorpus,
                  profile: dict,
                  deny_keys: Iterable[str] = (),
                  primary_reference: dict | None = None,
                  pool_size: int = 20,
                  popularity_penalty: float = 0.4) -> list[ArtistRow]:
    """Return the top *pool_size* artists ranked for *profile*.

    *deny_keys* are normalised-name strings (use :func:`corpus.normalise_name`)
    — artists matching any of them are dropped *before* ranking cutoff so
    the pool is always full of new candidates.
    """
    if not corpus.artists or pool_size <= 0:
        return []

    raw_query = build_query_tags(profile, primary_reference)
    query = _apply_aliases(corpus, raw_query)
    if not query:
        logger.debug("RAG: empty query after alias mapping — returning nothing.")
        return []

    deny_set = {normalise_name(k) for k in deny_keys if k}

    scores: dict[int, float] = defaultdict(float)
    for qtag, qweight in query.items():
        idf = corpus.tag_idf.get(qtag, 1.0)
        for row_idx in corpus.tag_index.get(qtag, ()):
            artist = corpus.artists[row_idx]
            w = _artist_tag_weight(artist, qtag)
            scores[row_idx] += idf * float(w) * qweight

    if not scores:
        return []

    top_idx = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:_RERANK_POOL]

    reranked: list[tuple[float, int]] = []
    for idx, s in top_idx:
        artist = corpus.artists[idx]
        if normalise_name(artist.name) in deny_set:
            continue
        pop = _artist_popularity(artist)
        final = s * (1.0 - popularity_penalty * pop)
        # Phase 2: small discovery sweet-spot boost — artists in the
        # 0.3-0.7 popularity band are lesser-known but viable and tend
        # to be the most useful suggestions. ±10 % swing.
        if 0.3 <= pop <= 0.7:
            final *= 1.10
        reranked.append((final, idx))

    reranked.sort(key=lambda t: t[0], reverse=True)
    return [corpus.artists[i] for _, i in reranked[:pool_size]]


# ── Per-artist scoring helpers (Phase 2) ─────────────────────────────

def _artist_tag_weight(artist: ArtistRow, qtag: str) -> int:
    """Resolve the per-artist weight for *qtag* against MB tags + Spotify genres.

    MB community tags carry their explicit ``tag_weights`` count. Spotify
    genres don't have per-artist weights — Spotify just lists them — so
    we treat them as constant weight 2 (slightly above an average MB tag,
    reflecting that Spotify-curated genres are higher signal than raw
    community tags). Falls back to 1 if no match — defensive, should be
    unreachable since the index only points us at artists that have the
    tag somewhere.
    """
    try:
        pos = artist.tags.index(qtag)
        return artist.tag_weights[pos] if pos < len(artist.tag_weights) else 1
    except ValueError:
        pass
    # Check Spotify genres (normalised match — corpus stores them raw).
    for g in artist.spotify_genres:
        if normalise_tag(g) == qtag:
            return 2
    return 1


def _artist_popularity(artist: ArtistRow) -> float:
    """Return a 0..1 popularity score, preferring real Spotify data.

    Spotify popularity is 0-100; we map to 0-1. For unenriched artists
    we fall back to the MB-derived ``listener_popularity`` proxy.
    """
    if artist.spotify_popularity is not None:
        return max(0.0, min(1.0, artist.spotify_popularity / 100.0))
    return max(0.0, min(1.0, artist.listener_popularity))


# ── Stratified per-facet retrieval (Option 2) ────────────────────────
#
# The flat ``score_artists`` ranks the whole corpus by combined tag overlap.
# For an eclectic profile (e.g. "post-punk + ambient + city pop") the
# strongest single facet can dominate the top-K and starve the others.
#
# ``score_artists_stratified`` runs the retrieval once *per facet* with a
# per-facet quota and merges the results so every non-empty facet gets
# guaranteed representation in the final pool. See
# documentation/TechnicalManual.md §"RAG design reference" → Stratified
# retrieval for the rationale.

# Facet → which profile fields contribute, with the per-field weight that
# ``build_query_tags`` already applies. Keeping the mapping close to the
# weights table at the top of build_query_tags so behaviour drift is obvious.
_FACET_FIELDS: dict[str, list[tuple[str, float]]] = {
    "must_have":         [("must_have", 2.0), ("must_have_tags", 2.0)],
    "soft_preferences":  [("soft_preferences", 1.0), ("core_description", 0.8)],
    "primary_reference": [],  # consumed from primary_reference arg directly
    "tags":              [("genres", 1.5), ("moods", 1.5), ("eras", 1.2)],
}


def _build_facet_query(prefs: dict, facet: str,
                       primary_reference: dict | None) -> dict[str, float]:
    """Project the profile down to a single-facet ``{tag: weight}`` query.

    Mirrors :func:`build_query_tags` but only ingests the fields that
    belong to *facet*. Returns an empty dict if the facet is empty —
    callers should skip those facets.
    """
    weights: dict[str, float] = defaultdict(float)

    def _add(tok: str, w: float):
        norm = normalise_tag(tok)
        if not norm:
            return
        mult = _COMPOUND_BOOST if (" " in norm or "-" in norm) else 1.0
        weights[norm] += w * mult

    def _ingest(source, weight: float):
        if source is None:
            return
        if isinstance(source, list):
            for item in source:
                if isinstance(item, str):
                    for tok in _extract_text_tokens(item):
                        _add(tok, weight)
                elif isinstance(item, dict):
                    for v in item.values():
                        _ingest(v, weight)
        elif isinstance(source, str):
            for tok in _extract_text_tokens(source):
                _add(tok, weight)

    for field_name, weight in _FACET_FIELDS.get(facet, []):
        _ingest(prefs.get(field_name), weight)

    if facet == "primary_reference" and primary_reference:
        _ingest(primary_reference.get("analysis"), 0.8)
        _ingest(primary_reference.get("genres"), 1.5)
        _ingest(primary_reference.get("moods"), 1.5)

    weights.pop("", None)
    return dict(weights)


def _score_with_query(corpus: RagCorpus,
                      query: dict[str, float],
                      deny_set: set[str],
                      pool_size: int,
                      popularity_penalty: float,
                      already_picked_idx: set[int]) -> list[tuple[float, int]]:
    """Internal: run TF-IDF + popularity-rerank with a pre-built query.

    Returns ``[(final_score, row_idx), ...]`` sorted desc, capped at
    *pool_size*. Skips rows already in *already_picked_idx* — used by
    the stratified merge to avoid double-counting.
    """
    if not query or pool_size <= 0:
        return []

    scores: dict[int, float] = defaultdict(float)
    for qtag, qweight in query.items():
        idf = corpus.tag_idf.get(qtag, 1.0)
        for row_idx in corpus.tag_index.get(qtag, ()):
            if row_idx in already_picked_idx:
                continue
            artist = corpus.artists[row_idx]
            w = _artist_tag_weight(artist, qtag)
            scores[row_idx] += idf * float(w) * qweight

    if not scores:
        return []

    top_idx = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:_RERANK_POOL]

    reranked: list[tuple[float, int]] = []
    for idx, s in top_idx:
        artist = corpus.artists[idx]
        if normalise_name(artist.name) in deny_set:
            continue
        pop = _artist_popularity(artist)
        final = s * (1.0 - popularity_penalty * pop)
        if 0.3 <= pop <= 0.7:
            final *= 1.10
        reranked.append((final, idx))

    reranked.sort(key=lambda t: t[0], reverse=True)
    return reranked[:pool_size]


def score_artists_stratified(corpus: RagCorpus,
                             profile: dict,
                             deny_keys: Iterable[str] = (),
                             primary_reference: dict | None = None,
                             pool_size: int = 100,
                             popularity_penalty: float = 0.4,
                             facet_weights: dict[str, float] | None = None
                             ) -> list[ArtistRow]:
    """Return up to *pool_size* artists with guaranteed per-facet quotas.

    *facet_weights* maps facet name → fraction of *pool_size*; missing
    keys default to 0. The remainder (1 - sum of weights, but never < 0)
    is filled from a final flat pass that ignores facets — this captures
    artists that match the profile broadly without dominating any single
    facet. See documentation/TechnicalManual.md §"RAG design reference"
    → Stratified retrieval.

    Falls back to the flat :func:`score_artists` when:
    - every facet returns an empty query (caller has a near-empty profile), or
    - *pool_size* <= 0.
    """
    if not corpus.artists or pool_size <= 0:
        return []

    weights = facet_weights or {
        "must_have": 0.50, "soft_preferences": 0.25,
        "primary_reference": 0.15, "tags": 0.10,
    }

    prefs = (profile or {}).get("preferences", {}) or {}
    deny_set = {normalise_name(k) for k in deny_keys if k}

    picked_idx: set[int] = set()
    picked_in_order: list[int] = []
    facet_pool_counts: dict[str, int] = {}

    for facet, frac in weights.items():
        quota = max(1, int(round(pool_size * frac)))
        query = _apply_aliases(corpus, _build_facet_query(prefs, facet, primary_reference))
        if not query:
            facet_pool_counts[facet] = 0
            continue
        ranked = _score_with_query(corpus, query, deny_set, quota,
                                   popularity_penalty, picked_idx)
        added = 0
        for _, idx in ranked:
            if idx in picked_idx:
                continue
            picked_idx.add(idx)
            picked_in_order.append(idx)
            added += 1
            if len(picked_in_order) >= pool_size:
                break
        facet_pool_counts[facet] = added
        if len(picked_in_order) >= pool_size:
            break

    # Fill remainder from a flat pass (any facet) so we always hit pool_size
    # when there's enough matching corpus material.
    if len(picked_in_order) < pool_size:
        flat_query = _apply_aliases(corpus, build_query_tags(profile, primary_reference))
        if flat_query:
            remaining = pool_size - len(picked_in_order)
            ranked = _score_with_query(corpus, flat_query, deny_set, remaining,
                                       popularity_penalty, picked_idx)
            for _, idx in ranked:
                if idx in picked_idx:
                    continue
                picked_idx.add(idx)
                picked_in_order.append(idx)
                if len(picked_in_order) >= pool_size:
                    break

    if not picked_in_order:
        # Nothing matched any facet — fall back to flat retrieval so we
        # don't silently return [] for a profile that has data but uses
        # tags the corpus doesn't index.
        logger.debug("RAG stratified: empty result, falling back to flat.")
        return score_artists(corpus, profile, deny_keys=deny_keys,
                             primary_reference=primary_reference,
                             pool_size=pool_size,
                             popularity_penalty=popularity_penalty)

    logger.debug("RAG stratified: %s → %d artists", facet_pool_counts,
                 len(picked_in_order))
    return [corpus.artists[i] for i in picked_in_order]


# ── Stage 1: code-side candidate retrieval (Phase 1 pipeline) ────────


def _avoid_traits_coverage(
    corpus: RagCorpus, profile: dict
) -> tuple[set[str], int, int]:
    """Build the canonical avoid-tag set + per-trait coverage stats.

    Returns ``(avoid_tags, traits_total, traits_covered)``:

    - *avoid_tags* — canonical tags (corpus-resolved) covering the avoid
      prose; directly comparable to ``artist.tags`` keys.
    - *traits_total* — count of distinct prose entries the user wrote
      under ``preferences.avoid``.
    - *traits_covered* — how many of those entries produced at least one
      corpus-recognised tag (i.e. could be enforced by tag-based
      filtering at all).

    F3 fix (2026-05-01): the L1 Stage-2 skip is only safe when
    ``traits_total == traits_covered``. For semantic prose like
    "American artists" / "80s production style" / "Songs that are not
    uplifting" the tokeniser produces zero corpus-resolved tags, so the
    code-side avoid filter is silently a no-op and the LLM semantic
    check is the only remaining gate. Reporting coverage lets the
    Stage 2 dispatcher decide whether the skip is safe.
    """
    prefs = (profile or {}).get("preferences", {}) or {}
    avoid_source = prefs.get("avoid")
    if not avoid_source:
        return set(), 0, 0

    if isinstance(avoid_source, str):
        items: list[str] = [avoid_source]
    elif isinstance(avoid_source, list):
        items = [s for s in avoid_source if isinstance(s, str) and s.strip()]
    else:
        return set(), 0, 0

    avoid_tags: set[str] = set()
    covered = 0
    for item in items:
        item_tags: set[str] = set()
        for tok in _extract_text_tokens(item):
            n = normalise_tag(tok)
            if not n:
                continue
            canon = corpus.resolve_alias(n)
            # Only include tags the corpus actually indexes — unindexed
            # tokens cannot match any artist and would silently exclude
            # nothing.
            if canon in corpus.tag_index:
                item_tags.add(canon)
        if item_tags:
            covered += 1
            avoid_tags.update(item_tags)

    return avoid_tags, len(items), covered


def _artist_has_any_tag(artist: ArtistRow, tag_set: set[str]) -> bool:
    """Return True if *artist* has any of the given normalised tags."""
    for t in artist.tags:
        if t in tag_set:
            return True
    for g in artist.spotify_genres:
        if normalise_tag(g) in tag_set:
            return True
    return False


def retrieve_candidates(
    corpus: RagCorpus,
    profile: dict,
    deny_keys: Iterable[str] = (),
    target_size: int = 50,
    popularity_penalty: float = 0.4,
    primary_reference: dict | None = None,
) -> list[ArtistRow]:
    """Stage 1 code-side retrieval for the three-stage pipeline (P1.1).

    Returns up to *target_size* candidate artists without any LLM call.
    Uses stratified scoring for initial ranking, then applies two hard filters:

    1. **Avoid filter** — drops artists whose tags overlap with
       ``preferences.avoid``. Skipped if fewer than one third of
       *target_size* survive (too aggressive for this profile).
    2. **Popularity band** — prefers artists in the 0.3–0.7 discovery
       sweet-spot. Relaxed to the full pool when fewer than half
       *target_size* fall inside the band.

    *deny_keys* are normalised artist name strings (history + confirmed +
    rejected) forwarded to the underlying stratified scorer so already-
    seen artists are excluded before ranking.

    *primary_reference* — optional dict with ``analysis``/``genres``/
    ``moods`` keys (from the Band/Song Analysis feature). When supplied,
    the stratified scorer reserves a 15 % facet quota for artists that
    overlap with the user's north-star reference. Without this, the
    quota is silently absorbed by the flat-fill fallback (the P2.2
    fix from 2026-04-27).

    Returns an empty list when the corpus is empty or *target_size* ≤ 0.
    """
    if not corpus.artists or target_size <= 0:
        return []

    # Fetch a broad pool — 3× target so there is room to survive filters.
    broad = score_artists_stratified(
        corpus, profile,
        deny_keys=deny_keys,
        pool_size=target_size * 3,
        popularity_penalty=popularity_penalty,
        primary_reference=primary_reference,
    )
    if not broad:
        return []

    # Hard filter 1: avoid tags — drop artists matching any avoid trait.
    avoid_tags, avoid_traits_total, avoid_traits_covered = (
        _avoid_traits_coverage(corpus, profile)
    )
    avoid_filter_applied = False
    if avoid_tags:
        filtered = [a for a in broad if not _artist_has_any_tag(a, avoid_tags)]
        # Threshold scales with target_size so the floor is not binding for
        # small target sizes (used in tests). For target_size=4 the floor
        # would otherwise be 10, making the avoid filter unreachable.
        threshold = max(min(10, target_size), target_size // 3)
        if len(filtered) >= threshold:
            broad = filtered
            avoid_filter_applied = True
        else:
            logger.debug(
                "retrieve_candidates: avoid filter too aggressive (%d→%d), skipping",
                len(broad), len(filtered),
            )

    # Hard filter 2: popularity band — prefer 0.3–0.7 discovery sweet-spot.
    in_band = [a for a in broad if 0.3 <= _artist_popularity(a) <= 0.7]
    if len(in_band) >= target_size // 2:
        broad = in_band
    else:
        logger.debug(
            "retrieve_candidates: popularity band too narrow (%d of %d in-band), using full pool",
            len(in_band), len(broad),
        )

    result = broad[:target_size]
    # L1 (2026-04-29): post-hoc sanity check — count surviving candidates
    # that still match any avoid tag. When `avoid_filter_applied` is True the
    # filter ran successfully and this MUST be 0 by construction; we surface
    # the count anyway so app.py can defensively re-verify before deciding
    # to skip the Stage 2 LLM call. When the filter was bypassed (too
    # aggressive) or there were no avoid_tags to begin with, the count is
    # over the unfiltered surviving set and may be > 0.
    pool_avoid_overlap = (
        sum(1 for a in result if _artist_has_any_tag(a, avoid_tags))
        if avoid_tags else 0
    )
    # F3 (2026-05-01): the L1 Stage-2 skip downstream MUST also check
    # that every avoid prose entry produced ≥1 corpus-resolved tag —
    # otherwise the `pool_avoid_overlap == 0` signal is meaningless
    # (zero overlap because the filter had nothing to filter on).
    avoid_traits_fully_covered = (
        avoid_traits_total > 0 and avoid_traits_total == avoid_traits_covered
    )
    global _LAST_RETRIEVAL_META
    _LAST_RETRIEVAL_META = {
        "avoid_tags_count": len(avoid_tags),
        "avoid_filter_applied": avoid_filter_applied,
        "pool_avoid_overlap": pool_avoid_overlap,
        "avoid_traits_total": avoid_traits_total,
        "avoid_traits_covered": avoid_traits_covered,
        "avoid_traits_fully_covered": avoid_traits_fully_covered,
        "candidates_returned": len(result),
    }
    logger.debug(
        "retrieve_candidates: %d candidates selected (avoid_tags=%d, "
        "filter_applied=%s, pool_overlap=%d, traits=%d/%d covered)",
        len(result), len(avoid_tags), avoid_filter_applied, pool_avoid_overlap,
        avoid_traits_covered, avoid_traits_total,
    )

    # F9 (2026-05-01): per-run trace capture. No-op when DEBUG_MODE off.
    # Captures the query tags + weights, avoid tag set + coverage, and
    # the returned candidate list with the data needed to debug "why
    # did artist X appear?" deterministically.
    try:
        from core.src import trace
        if trace.is_active():
            query_tags = build_query_tags(profile, primary_reference=primary_reference)
            trace.record("stage1_query", {
                "tags": dict(query_tags),
                "target_size": target_size,
                "popularity_penalty": popularity_penalty,
                "primary_reference_name": (primary_reference or {}).get("name"),
            })
            trace.record("stage1_avoid", {
                "tags": sorted(avoid_tags),
                "filter_applied": avoid_filter_applied,
                "pool_avoid_overlap": pool_avoid_overlap,
                "traits_total": avoid_traits_total,
                "traits_covered": avoid_traits_covered,
                "traits_fully_covered": avoid_traits_fully_covered,
            })
            trace.record("stage1_candidates", [
                {
                    "name": a.name,
                    "mbid": getattr(a, "mbid", None),
                    "tags": list(a.tags)[:10],
                    "spotify_genres": list(getattr(a, "spotify_genres", []) or [])[:10],
                    "listener_popularity": getattr(a, "listener_popularity", None),
                }
                for a in result
            ])
    except Exception as exc:  # pragma: no cover — trace must never break a run
        logger.debug("trace capture (stage1) failed: %s", exc)

    return result

