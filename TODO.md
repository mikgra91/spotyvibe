# TODO — Deferred Code-Review Items (2026-04-28)

Items identified during the code-review pass but deferred. Pick these up in a future session.

---

## 🔴 Needs a decision before fixing

### D1 — `spotify_metadata.py` violates "Spotify in playlist.py only"
**Rule:** `AGENTS.md` / `CLAUDE.md` both mandate all Spotify API calls in `core/src/playlist.py` only.
`core/src/spotify_metadata.py` hits `https://accounts.spotify.com/api/token` and
`https://api.spotify.com/v1/...` via `urllib` independently.

**Options:**
- Move the module's public helpers (`search_*`, `get_*_metadata`, `get_client_credentials_token`)
  into `playlist.py` (or an explicitly allowed sibling). ← recommended
- Document the deviation as an authorised exception in `CLAUDE.md` / `AGENTS.md`.

---

### D2 — `TechnicalManual.md` + `UserManual.md` describe removed RAG config constants
Several docs claim config constants that do **not** exist in `config.py`:
`RAG_ENABLED`, `RAG_CORPUS_PATH`, `RAG_POOL_SIZE`, `RAG_POPULARITY_PENALTY`,
`RAG_STRATIFIED`, `RAG_FACET_WEIGHTS`, `RAG_MANIFEST_URL`, `BATCH_SIZE_WITH_RAG`,
`get_effective_batch_size()`.

The same false claim appears in:
- `documentation/TechnicalManual.md` lines ~254–292 ("RAG candidate-pool feature" section)
- `documentation/UserManual.md` lines 174–178 ("Local LLM note")
- `documentation/help.en.md` line ~607
- `documentation/help.de.md` line ~610

**Question:** Were these constants intentionally removed (docs are wrong → rewrite to match
staged-pipeline reality) or accidentally lost (code is wrong → restore constants)?
Only `RETRIEVE_CANDIDATES_SIZE = 40` survives in `config.py`.

---

## 🟡 Should-fix — no decision needed, just work

### S1 — Pre-existing frontend test flake: `ragUpdateTip` toast intercepts pointer events
Several modal tests fail non-deterministically because the "New artist database available"
RAG-update toast appears on top of modal buttons and blocks clicks.

Affected tests (flaky, not always failing):
- `test_modals.TestHelpModal::test_closes_on_close_button`
- `test_modals.TestHelpModal::test_closes_on_overlay_click`
- `test_modals.TestSettingsModal::test_shows_model_dropdown`

**Recommended fix:** add an autouse Playwright fixture that dismisses / hides the
`#ragUpdateTip` element before each modal test, e.g.:
```python
@pytest.fixture(autouse=True)
def dismiss_rag_tip(page):
    page.add_init_script("document.addEventListener('DOMContentLoaded', () => { const t = document.getElementById('ragUpdateTip'); if (t) t.style.display = 'none'; });")
    yield
```
Or add `pointer-events: none` to the toast container when running under test.

### S2 — Pre-existing frontend test flake: `test_toggle_opens_and_closes_editor`
`frontend/tests/test_profile.py::TestProfileEditor::test_toggle_opens_and_closes_editor`
fails intermittently on baseline (confirmed pre-existing). The `close_profile_editor`
helper clicks `#trainToggleBtn` but `#trainBody` remains visible. Likely a CSS animation
not completing before the `to_be_hidden` assertion. Add a CSS transition override
in `conftest.py` (`page.add_style_tag(content="* { transition: none !important; animation: none !important; }")`)
or wait for the animation to complete before asserting.

### S3 — `eval_log.py`: `_profile_section_sizes` — `meta.goal` never populated
`meta_goal_chars` will always be 0 because nothing in the codebase sets `meta.goal`.
Either remove the field from the telemetry row, or implement the `meta.goal` concept
(requires a product decision on what "goal" means).

### S4 — Hardcoded English error strings raised to the UI (i18n sweep)
Backend exceptions whose messages surface directly in the UI:
- `playlist.py:840` — 403 reconnect message
- `openai_http.py:94–97, 275–278` — config + unsupported-model errors
- `suggestions.py:433, 438` — empty/invalid AI response messages
- `analysis.py:38` — "Artist name is required."

These should carry an i18n key so the frontend can translate them.
Pattern: raise a structured error with a `key` attribute + English fallback;
frontend looks up `i18n(error.key, error.message)`.

### S5 — `dislike_track`: track-level duplicate check missing (only artist-level was fixed)
Track-level dislikes (`profile["feedback"]["disliked_tracks"]`) have no dedup guard;
a user can press "dislike" on the same track multiple times and get N identical entries.
Add the same case-insensitive normalisation used for artist-level rejections.

### S6 — `openai_http.py`: `_NO_TEMPERATURE_MODELS` set is empty — dead branch
`core/src/openai_http.py` lines ~286–292: the set is always empty (noted in comment).
The branch is unreachable code. Either remove or move to config so it can actually
be populated when the next reasoning-tier model arrives.

### S7 — `suggestions.py`: 80-line `_STAGE3_JSON_SCHEMA` is dead code
Lines ~100–183: the json_schema variant was reverted; the schema and
`_stage3_response_format()` helper are unreachable. Either delete (use git history
to retrieve) or add a unit test proving consistency with the live prompt.

### S8 — Cover the local-LLM auto-downgrade path with a direct unit test
`openai_http._looks_like_schema_rejection` + `_JSON_SCHEMA_UNSUPPORTED` cache is
the canonical local-LLM compatibility pattern called out in `AGENTS.md` as a P0
product rule. It currently has no dedicated test — a regression here would silently
break every local-LLM user.

### S9 — Cover `validate_profile_schema` / `import_profile_dict` with unit tests
Profile import/export and schema validation (`core/src/profile.py`) have no direct
tests. Risk: silent profile corruption on save/import. These are P0 data-integrity paths.

### S10 — Hardcoded ARIA labels with interpolated artist/track names (i18n)
`frontend/templates/generate_section.html` lines 305–306:
`aria-label="Feedback on {{ track.artist|e }} — {{ track.title|e }}"` is untranslatable
server-side. Use a JS post-process step: store `data-track-artist` + `data-track-title`
attributes and update `aria-label` from the locale template string at render time in JS.

### S11 — `profile.py:swap_profile_with_history` is not crash-safe
Lines ~295–305: three sequential `rename` calls. If the process is killed between
step 2 and step 3, the backup copy is unrecoverable. Add a startup recovery path
that detects an orphan `*.swap.tmp` and either restores it or warns the user.

### S12 — `_migrate_flat_profiles` runs on every `load_profile` call
`core/src/profile.py` lines ~76–146: `ensure_profile()` is called on every request;
it calls `_migrate_flat_profiles()` which globs all `PROFILES_DIR/*.json` each time.
Add a module-level "already migrated this process" flag.

### S13 — Consolidate `EMPTY_PROFILE` / `TRAINED_PROFILE` constants into one shared module
`frontend/tests/helpers.py:174–198` and `helpers_integration.py:81–105` define these
twice with subtle drift risk. Move to `frontend/tests/_shared.py`.

---

## 🟢 Nice-to-have / polish

### N1 — `_auth_status_cache` doesn't cache the negative result
`core/src/playlist.py` lines ~198–204: on failure the cache slot is set to `None`,
so every failed status poll re-validates the token. With 1 req/sec polling from the
frontend this is unnecessary network traffic. Cache `"not_authenticated"` with the
same TTL.

### N2 — JS `addEventListener` leak in `quickstart-demo.js`
`frontend/static/js/modules/quickstart-demo.js`: `_openLightbox` adds a `keydown`
listener on every open call. Verify that the matching `removeEventListener` fires on
close; add it if not.

### N3 — Onboarding i18n: several hardcoded English strings / aria-labels not yet wired
`frontend/templates/onboarding.html` has ~10 hardcoded strings/aria-labels that have
matching or close-enough i18n keys but lack `data-i18n*` wiring. See full list in the
2026-04-28 frontend code-review report.

### N4 — `help.de.md` uses localised anchor IDs; `help.en.md` / `help.jp.md` use English ones
`/api/help/section/<anchor>` deep-links will 404 in German because the German file
uses `#erste-schritte` while the UI may request `#getting-started`. Normalise all
three files to use English anchors for stable cross-language deep-linking (`help.jp.md`
already does this correctly).

### N5 — `analysis.md` is pre-rework (2026-04-21) and superseded by `result-improvement.md`
Add a one-line banner at the top of `analysis.md`:
> _Status (2026-04-28): superseded by `result-improvement.md` Phase 2.6 / Scenario decisions. Kept as historical reference._

### N6 — `evaluation/README.md` line 20 says "30-track playlist" but baseline is 15 tracks
Update to: "Generates a 15-track playlist (configurable via `evaluation/scenario.py`)."

### N7 — `SKILL.md` `SKILL: git-commit-and-push` section should note the no-auto-commit rule
Add a prefix: "This procedure is invoked **only** when the user explicitly says 'commit and push'.
The agent must never initiate it autonomously."

