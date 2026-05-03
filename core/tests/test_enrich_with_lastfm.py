"""Tests for the Last.fm enrichment driver script."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools"))

import enrich_with_lastfm as driver  # noqa: E402
from lastfm_enrichment.client import (  # noqa: E402
    LastfmArtistInfo, LastfmAuthError, LastfmBackoffBudgetExhausted,
    LastfmRateLimitedError,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@pytest.fixture
def sample_corpus(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _write_jsonl(inp, [
        {"mbid": "mb-1", "name": "A", "listener_popularity": 0.9},
        {"mbid": "mb-2", "name": "B", "listener_popularity": 0.5},
        {"mbid": "",     "name": "C", "listener_popularity": 0.3},
    ])
    return inp, out


# ── Skip / passthrough paths ─────────────────────────────────────────


def test_passthrough_when_disable_flag_set(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("DISABLE_LASTFM_ENRICHMENT", "1")
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")
    rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == 0
    rows = _read_jsonl(out)
    assert rows == _read_jsonl(inp)


def test_passthrough_when_api_key_missing(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("DISABLE_LASTFM_ENRICHMENT", raising=False)
    rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == 0
    rows = _read_jsonl(out)
    assert rows == _read_jsonl(inp)


def test_returns_1_when_input_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")
    rc = driver.main([
        "--input", str(tmp_path / "missing.jsonl"),
        "--output", str(tmp_path / "out.jsonl"),
    ])
    assert rc == 1


# ── Enrichment happy path ────────────────────────────────────────────


def test_enriches_rows_with_listeners_playcount_and_tags(
    monkeypatch, sample_corpus
):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")
    monkeypatch.delenv("DISABLE_LASTFM_ENRICHMENT", raising=False)

    fake_info = {
        "mb-1": LastfmArtistInfo(
            listeners=1000, playcount=2000,
            tags=[("rock", 100), ("noise", 5)],
        ),
        "mb-2": LastfmArtistInfo(
            listeners=50, playcount=120,
            tags=[("indie", 80)],
        ),
    }

    def _fake_fetch(self, mbid):
        return fake_info[mbid]

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == 0

    rows = {r["mbid"] or r["name"]: r for r in _read_jsonl(out)}
    # mb-1: tags filtered by default min-weight=30 → noise dropped
    assert rows["mb-1"]["lastfm_listeners"] == 1000
    assert rows["mb-1"]["lastfm_playcount"] == 2000
    assert rows["mb-1"]["lastfm_tags"] == [["rock", 100]]
    # mb-2: indie at weight 80 survives
    assert rows["mb-2"]["lastfm_tags"] == [["indie", 80]]
    # No-mbid row is emitted unchanged (no Last.fm fields)
    assert "lastfm_listeners" not in rows["C"]
    assert "lastfm_tags" not in rows["C"]


def test_min_tag_weight_flag_overrides_default(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")
    monkeypatch.delenv("DISABLE_LASTFM_ENRICHMENT", raising=False)

    info = LastfmArtistInfo(tags=[("a", 50), ("b", 10)])
    with patch.object(driver.LastfmClient, "fetch_artist",
                       lambda self, mbid: info):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--min-tag-weight", "5",
        ])
    assert rc == 0
    rows = _read_jsonl(out)
    enriched = [r for r in rows if r.get("lastfm_tags")]
    # Both tags survive at weight≥5
    assert all(set(t[0] for t in r["lastfm_tags"]) == {"a", "b"}
               for r in enriched)


def test_max_enrich_limits_lookups(monkeypatch, tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _write_jsonl(inp, [
        {"mbid": f"mb-{i}", "name": f"A{i}", "listener_popularity": 0.9 - i * 0.01}
        for i in range(5)
    ])
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    calls: list[str] = []

    def _fake_fetch(self, mbid):
        calls.append(mbid)
        return LastfmArtistInfo(listeners=1)

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--max-enrich", "2",
        ])
    assert rc == 0
    # Only top 2 by popularity get fetched
    assert calls == ["mb-0", "mb-1"]
    rows = _read_jsonl(out)
    assert len(rows) == 5  # passthrough included


def test_min_popularity_skips_below_threshold(monkeypatch, tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    _write_jsonl(inp, [
        {"mbid": "mb-hi", "name": "Hi", "listener_popularity": 0.8},
        {"mbid": "mb-lo", "name": "Lo", "listener_popularity": 0.1},
    ])
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    calls: list[str] = []

    def _fake_fetch(self, mbid):
        calls.append(mbid)
        return LastfmArtistInfo(listeners=1)

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--min-popularity", "50",
        ])
    assert rc == 0
    assert calls == ["mb-hi"]


# ── Failure modes ────────────────────────────────────────────────────


def test_rate_limit_returns_special_exit_code(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmRateLimitedError("Retry-After 9999s")

    with patch.object(driver.LastfmClient, "fetch_artist", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.RATE_LIMIT_EXIT_CODE


def test_backoff_budget_exhausted_returns_special_exit_code(
    monkeypatch, sample_corpus
):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmBackoffBudgetExhausted("budget blown")

    with patch.object(driver.LastfmClient, "fetch_artist", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.RATE_LIMIT_EXIT_CODE


def test_auth_error_returns_dedicated_exit_code(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmAuthError("[10] Invalid API key")

    with patch.object(driver.LastfmClient, "fetch_artist", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.AUTH_ERROR_EXIT_CODE
