"""Retrieval-augmented candidate pool for suggestion prompts.

See documentation/guides/rag-implementation.md for design.
Public entry points:
    RagCorpus.load(path)             — construct an in-memory corpus.
    score_artists(corpus, query,     — return the top-K candidate pool.
                  deny_keys, ...)
    format_candidate_pool_block(...) — render the prompt fragment.
"""

from .corpus import RagCorpus, ArtistRow
from .retrieval import score_artists, score_artists_stratified, build_query_tags
from .prompt import format_candidate_pool_block

__all__ = [
    "RagCorpus",
    "ArtistRow",
    "score_artists",
    "score_artists_stratified",
    "build_query_tags",
    "format_candidate_pool_block",
]
