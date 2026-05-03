"""Tests for the Last.fm-enrichment build helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools"))

from lastfm_enrichment.client import (  # noqa: E402
    LastfmArtistInfo,
    LastfmArtistNotFound,
    LastfmAuthError,
    LastfmBackoffBudgetExhausted,
    LastfmClient,
    LastfmError,
    LastfmRateLimitedError,
)


def _resp(status_code=200, json_body=None, headers=None):
    r = MagicMock()
    r.status_code = status_code
    r.headers = headers or {}
    r.json.return_value = json_body or {}
    return r


def _client(session):
    # Disable inter-request throttle by zeroing the module constant for
    # the duration of the test — saves ~210ms × N calls in CI.
    return LastfmClient("test-key", session=session)


# ── Init ─────────────────────────────────────────────────────────────


def test_requires_api_key():
    with pytest.raises(ValueError):
        LastfmClient("")


def test_sets_user_agent_header():
    sess = MagicMock()
    sess.headers = {}
    LastfmClient("k", session=sess, user_agent="ua/1.0")
    assert sess.headers["User-Agent"] == "ua/1.0"


# ── get_artist_info ──────────────────────────────────────────────────


def test_get_artist_info_parses_listeners_and_playcount():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "artist": {"name": "Radiohead", "stats": {"listeners": "5123456",
                                                   "playcount": "987654321"}},
    })
    info = _client(sess).get_artist_info("a74b1b7f-71a5-4011-9441-d0b5e4122711")
    assert info.listeners == 5123456
    assert info.playcount == 987654321
    # tags left empty by getInfo path (driver merges getTopTags)
    assert info.tags == []


def test_get_artist_info_missing_stats_returns_none_fields():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={"artist": {"name": "X"}})
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners is None
    assert info.playcount is None


def test_get_artist_info_empty_mbid_short_circuits():
    sess = MagicMock()
    info = _client(sess).get_artist_info("")
    assert info == LastfmArtistInfo()
    sess.get.assert_not_called()


def test_get_artist_info_passes_required_query_params():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={"artist": {"stats": {}}})
    _client(sess).get_artist_info("mbid-x")
    call = sess.get.call_args
    params = call.kwargs["params"]
    assert params["api_key"] == "test-key"
    assert params["format"] == "json"
    assert params["method"] == "artist.getInfo"
    assert params["mbid"] == "mbid-x"


def test_get_artist_info_returns_empty_on_artist_not_found():
    # Last.fm signals "not found" via HTTP 200 + error code 6
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "error": 6, "message": "The artist you supplied could not be found",
    })
    info = _client(sess).get_artist_info("mbid-bogus")
    assert info == LastfmArtistInfo()


def test_invalid_api_key_raises_auth_error():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "error": 10, "message": "Invalid API key",
    })
    with pytest.raises(LastfmAuthError):
        _client(sess).get_artist_info("mbid-x")


def test_unknown_error_raises_generic_lastfm_error():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "error": 99, "message": "Unrecognised",
    })
    with pytest.raises(LastfmError):
        _client(sess).get_artist_info("mbid-x")


# ── get_top_tags ─────────────────────────────────────────────────────


def test_get_top_tags_returns_weighted_lowercased():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "toptags": {"tag": [
            {"name": "Rock", "count": 100},
            {"name": "Alternative Rock", "count": 54},
            {"name": "Indie", "count": 24},
        ]},
    })
    tags = _client(sess).get_top_tags("mbid-x")
    assert tags == [("rock", 100), ("alternative rock", 54), ("indie", 24)]


def test_get_top_tags_clamps_weight_range():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "toptags": {"tag": [
            {"name": "a", "count": 250},
            {"name": "b", "count": -5},
            {"name": "c", "count": "invalid"},
        ]},
    })
    tags = _client(sess).get_top_tags("mbid-x")
    assert tags == [("a", 100), ("b", 0), ("c", 0)]


def test_get_top_tags_handles_single_tag_dict():
    # Last.fm returns a single dict (not a list) when there is exactly one tag.
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "toptags": {"tag": {"name": "rock", "count": 100}},
    })
    tags = _client(sess).get_top_tags("mbid-x")
    assert tags == [("rock", 100)]


def test_get_top_tags_dedups_case_variants():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "toptags": {"tag": [
            {"name": "Rock", "count": 100},
            {"name": "rock", "count": 90},
        ]},
    })
    tags = _client(sess).get_top_tags("mbid-x")
    assert tags == [("rock", 100)]


def test_get_top_tags_empty_when_none():
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={"toptags": {}})
    assert _client(sess).get_top_tags("mbid-x") == []


# ── fetch_artist (combined) ──────────────────────────────────────────


def test_fetch_artist_merges_info_and_tags():
    sess = MagicMock()
    sess.get.side_effect = [
        _resp(json_body={"artist": {"stats": {"listeners": "10",
                                                "playcount": "20"}}}),
        _resp(json_body={"toptags": {"tag": [{"name": "rock", "count": 100}]}}),
    ]
    info = _client(sess).fetch_artist("mbid-x")
    assert info.listeners == 10
    assert info.playcount == 20
    assert info.tags == [("rock", 100)]


# ── Retry / backoff ──────────────────────────────────────────────────


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.side_effect = [
        _resp(status_code=429, headers={"Retry-After": "1"}),
        _resp(json_body={"artist": {"stats": {"listeners": "1"}}}),
    ]
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners == 1
    assert sess.get.call_count == 2


def test_retries_on_5xx_with_exponential_backoff(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", sleeps.append)
    sess = MagicMock()
    sess.get.side_effect = [
        _resp(status_code=500),
        _resp(status_code=503),
        _resp(json_body={"artist": {"stats": {"listeners": "1"}}}),
    ]
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners == 1
    # Inter-request throttle adds sub-second sleeps too — filter to the
    # backoff-sized ones. First retry waits 1s (2^0), second waits 2s (2^1).
    backoff_sleeps = [s for s in sleeps if s >= 1]
    assert backoff_sleeps == [1, 2]


def test_aborts_when_retry_after_exceeds_safety_cap(monkeypatch):
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.return_value = _resp(
        status_code=429, headers={"Retry-After": "9999"},
    )
    with pytest.raises(LastfmRateLimitedError):
        _client(sess).get_artist_info("mbid-x")


def test_aborts_when_cumulative_backoff_budget_exhausted(monkeypatch):
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr("lastfm_enrichment.client._MAX_TOTAL_BACKOFF_SEC", 1.0)
    sess = MagicMock()
    sess.get.return_value = _resp(
        status_code=429, headers={"Retry-After": "2"},
    )
    with pytest.raises(LastfmBackoffBudgetExhausted):
        _client(sess).get_artist_info("mbid-x")
