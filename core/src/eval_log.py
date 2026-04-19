"""Per-suggestion JSONL eval log for offline hallucination analysis.

Writes one JSON line per AI-suggested track to ``EVAL_LOG_FILE`` so the
RAG / model A/B work documented in
``documentation/guides/rag-implementation.md`` can be measured with
pandas/Jupyter instead of by hand.

Schema (one object per line)::

    {"ts": "2026-04-19T10:23:45Z",
     "run_id": "uuid",
     "batch_num": 1,
     "model": "gpt-5-mini",
     "rag_enabled": true,
     "rag_corpus_version": "2026-04-19" | null,
     "candidate_pool_size": 20,
     "profile_id": "...",
     "profile_hash": "abcd1234",
     "artist": "...",
     "track": "...",
     "found_on_spotify": true | false,
     "in_candidate_pool": true | false | null,
     "rationale_types": ["profile_match", "artist_match"]}

Gated on ``DEBUG_MODE`` (matches ``utils.app_log``); a no-op when debug
is off so production users don't pay for an analysis-only file.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_profile_hash(profile: dict) -> str:
    """Short, stable hash of the profile fields that drive suggestions.

    Hash is over ``must_have`` + ``avoid`` + ``soft_preferences`` + the
    confirmed-artists set. Listening history is excluded so the hash
    stays comparable across runs of the *same configuration*.
    """
    relevant = {
        "must_have": profile.get("must_have"),
        "avoid": profile.get("avoid"),
        "soft_preferences": profile.get("soft_preferences"),
        "confirmed": sorted(
            (a.get("name") if isinstance(a, dict) else str(a)).lower().strip()
            for a in profile.get("artists", {}).get("confirmed", [])
            if (a.get("name") if isinstance(a, dict) else str(a))
        ),
    }
    payload = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _read_corpus_version(meta_path: Path) -> str | None:
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    v = meta.get("corpus_version")
    return str(v) if v else None


def log_batch_outcome(
    *,
    run_id: str,
    batch_num: int,
    model: str,
    rag_enabled: bool,
    rag_corpus_meta_path: Path | None,
    candidate_pool_names: Iterable[str] | None,
    profile_id: str,
    profile: dict,
    suggested_playlist: list[dict],
    found_keys: Iterable[str],
    eval_log_path: Path,
    debug_mode: bool,
) -> None:
    """Append one row per suggested track to *eval_log_path*.

    ``found_keys`` is the canonical ``"artist - track"`` (lowercased,
    stripped) form used elsewhere in the suggestion pipeline. Tracks
    not in this set are flagged ``found_on_spotify=False`` — i.e. the
    LLM named something Spotify could not match (the prime
    hallucination signal).

    ``candidate_pool_names`` may be ``None`` when RAG was disabled or
    the corpus is absent; in that case ``in_candidate_pool`` is
    serialised as ``null`` rather than ``false`` so the two cases stay
    distinguishable downstream.
    """
    if not debug_mode:
        return
    if not suggested_playlist:
        return

    found_set = {k.lower().strip() for k in found_keys}
    pool_set: set[str] | None = None
    if candidate_pool_names is not None:
        pool_set = {n.lower().strip() for n in candidate_pool_names if n}

    corpus_version = (
        _read_corpus_version(rag_corpus_meta_path)
        if rag_enabled and rag_corpus_meta_path is not None
        else None
    )
    profile_hash = compute_profile_hash(profile)
    ts = _now_iso()

    eval_log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(eval_log_path, "a", encoding="utf-8") as fh:
            for entry in suggested_playlist:
                artist = (entry.get("artist") or "").lower().strip()
                track = (entry.get("track") or "").lower().strip()
                key = f"{artist} - {track}"
                rationale_types = [
                    r.get("type") for r in (entry.get("rationale") or [])
                    if isinstance(r, dict) and r.get("type")
                ]
                row = {
                    "ts": ts,
                    "run_id": run_id,
                    "batch_num": batch_num,
                    "model": model,
                    "rag_enabled": bool(rag_enabled),
                    "rag_corpus_version": corpus_version,
                    "candidate_pool_size": len(pool_set) if pool_set is not None else None,
                    "profile_id": profile_id,
                    "profile_hash": profile_hash,
                    "artist": artist,
                    "track": track,
                    "found_on_spotify": key in found_set,
                    "in_candidate_pool": (artist in pool_set) if pool_set is not None else None,
                    "rationale_types": rationale_types,
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover — disk-full / permission
        logger.warning("eval_log write failed (%s): %s", eval_log_path, exc)
