# Help & Quickstart — Current State Summary

Snapshot of what SpotyVibe ships today for onboarding help, to inform
the redesign discussion. Counts are at 2026-04-18.

---

## 1. Quickstart guide (modal)

### Files
- [frontend/templates/modals/quickstart_modal.html](frontend/templates/modals/quickstart_modal.html) — 337 lines
- [frontend/static/js/modules/quickstart-tour.js](frontend/static/js/modules/quickstart-tour.js) — 186 lines (pagination)
- [frontend/static/js/modules/quickstart-demo.js](frontend/static/js/modules/quickstart-demo.js) — 829 lines (hand-animated mock UI frames)
- [frontend/static/css/quickstart.css](frontend/static/css/quickstart.css)
- 166 `quickstart.*` i18n keys in each of `en.json` / `de.json` / `jp.json`

### Structure
- **TOC (page 0)** + **7 step pages** (1=Setup, 2=Profile, 3=Generate,
  4=Review, 5=Refine, 6=Repeat, 7=Band/Song Analysis).
- Provider split: each step has `data-qs-provider="openai" | "spotify" | "both"`.
  - **OpenAI tour:** 1 → 2 → 7 → 6 (4 steps visible)
  - **Spotify tour:** 1 → 3 → 4 → 5 → 6 (5 steps visible)
- Per-provider "Don't show again" flag in `localStorage`
  (`spv_quickstart_dismissed_openai` / `_spotify`).

### Content per step
Each step page contains **three parallel representations of the same
information**:
1. A prose paragraph (~3 sentences, `quickstart.stepN_desc`).
2. A "Key Actions" bulleted checklist (4–5 bullets, `quickstart.stepN_actionM`).
3. An interactive demo player: 3–4 mocked UI frames, auto-playing,
   ‹ / ›, play/pause, expand. Captions come from `quickstart.demoN_fM`.

### Auto-open behavior
- [modals.js:442-491](frontend/static/js/modules/modals.js#L442-L491) —
  `maybeShowQuickstart(provider)` opens the guide on first load per
  provider, unless dismissed.
- Opens for the **currently active provider**; switching provider can
  re-trigger a second auto-open for that provider's tour.
- "✕" close button is in the top-right corner; persistent "Don't show
  again" checkbox sits in a footer row visible on every page.

### UX footprint
- ~11 viewport heights of content if a user reads all of it.
- Modal is the first thing a new user sees before touching the app.
- Demos animate automatically (even though each step already has text
  + bullets), which draws attention away from reading.

---

## 2. Help page (user manual modal)

### Files
- [frontend/templates/modals/help_modal.html](frontend/templates/modals/help_modal.html) — thin shell, content injected server-side
- [documentation/help.en.md](documentation/help.en.md) — **1062 lines**
- [documentation/help.de.md](documentation/help.de.md) + `help.jp.md` (in-sync translations)
- 10 `help.*` i18n keys (chrome only: banner text, close/dismiss labels)

### Structure
Single long markdown document rendered into a scrollable modal. TOC
at the top with anchor links. Screenshots embedded from
`/docs/screenshots/`.

Top-level sections:

| # | Section | Sub-headings |
|---|---------|--------------|
| 1 | Privacy — What Leaves Your Device | — (1 table) |
| 2 | Getting Started | Overview, Before You Start, Understanding the Main Screen, Quick Start Guide |
| 3 | Account Setup | Open the Menu, Enter Your Credentials, Connect Your Spotify Account |
| 4 | User Preferences | Settings, Language, Theme |
| 5 | Music Profile | Create Your Music Profile (+8 sub-sub-sections), Import/Export/Reset, Updating Your Taste Over Time |
| 6 | Discovery & Analysis | Band/Song Analysis |
| 7 | Playlist Generation | Mode, Quick vs Advanced, Exploration Slider, Presets, Audio Filters, Emerging Artists, Start, Stop Early |
| 8 | Track Review & Feedback | Preview, Spotify Links, Like, Dislike, Remove |
| 9 | Refine Playlist | Select/Load, Review, Like, Dislike, Dismiss |
| 10 | Taste Dashboard | Opening, Charts, Sentiment, Profile Isolation |
| 11 | Song List & Run History | Persistent List, Run History |
| 12 | Mobile Usage | — |
| 13 | Troubleshooting & Tips | Troubleshooting, Final Tips |

**Totals:** 13 top-level sections, ~45 sub-headings, 1062 lines of
markdown, many embedded screenshots, ≥ 3 translated files to keep in
sync on every change.

### Access paths
- Menu `☰ → Help` — opens at top.
- Section-level `?` icons — open scrolled to the matching anchor.
- Fallback banner warns when the user's language has no translation yet.

---

## 3. Other surfaces touching onboarding

- **First-run wizard** at [frontend/templates/onboarding.html](frontend/templates/onboarding.html)
  (7-step credential/profile setup — separate from the Quickstart modal).
- **Tips/toasts system** ([frontend/static/js/modules/tips.js](frontend/static/js/modules/tips.js)) —
  one-shot hint toasts keyed off `localStorage`.
- **Setup guide** (`setup_guide.css`) — a secondary how-to for getting
  credentials (Spotify developer dashboard walkthrough).
- In-UI descriptions — every major collapsible section already has a
  one-line description below its title (per help text at
  [help.en.md:132-133](documentation/help.en.md#L132-L133)).

---

## 4. Problem signals

1. **Quickstart is dismissed immediately** (user report) — the modal
   blocks the app on first launch, presenting 4–5 screens of explanation
   before the user has a chance to form a question. Classic "forced tour"
   friction.
2. **Triple-encoding** per step (prose + checklist + animated demo)
   means the reader has to decide which to follow — more decisions = more
   bounce.
3. **Provider duplication** — Step 1 (Setup) and Step 6 (Repeat) run in
   both tours; users switching providers are re-introduced to content
   they may already have seen.
4. **Help manual is a 1062-line wall of text** — useful as a reference,
   but not task-oriented. The TOC has 45+ entries; finding "how do I
   dislike a track" requires scanning.
5. **Redundancy with in-UI affordances** — section titles already carry
   one-line descriptions, section-level `?` help icons already exist,
   and the onboarding wizard already covers credentials. Several
   Quickstart pages re-explain this.
6. **Maintenance cost** — 166 `quickstart.*` keys × 3 languages = 498
   translations to keep in sync; 1062-line help doc × 3 languages adds
   to the burden when features change.

---

## 5. Research — what 2025–26 onboarding literature says

Summarised from industry benchmark reports and design-pattern guides
(sources listed at the bottom). Numbers come from the Chameleon 2025
benchmark and Userpilot / Whatfix 2026 reports.

### Headline findings
- **78 % of users abandon product tours by step 3.**
- Tours with **more than 5 steps → 67 % abandonment** before completion.
- **76 % of static tooltips are dismissed within 3 seconds** when they
  appear unsolicited.
- **Forced tours underperform user-initiated tours** ("launcher-driven")
  by ~2× on completion. Launcher-driven tours average ~67 %
  completion; modal auto-opens average ~15–20 %.
- **Contextual, behaviour-triggered tips** generate **+61 %
  engagement** and **+34 % first-action completion** vs. upfront
  walkthroughs (Chameleon A/B case study).
- **Personalised / role-routed onboarding** improves completion by
  ~35 %.
- **Progressive disclosure** (reveal advanced features only when
  relevant) correlates with 30 %+ drop in settings-confusion support
  tickets.

### Patterns worth stealing
1. **Launcher / help hub** — a persistent small button (e.g. "?") that
   lets the user re-open a short guided tour on demand. No modal on
   first load.
2. **Smart checklist** — a collapsible 3–5 item list showing progress
   ("✓ Keys saved", "✓ Spotify connected", "○ First playlist
   generated"). Items auto-check based on app state, not a separate
   tour. Pattern used by Notion, Linear, Slack.
3. **Empty-state coaching** — when a panel has nothing in it yet,
   show a single clear call-to-action with one sentence of guidance,
   instead of explaining it preemptively.
4. **Just-in-time tooltips** — short (≤ 2-sentence) hints that appear
   when the user *touches* an unfamiliar control, once per lifetime,
   dismissable. SpotyVibe already has `tips.js` for this.
5. **Task-oriented docs** — split the long manual into ~5-minute
   "How do I …" articles. Search/index beats linear TOC for 1000+
   line docs. Stripe Docs and Linear's docs are the reference.
6. **One representation per step** — text OR demo, not both. Duplicate
   encoding forces the reader to decide which to trust and increases
   time-to-first-action.

---

## 6. Suggestions for SpotyVibe

Grouped from cheapest / least risky to larger rewrites. Each is
independent — you can adopt any subset.

### A. Stop auto-opening the Quickstart modal *(cheapest)*
- Change [modals.js:486-491](frontend/static/js/modules/modals.js#L486-L491)
  `maybeShowQuickstart()` to **never auto-open** after the first-run
  credential wizard. The wizard already introduces the app; the modal
  stacks a second tour on top of it.
- Replace with a **persistent launcher**: a small "?" floating button
  (bottom-right) or a "Tour" item in the `☰` menu. The existing
  `openQuickstart()` stays; it's now only user-initiated.
- Expected effect: dismiss rate stops mattering — users who want the
  tour find it, users who don't aren't blocked.
- **Estimated user-facing code changes:** ~10 lines in `modals.js`,
  no i18n changes.

### B. Collapse triple-encoding → single representation per step
Current: every step has **prose + bullet checklist + animated demo**.
Pick one:
- **Option B1 (minimal change):** drop the prose paragraph, keep the
  checklist + demo. The demo captions already provide context; the
  paragraph is redundant prose.
- **Option B2 (stronger change, recommended):** drop the paragraph AND
  the checklist — keep only the **demo with captions**. The demo is
  already the most memorable element and the only one that shows
  *where* to click. Reduce each step from ~120 words to ~30.

Either removes ~80 `quickstart.stepN_desc` / `stepN_actionM` keys × 3
languages (~240 fewer translations to maintain). Keep demos; they're
the unique value over plain docs.

### C. Reduce steps from 5 → 3 per provider
- OpenAI tour: **Setup → Profile → (that's it, try it)**. Drop "Band/
  Song Analysis" and "Repeat" from the tour (still in help).
- Spotify tour: **Setup → Generate → Review**. Drop "Refine" and
  "Repeat".
- Rationale: 5-step threshold is where abandonment spikes (Chameleon).
  The dropped steps are for *returning* users, not first-timers —
  surface them via contextual tips when the user first opens those
  panels (empty-state coaching).

### D. Smart checklist replaces the tour
A small collapsible card in the main UI (not a modal) showing progress:
```
  Getting started  (2 / 5)
  ✓ API keys saved
  ✓ Spotify connected
  ○ Create a music profile          [Jump →]
  ○ Generate your first playlist    [Jump →]
  ○ Like or dislike 3 tracks        [Jump →]
```
- Auto-checks based on profile / playlist / feedback state the backend
  already tracks. Never re-asks a completed step.
- Auto-hides when all items done; user can dismiss at any point.
- "Jump →" scrolls to and expands the relevant section — re-uses the
  existing section `?` anchor system.
- Replaces the role of the modal tour; keeps the demo player available
  via the launcher (A) for users who want the full walkthrough.

### E. Restructure `help.en.md` (and siblings)
Current: 1062 lines, 13 top-level sections, 45+ sub-headings — a
reference manual, not task-oriented.

- **Split into 5 task-oriented mini-articles:**
  1. *Set up your keys* (was §3)
  2. *Build a music profile* (was §5)
  3. *Generate playlists* (was §7 + part of §6)
  4. *Refine and review* (was §8 + §9)
  5. *Troubleshooting* (was §13)
- Drop the full TOC in favour of **5 tiles** on the help landing page,
  each linking to one mini-article. Keep deep anchors for `?` icon
  jumps.
- Move the *Taste Dashboard* (§10), *Run History* (§11), *Mobile Usage*
  (§12) to a secondary "Reference" section — still searchable, not
  front-and-centre.
- Expected reduction: ~25–30 % of help text is ceremony (repeated
  intros, overlap between Review and Refine sections) and can be
  merged.

### F. Empty-state coaching for advanced panels ✅ done 2026-04-18
- The first time a user expands **Refine Playlist**, **Band/Song
  Analysis**, or **Audio Filters**, show a one-line inline hint with
  an example ("Try: enter an artist you like; we'll suggest profile
  text you can paste"). Dismissable, once per lifetime.
- Re-uses `tips.js`. No new modal.
- Replaces the corresponding Quickstart pages.

### G. Two-question routing on first run *(optional, bigger)*
- After credential setup, ask one question: "Do you want to **(a)
  discover new music** or **(b) clean up an existing playlist**?" Route
  into a single-focus empty state pointing at Generate or Refine.
- Expands the checklist differently for each path.
- Personalised routing is where the benchmark reports see the biggest
  completion lift (+35 %). Lowest-priority of the suggestions because
  it adds persistent state.

### Content that could simply be removed
- `quickstart.step6_*` ("Repeat & Improve") — tautological; every app
  gets better with use. 1 page × 3 languages removed.
- `quickstart.stepN_desc` paragraphs (if adopting B2) — 7 keys × 3
  languages = 21 translations removed.
- Help sections that duplicate the onboarding wizard's credential
  walkthrough (`## Account Setup` — 54 lines, mostly redundant once
  §6F is in place).
- Mobile Usage section (§12) — move to README; not needed in-app help.

### Recommended adoption order
1. ✅ **A + B2 together** (1 commit) — remove auto-open, drop redundant
   prose, keep demos. Smallest risk, biggest impact. **(done 2026-04-18)**
2. ✅ **C** — trim tour to 3 steps per provider. **(done 2026-04-18)**
3. ✅ **D** — smart checklist. Needs a bit of backend state wiring but
   is the replacement for the tour's "guidance" role. **(done 2026-04-18)**
4. **F** — empty-state tips as tour shrinks.
5. **E** — help restructuring. Can run in parallel; purely
   documentation.
6. **G** — routing. Defer unless A–F don't move the needle.

---

## 7. Sources

- [The Hidden Metrics of Effective Product Tours — Chameleon, 2025](https://www.chameleon.io/blog/effective-product-tour-metrics)
- [Why Most Product Tours Fail — SaaSFactor](https://www.saasfactor.co/blogs/why-most-product-tours-fail-and-how-to-implement-contextual-onboarding)
- [7 User Onboarding Best Practices — Guidejar, 2025](https://www.guidejar.com/blog/7-user-onboarding-best-practices-that-actually-work-in-2025)
- [100+ User Onboarding Statistics — Userguiding, 2026](https://userguiding.com/blog/user-onboarding-statistics)
- [How to Create Effective Product Tours — Whatfix, 2025](https://whatfix.com/product-tour/)
- [Progressive Disclosure in UX — LogRocket](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)
- [What is Progressive Disclosure — Interaction Design Foundation, 2026](https://ixdf.org/literature/topics/progressive-disclosure)
- [SaaS Onboarding Flows That Convert in 2026 — SaaSUI](https://www.saasui.design/blog/saas-onboarding-flows-that-actually-convert-2026)
- [The Role of Empty States in Onboarding — Smashing Magazine](https://www.smashingmagazine.com/2017/02/user-onboarding-empty-states-mobile-apps/)
- [Empty states pattern — Carbon Design System](https://carbondesignsystem.com/patterns/empty-states-pattern/)
