# RULES.md — Detailed Conventions (read on demand)

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

## Documentation Update Checklist

| Doc | Audience | Notes |
|---|---|---|
| `README.md` | Developers | General overview |
| `documentation/UserManual.md` | End users | Comprehensive walkthrough |
| `documentation/help.en.md` + `help.de.md` + `help.jp.md` | In-app users | Served at `/api/help` (UI language selects the file; falls back to English with a banner). All three must stay in sync when content changes. |
| `documentation/TechnicalManual.md` | Developers | Architecture, API, data flow |

`help.en.md` / `help.de.md` / `help.jp.md`: Markdown with `> **Screenshot placeholder:**` markers. Keep sections self-contained and scannable. All three files must stay in sync when content changes.

## Spotify API (Quick Reference)

Full details in `SKILL.md`. Key points:

- `sp.playlist_items()` not `sp.playlist_tracks()` (removed endpoint)
- `sp.current_user_playlist_create()` not `sp.user_playlist_create()`
- Search `limit` max = 10, always pass explicitly
- Playlist inner key: `entry.get("item") or entry.get("track")`
- Playlist summary: `pl.get("items") or pl.get("tracks")`
- `fields` param must use new key names: `items(item(uri,name,...))` not `items(track(...))`

## Screenshot Tests

Excluded from routine runs via `pytest.ini` (`-m "not screenshots"`). Run manually:
```bash
python -m pytest frontend/tests/test_documentation_screenshots.py -v -m screenshots
```
