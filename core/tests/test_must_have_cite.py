"""Must-have cite detection (eval_log) — 2026-06 hardening.

``has_must_have_cite`` is a TEXT proxy for "did the model name a must-have
trait in a profile_match rationale?". These tests pin the tolerant
matcher: it must accept genuine citations the model wraps in quotes /
"Must:" prefixes / hyphen variants, and accept a single sub-trait of a
composite must-have — WITHOUT matching a soft-preference (which would
mask a real miscite, the failure mode the rewrite was built to expose).

Cases are taken verbatim from re-scoring the 2026-06 eval logs against
the recovered profiles.
"""
from __future__ import annotations

from core.src.eval_log import (
    arg_satisfies_must_have,
    build_must_have_subtraits,
)


def _sat(arg, must_have):
    return arg_satisfies_must_have(arg, build_must_have_subtraits(must_have))


# ── Real misses the OLD strict detector dropped (now must count) ──────

def test_composite_subtrait_cite_counts():
    mh = ["modern, theatrical, hook-forward anchor", "modern production"]
    assert _sat("hook-forward anchor", mh)          # one sub-trait of a composite
    assert _sat("theatrical", mh)


def test_quote_and_must_prefix_stripped():
    mh = ["modern, theatrical, hook-forward anchor", "modern production"]
    assert _sat('"Must: modern"', mh)               # echoed label + quotes
    assert _sat('"hook-forward anchor"', mh)


def test_hyphen_space_insensitive():
    assert _sat("math-rock energy", ["math rock"])
    assert _sat("post rock textures", ["Post-rock"])


def test_legacy_token_paraphrase_still_counts():
    # The CF-Telemetry-1 behaviour must be preserved.
    assert _sat("uplifting modern production sound", ["modern production"])
    assert _sat("Japanese city pop", ["japanese"])


# ── The guard: a soft-pref citation must NOT register as a must-have cite

def test_soft_pref_arg_does_not_match_genre_must_have():
    # must_have are genre labels; the arg cites a SOFT-pref sonic trait.
    mh = ["Post-rock", "slowcore", "math rock", "instrumental focus"]
    assert not _sat("tape-saturated guitar tones", mh)
    assert not _sat("polyrhythmic drumming", mh)
    assert not _sat('"ambient interludes"', mh)


def test_empty_and_unrelated():
    mh = ["math rock"]
    assert not _sat("", mh)
    assert not _sat("catchy chorus", mh)


# ── build_must_have_subtraits structure ──────────────────────────────

def test_build_splits_composite_and_dedupes():
    st = build_must_have_subtraits(["modern, theatrical, hook-forward anchor"])
    phrases = {p for p, _c, _t in st}
    assert "modern, theatrical, hook-forward anchor" in phrases  # whole kept
    assert "modern" in phrases and "theatrical" in phrases
    assert "hook-forward anchor" in phrases


def test_build_drops_empty_and_stopword_only():
    assert build_must_have_subtraits([]) == []
    assert build_must_have_subtraits(["", "  "]) == []
    # a stop-word-only entry yields no usable tokens
    assert build_must_have_subtraits(["the and of"]) == []
