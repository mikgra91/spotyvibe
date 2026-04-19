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
