"""Cloud Run Job entry point: refresh the RAG corpus and upload to GCS.

Reads its configuration from env vars set in the Job spec:
    GCS_BUCKET           — destination bucket (e.g. "spotivibe-rag-corpus")
    CORPUS_TOP_N         — top-N artists to include (default 350000)
    KEEP_INTERMEDIATES   — "1" to retain MB dumps between runs (default off)

Pipeline:
    1. Run refresh_rag_corpus.py (downloads MB dump + invokes build_rag_corpus.py).
    2. Compute sha256 of the resulting artists.jsonl.gz.
    3. Upload artists.jsonl.gz to gs://$GCS_BUCKET/artists.jsonl.gz.
    4. Write + upload manifest.json with corpus_url, sha256, size, build timestamp.
    5. Wipe the working directory (corpus build leaves ~33 GB extracted).

Exit non-zero on any failure so Cloud Run logs the run as failed.
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

ROOT = Path(__file__).resolve().parent.parent  # repo root inside the container
CORPUS_PATH = ROOT / "data" / "rag_corpus" / "artists.jsonl.gz"
MANIFEST_PATH = ROOT / "data" / "rag_corpus" / "manifest.json"
WORK_DIR = ROOT / "build-tools" / ".rag-cache"


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    bucket_name = os.environ["GCS_BUCKET"]
    top_n = os.environ.get("CORPUS_TOP_N", "350000")

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

    # 2. Compute hash + assemble manifest.
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

    # 3. + 4. Upload both, corpus first so manifest never points at a missing asset.
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    print(f"Uploading {CORPUS_PATH} ({size:,} bytes) -> gs://{bucket_name}/artists.jsonl.gz",
          flush=True)
    blob = bucket.blob("artists.jsonl.gz")
    blob.cache_control = "public, max-age=86400"  # 1-day CDN cache
    blob.upload_from_filename(str(CORPUS_PATH))

    print(f"Uploading manifest -> gs://{bucket_name}/manifest.json", flush=True)
    mblob = bucket.blob("manifest.json")
    mblob.cache_control = "public, max-age=300"  # 5-min cache
    mblob.upload_from_filename(str(MANIFEST_PATH))

    # 5. Wipe the work dir.
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print(f"OK: published version {version} ({sha[:12]}...)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

