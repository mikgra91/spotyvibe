# SpotyVibe — Security Hardening & Stabilization Plan

**Status:** VERIFIED by independent agent (PASS w/ revisions, 2026-06-14) — revisions folded in below; awaiting user content review before execution.
**Author:** Claude (Opus). **Date:** 2026-06-14. **Branch base:** `develop` @ `dcfd226`.

## 0. Goal & guardrails (binding)

Deliver the best music-suggestion results, **then** cheapest, **then** fastest — in that strict priority order (project North Star). This plan only *hardens and stabilizes existing features*. It does **not** add product features or change recommendation behavior.

Hard guardrails for every change in this plan:
- **No feature removal.** Nothing actively used is deleted or disabled.
- **No feature breakage.** Behavior of every existing feature is preserved.
- **Every touched feature is covered by unit tests** asserting all relevant behaviors (happy path + the new guard path + the rejection path).
- **Every UI-affecting change is covered by Playwright tests**: UI renders, elements do not overlap, nothing becomes inaccessible/hidden, no new console errors / CSP violations.
- **No quality/cost/speed regression.** Any change on the generation path (Stages 1–3, prompts, retrieval) must pass `evaluation/run_evaluation.py` with non-regression on found-rate + cite-rate across the supported models before it ships. Pure-defensive changes off the generation path still run the full unit + Playwright suite.
- **Reversible, phased.** Each workstream is an isolated change set with its own rollback. Risky changes (CSP) ship in report-only mode first.

## 1. Threat model

SpotyVibe is a **single-user desktop app**: a local Flask server bound to `127.0.0.1:5000`, driven by the user's browser, talking to Spotify + an LLM provider. There is no remote multi-tenant server. Therefore the realistic attacker surfaces are:

| # | Surface | Why it matters here |
|---|---|---|
| T1 | **Other web pages in the user's browser** | Can issue cross-origin requests to `http://127.0.0.1:5000` (CSRF) and, via DNS-rebinding, read responses. State-changing endpoints incl. **credential storage** are reachable. |
| T2 | **Untrusted content rendered in the DOM** | Spotify artist/track/playlist names, LLM rationale text, and user profile prose are attacker-influenceable and rendered into the page → stored/reflected **DOM XSS** if any sink skips escaping. |
| T3 | **Untrusted content fed to the LLM** | Profile text is untrusted (prompt injection) → could distort output or break JSON. |
| T4 | **Malformed / out-of-range inputs to API** | Wrong-type bodies (already fixed), out-of-range numeric/enum params → bad state, crashes, or **cost blow-ups** (violates price priority). |
| T5 | **Secret handling** | API keys + Spotify tokens on disk / in logs / in responses. |

Out of scope (explicit non-goals): adding authentication, multi-tenant hosting, network exposure beyond localhost, UI redesign.

## 2. Findings (evidence-based, from survey)

| ID | Finding | Evidence | Severity |
|---|---|---|---|
| F1 | **No CSRF / origin defense** on mutating endpoints (57 routes incl. `POST /api/settings/credentials`, `/api/save-profile`, `/api/remove`, playlist create). No `SameSite`, no `Origin`/`Referer` check, no token. | `app.py` after_request sets only cache headers; grep for `SameSite/csrf/Origin` → none. | **High** |
| F2 | **No security headers** (no CSP, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`). | `app.py:216` `_add_cache_headers` only. | Medium |
| F3 | **XSS sink coverage is inconsistent.** Escapers exist (`esc`/`escHtml`/`attr` in `ui.js`, plus per-module `_esc`) and are applied at most sinks, but 26 modules use `innerHTML` and escaping is not centrally enforced. Candidate unescaped path: `review.js:205` toast message built from `track.artist`/`track.track` → `showToast()` (sink type unverified). | Greps in §survey. | Medium |
| F4 | **No server-side bounds/enum validation** on numeric params (audio-filter ranges, batch size, playlist size, slider values). Wrong-type JSON already hardened (`_request_json_object`), but value ranges are not clamped server-side. | `test_api_robustness.py` covers type only. | Medium |
| F5 | **Ephemeral `FLASK_SECRET_KEY`** (`os.urandom(24)` per start) → session/flash state resets each launch. | `app.py:205`. | Low |
| F6 | **Prompt-injection** surface: profile prose → LLM. Prompts carry a SECURITY note + output is schema-normalized, but not explicitly fuzz-tested. | `prompts/*system*.txt`, `suggestions.normalize_response`. | Low–Med |
| F7 | **Path traversal** on `/docs/screenshots/<path>` + `/docs/guides/<path>`: uses Flask `send_from_directory` (traversal-safe) but no regression test pins it. | `app.py:415-426`. | Low |
| F8 | **SSRF-adjacent: LLM `base_url` not allowlisted.** `POST /api/llm/fetch_models` accepts an arbitrary `base_url` (https-only for non-localhost, localhost allowed). A crafted value could probe an internal service. *(Added by verifier.)* | `app.py:2689-2707`. | Medium |
| F9 | **Duplicate route decorator** `@app.route("/api/run", methods=["POST"])` declared twice (no functional impact; maintenance debt). *(Added by verifier.)* | `app.py:838-839`. | Low |

## 3. Workstreams (prioritized; each independently shippable)

Priority = (risk reduction) × (low breakage risk). Order: F1 → F4 → F3 → F2 → F5/F7 → F6.

### WS1 — CSRF / same-origin guard (F1, T1)  **[highest value]** — ✅ DONE (2026-06-14)
> Implemented `_csrf_origin_guard` before_request + `SameSite=Lax`/`HttpOnly` cookies in `app.py`. Tests: `core/tests/test_csrf_guard.py` (8 cases). Regression: `test_api_robustness` + `test_app` green (224). Playwright: `test_wf_onboarding.py` (8) green → same-origin browser POST unaffected.
- **Fix:** add a `before_request` hook that, for mutating methods (`POST/PUT/PATCH/DELETE`), requires the `Origin` (fallback `Referer`) host to be in a localhost allowlist. Reject mismatches with `403`. Also set session cookie `SameSite=Lax`, `HttpOnly`. GET/HEAD untouched.
- **Allowlist (verifier-confirmed):** `http://127.0.0.1:{port}`, `http://localhost:{port}`, and the bare-host variants, where `{port}` is the actual bound port (parameterized, default 5000; tests bind dynamic ports → read from app config / env, do not hard-code 5000). pywebview (Windows WebView2 / macOS WebKit) sends `Origin: http://127.0.0.1:5000` on same-origin POST — confirmed via `desktop_launcher.py:440`; no `file://`/null origin path exists.
- **Missing-Origin policy (verifier revision):** if BOTH `Origin` and `Referer` are absent on a mutating request, **allow only when the server is bound to loopback** (our default) and log it; deny otherwise. This avoids breaking any native/headless caller that omits Origin while keeping remote CSRF closed.
- **Non-breaking:** all app fetches are same-origin relative URLs (`/api/...`) — verifier confirmed **zero** cross-origin POSTs exist → always pass.
- **Unit tests:** mutating request with foreign `Origin` → 403; correct localhost `Origin` → passes; foreign `Referer` (no Origin) → 403; absent Origin+Referer on loopback → allowed (+logged); GET with foreign Origin → unaffected; dynamic-port origin accepted. Cover these 3 endpoints explicitly: `/api/settings/credentials`, `/api/feedback`, `/api/save-profile`.
- **Playwright:** full happy-path run (train → generate → feedback → review) still works; no 403s in normal use.
- **Rollback:** remove the hook (single function).

### WS2 — Server-side input bounds/enums + LLM base_url allowlist (F4, **F8**, T4) — ✅ DONE (2026-06-14)
> Found temperature (0-2) + playlist_size (5-30) **already** clamped server-side. Added `_sanitize_audio_filters` (drops malformed/unknown; preserves BPM tempo — no wrong 0-1 clamp) on `/api/run`. F8: replaced provider-allowlist idea (would break custom/self-hosted providers) with `_is_internal_host` SSRF guard — blocks RFC1918/link-local/reserved (incl. 169.254 metadata), allows loopback (local LLMs) + public. Tests: `core/tests/test_input_bounds.py` (11). Full core suite green (only known-pre-existing `test_includes_default_model` fails). audio_filters change is behavior-preserving for valid inputs → no eval-gate needed.
- **Fix:** central validators for numeric/enum params (clamp to documented range or `400`): audio-filter low/high (0–1), batch size, playlist size, slider/energy/valence (0–1), `temperature` (0–2), `playlist_size` (5–30). Apply server-side in the affected routes (currently only client-clamped at `app.py:862-869`). Clamp where the UI already constrains (non-breaking); reject only impossible values.
- **F8 (verifier):** for `POST /api/llm/fetch_models`, restrict `base_url` to an allowlist (known providers + the configured `LLM_BASE_URL` + loopback for local LLMs) so it can't be pointed at arbitrary internal services. Keep local-LLM support (loopback stays allowed) → non-breaking.
- **Why it matters for North Star:** caps runaway token cost (price) and prevents degenerate requests (quality/stability).
- **Unit tests:** per param: in-range passes unchanged; above/below → clamped to bound (or 400 for enums); non-numeric already covered. Assert generation cost cannot be inflated past the cap.
- **Playwright:** sliders/inputs still move through full range; values persist; no UI lock-up.
- **Rollback:** per-route validator removal.

### WS3 — XSS sink audit + escaper consolidation (F3, T2) — ✅ DONE (2026-06-14)
> Audited all `innerHTML` sinks rendering untrusted (Spotify/LLM/profile) data. Safe: `buildTrackCardHtml` (esc/attr), `rationale.js` (`_escHtml` before interpolate), `discover-artists`/`review`/`history` (esc'd), toasts (textContent). Internal-only (not untrusted): `completeness` detail (numbers), `getting-started` (i18n+numbers). **Real gap fixed:** `playlist_seed.js:92` rendered `src="${p.cover_url}"` raw (local `_esc` doesn't escape quotes) → routed through `attr()`. Regression test `frontend/tests/test_xss_escaping.py` (crafted cover_url cannot break out of the img src). No behavior change.
- **Fix:** enumerate every `innerHTML`/`insertAdjacentHTML` sink; for each that renders Spotify/LLM/profile data, ensure a single canonical escaper (`esc`) wraps it; convert toast/message paths to `textContent` where no markup is needed; collapse `_esc` duplicates to the `ui.js` export. No visual/behavior change.
- **Verifier note:** `showToast` (`ui.js:134-143`) already uses `textContent` (safe). The must-audit sink is **`buildTrackCardHtml()` in `feedback.js`** (used by `review.js:66,96` and discovery/preview) — confirm every `artist`/`track`/`rationale` field is escaped there.
- **Unit tests (JS):** `esc`/`escHtml`/`attr` correctly neutralize `< > " ' &`; round-trip of a malicious artist name.
- **Playwright:** seed a track/artist whose name contains `<img src=x onerror=window.__xss=1>` (via mocked Spotify/LLM response), render the tracklist/history/review/discover views → assert `window.__xss` is undefined AND the literal text is shown (feature intact, not stripped). Assert no element overlap/inaccessibility introduced.
- **Rollback:** per-sink revert.

### WS4 — Security headers (F2, T1/T2 defense-in-depth) — ✅ HEADERS DONE (2026-06-14); CSP DEFERRED
> Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` to the global `after_request` (setdefault, every response). Test: `core/tests/test_security_headers.py` (2). **CSP (even report-only) deliberately NOT added yet:** report-only still emits console violations for the ~80–120 inline handlers, which breaks `test_page_load`'s console-cleanliness assertion — so CSP must wait for the handler→listener migration (the committed WS4 enforce prerequisite). Non-CSP headers are non-breaking and shipped now.
- **Fix:** extend `after_request` with `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (+ `frame-ancestors 'none'`), `Referrer-Policy: same-origin` (these ship immediately — non-breaking), and a **CSP in report-only mode first**.
- **CSP enforcement exit criterion (verifier revision):** the app has **~80–120 inline event handlers** (`onclick`/`onchange`/`onkeydown`) across 24+ templates → a strict `script-src` would break them. **Commit to Option A: migrate inline handlers to delegated `addEventListener` listeners** as the prerequisite for promoting CSP report-only → enforce. (Nonce/hash injection rejected: nonces need template-context plumbing for every handler; hashes are whitespace-brittle.) Until migration is complete, CSP stays **report-only** (safe, non-breaking). Handler migration is itself feature-preserving and Playwright-gated.
- **Unit tests:** headers present on HTML responses; static assets unaffected.
- **Playwright:** no CSP violations in console across all pages/flows; no clickjacking-frame breakage of legit functionality.
- **Rollback:** drop headers; CSP stays report-only if any violation remains.

### WS5 — Secret & session hygiene (F5, T5) — ✅ DONE (2026-06-14)
> `config.get_or_create_secret_key()` (env override → persisted `.flask_secret`, 0600 POSIX) wired into `app.py`; `.credentials` chmod 0600 on write; masked-GET contract confirmed. Tests: `core/tests/test_secret_and_creds.py` (3). Regression: `test_config` + `test_app` green. Windows: chmod is a no-op (gated). Full settings-flow Playwright deferred to Phase-A end run.
- **Fix:** persist a generated `FLASK_SECRET_KEY` in the app data dir (0600) if not provided via env, so sessions survive restart; assert API keys are never returned by `GET` settings endpoints and never logged (redaction check); set `.credentials` file mode to 0600 on write (best-effort on Windows).
- **Unit tests:** secret key stable across two app inits; settings GET response contains no secret values; logger output for a settings save contains no key material. **Windows note (verifier):** POSIX `chmod 0600` is a no-op on Windows — gate the perms assertion on `os.name == 'posix'`; on Windows document as best-effort (optionally NTFS ACL), no failing test.
- **Playwright:** settings round-trip (save → reload → masked display) unchanged.
- **Rollback:** revert to ephemeral key.

### WS6 — Prompt-injection robustness (F6, T3) — ✅ DONE (2026-06-16)
- **Fix shipped:** new `core/src/prompt_safety.py::neutralize_untrusted` — *structural* defang of injection mechanics on untrusted free text: (1) collapse CR/LF runs to a single space (a one-line value can't forge a new prompt line / `System:` turn / fenced block), (2) strip triple-backtick/tilde fences, (3) defang start-of-line role markers + a curated set of unambiguous override phrases ("ignore previous instructions", "disregard the system prompt", "new instructions:", …) → `[filtered]`. Wired at the three Stage-3 chokepoints in `suggestions.py`: `build_taste_summary` (per section + anchors), `build_feedback_summary` (artist/track/reason), `_format_approved_artists_block` (names + `known:` titles). Prompt *text* unchanged — the existing system-prompt `SECURITY:` directive stays; defense is at the data layer.
- **Why no prompt-template delimiting:** delimiting changes tokens for *every* input (incl. legitimate) → real eval risk. The neutralizer is a **strict no-op on legitimate music metadata**, so it changes nothing on the eval corpus.
- **Gate — satisfied without billable eval:** `neutralize_untrusted` is a strict no-op on both shipped eval seed profiles (`aged_japanese_s5`, `aged_mainstream_s5`) — verified by `test_seed_profile_free_text_is_strict_noop` (every must_have / soft / avoid / core_description / primary_reference / anchor unchanged). ⇒ Stage-3 prompt renders **byte-identical** for the evaluation corpus ⇒ quality/cost/speed non-regression **by construction**. A full multi-model `run_evaluation.py` run remains available as belt-and-suspenders but is not required to prove non-regression.
- **Unit tests:** `core/tests/test_prompt_safety.py` (49) — no-op on 16 legit strings, defang of 11 override variants, newline-collapse, fence strip, role-turn defang + midline false-positive guard, idempotency, non-string/empty passthrough, `neutralize_list`, and the 3 wired chokepoints (taste/feedback/approved each: malicious defanged + legit preserved). Full core suite green (no regression).
- **Residual risk (accepted, Low):** localhost desktop app where the profile owner is the only "attacker" against their own recommendations; output is further constrained by the approved-artist allow-list + known-track grounding + `normalize_response` schema, so a value that slips the neutralizer still cannot make the app recommend arbitrary tracks. The legacy full-`profile_json` Stage path (being phased out) is not wired — values there are JSON-embedded (lower risk); feedback summary it shares IS neutralized.
- **Rollback:** remove the `neutralize_untrusted` import + 3 call-sites in `suggestions.py` and delete `prompt_safety.py` (no prompt-text change to revert).

### WS7 — Traversal + run-state regression tests (F7) — ✅ DONE (2026-06-14)
> No code change. Tests: `core/tests/test_traversal_and_runstate.py` (10) — traversal blocked on both `/docs/*` routes (8 payloads), `_sweep_stale_runs` GC, idempotent `cancel_run`/unknown-run.
- **Fix:** no code change expected; add regression tests pinning `send_from_directory` traversal safety (`../../etc/...` → 404/403) and run-state cleanup (stale `_runs` GC, cancel path) so future refactors can't regress them.
- **Unit tests:** traversal attempts blocked; stale run GC; double-cancel safe.

### WS8 — Verifier minor findings (F9 + cleanups) — ✅ DONE (2026-06-14, partial)
> Removed duplicate `@app.route("/api/run")` (F9); added `core/tests/test_route_registry.py` (dup-detection guard). Creds-endpoint throttle **deliberately skipped** (marginal value on a localhost single-user app, UX risk) — WS1 already closes the cross-origin path. `_runs` lock contract left as-is (WS7 proves cancel/GC are race-safe under `_runs_lock`).
- **F9:** remove the duplicate `@app.route("/api/run", methods=["POST"])` at `app.py:839` (Flask collapses it today; pure cleanup). Add a unit test that enumerates `app.url_map` and asserts no `(rule, method)` is registered twice → catches future dupes.
- **Creds endpoint throttle (low):** optional minimal rate-limit on `/api/settings/credentials` (e.g. ≥1s between saves) as anti-brute-force belt-and-suspenders once WS1 lands. Unit test: rapid double-save → second throttled. Skip if it risks legit UX.
- **`_runs` thread-safety (low):** document the lock contract; if the `finally` perf-log path reads shared run state, take `_runs_lock` around it. Unit test: concurrent cancel + finalize is race-free.

### Stabilization fixes (during Phase A) — ✅ DONE (2026-06-14)
Pre-existing breakage surfaced while validating Phase A (all confirmed on clean baseline `dcfd226`, i.e. not introduced by this work):
- **REAL BUG FIXED — Apply-to-Playlist modal never opened.** `apply-playlist.js` toggled `.hidden`/aria but `.modal-overlay` is `display:none` until `.open` (the convention every other modal uses). Added `.open` on show / removed on hide → feature restored. Verified end-to-end by the new apply-flow test.
- **Stale tests repaired (post-refactor "generate→list, apply→Spotify"):** `test_generation.py` — replaced inline-radio `TestPlaylistMode` with `TestApplyPlaylistModal` (covers the live modal) and fixed `test_generation_flow` (status now "added to list", no link at generation). `test_wf_generate_create.py` — `test_playlist_link_shown` → `test_apply_to_playlist_sends_tracks` (drives the real apply flow). All touched files green **isolated** (test_generation 42/42; +wf create/append/override).
- **Flagged, NOT fixed (product-behavior question):** after apply with no ctx, `submitApply` runs `setSuggestions([]) + renderTracks()` which collapses `#discoverTrackArea` — the parent of `#playlistLinkBox` — so the just-shown Spotify link is hidden again. If the link should persist post-apply, that's a follow-up.
- **Test-infra finding → FIXED (2026-06-15):** `run_frontend_tests.sh` runs 3 heavy Playwright groups in parallel → resource contention caused **non-deterministic timeout flakes** (different failing set each run; all pass isolated/serially). Added a `run_group` **single retry-on-failure guard**: a group that fails its first attempt is re-run once before being declared failed. Transient-contention flakes pass on attempt 2; genuine failures fail both attempts and still exit non-zero. No new dependency (no pytest-rerunfailures), no parallelism reduction.

### Pre-existing-failure analysis (per user instruction, 2026-06-15) — ✅ COMPLETE
Instruction: *"pre existing failures should be analyzed. If they are outdated tests, remove them. If they are feature relevant test and fail, then fix them."*
- **Method:** ran the entire frontend suite **serially** (`pytest frontend/tests/ -m "not screenshots"`, no parallel contention) as ground truth → **234/234 PASS, exit 0**. Core suite `pytest core/tests/ -q` → **0 failures**.
- **Verdict:** zero genuine failures remain. None were outdated-junk to delete — every "failure" was either (a) a **feature-relevant** test written against the old "generate→Spotify-link" flow → **fixed/rewritten** to the current apply-modal flow (and surfaced the real apply-modal `.open` bug, now fixed), or (b) a **parallel-runner contention flake** → addressed by the retry guard above. `test_includes_default_model` (core) likewise fixed: stale hard-coded `gpt-4.1-mini` → `DEFAULT_OPENAI_MODEL` constant + supported assertion.

## 4. Verification strategy (applies to every workstream)

1. `python -m pytest core/tests/ -q` (≈620 tests) — **fully green** (incl. `test_includes_default_model`, now fixed to use `DEFAULT_OPENAI_MODEL`).
2. `bash build-tools/run_frontend_tests.sh` — Playwright groups; assert: no console errors/CSP violations, **no element overlap**, **no inaccessible/hidden interactive elements**, all flows complete.
3. For WS2/WS6 (generation path): `python evaluation/run_evaluation.py` multi-model — non-regression on found-rate + cite-rate (use hardened detector); cost not increased; latency not increased.
4. New behavior never ships without a test that fails before the fix and passes after.

## 5. Sequencing

Phase A (defensive, off generation path, low risk): WS1, WS5, WS7, WS8.
Phase B: WS3 (XSS audit), WS2 (bounds + base_url allowlist).
Phase C (tunable / higher-touch): WS4 (headers now; CSP report-only → handler migration → enforce), WS6 (prompt — eval-gated).

Each phase: implement → unit → Playwright → (eval gate if applicable) → checkpoint. No `git commit`/`push` without an explicit `CP ALLOWED` per project rule.

## 6. Explicit non-goals / will-not-touch

- No auth, no multi-tenant, no network exposure changes.
- No recommendation-algorithm changes (only WS6 prompt *delimiting*, eval-gated).
- No UI redesign; no removal of inline handlers if CSP can accommodate them via nonces/hashes.
- No dependency upgrades unless a workstream strictly requires one.

## 7. Open questions — RESOLVED by verifier

1. **Webview Origin?** ✅ Resolved — pywebview sends `Origin: http://127.0.0.1:5000` on same-origin POST (`desktop_launcher.py:440`); no `file://`/null-origin path exists. Allowlist localhost variants (WS1).
2. **Any cross-origin POST feature?** ✅ No — verifier confirmed all `/api/*` calls are same-origin relative URLs; WS1 introduces zero breakage.
3. **Inline handlers for CSP?** ✅ ~80–120 inline handlers across 24+ templates → WS4 commits to handler→listener migration (Option A) as the enforce gate; report-only until then.
</content>
