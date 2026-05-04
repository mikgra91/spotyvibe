"""Cloud Run Job entry point: refresh the RAG corpus and upload to GCS.

Reads its configuration from env vars set in the Job spec:
    GCS_BUCKET                  — destination bucket (e.g. "spotivibe-rag-corpus")
    CORPUS_TOP_N                — top-N artists to include (default 500000)
    KEEP_INTERMEDIATES          — "1" to retain MB dumps between runs (default off)
    SPOTIFY_CLIENT_ID           — (optional) enables Phase 2 Spotify enrichment
    SPOTIFY_CLIENT_SECRET       — (optional) enables Phase 2 Spotify enrichment
    DISABLE_SPOTIFY_ENRICHMENT  — "1" to force-skip enrichment even if creds set
    SPOTIFY_MAX_ENRICH          — (optional) cap on Spotify lookups (default: script's 50000)
    LASTFM_API_KEY              — (optional) enables Phase B Last.fm enrichment
    DISABLE_LASTFM_ENRICHMENT   — "1" to force-skip Last.fm even if key set
    LASTFM_MAX_ENRICH           — (optional) cap on Last.fm lookups (default: script's 170000)
    MIN_REBUILD_DAYS            — skip the run if a build was published within
                                  this many days (default 6). Set to 0 to force.
    FORCE_REBUILD               — "1" to ignore both the halt flag and the
                                  recent-build skip. Used for manual triggers.

Circuit breaker:
    The job consults ``gs://$GCS_BUCKET/halt.flag`` at startup.

    Two flavours of halt:
      - **Hard halt** (no ``expires_at`` field): set by the rate-limit
        catcher when ``enrich_with_spotify.py`` exits with code 42.
        Requires the user to delete the flag manually before scheduled
        runs resume:

            gcloud storage rm gs://$GCS_BUCKET/halt.flag

      - **Soft halt** (with ``expires_at`` ISO-8601 UTC timestamp):
        seeded externally to wait out a known temp-ban window. The job
        auto-deletes the flag once the timestamp is in the past, then
        proceeds normally on that same run. No human in the loop.

Pipeline (when not halted / not recently built):
    1. Run refresh_rag_corpus.py (downloads MB dump + invokes build_rag_corpus.py).
    2. Run enrich_with_spotify.py to attach Spotify metadata (optional).
    3. Compute sha256 of the resulting artists.jsonl.gz.
    4. Upload artists.jsonl.gz to gs://$GCS_BUCKET/artists.jsonl.gz.
    5. Write + upload manifest.json with corpus_url, sha256, size, build timestamp.
    6. Wipe the working directory.

Exit non-zero on any unexpected failure so Cloud Run logs the run as failed.
Exit zero when intentionally skipping (halt flag set, recent build).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from google.cloud import storage  # type: ignore
from google.cloud.exceptions import NotFound  # type: ignore

ROOT = Path(__file__).resolve().parent.parent  # repo root inside the container
CORPUS_PATH = ROOT / "data" / "rag_corpus" / "artists.jsonl.gz"
MANIFEST_PATH = ROOT / "data" / "rag_corpus" / "manifest.json"
WORK_DIR = ROOT / "build-tools" / ".rag-cache"

# Must match enrich_with_spotify.RATE_LIMIT_EXIT_CODE.
RATE_LIMIT_EXIT_CODE = 42
# Must match enrich_with_lastfm.{RATE_LIMIT,AUTH_ERROR}_EXIT_CODE.
LASTFM_RATE_LIMIT_EXIT_CODE = 43
LASTFM_AUTH_ERROR_EXIT_CODE = 44

HALT_FLAG_BLOB = "halt.flag"
MANIFEST_BLOB = "manifest.json"


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def _run_allow_exit_codes(cmd: list[str], allowed: set[int]) -> int:
    """Run *cmd*; return its exit code. Raise if it's neither 0 nor in *allowed*."""
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0 and proc.returncode not in allowed:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return proc.returncode


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Circuit breaker (GCS halt.flag) ──────────────────────────────────

def _halt_flag_active(bucket) -> dict | None:
    """Return halt-flag content if the breaker is currently OPEN.

    The halt flag may carry an optional ``expires_at`` ISO-8601 UTC
    timestamp:

    - **No expires_at**: hard halt. Always considered active. Set by
      the rate-limit catcher (see ``_set_halt_flag``). Requires the
      user to delete the flag manually before the job resumes — this
      is intentional: an unexpected rate-limit means something is
      structurally wrong (creds, throttle config, Spotify policy
      change) and silently retrying could trigger another multi-hour
      temp-ban.

    - **expires_at in the future**: soft halt with known expiry.
      Active. The job exits cleanly, leaving the flag in place.

    - **expires_at in the past**: stale soft halt. The flag is
      deleted and the job proceeds — this is how the system
      auto-resumes after a known temp-ban window.

    Returns the parsed dict if the breaker is active, else None.
    """
    blob = bucket.blob(HALT_FLAG_BLOB)
    try:
        body = blob.download_as_text()
    except NotFound:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # Corrupt flag — treat as hard halt; safer than running.
        return {"reason": "unparseable", "raw": body[:200]}

    expires_at_str = (data.get("expires_at") or "").strip()
    if not expires_at_str:
        # Hard halt — manual reset required.
        return data

    expires_at = _parse_iso_utc(expires_at_str)
    if expires_at is None:
        # Bad timestamp — be conservative, treat as active.
        return {**data, "_warning": f"unparseable expires_at: {expires_at_str!r}"}

    now = datetime.datetime.now(datetime.timezone.utc)
    if now < expires_at:
        return data  # still within the wait window

    # Expiry has passed — auto-clear the flag and proceed.
    try:
        blob.delete()
        print(
            f"♻ halt.flag expired at {expires_at_str} — deleted, resuming.",
            flush=True,
        )
    except Exception as exc:  # pragma: no cover — defensive
        print(f"WARNING: could not delete expired halt.flag: {exc}", flush=True)
    return None


def _parse_iso_utc(s: str) -> datetime.datetime | None:
    """Parse an ISO-8601 timestamp; assume UTC if no tz info. Return None on failure."""
    s = s.strip().rstrip("Z")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _set_halt_flag(bucket, reason: str, detail: str = "") -> None:
    """Write a HARD halt flag (no auto-expiry) — manual reset required.

    Used by the rate-limit catcher. Auto-expiring flags are only
    created externally (e.g. when seeding a known temp-ban window).
    """
    payload = {
        "halted_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
        "reason": reason,
        "detail": detail,
        "resume_with": (
            "gcloud storage rm gs://"
            + bucket.name + "/" + HALT_FLAG_BLOB
        ),
    }
    blob = bucket.blob(HALT_FLAG_BLOB)
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(json.dumps(payload, indent=2),
                            content_type="application/json")
    print(f"⚠ Wrote HARD halt flag (manual reset required): {payload}", flush=True)


def _recent_build_within_days(bucket, days: int) -> bool:
    """True if the published manifest's built_at is younger than *days* days."""
    if days <= 0:
        return False
    blob = bucket.blob(MANIFEST_BLOB)
    try:
        body = blob.download_as_text()
    except NotFound:
        return False
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    built_at_str = (data.get("built_at") or "").rstrip("Z")
    if not built_at_str:
        return False
    try:
        built_at = datetime.datetime.fromisoformat(built_at_str)
    except ValueError:
        return False
    if built_at.tzinfo is None:
        built_at = built_at.replace(tzinfo=datetime.timezone.utc)
    age = datetime.datetime.now(datetime.timezone.utc) - built_at
    return age.total_seconds() < days * 86400


def main() -> int:
    bucket_name = os.environ["GCS_BUCKET"]
    top_n = os.environ.get("CORPUS_TOP_N", "500000")
    force = os.environ.get("FORCE_REBUILD") == "1"
    min_rebuild_days = int(os.environ.get("MIN_REBUILD_DAYS", "6"))

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # 0a. Circuit-breaker check.
    if not force:
        halt = _halt_flag_active(bucket)
        if halt is not None:
            print("⏸ Halt flag is set — skipping run. Details:", flush=True)
            print(json.dumps(halt, indent=2), flush=True)
            print(f"To resume early: gcloud storage rm gs://{bucket_name}/{HALT_FLAG_BLOB}",
                  flush=True)
            return 0

    # 0b. Skip if a recent successful build already exists.
    if not force and _recent_build_within_days(bucket, min_rebuild_days):
        print(f"⏭ A successful build is < {min_rebuild_days} days old — skipping.",
              flush=True)
        return 0

    # 1. Build the corpus.
    cleanup_flag = [] if os.environ.get("KEEP_INTERMEDIATES") == "1" else ["--cleanup"]
    _run([
        sys.executable, "build-tools/refresh_rag_corpus.py",
        "--top-n", top_n,
        *cleanup_flag,
    ])

    if not CORPUS_PATH.exists():
        print(f"ERROR: corpus not produced at {CORPUS_PATH}", file=sys.stderr)
        return 1

    # 2. Optional: enrich with Spotify metadata. If creds missing or
    #    DISABLE_SPOTIFY_ENRICHMENT=1, skip silently — the unenriched
    #    corpus still works for retrieval.
    sp_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    sp_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    skip_enrichment = os.environ.get("DISABLE_SPOTIFY_ENRICHMENT") == "1"
    if sp_id and sp_secret and not skip_enrichment:
        enriched_path = CORPUS_PATH.with_name("artists.enriched.jsonl.gz")
        print("Phase 2: enriching corpus with Spotify metadata …", flush=True)
        spotify_max = os.environ.get("SPOTIFY_MAX_ENRICH", "").strip()
        rc = _run_allow_exit_codes(
            [
                sys.executable, "build-tools/enrich_with_spotify.py",
                "--input", str(CORPUS_PATH),
                "--output", str(enriched_path),
                *(["--max-enrich", spotify_max] if spotify_max else []),
            ],
            allowed={RATE_LIMIT_EXIT_CODE},
        )
        if rc == RATE_LIMIT_EXIT_CODE:
            # Open the circuit and FAIL the run. Do NOT upload anything —
            # the existing GCS corpus stays intact for users.
            _set_halt_flag(
                bucket,
                reason="spotify_rate_limited",
                detail=("enrich_with_spotify.py exited 42 (rate-limited). "
                        "Wait 24h+, investigate, then delete halt.flag to resume."),
            )
            print("ABORT: Spotify rate-limit detected. Halt flag set, no upload.",
                  file=sys.stderr, flush=True)
            return 1
        if enriched_path.exists():
            enriched_path.replace(CORPUS_PATH)
            print(f"Enriched corpus replaces {CORPUS_PATH}", flush=True)
        else:
            print("WARNING: enrichment produced no output — keeping MB-only corpus",
                  flush=True)
    else:
        if skip_enrichment:
            print("Spotify enrichment disabled by DISABLE_SPOTIFY_ENRICHMENT=1", flush=True)
        else:
            print("Spotify creds not set — skipping Phase 2 enrichment", flush=True)

    # 2b. Phase B: enrich with Last.fm metadata. The driver itself
    # passes through unchanged when LASTFM_API_KEY is not set or
    # DISABLE_LASTFM_ENRICHMENT=1, so it is safe to invoke unconditionally
    # — but we still wire the rate-limit (43) and auth-error (44) exits
    # back to the circuit breaker.
    lastfm_path = CORPUS_PATH.with_name("artists.lastfm.jsonl.gz")
    print("Phase B: enriching corpus with Last.fm metadata …", flush=True)
    lastfm_max = os.environ.get("LASTFM_MAX_ENRICH", "").strip()
    rc = _run_allow_exit_codes(
        [
            sys.executable, "build-tools/enrich_with_lastfm.py",
            "--input", str(CORPUS_PATH),
            "--output", str(lastfm_path),
            *(["--max-enrich", lastfm_max] if lastfm_max else []),
        ],
        allowed={LASTFM_RATE_LIMIT_EXIT_CODE, LASTFM_AUTH_ERROR_EXIT_CODE},
    )
    if rc == LASTFM_RATE_LIMIT_EXIT_CODE:
        _set_halt_flag(
            bucket,
            reason="lastfm_rate_limited",
            detail=("enrich_with_lastfm.py exited 43 (rate-limited). "
                    "Wait, investigate, then delete halt.flag to resume."),
        )
        print("ABORT: Last.fm rate-limit detected. Halt flag set, no upload.",
              file=sys.stderr, flush=True)
        return 1
    if rc == LASTFM_AUTH_ERROR_EXIT_CODE:
        # Auth error = bad key. Fail loudly but DO NOT set the halt flag —
        # the user can rotate the secret without needing to clear a flag.
        print("ABORT: Last.fm API key invalid/suspended. Fix LASTFM_API_KEY secret.",
              file=sys.stderr, flush=True)
        return 1
    if lastfm_path.exists():
        lastfm_path.replace(CORPUS_PATH)
        print(f"Last.fm-enriched corpus replaces {CORPUS_PATH}", flush=True)

    # 3. Compute hash + assemble manifest.
    sha = _sha256(CORPUS_PATH)
    size = CORPUS_PATH.stat().st_size
    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    corpus_url = f"https://storage.googleapis.com/{bucket_name}/artists.jsonl.gz"
    manifest = {
        "corpus_version": version,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
        "sha256": sha,
        "size_bytes": size,
        "corpus_url": corpus_url,
        "source": "cloud-run-job",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    # 4. + 5. Upload both, corpus first so manifest never points at a missing asset.
    print(f"Uploading {CORPUS_PATH} ({size:,} bytes) -> gs://{bucket_name}/artists.jsonl.gz",
          flush=True)
    blob = bucket.blob("artists.jsonl.gz")
    blob.cache_control = "public, max-age=86400"  # 1-day CDN cache
    blob.upload_from_filename(str(CORPUS_PATH))

    print(f"Uploading manifest -> gs://{bucket_name}/manifest.json", flush=True)
    mblob = bucket.blob("manifest.json")
    mblob.cache_control = "public, max-age=300"  # 5-min cache
    mblob.upload_from_filename(str(MANIFEST_PATH))

    # 6. Wipe the work dir.
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print(f"OK: published version {version} ({sha[:12]}...)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

