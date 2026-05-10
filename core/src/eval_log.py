"""Per-suggestion JSONL eval log for offline hallucination analysis.

Writes one JSON line per AI-suggested track to ``EVAL_LOG_FILE`` so the
RAG / model A/B work documented in ``documentation/TechnicalManual.md``
§"RAG design reference" can be measured with pandas/Jupyter instead of
by hand.

Five row kinds are emitted to the same file (joined by ``run_id``):

  - ``track`` — per AI-suggested track (Phase 0 baseline).
  - ``batch_summary`` — per LLM call inside a generation run.
  - ``run_summary`` — once per generation run (latency p50/p95).
  - ``stage2_summary`` — once per run, Phase 1 P1.2 avoid-checker LLM cost.
  - ``profile_update_summary`` — per AI Profile Update / playlist seed draft.
  - ``analysis_summary`` — per Band/Song Analysis call.

The two original kinds are documented inline below; the new ones share a
common shape: ``status``, ``latency_s``, ``usage``, ``prompt_chars``.

1. **Per-track rows** (``kind`` field absent / equal to ``"track"``) —
   one per AI-suggested track. The original Apr-2026 schema, kept
   backward-compatible::

        {"ts": "2026-04-19T10:23:45Z",
         "run_id": "uuid",
         "batch_num": 1,
         "model": "gpt-5-mini",
         "rag_enabled": true,
         "rag_corpus_version": "2026-04-19" | null,
         "candidate_pool_size": 100,
         "profile_id": "...",
         "profile_hash": "abcd1234",
         "artist": "...", "track": "...",
         "found_on_spotify": true | false,
         "in_candidate_pool": true | false | null,
         "rationale_types": ["profile_match", "artist_match"],
         "effective_batch_size": 5,           # added 2026-04-22 (Option A)
         "config_signature": "c1f2a3"}        # added 2026-04-22

2. **Per-batch summary rows** (``kind: "batch_summary"``) — one per LLM
   call, added 2026-04-22 to track Option A (per-call batch shrink) and
   Option C (prompt trim) impact on output quality::

        {"kind": "batch_summary",
         "ts": "...", "run_id": "...", "batch_num": 1,
         "model": "...", "rag_enabled": true,
         "config_signature": "c1f2a3",
         "effective_batch_size": 5,
         "rag_pool_size": 100, "rag_stratified": true,
         "prompt_components": {"system": 1820, "user_total": 5240,
                               "profile": 980, "deny_set": 1450,
                               "pool": 1180, "accepted": 0,
                               "feedback": 220, "diversity_hint": 0,
                               "audio_filters": 0},
         "usage": {"prompt_tokens": 1900, "completion_tokens": 720,
                   "total_tokens": 2620},
         "gpt_returned_count": 8,
         "after_filter_count": 6,
         "spotify_found_count": 5,
         "in_pool_count": 2,
         "consecutive_empty_batches": 0}

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


def compute_config_signature(*,
                             rag_enabled: bool,
                             rag_pool_size: int | None,
                             rag_stratified: bool | None,
                             effective_batch_size: int | None,
                             extra: dict | None = None) -> str:
    """Short, stable hash of the configuration knobs that shape the prompt.

    Two batches with the same signature were generated under the same
    Option A / Option C configuration and can be compared apples-to-apples
    in the eval log. ``extra`` is an open dict for future trim flags
    (e.g. ``{"slim_pool": True, "compact_json": True}``) — pass any
    JSON-serialisable knob you want to bucket on.
    """
    payload = {
        "rag_enabled": bool(rag_enabled),
        "rag_pool_size": rag_pool_size,
        "rag_stratified": rag_stratified,
        "effective_batch_size": effective_batch_size,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


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
    effective_batch_size: int | None = None,
    config_signature: str | None = None,
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

    ``effective_batch_size`` and ``config_signature`` (added 2026-04-22)
    are optional but strongly recommended — they let the per-track rows
    be joined back to the per-batch summary rows for trim-impact analysis.
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
    must_have_tags = [
        str(t).strip() for t in
        ((profile or {}).get("preferences", {}) or {}).get("must_have", []) or []
        if str(t).strip()
    ]
    # CF-Telemetry-1 (2026-04-28): tokenise must-have tags so paraphrases
    # like "uplifting modern production" satisfy the "modern production"
    # must-have. Match if every meaningful token of the tag appears in
    # the rationale arg as a separate word (case-insensitive). Falls
    # back to the legacy substring contains so existing matches still
    # count. Stop-words filtered to avoid trivial matches like "and",
    # "or" forcing every must-have to look satisfied.
    _MH_STOP = {
        "a", "an", "the", "and", "or", "of", "with", "to", "in",
        "on", "for", "is", "are", "be", "by", "at", "as", "but",
    }
    must_have_token_sets: list[tuple[str, set[str]]] = []
    for _mh in must_have_tags:
        _toks = {
            "".join(c for c in w.lower() if c.isalnum())
            for w in _mh.split()
        }
        _toks = {t for t in _toks if t and t not in _MH_STOP}
        if _toks:
            must_have_token_sets.append((_mh, _toks))

    def _arg_satisfies_must_have(arg: str) -> bool:
        if not arg:
            return False
        _arg_lower = arg.lower()
        for _mh, _toks in must_have_token_sets:
            # Legacy contains (preserves prior matches)
            if _mh.lower() in _arg_lower:
                return True
            # Token-set containment: every alnum token of the must-have
            # appears as a word substring in the rationale arg.
            if all(_t in _arg_lower for _t in _toks):
                return True
        return False
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
                rationale_args = [
                    r.get("arg", "") for r in (entry.get("rationale") or [])
                    if isinstance(r, dict) and r.get("type")
                ]
                row = {
                    "kind": "track",
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
                    "rationale_args": rationale_args,
                    "rationale_count": len(rationale_types),
                    "has_must_have_cite": any(
                        r.get("type") == "profile_match"
                        and _arg_satisfies_must_have(r.get("arg") or "")
                        for r in (entry.get("rationale") or [])
                        if isinstance(r, dict)
                    ) if must_have_token_sets else None,
                    "effective_batch_size": effective_batch_size,
                    "config_signature": config_signature,
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover — disk-full / permission
        logger.warning("eval_log write failed (%s): %s", eval_log_path, exc)


def log_batch_summary(
    *,
    run_id: str,
    batch_num: int,
    model: str,
    rag_enabled: bool,
    rag_corpus_meta_path: Path | None,
    profile_id: str,
    profile: dict,
    eval_log_path: Path,
    debug_mode: bool,
    effective_batch_size: int | None = None,
    rag_pool_size: int | None = None,
    rag_stratified: bool | None = None,
    candidate_pool_names: Iterable[str] | None = None,
    prompt_components: dict | None = None,
    usage: dict | None = None,
    latency_s: float | None = None,
    gpt_returned_count: int | None = None,
    after_filter_count: int | None = None,
    spotify_found_count: int | None = None,
    in_pool_count: int | None = None,
    consecutive_empty_batches: int | None = None,
    config_signature: str | None = None,
    suggested_playlist: list[dict] | None = None,
    stage1_candidate_count: int | None = None,
    stage2_approved_count: int | None = None,
    schema_collapse: dict | None = None,
    system_fingerprint: str | None = None,
    prompt_hashes: dict | None = None,
    stage3_mode: str | None = None,
) -> None:
    """Append a single ``kind: "batch_summary"`` row to the eval log.

    One row per LLM call. Added 2026-04-22 to enable offline analysis of
    how Option A (per-call batch shrink under RAG) and Option C (prompt
    trims) affect output quality. The row carries:

    - **What was sent** (``prompt_components``): per-component char counts
      from ``suggestions.get_last_prompt_components()`` — system, profile,
      deny_set, pool, accepted-tracks listing, feedback, audio filters,
      diversity hint, and the user-message total. Char counts (not tokens)
      so the row is deterministic and tokeniser-free.
    - **What it cost** (``usage``): OpenAI's ``prompt_tokens`` /
      ``completion_tokens`` / ``total_tokens`` when the provider returns
      them (``null`` otherwise — common for local LLMs).
    - **What came back** (``gpt_returned_count`` / ``after_filter_count``
      / ``spotify_found_count`` / ``in_pool_count``): the funnel from raw
      LLM output → post-dedup → Spotify-verified → pool-anchored.
    - **Under which configuration** (``config_signature`` +
      ``effective_batch_size`` + ``rag_pool_size`` + ``rag_stratified``):
      so multiple runs can be bucketed without diffing run timestamps.

    Same gating as ``log_batch_outcome`` — no-op unless ``debug_mode``.
    Failures are logged as a warning but never raise.
    """
    if not debug_mode:
        return

    pool_set = (
        {n.lower().strip() for n in candidate_pool_names if n}
        if candidate_pool_names is not None else None
    )
    corpus_version = (
        _read_corpus_version(rag_corpus_meta_path)
        if rag_enabled and rag_corpus_meta_path is not None
        else None
    )

    # ── Rationale coverage stats ──────────────────────────────────────
    rationale_stats = None
    if suggested_playlist:
        prefs = ((profile or {}).get("preferences", {}) or {})
        mh_tags = [str(t).strip().lower() for t in (prefs.get("must_have") or []) if str(t).strip()]
        total_tracks = len(suggested_playlist)
        rationale_counts = []
        must_have_cite_count = 0
        type_counter: dict[str, int] = {}
        for entry in suggested_playlist:
            rats = [r for r in (entry.get("rationale") or []) if isinstance(r, dict) and r.get("type")]
            rationale_counts.append(len(rats))
            for r in rats:
                rtype = r.get("type", "unknown")
                type_counter[rtype] = type_counter.get(rtype, 0) + 1
                if rtype == "profile_match" and mh_tags:
                    arg_lower = (r.get("arg") or "").lower()
                    if any(mh in arg_lower for mh in mh_tags):
                        must_have_cite_count += 1
                        break  # count once per track
        rationale_stats = {
            "avg_rationale_per_track": round(sum(rationale_counts) / total_tracks, 2) if total_tracks else 0,
            "must_have_cite_rate": round(must_have_cite_count / total_tracks, 2) if total_tracks and mh_tags else None,
            "type_distribution": type_counter,
        }

    # L16 (2026-04-29): hoist cached_tokens out of usage.prompt_tokens_details
    # to a top-level field so the aggregator can compute the prefix-cache hit
    # rate without descending into the (provider-specific) usage subtree.
    # OpenAI populates usage.prompt_tokens_details.cached_tokens when the
    # request hits the automatic 50% prompt-prefix discount tier; local
    # providers typically omit this field entirely. None means "provider did
    # not report" (treat as 0 for ratios but distinguish in audits).
    cached_tokens = None
    if isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            ct = details.get("cached_tokens")
            if isinstance(ct, int):
                cached_tokens = ct

    row = {
        "kind": "batch_summary",
        "ts": _now_iso(),
        "run_id": run_id,
        "batch_num": batch_num,
        "model": model,
        "rag_enabled": bool(rag_enabled),
        "rag_corpus_version": corpus_version,
        "candidate_pool_size": len(pool_set) if pool_set is not None else None,
        "profile_id": profile_id,
        "profile_hash": compute_profile_hash(profile),
        "config_signature": config_signature,
        "effective_batch_size": effective_batch_size,
        "rag_pool_size": rag_pool_size,
        "rag_stratified": rag_stratified,
        "prompt_components": prompt_components or {},
        "usage": usage,
        "cached_tokens": cached_tokens,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "gpt_returned_count": gpt_returned_count,
        "after_filter_count": after_filter_count,
        "spotify_found_count": spotify_found_count,
        "in_pool_count": in_pool_count,
        "consecutive_empty_batches": consecutive_empty_batches,
        "rationale_stats": rationale_stats,
        "stage1_candidate_count": stage1_candidate_count,
        "stage2_approved_count": stage2_approved_count,
        "schema_collapse": schema_collapse,
        # Tier 1 (2026-05-10) — diagnostics for OpenAI model-roll detection
        # + prompt-drift detection + L5 mode auditing. None when the
        # provider didn't surface the field (local LLMs, older snapshots).
        "system_fingerprint": system_fingerprint,
        "prompt_hashes": prompt_hashes or {},
        "stage3_mode": stage3_mode,
    }

    eval_log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(eval_log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover
        logger.warning("eval_log batch summary write failed (%s): %s",
                       eval_log_path, exc)


def log_run_summary(
    *,
    run_id: str,
    model: str,
    profile_id: str,
    eval_log_path: Path,
    debug_mode: bool,
    batch_count: int,
    batch_latencies_s: list[float],
    total_wall_s: float,
    verified_count: int,
    playlist_size: int,
    gpt_call_count: int,
) -> None:
    """Append one ``kind: "run_summary"`` row.

    Establishes the latency baseline Goal #3 measures against. p50/p95 are
    computed over per-batch LLM-call latencies; ``total_wall_s`` is end-to-end
    pipeline wall-clock (LLM + Spotify verify + everything else).
    """
    if not debug_mode:
        return

    def _percentile(values: list[float], pct: float) -> float | None:
        if not values:
            return None
        s = sorted(values)
        # Linear interpolation between closest ranks
        k = (len(s) - 1) * pct
        lo = int(k)
        hi = min(lo + 1, len(s) - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)

    row = {
        "kind": "run_summary",
        "ts": _now_iso(),
        "run_id": run_id,
        "model": model,
        "profile_id": profile_id,
        "batch_count": batch_count,
        "gpt_call_count": gpt_call_count,
        "verified_count": verified_count,
        "playlist_size": playlist_size,
        "total_wall_s": round(total_wall_s, 3),
        "batch_latency_s": {
            "p50": _percentile(batch_latencies_s, 0.50),
            "p95": _percentile(batch_latencies_s, 0.95),
            "max": round(max(batch_latencies_s), 3) if batch_latencies_s else None,
            "samples": len(batch_latencies_s),
        },
    }

    eval_log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(eval_log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover
        logger.warning("eval_log run summary write failed (%s): %s",
                       eval_log_path, exc)


# ── Per-feature single-call summaries ────────────────────────────────
#
# Phase-1 evaluation period needs per-feature cost / latency / quality
# rows so the user's "test all three features then analyse" workflow has
# something to compare. Each function appends one row of its own ``kind``
# so pandas joins (run_id / profile_id / config_signature) stay clean.

def _write_row(eval_log_path: Path, row: dict, kind_label: str) -> None:
    """Shared row-writer for the per-feature summaries below."""
    eval_log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(eval_log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover
        logger.warning("eval_log %s write failed (%s): %s",
                       kind_label, eval_log_path, exc)


def log_stage2_summary(
    *,
    run_id: str,
    model: str,
    profile_id: str,
    profile: dict,
    eval_log_path: Path,
    debug_mode: bool,
    candidates_in: int,
    approved_out: int,
    avoid_traits_count: int,
    status: str,
    latency_s: float | None,
    usage: dict | None,
    prompt_chars: int | None = None,
    config_signature: str | None = None,
) -> None:
    """Append one ``kind: "stage2_summary"`` row (Phase 1 P1.2 telemetry).

    One row per generation run. ``status`` is one of ``"ok"``,
    ``"empty_response"``, ``"error"`` so a flaky Stage 2 surfaces in the
    eval log instead of silently degrading to "blocking nothing".
    """
    if not debug_mode:
        return

    row = {
        "kind": "stage2_summary",
        "ts": _now_iso(),
        "run_id": run_id,
        "model": model,
        "profile_id": profile_id,
        "profile_hash": compute_profile_hash(profile),
        "config_signature": config_signature,
        "candidates_in": candidates_in,
        "approved_out": approved_out,
        "avoid_traits_count": avoid_traits_count,
        "status": status,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "usage": usage,
        "prompt_chars": prompt_chars,
    }
    _write_row(eval_log_path, row, "stage2_summary")


def log_profile_update_summary(
    *,
    run_id: str,
    model: str,
    profile_id: str,
    profile_before: dict,
    profile_after: dict | None,
    eval_log_path: Path,
    debug_mode: bool,
    label: str,
    status: str,
    latency_s: float | None,
    usage: dict | None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
) -> None:
    """Append one ``kind: "profile_update_summary"`` row.

    Captures cost / latency / quality signals for the AI Profile Update path
    (``train_profile``) and the playlist-seed draft path
    (``draft_profile_from_playlist``). ``label`` distinguishes the two so
    analysis can bucket them. Profile-hash before vs after lets the analyst
    confirm the call actually mutated the profile.
    """
    if not debug_mode:
        return

    row = {
        "kind": "profile_update_summary",
        "ts": _now_iso(),
        "run_id": run_id,
        "label": label,
        "model": model,
        "profile_id": profile_id,
        "profile_hash_before": compute_profile_hash(profile_before),
        "profile_hash_after": (
            compute_profile_hash(profile_after) if profile_after is not None else None
        ),
        "status": status,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "usage": usage,
        "prompt_chars": prompt_chars,
        "response_chars": response_chars,
        # OPEN-5 (2026-04-28): instrument profile section sizes so we can
        # decide whether to build the LLM consolidation step (P3.2). Run
        # this for ≥ 10 successive AI Profile Updates on a real profile;
        # if any of {soft_preferences, avoid, must_have} ever exceeds
        # ~8 entries, the consolidation call earns its keep.
        "section_sizes": _profile_section_sizes(profile_after or profile_before),
    }
    _write_row(eval_log_path, row, "profile_update_summary")


def _profile_section_sizes(profile: dict | None) -> dict:
    """Return entry counts and char lengths for the mutable profile sections
    we want to bound under P3.2. Tolerant of missing keys / wrong types."""
    if not isinstance(profile, dict):
        return {}
    prefs = profile.get("preferences") or {}
    if not isinstance(prefs, dict):
        prefs = {}
    meta = profile.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}

    def _len_list(val) -> int:
        return len(val) if isinstance(val, list) else 0

    def _len_str(val) -> int:
        return len(val) if isinstance(val, str) else 0

    return {
        "must_have_count": _len_list(prefs.get("must_have")),
        "soft_preferences_count": _len_list(prefs.get("soft_preferences")),
        "avoid_count": _len_list(prefs.get("avoid")),
        "core_description_chars": _len_str(prefs.get("core_description")),
    }


def log_analysis_summary(
    *,
    run_id: str,
    model: str,
    profile_id: str,
    eval_log_path: Path,
    debug_mode: bool,
    artist: str,
    track: str,
    status: str,
    latency_s: float | None,
    usage: dict | None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
    genre_count: int | None = None,
    style_tag_count: int | None = None,
    suggestion_count: int | None = None,
) -> None:
    """Append one ``kind: "analysis_summary"`` row (Band/Song Analysis).

    One row per ``analyze_band_song`` invocation so the analyst can compare
    Band/Song Analysis cost and quality across model A/B variants.
    """
    if not debug_mode:
        return

    row = {
        "kind": "analysis_summary",
        "ts": _now_iso(),
        "run_id": run_id,
        "model": model,
        "profile_id": profile_id,
        "artist": (artist or "").lower().strip(),
        "track": (track or "").lower().strip(),
        "status": status,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "usage": usage,
        "prompt_chars": prompt_chars,
        "response_chars": response_chars,
        "genre_count": genre_count,
        "style_tag_count": style_tag_count,
        "suggestion_count": suggestion_count,
    }
    _write_row(eval_log_path, row, "analysis_summary")
