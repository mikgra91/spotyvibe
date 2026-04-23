"""TF-IDF + popularity-penalised artist retrieval.

The retrieval contract is a single function — ``score_artists`` — so that
v2 can swap the implementation for embedding-based retrieval without
touching any caller. See rag-implementation.md §4 and §7.
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


def _extract_text_tokens(text: str) -> list[str]:
    """Crude tokeniser used to harvest extra tag hints from free-text fields.

    Splits on non-word characters, lowercases, drops 1-char tokens, and
    also emits 2-grams because genre names like "post punk" or "dream pop"
    are commonly written without a hyphen in user prose.
    """
    if not text:
        return []
    words = [w.lower() for w in re.split(r"\W+", str(text)) if len(w) > 1]
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


def _apply_aliases(corpus: RagCorpus, query: dict[str, float]) -> dict[str, float]:
    """Rewrite query keys through the alias map and drop tags the corpus
    doesn't know about — they can't possibly match anything anyway."""
    mapped: dict[str, float] = defaultdict(float)
    for tag, w in query.items():
        canon = corpus.resolve_alias(tag)
        if canon in corpus.tag_index:
            mapped[canon] += w
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
            # tag_weight for this artist: find its position in artist.tags
            # (tags are small — usually <20 — so linear scan is fine).
            try:
                pos = artist.tags.index(qtag)
                w = artist.tag_weights[pos] if pos < len(artist.tag_weights) else 1
            except ValueError:
                # Could happen if the artist has the tag in a non-normalised
                # form; fall back to 1 rather than missing the hit.
                w = 1
            scores[row_idx] += idf * float(w) * qweight

    if not scores:
        return []

    top_idx = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:_RERANK_POOL]

    reranked: list[tuple[float, int]] = []
    for idx, s in top_idx:
        artist = corpus.artists[idx]
        if normalise_name(artist.name) in deny_set:
            continue
        pop = max(0.0, min(1.0, artist.listener_popularity))
        final = s * (1.0 - popularity_penalty * pop)
        reranked.append((final, idx))

    reranked.sort(key=lambda t: t[0], reverse=True)
    return [corpus.artists[i] for _, i in reranked[:pool_size]]


# ── Stratified per-facet retrieval (Option 2) ────────────────────────
#
# The flat ``score_artists`` ranks the whole corpus by combined tag overlap.
# For an eclectic profile (e.g. "post-punk + ambient + city pop") the
# strongest single facet can dominate the top-K and starve the others.
#
# ``score_artists_stratified`` runs the retrieval once *per facet* with a
# per-facet quota and merges the results so every non-empty facet gets
# guaranteed representation in the final pool. See
# documentation/guides/rag-implementation.md §4 for the rationale.

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
            try:
                pos = artist.tags.index(qtag)
                w = artist.tag_weights[pos] if pos < len(artist.tag_weights) else 1
            except ValueError:
                w = 1
            scores[row_idx] += idf * float(w) * qweight

    if not scores:
        return []

    top_idx = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:_RERANK_POOL]

    reranked: list[tuple[float, int]] = []
    for idx, s in top_idx:
        artist = corpus.artists[idx]
        if normalise_name(artist.name) in deny_set:
            continue
        pop = max(0.0, min(1.0, artist.listener_popularity))
        final = s * (1.0 - popularity_penalty * pop)
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
    facet. See rag-implementation.md §4.

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

