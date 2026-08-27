"""Tests for the standalone blocklist publisher (build-tools/publish_ai_blocklist.py).

Proves the property that motivated splitting it out of cloud_run_publish.py:
the blocklist publishes on its own, and it fails **loudly** instead of silently
skipping — the old best-effort behaviour left a corpus publish looking
successful while the blocklist never shipped.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "build-tools"))

import publish_ai_blocklist as P  # noqa: E402

CSV = "artist,id\nAtomship,4PbKVheWA7ToOxOrqqzjol\nSmokey,32PcXsAFr3ArYaHSYr8qGh\n"


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen(body: str):
    return lambda req, timeout=None: _FakeResponse(body.encode("utf-8"))


# ── Upstream parsing ─────────────────────────────────────────────────

def test_fetch_artist_ids_parses_csv():
    with patch("urllib.request.urlopen", _urlopen(CSV)):
        ids = P.fetch_artist_ids("http://ex/ai.csv")
    assert ids == ["4PbKVheWA7ToOxOrqqzjol", "32PcXsAFr3ArYaHSYr8qGh"]


def test_fetch_artist_ids_dedupes_preserving_order():
    csv = CSV + "Dup,4PbKVheWA7ToOxOrqqzjol\nThird,3ec16T2vMbjJi4luOqt6ps\n"
    with patch("urllib.request.urlopen", _urlopen(csv)):
        ids = P.fetch_artist_ids("http://ex/ai.csv")
    assert ids == ["4PbKVheWA7ToOxOrqqzjol", "32PcXsAFr3ArYaHSYr8qGh",
                   "3ec16T2vMbjJi4luOqt6ps"]


def test_fetch_artist_ids_rejects_malformed_ids():
    """A truncated/garbage id must never reach the deny set."""
    csv = CSV + "Bad,not-an-id\nEmpty,\nSpaced, 3ec16T2vMbjJi4luOqt6ps \n"
    with patch("urllib.request.urlopen", _urlopen(csv)):
        ids = P.fetch_artist_ids("http://ex/ai.csv")
    assert "not-an-id" not in ids
    assert "3ec16T2vMbjJi4luOqt6ps" in ids  # whitespace-trimmed, still valid
    assert all(len(i) == 22 for i in ids)


def test_fetch_artist_ids_strips_bom():
    with patch("urllib.request.urlopen", _urlopen("﻿" + CSV)):
        ids = P.fetch_artist_ids("http://ex/ai.csv")
    assert ids[0] == "4PbKVheWA7ToOxOrqqzjol"


def test_build_payload_is_byte_stable():
    """Identical upstream data must hash identically so re-publish is a no-op."""
    ids = ["4PbKVheWA7ToOxOrqqzjol", "32PcXsAFr3ArYaHSYr8qGh"]
    assert P.build_payload(ids, "2026-08-27") == P.build_payload(ids, "2026-08-27")
    payload = json.loads(P.build_payload(ids, "2026-08-27"))
    assert payload["count"] == 2
    assert payload["artist_ids"] == ids
    assert payload["version"] == "2026-08-27"


def test_artifact_blob_name_is_content_addressed():
    sha = hashlib.sha256(b"x").hexdigest()
    name = P._artifact_blob_name(sha)
    assert name == f"ai_artists.{sha[:12]}.json"


# ── main(): exit codes and guards ────────────────────────────────────

@pytest.fixture
def env(monkeypatch):
    for key in ("GCS_BUCKET", "FORCE_PUBLISH", "MIN_COUNT", "MIN_COUNT_RATIO",
                "KEEP_VERSIONS", "DRY_RUN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    return monkeypatch


def test_dry_run_needs_no_gcs(env):
    env.setenv("DRY_RUN", "1")
    env.setenv("MIN_COUNT", "1")
    env.delenv("GCS_BUCKET")
    with patch("urllib.request.urlopen", _urlopen(CSV)):
        assert P.main() == P.EXIT_OK


def test_upstream_failure_exits_nonzero(env):
    """The old code printed a warning and let the caller report success."""
    def boom(req, timeout=None):
        raise OSError("connection reset")
    with patch("urllib.request.urlopen", boom):
        assert P.main() == P.EXIT_UPSTREAM


def test_too_few_ids_refuses_to_publish(env):
    with patch("urllib.request.urlopen", _urlopen(CSV)):  # only 2 ids
        assert P.main() == P.EXIT_UPSTREAM  # default MIN_COUNT is 1000


def test_shrink_guard_blocks_a_collapsed_upstream(env):
    """An upstream format break must not silently disable the filter."""
    env.setenv("MIN_COUNT", "1")
    bucket = MagicMock()
    with patch("urllib.request.urlopen", _urlopen(CSV)), \
         patch.object(P, "_bucket", return_value=bucket), \
         patch.object(P, "read_published_manifest",
                      return_value={"count": 7487, "sha256": "f" * 64}):
        assert P.main() == P.EXIT_UPSTREAM
    bucket.blob.assert_not_called()


def test_force_publish_overrides_shrink_guard(env):
    env.setenv("MIN_COUNT", "1")
    env.setenv("FORCE_PUBLISH", "1")
    env.setenv("KEEP_VERSIONS", "0")
    uploads = []
    with patch("urllib.request.urlopen", _urlopen(CSV)), \
         patch.object(P, "_bucket", return_value=MagicMock()), \
         patch.object(P, "read_published_manifest",
                      return_value={"count": 7487, "sha256": "f" * 64}), \
         patch.object(P, "_upload_bytes",
                      side_effect=lambda b, n, d, c: uploads.append((n, d))):
        assert P.main() == P.EXIT_OK
    assert len(uploads) == 2


def test_unchanged_content_is_a_no_op(env):
    env.setenv("MIN_COUNT", "1")
    with patch("urllib.request.urlopen", _urlopen(CSV)):
        ids = P.fetch_artist_ids("http://ex/ai.csv")
    import datetime
    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    sha = hashlib.sha256(P.build_payload(ids, version)).hexdigest()

    with patch("urllib.request.urlopen", _urlopen(CSV)), \
         patch.object(P, "_bucket", return_value=MagicMock()), \
         patch.object(P, "read_published_manifest",
                      return_value={"count": 2, "sha256": sha,
                                    "blocklist_version": version}), \
         patch.object(P, "_upload_bytes") as mock_upload:
        assert P.main() == P.EXIT_OK
    mock_upload.assert_not_called()


def test_publish_uploads_artifact_before_manifest(env):
    """A manifest must never name a blob that isn't uploaded yet."""
    env.setenv("MIN_COUNT", "1")
    env.setenv("KEEP_VERSIONS", "0")
    uploads = []
    with patch("urllib.request.urlopen", _urlopen(CSV)), \
         patch.object(P, "_bucket", return_value=MagicMock()), \
         patch.object(P, "read_published_manifest", return_value=None), \
         patch.object(P, "_upload_bytes",
                      side_effect=lambda b, n, d, c: uploads.append((n, d, c))):
        assert P.main() == P.EXIT_OK

    assert len(uploads) == 2
    artifact_name, artifact_bytes, artifact_cache = uploads[0]
    manifest_name, manifest_bytes, manifest_cache = uploads[1]
    assert artifact_name.startswith("ai_artists.")
    assert manifest_name == P.MANIFEST_BLOB
    assert "immutable" in artifact_cache          # content-addressed URL
    assert "max-age=300" in manifest_cache        # pointer must stay fresh

    manifest = json.loads(manifest_bytes)
    assert manifest["blocklist_url"].endswith(artifact_name)
    assert manifest["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert manifest["count"] == 2
    assert manifest["size_bytes"] == len(artifact_bytes)
    # No corpus fields — that coupling is what the split removed.
    assert "corpus_url" not in manifest
    assert "corpus_version" not in manifest


def test_gcs_write_failure_exits_nonzero(env):
    env.setenv("MIN_COUNT", "1")
    with patch("urllib.request.urlopen", _urlopen(CSV)), \
         patch.object(P, "_bucket", return_value=MagicMock()), \
         patch.object(P, "read_published_manifest", return_value=None), \
         patch.object(P, "_upload_bytes", side_effect=RuntimeError("403")):
        assert P.main() == P.EXIT_GCS


def test_missing_bucket_exits_nonzero(env):
    env.delenv("GCS_BUCKET")
    assert P.main() == P.EXIT_GCS


# ── Pruning ──────────────────────────────────────────────────────────

def test_prune_keeps_recent_artifacts_and_never_deletes_current():
    import datetime

    def blob(name, day):
        b = MagicMock()
        b.name = name
        b.time_created = datetime.datetime(2026, 8, day,
                                           tzinfo=datetime.timezone.utc)
        return b

    current = "ai_artists.current00000.json"
    old = [blob(f"ai_artists.old{i:018d}.json", i + 1) for i in range(6)]
    bucket = MagicMock()
    bucket.list_blobs.return_value = old + [blob(current, 20)]

    P.prune_old_artifacts(bucket, current, keep=3)

    deleted = [b.name for b in old if b.delete.called]
    kept = [b.name for b in old if not b.delete.called]
    assert len(kept) == 2          # keep=3 counts the current one
    assert len(deleted) == 4
    assert current not in deleted


def test_prune_disabled_by_zero():
    bucket = MagicMock()
    P.prune_old_artifacts(bucket, "ai_artists.x.json", keep=0)
    bucket.list_blobs.assert_not_called()
