"""Late-verify pass — batched ground-truth verification over a completed
eval session that ran in ``null`` / ``overlay`` / ``l0_l1`` mode.

When the harness runs in a non-spotify ``verify_mode`` to save time and
quota, Stage-3-emitted track titles are NOT validated against Spotify.
This script reads the resulting ``eval.jsonl`` slices, pulls every
unique (artist, track) pair out of the ``batch_summary`` rows, runs
``SpotifyVerifier`` against them in one batch, and writes the verdicts
to ``late_verify.json`` next to each slice.

Use it AFTER a fast eval to spend Spotify quota in a controlled,
deduplicated batch — typically 10–50 unique tracks vs the 300–500
per-call total a `--verify-mode spotify` run would have made.

Usage:
    python -m evaluation.late_verify <results-dir>
    python -m evaluation.late_verify <results-dir>/<per-run-dir>

Idempotent: re-running over the same dir re-uses the existing
``late_verify.json`` cache.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("late_verify")


# ── Track extraction ─────────────────────────────────────────────────

def iter_tracks_from_eval_log(path: Path) -> Iterable[dict[str, str]]:
    """Yield each unique ``{"artist": ..., "track": ...}`` from the
    ``batch_summary`` rows in an eval.jsonl slice. Dedup is via a
    case-insensitive ``(artist, track)`` key so the same pick across
    multiple batches is verified once."""
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") != "batch_summary":
                continue
            for entry in (row.get("suggested_playlist") or []):
                a = str(entry.get("artist") or "").strip()
                t = str(entry.get("track")  or "").strip()
                if not a or not t:
                    continue
                key = (a.lower(), t.lower())
                if key in seen:
                    continue
                seen.add(key)
                yield {"artist": a, "track": t}


# ── Verification ─────────────────────────────────────────────────────

def verify_tracks(tracks: list[dict[str, str]], verifier: Any,
                  *, sleep_between: float = 0.0) -> dict[str, Any]:
    """Run *verifier* across *tracks* sequentially. Returns a summary
    dict suitable for ``json.dump``.

    ``sleep_between`` adds an inter-call delay (eval-harness convention
    for serial mode); default 0 because verifiers manage their own
    rate limits.
    """
    out: list[dict[str, Any]] = []
    found = 0
    for t in tracks:
        try:
            kind, payload = verifier.verify(t)
        except Exception as exc:                                       # noqa: BLE001
            out.append({"artist": t["artist"], "track": t["track"],
                         "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        if kind == "found":
            found += 1
            out.append({"artist": t["artist"], "track": t["track"],
                         "status": "found",
                         "uri":          payload.get("uri"),
                         "track_id":     payload.get("track_id"),
                         "release_date": payload.get("release_date"),
                         "verified_by":  payload.get("verified_by") or
                                         getattr(verifier, "name", "?")})
        else:
            out.append({"artist": t["artist"], "track": t["track"],
                         "status": "not_found"})
        if sleep_between > 0:
            time.sleep(sleep_between)
    return {
        "total":     len(tracks),
        "found":     found,
        "not_found": len(tracks) - found - sum(1 for r in out if r["status"] == "error"),
        "errors":    sum(1 for r in out if r["status"] == "error"),
        "results":   out,
    }


# ── Per-directory driver ─────────────────────────────────────────────

def process_run_dir(run_dir: Path, verifier: Any, *,
                     sleep_between: float = 0.0,
                     force: bool = False) -> dict[str, Any] | None:
    """Process one per-run directory. Returns the summary dict (also
    written to ``late_verify.json`` in the directory), or None when
    there's no eval.jsonl to process."""
    eval_log = run_dir / "eval.jsonl"
    if not eval_log.exists():
        logger.info("Skip %s — no eval.jsonl", run_dir)
        return None

    out_path = run_dir / "late_verify.json"
    if out_path.exists() and not force:
        logger.info("Skip %s — late_verify.json already present (--force to redo)",
                    run_dir)
        return json.loads(out_path.read_text(encoding="utf-8"))

    tracks = list(iter_tracks_from_eval_log(eval_log))
    if not tracks:
        logger.info("Skip %s — no batch_summary tracks", run_dir)
        return None

    logger.info("Verifying %d unique tracks in %s …", len(tracks), run_dir.name)
    summary = verify_tracks(tracks, verifier, sleep_between=sleep_between)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    logger.info("  found=%d/%d (%.1f%%) — wrote %s",
                summary["found"], summary["total"],
                100.0 * summary["found"] / max(1, summary["total"]),
                out_path.name)
    return summary


def discover_run_dirs(root: Path) -> list[Path]:
    """If *root* contains an ``eval.jsonl`` it IS a per-run dir; else
    treat it as a session root and return every subdir containing one."""
    if (root / "eval.jsonl").exists():
        return [root]
    return sorted([p for p in root.iterdir()
                    if p.is_dir() and (p / "eval.jsonl").exists()])


# ── CLI ─────────────────────────────────────────────────────────────

def _build_default_verifier():
    """Build a ``SpotifyVerifier`` against the user's live Spotify
    client. Only called when the CLI actually runs (so unit tests can
    inject a fake verifier without ever needing OAuth)."""
    import config
    config.load_config()
    from core.src.playlist import get_spotify_client
    from core.src.verify import SpotifyVerifier
    return SpotifyVerifier(shared_sp=get_spotify_client())


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path,
                        help="Session results dir OR a single per-run dir.")
    parser.add_argument("--force", action="store_true",
                        help="Re-verify even when late_verify.json already exists.")
    parser.add_argument("--sleep-ms", type=int, default=0,
                        help="Inter-call sleep (ms). Default 0 (verifiers manage "
                             "their own throttle).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if not args.path.exists():
        logger.error("Path not found: %s", args.path)
        return 2

    run_dirs = discover_run_dirs(args.path)
    if not run_dirs:
        logger.error("No per-run dirs with eval.jsonl found under %s", args.path)
        return 3

    verifier = _build_default_verifier()
    sleep_between = args.sleep_ms / 1000.0

    total_found = total_seen = 0
    for d in run_dirs:
        s = process_run_dir(d, verifier, sleep_between=sleep_between,
                             force=args.force)
        if s is not None:
            total_found += s["found"]
            total_seen  += s["total"]

    logger.info("Done. Across %d run-dir(s): found=%d/%d (%.1f%%).",
                len(run_dirs), total_found, total_seen,
                100.0 * total_found / max(1, total_seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
