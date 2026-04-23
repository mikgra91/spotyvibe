"""Enrich a MusicBrainz-only RAG corpus with Spotify metadata.

Reads ``--input artists.jsonl[.gz]``, resolves each artist to a Spotify
artist via search + matching heuristic, then bulk-fetches the matched
IDs (50 at a time) and writes ``--output enriched.jsonl[.gz]``.

For every artist we attempt to add:
- ``spotify_id``         (str, ID for future lookups)
- ``spotify_popularity`` (int 0-100, **real** popularity)
- ``spotify_followers``  (int)
- ``spotify_genres``     (list[str], dense Spotify-curated genres)

If matching fails (no candidate clears ``MIN_MATCH_SCORE``), the row is
emitted **unchanged** — the runtime treats unenriched rows as legacy
and falls back to MB tags + the proxy popularity. Backward compatible.

Credentials come from env vars ``SPOTIFY_CLIENT_ID`` /
``SPOTIFY_CLIENT_SECRET`` so the secrets stay out of CLI history and
git diffs.
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

# Local package — we're inside build-tools/, sibling to this script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from spotify_enrichment.client import (  # noqa: E402
    SpotifyBackoffBudgetExhausted, SpotifyClient, SpotifyRateLimitedError,
)
from spotify_enrichment.matching import pick_best_match  # noqa: E402

logger = logging.getLogger("enrich_with_spotify")

# Distinct exit code so cloud_run_publish.py can detect rate-limit
# specifically and trip the GCS halt.flag circuit breaker. Any non-42
# non-zero exit is a generic failure (network, auth, etc.).
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


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Path to MB-only artists.jsonl[.gz] (output of build_rag_corpus.py).")
    parser.add_argument("--output", type=Path, required=True,
                        help="Where to write the enriched corpus.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Optional cap on artists to process (0 = all). Useful for smoke tests.")
    parser.add_argument("--max-enrich", type=int, default=50_000,
                        help="Hard ceiling on Spotify lookups. We sort the input by "
                             "MB proxy popularity DESC and only enrich the top N. "
                             "The remaining artists are emitted unchanged. Default 50000 — "
                             "≈ 60 min of API time. Long-tail MB artists rarely surface "
                             "in retrieval anyway.")
    parser.add_argument("--min-popularity", type=int, default=0,
                        help="Skip Spotify lookup for MB artists below this proxy popularity (0..100). "
                             "0 = enrich everything (default).")
    parser.add_argument("--progress-every", type=int, default=500,
                        help="Log progress every N artists.")
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

    # Load all input rows into memory so we can sort by MB proxy
    # popularity and only enrich the top --max-enrich slice. The
    # corpus is ~10 MB / ~170K rows — comfortably fits.
    logger.info("Loading input %s …", args.input)
    all_rows: list[dict] = list(_iter_input(args.input))
    if args.limit:
        all_rows = all_rows[: args.limit]
    all_rows.sort(key=lambda r: float(r.get("listener_popularity") or 0.0),
                  reverse=True)

    # Determine the slice we attempt to enrich.
    enrich_slice = all_rows[: args.max_enrich]
    passthrough = all_rows[args.max_enrich:]
    logger.info(
        "%d rows total — enriching top %d by popularity, %d streamed unchanged",
        len(all_rows), len(enrich_slice), len(passthrough),
    )

    # Pass 1: search every artist in the slice.
    pending: list[tuple[dict, str]] = []   # (mb_row, matched_spotify_id)
    skipped: list[dict] = []
    n_seen = 0
    n_matched = 0
    n_skipped_low_pop = 0
    started = time.time()

    try:
        for mb_row in enrich_slice:
            n_seen += 1

            proxy_pop = float(mb_row.get("listener_popularity") or 0.0) * 100.0
            if proxy_pop < args.min_popularity:
                n_skipped_low_pop += 1
                skipped.append(mb_row)
                continue

            name = str(mb_row.get("name") or "")
            candidates = client.search_artists(name, limit=5)
            match = pick_best_match(
                mb_name=name,
                mb_begin_year=mb_row.get("begin_year"),
                mb_tags=mb_row.get("tags") or [],
                candidates=candidates,
            )
            if match is None:
                skipped.append(mb_row)
            else:
                pending.append((mb_row, match.spotify_id))
                n_matched += 1

            if n_seen % args.progress_every == 0:
                elapsed = time.time() - started
                rate = n_seen / elapsed if elapsed > 0 else 0
                logger.info("Pass 1: %d scanned, %d matched, %d skipped — %.1f artists/sec",
                            n_seen, n_matched, len(skipped) - n_skipped_low_pop, rate)
    except (SpotifyRateLimitedError, SpotifyBackoffBudgetExhausted) as exc:
        # Rate-limit hit. Per design: FAIL the entire run so the
        # circuit breaker in cloud_run_publish.py opens and no further
        # job executions take place until the user resets it.
        # Do NOT write a partial corpus — the existing GCS corpus
        # stays as-is so users keep working with valid data.
        logger.error("Spotify enrichment ABORTED (rate-limited): %s", exc)
        logger.error("Processed %d/%d artists in slice before abort.",
                     n_seen, len(enrich_slice))
        return RATE_LIMIT_EXIT_CODE

    logger.info("Pass 1 done — %d matched, %d unmatched, %d below min-popularity",
                n_matched, len(skipped) - n_skipped_low_pop, n_skipped_low_pop)

    # Pass 2: bulk-fetch details for matched IDs.
    sp_by_id: dict[str, object] = {}
    if pending:
        logger.info("Pass 2: bulk-fetching Spotify details for %d artists …", n_matched)
        try:
            sp_ids = [sp_id for _, sp_id in pending]
            sp_details = client.get_artists(sp_ids)
            sp_by_id = {sp.id: sp for sp in sp_details}
            logger.info("Got details for %d/%d artists", len(sp_details), n_matched)
        except (SpotifyRateLimitedError, SpotifyBackoffBudgetExhausted) as exc:
            logger.error("Spotify enrichment ABORTED in Pass 2 (rate-limited): %s", exc)
            return RATE_LIMIT_EXIT_CODE

    # Pass 3: write the enriched corpus.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_enriched = 0
    n_written = 0
    with _open_jsonl(args.output, "wt") as out:
        for mb_row, sp_id in pending:
            sp = sp_by_id.get(sp_id)
            row = dict(mb_row)
            if sp is not None:
                row["spotify_id"] = sp.id
                row["spotify_popularity"] = sp.popularity
                row["spotify_followers"] = sp.followers
                row["spotify_genres"] = sp.genres
                n_enriched += 1
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1
        for mb_row in skipped:
            out.write(json.dumps(mb_row, ensure_ascii=False) + "\n")
            n_written += 1
        for mb_row in passthrough:
            out.write(json.dumps(mb_row, ensure_ascii=False) + "\n")
            n_written += 1

    elapsed = time.time() - started
    logger.info(
        "Done: %d total rows written (%d enriched = %.1f%% of slice; "
        "%d untouched / passthrough) in %.1f min",
        n_written, n_enriched,
        100.0 * n_enriched / max(1, len(enrich_slice)),
        n_written - n_enriched, elapsed / 60.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())







