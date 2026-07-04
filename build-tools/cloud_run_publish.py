"""Cloud Run Job entry point: refresh the RAG corpus and upload to GCS.

This script runs as a **batched, self-chaining state machine**. One
monthly Cloud Scheduler trigger fires the first execution of a cycle;
each execution processes one ~5000-artist batch and then triggers the
next execution of itself via the Cloud Run Admin API. The cycle
finishes when every batch has run, at which point the final execution
merges all enrichment work into the published corpus + manifest.

Why batched? Last.fm enrichment of the full 175k-artist corpus takes
~29 h at the polite throttle, which does not fit in Cloud Run's
24 h task-timeout cap. Splitting into ~35 batches of 5000 artists
puts each execution at ~50 min and lets the workflow span 1-3 days
without operator intervention.

Env vars (Job spec):
    GCS_BUCKET                  — destination bucket (e.g. "spotivibe-rag-corpus")
    CORPUS_TOP_N                — top-N artists to include in Phase 1 (default 500000)
    KEEP_INTERMEDIATES          — "1" to retain MB dumps between Phase-1 runs
    SPOTIFY_CLIENT_ID           — (dormant) re-enabling needs SPOTIFY_CLIENT_SECRET too
    SPOTIFY_CLIENT_SECRET       — (dormant)
    DISABLE_SPOTIFY_ENRICHMENT  — "1" force-skip Spotify path. Default behaviour today.
    SPOTIFY_MAX_ENRICH          — (dormant) cap on Spotify lookups
    LASTFM_API_KEY              — required for the Last.fm enrichment phase
    DISABLE_LASTFM_ENRICHMENT   — "1" force-skip Last.fm (passthrough only)
    BATCH_SIZE                  — artists enriched per execution (default 5000)
    BATCH_RUN_REGION            — Cloud Run region used by the self-trigger
                                  REST call (default us-central1).
    BATCH_RUN_JOB               — Cloud Run job name used by the self-trigger
                                  REST call (default spotivibe-rag-builder).
    DISABLE_SELF_TRIGGER        — "1" disables the self-trigger entirely. Use
                                  when stepping through batches manually.
    CYCLE_TTL_DAYS              — state older than this is treated as stale
                                  and a fresh cycle is started (default 25).
    MIN_REBUILD_DAYS            — applies only at cycle START: if the
                                  published manifest is younger than this,
                                  the cycle is skipped before Phase 1 runs.
                                  Default 6. Pair with FORCE_REBUILD=1 to
                                  override for manual triggers.
    FORCE_REBUILD               — "1" ignores both halt flag and the
                                  recent-build skip. Used for manual triggers.

Circuit breaker:
    gs://$GCS_BUCKET/halt.flag (see _halt_flag_active for hard/soft semantics).
    Halt aborts the WHOLE cycle and stops self-chaining.

Cycle state:
    gs://$GCS_BUCKET/build-state.json. Single source of truth for whether
    the cycle is in progress and where the next batch should resume. Per
    cycle: cycle_id, total_artists, batch_size, next_offset, completed
    batches, and a structural_failures list for investigate-worthy errors
    (rate-limit, auth, transient-cluster).

    Per-artist failures are recorded by run_lastfm_enrichment.py via
    --failures-out and aggregated into the state file at batch end.
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
DATA_DIR = ROOT / "data" / "rag_corpus"
CORPUS_PATH = DATA_DIR / "artists.jsonl.gz"
MB_ONLY_PATH = DATA_DIR / "artists.mb-only.jsonl.gz"
MANIFEST_PATH = DATA_DIR / "manifest.json"
WORK_DIR = ROOT / "build-tools" / ".rag-cache"

# Exit-code contract with the enrichment scripts.
RATE_LIMIT_EXIT_CODE = 42                 # run_spotify_enrichment.py
LASTFM_RATE_LIMIT_EXIT_CODE = 43          # run_lastfm_enrichment.py
LASTFM_AUTH_ERROR_EXIT_CODE = 44
LASTFM_SMOKE_FAIL_EXIT_CODE = 45

# GCS blob names.
HALT_FLAG_BLOB = "halt.flag"
MANIFEST_BLOB = "manifest.json"
CORPUS_BLOB = "artists.jsonl.gz"
MB_ONLY_BLOB = "artists.mb-only.jsonl.gz"
LASTFM_CHECKPOINT_BLOB = "lastfm-checkpoint.jsonl"
STATE_BLOB = "build-state.json"
# AI controlled-vocabulary tag overlay (mbid -> {ai_tags, ai_confidence}).
# Produced locally in intervals (evaluation/enrichment_probe/enrich_ai_layer.py)
# and uploaded once; merged into every published corpus so the AI layer
# survives weekly MB/Last.fm rebuilds (carry-forward by mbid).
AI_OVERLAY_BLOB = "ai_tags_overlay.json"
# AI-generated-artist blocklist (Spotify artist IDs). Built from the
# community-maintained CSV at CennoxX/spotify-ai-blocker (MIT) and published
# alongside the corpus so clients can filter AI music via the same manifest.
AI_BLOCKLIST_BLOB = "ai_artists.json"
AI_BLOCKLIST_CSV_URL = os.environ.get(
    "AI_BLOCKLIST_CSV_URL",
    "https://raw.githubusercontent.com/CennoxX/spotify-ai-blocker/main/SpotifyAiArtists.csv",
)

DEFAULT_BATCH_SIZE = 5000


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


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"


def _build_ai_blocklist(dest: Path, version: str):
    """Fetch the upstream AI-artist CSV and write a deduped JSON ID set.

    Best-effort: returns ``None`` (caller skips blocklist publishing) when the
    upstream CSV is unreachable or empty, so a transient GitHub outage never
    blocks the weekly corpus release. Source: CennoxX/spotify-ai-blocker (MIT).

    Returns ``(count, sha256)`` on success.
    """
    import csv as _csv
    import io as _io
    import urllib.request as _urlreq
    try:
        with _urlreq.urlopen(AI_BLOCKLIST_CSV_URL, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"⚠ AI blocklist fetch skipped ({AI_BLOCKLIST_CSV_URL}): {exc}",
              flush=True)
        return None
    ids, seen = [], set()
    for row in _csv.DictReader(_io.StringIO(text)):
        aid = (row.get("id") or "").strip()
        if aid and aid not in seen:
            seen.add(aid)
            ids.append(aid)
    if not ids:
        print("⚠ AI blocklist CSV had no usable ids — skipping.", flush=True)
        return None
    payload = {
        "version": version,
        "source": "https://github.com/CennoxX/spotify-ai-blocker (MIT)",
        "count": len(ids),
        "artist_ids": ids,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload), encoding="utf-8")
    return len(ids), _sha256(dest)


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


# ── Circuit breaker (GCS halt.flag) ──────────────────────────────────

def _halt_flag_active(bucket) -> dict | None:
    """Return halt-flag content if the breaker is currently OPEN."""
    blob = bucket.blob(HALT_FLAG_BLOB)
    try:
        body = blob.download_as_text()
    except NotFound:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"reason": "unparseable", "raw": body[:200]}

    expires_at_str = (data.get("expires_at") or "").strip()
    if not expires_at_str:
        return data

    expires_at = _parse_iso_utc(expires_at_str)
    if expires_at is None:
        return {**data, "_warning": f"unparseable expires_at: {expires_at_str!r}"}
    if datetime.datetime.now(datetime.timezone.utc) < expires_at:
        return data
    try:
        blob.delete()
        print(f"♻ halt.flag expired at {expires_at_str} — deleted, resuming.",
              flush=True)
    except Exception as exc:  # pragma: no cover — defensive
        print(f"WARNING: could not delete expired halt.flag: {exc}", flush=True)
    return None


def _set_halt_flag(bucket, reason: str, detail: str = "") -> None:
    """Write a HARD halt flag (no auto-expiry) — manual reset required."""
    payload = {
        "halted_at": _now_iso(),
        "reason": reason,
        "detail": detail,
        "resume_with": f"gcloud storage rm gs://{bucket.name}/{HALT_FLAG_BLOB}",
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


# ── State file ───────────────────────────────────────────────────────

def _load_state(bucket) -> dict | None:
    blob = bucket.blob(STATE_BLOB)
    try:
        body = blob.download_as_text()
    except NotFound:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"WARNING: state file is unparseable — treating as missing.",
              flush=True)
        return None


def _save_state(bucket, state: dict) -> None:
    blob = bucket.blob(STATE_BLOB)
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(json.dumps(state, indent=2),
                            content_type="application/json")


def _delete_state(bucket) -> None:
    try:
        bucket.blob(STATE_BLOB).delete()
    except NotFound:
        pass


def _state_is_stale(state: dict, ttl_days: int) -> bool:
    started = _parse_iso_utc(state.get("started_at", ""))
    if started is None:
        return True
    age = datetime.datetime.now(datetime.timezone.utc) - started
    return age.total_seconds() > ttl_days * 86400


# ── Self-trigger via Cloud Run Admin REST API ────────────────────────

def _trigger_next_execution(project_id: str, region: str, job_name: str) -> None:
    """POST to run.googleapis.com/v2/.../jobs/{name}:run to kick the next batch.

    Uses Application Default Credentials — inside a Cloud Run Job
    container that resolves to the job's service account, which must
    hold ``roles/run.developer`` (or ``run.jobs.run``) on this job.
    """
    if os.environ.get("DISABLE_SELF_TRIGGER") == "1":
        print("⏸ DISABLE_SELF_TRIGGER=1 — not triggering next execution.",
              flush=True)
        return
    try:
        from google.auth import default as auth_default  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        import requests  # type: ignore
    except ImportError as exc:
        print(f"WARNING: self-trigger imports failed ({exc}); "
              "next batch must be kicked manually.", flush=True)
        return

    try:
        creds, _ = auth_default(scopes=[
            "https://www.googleapis.com/auth/cloud-platform"
        ])
        creds.refresh(Request())
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: ADC refresh failed ({exc}); "
              "next batch must be kicked manually.", flush=True)
        return

    url = (
        f"https://run.googleapis.com/v2/projects/{project_id}"
        f"/locations/{region}/jobs/{job_name}:run"
    )
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            json={},
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: self-trigger POST failed ({exc}); "
              "next batch must be kicked manually.", flush=True)
        return
    if 200 <= resp.status_code < 300:
        print(f"➡ Triggered next execution of {job_name} (status={resp.status_code}).",
              flush=True)
    else:
        print(f"WARNING: self-trigger returned HTTP {resp.status_code}: "
              f"{resp.text[:300]}", flush=True)


def _project_id_from_metadata() -> str:
    """Read the GCP project id from the metadata server (Cloud Run container)."""
    try:
        import requests  # type: ignore
        resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
            timeout=5,
        )
        if resp.ok:
            return resp.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()


# ── Phase helpers ────────────────────────────────────────────────────

def _run_phase1_mb_build(top_n: str, keep_intermediates: bool) -> Path:
    """Run refresh_rag_corpus.py and return the produced corpus path."""
    cleanup_flag = [] if keep_intermediates else ["--cleanup"]
    _run([
        sys.executable, "build-tools/rag/refresh_rag_corpus.py",
        "--top-n", top_n,
        *cleanup_flag,
    ])
    if not CORPUS_PATH.exists():
        raise RuntimeError(f"Phase 1 did not produce {CORPUS_PATH}")
    return CORPUS_PATH


def _seed_lastfm_checkpoint_from_previous(bucket, bucket_name: str) -> bool:
    """Carry the previous corpus's Last.fm layer forward onto the fresh MB build.

    The published corpus is layered by ``mbid``: an MB tag change does not
    change an artist's Last.fm data, so re-fetching all ~175k artists from
    Last.fm every cycle (~29 h) is wasted work. Instead we merge the
    previously-published ``artists.jsonl.gz`` against the freshly-built
    MB-only corpus (``merge_corpus.py``) and write a *seed checkpoint*
    containing every artist that already has Last.fm data — with the new
    MB fields applied. Uploaded as ``LASTFM_CHECKPOINT_BLOB``, Phase B's
    existing skip-set then skips all carried-forward artists and fetches
    only the delta (new / never-enriched mbids).

    Returns True when a seed was produced (a previous corpus existed),
    False for a first-ever build (caller falls back to a full pass).
    """
    prev_local = DATA_DIR / "previous-corpus.jsonl.gz"
    if not _download(bucket, CORPUS_BLOB, prev_local):
        print("No previously-published corpus on GCS — first build. "
              "Last.fm pass will enrich the full corpus.", flush=True)
        return False
    local_checkpoint = DATA_DIR / "lastfm-checkpoint.jsonl"
    _run([
        sys.executable, "build-tools/rag/merge_corpus.py",
        "--new-mb", str(MB_ONLY_PATH),
        "--previous", str(prev_local),
        "--seed-checkpoint", str(local_checkpoint),
    ])
    if not local_checkpoint.exists() or local_checkpoint.stat().st_size == 0:
        print("WARNING: merge produced no seed checkpoint — falling back to "
              "a full Last.fm pass.", flush=True)
        return False
    # Plain JSONL (no gzip): matches the per-execution checkpoint format
    # the enricher appends to and finalise reads.
    _upload(bucket, local_checkpoint, LASTFM_CHECKPOINT_BLOB, "private, max-age=0")
    carried = _count_rows(local_checkpoint)
    print(f"Seeded Last.fm checkpoint with {carried} carried-forward rows → "
          f"gs://{bucket_name}/{LASTFM_CHECKPOINT_BLOB}. Phase B will fetch "
          f"only new / never-enriched artists.", flush=True)
    return True


def _bake_ai_overlay(bucket, checkpoint_path: Path) -> Path:
    """Merge the AI tag overlay (if present on GCS) into the final corpus.

    The AI layer (``ai_tags`` / ``ai_confidence``) is produced locally in
    intervals (``evaluation/enrichment_probe/enrich_ai_layer.py``) and
    uploaded once as ``AI_OVERLAY_BLOB``. Baking it into the published rows
    means clients get enriched tags via the normal corpus download — no
    separate sidecar fetch — and ``merge_layers`` carries the AI fields
    forward by ``mbid`` on subsequent cycles.

    Best-effort: if no overlay is on GCS the checkpoint is published
    unchanged (existing ai_tags still survive via carry-forward from the
    previous corpus during Last.fm seeding). Re-applying the overlay here
    also lets a freshly-uploaded overlay refresh the published tags.

    Returns the path to publish — the baked file when an overlay was
    applied, otherwise the original *checkpoint_path*.
    """
    ai_local = DATA_DIR / "ai_tags_overlay.json"
    if not _download(bucket, AI_OVERLAY_BLOB, ai_local):
        print("No AI overlay on GCS — publishing without an explicit AI bake "
              "(carry-forward still preserves any existing ai_tags).",
              flush=True)
        return checkpoint_path
    baked = DATA_DIR / "artists.baked.jsonl"
    # new-mb == previous == checkpoint: MB + Last.fm fields are taken from the
    # checkpoint itself (authoritative + carried), and only the AI layer is
    # (re)applied from the overlay. merge_layers is idempotent here.
    _run([
        sys.executable, "build-tools/rag/merge_corpus.py",
        "--new-mb", str(checkpoint_path),
        "--previous", str(checkpoint_path),
        "--ai-overlay", str(ai_local),
        "--out", str(baked),
    ])
    if not baked.exists() or baked.stat().st_size == 0:
        print("WARNING: AI bake produced no output — publishing checkpoint "
              "unchanged.", flush=True)
        return checkpoint_path
    print(f"Baked AI overlay into corpus → {baked}", flush=True)
    return baked


def _upload(bucket, src: Path, blob_name: str, cache_control: str) -> None:
    blob = bucket.blob(blob_name)
    blob.cache_control = cache_control
    blob.upload_from_filename(str(src))


def _download(bucket, blob_name: str, dest: Path) -> bool:
    blob = bucket.blob(blob_name)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))
        return True
    except NotFound:
        return False


def _count_rows(path: Path) -> int:
    """Quick row-count for a (possibly gzipped) jsonl file."""
    import gzip
    opener = gzip.open if path.suffix == ".gz" else open
    n = 0
    with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for _ in fh:
            n += 1
    return n


def _run_lastfm_batch(bucket_name: str, offset: int, size: int,
                      failures_path: Path) -> int:
    """Invoke run_lastfm_enrichment.py for [offset, offset+size). Returns exit code."""
    # Force plain JSONL checkpoint (no gzip): gzip-append across
    # executions produced unreadable streams in production (zlib
    # "invalid block type" on the next exec's _load_checkpoint_mbids).
    # Plain JSONL is robust to per-execution upload/download cycles.
    local_checkpoint = DATA_DIR / "lastfm-checkpoint.jsonl"
    cmd = [
        sys.executable, "build-tools/rag/run_lastfm_enrichment.py",
        "--input", str(MB_ONLY_PATH),
        # `--output` is required but unused in batched mode (the
        # checkpoint is the durable artefact).
        "--output", str(MB_ONLY_PATH.with_name("artists.lastfm.jsonl.gz")),
        "--batch-offset", str(offset),
        "--batch-size", str(size),
        "--checkpoint", str(local_checkpoint),
        "--checkpoint-gcs-uri", f"gs://{bucket_name}/{LASTFM_CHECKPOINT_BLOB}",
        "--failures-out", str(failures_path),
        # ~500 entries / 5 min keeps loss-on-SIGKILL bounded.
        "--checkpoint-every", "500",
        "--top-tracks-per-artist", "5",
    ]
    lastfm_max = os.environ.get("LASTFM_MAX_ENRICH", "").strip()
    if lastfm_max:
        cmd += ["--max-enrich", lastfm_max]
    return _run_allow_exit_codes(
        cmd,
        allowed={
            LASTFM_RATE_LIMIT_EXIT_CODE,
            LASTFM_AUTH_ERROR_EXIT_CODE,
            LASTFM_SMOKE_FAIL_EXIT_CODE,
        },
    )


def _finalise_cycle(bucket, bucket_name: str, state: dict) -> int:
    """Final batch done — promote the checkpoint into the published corpus.

    Sanity checks BEFORE overwriting the live corpus:
      - checkpoint must exist
      - checkpoint must be at least MIN_PUBLISH_RATIO of the MB-only
        corpus by row count; otherwise the run partially failed and we
        refuse to clobber the working corpus
      - structural_failures count must not dominate completed_batches
    """
    print("=" * 60, flush=True)
    print("Finalising cycle: assembling published corpus + manifest.",
          flush=True)
    print("=" * 60, flush=True)

    # Bring the merged checkpoint local. New format = plain JSONL.
    local_corpus = DATA_DIR / "artists.final.jsonl"
    if not _download(bucket, LASTFM_CHECKPOINT_BLOB, local_corpus):
        print(f"ERROR: no checkpoint at gs://{bucket_name}/{LASTFM_CHECKPOINT_BLOB}; "
              "cannot finalise. State left in place for investigation.",
              file=sys.stderr, flush=True)
        return 1

    # Bring the MB-only corpus for the sanity check.
    if not MB_ONLY_PATH.exists() and not _download(bucket, MB_ONLY_BLOB, MB_ONLY_PATH):
        print(f"ERROR: no MB-only corpus at gs://{bucket_name}/{MB_ONLY_BLOB}; "
              "cannot finalise.", file=sys.stderr, flush=True)
        return 1

    # Bake the AI tag layer into the corpus before publishing (best-effort;
    # see _bake_ai_overlay). Row count is preserved, so the sanity ratios
    # below are unaffected.
    local_corpus = _bake_ai_overlay(bucket, local_corpus)

    final_rows = _count_rows(local_corpus)
    mb_rows = _count_rows(MB_ONLY_PATH)
    completed = len(state.get("completed_batches", []))
    failures = len(state.get("structural_failures", []))
    total_batches = max(1, completed + failures)
    success_ratio = completed / total_batches

    MIN_ROW_RATIO = 0.80
    MIN_SUCCESS_RATIO = 0.80
    row_ratio = final_rows / max(1, mb_rows)

    print(f"Finalise sanity: checkpoint rows={final_rows}, "
          f"MB-only rows={mb_rows}, row_ratio={row_ratio:.2%}", flush=True)
    print(f"Finalise sanity: completed_batches={completed}, "
          f"structural_failures={failures}, "
          f"success_ratio={success_ratio:.2%}", flush=True)

    if row_ratio < MIN_ROW_RATIO:
        print(
            f"⚠ ⚠ ⚠ REFUSING TO PUBLISH: checkpoint has only {row_ratio:.1%} "
            f"of MB-only row count (threshold {MIN_ROW_RATIO:.0%}). The "
            f"existing published corpus is left untouched. State + "
            f"checkpoint preserved for investigation. Clear "
            f"build-state.json + lastfm-checkpoint.jsonl manually if you "
            f"want to retry from scratch.",
            file=sys.stderr, flush=True,
        )
        return 1
    if success_ratio < MIN_SUCCESS_RATIO:
        print(
            f"⚠ ⚠ ⚠ REFUSING TO PUBLISH: only {success_ratio:.1%} of "
            f"batches completed cleanly (threshold {MIN_SUCCESS_RATIO:.0%}). "
            f"Existing published corpus left untouched.",
            file=sys.stderr, flush=True,
        )
        return 1

    # Gzip the plain-JSONL checkpoint before publishing. The
    # CORPUS_BLOB name is `artists.jsonl.gz`; clients expect a real
    # gzip stream there. Uploading the plain file under that name
    # would break every downstream consumer (cdn cache, manifest
    # sha mismatch, decompression errors).
    import gzip as _gzip_mod
    gzipped_corpus = DATA_DIR / "artists.final.jsonl.gz"
    print(f"Gzipping plain checkpoint → {gzipped_corpus}", flush=True)
    with open(local_corpus, "rb") as src, _gzip_mod.open(gzipped_corpus, "wb") as dst:
        shutil.copyfileobj(src, dst)

    sha = _sha256(gzipped_corpus)
    size = gzipped_corpus.stat().st_size
    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    corpus_url = f"https://storage.googleapis.com/{bucket_name}/{CORPUS_BLOB}"
    manifest = {
        "corpus_version": version,
        "built_at": _now_iso(),
        "sha256": sha,
        "size_bytes": size,
        "row_count": final_rows,
        "corpus_url": corpus_url,
        "source": "cloud-run-job (batched workflow)",
        "cycle_id": state.get("cycle_id"),
        "batches_completed": completed,
        "structural_failures": state.get("structural_failures", []),
    }

    print(f"Uploading {gzipped_corpus} ({size:,} bytes gzipped, "
          f"{final_rows} rows) → gs://{bucket_name}/{CORPUS_BLOB}", flush=True)
    _upload(bucket, gzipped_corpus, CORPUS_BLOB, "public, max-age=86400")

    # AI-artist blocklist (sibling artifact). Best-effort — a failed fetch
    # leaves the manifest without blocklist fields, which older/newer clients
    # both tolerate (the filter stays inert until a blocklist is present).
    ai_blocklist_path = DATA_DIR / AI_BLOCKLIST_BLOB
    ai_result = _build_ai_blocklist(ai_blocklist_path, version)
    if ai_result is not None:
        ai_count, ai_sha = ai_result
        print(f"Uploading AI blocklist ({ai_count} ids) → "
              f"gs://{bucket_name}/{AI_BLOCKLIST_BLOB}", flush=True)
        _upload(bucket, ai_blocklist_path, AI_BLOCKLIST_BLOB, "public, max-age=86400")
        manifest["ai_blocklist_url"] = (
            f"https://storage.googleapis.com/{bucket_name}/{AI_BLOCKLIST_BLOB}")
        manifest["ai_blocklist_sha256"] = ai_sha
        manifest["ai_blocklist_version"] = version
        manifest["ai_blocklist_count"] = ai_count

    print(f"Uploading manifest → gs://{bucket_name}/{MANIFEST_BLOB}", flush=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _upload(bucket, MANIFEST_PATH, MANIFEST_BLOB, "public, max-age=300")

    _delete_state(bucket)
    print(f"OK: published version {version} ({sha[:12]}…). "
          f"State cleared; next cycle starts on next trigger.", flush=True)
    return 0


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    bucket_name = os.environ["GCS_BUCKET"]
    top_n = os.environ.get("CORPUS_TOP_N", "500000")
    force = os.environ.get("FORCE_REBUILD") == "1"
    min_rebuild_days = int(os.environ.get("MIN_REBUILD_DAYS", "6"))
    cycle_ttl_days = int(os.environ.get("CYCLE_TTL_DAYS", "25"))
    batch_size = int(os.environ.get("BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # 0a. Halt flag aborts the whole cycle — no self-chaining.
    halt = _halt_flag_active(bucket)
    if halt is not None:
        if force:
            print(f"FORCE_REBUILD=1 — ignoring halt.flag for this execution.\n"
                  f"  flag contents: {json.dumps(halt)}", flush=True)
        else:
            print("⏸ Halt flag is set — skipping run. Details:", flush=True)
            print(json.dumps(halt, indent=2), flush=True)
            print(f"To resume: gcloud storage rm gs://{bucket_name}/{HALT_FLAG_BLOB}",
                  flush=True)
            return 0

    # 0b. Load (or start) the cycle state.
    state = _load_state(bucket)
    if state is None:
        new_cycle = True
    elif _state_is_stale(state, cycle_ttl_days):
        print(f"⏰ Existing state is older than {cycle_ttl_days} days "
              f"(started_at={state.get('started_at')}). Starting fresh cycle.",
              flush=True)
        new_cycle = True
    else:
        new_cycle = False

    # 0c. New cycle gate: respect MIN_REBUILD_DAYS unless FORCE_REBUILD=1.
    if new_cycle and not force and _recent_build_within_days(bucket, min_rebuild_days):
        print(
            f"⏭ ⏭ ⏭ SKIPPING new cycle: published build is < "
            f"{min_rebuild_days} days old. This execution did NO work. "
            f"Set FORCE_REBUILD=1 to override (the helper scripts under "
            f"build-tools/cloud-run-job/ do this automatically). Cloud Run "
            f"will still report this execution as 'succeeded' — there is "
            f"no failed status for a deliberate skip.",
            flush=True,
        )
        return 0

    # ── Phase 1: build (or reuse) the MB-only corpus ─────────────────
    if new_cycle:
        print("=" * 60, flush=True)
        print("Phase 1: MusicBrainz corpus build", flush=True)
        print("=" * 60, flush=True)
        keep_intermediates = os.environ.get("KEEP_INTERMEDIATES") == "1"
        corpus_local = _run_phase1_mb_build(top_n, keep_intermediates)
        # Persist the MB-only artefact to GCS so subsequent batches in
        # this cycle skip Phase 1 entirely.
        MB_ONLY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if corpus_local != MB_ONLY_PATH:
            shutil.copy(str(corpus_local), str(MB_ONLY_PATH))
        # private blob — clients should consume the published corpus, not the MB-only one.
        _upload(bucket, MB_ONLY_PATH, MB_ONLY_BLOB,
                "private, max-age=0")
        total_artists = _count_rows(MB_ONLY_PATH)
        state = {
            "cycle_id": _now_iso(),
            "started_at": _now_iso(),
            "total_artists": total_artists,
            "batch_size": batch_size,
            "next_offset": 0,
            "completed_batches": [],
            "structural_failures": [],
        }
        # Incremental Last.fm: carry the previous corpus's Last.fm layer
        # forward onto the fresh MB build so this cycle re-fetches only
        # new / never-enriched artists instead of all ~175k (saves ~29 h).
        # Falls back to a full enrichment pass on a first-ever build.
        seeded = _seed_lastfm_checkpoint_from_previous(bucket, bucket_name)
        if not seeded:
            try:
                bucket.blob(LASTFM_CHECKPOINT_BLOB).delete()
                print(f"Cleared prior {LASTFM_CHECKPOINT_BLOB} "
                      "(first build / no seed).", flush=True)
            except NotFound:
                pass
        _save_state(bucket, state)
        print(f"Cycle initialised: {total_artists} artists, batch_size={batch_size}.",
              flush=True)
        # Phase 1 already consumed ~20 min. Do NOT run a batch in the
        # same execution — first batch + Phase 1 has tipped over the 1 h
        # timeout in practice. Trigger the next execution and exit so
        # batch 1 gets a fresh ~50-min budget on its own container.
        project_id = _project_id_from_metadata()
        region = os.environ.get("BATCH_RUN_REGION", "us-central1")
        job_name = os.environ.get("BATCH_RUN_JOB", "spotivibe-rag-builder")
        print("Phase 1 done. Self-triggering next execution to start batch 1 "
              "with a fresh task-timeout budget.", flush=True)
        if project_id:
            _trigger_next_execution(project_id, region, job_name)
        else:
            print("WARNING: project id not resolvable from metadata server; "
                  "first batch must be kicked manually.", flush=True)
        return 0
    else:
        print(f"Resuming cycle {state.get('cycle_id')} "
              f"(next_offset={state.get('next_offset')}, "
              f"completed_batches={len(state.get('completed_batches', []))}).",
              flush=True)
        if not _download(bucket, MB_ONLY_BLOB, MB_ONLY_PATH):
            print(f"ERROR: MB-only corpus not on GCS at {MB_ONLY_BLOB}; "
                  "state is corrupt. Deleting state to force a fresh cycle "
                  "on next trigger.", file=sys.stderr, flush=True)
            _delete_state(bucket)
            return 1

    # ── Spotify path: dormant (kept for emergency re-enable) ─────────
    sp_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    sp_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if (sp_id and sp_secret
            and os.environ.get("DISABLE_SPOTIFY_ENRICHMENT") != "1"
            and new_cycle):
        print("⚠ Spotify enrichment is enabled — running once at cycle start.",
              flush=True)
        enriched_path = MB_ONLY_PATH.with_name("artists.spotify.jsonl.gz")
        spotify_max = os.environ.get("SPOTIFY_MAX_ENRICH", "").strip()
        rc = _run_allow_exit_codes(
            [
                sys.executable, "build-tools/rag/run_spotify_enrichment.py",
                "--input", str(MB_ONLY_PATH),
                "--output", str(enriched_path),
                *(["--max-enrich", spotify_max] if spotify_max else []),
            ],
            allowed={RATE_LIMIT_EXIT_CODE},
        )
        if rc == RATE_LIMIT_EXIT_CODE:
            _set_halt_flag(
                bucket,
                reason="spotify_rate_limited",
                detail="run_spotify_enrichment.py exited 42. Cycle paused.",
            )
            return 1
        if enriched_path.exists():
            enriched_path.replace(MB_ONLY_PATH)
            _upload(bucket, MB_ONLY_PATH, MB_ONLY_BLOB,
                    "private, max-age=0")
            state["total_artists"] = _count_rows(MB_ONLY_PATH)
            _save_state(bucket, state)

    # ── Phase B: one Last.fm enrichment batch ────────────────────────
    if state["next_offset"] >= state["total_artists"]:
        # All batches done — finalise and clean up.
        rc = _finalise_cycle(bucket, bucket_name, state)
        return rc

    offset = state["next_offset"]
    size = min(state["batch_size"], state["total_artists"] - offset)
    batch_label = f"{offset}-{offset + size}"

    print("=" * 60, flush=True)
    print(f"Phase B batch {batch_label} "
          f"({len(state.get('completed_batches', [])) + 1} of "
          f"~{(state['total_artists'] + state['batch_size'] - 1) // state['batch_size']})",
          flush=True)
    print("=" * 60, flush=True)

    failure_already_recorded = False
    if os.environ.get("DISABLE_LASTFM_ENRICHMENT") == "1":
        print("DISABLE_LASTFM_ENRICHMENT=1 — skipping enrichment but still "
              "advancing offset.", flush=True)
        rc = 0
    elif not os.environ.get("LASTFM_API_KEY", "").strip():
        print("LASTFM_API_KEY missing — skipping enrichment but still "
              "advancing offset.", flush=True)
        rc = 0
    else:
        failures_path = DATA_DIR / f"failures.{batch_label}.jsonl"
        try:
            rc = _run_lastfm_batch(bucket_name, offset, size, failures_path)
        except subprocess.CalledProcessError as exc:
            print(f"Batch {batch_label} crashed (exit {exc.returncode}). "
                  "Logging structural failure and advancing.",
                  flush=True)
            state["structural_failures"].append({
                "batch": batch_label,
                "stage": "lastfm",
                "exit_code": exc.returncode,
                "category": "subprocess_crashed",
                "at": _now_iso(),
            })
            rc = -1
            failure_already_recorded = True

    # Record outcome + advance offset regardless of success.
    if rc == 0:
        state["completed_batches"].append({
            "batch": batch_label,
            "completed_at": _now_iso(),
        })
    elif rc == LASTFM_RATE_LIMIT_EXIT_CODE:
        # Halt flag was set by the rate-limit catcher inside the
        # enricher subprocess? No — it lives here. Set it now and stop
        # the chain.
        _set_halt_flag(
            bucket,
            reason="lastfm_rate_limited",
            detail=f"Batch {batch_label} hit the Last.fm rate limit. "
                   "Wait, investigate, then delete halt.flag to resume.",
        )
        state["structural_failures"].append({
            "batch": batch_label,
            "stage": "lastfm",
            "exit_code": rc,
            "category": "rate_limit",
            "at": _now_iso(),
        })
        _save_state(bucket, state)
        # Stop the chain — halt flag will block the next execution
        # until manually cleared.
        return 0
    elif rc == LASTFM_AUTH_ERROR_EXIT_CODE:
        print("ABORT: Last.fm API key invalid/suspended. Pausing cycle.",
              file=sys.stderr, flush=True)
        state["structural_failures"].append({
            "batch": batch_label,
            "stage": "lastfm",
            "exit_code": rc,
            "category": "auth",
            "at": _now_iso(),
        })
        _save_state(bucket, state)
        return 0
    elif not failure_already_recorded:
        # Treat other non-zero exits as recoverable: log + advance.
        # Skipped if the subprocess-crashed branch already recorded
        # this batch (avoids the duplicate-entry bug).
        state["structural_failures"].append({
            "batch": batch_label,
            "stage": "lastfm",
            "exit_code": rc,
            "category": "transient_cluster" if rc == LASTFM_SMOKE_FAIL_EXIT_CODE
                        else "unknown",
            "at": _now_iso(),
        })

    state["next_offset"] = offset + size
    _save_state(bucket, state)

    # ── Self-trigger next batch (or finalise) ────────────────────────
    project_id = _project_id_from_metadata()
    region = os.environ.get("BATCH_RUN_REGION", "us-central1")
    job_name = os.environ.get("BATCH_RUN_JOB", "spotivibe-rag-builder")
    if project_id:
        _trigger_next_execution(project_id, region, job_name)
    else:
        print("WARNING: project id not resolvable from metadata server; "
              "next batch must be kicked manually.", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
