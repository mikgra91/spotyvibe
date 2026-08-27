"""Cloud Run Job entry point: publish the AI-generated-artist blocklist to GCS.

Deliberately independent of cloud_run_publish.py. The blocklist and the RAG
corpus are unrelated artifacts on unrelated cadences — upstream curates AI
artists continuously, while a corpus rebuild is a multi-day, 37-batch cycle.
Bundling them (the pre-Aug-2026 design) meant the blocklist could only ship as
a side effect of a completed corpus cycle, and one transient CSV fetch failure
during that cycle silently stripped the blocklist fields from the published
manifest.

Publishes two blobs:
    ai_artists.<sha12>.json      — content-addressed, immutable, long cache
    ai_blocklist_manifest.json   — small, short cache, names the current artifact

The artifact URL is content-addressed so a client can never pair a fresh
manifest with a CDN-cached stale body — that combination would surface as a
bogus ``checksum_failed`` to the user.

Failures are LOUD (non-zero exit). Publishing the blocklist is this job's only
purpose, so a best-effort skip would be indistinguishable from success.

Env vars (Job spec):
    GCS_BUCKET           — destination bucket (e.g. "spotivibe-rag-corpus"). Required.
    AI_BLOCKLIST_CSV_URL — upstream CSV override (default: CennoxX/spotify-ai-blocker)
    FORCE_PUBLISH        — "1" re-uploads even when content is unchanged and
                           bypasses the shrink guard. For manual recovery.
    MIN_COUNT            — absolute floor on usable ids (default 1000)
    MIN_COUNT_RATIO      — reject a CSV holding less than this fraction of the
                           currently published count (default 0.5). Stops an
                           upstream format break from silently disabling the
                           filter for every client.
    KEEP_VERSIONS        — content-addressed artifacts to retain (default 5).
                           0 disables pruning.
    DRY_RUN              — "1" does everything except touch GCS.

Exit codes:
    0  published, or content unchanged (no-op), or dry run
    1  upstream CSV unreachable / unusable / failed a safety guard
    2  GCS read or write failure
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

AI_BLOCKLIST_CSV_URL = os.environ.get(
    "AI_BLOCKLIST_CSV_URL",
    "https://raw.githubusercontent.com/CennoxX/spotify-ai-blocker/main/SpotifyAiArtists.csv",
)
UPSTREAM_CREDIT = "https://github.com/CennoxX/spotify-ai-blocker (MIT)"

MANIFEST_BLOB = "ai_blocklist_manifest.json"
ARTIFACT_PREFIX = "ai_artists."
ARTIFACT_SUFFIX = ".json"

# Spotify artist IDs are 22-char base62. Anything else is a parse artefact
# (stray header row, quoted field, BOM) and must not enter the deny set.
_SPOTIFY_ID_RE = re.compile(r"[0-9A-Za-z]{22}")

_CSV_TIMEOUT = 30.0
_USER_AGENT = "spotyvibe-blocklist-publisher/1.0 (+https://github.com/mikgra91/spotyvibe)"

EXIT_OK = 0
EXIT_UPSTREAM = 1
EXIT_GCS = 2


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"


def _artifact_blob_name(sha: str) -> str:
    return f"{ARTIFACT_PREFIX}{sha[:12]}{ARTIFACT_SUFFIX}"


# ── Upstream ─────────────────────────────────────────────────────────

def fetch_artist_ids(url: str = AI_BLOCKLIST_CSV_URL) -> list[str]:
    """Fetch the upstream CSV and return deduped, validated Spotify artist IDs.

    Order is preserved so a re-publish of unchanged upstream data hashes
    identically and short-circuits as a no-op.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_CSV_TIMEOUT) as resp:
        text = resp.read().decode("utf-8-sig")

    ids: list[str] = []
    seen: set[str] = set()
    malformed = 0
    for row in csv.DictReader(io.StringIO(text)):
        aid = (row.get("id") or "").strip()
        if not aid:
            continue
        if not _SPOTIFY_ID_RE.fullmatch(aid):
            malformed += 1
            continue
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)
    if malformed:
        print(f"  note: skipped {malformed} malformed id(s)", flush=True)
    return ids


def build_payload(ids: list[str], version: str) -> bytes:
    """Serialise the deny set. Byte-stable for identical input."""
    payload = {
        "version": version,
        "source": UPSTREAM_CREDIT,
        "count": len(ids),
        "artist_ids": ids,
    }
    return json.dumps(payload).encode("utf-8")


# ── GCS ──────────────────────────────────────────────────────────────

def _bucket(bucket_name: str):
    from google.cloud import storage  # imported lazily so DRY_RUN needs no SDK
    return storage.Client().bucket(bucket_name)


def read_published_manifest(bucket) -> dict | None:
    """Return the currently published manifest, or None if absent/unparseable."""
    from google.cloud.exceptions import NotFound
    try:
        body = bucket.blob(MANIFEST_BLOB).download_as_text()
    except NotFound:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print("WARNING: published manifest is unparseable — treating as absent.",
              flush=True)
        return None


def _upload_bytes(bucket, blob_name: str, data: bytes, cache_control: str) -> None:
    blob = bucket.blob(blob_name)
    blob.cache_control = cache_control
    blob.upload_from_string(data, content_type="application/json")


def prune_old_artifacts(bucket, keep_blob: str, keep: int) -> None:
    """Delete superseded content-addressed artifacts, newest *keep* retained.

    Retention (rather than delete-all-but-current) leaves older manifests that
    clients may still be holding resolvable for a few cycles.
    """
    if keep <= 0:
        return
    blobs = [b for b in bucket.list_blobs(prefix=ARTIFACT_PREFIX)
             if b.name.endswith(ARTIFACT_SUFFIX) and b.name != keep_blob]
    blobs.sort(key=lambda b: b.time_created or datetime.datetime.min, reverse=True)
    for blob in blobs[max(keep - 1, 0):]:
        print(f"  pruning superseded artifact: {blob.name}", flush=True)
        try:
            blob.delete()
        except Exception as exc:  # pragma: no cover — pruning is never fatal
            print(f"  WARNING: prune failed for {blob.name}: {exc}", flush=True)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    force = os.environ.get("FORCE_PUBLISH") == "1"
    min_count = int(os.environ.get("MIN_COUNT", "1000"))
    min_ratio = float(os.environ.get("MIN_COUNT_RATIO", "0.5"))
    keep_versions = int(os.environ.get("KEEP_VERSIONS", "5"))

    bucket_name = os.environ.get("GCS_BUCKET")
    if not bucket_name and not dry_run:
        print("ERROR: GCS_BUCKET is required (or set DRY_RUN=1).", file=sys.stderr,
              flush=True)
        return EXIT_GCS

    print(f"Fetching AI blocklist from {AI_BLOCKLIST_CSV_URL}", flush=True)
    try:
        ids = fetch_artist_ids()
    except (urllib.error.URLError, TimeoutError, OSError,
            UnicodeDecodeError, csv.Error) as exc:
        print(f"ERROR: upstream CSV fetch/parse failed: {exc}", file=sys.stderr,
              flush=True)
        return EXIT_UPSTREAM

    count = len(ids)
    print(f"  parsed {count:,} unique artist ids", flush=True)

    if count < min_count:
        print(f"ERROR: only {count:,} usable ids (floor is {min_count:,}). "
              f"Upstream is probably broken — refusing to publish.",
              file=sys.stderr, flush=True)
        return EXIT_UPSTREAM

    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    data = build_payload(ids, version)
    sha = hashlib.sha256(data).hexdigest()
    artifact_blob = _artifact_blob_name(sha)
    print(f"  artifact {artifact_blob} ({len(data):,} bytes, sha {sha[:12]}…)",
          flush=True)

    if dry_run:
        out = Path(tempfile.gettempdir()) / artifact_blob
        out.write_bytes(data)
        print(f"DRY_RUN: wrote {out} — no GCS access. Would publish "
              f"{count:,} ids as version {version}.", flush=True)
        return EXIT_OK

    try:
        bucket = _bucket(bucket_name)
        published = read_published_manifest(bucket)
    except Exception as exc:
        print(f"ERROR: GCS read failed: {exc}", file=sys.stderr, flush=True)
        return EXIT_GCS

    if published:
        prev_count = int(published.get("count") or 0)
        if not force and prev_count and count < prev_count * min_ratio:
            print(f"ERROR: {count:,} ids is under {min_ratio:.0%} of the published "
                  f"{prev_count:,} — refusing to shrink the blocklist. Set "
                  f"FORCE_PUBLISH=1 if the drop is legitimate.",
                  file=sys.stderr, flush=True)
            return EXIT_UPSTREAM
        if not force and (published.get("sha256") or "").lower() == sha:
            print(f"Content unchanged since {published.get('blocklist_version')} "
                  f"({count:,} ids) — nothing to publish.", flush=True)
            return EXIT_OK

    manifest = {
        "blocklist_version": version,
        "built_at": _now_iso(),
        "sha256": sha,
        "size_bytes": len(data),
        "count": count,
        "blocklist_url":
            f"https://storage.googleapis.com/{bucket_name}/{artifact_blob}",
        "source": UPSTREAM_CREDIT,
        "source_url": AI_BLOCKLIST_CSV_URL,
    }

    try:
        # Artifact first: a manifest must never name a blob that isn't there yet.
        print(f"Uploading artifact → gs://{bucket_name}/{artifact_blob}", flush=True)
        _upload_bytes(bucket, artifact_blob, data,
                      "public, max-age=31536000, immutable")
        print(f"Uploading manifest → gs://{bucket_name}/{MANIFEST_BLOB}", flush=True)
        _upload_bytes(bucket, MANIFEST_BLOB,
                      json.dumps(manifest, indent=2).encode("utf-8"),
                      "public, max-age=300")
    except Exception as exc:
        print(f"ERROR: GCS write failed: {exc}", file=sys.stderr, flush=True)
        return EXIT_GCS

    prune_old_artifacts(bucket, artifact_blob, keep_versions)

    print(f"OK: published blocklist version {version} — {count:,} artist ids "
          f"({sha[:12]}…).", flush=True)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
