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
    assert "Alpha" in block
    assert "Beta" in block
    assert "shoegaze" in block
    assert "GUIDANCE:" in block


def test_tag_cap_enforced():
    artists = [_row("Alpha", ["t1", "t2", "t3", "t4", "t5"])]
    block = format_candidate_pool_block(artists, max_tags_per_artist=2)
    assert "t1" in block and "t2" in block
    assert "t3" not in block


def test_artist_with_no_tags_renders_name_only():
    """Slim format must still work when the row has no tags."""
    artists = [_row("Solo", [])]
    block = format_candidate_pool_block(artists)
    assert "Solo" in block


def test_token_budget_under_cap():
    """20 artists should stay under the 1200-char cap."""
    artists = [_row(f"Artist Number {i}", ["tag-a", "tag-b", "tag-c"])
               for i in range(20)]
    block = format_candidate_pool_block(artists)
    assert len(block) < 1400
    assert len(block) < 1200
