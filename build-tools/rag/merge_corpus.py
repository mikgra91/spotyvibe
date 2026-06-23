"""Layered merge/update for the RAG corpus — one job per source.

The corpus is built from three independently-owned layers, each keyed by
``mbid``:

- **MusicBrainz base** — ``name, begin_year, tags, tag_weights,
  listener_popularity``. Rebuilt from the monthly MB dump by
  ``build_rag_corpus.py``.
- **Last.fm** — ``lastfm_listeners, lastfm_playcount, lastfm_tags,
  top_tracks``. Fetched by ``run_lastfm_enrichment.py``.
- **AI** — ``ai_tags, ai_confidence``. Produced locally (manually, in
  intervals) and shipped as a sibling overlay file.

Historically the Cloud Run cycle *rebuilt everything from scratch* every
run — including re-fetching all ~175k artists from Last.fm (~29 h). That
is wasteful: an MB tag change does not change an artist's Last.fm data,
and the AI layer is unrelated to both. This module makes each layer
update **independently** — a rebuild of one layer carries the other two
forward by ``mbid`` instead of discarding them.

``merge_layers`` is pure (no I/O) so it is cheap to unit-test against
real corpus rows. The CLI wraps it for the Cloud Run wiring: it produces
the merged corpus and, optionally, a *seed checkpoint* containing only
the rows that already carry Last.fm data, so the Last.fm enrichment pass
skips them and fetches only the delta (new / never-enriched artists).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger("merge_corpus")

# ── Field ownership ──────────────────────────────────────────────────
# ``mbid`` is the stable identity key (not owned by any single layer).
# Each tuple below is the exclusive set of fields a layer may write; a
# layer update never touches another layer's fields.
MB_FIELDS: tuple[str, ...] = (
    "name", "begin_year", "tags", "tag_weights", "listener_popularity",
    # Legacy MB-owned fields — dropped by the current builder but kept
    # here so older published corpora still merge cleanly.
    "sort_name", "country", "end_year",
)
LASTFM_FIELDS: tuple[str, ...] = (
    "lastfm_listeners", "lastfm_playcount", "lastfm_tags", "top_tracks",
)
AI_FIELDS: tuple[str, ...] = (
    "ai_tags", "ai_confidence",
)

# Fields that decide whether the MB layer genuinely changed. Excludes
# ``listener_popularity`` because it is a *derived rank* recomputed every
# build over the whole pool — it drifts for almost every artist on every
# run without the artist's MB record having changed, so including it
# would defeat the skip-if-unchanged gate.
_MB_IDENTITY_FIELDS: tuple[str, ...] = (
    "name", "begin_year", "tags", "tag_weights", "sort_name",
    "country", "end_year",
)


def _pick(row: dict | None, fields: tuple[str, ...]) -> dict:
    """Return the subset of *fields* present (and non-None) in *row*."""
    if not row:
        return {}
    return {f: row[f] for f in fields if row.get(f) is not None}


def mb_content_hash(row: dict | None) -> str:
    """Stable hash of the MusicBrainz-owned identity fields of *row*.

    Two rows with the same MB record (same name/year/tags) hash equal
    regardless of enrichment or popularity-rank drift, so the merge can
    skip artists whose MB record did not change between dumps.
    """
    payload = {f: (row.get(f) if row else None) for f in _MB_IDENTITY_FIELDS}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def merge_layers(
    new_mb_rows: list[dict],
    prev_rows: list[dict] | None = None,
    *,
    lastfm_overlay: dict[str, dict] | None = None,
    ai_overlay: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """Merge the three layers by ``mbid`` into a single corpus.

    Authority / carry-forward rules:

    - **MB fields** always come from *new_mb_rows* (the fresh build is
      authoritative for the MB layer).
    - **Last.fm fields** come from *lastfm_overlay* when it has an entry
      for the mbid (a fresh fetch), otherwise they are *carried forward*
      from *prev_rows* (the previously-published corpus). An MB rebuild
      therefore never loses Last.fm data.
    - **AI fields** come from *ai_overlay* when present, otherwise carried
      forward from *prev_rows*. The AI layer survives a rebuild of either
      other layer.

    Artists in *prev_rows* but absent from *new_mb_rows* are dropped
    (the MB record no longer exists). New mbids are added.

    Returns ``(merged_rows, stats)``. ``stats["needs_lastfm"]`` is the
    list of mbids that still lack any Last.fm field after the merge — the
    exact delta the Last.fm pass must fetch.
    """
    prev_by_mbid: dict[str, dict] = {
        r["mbid"]: r for r in (prev_rows or []) if r.get("mbid")
    }
    lfm_ov = lastfm_overlay or {}
    ai_ov = ai_overlay or {}

    merged: list[dict] = []
    stats = {
        "total": 0, "added": 0, "removed": 0,
        "mb_changed": 0, "mb_unchanged": 0,
        "lastfm_carried": 0, "lastfm_fresh": 0,
        "ai_carried": 0, "ai_fresh": 0,
        "needs_lastfm": [],
    }
    seen_prev: set[str] = set()

    for nmb in new_mb_rows:
        mbid = (nmb.get("mbid") or "").strip()
        if not mbid:
            # No identity key → cannot be merged/carried. Keep MB fields
            # only; it will always be treated as "needs Last.fm".
            row = {"mbid": ""}
            row.update(_pick(nmb, MB_FIELDS))
            merged.append(row)
            stats["total"] += 1
            stats["added"] += 1
            stats["needs_lastfm"].append("")
            continue

        prev = prev_by_mbid.get(mbid)
        row: dict = {"mbid": mbid}
        row.update(_pick(nmb, MB_FIELDS))  # fresh MB layer is authoritative

        # Classify the MB change for stats / skip accounting.
        if prev is None:
            stats["added"] += 1
        else:
            seen_prev.add(mbid)
            if mb_content_hash(prev) == mb_content_hash(nmb):
                stats["mb_unchanged"] += 1
            else:
                stats["mb_changed"] += 1

        # ── Last.fm layer ────────────────────────────────────────────
        if mbid in lfm_ov:
            lfm = _pick(lfm_ov[mbid], LASTFM_FIELDS)
            if lfm:
                stats["lastfm_fresh"] += 1
        else:
            lfm = _pick(prev, LASTFM_FIELDS)
            if lfm:
                stats["lastfm_carried"] += 1
        row.update(lfm)

        # ── AI layer ─────────────────────────────────────────────────
        if mbid in ai_ov:
            ai = _pick(ai_ov[mbid], AI_FIELDS)
            if ai:
                stats["ai_fresh"] += 1
        else:
            ai = _pick(prev, AI_FIELDS)
            if ai:
                stats["ai_carried"] += 1
        row.update(ai)

        if not _pick(row, LASTFM_FIELDS):
            stats["needs_lastfm"].append(mbid)

        merged.append(row)
        stats["total"] += 1

    stats["removed"] = len(prev_by_mbid) - len(seen_prev)
    return merged, stats


# ── I/O helpers (CLI only) ───────────────────────────────────────────

def _iter_jsonl(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _read_overlay(path: Path) -> dict[str, dict]:
    """Read an mbid-keyed overlay file: ``{mbid: {fields...}}`` or the
    enrichment-probe ``{schema_version, entries: {mbid: {...}}}`` shape."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data and isinstance(data["entries"], dict):
        return data["entries"]
    return data if isinstance(data, dict) else {}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as fh:  # type: ignore[arg-type]
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-mb", type=Path, required=True,
                        help="Freshly built MB-only corpus (jsonl[.gz]).")
    parser.add_argument("--previous", type=Path, default=None,
                        help="Previously published corpus (jsonl[.gz]) to "
                             "carry Last.fm + AI fields forward from. "
                             "Omit for a first-ever build.")
    parser.add_argument("--lastfm-overlay", type=Path, default=None,
                        help="Optional mbid-keyed Last.fm overlay (fresh fetch).")
    parser.add_argument("--ai-overlay", type=Path, default=None,
                        help="Optional mbid-keyed AI overlay (ai_tags_overlay.json).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write the merged corpus here (jsonl[.gz]).")
    parser.add_argument("--seed-checkpoint", type=Path, default=None,
                        help="Write only the rows that already carry Last.fm "
                             "data, as plain JSONL, for pre-seeding the "
                             "Last.fm enrichment checkpoint so the pass "
                             "fetches only the delta.")
    args = parser.parse_args(argv)

    new_mb = list(_iter_jsonl(args.new_mb))
    prev = list(_iter_jsonl(args.previous)) if args.previous and args.previous.exists() else []
    lfm_ov = _read_overlay(args.lastfm_overlay) if args.lastfm_overlay else None
    ai_ov = _read_overlay(args.ai_overlay) if args.ai_overlay else None

    merged, stats = merge_layers(new_mb, prev, lastfm_overlay=lfm_ov, ai_overlay=ai_ov)
    logger.info(
        "Merged %d rows: +%d added, -%d removed, %d mb-changed, %d mb-unchanged | "
        "Last.fm: %d carried, %d fresh, %d need fetch | AI: %d carried, %d fresh",
        stats["total"], stats["added"], stats["removed"],
        stats["mb_changed"], stats["mb_unchanged"],
        stats["lastfm_carried"], stats["lastfm_fresh"], len(stats["needs_lastfm"]),
        stats["ai_carried"], stats["ai_fresh"],
    )

    if args.out:
        _write_jsonl(args.out, merged)
        logger.info("Wrote merged corpus → %s", args.out)

    if args.seed_checkpoint:
        seeded = [r for r in merged if _pick(r, LASTFM_FIELDS)]
        _write_jsonl(args.seed_checkpoint, seeded)
        logger.info("Wrote %d Last.fm-carrying rows → %s (seed checkpoint)",
                    len(seeded), args.seed_checkpoint)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
