"""Retrieval-augmented candidate pool for suggestion prompts.

See documentation/TechnicalManual.md §"RAG candidate-pool feature" and
§"RAG design reference" for the design.
Public entry points:
    RagCorpus.load(path)             — construct an in-memory corpus.
    score_artists(corpus, query,     — return the top-K candidate pool.
                  deny_keys, ...)
    format_candidate_pool_block(...) — render the prompt fragment.
"""

from .corpus import RagCorpus, ArtistRow
from .retrieval import (score_artists, score_artists_stratified, build_query_tags,
                        retrieve_candidates, retrieve_anchor_candidates,
                        build_anchor_query_tags)
from .prompt import format_candidate_pool_block

__all__ = [
    "RagCorpus",
    "ArtistRow",
    "score_artists",
    "score_artists_stratified",
    "build_query_tags",
    "retrieve_candidates",
    "retrieve_anchor_candidates",
    "build_anchor_query_tags",
    "format_candidate_pool_block",
]
