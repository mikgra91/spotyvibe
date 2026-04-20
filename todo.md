# TODO List — Implementation Status

> Last updated: 2026-04-20
> Tests: ✅ 508 core + ✅ 233 frontend (0 failures)

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

## ⏭ 7. Custom "New Artist" % visual cue — SKIPPED (per request)

Plan kept for later:
- Compare slider value against active preset's `new_artist_pct`; toggle an `is-custom` class on the slider wrapper.
- CSS: dim slider when custom, emphasise a "CUSTOM" label underneath.
- New i18n key `settings.new_artist_pct_custom` (en/de/jp).

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

