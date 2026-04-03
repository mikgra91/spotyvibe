# Implementation Plan — TODO.md

> **Target agent:** Claude Sonnet 4.6
> **Generated:** 2026-04-03 | **Revised:** 2026-04-03
> **Source:** `TODO.md` (17 items)
> **Codebase rules:** See `AGENTS.md` and `SKILL.md` before implementing.

---

## Pre-Implementation Checklist

1. Read `AGENTS.md` — project rules, commit style, test requirements, documentation updates.
2. Read `SKILL.md` — git workflow, Spotify API reference, context file regeneration.
3. Run `python -m pytest core/tests/ frontend/tests/ -v` before and after each group to catch regressions.
4. After each group, update `documentation/help.md`, `documentation/UserManual.md`, `documentation/TechnicalManual.md`, `README.md` as needed per AGENTS.md rules.
5. Regenerate `context/backend-context.md` and `context/frontend-context.md` when their source files change.
6. Use Git Bash for all terminal commands. Follow commit message format from AGENTS.md.
7. Read `context/backend-context.md` and `context/frontend-context.md` for general overview of the application.

---

## Implementation Order

Execute in this order to minimize merge conflicts and maximize testability:

| Order | Group | File | Items | Risk | Complexity |
|---|---|---|---|---|---|
| 1 | B | [Group-B.md](Group-B.md) | #11, #12 — Toggle labels | Low | Trivial |
| 2 | K | [Group-K.md](Group-K.md) | #16 — Track count removal | Low | Trivial |
| 3 | D | [Group-D.md](Group-D.md) | #10 — Export feedback | Low | Trivial |
| 4 | C | [Group-C.md](Group-C.md) | #9 — Help anchors | Low | Small |
| 5 | I | [Group-I.md](Group-I.md) | #6, #7 — Dropdown styling | Low | Small |
| 6 | E | [Group-E.md](Group-E.md) | #8 — GPT language sync | Medium | Medium |
| 7 | F | [Group-F.md](Group-F.md) | #13 — Audio % | Low | Medium |
| 8 | J | [Group-J.md](Group-J.md) | #3 — Jump bubble fix | Low | Small |
| 9 | H | [Group-H.md](Group-H.md) | #15 — Training spinner | Low | Medium |
| 10 | G | [Group-G.md](Group-G.md) | #14 — Logging split | Medium | Medium |
| 11 | L | [Group-L.md](Group-L.md) | #17 — Preview auth | Low | Small |
| 12 | A | [Group-A.md](Group-A.md) | #1,2,4,5 — pywebview fixes | Medium | Medium |

**Commit strategy:** One commit per group. Each commit must pass `python -m pytest core/tests/ frontend/tests/ -v`.

---

## i18n Key Summary (All New Keys)

### `en.json` additions:
```json
{
    "analysis.show": "Open Analysis",
    "analysis.hide": "Hide",
    "history.hide": "Hide",
    "msg.export_saved": "Profile exported — check your Downloads folder for spotyvibe_profile.json",
    "preview.login_hint": "For full playback, ",
    "preview.login_link": "log in to Spotify",
    "preview.login_hint_suffix": " in your browser."
}
```

### `de.json` additions:
```json
{
    "analysis.show": "Analyse öffnen",
    "analysis.hide": "Ausblenden",
    "history.hide": "Ausblenden",
    "msg.export_saved": "Profil exportiert — Prüfe deinen Downloads-Ordner nach spotyvibe_profile.json",
    "preview.login_hint": "Für vollständige Wiedergabe, ",
    "preview.login_link": "bei Spotify anmelden",
    "preview.login_hint_suffix": " im Browser."
}
```

### Keys to remove (Group E):
- `settings.gpt_language` from both `en.json` and `de.json`

---

## Documentation Updates Required

Per AGENTS.md, every feature change must update all 4 docs:

| Doc | Groups requiring updates |
|---|---|
| `README.md` | A (pywebview mention), G (logging split) |
| `documentation/UserManual.md` | A (desktop experience), F (audio % labels), E (language sync), L (preview login), H (training spinner) |
| `documentation/help.md` | F (audio filter labels), E (language change behavior), L (preview login), H (training spinner) |
| `documentation/TechnicalManual.md` | A (desktop architecture), G (logging architecture), E (language sync flow) |

### Context files to regenerate:
- `context/backend-context.md` — after Groups E, G
- `context/frontend-context.md` — after Groups B, C, D, F, H, I, J, K, L
