"""One-off builder for ``data/rag_corpus/artists.jsonl.gz``.

Usage::

    python build-tools/build_rag_corpus.py \\
        --source <path-to-mbdump-extract-or-json> \\
        --output data/rag_corpus/artists.jsonl.gz \\
        --top-n 500000

See ``documentation/TechnicalManual.md`` §"RAG design reference" → Corpus
size rationale and Per-artist schema for the rationale behind the quality
filters. The actual yield (~170-180K artists) is determined by MusicBrainz
community tag coverage, not the top-n cap.

The script accepts two input shapes:

1. A MusicBrainz JSON dump directory (``--source mbdump/``) containing
   the newline-delimited JSON files ``artist`` and ``release-group``.
   These come from extracting ``artist.tar.xz`` and
   ``release-group.tar.xz`` from
   https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/<date>/.
   Tags are read inline from each artist record's ``tags`` array — the
   JSON dump does not ship a separate ``tag``/``artist_tag`` join.
2. A pre-flattened JSONL file where each line already matches the
   target schema (for test fixtures / enriched builds that include
   Spotify follower counts — see §2.3 Option B). In that mode the
   script just re-ranks by ``listener_popularity`` and caps at
   ``--top-n``.

The output file is streamed, gzip-compressed, and deterministic given
the same input.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("build_rag_corpus")

# MusicBrainz convention: non-real artist placeholders are tagged with one of
# these. Dropping them keeps "Various Artists" / "[anonymous]" / "[unknown]"
# out of suggestion candidate pools.
_SPECIAL_PURPOSE_TAGS = {"special purpose artist", "special purpose"}

# Item: filter out artists whose career started before the 1960s. The share
# of users that listens to pre-1960s music is negligible for this app and
# keeping them in the corpus only burns capacity. Artists with no known
# begin year are kept (we cannot prove they're old) — same for artists
# whose begin year sits inside the 1960s decade or later.
MIN_ARTIST_BEGIN_YEAR = 1960


def _iter_jsonl(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _iter_jsonl_from_tar(tar_path: Path, member_name: str):
    """Stream JSONL records from a member inside a .tar.xz without full extraction.

    ``member_name`` is the path inside the tarball, e.g. ``mbdump/artist``.
    """
    with tarfile.open(tar_path, "r:xz") as tf:
        for m in tf:
            if m.name.endswith(f"/{member_name}") or m.name == member_name:
                fobj = tf.extractfile(m)
                if fobj is None:
                    return
                import io
                reader = io.TextIOWrapper(fobj, encoding="utf-8")
                for line in reader:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
                return


def _resolve_dump_file(source: Path, name: str) -> Path | None:
    """Find ``<name>`` in ``source`` or one level deep (e.g. ``mbdump/``).

    The JSON-dump tarballs extract to ``mbdump/<entity>``; when the user
    extracts several tarballs into one directory they merge cleanly, but
    some extractors leave the ``mbdump/`` wrapper in place. Accept both.
    """
    direct = source / name
    if direct.exists():
        return direct
    for child in source.iterdir():
        if child.is_dir():
            candidate = child / name
            if candidate.exists():
                return candidate
    return None


def _parse_year(value) -> int | None:
    if not value:
        return None
    s = str(value)
    try:
        return int(s[:4])
    except ValueError:
        return None


def _load_mb_dump(source: Path, *, artist_tar: Path | None = None,
                  release_group_tar: Path | None = None) -> list[dict]:
    """Load a MusicBrainz JSON dump into flat ArtistRow dicts.

    Supports two modes:
    - Directory mode (legacy): ``source`` points to extracted mbdump/ dir.
    - Tar mode: ``artist_tar`` and ``release_group_tar`` point to .tar.xz
      files, streamed without extraction (saves ~33 GB disk).
    """
    # Determine the iterators based on mode
    if artist_tar and artist_tar.exists():
        logger.info("Streaming artist records from %s (no extraction)", artist_tar)
        artist_iter = lambda: _iter_jsonl_from_tar(artist_tar, "artist")
        if release_group_tar and release_group_tar.exists():
            logger.info("Streaming release-group records from %s", release_group_tar)
            rg_iter = lambda: _iter_jsonl_from_tar(release_group_tar, "release-group")
        else:
            rg_iter = None
    else:
        artist_file = _resolve_dump_file(source, "artist")
        if artist_file is None:
            raise SystemExit(
                f"Missing MusicBrainz JSON dump file 'artist' under {source}. "
                "Extract artist.tar.xz from the json-dumps/<date>/ folder first."
            )
        artist_iter = lambda: _iter_jsonl(artist_file)
        release_group_file = _resolve_dump_file(source, "release-group")
        rg_iter = (lambda: _iter_jsonl(release_group_file)) if release_group_file else None

    logger.info("Loading release-group for release counts …")
    release_counts: dict[str, int] = defaultdict(int)
    if rg_iter is not None:
        for row in rg_iter():
            for credit in row.get("artist-credit") or []:
                artist = credit.get("artist") if isinstance(credit, dict) else None
                aid = artist.get("id") if isinstance(artist, dict) else None
                if aid:
                    release_counts[str(aid)] += 1
    else:
        logger.warning(
            "release-group file not found — skipping ≥1-release filter. "
            "Extract release-group.tar.xz for better popularity signal."
        )

    has_rg = rg_iter is not None
    logger.info("Loading artists …")
    artists: list[dict] = []
    for row in artist_iter():
        aid = str(row.get("id") or "")
        if not aid:
            continue
        raw_tags = row.get("tags") or []
        atags: list[tuple[str, int]] = []
        is_special_purpose = False
        for t in raw_tags:
            if not isinstance(t, dict):
                continue
            name = t.get("name") or ""
            count = int(t.get("count") or 1)
            if not name:
                continue
            if name.lower() in _SPECIAL_PURPOSE_TAGS:
                is_special_purpose = True
                break
            atags.append((name, count))
        if is_special_purpose:
            continue  # drop Various Artists / [anonymous] / [unknown] / etc.
        if not atags:
            continue  # rule §2.2 step 2: require ≥1 tag

        rc = release_counts.get(aid, 0)
        if has_rg and rc < 1:
            continue  # require ≥1 release when we have the data

        life_span = row.get("life-span") or {}
        begin_year = _parse_year(life_span.get("begin"))
        # Drop pre-1960s artists — see MIN_ARTIST_BEGIN_YEAR.
        if begin_year is not None and begin_year < MIN_ARTIST_BEGIN_YEAR:
            continue
        sorted_tags = sorted(atags, key=lambda t: -t[1])
        # Slim row schema — only fields consumed by the runtime retriever
        # are persisted. Dropped vs. v1: sort_name, country, end_year.
        # See documentation/TechnicalManual.md §"RAG design reference" →
        # Per-artist schema (slimming history note).
        artists.append({
            "mbid": aid,
            "name": row.get("name") or "",
            "begin_year": begin_year,
            "tags": [t for t, _ in sorted_tags],
            "tag_weights": [w for _, w in sorted_tags],
            "_release_count": rc,
            "_tag_total": sum(w for _, w in sorted_tags),
        })
    return artists


def _apply_popularity(artists: list[dict]) -> None:
    """Option A proxy: normalise release_count + tag_total into 0..1.

    Rank by ``log(release_count+1) + log(tag_total+1)`` and map each
    artist's rank to a 0..1 score so the re-rank step has a stable scale.
    """
    def raw_score(a: dict) -> float:
        return math.log(1 + a.get("_release_count", 0)) + math.log(1 + a.get("_tag_total", 0))

    ordered = sorted(artists, key=raw_score, reverse=True)
    n = max(1, len(ordered))
    for rank, a in enumerate(ordered):
        a["listener_popularity"] = 1.0 - (rank / n)


def _emit(artists: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if output.suffix == ".gz" else open
    with opener(output, "wt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for a in artists:
            clean = {k: v for k, v in a.items() if not k.startswith("_")}
            fh.write(json.dumps(clean, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="MusicBrainz JSON dump directory OR a pre-flattened JSONL file.")
    parser.add_argument("--output", type=Path,
                        default=Path("data/rag_corpus/artists.jsonl.gz"))
    parser.add_argument("--top-n", type=int, default=500_000,
                        help="Maximum artists to keep (ranked by popularity proxy). "
                             "Note: the actual yield depends on MusicBrainz tag coverage — "
                             "typically ~170-180K artists survive the quality filters.")
    parser.add_argument("--artist-tar", type=Path, default=None,
                        help="Path to artist.tar.xz (stream mode — avoids extraction to disk).")
    parser.add_argument("--release-group-tar", type=Path, default=None,
                        help="Path to release-group.tar.xz (stream mode).")
    args = parser.parse_args(argv)

    if args.source.is_dir() or (args.artist_tar and args.artist_tar.exists()):
        artists = _load_mb_dump(args.source, artist_tar=args.artist_tar,
                                release_group_tar=args.release_group_tar)
        _apply_popularity(artists)
    elif args.source.is_file():
        logger.info("Loading pre-flattened JSONL from %s", args.source)
        artists = list(_iter_jsonl(args.source))
        if artists and "listener_popularity" not in artists[0]:
            _apply_popularity(artists)
    else:
        logger.error("Source not found: %s", args.source)
        return 1

    artists.sort(key=lambda a: a.get("listener_popularity", 0.0), reverse=True)
    if len(artists) > args.top_n:
        artists = artists[: args.top_n]

    _emit(artists, args.output)
    logger.info("Wrote %d artists to %s", len(artists), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
