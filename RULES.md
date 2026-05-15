# RULES.md — Detailed Conventions (read on demand)

For everything else (build, where-to-change-what, the 9 must-follow rules, git rule, context discipline, graphify), see `CLAUDE.md`. For Spotify API conventions, see `SKILL.md`.

## Accessibility (a11y)

Every frontend change must consider assistive-technology users:

- **ARIA** — All interactive elements need `aria-label` or `aria-labelledby`. Use `aria-expanded`, `aria-controls`, `aria-modal`, `aria-live`, `role` where applicable.
- **Focus** — Modals trap focus, restore on close. Logical tab order. Never leave focus on hidden elements.
- **Keyboard** — Every mouse/touch action must work via `Tab`, `Enter`, `Space`, `Escape`. Add `onkeydown` alongside `onclick` for custom controls.
- **Screen readers** — `.sr-only` for announced-only text. `aria-hidden="true"` on decorative icons.
- **Contrast** — WCAG AA: 4.5:1 text, 3:1 large text/UI. Never convey info by color alone.
- **Semantic HTML** — Prefer `<button>`, `<a>`, `<nav>`, `<main>`, `<section>`, `<label>` over `<div>`/`<span>`.
- **Motion** — Respect `prefers-reduced-motion`.
- **Skip link** — Must remain functional.

## i18n Details

- Language files: `frontend/static/i18n/en.json` (English), `de.json` (German), `jp.json` (Japanese). All three must contain the **same key set** — enforced by `core/tests/test_i18n_parity.py`.
- HTML: `data-i18n="key"` for text, `data-i18n-placeholder="key"` for inputs, `data-i18n-title="key"` for tooltips, `data-i18n-attr="attr:key"` for arbitrary attributes (e.g. `aria-label`).
- JS: `import { i18n } from './i18n.js'` then `i18n('key', 'Fallback')`.
- Onboarding: uses own `obI18n()` / `obApplyLang()` (no ES modules).
- Key naming: dot-separated namespaces (`profile.title`, `feedback.like`, `pipeline.cancelled`).
- `help.en.md` / `help.de.md` / `help.jp.md`: Markdown with `> **Screenshot placeholder:**` markers. Keep sections self-contained and scannable. All three files must stay in sync when content changes.
