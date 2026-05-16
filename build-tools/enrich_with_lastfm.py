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

Pre-flight smoke test:
- Before processing the full slice, fetch a small set of well-known
  MBIDs (Radiohead, Beatles, Daft Punk). A failure here aborts the run
  in <30s instead of after ~18h — protecting against bad API keys,
  egress / DNS misconfig, or Last.fm being globally down.

Checkpoint / resume:
- Every ``--checkpoint-every`` artists, the in-progress output is
  flushed to ``--checkpoint`` (defaults to ``{output}.partial``).
  When ``--checkpoint-gcs-uri`` is set, the checkpoint is also synced
  to GCS so a Cloud Run container restart can pick up where the last
  one left off rather than re-burning 18 h of compute.
- On startup, if the checkpoint exists, already-enriched MBIDs are
  loaded into a skip set and the loop resumes.
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
    LastfmRateLimitedError, LastfmServiceUnavailable, LastfmTransientFailure,
)

logger = logging.getLogger("enrich_with_lastfm")

# Distinct from the Spotify exit code (42) so cloud_run_publish.py
# can report which source rate-limited.
RATE_LIMIT_EXIT_CODE = 43

# Auth-error abort — invalid / suspended API key. Distinct from the
# rate-limit code so a bad key fails the run loudly without tripping
# the per-source halt.flag (which would freeze future builds).
AUTH_ERROR_EXIT_CODE = 44

# Smoke-test failure abort. Distinct again so cloud_run_publish.py
# can log which gate tripped without conflating with rate-limit /
# auth signals.
SMOKE_FAIL_EXIT_CODE = 45

# Default minimum tag weight (0-100) below which Last.fm tags are
# dropped. Last.fm community tags include junk ("seen live", "my
# favourite") at low counts; 30 is a conservative noise floor.
DEFAULT_MIN_TAG_WEIGHT = 30

# Pre-flight smoke MBIDs. Picked because they are very high-traffic
# artists with stable MusicBrainz IDs that have been served from
# Last.fm for ~15 years; if Last.fm cannot return JSON for these,
# something is structurally wrong (key, network, outage) and the run
# should abort before the 18 h enrichment loop.
SMOKE_MBIDS: list[tuple[str, str]] = [
    ("a74b1b7f-71a5-4011-9441-d0b5e4122711", "Radiohead"),
    ("b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d", "The Beatles"),
    ("056e4f3e-d505-4dad-8ec1-d04f521cbb56", "Daft Punk"),
]


def _open_jsonl(path: Path, mode: str):
    # Use ``str(path).endswith(".gz")`` rather than ``path.suffix == ".gz"``:
    # a checkpoint sibling like ``out.jsonl.gz.partial`` should still be
    # written through gzip, but ``Path.suffix`` only returns the last
    # extension (``.partial``) and would silently fall back to plain
    # text — producing a 52 MB "gzip" file that isn't gzip at all.
    opener = gzip.open if str(path).endswith(".gz") else open
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


def _smoke_test(client: LastfmClient, mbids: list[tuple[str, str]]) -> int:
    """Probe Last.fm with a handful of well-known MBIDs.

    Returns 0 on success; on failure returns one of the dedicated
    exit codes (auth / rate-limit / smoke-fail) so the caller can
    abort *before* starting the 18 h enrichment loop. We surface the
    auth and rate-limit codes verbatim so cloud_run_publish.py routes
    them through the existing halt-flag logic; everything else
    collapses to ``SMOKE_FAIL_EXIT_CODE``.
    """
    logger.info("Smoke pre-flight: probing %d known MBIDs …", len(mbids))
    for mbid, label in mbids:
        try:
            info = client.get_artist_info(mbid)
        except LastfmAuthError as exc:
            logger.error("Smoke FAIL: auth error on %s: %s", label, exc)
            return AUTH_ERROR_EXIT_CODE
        except LastfmRateLimitedError as exc:
            logger.error("Smoke FAIL: rate-limited on %s: %s", label, exc)
            return RATE_LIMIT_EXIT_CODE
        except LastfmBackoffBudgetExhausted as exc:
            logger.error("Smoke FAIL: backoff budget exhausted on %s: %s",
                         label, exc)
            return RATE_LIMIT_EXIT_CODE
        except LastfmTransientFailure as exc:
            logger.error("Smoke FAIL: transient failure on %s after retries: %s",
                         label, exc)
            return SMOKE_FAIL_EXIT_CODE
        except Exception as exc:  # noqa: BLE001
            logger.error("Smoke FAIL: unexpected %s on %s: %s",
                         type(exc).__name__, label, exc)
            return SMOKE_FAIL_EXIT_CODE
        if not info.listeners or info.listeners < 1000:
            # All 3 smoke artists have millions of listeners. <1k means
            # the response was structurally OK but semantically wrong
            # (wrong account, sandbox, etc.).
            logger.error(
                "Smoke FAIL: %s reported listeners=%s (expected millions)",
                label, info.listeners,
            )
            return SMOKE_FAIL_EXIT_CODE
        logger.info("Smoke OK: %s listeners=%d", label, info.listeners)
    logger.info("Smoke pre-flight passed.")
    return 0


# ── Checkpoint helpers ────────────────────────────────────────────────


def _load_checkpoint_mbids(path: Path) -> set[str]:
    """Read a checkpoint jsonl[.gz] and return the set of MBIDs already
    written. Empty set when the file does not exist or is unreadable.

    Tolerates partially-written final lines (gzip member truncation).
    """
    if not path.exists() or path.stat().st_size == 0:
        return set()
    seen: set[str] = set()
    try:
        with _open_jsonl(path, "rt") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # Truncated tail line from a crashed previous run —
                    # tolerate, the row will simply be re-enriched.
                    continue
                mbid = (row.get("mbid") or "").strip()
                if mbid:
                    seen.add(mbid)
    except (OSError, EOFError) as exc:
        logger.warning("Checkpoint %s unreadable (%s) — starting fresh.",
                       path, exc)
        return set()
    return seen


def _gcs_blob(uri: str):
    """Return a (bucket, blob) pair for ``gs://bucket/path``. Lazy
    import so unit tests + local dev runs do not require the GCS SDK."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got {uri!r}")
    rest = uri[len("gs://"):]
    bucket_name, _, blob_path = rest.partition("/")
    if not bucket_name or not blob_path:
        raise ValueError(f"Invalid gs:// URI: {uri!r}")
    from google.cloud import storage  # type: ignore  # noqa: PLC0415
    client = storage.Client()
    return client.bucket(bucket_name).blob(blob_path)


def _download_checkpoint_from_gcs(uri: str, dest: Path) -> bool:
    """Download ``uri`` to ``dest`` if it exists. Returns True on success."""
    try:
        blob = _gcs_blob(uri)
        if not blob.exists():
            logger.info("No GCS checkpoint at %s — starting fresh.", uri)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))
        logger.info("Downloaded GCS checkpoint %s → %s (%d bytes)",
                    uri, dest, dest.stat().st_size)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not download GCS checkpoint %s (%s) — "
                       "starting fresh.", uri, exc)
        return False


def _upload_checkpoint_to_gcs(src: Path, uri: str) -> None:
    """Best-effort upload; failures are logged but do not abort the run."""
    try:
        blob = _gcs_blob(uri)
        blob.upload_from_filename(str(src))
        logger.info("Uploaded checkpoint %s → %s", src, uri)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Checkpoint upload to %s failed (%s) — continuing.",
                       uri, exc)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap on artists to process (0 = all). Smoke tests.")
    parser.add_argument("--max-enrich", type=int, default=0,
                        help="Hard ceiling on Last.fm lookups. Top N by MB "
                             "proxy popularity get enriched; remainder is "
                             "emitted unchanged. 0 = enrich all (default).")
    parser.add_argument("--min-popularity", type=int, default=0,
                        help="Skip Last.fm lookup for MB artists below this "
                             "proxy popularity (0..100). 0 = enrich all.")
    parser.add_argument("--min-tag-weight", type=int,
                        default=DEFAULT_MIN_TAG_WEIGHT,
                        help="Drop Last.fm tags below this 0-100 weight. "
                             f"Default {DEFAULT_MIN_TAG_WEIGHT} (community-tag "
                             "noise floor).")
    parser.add_argument("--top-tracks-per-artist", type=int, default=5,
                        help="Attach the artist's N most-played Last.fm "
                             "tracks as `top_tracks`. 0 disables the call "
                             "(saves 1 API request per artist).")
    parser.add_argument("--progress-every", type=int, default=500)
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help="Path for incremental checkpoint output. "
                             "Defaults to {output}.partial. Resumed on restart.")
    parser.add_argument("--checkpoint-every", type=int, default=2000,
                        help="Flush + (optionally) GCS-sync the checkpoint "
                             "every N enriched artists. Default 2000.")
    parser.add_argument("--checkpoint-gcs-uri", type=str, default="",
                        help="Optional gs:// URI to mirror the checkpoint to. "
                             "Lets a Cloud Run container restart resume "
                             "from where the previous one stopped.")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore any existing checkpoint and rebuild "
                             "from scratch.")
    parser.add_argument("--skip-smoke", action="store_true",
                        help="Skip the pre-flight smoke probe. Useful in "
                             "tests; do not set in production.")
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

    # ── Pre-flight smoke probe ────────────────────────────────────────
    if not args.skip_smoke:
        rc = _smoke_test(client, SMOKE_MBIDS)
        if rc != 0:
            return rc

    # ── Resolve checkpoint paths and (optionally) restore from GCS ────
    # Default: insert ".partial" *before* the final extension so the
    # gzip detection in ``_open_jsonl`` continues to fire (e.g.
    # ``out.jsonl.gz`` → ``out.jsonl.partial.gz``).
    if args.checkpoint:
        checkpoint_path = args.checkpoint
    elif args.output.suffix == ".gz":
        checkpoint_path = args.output.with_name(
            args.output.stem + ".partial" + args.output.suffix
        )
    else:
        checkpoint_path = args.output.with_suffix(
            args.output.suffix + ".partial"
        )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    if args.no_resume and checkpoint_path.exists():
        logger.info("--no-resume: deleting stale checkpoint %s", checkpoint_path)
        checkpoint_path.unlink()
    elif args.checkpoint_gcs_uri and not checkpoint_path.exists():
        _download_checkpoint_from_gcs(args.checkpoint_gcs_uri, checkpoint_path)

    seen_mbids = _load_checkpoint_mbids(checkpoint_path)
    if seen_mbids:
        logger.info("Resuming from checkpoint: %d MBIDs already enriched.",
                    len(seen_mbids))

    # ── Load + sort input ─────────────────────────────────────────────
    logger.info("Loading input %s …", args.input)
    all_rows: list[dict] = list(_iter_input(args.input))
    if args.limit:
        all_rows = all_rows[: args.limit]
    all_rows.sort(key=lambda r: float(r.get("listener_popularity") or 0.0),
                  reverse=True)

    if args.max_enrich > 0:
        enrich_slice = all_rows[: args.max_enrich]
        passthrough = all_rows[args.max_enrich:]
    else:
        enrich_slice = all_rows
        passthrough = []
    logger.info(
        "%d rows total — enriching top %d, %d streamed unchanged",
        len(all_rows), len(enrich_slice), len(passthrough),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_seen = 0
    n_enriched = 0
    n_skipped_no_mbid = 0
    n_skipped_low_pop = 0
    n_resumed = 0
    n_written = 0
    last_sync_at = 0
    started = time.time()

    # Append-mode jsonl[.gz]: gzip files concatenate cleanly, so each
    # flushed batch becomes a new gzip member that downstream readers
    # decompress transparently.
    try:
        with _open_jsonl(checkpoint_path, "at") as out:
            for mb_row in enrich_slice:
                n_seen += 1
                row = dict(mb_row)

                mbid = (row.get("mbid") or "").strip()
                proxy_pop = float(row.get("listener_popularity") or 0.0) * 100.0

                if mbid and mbid in seen_mbids:
                    # Already in checkpoint — do not re-enrich and do
                    # not re-emit (it's already on disk).
                    n_resumed += 1
                    continue

                if not mbid:
                    n_skipped_no_mbid += 1
                elif proxy_pop < args.min_popularity:
                    n_skipped_low_pop += 1
                else:
                    info = client.fetch_artist(
                        mbid, top_tracks_n=args.top_tracks_per_artist,
                    )
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
                    if info.top_tracks:
                        row["top_tracks"] = info.top_tracks
                    if (info.listeners is not None
                            or info.playcount is not None
                            or filtered_tags
                            or info.top_tracks):
                        n_enriched += 1

                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_written += 1
                if mbid:
                    seen_mbids.add(mbid)

                # Periodic checkpoint flush + GCS sync.
                if (n_written - last_sync_at) >= args.checkpoint_every:
                    out.flush()
                    if args.checkpoint_gcs_uri:
                        _upload_checkpoint_to_gcs(
                            checkpoint_path, args.checkpoint_gcs_uri,
                        )
                    last_sync_at = n_written

                if n_seen % args.progress_every == 0:
                    elapsed = time.time() - started
                    rate = n_seen / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Progress: %d/%d (resumed %d), %d enriched, "
                        "%.1f artists/sec",
                        n_seen, len(enrich_slice), n_resumed, n_enriched, rate,
                    )

            for mb_row in passthrough:
                out.write(json.dumps(mb_row, ensure_ascii=False) + "\n")
                n_written += 1

    except LastfmAuthError as exc:
        logger.error("Last.fm auth error — aborting: %s", exc)
        return AUTH_ERROR_EXIT_CODE
    except (LastfmRateLimitedError, LastfmBackoffBudgetExhausted,
            LastfmServiceUnavailable) as exc:
        logger.error("Last.fm enrichment ABORTED (rate-limited / unavailable): %s",
                     exc)
        logger.error("Processed %d/%d artists in slice before abort "
                     "(%d resumed). Checkpoint preserved at %s.",
                     n_seen, len(enrich_slice), n_resumed, checkpoint_path)
        # Best-effort: push the latest checkpoint up so the next
        # container can resume rather than start from zero.
        if args.checkpoint_gcs_uri:
            _upload_checkpoint_to_gcs(checkpoint_path, args.checkpoint_gcs_uri)
        return RATE_LIMIT_EXIT_CODE

    # Successful completion: promote checkpoint → output (atomic
    # rename on POSIX/Windows when on the same filesystem).
    if args.output.exists():
        args.output.unlink()
    checkpoint_path.replace(args.output)
    logger.info("Promoted checkpoint → %s", args.output)

    # Best-effort: clear the GCS checkpoint so the next scheduled run
    # does not accidentally resume from a stale set.
    if args.checkpoint_gcs_uri:
        try:
            blob = _gcs_blob(args.checkpoint_gcs_uri)
            if blob.exists():
                blob.delete()
                logger.info("Cleared completed GCS checkpoint %s",
                            args.checkpoint_gcs_uri)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not clear GCS checkpoint %s: %s",
                           args.checkpoint_gcs_uri, exc)

    elapsed = time.time() - started
    logger.info(
        "Done: %d total rows written (%d enriched = %.1f%% of slice; "
        "%d resumed, %d no-mbid, %d low-pop) in %.1f min",
        n_written + n_resumed, n_enriched,
        100.0 * n_enriched / max(1, len(enrich_slice)),
        n_resumed, n_skipped_no_mbid, n_skipped_low_pop, elapsed / 60.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
