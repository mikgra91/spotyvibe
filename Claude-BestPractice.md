# Claude Best Practices — Token Efficiency & Reliability

Research-backed strategies for reducing token usage and increasing reliability when using Claude (Sonnet/Opus) in Claude Code CLI.

---

## 1. CLAUDE.md Optimization

### Keep It Under 200 Lines
Compliance drops significantly after 150–200 instructions due to context dilution. Every line should answer: *"Would Claude make a mistake without this?"* — if not, it's noise.

- **Source:** [Anthropic — Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices), [Arize — CLAUDE.md Best Practices with Prompt Learning](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/)

### Never Use CLAUDE.md for Code Style
Formatting rules waste context tokens. Use deterministic linters/formatters instead (ESLint, Prettier, Black, Ruff).

- **Source:** [Anthropic — Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices)

### Use Numbered Rules, Not Prose
Structured formats (numbered lists, tables, headings) are parsed more reliably than paragraphs. Markdown headings, bulleted lists, and code blocks provide structural signals LLMs use to map content relationships.

- **Source:** [Webex — Boosting AI Performance with LLM-Friendly Content in Markdown](https://developer.webex.com/blog/boosting-ai-performance-the-power-of-llm-friendly-content-in-markdown)

### Iterative Refinement
Start with structure and tech stack, add numbered rules for recurring mistakes, include concrete examples for complex domains, remove outdated instructions on each iteration. Developers report +11% better code quality through this pattern.

- **Source:** [Arize — CLAUDE.md Best Practices with Prompt Learning](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/)

---

## 2. The "Lost in the Middle" Effect

### Core Finding
LLM performance degrades by **>30%** when relevant information is in the middle of the context window, even with long-context models. This creates a U-shaped performance curve: models recall the **beginning** and **end** of context best, but lose information in the middle.

### Root Cause
Transformer attention mechanisms and Rotary Position Embedding (RoPE) cause long-term decay that de-emphasizes middle content while prioritizing the start and end.

### How to Apply
- Place **critical rules at the TOP** of CLAUDE.md.
- Place **trigger-based rules at the BOTTOM** (e.g., "on commit, do X").
- Put reference material (project tree, route tables) in the middle — it's consulted, not recalled from memory.
- If a rule is critical, consider **repeating it** at the end.

- **Source:** [Liu et al. — Lost in the Middle: How Language Models Use Long Contexts (ACL 2024)](https://aclanthology.org/2024.tacl-1.9/), [ArXiv 2307.03172](https://arxiv.org/abs/2307.03172)

---

## 3. Code Navigation is the #1 Token Waste

### Finding
**60–80% of agentic coding tokens** go toward locating code, not solving the actual problem. The largest cost driver is figuring out *where things are*, not answering the question.

### How to Apply
- Add a **"Where to Change What"** table in CLAUDE.md that maps tasks to files directly.
- Include the **full project tree** with one-line descriptions so Claude never needs to run `tree`, `glob`, or `ls` to orient itself.
- Use **clear, descriptive file and function names** — Python code is especially affected by naming quality because dynamic typing provides fewer structural cues (see section 4).

- **Source:** [Jake Nesler — Your AI Coding Agent Wastes 80% of Its Tokens Just Finding Things](https://medium.com/@jakenesler/context-compression-to-reduce-llm-costs-and-frequency-of-hitting-limits-e11d43a26589)

### Example "Where to Change What" Table
```markdown
| Task | Files |
|---|---|
| API endpoint / route | `app.py` |
| Spotify OAuth or playlist CRUD | `core/src/playlist.py` |
| OpenAI / GPT calls | `core/src/openai_http.py` |
| Page layout | `frontend/templates/base.html` + partials |
| Styling | `frontend/static/css/styles.css` |
| JS feature logic | `frontend/static/js/modules/<feature>.js` |
| Translations | `frontend/static/i18n/en.json` + `de.json` |
```

---

## 4. Naming Affects LLM Performance (Measurably)

### Finding
Code representation learning heavily relies on well-defined names. When naming attributes are anonymized or unclear, LLM code understanding degrades significantly — especially in **Python**, where dynamic typing means the model depends more on names than on structural/syntactic cues. Java code, with strong typing and boilerplate, is more resilient.

### How to Apply
- Invest in clear, descriptive function/variable/module names.
- Prefer `get_user_playlist()` over `fetch()` or `do_thing()`.
- File names should describe their domain: `playlist.py`, `feedback.py`, `history.py` — not `helpers.py`, `misc.py`, `utils2.py`.
- Good naming directly reduces exploration tool calls because Claude can find relevant code without searching.

- **Source:** [ArXiv — How Does Naming Affect LLMs on Code Analysis Tasks? (2307.12488)](https://arxiv.org/html/2307.12488v5)

---

## 5. Progressive Disclosure — Load Detail on Demand

### Finding (SkillReducer Framework)
Loading all instructions upfront wastes tokens on rules that aren't relevant to the current task. The SkillReducer framework achieves **48% compression** of skill descriptions and **39% reduction in body tokens** while maintaining an 86% pass rate — by using tiered/progressive disclosure.

### How to Apply
- **CLAUDE.md** — Always loaded. Keep only essential rules and structure (<200 lines).
- **RULES.md / SKILL.md** — On-demand. Detailed conventions, API references, checklists. Referenced from CLAUDE.md with "Read X before doing Y."
- Never inline full API docs or verbose checklists into CLAUDE.md.

- **Source:** [ArXiv — SkillReducer: Optimizing LLM Agent Skills for Token Efficiency (2603.29919)](https://arxiv.org/html/2603.29919)

---

## 6. AGENTS.md — Proven at Scale

### Finding
AGENTS.md files have been adopted by **60,000+ repositories** as a "README for agents." They specify architecture, conventions, and operational procedures, reducing agent search overhead.

### How to Apply
- If using Claude Code, put everything in `CLAUDE.md` (auto-loaded). Use `AGENTS.md` for non-Claude agents.
- Avoid duplication between the two files — duplication wastes context on repeated information.
- Keep AGENTS.md as a minimal pointer to CLAUDE.md + tech stack summary.

- **Source:** [ArXiv — On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents (2601.20404)](https://arxiv.org/html/2601.20404v2)

---

## 7. Context Management Commands

| Command | When to Use | Effect |
|---|---|---|
| `/compact` | Conversation getting long, Claude losing track | Summarizes and condenses context |
| `/clear` | Switching to unrelated work | Starts fresh, prevents stale context waste |
| `/effort` | Simple tasks that don't need deep reasoning | Reduces thinking tokens |
| `/model sonnet` | Routine code changes (80%+ of tasks) | ~60% cheaper than Opus |
| `/model opus` | Complex reasoning, deep refactoring | Full capability |

- **Source:** [Anthropic — Manage Costs Effectively](https://code.claude.com/docs/en/costs)

### Small Fast Model Override

Claude Code uses a lightweight "small fast model" internally for background operations (`/compact` summaries, commit message generation, tool result summarization). By default this is Haiku. You can explicitly set it via the `ANTHROPIC_SMALL_FAST_MODEL` environment variable in your Claude Code `settings.json`:

```jsonc
// ~/.claude/settings.json (user-level) or .claude/settings.json (project-level)
{
  "env": {
    "ANTHROPIC_SMALL_FAST_MODEL": "claude-haiku-3-5-20241022"
  }
}
```

This does **not** route user prompts to Haiku — only background operations. For switching the main model, use `/model` interactively.

- **Source:** [Anthropic — Claude Code Configuration](https://code.claude.com/docs/en/configuration)

---

## 8. Prompt Caching

### How It Works
Claude automatically caches the longest matching prefix of your prompt. Subsequent calls that share the same prefix pay only 10% of the normal input cost for the cached portion.

| Token Type | Cost vs Base |
|---|---|
| Cache write | 1.25x (first time) |
| Cache read | **0.1x** (subsequent) |
| Normal input | 1.0x |

### Requirements
- Minimum cacheable length: **1,024 tokens** (Sonnet), 4,096 tokens (Opus/Haiku).
- Cache TTL: 5 minutes (default), refreshed on each hit.
- Automatic: no manual tracking needed — Claude reads from your longest previously cached prefix.

### Implication for CLAUDE.md
A stable CLAUDE.md that rarely changes gets cached across tool calls within a conversation. Frequent edits to CLAUDE.md during a session break the cache prefix.

- **Source:** [Anthropic — Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Anthropic — Token-Saving Updates](https://www.anthropic.com/news/token-saving-updates)

---

## 9. Trajectory Reduction

### Finding
In agentic workflows, tool call messages accumulate in the conversation trajectory and remain present even when no longer relevant, causing significant token waste. Trajectory reduction techniques drop accumulated input tokens to **47–72%** of baseline.

### How to Apply
- Use `/compact` when the conversation has accumulated many tool results.
- Use subagents for exploratory research — their results don't pollute the main context.
- Break unrelated tasks into separate conversations rather than one long session.

- **Source:** [ArXiv — Improving the Efficiency of LLM Agent Systems through Trajectory Reduction (2509.23586)](https://arxiv.org/pdf/2509.23586)

---

## 10. Subagents for Context Isolation

### How It Works
Subagents run in separate context windows. The main conversation receives only the summary, not the full tool call history. This is effective for:
- Exploratory research / codebase investigation
- Running tests and reporting results
- Parallel independent tasks

### When NOT to Use
- Simple, directed searches (use Glob/Grep directly — faster and cheaper)
- Tasks where you need the results immediately in the main context
- When the overhead of spawning outweighs the context savings

- **Source:** [Anthropic — Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices)

---

## 11. Dynamic Toolset Optimization

### Finding
Static toolsets (loading all tool schemas upfront) waste tokens. A dynamic three-step approach achieves up to **160x token reduction** while maintaining 100% success rates:
1. `search_tools` — natural language query to find relevant tools
2. `describe_tools` — load only the matched tool schemas
3. `execute_tool` — call with parameters

### Implication
When building MCP servers or custom tools, don't expose everything at once. Use progressive tool discovery.

- **Source:** [Speakeasy — Reducing MCP Token Usage by 100x](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2)

---

## 12. Hook-Based Preprocessing

### How It Works
Custom hooks preprocess data before Claude sees it. For example, grepping ERROR lines from a 10,000-line log reduces context from tens of thousands to hundreds of tokens.

### How to Apply
- Configure hooks in Claude Code `settings.json` that filter, summarize, or transform tool outputs.
- Particularly useful for: log analysis, large file reads, test output parsing.

- **Source:** [Claude Code — Pricing & Usage Optimization](https://claudefa.st/blog/guide/development/usage-optimization)

---

## Summary: Priority-Ordered Checklist

1. **CLAUDE.md under 200 lines** — highest-impact single change
2. **"Where to Change What" table** — eliminates 60-80% of exploration tokens
3. **Full project tree in CLAUDE.md** — prevents `tree`/`glob`/`ls` tool calls
4. **Critical rules at TOP and BOTTOM** — lost-in-the-middle mitigation
5. **Progressive disclosure** — verbose rules in separate on-demand files
6. **Clear file/function naming** — reduces search tool calls
7. **Use `/compact` and `/clear`** — manage context accumulation
8. **Default to Sonnet** — upgrade to Opus only when needed
9. **Break work into focused conversations** — prevents trajectory bloat
10. **No code style in CLAUDE.md** — use linters
