"""Per-run trace bundle for deterministic debugging (F9, 2026-05-01).

Production code currently logs aggregate telemetry (``eval.jsonl``
rows: counts, statuses, token totals) but no per-run record of
*which* artists Stage 1 retrieved, *which* tags drove their score,
*which* avoid traits Stage 2 was given, or *what* Stage 3 actually
saw in its prompt. That gap blocks every diagnosis the moment it
moves past "the counts look wrong" and into "why did artist X
appear / not appear?". See ``context/claudeAnalyse.md`` F9.

This module fixes that with a thin singleton that the production
pipeline writes into during a generation run and serialises to a
single JSON file per run when the run finishes:

    %LOCALAPPDATA%/spotyvibe/debug/<run_id>/trace.json

Singleton-per-run pattern matches the existing ``_LAST_RETRIEVAL_META``
/ ``_LAST_PROMPT_COMPONENTS`` pattern elsewhere in the codebase. Not
thread-safe — same single-flight assumption as the rest of the
suggestion pipeline (one playlist generation at a time per user).

Capture is gated on :func:`config.get_debug_mode` so production
deployments without DEBUG_MODE pay zero overhead. When tracing is
off, every public function on this module is a fast no-op.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceBundle:
    """Container for one playlist run's diagnostic data.

    Sections are populated incrementally as each pipeline stage runs;
    a missing section means that stage either didn't run (e.g. legacy
    fallback) or ran but didn't surface any data through ``record``.
    The ``stages`` dict mirrors the pipeline order (stage1 / stage2 /
    stage3 / postfilter / spotify) so a future renderer can lay them
    out chronologically without parsing.
    """
    run_id: str
    started_at: float = field(default_factory=time.time)
    profile: dict | None = None
    stages: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 3),
            "profile": self.profile,
            "stages": self.stages,
        }


# Singleton holding the active run's bundle. ``None`` when tracing is
# off or no run is in flight.
_CURRENT: TraceBundle | None = None


def _enabled() -> bool:
    """Return True when tracing should write data.

    Reads ``config.get_debug_mode`` lazily so the import order between
    this module and ``config`` doesn't matter and tests can flip the
    flag mid-test via ``os.environ``. Falls back to False on any error
    so a misconfigured environment never breaks production.
    """
    try:
        from config import get_debug_mode
        return bool(get_debug_mode())
    except Exception:  # pragma: no cover — defensive
        return False


def start_trace(run_id: str, profile: dict | None = None) -> None:
    """Begin a new run trace. Idempotent for the same run_id.

    Called by the request dispatcher (``app.py /api/run``) at the
    start of a playlist generation. Subsequent ``record`` calls
    populate the bundle until :func:`finalize_trace` writes it out.

    No-op when DEBUG_MODE is off — production runs pay nothing.
    """
    global _CURRENT
    if not _enabled():
        _CURRENT = None
        return
    # Serialise the profile shallowly (we don't want to hold a live
    # reference that mutates during the run). Use json round-trip so
    # nested dicts/lists are independently snapshotted.
    try:
        prof_snapshot = json.loads(json.dumps(profile, default=str)) if profile else None
    except (TypeError, ValueError):
        prof_snapshot = {"_unserialisable": str(type(profile))}
    _CURRENT = TraceBundle(run_id=run_id, profile=prof_snapshot)


def is_active() -> bool:
    """Return True when there is an active run trace accepting writes."""
    return _CURRENT is not None


def record(stage: str, data: Any) -> None:
    """Persist a stage's diagnostic payload into the current trace.

    *stage* is a free-form key like ``"stage1_query"`` /
    ``"stage2_response"`` / ``"spotify_search"``. Repeated writes to
    the same key overwrite — callers that need a list (e.g. per-track
    Spotify searches) should append into the value themselves before
    handing it to ``record``, or use :func:`append`.

    The payload is shallow-cloned via JSON round-trip so callers can
    mutate the original after handing it over. Unserialisable fields
    (e.g. dataclass instances, numpy arrays) are stringified rather
    than raising — the trace must never break a generation run.
    """
    if _CURRENT is None:
        return
    try:
        cloned = json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError):
        cloned = {"_unserialisable": repr(data)[:500]}
    _CURRENT.stages[stage] = cloned


def append(stage: str, item: Any) -> None:
    """Append *item* to a list under *stage* (creating the list if absent).

    Use this for per-iteration data — Spotify searches per track,
    Stage-3 batches, etc. Same serialisation contract as
    :func:`record` and same fail-safe behaviour when tracing is off.
    """
    if _CURRENT is None:
        return
    try:
        cloned = json.loads(json.dumps(item, default=str))
    except (TypeError, ValueError):
        cloned = {"_unserialisable": repr(item)[:500]}
    bucket = _CURRENT.stages.get(stage)
    if not isinstance(bucket, list):
        bucket = []
        _CURRENT.stages[stage] = bucket
    bucket.append(cloned)


def finalize_trace(base_dir: Path | None = None) -> Path | None:
    """Write the current trace to ``<base_dir>/<run_id>/trace.json``.

    Returns the path on success, None when tracing was off or no run
    was active. Always clears ``_CURRENT`` so the next ``start_trace``
    starts clean even if writing failed.

    The directory is created on demand. Errors are logged and
    swallowed — the trace is diagnostic, never load-bearing.
    """
    global _CURRENT
    if _CURRENT is None:
        return None
    bundle = _CURRENT
    _CURRENT = None  # clear before write so a write-failure can't leak

    if base_dir is None:
        try:
            from config import DEBUG_TRACE_DIR
            base_dir = DEBUG_TRACE_DIR
        except Exception as exc:
            logger.warning("trace finalize: cannot resolve base dir (%s)", exc)
            return None

    try:
        run_dir = Path(base_dir) / bundle.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        out = run_dir / "trace.json"
        out.write_text(
            json.dumps(bundle.to_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("[trace] wrote %s (%d stages)", out, len(bundle.stages))
        return out
    except Exception as exc:
        logger.warning("trace finalize: write failed (%s)", exc)
        return None


def reset_for_test() -> None:
    """Test-only helper: clear the singleton without writing.

    Lets unit tests start fresh without depending on environment state.
    Production code should not call this.
    """
    global _CURRENT
    _CURRENT = None


__all__ = [
    "TraceBundle",
    "start_trace",
    "is_active",
    "record",
    "append",
    "finalize_trace",
    "reset_for_test",
]
