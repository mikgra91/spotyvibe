# Implementation Decisions — Mobile Frontend Feedback
> Based on `feedback-gemini.md` (Gemini) and `feedback-opus.md` (Opus), reviewed against `frontend-state.md`.
> Created: 2026-04-03
---
## Decision Methodology
Both reviews agree on the same core problem areas. Opus provides significantly deeper analysis with concrete code-level fixes, so it serves as the primary action source. Items are evaluated on **user impact**, **effort**, and **alignment with SpotyVibe's current stage** (functional web + Android WebView wrapper).
Items are categorised as:
- ✅ **IMPLEMENT** — clear value, reasonable effort, improves real user experience
- ⏳ **DEFER** — valid concern but low urgency, high effort, or premature optimisation
- ❌ **REJECT** — not applicable, already handled, or cost outweighs benefit
---
## ✅ IMPLEMENT (10 items)
1. **Canvas themes: JS prefers-reduced-motion guard & mobile simplification** (P0, Low effort)
2. **SSE streaming: reconnection & visibility listener** (P0, Medium effort)
3. **Sticky hover states — wrap in @media (hover: hover)** (P1, Low effort)
4. **Track cover play button: always visible on touch devices** (P1, Low effort)
5. **Preview overlay focus trap** (P1, Low effort)
6. **Hide "Open Data Directory" on mobile** (P2, Low effort)
7. **theme-color meta tag** (Trivial)
8. **Lazy loading for track cover images** (Trivial)
9. **Jump bubble opacity — never fully invisible** (Low effort)
10. **Replace alert()/confirm() with custom dialogs** (Medium effort)
## ⏳ DEFER (6 items)
- Profile Import/Export in Android WebView
- Accordion scroll fatigue / sticky save bar
- Tooltips tap-to-toggle on mobile
- Feedback form obscured by virtual keyboard
- Settings bottom-sheet backdrop
- Swipe gesture discoverability (a11y)
## ❌ REJECT (2 items)
- Service Worker / Offline Shell
- Split monolithic CSS file
