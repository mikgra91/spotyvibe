"""Tests for the model-conditional omission-rule resolver (R1.3 outcome).

The R1 baseline at `evaluation/baselines/2026-05-12_r1_full/` showed
that the strict `omitted_artists ≥ N − M` rule helps gpt-5.4 (+10 pp
Spotify-found) but collapses mini (playlist A 13.0 → 8.0, -38 %).

These tests pin the resolver behaviour so a future prompt-rewrite
can't silently re-tier a model into the wrong bucket.
"""
from __future__ import annotations

import pytest

from core.src.suggestions import (
    _OMISSION_RULE_SOFT,
    _OMISSION_RULE_STRICT_ARTICULATION,
    _OMISSION_RULE_STRICT_MODELS,
    _get_omission_rule,
)


def test_strict_models_get_articulation_variant() -> None:
    for model in _OMISSION_RULE_STRICT_MODELS:
        assert _get_omission_rule(model) == _OMISSION_RULE_STRICT_ARTICULATION


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.4-mini",
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "llama3:70b",
        "qwen2.5-coder",
        "",
        None,
    ],
)
def test_non_strict_models_get_soft_variant(model: str | None) -> None:
    assert _get_omission_rule(model) == _OMISSION_RULE_SOFT


def test_case_and_whitespace_insensitive() -> None:
    """Slug normalisation should not depend on user-supplied formatting."""
    assert _get_omission_rule("  GPT-5.4  ") == _OMISSION_RULE_STRICT_ARTICULATION
    assert _get_omission_rule("Gpt-4.1") == _OMISSION_RULE_STRICT_ARTICULATION


def test_strict_and_soft_are_distinct_strings() -> None:
    """Guard against an accidental copy-paste regression."""
    assert _OMISSION_RULE_SOFT != _OMISSION_RULE_STRICT_ARTICULATION
    # The soft variant must NOT contain the strict-rule's "include exactly
    # one entry" phrasing (that's what collapsed mini).
    assert "include exactly one entry" not in _OMISSION_RULE_SOFT
    # The strict variant must mention that QUOTA still wins — that is the
    # safeguard that distinguishes it from the rejected R1.3-strict rule.
    assert "QUOTA still takes precedence" in _OMISSION_RULE_STRICT_ARTICULATION


def test_mini_explicitly_excluded_from_strict() -> None:
    """Hard regression guard: mini variants must never silently flip to strict."""
    assert "gpt-5.4-mini" not in _OMISSION_RULE_STRICT_MODELS
    assert "gpt-4.1-mini" not in _OMISSION_RULE_STRICT_MODELS


def test_prompt_template_has_placeholder() -> None:
    """The shared system prompt must keep the `{omission_rule}` slot —
    otherwise the resolver becomes dead code."""
    from core.src.suggestions import TRACK_SELECT_SYSTEM_FILE, load_text_file

    template = load_text_file(TRACK_SELECT_SYSTEM_FILE)
    assert "{omission_rule}" in template

