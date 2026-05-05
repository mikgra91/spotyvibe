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
    rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
    assert rc == 0
    rows = _read_jsonl(out)
    assert rows == _read_jsonl(inp)


def test_passthrough_when_api_key_missing(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("DISABLE_LASTFM_ENRICHMENT", raising=False)
    rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
    assert rc == 0
    rows = _read_jsonl(out)
    assert rows == _read_jsonl(inp)


def test_returns_1_when_input_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")
    rc = driver.main([
        "--input", str(tmp_path / "missing.jsonl"),
        "--output", str(tmp_path / "out.jsonl"),
        "--skip-smoke",
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
        rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
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
            "--min-tag-weight", "5", "--skip-smoke",
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
            "--max-enrich", "2", "--skip-smoke",
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
            "--min-popularity", "50", "--skip-smoke",
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
        rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
    assert rc == driver.RATE_LIMIT_EXIT_CODE


def test_backoff_budget_exhausted_returns_special_exit_code(
    monkeypatch, sample_corpus
):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmBackoffBudgetExhausted("budget blown")

    with patch.object(driver.LastfmClient, "fetch_artist", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
    assert rc == driver.RATE_LIMIT_EXIT_CODE


def test_auth_error_returns_dedicated_exit_code(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmAuthError("[10] Invalid API key")

    with patch.object(driver.LastfmClient, "fetch_artist", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out), "--skip-smoke"])
    assert rc == driver.AUTH_ERROR_EXIT_CODE


# ── Smoke pre-flight ─────────────────────────────────────────────────


def test_smoke_pre_flight_aborts_on_auth_error(monkeypatch, sample_corpus):
    """Smoke pre-flight catches a bad API key before the 18 h main loop."""
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "bad-key")

    def _raise(self, mbid):
        raise LastfmAuthError("[10] Invalid API key")

    with patch.object(driver.LastfmClient, "get_artist_info", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.AUTH_ERROR_EXIT_CODE
    assert not out.exists()  # no main-loop output should have been written


def test_smoke_pre_flight_aborts_on_rate_limit(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def _raise(self, mbid):
        raise LastfmRateLimitedError("Retry-After 9999s")

    with patch.object(driver.LastfmClient, "get_artist_info", _raise):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.RATE_LIMIT_EXIT_CODE


def test_smoke_pre_flight_aborts_on_low_listener_count(monkeypatch, sample_corpus):
    """If smoke artists return suspiciously low listener counts (sandbox /
    wrong account), abort — the data would be useless."""
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    with patch.object(driver.LastfmClient, "get_artist_info",
                       lambda self, mbid: LastfmArtistInfo(listeners=5)):
        rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == driver.SMOKE_FAIL_EXIT_CODE


def test_smoke_pre_flight_passes_with_real_listeners(monkeypatch, sample_corpus):
    inp, out = sample_corpus
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    with patch.object(driver.LastfmClient, "get_artist_info",
                       lambda self, mbid: LastfmArtistInfo(listeners=5_000_000)):
        with patch.object(driver.LastfmClient, "fetch_artist",
                           lambda self, mbid: LastfmArtistInfo(listeners=1)):
            rc = driver.main(["--input", str(inp), "--output", str(out)])
    assert rc == 0
    assert out.exists()


# ── Checkpoint / resume ──────────────────────────────────────────────


def test_resumes_from_existing_checkpoint(monkeypatch, tmp_path):
    """Pre-existing checkpoint with mb-1 already enriched → mb-1 is not
    re-fetched, and the final output preserves both rows."""
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    checkpoint = tmp_path / "ckpt.jsonl"
    _write_jsonl(inp, [
        {"mbid": "mb-1", "name": "A", "listener_popularity": 0.9},
        {"mbid": "mb-2", "name": "B", "listener_popularity": 0.5},
    ])
    # Seed the checkpoint with mb-1 already enriched.
    _write_jsonl(checkpoint, [
        {"mbid": "mb-1", "name": "A",
         "listener_popularity": 0.9, "lastfm_listeners": 999},
    ])
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    calls: list[str] = []

    def _fake_fetch(self, mbid):
        calls.append(mbid)
        return LastfmArtistInfo(listeners=42)

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--checkpoint", str(checkpoint), "--skip-smoke",
        ])
    assert rc == 0
    # mb-1 was NOT re-fetched (already in checkpoint)
    assert calls == ["mb-2"]
    rows = {r["mbid"]: r for r in _read_jsonl(out)}
    # mb-1 retains its checkpointed enrichment
    assert rows["mb-1"]["lastfm_listeners"] == 999
    # mb-2 got the fresh enrichment
    assert rows["mb-2"]["lastfm_listeners"] == 42
    # Checkpoint promoted → output (so checkpoint no longer exists)
    assert not checkpoint.exists()


def test_no_resume_flag_ignores_checkpoint(monkeypatch, tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    checkpoint = tmp_path / "ckpt.jsonl"
    _write_jsonl(inp, [
        {"mbid": "mb-1", "name": "A", "listener_popularity": 0.9},
    ])
    _write_jsonl(checkpoint, [
        {"mbid": "mb-1", "name": "A",
         "listener_popularity": 0.9, "lastfm_listeners": 999},
    ])
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    calls: list[str] = []

    def _fake_fetch(self, mbid):
        calls.append(mbid)
        return LastfmArtistInfo(listeners=42)

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--checkpoint", str(checkpoint), "--no-resume", "--skip-smoke",
        ])
    assert rc == 0
    # --no-resume → mb-1 IS re-fetched
    assert calls == ["mb-1"]
    rows = _read_jsonl(out)
    assert rows[0]["lastfm_listeners"] == 42


def test_checkpoint_preserved_on_rate_limit_abort(monkeypatch, tmp_path):
    """When the run aborts mid-way, the checkpoint must survive so the
    next container can pick up where it left off."""
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    checkpoint = tmp_path / "ckpt.jsonl"
    _write_jsonl(inp, [
        {"mbid": "mb-1", "name": "A", "listener_popularity": 0.9},
        {"mbid": "mb-2", "name": "B", "listener_popularity": 0.5},
    ])
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    call_count = {"n": 0}

    def _fake_fetch(self, mbid):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LastfmArtistInfo(listeners=10)
        raise LastfmRateLimitedError("Retry-After 9999s")

    with patch.object(driver.LastfmClient, "fetch_artist", _fake_fetch):
        rc = driver.main([
            "--input", str(inp), "--output", str(out),
            "--checkpoint", str(checkpoint), "--skip-smoke",
        ])
    assert rc == driver.RATE_LIMIT_EXIT_CODE
    # Final output NOT produced
    assert not out.exists()
    # Checkpoint preserved with mb-1's partial work
    assert checkpoint.exists()
    rows = _read_jsonl(checkpoint)
    mbids_in_ckpt = {r["mbid"] for r in rows}
    assert "mb-1" in mbids_in_ckpt
