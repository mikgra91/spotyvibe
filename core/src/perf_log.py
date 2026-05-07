"""M3 (2026-05-07) — per-run perf summary persisted to a local sqlite file.

One row per playlist generation. Schema is small on purpose — enough to
answer "did latency / cost / quality drift over N weeks?" with a single
SQL query, without needing to re-run the eval harness.

Columns
-------
``run_id``         — UUID; PRIMARY KEY.
``ts_utc``         — ISO-8601 timestamp of the row insert.
``model``          — provider:model identifier (e.g. ``"openai:gpt-5.4"``).
``stage_metrics``  — JSON dump of ``{stage: {duration_s, calls,
                     tokens_in, tokens_out}}`` (E1 surface, see
                     ``core/src/trace.py``).
``tracks_found``   — int; tracks the run finalised with.
``tracks_target``  — int; what the user requested (so found-rate is
                     computable in SQL: ``tracks_found / tracks_target``).
``exhausted``      — int (0/1). 1 when the run hit the GPT-exhaustion
                     guard (Stage 3 kept hitting already-known tracks).
``error``          — short message string, or NULL when the run
                     succeeded. Long stack traces live in the trace
                     bundle, not here.
``schema_version`` — int; bumped on incompatible column changes so
                     migrations can be detected.

The sqlite file lives at ``_APP_DIR / "perf_log.sqlite"`` next to
credentials and other per-user state. Pure-stdlib (no SQLAlchemy /
ORM) so cold-start cost is one ``sqlite3.connect``. Concurrency: the
generation pipeline is single-flight per process (see ``app.py``
``_runs_lock``) so no contention is expected; if a second writer ever
shows up, sqlite's default serialised mode handles it.

Failures are logged + swallowed. The perf log is diagnostic — it must
never break a generation run.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_SCHEMA_VERSION = 1
_DEFAULT_DB_NAME = "perf_log.sqlite"


def _resolve_db_path(db_path: Path | None = None) -> Path | None:
    if db_path is not None:
        return Path(db_path)
    try:
        from config import _APP_DIR  # type: ignore[attr-defined]
        return Path(_APP_DIR) / _DEFAULT_DB_NAME
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("perf_log: cannot resolve _APP_DIR (%s)", exc)
        return None


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_perf (
            run_id          TEXT PRIMARY KEY,
            ts_utc          TEXT NOT NULL,
            model           TEXT,
            stage_metrics   TEXT NOT NULL,
            tracks_found    INTEGER NOT NULL,
            tracks_target   INTEGER NOT NULL,
            exhausted       INTEGER NOT NULL DEFAULT 0,
            error           TEXT,
            schema_version  INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    return conn


def record_run(
    run_id: str,
    *,
    stage_metrics: dict[str, dict[str, Any]] | None,
    model: str | None,
    tracks_found: int,
    tracks_target: int,
    exhausted: bool = False,
    error: str | None = None,
    db_path: Path | None = None,
) -> Path | None:
    """Insert one row describing a completed run.

    Returns the database path on success, ``None`` on any failure.
    Idempotent on ``run_id`` (``INSERT OR REPLACE``) so a duplicate
    record_run call from a retry path doesn't crash.
    """
    if not run_id:
        return None
    resolved = _resolve_db_path(db_path)
    if resolved is None:
        return None
    try:
        conn = _connect(resolved)
        try:
            payload = json.dumps(stage_metrics or {}, ensure_ascii=False)
            conn.execute(
                """
                INSERT OR REPLACE INTO run_perf
                (run_id, ts_utc, model, stage_metrics, tracks_found,
                 tracks_target, exhausted, error, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    model or None,
                    payload,
                    int(tracks_found),
                    int(tracks_target),
                    1 if exhausted else 0,
                    error,
                    _SCHEMA_VERSION,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return resolved
    except Exception as exc:
        logger.warning("perf_log.record_run failed (%s)", exc)
        return None


def read_runs(
    *,
    limit: int = 100,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent *limit* rows, newest first.

    Convenience for ad-hoc inspection / unit tests. Stage_metrics is
    JSON-decoded back to a dict.
    """
    resolved = _resolve_db_path(db_path)
    if resolved is None or not resolved.exists():
        return []
    try:
        conn = _connect(resolved)
        try:
            rows = conn.execute(
                """
                SELECT run_id, ts_utc, model, stage_metrics, tracks_found,
                       tracks_target, exhausted, error, schema_version
                FROM run_perf
                ORDER BY ts_utc DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("perf_log.read_runs failed (%s)", exc)
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            metrics = json.loads(r[3]) if r[3] else {}
        except (TypeError, ValueError):
            metrics = {}
        out.append({
            "run_id": r[0],
            "ts_utc": r[1],
            "model": r[2],
            "stage_metrics": metrics,
            "tracks_found": r[4],
            "tracks_target": r[5],
            "exhausted": bool(r[6]),
            "error": r[7],
            "schema_version": r[8],
        })
    return out


__all__ = ["record_run", "read_runs"]
