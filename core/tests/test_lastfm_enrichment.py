"""Tests for the Last.fm-enrichment build helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools"))

import requests  # noqa: E402

from lastfm_enrichment.client import (  # noqa: E402
    LastfmArtistInfo,
    LastfmArtistNotFound,
    LastfmAuthError,
    LastfmBackoffBudgetExhausted,
    LastfmClient,
    LastfmError,
    LastfmRateLimitedError,
    LastfmServiceUnavailable,
    LastfmTransientFailure,
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


# ── Transient failures: non-JSON / network / max-retries ─────────────


def _bad_json_resp(status_code=200, body=b"<html>503 maintenance</html>"):
    """Build a response whose .json() raises ValueError (non-JSON body)."""
    r = MagicMock()
    r.status_code = status_code
    r.headers = {}
    r.content = body
    r.text = body.decode("utf-8", errors="replace")
    r.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")
    return r


def test_retries_on_non_json_body_then_succeeds(monkeypatch):
    """Last.fm 200 + HTML maintenance page → retry, do not crash the run."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.side_effect = [
        _bad_json_resp(),
        _bad_json_resp(body=b""),  # also: empty body
        _resp(json_body={"artist": {"stats": {"listeners": "7"}}}),
    ]
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners == 7
    assert sess.get.call_count == 3


def test_non_json_body_raises_transient_after_max_retries(monkeypatch):
    """After max_retries on non-JSON, raise LastfmTransientFailure (not RuntimeError)."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.return_value = _bad_json_resp()
    with pytest.raises(LastfmTransientFailure):
        _client(sess).get_artist_info("mbid-x")


def test_non_object_json_body_retried(monkeypatch):
    """A JSON list at top level is corrupt — retry."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.headers = {}
    list_resp.json.return_value = ["unexpected", "list"]
    sess.get.side_effect = [
        list_resp,
        _resp(json_body={"artist": {"stats": {"listeners": "1"}}}),
    ]
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners == 1
    assert sess.get.call_count == 2


def test_retries_on_connection_error(monkeypatch):
    """ConnectionError / Timeout / SSL error → exp backoff, not crash."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.side_effect = [
        requests.ConnectionError("Connection reset by peer"),
        requests.Timeout("Read timed out"),
        _resp(json_body={"artist": {"stats": {"listeners": "9"}}}),
    ]
    info = _client(sess).get_artist_info("mbid-x")
    assert info.listeners == 9
    assert sess.get.call_count == 3


def test_network_errors_after_max_retries_raise_transient(monkeypatch):
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.side_effect = requests.ConnectionError("perma-fail")
    with pytest.raises(LastfmTransientFailure):
        _client(sess).get_artist_info("mbid-x")


def test_4xx_other_than_429_raises_lastfm_error_no_retry(monkeypatch):
    """400 / 403 means our request is bad — propagate, do not retry."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    resp = MagicMock()
    resp.status_code = 403
    resp.headers = {}
    resp.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    sess = MagicMock()
    sess.get.return_value = resp
    with pytest.raises(LastfmError):
        _client(sess).get_artist_info("mbid-x")
    assert sess.get.call_count == 1


# ── fetch_artist circuit breaker ─────────────────────────────────────


def test_fetch_artist_swallows_single_transient_failure(monkeypatch):
    """One bad artist returns empty info; the run continues."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.return_value = _bad_json_resp()
    info = _client(sess).fetch_artist("mbid-x")
    assert info == LastfmArtistInfo()


def test_fetch_artist_resets_consecutive_counter_on_success(monkeypatch):
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr("lastfm_enrichment.client._MAX_CONSECUTIVE_TRANSIENT_FAILURES", 3)
    sess = MagicMock()
    # Two transients (5 attempts each = 10 calls), then a clean fetch
    # (getInfo + getTopTags = 2 calls), then more transients.
    transient_seq = [_bad_json_resp() for _ in range(5)] * 2
    success_seq = [
        _resp(json_body={"artist": {"stats": {"listeners": "1"}}}),
        _resp(json_body={"toptags": {"tag": []}}),
    ]
    more_transients = [_bad_json_resp() for _ in range(5)] * 2
    sess.get.side_effect = transient_seq + success_seq + more_transients
    c = _client(sess)
    c.fetch_artist("a")  # transient #1 (counter=1)
    c.fetch_artist("b")  # transient #2 (counter=2)
    info = c.fetch_artist("c")  # success → counter resets
    assert info.listeners == 1
    # Two more transients: counter goes 1, 2 — does NOT trip (would be 3+ pre-reset)
    c.fetch_artist("d")
    c.fetch_artist("e")
    # Counter is 2 now; no exception. Confirms reset worked.


def test_fetch_artist_circuit_breaker_aborts_after_threshold(monkeypatch):
    """N consecutive transient failures → LastfmServiceUnavailable."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr("lastfm_enrichment.client._MAX_CONSECUTIVE_TRANSIENT_FAILURES", 3)
    sess = MagicMock()
    sess.get.return_value = _bad_json_resp()
    c = _client(sess)
    c.fetch_artist("a")  # 1
    c.fetch_artist("b")  # 2
    with pytest.raises(LastfmServiceUnavailable):
        c.fetch_artist("c")  # 3 → trip


def test_fetch_artist_does_not_swallow_auth_error(monkeypatch):
    """Auth errors must propagate — bad API key should fail loudly."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.return_value = _resp(json_body={
        "error": 10, "message": "Invalid API key",
    })
    with pytest.raises(LastfmAuthError):
        _client(sess).fetch_artist("mbid-x")


def test_fetch_artist_does_not_swallow_rate_limit(monkeypatch):
    """Rate-limit errors must propagate so the driver sets the halt flag."""
    monkeypatch.setattr("lastfm_enrichment.client.time.sleep", lambda *_a, **_k: None)
    sess = MagicMock()
    sess.get.return_value = _resp(
        status_code=429, headers={"Retry-After": "9999"},
    )
    with pytest.raises(LastfmRateLimitedError):
        _client(sess).fetch_artist("mbid-x")
