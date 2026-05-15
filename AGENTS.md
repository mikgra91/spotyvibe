# AGENTS.md

> ## 🔴🔴🔴 ABSOLUTE RULE — READ BEFORE ANYTHING ELSE
>
> **NEVER run `git commit`, `git push`, or any command that creates commits or pushes to a remote.**
>
> The ONLY exception: the user's **current message** contains the **EXACT, LITERAL, CASE-SENSITIVE STRING `CP ALLOWED`** as a standalone, top-level instruction. No other phrase grants permission — not "commit and push", not "go ahead", not "yes", not any natural-language equivalent. **`CP ALLOWED` or nothing.**
>
> - One occurrence of `CP ALLOWED` = ONE git operation. Permission revoked the instant it completes.
> - Editing, fixing, planning, or reviewing code is **NEVER** implicit permission to commit.
> - When in doubt: **do NOT commit. Ask the user.**
> - There are **zero exceptions** to this rule. It has been violated 9 times. Each violation caused real damage.

Project-level instructions for AI coding agents working on this codebase.
**Claude users:** all instructions are in `CLAUDE.md`. Read that. This file exists only for non-Claude agents.

Cross-references:
- `CLAUDE.md` — full project rules, structure, build/run, where-to-change-what, context discipline, graphify usage
- `SKILL.md` — Spotify Web API reference + conventions
- `RULES.md` — a11y checklist + i18n details
- `documentation/MCPServers.md` — optional MCP servers (Spotify, GitHub, Playwright, MDN)
- `documentation/TechnicalManual.md` — architecture, modules, data flow, test recipes

## 🎯 Project North Star

**Priorities, in strict order:**

1. **Quality** — recommendation relevance, must-have-cite rate, found-on-Spotify rate.
2. **Price** — cost per generated playlist. Saving tokens matters.
3. **Speed** — wall-clock latency.

**Hard rules derived from these priorities:**

- **No regression — ever.** Every change must show a *non-regression* on every metric for every supported model on the eval harness (`evaluation/run_evaluation.py`). If a change improves cost/speed but regresses quality on any model, it does **not** ship. Quality always wins ties.
- **Local-LLM compatibility is first-class.** The project supports local LLMs (Ollama, llama.cpp, etc.) alongside cloud providers. Never assume cloud-only features (`json_schema`, parallel tool calls, vision, function calling, etc.) are available — always provide a graceful fallback. The auto-downgrade pattern in `core/src/openai_http.py` (`_JSON_SCHEMA_UNSUPPORTED` cache) is the canonical example.
- **Measure before shipping.** Run the evaluation harness against multiple models (cloud + local) before declaring a change ready. A passing unit-test suite is necessary but not sufficient.
- **Document model behaviour.** Keep model evaluation results in `evaluation/baselines/` and `evaluation/results/` so users can pick a model that matches their priorities. Some models (e.g., reasoning-heavy ones) may be unfit for this workload — say so explicitly.

## Pre-existing test failures

When the test suite runs, **all** failures must be investigated and fixed — not just those caused by changes made in the current session. A test that was already broken before you started is still a bug. Report it, diagnose it, and fix it. Never dismiss a failure with "this wasn't caused by my changes" or silently skip it.
