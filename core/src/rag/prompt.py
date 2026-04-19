"""Render a candidate-pool block for injection into the GPT system prompt.

Kept tiny and deterministic so its token-count is predictable — we claim
≤250 input tokens in rag-implementation.md §5.2 and hold ourselves to it.
"""

from __future__ import annotations

from .corpus import ArtistRow


def format_candidate_pool_block(artists: list[ArtistRow],
                                max_tags_per_artist: int = 3) -> str:
    """Return the ``CANDIDATE_POOL`` block, or empty string when *artists* is empty.

    Callers should concatenate this *after* the stable system prompt +
    profile and *before* the deny-list block (see §5.3 for KV-cache
    rationale).
    """
    if not artists:
        return ""

    lines: list[str] = [
        f"CANDIDATE_POOL ({len(artists)} artists ranked by profile match, "
        "mid-popularity-weighted):"
    ]
    for i, a in enumerate(artists, 1):
        shown_tags = [t for t in a.tags[:max_tags_per_artist] if t]
        tag_str = f" — tags: [{', '.join(shown_tags)}]" if shown_tags else ""
        lines.append(f"{i}. {a.name}{tag_str}")

    lines.append("")
    lines.append("GUIDANCE:")
    lines.append("- Prefer artists from CANDIDATE_POOL when a suggestion fits. "
                 "You do not have to pick all of them.")
    lines.append("- You MAY suggest artists outside the pool if they match the "
                 "profile strictly better. Do NOT invent artists.")
    lines.append("- CANDIDATE_POOL does NOT override DENY_LIST or "
                 "must_have/avoid constraints — those still win.")
    return "\n".join(lines)
