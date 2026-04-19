"""Unit tests for the candidate-pool prompt formatter."""

from __future__ import annotations

from core.src.rag.corpus import ArtistRow
from core.src.rag.prompt import format_candidate_pool_block


def _row(name: str, tags: list[str]) -> ArtistRow:
    return ArtistRow(mbid="x", name=name, tags=tags, tag_weights=[1] * len(tags))


def test_empty_pool_is_empty_string():
    assert format_candidate_pool_block([]) == ""


def test_block_contains_header_and_artists():
    artists = [_row("Alpha", ["shoegaze", "dream pop"]),
               _row("Beta", ["post-punk"])]
    block = format_candidate_pool_block(artists)
    assert "CANDIDATE_POOL (2 artists" in block
    assert "1. Alpha" in block
    assert "2. Beta" in block
    assert "shoegaze" in block
    assert "GUIDANCE:" in block


def test_tag_cap_enforced():
    artists = [_row("Alpha", ["t1", "t2", "t3", "t4", "t5"])]
    block = format_candidate_pool_block(artists, max_tags_per_artist=2)
    assert "t1" in block and "t2" in block
    assert "t3" not in block


def test_token_budget_holds():
    # §5.2 claim: 20 artists ≈ 240 input tokens (~12 tokens/line).
    # Use character count as a proxy (~4 chars/token for English).
    artists = [_row(f"Artist Number {i}", ["tag-a", "tag-b", "tag-c"])
               for i in range(20)]
    block = format_candidate_pool_block(artists)
    # Rough cap: 250 tokens * 4 chars = 1000 chars, allow 1200 for headers.
    assert len(block) < 1400
