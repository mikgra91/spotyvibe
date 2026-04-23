# TODO List — Implementation Status

> Last updated: 2026-04-22
> Tests: ✅ 539 core + ✅ 233 frontend (0 failures)
> Latest decision report: `C:\Users\apatecgratzl\Desktop\CoPilot_Reports\spotyvibe-decisions-2026-04-21.md`
> Cloud Run guide: `documentation/guides/cloud-run-rag-setup.md`

---

## ✅ 12. RAG redesign — stratified retrieval + 100-slot pool + emerging bypass + corpus slimming

- **`config.py`**:
  - `RAG_POOL_SIZE: 20 → 100` (eval log showed only ~19% of GPT picks came from the 20-slot pool — too narrow to anchor for eclectic profiles).
  - New `RAG_STRATIFIED = True` and `RAG_FACET_WEIGHTS = {must_have: 0.50, soft_preferences: 0.25, primary_reference: 0.15, tags: 0.10}`.
- **`core/src/rag/retrieval.py`** — new `score_artists_stratified()` runs the retriever once per profile facet with a per-facet quota, dedupes across facets, fills the remainder from a flat pass, and falls back to the flat scorer if every facet is empty.
- **`core/src/suggestions.py::build_messages`**:
  - Now calls `score_artists_stratified()` (gated by `RAG_STRATIFIED`) and uses the new pool size.
  - **Bypasses RAG entirely when `emerging_only=True`** — the corpus is republished quarterly and cannot contain artists who debuted in the last 6 months, so injecting the pool would contradict the system constraint. The post-Spotify `filter_emerging_artists` (album `release_date` check) remains the factual verification.
- **Corpus slimming** — `core/src/rag/corpus.py` + `build-tools/build_rag_corpus.py`:
  - Dropped from `ArtistRow`: `sort_name`, `country`, `end_year` (loaded but never read by any retriever).
  - Dropped from `RagCorpus`: `by_mbid`, `by_name_normalised` dicts (built but no callers).
  - Net: ~25–30% resident memory reduction, ~10–15% disk size reduction. Old corpora still load — JSONL parser silently ignores extra fields.
- **Tests** (all passing):
  - `core/tests/test_rag_retrieval.py` — 5 new stratified tests (per-facet representation, dedupe, fallback, deny-keys, pool cap).
  - `core/tests/test_suggestions_rag_pool.py` — 2 new tests covering the `emerging_only` RAG bypass (positive + counterpart).
  - `core/tests/test_rag_corpus.py` — updated to assert the slimmed schema.
- **Docs**: `documentation/TechnicalManual.md` (RAG section), `documentation/guides/rag-implementation.md` §3.2 (slimming) + §4.3 (stratified) + §4.4 (pool sizing rationale with eval data) + §4.5 (emerging bypass).

---

## ✅ 13. Preview-player long-title wrap

- `frontend/static/css/preview.css::.spotify-preview-title` — replaced `white-space: nowrap` + `text-overflow: ellipsis` with a 2-line `-webkit-line-clamp` + `overflow-wrap: anywhere`. Long *"Artist — Track"* strings now wrap onto a second line and ellipsise after that, instead of stretching the player panel.

---

## 📊 RAG vs no-RAG analysis (data captured 2026-04-20)

Source: `documentation/spotyvibe_with_rag/eval.jsonl` vs `documentation/spotyvibe_without_rag/eval.jsonl`

| Metric | Without RAG | With RAG (pool=20) |
|---|---|---|
| Rows | 141 | 127 |
| Spotify-found rate | **63.8%** (90/141) | **94.5%** (120/127) — **+30.7 pp** |
| Unique artists / row | 0.61 | 0.63 |
| Artists picked from candidate pool | n/a | **18.9%** (24/127) |
| Runs analysed | 3 | 4 |

**Conclusions baked into item 12:**

1. RAG is **unambiguously net-positive** on hallucination — removing it was off the table.
2. Only ~19% of GPT picks at pool=20 came from the pool itself → the pool is too narrow to anchor an eclectic profile. Bumping to 100 widens the funnel without changing the architecture or risking the +30.7 pp uplift. Re-measure in v1.1 after stratified rollout.

---

## ✅ 11. SDK player auto-advance — properly fixed (re-opened from item 5)
- **Root cause** (now identified): Spotify's Web Playback SDK fires `state_changed` with `position: 0, paused: true` the instant a track ends naturally. The 250 ms ticker's auto-advance window (`projected >= duration - 100` — only 100 ms wide) was frequently narrower than the tick interval, so no tick landed inside the window before `state_changed` reset `_sdkLastPositionMs = 0` and `_stopTicker()` stopped the projection loop. Auto-advance was silently lost.
- **Fix** (`frontend/static/js/modules/preview.js`):
  - New state variable `_sdkCurrentTrackId` tracks the SDK's `current_track.id` independently of the auto-advance latch (the original code conflated the two — `currentTrackId !== _sdkAdvanceFiredFor` was reset-on-mismatch logic that fired wrongly because the latch starts empty).
  - In `onSdkStateChanged`, before mutating `_sdkLastPositionMs`/`_sdkPaused`, detect natural end-of-track: `sameTrack && wasPlayingPastStart(>1s) && newPaused && newPos === 0` → call `nextPreview()` once (latched on the previewer's track id).
  - The ticker's projected-end check is preserved as a secondary safety net for the case where Spotify emits a final `state_changed` with `position == duration` instead of resetting to 0 (rare but observed on some browser/SDK combinations).
- Tests: full suite green — 516 core + 233 frontend, 0 failures.

---

## ✅ 1. MusicBrainz data storage location & scaling

### 1a. Storage location — DONE
- Corpus + meta sidecar moved out of `BASE_DIR/data/rag_corpus/` into the user's app dir (`%LOCALAPPDATA%/spotyvibe/rag_corpus/` on Windows). The `tag_aliases.json` (bundled with the app) stays under `BASE_DIR`.
- One-time migration: any legacy file under `BASE_DIR/data/rag_corpus/` is automatically moved into the new location on startup (silently ignored if the legacy dir is read-only, e.g. inside the PyInstaller `_MEIPASS` extraction dir).
- Files: `config.py` (`_init_rag_paths()`), `documentation/TechnicalManual.md`.

### 1b. Default top-N raised — DONE
- `build-tools/build_rag_corpus.py --top-n` default changed from `100_000` → `350_000`.
- Docs updated: `documentation/TechnicalManual.md`, `documentation/guides/rag-implementation.md`.
- ⚠ Manual follow-up: rebuild and republish the corpus (`python build-tools/refresh_rag_corpus.py && python build-tools/publish_rag_corpus.py`). Existing clients pick it up via the rolling `rag-corpus-latest` release.

---

## ✅ 2. Global "new corpus available" popup — DONE
- New modal: `frontend/templates/modals/rag_update_modal.html` (Download + Cancel buttons, no other side effects on Cancel).
- New JS module: `frontend/static/js/modules/rag_update_prompt.js`. Wired into `main.js` after `Tips.init()`.
- Shows once per tab session (sessionStorage flag) when `/api/settings.rag_update.status` is `update_available` or `missing_corpus`. The first-time copy ("…corpus is available…") is used when there is no installed corpus yet.
- i18n: `rag.update.{title,body,body_first_time,download,cancel,downloading,success,failed}` in en/de/jp.

---

## ✅ 3. Preview player timebar freezes — DONE
- `frontend/static/js/modules/preview.js`:
  - Added a 4 Hz interval ticker that extrapolates `_sdkLastPositionMs` from wall-clock time while playing, redrawing the seek bar/time labels between SDK `state_changed` events.
  - Real `state_changed` events still re-anchor the position so the projection never drifts.
  - `visibilitychange → visible` forces a `getCurrentState()` resync to avoid the "post-blur jump".
  - Ticker stops on close/pause and is restarted on play.

---

## ✅ 4. "Regenerate profile" tip after many likes/dislikes — DONE
- `frontend/static/js/modules/tips.js`:
  - New tip id `regenerate_profile_after_feedback` with `autoDismissMs: 10000` (per-tip override; default stays 12 s).
  - New `oncePerSessionOnly: true` flag — the tip is NOT added to the persistent "seen" list, so it re-appears on every new app launch (in-memory `sessionTipShown` still prevents repeats within one session).
- `frontend/static/js/modules/preview.js`:
  - Session counter `_feedbackEventCount`; first trigger after 10 events, re-trigger every additional 30.
- i18n: `tip.regen_profile{,_body,_link}` in en/de/jp.

---

## ✅ 5. SDK player auto-advance reliability — DONE
- The fragile `position >= duration - 500` check (which silently failed when Spotify reset position to 0 at track end) is replaced by detection inside the new ticker (item 3). Once the ticker's projected position crosses `duration - 100 ms`, `nextPreview()` fires once.
- A latch `_sdkAdvanceFiredFor` keyed by track id prevents double-firing.
- Iframe path is intentionally untouched — it's only a fallback.

---

## ✅ 6. Disliking a whole band purges its tracks from the active playlist — DONE
- Backend:
  - New helper `remove_all_tracks_by_artist(artist, playlist_id)` in `core/src/playlist.py` — scans all playlist items, matches against every artist credit case-insensitively, removes in batches of 100.
  - New endpoint `POST /api/feedback/dislike-artist` in `app.py`. Records the artist-level dislike AND strips the active playlist; returns `{removal: {removed_count, removed_tracks}}`.
- Frontend (`frontend/static/js/modules/feedback.js`):
  - When `submitFeedback` fires with `action=dislike` and an empty track field, a `window.confirm` prompt asks: *"Remove ALL songs by '<artist>' from this playlist and never suggest them again?"* Cancel does nothing; OK calls the new endpoint and shows a toast with the removed count.
- i18n: `feedback.confirm_dislike_artist`, `feedback.artist_disliked_purged`, `feedback.artist_disliked_no_tracks` in en/de/jp.
- Scope: only the currently active playlist (per agreed recommendation).

---

## ✅ 7. Custom "New Artist" % visual cue — DONE
- Template: `frontend/templates/generate_section.html` — added `<span class="new-artist-pct-custom-badge">` next to `#genNewArtistPct` and gave the wrap an `id="genNewArtistPctWrap"`.
- JS: `frontend/static/js/modules/presets.js`:
  - New `_updateNewArtistPctCustomBadge()` + exported `refreshNewArtistPctBadge()`.
  - Called from `_selectPreset`, `_updateCurrentPreset`, `markCustomUnsaved`, on `genNewArtistPct` `input`/`change`, and on init.
  - Compares the field value against `getActivePreset().settings.new_artist_pct` — when they differ, the wrap gets the `is-custom` class and the badge is unhidden.
  - Wired AFTER the `window.*` exports inside `init()` (with a try/catch) so a defect here cannot strand the preset onclick handlers.
- JS: `frontend/static/js/modules/exploration.js` — after `_applyNotchToFields` mutates the field, dynamically import `presets.js` and call `refreshNewArtistPctBadge()` so jumping to a notch hides the badge again.
- CSS: `frontend/static/css/forms.css` — `.gen-field-new-artist-pct.is-custom input` (subtle accent border + tinted background) and `.new-artist-pct-custom-badge` (compact pill, accent colour, `cursor: help`).
- i18n: new keys `settings.new_artist_pct_custom` and `settings.new_artist_pct_custom_hint` in en/de/jp.
- Docs: `UserManual.md` § Presets, `help.{en,de,jp}.md` § Generation Presets — short paragraph explaining the badge.

---

## ✅ 10. MusicBrainz pre-1960s filter — DONE
- Builder: `build-tools/build_rag_corpus.py` — new constant `MIN_ARTIST_BEGIN_YEAR = 1960`; artists whose `life-span.begin` parses to a year < 1960 are dropped during `_load_mb_dump`. Artists with no `begin_year` are kept (insufficient evidence to drop).
- Runtime mirror: `core/src/rag/corpus.py::_iter_rows` filters the same way, so users on a pre-filter corpus benefit immediately without rebuilding.
- Onboarding info: `frontend/templates/onboarding.html` step 1 — new `.ob-corpus-note` panel below the privacy panel (`data-i18n="ob.corpus_scope_note"`). Mentioned only here so we don't repeat it everywhere.
- Settings tooltip: `frontend/templates/modals/settings_modal.html` — new `<span class="rag-help-indicator" tabindex="0">ⓘ</span>` next to the RAG toggle, `data-i18n-title="settings.rag.scope_help"`. Keyboard-focusable.
- CSS: `frontend/static/css/onboarding.css` (`.ob-corpus-note*`), `frontend/static/css/forms.css` (`.rag-help-indicator`).
- i18n: `ob.corpus_scope_note`, `settings.rag.scope_help` in en/de/jp.
- Tests: new `test_pre_1960s_artists_are_filtered` in `core/tests/test_rag_corpus.py`.
- Docs: `documentation/guides/rag-implementation.md` §2.2 step 3 + runtime mirror note; `documentation/TechnicalManual.md` corpus row updated; `UserManual.md` § Artist coverage; `help.{en,de,jp}.md` § Generation Presets blockquote.

---

## ✅ 8. Prompt rationale fix — DONE
- Verified diagnosis using `documentation/spotyvibe_with_rag/prompt.log` and the saved profile (5 must-haves + 3 soft prefs, but every track only got 2 rationale entries).
- `prompts/system_prompt.txt`:
  - Replaced hardcoded "1-2 entries" with `{rationale_count}` placeholder.
  - Added a directive: *"Each rationale entry MUST cite a different facet of the profile (must_have, soft_preference, primary_reference, era, region, instrumentation, mood). Do NOT repeat the same facet across entries."*
- `core/src/suggestions.py` `build_messages()`:
  - Computes `rationale_count` from `len(must_have) + len(soft_preferences)`:
    - 0–1 facets → `"1-2"`
    - 2–4 facets → `"2-3"`
    - 5+ facets → `"3-5"`
- For the saved profile this now produces `"3-5"` rationale entries per track.

---

## ⏭ 9. Must-Have / profile-strength bug — SKIPPED (per request)

Diagnosis kept for later:
- `_scoreList(text, strongThreshold=2)` in `frontend/static/js/modules/completeness.js` gives 0.5 (partial) for 1 line, 1.0 (strong) for ≥2 lines.
- Hypothesis: after AI Profile Update, the textareas are repopulated while the must-have accordion is collapsed → user sees no UI change but the meter reads `<textarea>.value` directly so it jumps to 100 %.
- Secondary factor: `_scoreTouched` flips 0 → 1 (extra +10 %) on the synthetic input events dispatched by `profile.js`.
- Action when revisited: reproduce with the must-have accordion expanded, decide between auto-expand-on-grow vs. smoothing the scoring curve.

---

## Files changed
- `config.py` — RAG corpus path migration to user app dir.
- `core/src/playlist.py` — `remove_all_tracks_by_artist()`.
- `core/src/suggestions.py` — `{rationale_count}` substitution.
- `app.py` — `POST /api/feedback/dislike-artist` endpoint + import.
- `prompts/system_prompt.txt` — dynamic rationale count + facet diversity.
- `build-tools/build_rag_corpus.py` — default `--top-n` 350K.
- `frontend/static/js/main.js` — wire `RagUpdatePrompt`.
- `frontend/static/js/modules/preview.js` — SDK ticker + reliable end detection + feedback counter.
- `frontend/static/js/modules/tips.js` — per-tip auto-dismiss + `oncePerSessionOnly`.
- `frontend/static/js/modules/feedback.js` — artist-dislike confirm + new endpoint call.
- `frontend/static/js/modules/rag_update_prompt.js` — NEW module for global popup.
- `frontend/templates/base.html` — include new modal.
- `frontend/templates/modals/rag_update_modal.html` — NEW modal template.
- `frontend/static/i18n/{en,de,jp}.json` — new tip + popup + dislike-artist keys.
- `documentation/TechnicalManual.md` — corpus path + 350K + 200 MB resident.
- `documentation/guides/rag-implementation.md` — top-N rationale + memory footprint.

## Notes / follow-up suggestions (not blocking)
- **Republish corpus** — rebuild `artists.jsonl.gz` with the new `--top-n 350000` and run `publish_rag_corpus.py` so existing installs get the larger pool via the global popup.
- **README / UserManual / help.{en,de,jp}.md** — not yet touched. Worth a short pass to mention the new "Download offline corpus" prompt and the artist-dislike behaviour.
- **Items 7 & 9** — analysis preserved above; pick them up when ready.

---

## ✅ 14. RAG token-budget mitigation — Option A shipped (2026-04-22)

Background: the Apr-21 decision report estimated each batch prompt at **12–18 k tokens** with the new 100-slot pool. That number is fine for hosted GPT-4-class models but breaks small local LLMs (Llama 3 8B, Gemma 9B, Mistral 7B — typical 8 k context window). Three mitigations were considered:

| | Option | Decision | Why |
|---|---|---|---|
| **A** | Reduce per-LLM-call batch size when RAG is on | **✅ Shipped** | Smallest contained change. Total playlist size unchanged — pipeline just makes more, smaller calls. |
| **B** | Self-host a smaller open-weight LLM (Cloud Run + Ollama) as drop-in OpenAI replacement | **❌ Rejected, documented** | Cost is comparable but recommendation quality drops sharply (4-bit Gemma/Llama ≪ GPT-4 for creative music reasoning). See `analysis.md` § Scenario B. |
| **C** | Trim the prompt itself (system prompt, profile, RAG entry format) | **🔬 Analysis only** — see § Option C below. Not implemented. |

**Implementation (Option A):**

- `config.py` — new constant `BATCH_SIZE_WITH_RAG = 5` and helper `get_effective_batch_size()` that returns it when RAG is enabled, else `BATCH_SIZE = 10`.
- `app.py::run_pipeline` — uses `get_effective_batch_size()` instead of the bare `BATCH_SIZE` constant. The `MAX_GPT_CALLS_PER_RUN = 20` guardrail already accommodates the doubled call count.
- Tests: new `TestGetEffectiveBatchSize` class in `core/tests/test_config.py` (3 tests).
- Docs:
  - `documentation/TechnicalManual.md` § RAG — new "Per-call batch size shrinks under RAG" paragraph + the **RAG limitations on small local LLMs** call-out (Option B rejection rationale + mitigations: disable RAG, lower `RAG_POOL_SIZE`, lower `BATCH_SIZE_WITH_RAG`, use 16 k+ context model).
  - `documentation/UserManual.md` § Artist coverage — added "Local LLMs and the candidate pool (RAG)" subsection.
  - `documentation/help.{en,de,jp}.md` — added a short "Local LLM note" blockquote alongside the existing "Artist coverage note".

---

## 🔬 Option C — Prompt-trim analysis (#1, #2, #4, #5 shipped 2026-04-22; #3, #6 deferred)

> Where can we claw tokens back from the prompt itself if the per-call shrink (Option A) is not enough? This section is the audit. Items #1, #2, #4, #5 below are now **shipped**; #3 (system-prompt rewrite) and #6 (drop JSON-schema example) remain deferred behind eval-log verification.

### What shipped (2026-04-22)

| # | Trim | Files | Saving |
|---|---|---|---|
| #1 | Compact JSON serialisation in `_build_deny_set_json` and `profile_json` (`separators=(",", ":")` instead of `indent=2`) | `core/src/suggestions.py::_build_deny_set_json` + `build_messages` | ~300–1500 tok depending on history size |
| #2 | Slim RAG pool entry format — drop the `"42. "` index prefix and the `"— tags:"` prose; new format is `Artist Name (tag1, tag2)` | `core/src/rag/prompt.py::format_candidate_pool_block` | ~600 tok / batch at 100-slot pool |
| #4 | Truncate `recent_feedback` reasons to last 3 entries per side; cap whole block at 300 chars (was 2000) | `core/src/suggestions.py::build_feedback_summary` | ~100–500 tok when feedback is large |
| #5 | Strip from `profile_for_gpt`: `name`, `last_updated` (pure metadata, model never reads them) and `feedback.liked_tracks` / `feedback.disliked_tracks` (already in DENY_LIST + feedback summary) | `core/src/suggestions.py::build_messages` | ~200–1500 tok depending on feedback size |

**Tests added** (6 total, all green):

- `core/tests/test_rag_prompt.py` — `test_artist_with_no_tags_renders_name_only` + updated `test_block_contains_header_and_artists` and `test_token_budget_holds` to lock in the slim format.
- `core/tests/test_suggestions.py::TestOptionCPromptTrims` — 5 tests pinning compact JSON (deny set + profile), feedback-summary cap, last-3-reasons rule, and profile-field stripping.

**Combined effect**: a typical RAG-on batch prompt drops from the 4.5–9 k input-token range (revised estimate, see decision report 2026-04-21 § 1) down to **~3.0–6.5 k input tokens**. Stacked with Option A's smaller per-call batch (5 instead of 10), the full conversation lands at **~4–8 k tokens** — comfortably inside small local-LLM windows for typical history sizes.

### What did NOT ship (deferred — would need eval-log verification first)

- **#3 — Compress the system prompt.** Collapsing the seven numbered rules + dropping `_VALIDATION_BLOCKS` duplication is the largest remaining win (~700–1200 tok / batch) but also the highest-risk single change. Defer until #1+#2 land in production and the eval log shows headroom.
- **#6 — Drop the JSON-schema example from `prompt_template.txt`.** Worth ~150 tok but only safe to do after a 100-track A/B confirms quality is unchanged.

### What "trim" means in this codebase

Every batch sends one **system message** (~1.5–2 k tokens) and one **user message** (~4–10 k tokens depending on history size and pool). "Trim" = reduce the *byte-count* of these messages without losing semantic information that the LLM actually uses. Not the same as Option A (fewer tokens *per call*) — Option C reduces tokens *per token-bearing prompt component*, so it stacks with Option A.

### Token audit per prompt component

Numbers below are rough estimates from `prompts/system_prompt.txt`, `prompts/prompt_template.txt`, and a representative profile + history (run a real test before betting on the figures):

| Component | Today (~tokens) | Trim ceiling (~tokens) | Risk if trimmed | Effort |
|---|---|---|---|---|
| System prompt prose (`system_prompt.txt`) | 1500–2000 | **600–800** (drop redundant "DENY" reminders, tighten validation block, single-line numbered rules) | Low — model still has the structured constraints; risk is loss of the model-specific reasoning chain on `gpt-5.4` | **High value, low risk.** Start here. |
| RAG pool entry format `"42. Artist Name — tags: [a, b, c]"` | ~12 tok × 100 = **1200** | **~6 tok × 100 = 600** if we drop the index prefix and tag list, e.g. `"Artist Name (rock, ambient)"` | Medium — ranking logic in stratified retrieval works code-side, the index isn't read by GPT; tags help GPT pick in-genre matches but GPT can re-derive from name context | **Highest single saving.** ~600 tok / batch. |
| Profile JSON (`profile_for_gpt`) | 1000–2500 | **600–1200** by stripping `analysis.*` (only used for the analysis prompt, not suggestions), `feedback.profile_versions`, and dropping the `audio_targets` block when not used | Medium — code paths that *read* these fields would have to be audited; some may be downstream | Medium effort, medium value. |
| `deny_set_json` | 500–4000 (scales with history) | **30–50% smaller** by switching from pretty-printed `json.dumps(indent=2)` to compact `json.dumps(separators=(",", ":"))` and capping per-artist `forbidden_tracks` to the most recent N | Low — JSON whitespace is pure overhead, and the artist-level `exhausted_artists` bucket already covers the case where a per-artist track list grows unbounded | **Cheap quick win.** ~200–1500 tok depending on history. |
| `accepted_tracks` listing (`"- artist - track\n"`) | 0 on first batch, ~30 × N tracks on later batches | **Same content, drop the dash bullet + per-line repeat of "I already accepted these"** | Low | Trivial. ~10–20% of that block. |
| Diversity-hints sentence (history > 50) | ~30 | not worth trimming | — | Skip. |
| `recent_feedback` block | 200–800 | **strip "(reason: …)" past the first 3 entries** — reasons rarely change the model's behaviour past the first few examples | Low | Trivial. |
| User-message template scaffolding (`prompt_template.txt`) | 200–400 | **100–150** by removing the JSON-schema example block (the `response_format={"type":"json_object"}` API-level contract makes the prose example largely redundant) | Medium — some models lean on the in-prompt schema example; verify with a 50-track A/B before removing | Medium effort, medium value. |
| **Estimated total ceiling** | 4500–9000 input tok per typical batch | **~2200–4500** (≈ **45–55 % reduction**) | | |

### Concrete trim plan (in priority order)

1. **Compact JSON serialisation everywhere** (`json.dumps(..., separators=(",", ":"))` instead of `indent=2`) — touches `_build_deny_set_json` and the `profile_json` interpolation. Zero risk, immediate ~15–25 % shrink on those two sub-blocks. Estimated saving: **300–1500 tokens** depending on history size.
2. **Slim RAG pool entry format** — change `format_candidate_pool_block` from numbered+tagged to plain comma-separated `"name (tag1, tag2)"`, drop the index prefix. Estimated saving: **~600 tokens / batch** at 100-slot pool.
3. **Compress the system prompt** — collapse the seven numbered rules into a tight single block, drop the model-name-keyed `_VALIDATION_BLOCKS` duplication (the structured `gpt-5-4` block restates rules 1–7), drop the longer "REASONING:" preamble for `gpt-4-1`. Keep one validation block per model family but cut prose by ~50 %. Estimated saving: **~700–1200 tokens / batch**.
4. **Truncate `recent_feedback` reasons** to first 3 entries; cap whole block at 300 chars (today: 2000). Estimated saving: **100–500 tokens** when feedback is large.
5. **Strip `analysis.*` from `profile_for_gpt`** when the suggestions endpoint is the caller (it's only used by the dedicated analysis prompt). Estimated saving: **300–800 tokens** on profiles that have run analysis.
6. **Drop the JSON-schema example from `prompt_template.txt`** — only after a 100-track A/B confirms quality is unchanged. Estimated saving: **~150 tokens**.

### Trade-offs

- **Pro**: combined with Option A's smaller batch, total prompt+output for a RAG-enabled call drops from today's 6–9 k tokens to a projected **3.5–5 k tokens**, comfortably inside any 8 k local-LLM context with room for the JSON output.
- **Pro**: every trim above is **cumulative with Option A**, not redundant.
- **Con**: each trim is a small quality risk that needs verification against the existing eval log (`spotyvibe_with_rag/eval.jsonl`). The system prompt cut (#3) is the highest-risk one — model-family validation prose has historically improved hallucination resistance on `gpt-5.4`.
- **Con**: more conditional code paths (compact-vs-pretty JSON, slim-vs-tagged pool) add maintenance surface. Mitigate by making trims unconditional, not behind a feature flag.
- **Con**: harder to debug `prompt.log` when JSON is one-line — keep a debug-only pretty-print path.

### Recommended sequencing if Option C is taken up

1. Land #1 (compact JSON) and #2 (slim pool format) together — trivial, big win, low risk. **Do alongside re-running the eval A/B** to capture before/after `in_candidate_pool` and Spotify-found-rate metrics.
2. Land #4 + #5 in the next pass — cosmetic edits, cheap to revert.
3. Defer #3 + #6 until #1, #2, #4, #5 land and the eval log shows headroom for further compression.

### When to actually do this

Option A alone (per-call batch shrunk to 5) buys enough headroom for **most 8 k-context local LLMs today**. Option C only becomes urgent if:
- A user reports prompt-truncation symptoms even at `BATCH_SIZE_WITH_RAG = 5`, **or**
- We add features that further inflate the prompt (audio-feature targets, multi-language pool entries), **or**
- We genuinely want to support **4 k-context** local models as a first-class path.

---

## ☁️ Cloud Run incorporation — recommendation (2026-04-22)

Source: `analysis.md` (in repo root, generated 2026-04-21).
**Implementation guide written 2026-04-22** → see [`documentation/guides/cloud-run-rag-setup.md`](documentation/guides/cloud-run-rag-setup.md). That doc covers project + bucket + service-account creation, the Cloud Run Job that wraps `refresh_rag_corpus.py`, the weekly Cloud Scheduler trigger, the public-read bucket layout, the env-var cutover (`RAG_MANIFEST_URL`), the dual-publish migration plan, and the cost ceiling (~$0/mo, structurally bounded by the 60-min task timeout).

**TL;DR — yes, but only for one specific service first.** Cloud Run is the right platform for a **remote RAG retrieval endpoint** (Scenario C.2 in `analysis.md`); it is *not* recommended as a host for the LLM (Scenario B) and is *not* the right next step for a multi-tenant hosted Flask backend (Scenario A) until there is concrete user demand.

### Recommended next step: Scenario C.2 — RAG as a Cloud Run service

| Aspect | Detail |
|---|---|
| **Surface** | One POST endpoint `POST /api/rag/score_artists` mirroring the existing `core/src/rag/retrieval.py::score_artists` signature. |
| **Container** | Lift `core/src/rag/` as-is, wrap in a tiny Flask/FastAPI shim. No GPU, no ML dependencies — pure TF-IDF over an in-memory corpus. |
| **Corpus storage** | Read `artists.jsonl.gz` from a GCS bucket on container start (replaces the GitHub Releases asset for the cloud path; keep GH for desktop). |
| **Cost at current scale** | **$0/mo** — well inside the always-free tier (180 k vCPU-sec/mo; this workload uses ~2 k). Stays free until ~100× current volume. |
| **Client-side change** | Introduce a `RagBackend` abstraction in `core/src/suggestions.py` with two implementations: `LocalRag` (today) and `RemoteRag` (HTTP). Desktop EXE/wheel stays fully offline-capable; only the future hosted/mobile variant uses `RemoteRag`. |

### Why this fits SpotyVibe specifically

1. **Removes the corpus-on-device problem** — no more 7 MB download, no more "Download offline corpus" modal, no more version-skew between client and corpus. Fixes the original Android blocker (`a21c87b`).
2. **Token-budget orthogonal** — the RAG prompt-injection cost (Option A above) is unaffected; only *where the scoring runs* changes. The remote endpoint returns the same shape of pool the local code does.
3. **Cheap to undo** — if the latency or operational overhead is bad, the `LocalRag` implementation stays in the codebase as the default and the abstraction is the only carrying cost.

### Explicit non-recommendations

- **Scenario A (hosted multi-tenant Flask backend) — defer.** Requires breaking the single-user-filesystem assumption (`config.py`, `.credentials`, `personalized_music_profile.json`) and answering the "who pays for OpenAI tokens" question. Big rewrite for marginal benefit until there is user demand for a hosted variant.
- **Scenario B (self-hosted LLM on Cloud Run GPU) — reject.** Costs are comparable to OpenAI at current volume (~$6/mo) but recommendation quality drops noticeably with 4-bit Gemma/Llama versus GPT-4-class. Cold starts (15–30 s) make the sporadic-use UX bad. Already documented as a rejected alternative in `documentation/TechnicalManual.md` § RAG.
- **Scenario D (Android revival) — defer.** Cloud Run + remote RAG removes the *technical* blocker (`a21c87b`), but the Kotlin client + JSON-API extraction is still weeks of work. Only revisit if Scenario A also lands.

### Suggested order if pursued

`C.2 (remote RAG)` → `C.1 (Spotify artist cache as GCP-hosted shared cache)` → `A (multi-tenant backend)` → `D (Android client)`. Each step is independently useful and de-risks the next.

### What to *not* do

- Don't deploy a min-instance GPU service "just in case" — that's ~$484/mo burning while idle.
- Don't rewrite the Flask backend to be multi-tenant before there is demand for a hosted variant.
- Don't put the LLM behind a 5-minute default timeout without streaming.

---

## ✅ 15. Eval-log telemetry for Option A / Option C quality tracking (2026-04-22)

**Goal**: instrument the suggestion pipeline so the impact of the recent prompt-shrinking changes (Option A batch shrink, Option C trims #1/#2/#4/#5) on output quality can be measured offline instead of guessed at.

**What we ship**:

1. **New module-level capture in `core/src/suggestions.py`**:
   - `_LAST_PROMPT_COMPONENTS: dict[str, int]` — populated at the end of `build_messages()` with per-component char counts (`system`, `user_total`, `profile`, `deny_set`, `pool`, `accepted`, `feedback`, `audio_filters`, `diversity_hint`). Char counts (not tokens) so the capture is deterministic and tokeniser-free. Exposed via `get_last_prompt_components()`.
   - `call_gpt()` now attaches OpenAI's `usage` block (`prompt_tokens` / `completion_tokens` / `total_tokens`) to the result dict under `_usage`. Local LLM providers that omit `usage` produce `_usage: None` (key always present so callers can `result.pop("_usage", None)` safely).

2. **New writer `log_batch_summary()` in `core/src/eval_log.py`** — one `kind: "batch_summary"` JSONL row per LLM call carrying:
   - **What was sent**: `prompt_components` dict
   - **What it cost**: `usage` dict (when provider returns it)
   - **What came back**: `gpt_returned_count → after_filter_count → spotify_found_count → in_pool_count` funnel + `consecutive_empty_batches`
   - **Under which configuration**: `config_signature` + `effective_batch_size` + `rag_pool_size` + `rag_stratified`

3. **New helper `compute_config_signature()`** — short SHA1 hash over `{rag_enabled, rag_pool_size, rag_stratified, effective_batch_size, extra}` so per-track and per-batch rows can be **bucketed by configuration** without diffing run timestamps. The `extra` dict carries trim flags (`compact_json`, `slim_pool_format`, `feedback_trim_v2`, `strip_dup_profile_fields`) so a future change can be A/B-bucketed by simply flipping a flag.

4. **Per-track rows extended** with `kind: "track"`, `effective_batch_size`, and `config_signature` so they join cleanly to the per-batch summary rows on `(run_id, batch_num, config_signature)`.

5. **Wiring in `app.py::run_pipeline`** — pops `_usage`, computes funnel counts before/after `filter_duplicate_suggestions` + Spotify verification, writes one `track` row per suggestion plus one `batch_summary` row per LLM call. All wrapped in the existing telemetry try/except so a logging failure can never break a generation run.

6. **Same gating as before** — both writers are no-ops unless `DEBUG_MODE=true`. Production users pay nothing.

7. **Tests** (14 new, all green):
   - `core/tests/test_eval_log.py` — `kind: "track"` marker, optional kwargs default to `None`, `compute_config_signature` stability + change detection (3 tests), `log_batch_summary` no-op-when-debug-off + full-row write + missing-usage handling + coexistence with track rows (4 tests).
   - `core/tests/test_suggestions.py::TestPromptTelemetryCapture` — `get_last_prompt_components` populated + records accepted-listing size, `call_gpt._usage` attached + `None` when provider omits it (4 tests).

8. **Documentation** — `documentation/TechnicalManual.md` § "Eval-log telemetry" with the schema breakdown, a pandas analysis snippet, and the "config_signature is how you bucket A/B runs" workflow.

**How to use it for the impending re-A/B**:
- Run the same profile twice, once with the current config (`config_signature = X`), once with a tweaked one (`config_signature = Y`).
- `groupby("config_signature")["found_on_spotify"].mean()` → Spotify-found-rate delta (the headline hallucination metric).
- `groupby("config_signature")[["gpt_returned_count","after_filter_count","spotify_found_count","in_pool_count"]].mean()` → funnel-pass-through rates.
- `prompt_components` series tells you which trim moved which sub-block — useful for proving that e.g. the slim pool format actually shrank the `pool` component.

---

## ⚠ Re-opened bugs

- **[ ] When a song finishes, the player does not automatically move on to the next song.** Originally tracked as item 5 (auto-advance) and "fixed" twice (items 5 and 11). Re-opened on the user's report 2026-04-22 — the fix in item 11 was apparently incomplete or regressed. Need to:
  1. Reproduce against the current build (Web Playback SDK path, not the iframe fallback).
  2. Add explicit logging around `_sdkLastPositionMs`, `_sdkPaused`, `_sdkCurrentTrackId`, and the ticker's projection to confirm which signal is being lost this time.
  3. Consider a third belt-and-braces detection — a wall-clock timeout that fires `nextPreview()` after `duration + 2000ms` if neither the ticker nor the SDK state-change handler has advanced.
- **[ ] Wrap song title if it is too long in preview player.** Already fixed in item 13 — but the user reports the player still gets stretched in some cases. Re-verify and tighten the CSS clamp / overflow handling.
- **[ ] Analyse results between RAG and not-RAG** — see `documentation/spotyvibe_with_rag/` and `documentation/spotyvibe_without_rag/` eval logs. Re-run the A/B with the new stratified retrieval + 100-slot pool + Option A batch shrink, confirm the `in_candidate_pool` ratio target (≥ 40 %) from the Apr-21 decision report.

- **[ ] RAG enrichment Phase 3 — Spotify related-artists graph as re-ranking signal.** After Phase 2 (Spotify popularity + genres) is in production, leverage Spotify's `/v1/artists/{id}/related-artists` endpoint to build an artist-similarity graph. Use it as a soft re-ranking signal in `score_artists`: if the top candidates are densely connected in the Spotify graph, they are more likely to fit the user's taste cluster. Considerations:
  - Rate-limited endpoint — pre-compute the graph during the Cloud Run build and store as adjacency lists (~5-10 MB additional gzipped).
  - Graph weight should be tunable and small (e.g., +10-15 % score boost) so it never overrides explicit must_have / avoid constraints.
  - Optional: use the graph to detect and surface "bridge" artists between the user's listed must_have artists.
  - Depends on Phase 2 being live and stable.
