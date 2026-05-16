"""Fetch the latest MusicBrainz JSON dump and rebuild the RAG corpus.

End-to-end automation for the manual MusicBrainz dump → corpus pipeline.
See ``documentation/TechnicalManual.md`` §"RAG corpus — Cloud Run
automated pipeline" for the production cadence; the steps here are:

1. Read the ``LATEST`` marker at
   https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/ to find
   the most recent dump folder.
2. Download ``artist.tar.xz`` and ``release-group.tar.xz`` from that
   folder (resumed if a partial file from a previous run is present).
3. Extract both into a working directory (default
   ``build-tools/.rag-cache/mb/``), producing
   ``mbdump/artist`` and ``mbdump/release-group``.
4. Invoke ``build_rag_corpus.py`` to write
   ``data/rag_corpus/artists.jsonl.gz``.

Intermediate downloads and extracted files are large (~3 GB compressed,
~33 GB extracted). By default the working directory is kept so a
subsequent run that targets the same dump date is near-instant; pass
``--cleanup`` to wipe it once the corpus has been built.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

BASE_URL = "https://data.metabrainz.org/pub/musicbrainz/data/json-dumps"
ENTITY_FILES = ("artist.tar.xz", "release-group.tar.xz")

logger = logging.getLogger("refresh_rag_corpus")


def _fetch_latest_folder() -> str:
    """Return the newest dump folder name, e.g. ``20260418-001002``."""
    url = f"{BASE_URL}/LATEST"
    logger.info("Reading %s", url)
    with urllib.request.urlopen(url, timeout=30) as resp:
        name = resp.read().decode("utf-8").strip()
    if not name:
        raise SystemExit(f"LATEST marker at {url} is empty")
    return name


def _download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` with resume support and a progress log."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0

    req = urllib.request.Request(url)
    if existing > 0:
        req.add_header("Range", f"bytes={existing}-")

    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and existing > 0:
            logger.info("%s already fully downloaded (%d bytes)", dest.name, existing)
            return
        raise

    total = resp.length or 0
    if existing > 0 and resp.status == 206:
        logger.info("Resuming %s at %d bytes (+%s remaining)", dest.name, existing, total)
        mode = "ab"
    else:
        if existing > 0:
            logger.info("Server ignored Range; restarting %s", dest.name)
        mode = "wb"
        existing = 0

    downloaded = existing
    last_logged_gb = downloaded // (1 << 30)
    with open(dest, mode) as fh:
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            fh.write(chunk)
            downloaded += len(chunk)
            gb = downloaded // (1 << 30)
            if gb > last_logged_gb:
                logger.info("  %s: %d GiB downloaded", dest.name, gb)
                last_logged_gb = gb
    logger.info("Finished %s (%d bytes)", dest.name, downloaded)


def _extract(tarball: Path, dest: Path) -> None:
    """Extract ``tarball`` into ``dest`` (idempotent)."""
    logger.info("Extracting %s into %s", tarball.name, dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:xz") as tf:
        tf.extractall(dest)


def _run_builder(source: Path, output: Path, top_n: int, *,
                 artist_tar: Path | None = None,
                 release_group_tar: Path | None = None) -> None:
    builder = Path(__file__).parent / "build_rag_corpus.py"
    cmd = [
        sys.executable, str(builder),
        "--source", str(source),
        "--output", str(output),
        "--top-n", str(top_n),
    ]
    if artist_tar:
        cmd += ["--artist-tar", str(artist_tar)]
    if release_group_tar:
        cmd += ["--release-group-tar", str(release_group_tar)]
    logger.info("Running builder: %s", " ".join(cmd))
    subprocess.check_call(cmd)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-dir", type=Path,
        default=Path(__file__).parent / ".rag-cache" / "mb",
        help="Where to stash downloads and extracted dumps (default: build-tools/.rag-cache/mb).",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/rag_corpus/artists.jsonl.gz"),
        help="Corpus output path (default: data/rag_corpus/artists.jsonl.gz).",
    )
    parser.add_argument("--top-n", type=int, default=100_000)
    parser.add_argument(
        "--folder", default=None,
        help="Pin a specific dump folder (e.g. 20260418-001002). Default: resolve LATEST.",
    )
    parser.add_argument(
        "--cleanup", action="store_true",
        help="Delete the work directory after a successful build.",
    )
    args = parser.parse_args(argv)

    folder = args.folder or _fetch_latest_folder()
    logger.info("Using MusicBrainz dump folder: %s", folder)

    work = args.work_dir / folder
    downloads = work / "downloads"
    extract_root = work  # artist.tar.xz / release-group.tar.xz both produce mbdump/

    for name in ENTITY_FILES:
        url = f"{BASE_URL}/{folder}/{name}"
        dest = downloads / name
        _download(url, dest)

    mbdump = extract_root / "mbdump"
    expected = {"artist": mbdump / "artist", "release-group": mbdump / "release-group"}

    # Prefer streaming from tar archives (no extraction needed — saves ~33 GB
    # disk, critical for Cloud Run's ephemeral storage limits).
    artist_tar = downloads / "artist.tar.xz"
    rg_tar = downloads / "release-group.tar.xz"

    if artist_tar.exists():
        logger.info("Using tar-stream mode (no extraction to disk)")
        _run_builder(extract_root, args.output, args.top_n,
                     artist_tar=artist_tar, release_group_tar=rg_tar)
    elif all(p.exists() for p in expected.values()):
        logger.info("Extracted files already present, skipping extraction")
        _run_builder(extract_root, args.output, args.top_n)
    else:
        for name in ENTITY_FILES:
            _extract(downloads / name, extract_root)
        _run_builder(extract_root, args.output, args.top_n)

    if args.cleanup:
        logger.info("Cleaning up %s", work)
        shutil.rmtree(work, ignore_errors=True)

    logger.info("Done. Corpus written to %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
