"""Unit tests for core.src.rag.distribution."""

from __future__ import annotations

import hashlib
import http.server
import json
import threading
from pathlib import Path

import pytest

from core.src.rag.distribution import (
    BlocklistManifest, RemoteManifest, check_blocklist_update, check_for_update,
    download_blocklist, download_corpus, fetch_remote_manifest,
    installed_blocklist_version, read_local_meta, resolve_blocklist_manifest,
    write_local_meta,
)


# ── Local HTTP fixture ──────────────────────────────────────────────

@pytest.fixture
def http_root(tmp_path):
    """Serve `tmp_path` over HTTP on a random port for the duration of the test."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(tmp_path), **kw)
        def log_message(self, *a, **kw):
            pass  # silence access log noise
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield tmp_path, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _write_manifest(root: Path, **overrides) -> dict:
    payload = {
        "corpus_version": "2026-04-19",
        "built_at": "2026-04-19T10:00:00Z",
        "sha256": "deadbeef",
        "size_bytes": 123,
        "corpus_url": "http://example.invalid/artists.jsonl.gz",
    }
    payload.update(overrides)
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ── fetch_remote_manifest ──────────────────────────────────────────

def test_fetch_manifest_ok(http_root):
    root, base = http_root
    _write_manifest(root)
    manifest = fetch_remote_manifest(f"{base}/manifest.json")
    assert manifest is not None
    assert manifest.corpus_version == "2026-04-19"
    assert manifest.sha256 == "deadbeef"


def test_fetch_manifest_missing_returns_none():
    # Unreachable URL → None, not a raised exception.
    m = fetch_remote_manifest("http://127.0.0.1:1/manifest.json", timeout=0.5)
    assert m is None


def test_fetch_manifest_invalid_json_returns_none(http_root):
    root, base = http_root
    (root / "manifest.json").write_text("not json", encoding="utf-8")
    assert fetch_remote_manifest(f"{base}/manifest.json") is None


def test_fetch_manifest_incomplete_returns_none(http_root):
    root, base = http_root
    _write_manifest(root, sha256="")  # missing required field
    assert fetch_remote_manifest(f"{base}/manifest.json") is None


# ── check_for_update ────────────────────────────────────────────────

def test_check_offline_when_manifest_unreachable(tmp_path):
    status = check_for_update(
        tmp_path / "corpus.gz", tmp_path / "meta.json",
        manifest_url="http://127.0.0.1:1/manifest.json",
    )
    assert status == {"status": "offline"}


def test_check_missing_corpus(http_root, tmp_path):
    root, base = http_root
    _write_manifest(root)
    status = check_for_update(
        tmp_path / "corpus.gz", tmp_path / "meta.json",
        manifest_url=f"{base}/manifest.json",
    )
    assert status["status"] == "missing_corpus"
    assert status["remote"]["corpus_version"] == "2026-04-19"


def test_check_current_when_versions_match(http_root, tmp_path):
    root, base = http_root
    _write_manifest(root)
    corpus = tmp_path / "corpus.gz"
    corpus.write_bytes(b"stub")
    (tmp_path / "meta.json").write_text(
        json.dumps({"corpus_version": "2026-04-19"}), encoding="utf-8")
    status = check_for_update(corpus, tmp_path / "meta.json",
                              manifest_url=f"{base}/manifest.json")
    assert status["status"] == "current"


def test_check_update_available(http_root, tmp_path):
    root, base = http_root
    _write_manifest(root, corpus_version="2026-05-01")
    corpus = tmp_path / "corpus.gz"
    corpus.write_bytes(b"stub")
    (tmp_path / "meta.json").write_text(
        json.dumps({"corpus_version": "2026-04-19"}), encoding="utf-8")
    status = check_for_update(corpus, tmp_path / "meta.json",
                              manifest_url=f"{base}/manifest.json")
    assert status["status"] == "update_available"
    assert status["local_version"] == "2026-04-19"
    assert status["remote"]["corpus_version"] == "2026-05-01"


# ── download_corpus ────────────────────────────────────────────────

def test_download_corpus_streams_and_verifies(http_root, tmp_path):
    root, base = http_root
    payload = b"artist row A\nartist row B\n" * 100
    (root / "artists.jsonl.gz").write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    manifest = RemoteManifest(
        corpus_version="2026-04-19",
        built_at="2026-04-19T10:00:00Z",
        sha256=sha,
        size_bytes=len(payload),
        corpus_url=f"{base}/artists.jsonl.gz",
    )
    dest = tmp_path / "corpus.jsonl.gz"
    meta = tmp_path / "corpus.meta.json"
    download_corpus(manifest, dest, meta)
    assert dest.read_bytes() == payload
    assert not (tmp_path / "corpus.jsonl.gz.part").exists()
    meta_data = json.loads(meta.read_text(encoding="utf-8"))
    assert meta_data["corpus_version"] == "2026-04-19"
    assert meta_data["sha256"] == sha


def test_download_corpus_sha_mismatch_raises(http_root, tmp_path):
    root, base = http_root
    (root / "artists.jsonl.gz").write_bytes(b"payload")
    bogus = RemoteManifest(
        corpus_version="v", built_at="t",
        sha256="0" * 64, size_bytes=7,
        corpus_url=f"{base}/artists.jsonl.gz",
    )
    dest = tmp_path / "corpus.jsonl.gz"
    with pytest.raises(ValueError, match="sha256"):
        download_corpus(bogus, dest, tmp_path / "meta.json")
    # Partial file must have been cleaned up on mismatch.
    assert not (tmp_path / "corpus.jsonl.gz.part").exists()
    assert not dest.exists()


# ── local meta helpers ─────────────────────────────────────────────

def test_local_meta_roundtrip(tmp_path):
    m = RemoteManifest(
        corpus_version="v", built_at="t", sha256="a" * 64,
        size_bytes=42, corpus_url="http://ex/a",
    )
    path = tmp_path / "meta.json"
    write_local_meta(path, m)
    assert read_local_meta(path) == {
        "corpus_version": "v", "built_at": "t",
        "sha256": "a" * 64, "size_bytes": 42,
    }


def test_read_local_meta_missing_returns_none(tmp_path):
    assert read_local_meta(tmp_path / "nope.json") is None


# ── AI blocklist manifest fields + download ────────────────────────

def test_manifest_parses_ai_blocklist_fields():
    m = RemoteManifest.from_json({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": "http://ex/a",
        "ai_blocklist_url": "http://ex/ai_artists.json",
        "ai_blocklist_sha256": "B" * 64,  # uppercased on purpose
        "ai_blocklist_version": "2026-06-30",
        "ai_blocklist_count": 4321,
    })
    assert m.has_ai_blocklist()
    assert m.ai_blocklist_sha256 == "b" * 64  # normalised to lowercase
    assert m.ai_blocklist_version == "2026-06-30"
    assert m.ai_blocklist_count == 4321


def test_manifest_without_ai_blocklist_is_backward_compatible():
    # Older manifests lack the blocklist fields entirely.
    m = RemoteManifest.from_json({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": "http://ex/a",
    })
    assert m.is_valid()
    assert not m.has_ai_blocklist()
    assert m.ai_blocklist_url == ""
    assert m.ai_blocklist_count == 0


def _blocklist_manifest(url, sha, **kw):
    return BlocklistManifest(
        blocklist_version=kw.get("version", "2026-08-27"),
        built_at="t", sha256=sha, size_bytes=kw.get("size_bytes", 1),
        count=kw.get("count", 3), blocklist_url=url,
    )


def test_blocklist_manifest_parses_its_own_document():
    m = BlocklistManifest.from_json({
        "blocklist_version": "2026-08-27", "built_at": "t",
        "sha256": "B" * 64,  # uppercased on purpose
        "size_bytes": 194783, "count": 7487,
        "blocklist_url": "http://ex/ai_artists.abc123.json",
        "source": "upstream (MIT)",
    })
    assert m.is_valid()
    assert m.sha256 == "b" * 64  # normalised to lowercase
    assert m.blocklist_version == "2026-08-27"
    assert m.count == 7487


def test_blocklist_manifest_validity_ignores_corpus_fields():
    """The old coupling — a blocklist was unreachable without a valid corpus."""
    m = BlocklistManifest.from_json({
        "sha256": "a" * 64, "blocklist_url": "http://ex/ai.json",
    })
    assert m.is_valid()
    assert BlocklistManifest.from_json({"sha256": "a" * 64}).is_valid() is False


def test_blocklist_manifest_from_pre_split_corpus_manifest():
    corpus = RemoteManifest.from_json({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": "http://ex/a",
        "ai_blocklist_url": "http://ex/ai_artists.json",
        "ai_blocklist_sha256": "b" * 64,
        "ai_blocklist_version": "2026-06-30",
        "ai_blocklist_count": 4321,
    })
    m = BlocklistManifest.from_corpus(corpus)
    assert m is not None
    assert m.blocklist_url == "http://ex/ai_artists.json"
    assert m.count == 4321
    assert m.blocklist_version == "2026-06-30"
    # A corpus manifest with no blocklist fields yields nothing to adapt.
    plain = RemoteManifest.from_json({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": "http://ex/a",
    })
    assert BlocklistManifest.from_corpus(plain) is None


def test_download_blocklist_streams_and_verifies(http_root, tmp_path):
    root, base = http_root
    payload = json.dumps({"artist_ids": ["a1", "a2", "a3"]}).encode("utf-8")
    (root / "remote_ai_artists.json").write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    manifest = _blocklist_manifest(f"{base}/remote_ai_artists.json", sha, count=3)
    dest = tmp_path / "installed" / "ai_artists.json"
    meta = tmp_path / "installed" / "ai_artists.meta.json"
    count = download_blocklist(manifest, dest, meta)
    assert count == 3
    assert dest.read_bytes() == payload
    assert not dest.with_name("ai_artists.json.part").exists()
    assert json.loads(meta.read_text())["blocklist_version"] == "2026-08-27"


def test_download_blocklist_sha_mismatch_raises(http_root, tmp_path):
    root, base = http_root
    (root / "remote_ai_artists.json").write_bytes(b'["x"]')
    manifest = _blocklist_manifest(f"{base}/remote_ai_artists.json", "f" * 64)
    dest = tmp_path / "installed" / "ai_artists.json"
    meta = tmp_path / "installed" / "ai_artists.meta.json"
    with pytest.raises(ValueError, match="sha256"):
        download_blocklist(manifest, dest, meta)
    assert not dest.with_name("ai_artists.json.part").exists()
    assert not dest.exists()
    assert not meta.exists()  # a rejected download must not claim an install


def test_download_blocklist_without_url_raises(tmp_path):
    manifest = BlocklistManifest(
        blocklist_version="v", built_at="t", sha256="0" * 64,
        size_bytes=1, count=0, blocklist_url="",
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        download_blocklist(manifest, tmp_path / "ai_artists.json")


def test_resolve_blocklist_manifest_prefers_own_manifest(http_root, tmp_path):
    root, base = http_root
    (root / "ai_blocklist_manifest.json").write_text(json.dumps({
        "blocklist_version": "2026-08-27", "built_at": "t",
        "sha256": "a" * 64, "size_bytes": 10, "count": 7487,
        "blocklist_url": f"{base}/ai_artists.abc.json",
    }))
    manifest, reason = resolve_blocklist_manifest(
        f"{base}/ai_blocklist_manifest.json",
        corpus_manifest_url=f"{base}/manifest.json")
    assert reason == "ok"
    assert manifest.count == 7487
    assert manifest.blocklist_version == "2026-08-27"


def test_resolve_blocklist_manifest_falls_back_to_corpus(http_root):
    """A bucket published before the split still serves a blocklist."""
    root, base = http_root
    (root / "manifest.json").write_text(json.dumps({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": f"{base}/artists.jsonl.gz",
        "ai_blocklist_url": f"{base}/ai_artists.json",
        "ai_blocklist_sha256": "b" * 64,
        "ai_blocklist_version": "2026-06-30",
        "ai_blocklist_count": 4321,
    }))
    manifest, reason = resolve_blocklist_manifest(
        f"{base}/absent_blocklist_manifest.json",
        corpus_manifest_url=f"{base}/manifest.json")
    assert reason == "ok"
    assert manifest.count == 4321
    assert manifest.source == "legacy corpus manifest"


def test_resolve_blocklist_manifest_reports_unpublished(http_root):
    """Reachable manifest that names no blocklist is not the same as offline."""
    root, base = http_root
    (root / "manifest.json").write_text(json.dumps({
        "corpus_version": "v", "built_at": "t", "sha256": "a" * 64,
        "size_bytes": 1, "corpus_url": f"{base}/artists.jsonl.gz",
    }))
    manifest, reason = resolve_blocklist_manifest(
        f"{base}/absent_blocklist_manifest.json",
        corpus_manifest_url=f"{base}/manifest.json")
    assert manifest is None
    assert reason == "unpublished"


def test_resolve_blocklist_manifest_reports_offline(http_root):
    _root, base = http_root
    manifest, reason = resolve_blocklist_manifest(
        f"{base}/nope.json", corpus_manifest_url=f"{base}/also-nope.json")
    assert manifest is None
    assert reason == "offline"


def test_check_blocklist_update_statuses(http_root, tmp_path):
    root, base = http_root
    (root / "ai_blocklist_manifest.json").write_text(json.dumps({
        "blocklist_version": "2026-08-27", "built_at": "t",
        "sha256": "a" * 64, "size_bytes": 10, "count": 7487,
        "blocklist_url": f"{base}/ai_artists.abc.json",
    }))
    url = f"{base}/ai_blocklist_manifest.json"
    blocklist = tmp_path / "ai_artists.json"
    meta = tmp_path / "ai_artists.meta.json"

    assert check_blocklist_update(blocklist, meta, url)["status"] == "missing_blocklist"

    blocklist.write_text(json.dumps({"version": "2026-07-01", "artist_ids": []}))
    result = check_blocklist_update(blocklist, meta, url)
    assert result["status"] == "update_available"
    # Version came from inside the artifact — no sidecar was ever written.
    assert result["local_version"] == "2026-07-01"

    meta.write_text(json.dumps({"blocklist_version": "2026-08-27"}))
    assert check_blocklist_update(blocklist, meta, url)["status"] == "current"


def test_installed_blocklist_version_prefers_sidecar(tmp_path):
    blocklist = tmp_path / "ai_artists.json"
    meta = tmp_path / "ai_artists.meta.json"
    blocklist.write_text(json.dumps({"version": "from-artifact", "artist_ids": []}))
    assert installed_blocklist_version(blocklist, meta) == "from-artifact"
    meta.write_text(json.dumps({"blocklist_version": "from-sidecar"}))
    assert installed_blocklist_version(blocklist, meta) == "from-sidecar"


def test_installed_blocklist_version_unknown_is_empty(tmp_path):
    assert installed_blocklist_version(
        tmp_path / "absent.json", tmp_path / "absent.meta.json") == ""
