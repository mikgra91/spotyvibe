"""Enrich the RAG corpus with Last.fm metadata (Phase B).

Reads ``--input artists.jsonl[.gz]`` (the corpus produced by
``build_rag_corpus.py`` and optionally already enriched by
``enrich_with_spotify.py``), looks each MBID up on Last.fm, and writes
``--output enriched.jsonl[.gz]`` with three additive fields:

- ``lastfm_listeners`` (int | None)
- ``lastfm_playcount`` (int | None)
- ``lastfm_tags``      (list[ [tag, weight 0-100] ])

Rows without a usable ``mbid`` are emitted **unchanged** — the runtime
treats unenriched rows as legacy and falls back to MB tags + the proxy
popularity. Backward compatible.

Activation:
- ``LASTFM_API_KEY``  must be set (skip cleanly with passthrough copy
  when absent so the Cloud Run build stays green pre-provisioning).
- ``DISABLE_LASTFM_ENRICHMENT=1`` forces passthrough.

Rate-limit safety: ``LastfmRateLimitedError`` (Retry-After exceeds the
safety cap) and ``LastfmBackoffBudgetExhausted`` exit with
:data:`RATE_LIMIT_EXIT_CODE` (=43) so ``cloud_run_publish.py`` can trip
its circuit breaker without confusing Last.fm bans with the Spotify
ones (=42).
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

from lastfm_enrichment.client import (  # noqa: E402
    LastfmAuthError, LastfmBackoffBudgetExhausted, LastfmClient,
    LastfmRateLimitedError,
)

logger = logging.getLogger("enrich_with_lastfm")

# Distinct from the Spotify exit code (42) so cloud_run_publish.py
# can report which source rate-limited.
RATE_LIMIT_EXIT_CODE = 43

# Auth-error abort — invalid / suspended API key. Distinct from the
# rate-limit code so a bad key fails the run loudly without tripping
# the per-source halt.flag (which would freeze future builds).
AUTH_ERROR_EXIT_CODE = 44

# Default minimum tag weight (0-100) below which Last.fm tags are
# dropped. Last.fm community tags include junk ("seen live", "my
# favourite") at low counts; 30 is a conservative noise floor.
DEFAULT_MIN_TAG_WEIGHT = 30


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


def _passthrough(input_path: Path, output_path: Path) -> int:
    """Stream input → output unchanged. Used when enrichment is disabled."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with _open_jsonl(input_path, "rt") as src, _open_jsonl(output_path, "wt") as dst:
        for line in src:
            dst.write(line)
            n += 1
    logger.info("Passthrough: %d lines copied %s → %s", n, input_path, output_path)
    return n


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap on artists to process (0 = all). Smoke tests.")
    parser.add_argument("--max-enrich", type=int, default=170_000,
                        help="Hard ceiling on Last.fm lookups. Top N by MB "
                             "proxy popularity get enriched; remainder is "
                             "emitted unchanged. Default 170000 ≈ entire MB.")
    parser.add_argument("--min-popularity", type=int, default=0,
                        help="Skip Last.fm lookup for MB artists below this "
                             "proxy popularity (0..100). 0 = enrich all.")
    parser.add_argument("--min-tag-weight", type=int,
                        default=DEFAULT_MIN_TAG_WEIGHT,
                        help="Drop Last.fm tags below this 0-100 weight. "
                             f"Default {DEFAULT_MIN_TAG_WEIGHT} (community-tag "
                             "noise floor).")
    parser.add_argument("--progress-every", type=int, default=500)
    args = parser.parse_args(argv)

    if not args.input.exists():
        logger.error("Input not found: %s", args.input)
        return 1

    if os.environ.get("DISABLE_LASTFM_ENRICHMENT") == "1":
        logger.info("DISABLE_LASTFM_ENRICHMENT=1 — skipping enrichment.")
        _passthrough(args.input, args.output)
        return 0

    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "LASTFM_API_KEY not set — emitting input unchanged. Provision "
            "the secret in Cloud Run to enable Last.fm enrichment."
        )
        _passthrough(args.input, args.output)
        return 0

    client = LastfmClient(api_key)

    logger.info("Loading input %s …", args.input)
    all_rows: list[dict] = list(_iter_input(args.input))
    if args.limit:
        all_rows = all_rows[: args.limit]
    all_rows.sort(key=lambda r: float(r.get("listener_popularity") or 0.0),
                  reverse=True)

    enrich_slice = all_rows[: args.max_enrich]
    passthrough = all_rows[args.max_enrich:]
    logger.info(
        "%d rows total — enriching top %d, %d streamed unchanged",
        len(all_rows), len(enrich_slice), len(passthrough),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_seen = 0
    n_enriched = 0
    n_skipped_no_mbid = 0
    n_skipped_low_pop = 0
    n_written = 0
    started = time.time()

    try:
        with _open_jsonl(args.output, "wt") as out:
            for mb_row in enrich_slice:
                n_seen += 1
                row = dict(mb_row)

                mbid = (row.get("mbid") or "").strip()
                proxy_pop = float(row.get("listener_popularity") or 0.0) * 100.0

                if not mbid:
                    n_skipped_no_mbid += 1
                elif proxy_pop < args.min_popularity:
                    n_skipped_low_pop += 1
                else:
                    info = client.fetch_artist(mbid)
                    if info.listeners is not None:
                        row["lastfm_listeners"] = info.listeners
                    if info.playcount is not None:
                        row["lastfm_playcount"] = info.playcount
                    filtered_tags = [
                        [name, weight] for name, weight in info.tags
                        if weight >= args.min_tag_weight
                    ]
                    if filtered_tags:
                        row["lastfm_tags"] = filtered_tags
                    if (info.listeners is not None
                            or info.playcount is not None
                            or filtered_tags):
                        n_enriched += 1

                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_written += 1

                if n_seen % args.progress_every == 0:
                    elapsed = time.time() - started
                    rate = n_seen / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Progress: %d/%d, %d enriched, %.1f artists/sec",
                        n_seen, len(enrich_slice), n_enriched, rate,
                    )

            for mb_row in passthrough:
                out.write(json.dumps(mb_row, ensure_ascii=False) + "\n")
                n_written += 1

    except LastfmAuthError as exc:
        logger.error("Last.fm auth error — aborting: %s", exc)
        return AUTH_ERROR_EXIT_CODE
    except (LastfmRateLimitedError, LastfmBackoffBudgetExhausted) as exc:
        logger.error("Last.fm enrichment ABORTED (rate-limited): %s", exc)
        logger.error("Processed %d/%d artists in slice before abort.",
                     n_seen, len(enrich_slice))
        return RATE_LIMIT_EXIT_CODE

    elapsed = time.time() - started
    logger.info(
        "Done: %d total rows written (%d enriched = %.1f%% of slice; "
        "%d no-mbid, %d low-pop) in %.1f min",
        n_written, n_enriched,
        100.0 * n_enriched / max(1, len(enrich_slice)),
        n_skipped_no_mbid, n_skipped_low_pop, elapsed / 60.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
