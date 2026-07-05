"""Stage-2 taste re-ranker — the "Judge" half of "Ground then Judge".

PROTOTYPE (2026-07-05). Not wired into the live pipeline yet; gated behind
`SPOTYVIBE_TASTE_RERANK`. Validated offline in `evaluation/taste_bench.py`:
tag/embedding retrieval separates the user's loves from same-genre rejects at
AUC ~0.5 (coin flip); this LLM re-ranker reaches ~0.78-0.91 depending on model.
See .dev-notes/corpus-diag-2026-07-05/ for the full evidence.

Design contract
---------------
- INPUT is a pool of REAL, already-grounded corpus artists (Stage-1 output).
  The LLM only SCORES/REORDERS them — it never invents an artist, so there is
  no hallucination and no extra Spotify verification round-trip. This is the
  answer to "LLM-first reopens hallucination": the LLM judges, it does not propose.
- Exemplars come from the profile the user already curates: `artists.confirmed`
  are the loves, `artists.rejected` (with reasons) are the rejects. Every
  like/dislike the user gives sharpens the next call's exemplars — that is the
  "gradually narrowing taste profile", implemented as exemplar curation rather
  than a static vector (which the benchmark shows would be chance-level).

Cost/speed: one names-only LLM call per generation (not per batch), cacheable.
"""
from __future__ import annotations

import json
import logging
import re

from .rag.corpus import normalise_name
from .openai_http import chat_completions_create, extract_chat_content

logger = logging.getLogger(__name__)

# How many exemplars to include. Enough to convey the taste; capped so the
# prompt stays small and cache-friendly.
_MAX_LOVE_EXEMPLARS = 20
_MAX_REJECT_EXEMPLARS = 20

_SYSTEM = (
    "You are a music-taste model. Given a user's loved and rejected artists, "
    "score how likely the user is to LOVE each candidate. The user's dominant "
    "axis is melody/hook/harmony quality (melody > hook > energy > style); they "
    "reject same-genre artists they find melodically boring or dated. Each "
    "candidate is given as 'Name [genre tags]'. Judge by BOTH the artist and the "
    "tags — the tags disambiguate homonyms (e.g. a 'Wings [death metal]' is NOT "
    "Paul McCartney's Wings) and describe artists you may not know. Score a "
    "candidate low if its tags clash with the user's taste, however famous the "
    "name looks. Return ONLY JSON {\"scores\":[{\"n\":<candidate number>,\"s\":"
    "<0-100>}]} for EVERY candidate — n is the integer shown before each candidate."
)


def _as_list(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v if isinstance(x, str) and x.strip()]
    return []


def _exemplars(profile: dict) -> tuple[str, list[str], list[tuple[str, str]]]:
    prefs = (profile or {}).get("preferences", {}) or {}
    # Build a rich taste directive: core description + the explicit MUST-HAVE and
    # AVOID traits. Surfacing must_have (e.g. "upbeat tempo", "high energy") and
    # avoid (e.g. "slow-tempo", "melancholic") lets the judge reward energetic /
    # uplifting artists and down-score slow, melancholic, or off-genre ones —
    # the axis the non-enforced energy/valence filter never actually controlled.
    core = prefs.get("core_description", "") or (profile or {}).get("meta", {}).get("goal", "")
    parts = []
    if core:
        parts.append(core.strip())
    must = _as_list(prefs.get("must_have"))
    if must:
        parts.append("MUST HAVE: " + "; ".join(must))
    avoid = _as_list(prefs.get("avoid"))
    if avoid:
        parts.append("AVOID (score these low): " + "; ".join(avoid))
    taste = "  |  ".join(parts)

    arts = (profile or {}).get("artists", {}) or {}
    loves = [a for a in (arts.get("confirmed") or []) if isinstance(a, str)][:_MAX_LOVE_EXEMPLARS]
    rejects: list[tuple[str, str]] = []
    for r in (arts.get("rejected") or []):
        if isinstance(r, dict) and r.get("name"):
            rejects.append((r["name"], r.get("reason", "user feedback")))
    return taste, loves, rejects[:_MAX_REJECT_EXEMPLARS]


def taste_scores(profile: dict, candidates: list,
                 model: str) -> dict[str, float]:
    """Return {normalised_name: 0-100 taste score} for *candidates*.

    *candidates* items may be plain names (str) or ``(name, tags)`` pairs. When
    tags are supplied they are shown to the judge as ``Name [tag, tag, …]`` so
    the model disambiguates corpus homonyms and can reason about unknown artists
    from their genre tags. Never raises for a bad LLM response — returns an empty
    dict so callers can fall back to the unranked pool.
    """
    if not candidates:
        return {}
    taste, loves, rejects = _exemplars(profile)
    if not loves and not rejects:
        return {}  # nothing to anchor on — caller keeps the original order

    def _line(i, c):
        if isinstance(c, (tuple, list)) and len(c) == 2:
            name, tags = c[0], list(c[1] or [])[:6]
            suffix = f" [{', '.join(tags)}]" if tags else ""
            return f"{i+1}. {name}{suffix}"
        return f"{i+1}. {c}"

    def _cand_name(c):
        return str(c[0]) if isinstance(c, (tuple, list)) else str(c)
    names = [_cand_name(c) for c in candidates]
    norm_names = {normalise_name(n) for n in names}

    love_block = "\n".join(f"- {a}" for a in loves) or "(none given)"
    reject_block = "\n".join(f"- {n} (reason: {why})" for n, why in rejects) or "(none given)"
    cand_block = "\n".join(_line(i, c) for i, c in enumerate(candidates))
    user = (f"USER TASTE: {taste}\n\nLOVES:\n{love_block}\n\n"
            f"REJECTED (with reasons):\n{reject_block}\n\n"
            f"CANDIDATES (score every one, 0=certain reject, 100=certain love):\n{cand_block}")

    try:
        resp = chat_completions_create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0.0, response_format={"type": "json_object"},
        )
        raw = extract_chat_content(resp)
    except Exception as exc:  # network / provider / auth — never break a run
        logger.warning("taste_rerank: LLM call failed, keeping pool order: %s", exc)
        return {}

    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(m.group(0) if m else raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("taste_rerank: unparseable response, keeping pool order")
        return {}
    items = data.get("scores") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    out: dict[str, float] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        try:
            s = float(it.get("s", it.get("score")))
        except (TypeError, ValueError):
            continue
        n = it.get("n", it.get("name", it.get("index")))
        key = None
        if isinstance(n, (int, float)) or (isinstance(n, str) and n.strip().isdigit()):
            idx = int(n) - 1  # candidates are 1-indexed in the prompt
            if 0 <= idx < len(names):
                key = normalise_name(names[idx])
        elif isinstance(n, str):
            # Model may echo "Name [tags]" — strip the bracketed tag suffix.
            stripped = re.sub(r"\s*\[[^\]]*\]\s*$", "", n).strip()
            cand = normalise_name(stripped)
            key = cand if cand in norm_names else (
                normalise_name(n) if normalise_name(n) in norm_names else cand)
        if key:
            out[key] = s
    return out


def rerank_pool(profile: dict, candidates: list, model: str,
                drop_frac: float = 0.0):
    """Reorder *candidates* (objects with a ``.name``) by taste score, desc.

    - Unscored candidates keep a neutral score and sink below scored ones but
      retain their relative order (stable).
    - *drop_frac* optionally trims the lowest-scoring fraction (0.0 = keep all).
    - On any failure returns *candidates* unchanged — the re-ranker is strictly
      additive and can never make the pool worse than Stage-1 alone.
    """
    if not candidates:
        return candidates
    # Pass (name, tags) so the judge can disambiguate homonyms and reason about
    # unknown artists from their tags.
    pairs = [(getattr(c, "name", ""),
              list(getattr(c, "tags", []) or []) + list(getattr(c, "spotify_genres", []) or []))
             for c in candidates]
    scores = taste_scores(profile, pairs, model)
    if not scores:
        return candidates  # graceful fallback

    neutral = -1.0  # unscored sink below anything the model scored (>=0)
    keyed = [(scores.get(normalise_name(getattr(c, "name", "")), neutral), i, c)
             for i, c in enumerate(candidates)]
    keyed.sort(key=lambda t: (t[0], -t[1]), reverse=True)
    ordered = [c for _, _, c in keyed]
    if drop_frac > 0.0:
        keep = max(1, int(round(len(ordered) * (1.0 - drop_frac))))
        ordered = ordered[:keep]
    logger.info("taste_rerank: reordered %d candidates (dropped %d)",
                len(candidates), len(candidates) - len(ordered))
    return ordered
