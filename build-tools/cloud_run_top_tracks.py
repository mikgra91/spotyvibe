"""Cloud Run Job entry point for the separate top-tracks enricher.

Pulls the published corpus from GCS, runs ``enrich_top_tracks.py`` over
it with a resumable checkpoint mirrored back to GCS, then uploads the
enriched corpus + an updated manifest. Designed to run on a different
schedule (and a different rate-limit budget) than the MB builder.

Env vars:
    GCS_BUCKET                  — bucket with the published corpus + manifest.
    SPOTIFY_CLIENT_ID           — required (else exit 2).
    SPOTIFY_CLIENT_SECRET       — required (else exit 2).
    TOP_TRACKS_PER_ARTIST       — default 5.
    TOP_TRACKS_LIMIT            — optional cap on artists to enrich.
    TOP_TRACKS_MIN_POPULARITY   — float 0..100, skip below.
    FORCE_REBUILD               — "1" ignores halt.flag (manual triggers).
    DISABLE_TOP_TRACKS          — "1" exits 0 without work (kill-switch).

Exit codes mirror ``cloud_run_publish.py``:
    0   — success or intentional skip
    1   — failure
    42  — Spotify rate-limited; halt.flag written, requires manual reset.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google.cloud import storage  # type: ignore
from google.cloud.exceptions import NotFound  # type: ignore

CORPUS_BLOB = "artists.jsonl.gz"
MANIFEST_BLOB = "manifest.json"
HALT_FLAG_BLOB = "halt.flag"
CHECKPOINT_BLOB = "top-tracks-checkpoint.json"

RATE_LIMIT_EXIT_CODE = 42


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _halt_flag_active(bucket) -> dict | None:
    blob = bucket.blob(HALT_FLAG_BLOB)
    try:
        body = blob.download_as_text()
    except NotFound:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"reason": "unparseable", "raw": body[:200]}


def _set_halt_flag(bucket, reason: str, detail: str) -> None:
    payload = {
        "halted_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
        "reason": reason,
        "detail": detail,
        "resume_with": f"gcloud storage rm gs://{bucket.name}/{HALT_FLAG_BLOB}",
    }
    blob = bucket.blob(HALT_FLAG_BLOB)
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(json.dumps(payload, indent=2),
                            content_type="application/json")
    print(f"⚠ Wrote HARD halt flag: {payload}", flush=True)


def main() -> int:
    if os.environ.get("DISABLE_TOP_TRACKS") == "1":
        print("DISABLE_TOP_TRACKS=1 — exiting without work.", flush=True)
        return 0

    bucket_name = os.environ["GCS_BUCKET"]
    sp_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    sp_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not sp_id or not sp_secret:
        print("ERROR: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET unset.",
              file=sys.stderr, flush=True)
        return 2

    force = os.environ.get("FORCE_REBUILD") == "1"
    top_n = os.environ.get("TOP_TRACKS_PER_ARTIST", "5")
    limit = os.environ.get("TOP_TRACKS_LIMIT", "").strip()
    min_pop = os.environ.get("TOP_TRACKS_MIN_POPULARITY", "").strip()

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    if not force:
        halt = _halt_flag_active(bucket)
        if halt is not None:
            print("⏸ halt.flag is set — skipping run. Details:", flush=True)
            print(json.dumps(halt, indent=2), flush=True)
            return 0

    with tempfile.TemporaryDirectory(prefix="rag-enrich-") as tmpdir:
        tmp = Path(tmpdir)
        corpus_in = tmp / "artists.in.jsonl.gz"
        corpus_out = tmp / "artists.out.jsonl.gz"
        checkpoint = tmp / "top-tracks-checkpoint.json"

        print(f"Downloading gs://{bucket_name}/{CORPUS_BLOB} -> {corpus_in}",
              flush=True)
        bucket.blob(CORPUS_BLOB).download_to_filename(str(corpus_in))

        # Pull prior checkpoint if present.
        cp_blob = bucket.blob(CHECKPOINT_BLOB)
        try:
            cp_blob.download_to_filename(str(checkpoint))
            print(f"Restored prior checkpoint ({checkpoint.stat().st_size:,} bytes)",
                  flush=True)
        except NotFound:
            print("No prior checkpoint — starting fresh.", flush=True)

        cmd = [
            sys.executable, "build-tools/enrich_top_tracks.py",
            "--input", str(corpus_in),
            "--output", str(corpus_out),
            "--top-tracks-per-artist", top_n,
            "--checkpoint", str(checkpoint),
            "--checkpoint-gcs-uri", f"gs://{bucket_name}/{CHECKPOINT_BLOB}",
        ]
        if limit:
            cmd += ["--limit", limit]
        if min_pop:
            cmd += ["--min-popularity", min_pop]
        print(f"$ {' '.join(cmd)}", flush=True)
        rc = subprocess.run(cmd, check=False).returncode

        if rc == RATE_LIMIT_EXIT_CODE:
            _set_halt_flag(
                bucket,
                reason="spotify_rate_limited",
                detail=("enrich_top_tracks.py exited 42. Checkpoint mirrored to "
                        f"gs://{bucket_name}/{CHECKPOINT_BLOB}. Wait 24h+, "
                        "investigate, then delete halt.flag to resume."),
            )
            print("ABORT: Spotify rate-limit. Halt flag set.", file=sys.stderr,
                  flush=True)
            return 1
        if rc != 0:
            print(f"ERROR: enrich_top_tracks.py exit {rc}", file=sys.stderr,
                  flush=True)
            return 1

        if not corpus_out.exists():
            print("ERROR: no output produced", file=sys.stderr, flush=True)
            return 1

        sha = _sha256(corpus_out)
        size = corpus_out.stat().st_size
        print(f"Uploading enriched corpus ({size:,} bytes, sha={sha[:12]}…) "
              f"-> gs://{bucket_name}/{CORPUS_BLOB}", flush=True)
        cblob = bucket.blob(CORPUS_BLOB)
        cblob.cache_control = "public, max-age=86400"
        cblob.upload_from_filename(str(corpus_out))

        # Refresh manifest (preserve prior fields, bump corpus_version + sha).
        manifest: dict = {}
        try:
            manifest = json.loads(
                bucket.blob(MANIFEST_BLOB).download_as_text())
        except (NotFound, json.JSONDecodeError):
            pass
        manifest.update({
            "corpus_version": datetime.datetime.now(datetime.timezone.utc)
                                       .strftime("%Y-%m-%d"),
            "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            "sha256": sha,
            "size_bytes": size,
            "source": "cloud-run-top-tracks-enricher",
        })
        mblob = bucket.blob(MANIFEST_BLOB)
        mblob.cache_control = "public, max-age=300"
        mblob.upload_from_string(json.dumps(manifest, indent=2),
                                 content_type="application/json")

        print(f"OK: enriched corpus published ({sha[:12]}…)", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
