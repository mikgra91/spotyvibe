"""Production-readiness scorecard — render gate results into a verdict.

The scorecard's job: turn N :class:`GateResult` rows into a single
"is this model production-ready?" answer, plus a short markdown
report that a human can read in 30 seconds.

Verdict ladder:

  - ``PRODUCTION_READY``    — every scenario PASSed, avg score ≥ 80.
  - ``DEGRADED``            — only WARNs (no FAILs), avg score ≥ 60.
  - ``NOT_PRODUCTION_READY``— any scenario FAILed, OR avg score < 60.

The console block and markdown report carry the same data. Markdown
goes to ``<results_dir>/scorecard.md``; the console block is what
``python -m evaluation.benchmark`` prints to stdout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .gates import (
    GateResult, VERDICT_FAIL, VERDICT_PASS, VERDICT_WARN, VERDICT_SKIPPED,
)


VERDICT_PRODUCTION_READY = "PRODUCTION_READY"
VERDICT_DEGRADED = "DEGRADED"
VERDICT_NOT_READY = "NOT_PRODUCTION_READY"


@dataclass
class Scorecard:
    """Aggregate verdict over a set of scenario results.

    ``overall_verdict`` is the headline shown at the top of the
    scorecard. ``exit_code`` is what the CLI returns to the shell:
    0 only when ``overall_verdict == PRODUCTION_READY``.
    """

    model: str
    started_at: str
    finished_at: str | None
    results: list[GateResult] = field(default_factory=list)
    overall_verdict: str = VERDICT_NOT_READY
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0
    average_score: float = 0.0
    total_cost_usd: float = 0.0
    total_wall_seconds: float = 0.0
    exit_code: int = 1

    def add(self, result: GateResult) -> None:
        self.results.append(result)


def _compute_verdict(scorecard: Scorecard) -> tuple[str, int]:
    """Return (verdict, exit_code) from the aggregate counters.

    Rules (in order; first match wins):
      - any FAIL → NOT_PRODUCTION_READY, exit 1
      - avg < 60 → NOT_PRODUCTION_READY, exit 1
      - any WARN → DEGRADED, exit 0 (degraded is shippable, marginally)
      - all PASS, avg ≥ 80 → PRODUCTION_READY, exit 0
      - otherwise → DEGRADED, exit 0
    """
    if scorecard.fail_count > 0:
        return VERDICT_NOT_READY, 1
    if scorecard.average_score < 60:
        return VERDICT_NOT_READY, 1
    if scorecard.warn_count > 0:
        return VERDICT_DEGRADED, 0
    if scorecard.pass_count > 0 and scorecard.average_score >= 80:
        return VERDICT_PRODUCTION_READY, 0
    return VERDICT_DEGRADED, 0


def finalise(scorecard: Scorecard) -> Scorecard:
    """Compute aggregates + verdict. Call once after all results are in."""
    for r in scorecard.results:
        if r.verdict == VERDICT_PASS:
            scorecard.pass_count += 1
        elif r.verdict == VERDICT_WARN:
            scorecard.warn_count += 1
        elif r.verdict == VERDICT_FAIL:
            scorecard.fail_count += 1
        else:
            scorecard.skipped_count += 1
        if r.cost_usd:
            scorecard.total_cost_usd += r.cost_usd
        if r.wall_seconds:
            scorecard.total_wall_seconds += r.wall_seconds
    scored = [r for r in scorecard.results if r.verdict != VERDICT_SKIPPED]
    if scored:
        scorecard.average_score = round(
            sum(r.score for r in scored) / len(scored), 1
        )
    scorecard.overall_verdict, scorecard.exit_code = _compute_verdict(scorecard)
    return scorecard


# ── Rendering ────────────────────────────────────────────────────────


def _verdict_icon(v: str) -> str:
    return {
        VERDICT_PASS: "[PASS]",
        VERDICT_WARN: "[WARN]",
        VERDICT_FAIL: "[FAIL]",
        VERDICT_SKIPPED: "[SKIP]",
    }.get(v, "[?]")


def _format_found_rate(rate: float | None) -> str:
    return f"{rate*100:.0f}%" if rate is not None else "  -"


def _diagnose_pattern(results: Sequence[GateResult]) -> list[str]:
    """Look across all results for KNOWN failure patterns + suggest a fix.

    These are the production-class diagnoses we've already observed.
    Each pattern check is conservative — it only fires when there's
    enough signal to be confident in the recommendation.
    """
    diagnoses: list[str] = []
    fails = [r for r in results if r.verdict == VERDICT_FAIL]
    if not fails:
        return diagnoses

    # Pattern 1: niche fails but mainstream passes → corpus coverage.
    mainstream = next(
        (r for r in results
         if "mainstream" in r.scenario_name and r.verdict == VERDICT_PASS),
        None,
    )
    niche_fails = [r for r in fails if "niche" in r.scenario_name
                   or "japanese" in r.scenario_name]
    if mainstream and niche_fails:
        diagnoses.append(
            "Niche-genre scenarios FAIL while mainstream PASSes. "
            "Likely a corpus-coverage gap (Stage 1 retrieval is fine "
            "on broad pools but thin on niche). Try: expand the "
            "corpus's `top_tracks` coverage on niche-language artists, "
            "or relax the must_have_tags filter on re-retrieve."
        )

    # Pattern 2: aged scenarios fail while clean variants pass → dedup.
    aged_fails = [r for r in fails if "aged" in r.scenario_name
                  or "session" in r.scenario_name]
    clean_pass = [r for r in results if "clean" in r.scenario_name
                  and r.verdict == VERDICT_PASS]
    if aged_fails and clean_pass:
        diagnoses.append(
            "Aged-state scenarios FAIL while clean variants PASS. "
            "Likely dedup-driven pool exhaustion (Q2 overlay pruning "
            "or Q3 low-found-rate trigger not firing on this model). "
            "Inspect trace `run_batches[*].outcome` for the "
            "consecutive_empty_after pattern."
        )

    # Pattern 3: low Spotify-found rates across the board → confab.
    low_found = [r for r in results
                 if r.spotify_found_rate is not None
                 and r.spotify_found_rate < 0.35]
    if len(low_found) >= 2:
        diagnoses.append(
            "Multiple scenarios show < 35% Spotify-found rate. "
            "The model is picking tracks Spotify cannot resolve — "
            "either weak parametric recall for non-mainstream titles "
            "or the model is ignoring the `known:` grounding. "
            "Try: enforce overlay-only picks via prompt change, "
            "or switch to a model with stronger music knowledge."
        )

    # Pattern 4: leakage across multiple scenarios → feedback path broken.
    leakage_fails = [r for r in fails if r.leakage_count > 0]
    if len(leakage_fails) >= 2:
        diagnoses.append(
            "Multiple scenarios show leakage (disliked / rejected "
            "re-appearing). The model is ignoring the "
            "`recently_filtered_tracks` prompt block or the dedup "
            "filter is not being applied. Check filter_duplicate_"
            "suggestions + Stage 3 prompt rendering."
        )

    # Pattern 5: pipeline errors → infrastructure / config.
    err_fails = [r for r in fails if any(
        h.startswith("Pipeline error") for h in r.hints
    )]
    if err_fails:
        diagnoses.append(
            "One or more scenarios raised a pipeline error — likely "
            "auth, network, or schema validation against this model. "
            "Read the per-scenario error in the table above before "
            "interpreting the rest of the scorecard."
        )

    return diagnoses


def render_console(scorecard: Scorecard) -> str:
    """Produce the human-readable console block.

    Width capped at 96 chars so it reads in default terminal sizes.
    """
    lines: list[str] = []
    lines.append("=" * 96)
    lines.append(f"SpotyVibe Benchmark - {scorecard.model}")
    lines.append(f"Started: {scorecard.started_at}    Finished: {scorecard.finished_at or '-'}")
    lines.append("=" * 96)
    lines.append("")

    # Per-scenario table
    header = (f"  {'SCENARIO':<32} {'VERDICT':<8} {'SCORE':>6} "
              f"{'FILL':>9} {'FOUND':>7} {'LEAK':>5} {'UNIQ':>5}")
    lines.append(header)
    lines.append("  " + "-" * 94)
    for r in scorecard.results:
        fill = f"{r.verified_count}/{r.target_count}"
        line = (
            f"  {r.scenario_name[:32]:<32} "
            f"{_verdict_icon(r.verdict):<8} "
            f"{r.score:>5.0f}  "
            f"{fill:>9} "
            f"{_format_found_rate(r.spotify_found_rate):>7} "
            f"{r.leakage_count:>5} "
            f"{r.unique_artist_count:>5}"
        )
        lines.append(line)
    lines.append("")

    # Aggregate
    lines.append(f"  PASS: {scorecard.pass_count}   "
                 f"WARN: {scorecard.warn_count}   "
                 f"FAIL: {scorecard.fail_count}   "
                 f"SKIP: {scorecard.skipped_count}")
    lines.append(f"  AVG SCORE: {scorecard.average_score:.1f} / 100")
    lines.append(f"  COST:      ${scorecard.total_cost_usd:.3f}")
    lines.append(f"  WALL:      {scorecard.total_wall_seconds:.0f}s "
                 f"({scorecard.total_wall_seconds/60:.1f} min)")
    lines.append("")
    lines.append(f"  VERDICT: {scorecard.overall_verdict}")
    lines.append("")

    # Per-scenario hints (failures + warns)
    interesting = [
        r for r in scorecard.results
        if r.verdict in (VERDICT_FAIL, VERDICT_WARN) and r.hints
    ]
    if interesting:
        lines.append("  SCENARIO HINTS")
        lines.append("  " + "-" * 94)
        for r in interesting:
            lines.append(f"  [{r.verdict}] {r.scenario_name}")
            for h in r.hints:
                # Wrap long hints at 88 chars (with 4-space indent).
                wrapped = _wrap(h, width=88, indent="      ")
                lines.extend(wrapped)
            lines.append("")

    # Cross-scenario diagnoses
    diagnoses = _diagnose_pattern(scorecard.results)
    if diagnoses:
        lines.append("  CROSS-SCENARIO DIAGNOSES")
        lines.append("  " + "-" * 94)
        for d in diagnoses:
            wrapped = _wrap(d, width=88, indent="    ")
            lines.extend(wrapped)
            lines.append("")

    lines.append("=" * 96)
    return "\n".join(lines)


def render_markdown(scorecard: Scorecard) -> str:
    """Produce the markdown scorecard for ``scorecard.md``."""
    md: list[str] = []
    md.append(f"# SpotyVibe Benchmark — `{scorecard.model}`")
    md.append("")
    md.append(f"- **Started:** {scorecard.started_at}")
    md.append(f"- **Finished:** {scorecard.finished_at or '—'}")
    md.append(f"- **Verdict:** **{scorecard.overall_verdict}**")
    md.append(f"- **Avg score:** {scorecard.average_score:.1f} / 100")
    md.append(f"- **Pass / Warn / Fail:** "
              f"{scorecard.pass_count} / "
              f"{scorecard.warn_count} / "
              f"{scorecard.fail_count}")
    md.append(f"- **Cost:** ${scorecard.total_cost_usd:.3f}")
    md.append(f"- **Wall:** {scorecard.total_wall_seconds:.0f}s "
              f"({scorecard.total_wall_seconds/60:.1f} min)")
    md.append("")
    md.append("## Per-scenario results")
    md.append("")
    md.append("| Scenario | Verdict | Score | Fill | Spotify-found | Leakage | Unique artists | Wall |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in scorecard.results:
        fill = f"{r.verified_count}/{r.target_count}"
        wall = f"{r.wall_seconds:.0f}s" if r.wall_seconds else "—"
        md.append(
            f"| `{r.scenario_name}` | **{r.verdict}** | "
            f"{r.score:.0f} | {fill} | "
            f"{_format_found_rate(r.spotify_found_rate)} | "
            f"{r.leakage_count} | {r.unique_artist_count} | {wall} |"
        )
    md.append("")

    interesting = [
        r for r in scorecard.results
        if r.verdict in (VERDICT_FAIL, VERDICT_WARN) and r.hints
    ]
    if interesting:
        md.append("## Scenario-level hints")
        md.append("")
        for r in interesting:
            md.append(f"### `{r.scenario_name}` — {r.verdict}")
            for h in r.hints:
                md.append(f"- {h}")
            md.append("")

    diagnoses = _diagnose_pattern(scorecard.results)
    if diagnoses:
        md.append("## Cross-scenario diagnoses")
        md.append("")
        for d in diagnoses:
            md.append(f"- {d}")
        md.append("")

    md.append("## How to interpret")
    md.append("")
    md.append("- **PRODUCTION_READY** → ship this model. Every scenario "
              "passed and the average score is ≥ 80.")
    md.append("- **DEGRADED** → shippable with caveats. No hard failures, "
              "but ≥1 scenario hit a soft cap (latency / cost / "
              "diversity floor). Investigate before defaulting to this model.")
    md.append("- **NOT_PRODUCTION_READY** → do NOT default users to this "
              "model. At least one scenario FAILed a hard gate. Read the "
              "per-scenario hints and the cross-scenario diagnoses above.")
    return "\n".join(md)


def render_scorecard(scorecard: Scorecard) -> tuple[str, str]:
    """Compatibility shim: return (console, markdown)."""
    return render_console(scorecard), render_markdown(scorecard)


def _wrap(text: str, *, width: int, indent: str) -> list[str]:
    """Word-wrap *text* into lines of length ≤ width with leading indent.

    Inline to avoid importing textwrap.fill (which mangles
    pre-formatted hint strings with multiple spaces).
    """
    words = text.split()
    if not words:
        return [indent]
    lines = []
    current = indent + words[0]
    for w in words[1:]:
        if len(current) + 1 + len(w) <= width:
            current += " " + w
        else:
            lines.append(current)
            current = indent + w
    lines.append(current)
    return lines
