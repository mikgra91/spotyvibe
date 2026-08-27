"""Corpus distribution & update-check for the RAG candidate pool.

The corpus file itself (``artists.jsonl.gz``) is hosted in a public
Google Cloud Storage bucket (``spotivibe-rag-corpus``), together with a
``manifest.json`` sidecar that names the version, size, and sha256. A
weekly Cloud Run Job rebuilds the corpus from the latest MusicBrainz
dump and uploads it automatically. The helpers in this module:

- :func:`fetch_remote_manifest` — best-effort GET of the manifest URL,
  short timeout, returns ``None`` on any network failure so the app
  boots even offline.
- :func:`check_for_update` — compares the local ``artists.meta.json``
  sidecar against the remote manifest and returns a status dict the
  Settings modal can render.
- :func:`download_corpus` — streams the remote file into a ``.part``
  temp, verifies sha256, atomically renames on success, and writes the
  meta sidecar.

All network calls use stdlib ``urllib`` — no new dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("rag.distribution")

DEFAULT_MANIFEST_URL = (
    "https://storage.googleapis.com/spotivibe-rag-corpus/manifest.json"
)
# The AI blocklist has its own manifest so either artifact can be republished
# without the other. Same bucket, separate object, separate publisher job.
DEFAULT_BLOCKLIST_MANIFEST_URL = (
    "https://storage.googleapis.com/spotivibe-rag-corpus/ai_blocklist_manifest.json"
)
_NETWORK_TIMEOUT = 5.0  # seconds; short so startup is never blocked for long


@dataclass(frozen=True)
class RemoteManifest:
    corpus_version: str
    built_at: str
    sha256: str
    size_bytes: int
    corpus_url: str
    # Legacy AI-blocklist fields. The blocklist moved to its own manifest in
    # Aug-2026; these are kept only so a client pointed at a bucket published
    # before the split still finds one (see BlocklistManifest.from_corpus).
    ai_blocklist_url: str = ""
    ai_blocklist_sha256: str = ""
    ai_blocklist_version: str = ""
    ai_blocklist_count: int = 0

    @classmethod
    def from_json(cls, payload: dict) -> "RemoteManifest":
        return cls(
            corpus_version=str(payload.get("corpus_version") or ""),
            built_at=str(payload.get("built_at") or ""),
            sha256=str(payload.get("sha256") or "").lower(),
            size_bytes=int(payload.get("size_bytes") or 0),
            corpus_url=str(payload.get("corpus_url") or ""),
            ai_blocklist_url=str(payload.get("ai_blocklist_url") or ""),
            ai_blocklist_sha256=str(payload.get("ai_blocklist_sha256") or "").lower(),
            ai_blocklist_version=str(payload.get("ai_blocklist_version") or ""),
            ai_blocklist_count=int(payload.get("ai_blocklist_count") or 0),
        )

    def is_valid(self) -> bool:
        return bool(self.corpus_version and self.sha256 and self.corpus_url)

    def has_ai_blocklist(self) -> bool:
        return bool(self.ai_blocklist_url and self.ai_blocklist_sha256)


@dataclass(frozen=True)
class BlocklistManifest:
    """Manifest for the AI-artist blocklist, independent of the corpus.

    Validity deliberately does NOT require any corpus field — that coupling was
    the reason a blocklist download was impossible whenever the corpus manifest
    was missing or malformed.
    """
    blocklist_version: str
    built_at: str
    sha256: str
    size_bytes: int
    count: int
    blocklist_url: str
    source: str = ""

    @classmethod
    def from_json(cls, payload: dict) -> "BlocklistManifest":
        return cls(
            blocklist_version=str(payload.get("blocklist_version") or ""),
            built_at=str(payload.get("built_at") or ""),
            sha256=str(payload.get("sha256") or "").lower(),
            size_bytes=int(payload.get("size_bytes") or 0),
            count=int(payload.get("count") or 0),
            blocklist_url=str(payload.get("blocklist_url") or ""),
            source=str(payload.get("source") or ""),
        )

    @classmethod
    def from_corpus(cls, manifest: RemoteManifest) -> "BlocklistManifest | None":
        """Adapt a pre-split corpus manifest's ``ai_blocklist_*`` fields."""
        if not manifest.has_ai_blocklist():
            return None
        return cls(
            blocklist_version=manifest.ai_blocklist_version,
            built_at=manifest.built_at,
            sha256=manifest.ai_blocklist_sha256,
            size_bytes=0,
            count=manifest.ai_blocklist_count,
            blocklist_url=manifest.ai_blocklist_url,
            source="legacy corpus manifest",
        )

    def is_valid(self) -> bool:
        return bool(self.blocklist_url and self.sha256)


def _fetch_manifest_json(url: str, timeout: float) -> dict | None:
    """Best-effort fetch of a tiny JSON document. ``None`` on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(64 * 1024)  # manifests are tiny; cap defensively
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.info("Manifest fetch skipped (%s): %s", url, exc)
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Manifest not valid JSON (%s): %s", url, exc)
        return None


def fetch_remote_manifest(url: str = DEFAULT_MANIFEST_URL,
                          timeout: float = _NETWORK_TIMEOUT) -> RemoteManifest | None:
    """Best-effort corpus manifest fetch. Returns ``None`` on any failure.

    Never raises — callers can use the result unconditionally.
    """
    data = _fetch_manifest_json(url, timeout)
    if data is None:
        return None
    manifest = RemoteManifest.from_json(data)
    if not manifest.is_valid():
        logger.warning("RAG manifest missing required fields: %s", data)
        return None
    return manifest


def resolve_blocklist_manifest(
        url: str = DEFAULT_BLOCKLIST_MANIFEST_URL,
        timeout: float = _NETWORK_TIMEOUT,
        corpus_manifest_url: str = DEFAULT_MANIFEST_URL,
) -> "tuple[BlocklistManifest | None, str]":
    """Resolve the blocklist manifest, reporting *why* when there isn't one.

    Returns ``(manifest, reason)`` where reason is ``"ok"``, ``"unpublished"``
    (a manifest was reachable but names no blocklist) or ``"offline"`` (nothing
    was reachable). The distinction matters to the caller: one is "try again
    later", the other is "nothing has been published yet".

    Falls back to the corpus manifest's legacy ``ai_blocklist_*`` fields so a
    client pointed at a bucket predating the Aug-2026 split still works.
    """
    reached = False

    data = _fetch_manifest_json(url, timeout)
    if data is not None:
        reached = True
        manifest = BlocklistManifest.from_json(data)
        if manifest.is_valid():
            return manifest, "ok"
        logger.warning("Blocklist manifest missing required fields: %s", data)

    corpus_data = _fetch_manifest_json(corpus_manifest_url, timeout)
    if corpus_data is not None:
        reached = True
        corpus = RemoteManifest.from_json(corpus_data)
        if corpus.is_valid():
            legacy = BlocklistManifest.from_corpus(corpus)
            if legacy is not None:
                logger.info("Using legacy blocklist fields from the corpus manifest.")
                return legacy, "ok"

    return None, ("unpublished" if reached else "offline")


def fetch_blocklist_manifest(
        url: str = DEFAULT_BLOCKLIST_MANIFEST_URL,
        timeout: float = _NETWORK_TIMEOUT,
        corpus_manifest_url: str = DEFAULT_MANIFEST_URL,
) -> BlocklistManifest | None:
    """Best-effort blocklist manifest fetch. ``None`` when there isn't one."""
    return resolve_blocklist_manifest(url, timeout, corpus_manifest_url)[0]


def read_local_meta(meta_path: Path) -> dict | None:
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Local RAG meta unreadable (%s): %s", meta_path, exc)
        return None


def write_local_meta(meta_path: Path, manifest: RemoteManifest) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({
            "corpus_version": manifest.corpus_version,
            "built_at": manifest.built_at,
            "sha256": manifest.sha256,
            "size_bytes": manifest.size_bytes,
        }, indent=2),
        encoding="utf-8",
    )


def check_for_update(corpus_path: Path,
                     meta_path: Path,
                     manifest_url: str = DEFAULT_MANIFEST_URL) -> dict:
    """Compare local installed corpus version with the remote manifest.

    Returns a dict shaped for the frontend:

    - ``{"status": "offline"}`` — manifest fetch failed (no network,
      404, etc.). Caller should treat the installed corpus as current.
    - ``{"status": "missing_corpus", "remote": {...}}`` — no corpus
      installed yet; offer a first-time download.
    - ``{"status": "current", "remote": {...}}`` — installed version
      matches remote.
    - ``{"status": "update_available", "local_version": "…",
      "remote": {...}}`` — offer an update.
    """
    remote = fetch_remote_manifest(manifest_url)
    if remote is None:
        return {"status": "offline"}

    remote_dict = {
        "corpus_version": remote.corpus_version,
        "built_at": remote.built_at,
        "size_bytes": remote.size_bytes,
    }

    if not corpus_path.exists():
        return {"status": "missing_corpus", "remote": remote_dict}

    local = read_local_meta(meta_path) or {}
    local_version = local.get("corpus_version") or ""
    if local_version == remote.corpus_version:
        return {"status": "current", "remote": remote_dict}

    return {
        "status": "update_available",
        "local_version": local_version,
        "remote": remote_dict,
    }


def download_corpus(manifest: RemoteManifest,
                    corpus_path: Path,
                    meta_path: Path,
                    timeout: float = 60.0) -> None:
    """Download ``manifest.corpus_url`` into ``corpus_path``.

    Streams into ``corpus_path.with_suffix('.part')``, hashes as it
    writes, raises ``ValueError`` on sha mismatch (and deletes the
    partial file), otherwise atomically renames into place and writes
    the meta sidecar.
    """
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    part = corpus_path.with_name(corpus_path.name + ".part")
    if part.exists():
        part.unlink()

    hasher = hashlib.sha256()
    size = 0
    logger.info("Downloading RAG corpus from %s", manifest.corpus_url)
    with urllib.request.urlopen(manifest.corpus_url, timeout=timeout) as resp, \
         open(part, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            fh.write(chunk)
            hasher.update(chunk)
            size += len(chunk)

    actual = hasher.hexdigest()
    if actual.lower() != manifest.sha256.lower():
        part.unlink(missing_ok=True)
        raise ValueError(
            f"sha256 mismatch: expected {manifest.sha256}, got {actual}")

    os.replace(part, corpus_path)
    write_local_meta(meta_path, manifest)
    logger.info("RAG corpus installed (%d bytes, version %s)",
                size, manifest.corpus_version)


def write_blocklist_meta(meta_path: Path, manifest: BlocklistManifest) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({
            "blocklist_version": manifest.blocklist_version,
            "built_at": manifest.built_at,
            "sha256": manifest.sha256,
            "count": manifest.count,
        }, indent=2),
        encoding="utf-8",
    )


def installed_blocklist_version(blocklist_path: Path,
                                meta_path: Path) -> str:
    """Best-effort version of the installed blocklist, ``""`` if unknown.

    Prefers the meta sidecar, then the ``version`` field inside the artifact
    itself — a blocklist installed before the sidecar existed still reports a
    version instead of looking perpetually out of date.
    """
    local = read_local_meta(meta_path) or {}
    version = str(local.get("blocklist_version") or "")
    if version:
        return version
    try:
        payload = json.loads(blocklist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("version") or "") if isinstance(payload, dict) else ""


def check_blocklist_update(
        blocklist_path: Path,
        meta_path: Path,
        manifest_url: str = DEFAULT_BLOCKLIST_MANIFEST_URL) -> dict:
    """Compare the installed blocklist with the published one.

    Mirrors ``check_for_update``: ``offline`` / ``unpublished`` /
    ``missing_blocklist`` / ``current`` / ``update_available``.
    """
    remote, reason = resolve_blocklist_manifest(manifest_url)
    if remote is None:
        return {"status": reason}

    remote_dict = {
        "blocklist_version": remote.blocklist_version,
        "built_at": remote.built_at,
        "count": remote.count,
    }
    if not blocklist_path.exists():
        return {"status": "missing_blocklist", "remote": remote_dict}

    local_version = installed_blocklist_version(blocklist_path, meta_path)
    if local_version and local_version == remote.blocklist_version:
        return {"status": "current", "remote": remote_dict}
    return {
        "status": "update_available",
        "local_version": local_version,
        "remote": remote_dict,
    }


def download_blocklist(manifest: BlocklistManifest,
                       dest_path: Path,
                       meta_path: Path | None = None,
                       timeout: float = 60.0) -> int:
    """Download the AI-artist blocklist named in *manifest* into *dest_path*.

    Streams ``blocklist_url`` into a ``.part`` temp, verifies sha256, raises
    ``ValueError`` on mismatch, otherwise atomically renames into place and
    (when given) writes the meta sidecar. Raises ``RuntimeError`` on an invalid
    manifest. Returns the manifest's artist count.
    """
    if not manifest.is_valid():
        raise RuntimeError("blocklist manifest is incomplete")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part = dest_path.with_name(dest_path.name + ".part")
    if part.exists():
        part.unlink()

    hasher = hashlib.sha256()
    logger.info("Downloading AI blocklist from %s", manifest.blocklist_url)
    with urllib.request.urlopen(manifest.blocklist_url, timeout=timeout) as resp, \
         open(part, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            fh.write(chunk)
            hasher.update(chunk)

    if hasher.hexdigest().lower() != manifest.sha256.lower():
        part.unlink(missing_ok=True)
        raise ValueError(
            f"sha256 mismatch: expected {manifest.sha256}, "
            f"got {hasher.hexdigest()}")

    os.replace(part, dest_path)
    if meta_path is not None:
        write_blocklist_meta(meta_path, manifest)
    logger.info("AI blocklist installed (version %s, %d artists)",
                manifest.blocklist_version, manifest.count)
    return manifest.count
