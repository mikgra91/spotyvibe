"""Probe runner — shared envelope, scoring aggregation, fingerprint shape.

A probe is a Python module exposing the following symbols:

- ``PROBE_ID: str`` — stable identifier (e.g. ``"B-1.constraint_grammar"``).
- ``VARIANTS: list[str]`` — variant names (e.g. ``["soft", "hard", "hard_with_quota"]``).
- ``RUNS_PER_VARIANT: dict[str, int]`` — how many calls per variant (default 1).
- ``build_messages(variant: str) -> list[dict]`` — OpenAI messages.
- ``response_format(variant: str) -> dict | None`` — schema or json_object hint.
- ``score(variant, parsed, raw) -> dict[str, float]`` — per-call rubric.
- ``aggregate(variant, per_call_scores) -> dict[str, float]`` — across calls.

The runner stays oblivious to *what* a probe measures. It only orchestrates
the call envelope (temperature=0, max_tokens=800), token bookkeeping, JSON
parsing, and result collection.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, Protocol

log = logging.getLogger(__name__)


# ── Pricing — rough USD/1M-token rates, late-2025 list prices ────────
# Used only for cost-estimation display; tax/region differences ignored.
# Unknown models fall back to gpt-4o pricing (defensive overestimate).
_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5.4":        (2.50, 10.00),
    "gpt-5.4-mini":   (0.15,  0.60),
    "gpt-4.1":        (2.00,  8.00),
    "gpt-4.1-mini":   (0.15,  0.60),
    "gpt-4o":         (2.50, 10.00),
    "gpt-4o-mini":    (0.15,  0.60),
}
_FALLBACK_PRICING = (2.50, 10.00)


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = _PRICING_USD_PER_MTOK.get(model, _FALLBACK_PRICING)
    return (tokens_in / 1_000_000.0) * pin + (tokens_out / 1_000_000.0) * pout


# ── Shared envelope constants (Research Track B §B.2) ────────────────
TEMPERATURE = 0.0
MAX_TOKENS  = 800


@dataclass
class ProbeResult:
    probe_id: str
    model: str
    variant: str
    call_idx: int                                  # 0-based within (probe, variant)
    raw_response: str
    parsed_json: Any                                # dict | list | None
    scores: dict[str, float]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_s: float
    error: str | None = None                        # populated when call/parse failed


@dataclass
class FingerprintProperty:
    """One row of the per-model fingerprint card (Track B §B.3)."""
    probe_id: str
    variant: str
    runs: int
    scores: dict[str, float]                        # aggregated across runs


@dataclass
class Fingerprint:
    model: str
    captured_at: str
    fingerprint_version: int
    probes: list[FingerprintProperty] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model":               self.model,
            "captured_at":         self.captured_at,
            "fingerprint_version": self.fingerprint_version,
            "total_cost_usd":      round(self.total_cost_usd, 6),
            "total_tokens_in":     self.total_tokens_in,
            "total_tokens_out":    self.total_tokens_out,
            "total_duration_s":    round(self.total_duration_s, 3),
            "probes": [
                {
                    "probe_id": p.probe_id,
                    "variant":  p.variant,
                    "runs":     p.runs,
                    "scores":   {k: _round(v) for k, v in p.scores.items()},
                }
                for p in self.probes
            ],
        }


def _round(v: float | int | str | None) -> float | int | str | None:
    if isinstance(v, float):
        return round(v, 4)
    return v


# ── OpenAI call shim (injectable for tests) ──────────────────────────

class _OpenAICall(Protocol):
    def __call__(
        self,
        model: str,
        messages: list,
        temperature: float = ...,
        response_format: dict | None = ...,
    ) -> dict: ...


def _default_openai_call(
    model: str,
    messages: list,
    temperature: float = TEMPERATURE,
    response_format: dict | None = None,
) -> dict:
    # Imported lazily so tests can run without OPENAI_API_KEY in env.
    from core.src.openai_http import chat_completions_create
    return chat_completions_create(
        model=model,
        messages=messages,
        temperature=temperature,
        response_format=response_format,
    )


# ── Single-probe execution ───────────────────────────────────────────

def _extract_content(response: dict) -> str:
    try:
        return (response["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def _usage_tokens(response: dict) -> tuple[int, int]:
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)


def _safe_json_loads(raw: str) -> Any:
    """Lenient JSON parse: handles ```json fences and prose preamble."""
    if not raw:
        return None
    s = raw.strip()
    # Strip code fences.
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s[3:]
        # First line after opening fence may be the language tag.
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0].strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Last-ditch: take the largest {...} or [...] substring.
        for open_c, close_c in (("{", "}"), ("[", "]")):
            i = s.find(open_c)
            j = s.rfind(close_c)
            if i != -1 and j > i:
                try:
                    return json.loads(s[i:j + 1])
                except json.JSONDecodeError:
                    pass
        return None


def run_probe(
    probe_module,
    model: str,
    *,
    openai_call: _OpenAICall | None = None,
) -> list[ProbeResult]:
    """Run every variant × runs_per_variant of one probe. Returns one
    ``ProbeResult`` per call (NOT per variant — aggregation happens in
    ``aggregate_fingerprint``).
    """
    call = openai_call or _default_openai_call
    results: list[ProbeResult] = []

    probe_id = getattr(probe_module, "PROBE_ID")
    variants = getattr(probe_module, "VARIANTS")
    runs_map = getattr(probe_module, "RUNS_PER_VARIANT", {})

    for variant in variants:
        runs = int(runs_map.get(variant, 1))
        for call_idx in range(runs):
            messages = probe_module.build_messages(variant)
            response_format = probe_module.response_format(variant)
            t0 = time.monotonic()
            raw = ""
            parsed: Any = None
            tokens_in = tokens_out = 0
            err: str | None = None
            scores: dict[str, float] = {}
            try:
                resp = call(
                    model=model,
                    messages=messages,
                    temperature=TEMPERATURE,
                    response_format=response_format,
                )
                raw = _extract_content(resp)
                tokens_in, tokens_out = _usage_tokens(resp)
                parsed = _safe_json_loads(raw)
                scores = probe_module.score(variant, parsed, raw)
            except Exception as exc:                          # noqa: BLE001
                # Probes are best-effort observers — a single failed call
                # should not abort the battery. Record and move on.
                err = f"{type(exc).__name__}: {exc}"
                log.warning("probe %s/%s call_idx=%d failed: %s",
                            probe_id, variant, call_idx, err)

            duration = time.monotonic() - t0
            results.append(ProbeResult(
                probe_id=probe_id,
                model=model,
                variant=variant,
                call_idx=call_idx,
                raw_response=raw,
                parsed_json=parsed,
                scores=scores,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=estimate_cost_usd(model, tokens_in, tokens_out),
                duration_s=duration,
                error=err,
            ))
    return results


def run_battery(
    probe_modules: Iterable[Any],
    model: str,
    *,
    openai_call: _OpenAICall | None = None,
) -> list[ProbeResult]:
    """Run a list of probes against one model. Order preserved."""
    out: list[ProbeResult] = []
    for mod in probe_modules:
        out.extend(run_probe(mod, model, openai_call=openai_call))
    return out


# ── Fingerprint aggregation ──────────────────────────────────────────

def _default_aggregate(
    variant: str, per_call_scores: list[dict[str, float]]
) -> dict[str, float]:
    """Mean aggregation across calls — used when a probe does not define
    its own ``aggregate``. Treats missing keys as 0.0 for that call.
    """
    keys = sorted({k for d in per_call_scores for k in d.keys()})
    n = len(per_call_scores) or 1
    return {k: sum(float(d.get(k, 0.0)) for d in per_call_scores) / n for k in keys}


def aggregate_fingerprint(
    results: list[ProbeResult],
    *,
    model: str,
    captured_at: str,
    fingerprint_version: int = 1,
    probe_modules: Iterable[Any] | None = None,
) -> Fingerprint:
    """Collapse per-call ``ProbeResult``s into one fingerprint card.

    When ``probe_modules`` is provided, each module's custom ``aggregate``
    function is used (if defined); otherwise the mean aggregator runs.
    """
    # Index modules by PROBE_ID for aggregate lookup.
    by_id: dict[str, Any] = {}
    if probe_modules is not None:
        for mod in probe_modules:
            by_id[getattr(mod, "PROBE_ID")] = mod

    # Group results.
    grouped: dict[tuple[str, str], list[ProbeResult]] = {}
    for r in results:
        grouped.setdefault((r.probe_id, r.variant), []).append(r)

    fp = Fingerprint(
        model=model,
        captured_at=captured_at,
        fingerprint_version=fingerprint_version,
    )
    for (probe_id, variant), group in grouped.items():
        scores_list = [g.scores for g in group if not g.error]
        mod = by_id.get(probe_id)
        aggregator: Callable[[str, list[dict]], dict[str, float]]
        if mod is not None and hasattr(mod, "aggregate"):
            aggregator = mod.aggregate
        else:
            aggregator = _default_aggregate
        agg = aggregator(variant, scores_list) if scores_list else {}
        fp.probes.append(FingerprintProperty(
            probe_id=probe_id,
            variant=variant,
            runs=len(group),
            scores=agg,
        ))
        fp.total_cost_usd  += sum(g.cost_usd     for g in group)
        fp.total_tokens_in += sum(g.tokens_in    for g in group)
        fp.total_tokens_out+= sum(g.tokens_out   for g in group)
        fp.total_duration_s+= sum(g.duration_s   for g in group)
    return fp


# ── Result serialization helpers ─────────────────────────────────────

def results_to_jsonl(results: list[ProbeResult]) -> str:
    """One JSON object per line — matches the eval_log convention."""
    lines = []
    for r in results:
        d = asdict(r)
        # parsed_json may contain non-JSON-serialisable objects from a bad
        # parse — coerce to repr so the line is always valid JSON.
        try:
            json.dumps(d["parsed_json"])
        except (TypeError, ValueError):
            d["parsed_json"] = repr(d["parsed_json"])
        lines.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(lines)
