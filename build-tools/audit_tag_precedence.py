"""Q4 — Tag-precedence audit (2026-05-07).

Confirms that ``_artist_popularity()`` prefers ``_lastfm_popularity()``
over the MusicBrainz-derived ``listener_popularity`` proxy whenever
Last.fm listener data is present.

Why this matters: ``next-steps.md`` Phase B shipped the precedence wiring
(see ``core/src/rag/retrieval.py`` ``_artist_popularity``). If MB proxy
still wins for any non-trivial slice of the corpus, the precedence wiring
has a bug — recommendations will silently regress to the pre-Phase-B
ranking shape.

Usage::

    python build-tools/audit_tag_precedence.py

Reads the local corpus from the user's app dir (auto-resolved via
``config``). Prints a per-pair report on a known mainstream-vs-niche
sample, then a corpus-wide sweep counting where Last.fm vs MB-proxy
drives the score. Exit code 0 if the precedence holds across the
corpus, 1 if any row with non-zero ``lastfm_listeners`` resolves to the
MB proxy instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so the script runs without an editable install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from config import RAG_CORPUS_PATH, RAG_TAG_ALIASES_PATH  # noqa: E402
from core.src.rag.corpus import RagCorpus  # noqa: E402
from core.src.rag.retrieval import (  # noqa: E402
    _artist_popularity,
    _lastfm_popularity,
)


def _resolve_corpus_path(path: Path) -> Path:
    """Detect a mis-suffixed plain-JSONL file written under a ``.gz`` name.

    Cloud Run gsutil sync occasionally lands the raw payload under
    ``artists.jsonl.gz``. The corpus loader picks the opener by suffix,
    so a plain file under that name explodes with ``BadGzipFile``. If
    the magic bytes don't match a gzip header, write a sibling
    ``.gz``-stripped copy and return that — non-destructive, repeatable.
    """
    if not path.exists():
        return path
    if path.suffix != ".gz":
        return path
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":  # gzip
        return path
    sibling = path.with_suffix("")  # strips .gz
    if not sibling.exists() or sibling.stat().st_mtime < path.stat().st_mtime:
        # Hard-link or copy. shutil.copy2 keeps mtime so the staleness
        # check above stays meaningful on re-runs.
        import shutil
        shutil.copy2(path, sibling)
        print(f"[info]Detected non-gzipped {path.name}; using {sibling.name} "
              f"({sibling.stat().st_size:,} bytes)")
    return sibling


# Known mainstream pairs to spot-check. Names are matched
# case-insensitively against ``ArtistRow.name``.
_PROBES = [
    "The Beatles",
    "Metallica",
    "Taylor Swift",
    "Drake",
    "Beyoncé",
]


def _find(corpus: RagCorpus, name: str):
    needle = name.lower().strip()
    for row in corpus.artists:  # type: ignore[attr-defined]
        if row.name.lower().strip() == needle:
            return row
    return None


def main() -> int:
    if not RAG_CORPUS_PATH.exists():
        print(f"[err]Corpus missing at {RAG_CORPUS_PATH}.", file=sys.stderr)
        print("Run the app once or sync from Cloud Run before retrying.",
              file=sys.stderr)
        return 2

    resolved = _resolve_corpus_path(RAG_CORPUS_PATH)
    corpus = RagCorpus.load(resolved, RAG_TAG_ALIASES_PATH)
    print(f"Loaded {len(corpus)} artists from {resolved}")
    print()

    # ── Spot-check known mainstream artists ──
    print("=" * 78)
    print("Spot-check — known mainstream artists")
    print("=" * 78)
    print(f"{'Artist':<28} {'Lfm listeners':>14} {'Lfm pop':>9} "
          f"{'MB proxy':>9} {'_artist_pop':>11} {'Source':>8}")
    print("-" * 78)
    matched = 0
    for name in _PROBES:
        row = _find(corpus, name)
        if row is None:
            print(f"{name:<28} {'(not in corpus)':>14}")
            continue
        matched += 1
        lfm_listeners = row.lastfm_listeners or 0
        lfm_pop = _lastfm_popularity(lfm_listeners) if lfm_listeners else None
        mb_proxy = row.listener_popularity
        actual = _artist_popularity(row)
        if lfm_listeners > 0 and abs(actual - lfm_pop) < 1e-6:
            source = "Last.fm"
        elif abs(actual - mb_proxy) < 1e-6:
            source = "MB proxy"
        else:
            source = "??"
        print(
            f"{name:<28} {lfm_listeners:>14,} "
            f"{(f'{lfm_pop:.3f}' if lfm_pop is not None else '—'):>9} "
            f"{mb_proxy:>9.3f} {actual:>11.3f} {source:>8}"
        )

    if matched == 0:
        print()
        print("[warn]None of the probe artists matched. Audit cannot prove "
              "precedence on a known pair — see corpus-wide sweep below.")

    # ── Corpus-wide sweep ──
    print()
    print("=" * 78)
    print("Corpus-wide sweep — drives popularity score?")
    print("=" * 78)
    total = 0
    has_lfm = 0
    lfm_drives = 0
    mb_drives = 0
    leaks = []  # rows with lastfm_listeners > 0 where MB still drives.
    for row in corpus.artists:  # type: ignore[attr-defined]
        total += 1
        lfm = row.lastfm_listeners or 0
        actual = _artist_popularity(row)
        mb_proxy = max(0.0, min(1.0, row.listener_popularity))
        if lfm > 0:
            has_lfm += 1
            lfm_pop = _lastfm_popularity(lfm)
            if abs(actual - lfm_pop) < 1e-6:
                lfm_drives += 1
            else:
                # Tie-break: if Last.fm pop happens to equal MB proxy,
                # we can't tell — but only flag mismatches that pick
                # MB proxy over a *different* Last.fm value.
                if abs(actual - mb_proxy) < 1e-6 and abs(lfm_pop - mb_proxy) >= 1e-6:
                    leaks.append((row.name, lfm, lfm_pop, mb_proxy))
        else:
            if abs(actual - mb_proxy) < 1e-6:
                mb_drives += 1

    print(f"Total rows                                 : {total:>10,}")
    print(f"  Rows with lastfm_listeners > 0           : {has_lfm:>10,} "
          f"({(has_lfm / total) * 100:5.1f} %)")
    print(f"  → Last.fm drives _artist_popularity      : {lfm_drives:>10,} "
          f"({(lfm_drives / has_lfm) * 100 if has_lfm else 0:5.1f} %)")
    print(f"  → MB proxy drives instead (precedence bug): {len(leaks):>10,}")
    print(f"  Rows w/o Last.fm (MB proxy fallback)      : "
          f"{total - has_lfm:>10,}")

    if leaks:
        print()
        print("First 10 precedence-bug rows:")
        for name, lfm, lfm_pop, mb_proxy in leaks[:10]:
            print(f"  {name:<40} lfm={lfm:>10,} "
                  f"lfm_pop={lfm_pop:.3f} mb={mb_proxy:.3f}")
        return 1

    print()
    print("[ok]Precedence holds: every row with Last.fm listeners "
          "resolves to the Last.fm-derived score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
