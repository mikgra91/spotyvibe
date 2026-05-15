"""Top-tracks-only enricher for the RAG corpus.

Reads ``--input artists.jsonl[.gz]`` and writes ``--output enriched.jsonl[.gz]``
with a ``top_tracks: list[str]`` field added per artist. Unlike
``enrich_with_spotify.py`` this script does NOT resolve Spotify artist IDs
nor fetch genres — it searches Spotify directly by artist name for top
tracks. Half the API calls of the dual-pass script; the only enrichment
field that still has value post Feb-2026.

Designed for the separate ``spotivibe-rag-enricher`` Cloud Run job:
the MB-only corpus is built + uploaded by the existing
``spotivibe-rag-builder`` job, and this enricher refreshes the
``top_tracks`` field as a separate, restartable pass.

Resumable: every ``--checkpoint-every`` artists the current state is
written to ``--checkpoint`` (local) and optionally mirrored to
``--checkpoint-gcs-uri``. On restart the script reloads the checkpoint
and skips already-fetched names.

Exit codes:
    0   — success
    1   — generic failure
    2   — bad CLI args / missing creds
    42  — Spotify rate-limited (matches enrich_with_spotify.py)
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spotify_enrichment.client import (  # noqa: E402
    SpotifyBackoffBudgetExhausted, SpotifyClient, SpotifyRateLimitedError,
)

logger = logging.getLogger("enrich_top_tracks")

RATE_LIMIT_EXIT_CODE = 42


def _open_jsonl(path: Path, mode: str):
    opener = gzip.open if path.suffix == ".gz" else open
    return opener(path, mode, encoding="utf-8")  # type: ignore[arg-type]


def _iter_input(path: Path):
    with _open_jsonl(path, "rt") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _load_checkpoint(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("checkpoint unreadable, starting empty: %s", path)
        return {}


def _save_checkpoint(path: Path | None, data: dict[str, list[str]],
                     gcs_uri: str | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if gcs_uri:
        try:
            from google.cloud import storage  # type: ignore
            assert gcs_uri.startswith("gs://"), gcs_uri
            bucket_name, _, blob_name = gcs_uri[5:].partition("/")
            storage.Client().bucket(bucket_name).blob(blob_name) \
                .upload_from_filename(str(path))
        except Exception as exc:  # pragma: no cover — best-effort mirror
            logger.warning("checkpoint GCS upload failed: %s", exc)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-tracks-per-artist", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0,
                        help="Optional cap on artists to enrich (0 = all).")
    parser.add_argument("--min-popularity", type=float, default=0.0,
                        help="Skip artists with listener_popularity below this. "
                             "0 = enrich everything.")
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help="Local JSON checkpoint of {artist_name: [tracks]}.")
    parser.add_argument("--checkpoint-gcs-uri", default=None,
                        help="Optional gs:// URI mirrored after every "
                             "--checkpoint-every artists.")
    parser.add_argument("--checkpoint-every", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=500)
    args = parser.parse_args(argv)

    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        logger.error("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set.")
        return 2
    if not args.input.exists():
        logger.error("Input not found: %s", args.input)
        return 1

    client = SpotifyClient(client_id, client_secret)

    logger.info("Loading input %s …", args.input)
    rows = list(_iter_input(args.input))
    rows.sort(key=lambda r: float(r.get("listener_popularity") or 0.0),
              reverse=True)
    if args.limit:
        rows = rows[: args.limit]
    logger.info("Loaded %d rows.", len(rows))

    cache = _load_checkpoint(args.checkpoint)
    logger.info("Checkpoint: %d entries already populated.", len(cache))

    n_seen = 0
    n_fetched = 0
    n_skipped_low_pop = 0
    n_with_tracks = 0
    started = time.time()

    try:
        for row in rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            n_seen += 1

            proxy_pop = float(row.get("listener_popularity") or 0.0) * 100.0
            if proxy_pop < args.min_popularity:
                n_skipped_low_pop += 1
                continue

            if name in cache:
                if cache[name]:
                    n_with_tracks += 1
                continue

            tracks = client.search_top_tracks(
                name, max_tracks=args.top_tracks_per_artist)
            cache[name] = tracks
            n_fetched += 1
            if tracks:
                n_with_tracks += 1

            if n_fetched and n_fetched % args.checkpoint_every == 0:
                _save_checkpoint(args.checkpoint, cache,
                                 args.checkpoint_gcs_uri)

            if n_seen % args.progress_every == 0:
                elapsed = time.time() - started
                rate = n_fetched / elapsed if elapsed > 0 else 0
                logger.info(
                    "Pass: %d scanned, %d fetched (%d with tracks), "
                    "%d skipped low-pop — %.1f fetches/sec",
                    n_seen, n_fetched, n_with_tracks, n_skipped_low_pop, rate,
                )
    except (SpotifyRateLimitedError, SpotifyBackoffBudgetExhausted) as exc:
        logger.error("Spotify enrichment ABORTED (rate-limited): %s", exc)
        logger.error("Processed %d/%d before abort. Checkpoint flushed.",
                     n_seen, len(rows))
        _save_checkpoint(args.checkpoint, cache, args.checkpoint_gcs_uri)
        return RATE_LIMIT_EXIT_CODE

    _save_checkpoint(args.checkpoint, cache, args.checkpoint_gcs_uri)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_enriched = 0
    with _open_jsonl(args.output, "wt") as out:
        for row in rows:
            name = str(row.get("name") or "").strip()
            tracks = cache.get(name) if name else None
            if tracks:
                out_row = dict(row)
                out_row["top_tracks"] = tracks
                n_enriched += 1
            else:
                out_row = row
            out.write(json.dumps(out_row, ensure_ascii=False) + "\n")
            n_written += 1

    elapsed = time.time() - started
    logger.info(
        "Done: %d rows written, %d with top_tracks (%.1f%%), "
        "%d new fetches in %.1f min",
        n_written, n_enriched,
        100.0 * n_enriched / max(1, n_written),
        n_fetched, elapsed / 60.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
