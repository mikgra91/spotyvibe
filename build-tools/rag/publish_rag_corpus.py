"""Publish ``data/rag_corpus/artists.jsonl.gz`` to GitHub Releases.

Uploads the corpus + a generated ``manifest.json`` to a rolling
``rag-corpus-latest`` tag/release on the repo. Clients fetch the
manifest once per startup (see
``core/src/rag/distribution.py``) and download the corpus when
the version changes or when it is absent locally.

Requires the GitHub CLI (``gh``) to be installed and authenticated::

    gh auth login

Usage::

    python build-tools/rag/publish_rag_corpus.py

Options let you pin a different tag or corpus path; defaults match
:mod:`config.RAG_MANIFEST_URL`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("publish_rag_corpus")

REPO_DEFAULT = "mikgra91/spotyvibe"
TAG_DEFAULT = "rag-corpus-latest"
CORPUS_DEFAULT = Path("data/rag_corpus/artists.jsonl.gz")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso_utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _version_from_mtime(path: Path) -> str:
    ts = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    return ts.strftime("%Y-%m-%d")


def _build_manifest(corpus: Path, repo: str, tag: str, version: str) -> dict:
    return {
        "corpus_version": version,
        "built_at": _iso_utc_now(),
        "sha256": _sha256(corpus),
        "size_bytes": corpus.stat().st_size,
        "corpus_url": f"https://github.com/{repo}/releases/download/{tag}/{corpus.name}",
    }


def _gh(*args: str) -> None:
    logger.info("$ gh %s", " ".join(args))
    subprocess.check_call(["gh", *args])


def _release_exists(repo: str, tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS_DEFAULT,
                        help=f"Corpus file to upload (default {CORPUS_DEFAULT}).")
    parser.add_argument("--repo", default=REPO_DEFAULT,
                        help=f"GitHub owner/repo (default {REPO_DEFAULT}).")
    parser.add_argument("--tag", default=TAG_DEFAULT,
                        help=f"Release tag to publish under (default {TAG_DEFAULT}).")
    parser.add_argument("--version", default=None,
                        help="Override corpus_version (default: UTC date from file mtime).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the manifest and print it; skip the gh upload.")
    args = parser.parse_args(argv)

    if not args.corpus.exists():
        logger.error("Corpus file missing: %s", args.corpus)
        return 1

    version = args.version or _version_from_mtime(args.corpus)
    manifest = _build_manifest(args.corpus, args.repo, args.tag, version)
    logger.info("Manifest: %s", json.dumps(manifest, indent=2))

    if args.dry_run:
        logger.info("Dry run — not uploading.")
        return 0

    with tempfile.TemporaryDirectory() as td:
        manifest_path = Path(td) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        title = f"RAG corpus {version}"
        notes = (
            f"Rolling RAG candidate-pool corpus.\n\n"
            f"- corpus_version: {version}\n"
            f"- sha256: {manifest['sha256']}\n"
            f"- size: {manifest['size_bytes']} bytes\n"
        )
        if _release_exists(args.repo, args.tag):
            logger.info("Release %s exists — replacing assets.", args.tag)
            _gh("release", "upload", args.tag,
                str(args.corpus), str(manifest_path),
                "--repo", args.repo, "--clobber")
            _gh("release", "edit", args.tag,
                "--repo", args.repo,
                "--title", title, "--notes", notes)
        else:
            logger.info("Creating release %s.", args.tag)
            _gh("release", "create", args.tag,
                str(args.corpus), str(manifest_path),
                "--repo", args.repo,
                "--title", title,
                "--notes", notes)

    logger.info("Published corpus %s to %s@%s", version, args.repo, args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
