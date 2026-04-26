"""Render a candidate-pool block for injection into the GPT system prompt.

Kept tiny and deterministic so its token-count is predictable — we claim
≤250 input tokens for a 20-artist pool (scales linearly to ~1,200 for the
100-slot default) in documentation/TechnicalManual.md §"RAG design
reference" → Token budget for the candidate pool, and hold ourselves to it.
"""

from __future__ import annotations

from .corpus import ArtistRow


def format_candidate_pool_block(artists: list[ArtistRow],
                                max_tags_per_artist: int = 3) -> str:
    """Return the ``CANDIDATE_POOL`` block, or empty string when *artists* is empty.

    Callers should concatenate this *after* the stable system prompt +
    profile and *before* the deny-list block (see §5.3 for KV-cache
    rationale).

    Output is intentionally terse (Option C #2, 2026-04-22): no per-row
    index prefix, tags inline in parentheses. Saves ~6 tokens / row vs the
    previous ``"42. Name — tags: [a, b, c]"`` format — at the 100-slot
    default that's ~600 tokens/batch reclaimed without losing any
    information GPT actually uses (the index was never read; the
    ``— tags:`` prose was redundant given the parenthetical convention).
    """
    if not artists:
        return ""

    lines: list[str] = [
        f"CANDIDATE_POOL ({len(artists)} artists ranked by profile match, "
        "mid-popularity-weighted):"
    ]
    for a in artists:
        shown_tags = [t for t in a.tags[:max_tags_per_artist] if t]
        tag_str = f" ({', '.join(shown_tags)})" if shown_tags else ""
        lines.append(f"{a.name}{tag_str}")

    lines.append("")
    lines.append("GUIDANCE:")
    lines.append("- Prefer pool artists when a suggestion fits. Not all need to be picked.")
    lines.append("- You MAY suggest artists outside the pool if they match the profile "
                 "strictly better. Do NOT invent artists.")
    lines.append("- CANDIDATE_POOL does NOT override DENY_LIST or must_have/avoid.")
    return "\n".join(lines)
