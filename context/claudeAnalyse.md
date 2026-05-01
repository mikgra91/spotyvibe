# Claude Analysis — Production Recommendation Quality Failure

Independent analysis. Cross-checked against `context/gpt5Analysis.md`. Reads from:
- [context/context_implementation-state.md](context_implementation-state.md)
- [context/context_todo.md](context_todo.md)
- [context/context_potential-issues.md](context_potential-issues.md)
- [context/gpt5Analysis.md](gpt5Analysis.md)

Evidence sources:
- `C:\Users\micha\AppData\Local\spotyvibe\debug\eval.jsonl`
- `C:\Users\micha\AppData\Local\spotyvibe\debug\6635a2fb-9b72-4d2b-925b-65af46a1904e\profile.json`
- `C:\Users\micha\AppData\Local\spotyvibe\debug\debug.log`

---

## Test profile under analysis

`japanese_Theatrical_music`:
- must_have: Uplifting music; harmonized vocals; no screaming; **Music must be Japanese**.
- avoid: Electronic music; excessive synths; **80s production style**; **American artists**; songs not uplifting.
- 49 disliked_tracks, 5 rejected_artists, **0 disliked_artists**.
- Production output included Boston, Ships Have Sailed, Danny Elfman, David Crosby (American), DREAMS COME TRUE / Dreamcatcher (80s/electronic), Yoko Kanno (instrumental, no singing).

---

## Failure chain (top → bottom)

```
Stage 1 retrieval
  ├─ no hard must-have gate                  → American rock outscores Japanese
  ├─ stopword strips "80s", "production"     → "80s production style" → 0 avoid tags
  ├─ negation blind                          → "Songs that are not uplifting"
  │                                            blacklists "uplifting"
  └─ "American artists" → corpus tag rare    → most US artists pass
       │
       ▼
Stage 2 LLM (semantic avoid check)
  └─ L1 skip fires when pool_avoid_overlap=0 → fires precisely when needed
       │                                       (per Stage 1 tokenizer flaws)
       ▼
Stage 3 LLM
  ├─ given approved pool                     → treats as authoritative
  ├─ taste_summary "Avoid: ..." too soft     → loses to approved-list signal
  └─ diversity hint contradicts profile      → "Focus on 1970s-1980s artists"
       │                                       on a "avoid 80s" profile
       ▼
Post-filter
  ├─ track-dislike never escalates           → no auto-promote to artist-reject
  └─ train_profile ignores feedback          → reasons ("80s", "not Japanese")
                                                never enter avoid list
       │
       ▼
Eval harness
  ├─ fresh sandbox profile each run          → can't see memory regressions
  ├─ no playlist-B after feedback            → leakage invisible
  └─ has_must_have_cite = text match         → false 90% pass while
                                                production fails 99%
```

---

## Findings, ordered by impact

### F1. Stage 1 has no hard must-have gate
**File:** [core/src/rag/retrieval.py:115-171](../core/src/rag/retrieval.py#L115)
**Function:** `build_query_tags`

`must_have` items tokenized, weighted 2.0, summed into TF-IDF score. No mechanism to require an artist match a specific tag. American rock artist hitting `uplifting`+`rock`+`harmonized`+`vocals` outscores Japanese-tagged artist with weaker tag overlap.

`"Music must be Japanese"` → tokens `music`, `japanese`. `music` not in stop list → noise weight against any artist tagged `music` literally.

**Fix direction:** add structured `must_have_tags: [japanese]` field to profile schema. Pre-filter pool — drop any artist not matching ALL hard tags before scoring. Train `train_profile` to extract hard tags from prose during profile creation.

---

### F2. Avoid tokenizer broken on negation, era terms, and rare tags
**File:** [core/src/rag/retrieval.py:53-81](../core/src/rag/retrieval.py#L53), [retrieval.py:504-542](../core/src/rag/retrieval.py#L504)
**Function:** `_STOP_TOKENS`, `_build_avoid_tags`

Per-avoid-string tokenization:
| Avoid prose | Tokens after stop-word strip | Effective filter |
|---|---|---|
| `"80s production style"` | `style` only (`80s`, `production` stop) | inert |
| `"American artists"` | `american`, `artists` (not corpus tag) | mostly inert |
| `"Songs that are not uplifting"` | `songs`, `uplifting` | **blacklists `uplifting`** — collides with must_have |
| `"Excessive use of synthesizers"` | `synthesizers` | depends on corpus alias for `synth`/`electronic` |
| `"Electronic music"` | `electronic`, `music` | works for `electronic` |

Result: avoid_tags set near-empty → pool_avoid_overlap=0 → triggers F3.

**Fix direction:**
1. Remove `80s`/`90s`/`production` from stop list when source is avoid block.
2. Add explicit corpus aliases: `80s → 1980s`, `synthesizers → synth + electronic`.
3. Add structured `avoid_tags` field parallel to `must_have_tags`, populated by `train_profile`.
4. Negation handling: skip tokens that follow `not`/`no` from going positive into either query OR avoid (current code can put `uplifting` into both).

---

### F3. Stage 2 LLM skip is unsafe
**File:** [core/src/suggestions.py:993-997](../core/src/suggestions.py#L993)
**Function:** `check_avoid_compliance`, lever L1
**Evidence:** `eval.jsonl` rows `kind=stage2_summary`, `status=skipped_no_overlap`, `candidates_in==approved_out`, `avoid_traits_count=4-5`.

L1 skip:
```python
if pool_avoid_overlap == 0:
    return list(artist_names), {..., "status": "skipped_no_overlap", ...}
```

Per F2, `pool_avoid_overlap` is trivially 0 for semantic avoid traits (`American artists`, `80s production`, `not uplifting`). Skip fires precisely when the LLM semantic check is the only remaining gate.

**Fix direction (P0, smallest patch):**
```python
if pool_avoid_overlap == 0 and _avoid_is_tag_complete(avoid_traits):
    # only skip if every avoid trait is known machine-verifiable
    return list(artist_names), {...}
```
Or simplest: drop the skip when `avoid_traits` is non-empty and any trait fails a "tag-detectable" allowlist (e.g. `electronic`, `country`, `metal`). Save L1 only for trivial cases.

GPT-5.5 finding #2. Confirmed.

---

### F4. No auto-escalation from track-dislike to artist-reject
**File:** [core/src/feedback.py:65-127](../core/src/feedback.py#L65)
**Function:** `dislike_track`

Two-tier rule by design: track-dislike only stores `(artist, track)`; artist-rejection requires explicit user action.

Observed in profile.json:
- 49 disliked_tracks across ~15 distinct artists.
- 9 disliked DREAMS COME TRUE tracks, 4 Dreamcatcher, 4 Crystal Kay, 3 Yoko Kanno, 3 DIR EN GREY, 3 D.
- Only 5 in `artists.rejected` (all manual `[EXCLUDED] Artist: …` clicks).
- `feedback.disliked_artists: []`.

After 3+ tracks disliked from same artist with reasons like `"Blantantly disregarding profile again!"`, that artist still eligible for future suggestion (until `history.suggested_artists` excludes them — single-playlist lag).

**Fix direction:** in `dislike_track`, after appending track-dislike, count case-insensitive (artist, *) entries; if ≥ N (suggest 3), append to `artists.rejected` with concatenated reasons. ~10 LOC.

---

### F5. `train_profile` never consumes feedback
**File:** [core/src/profile.py:595-744](../core/src/profile.py#L595)
**Function:** `train_profile`
**Evidence:** every `kind=profile_update_summary` row in `eval.jsonl` shows `profile_hash_before == profile_hash_after`.

`train_profile` reads only `sections` from the UI form (vibe_description / core_description / must_have / soft_preferences / avoid). `feedback.disliked_tracks` and their `reason` strings never enter the prompt.

User dislike reasons rich with avoid signal (`"80s"`, `"not Japanese"`, `"no singing"`, `"R and B, not ROCK"`) — none reach the avoid list automatically.

This is the deferred OPEN-6 / P3.3 from `context_implementation-state.md` lines 254-256. UX implies it works; it doesn't.

**Fix direction:** when `train_profile` runs, also include a synthesised `## RECENT DISLIKES (with reasons)` section in the user message, sourced from `profile.feedback.disliked_tracks[-N:]`. Let GPT roll recurring reasons into avoid/must_have. Acceptance: 20 disliked reasons → ≥2 recurring avoid entries (matches OPEN-6 acceptance).

Alternative deterministic path: code-side reason aggregation — count tokens in `reason` strings; promote tokens above threshold to `avoid_tags`. No LLM call.

---

### F6. Stage 3 prompt uses taste_summary, not full profile, but that's not the bug
**File:** [core/src/suggestions.py:882-939](../core/src/suggestions.py#L882) (`build_taste_summary`), [suggestions.py:1081-1260](../core/src/suggestions.py#L1081) (`select_tracks`)
**Evidence:** `eval.jsonl` `prompt_components.profile=0, deny_set=0`.

By design — replaced by `build_taste_summary` (≤800 chars). Avoid block IS in user message:
> `Avoid: Electronic music, Excessive use of synthesizers, 80s production style, American artists, Songs that are not uplifting.`

Failure mode: once Stage 1+2 hand Stage 3 a pre-approved artist list, model treats list as authoritative. Soft "Avoid: …" string in the same prompt loses against the explicit approved list. Standard LLM gating behavior.

**Implication:** fixing F1+F2+F3 (pool quality) eliminates this. No change to Stage 3 prompt needed.

---

### F7. Hardcoded diversity hint contradicts profile
**File:** [core/src/suggestions.py:1233-1241](../core/src/suggestions.py#L1233)

```python
diversity_hints = [
    "Focus on artists from the 1970s-1980s that match the profile.",
    "Explore Japanese, Korean, or Scandinavian artists matching the profile.",
    ...
]
hint = diversity_hints[batch_num % len(diversity_hints)]
```

Cycle includes 1970s-1980s focus. User profile actively avoids 80s. No profile-aware filter.

GPT-5.5 finding #5. Confirmed.

**Fix direction:** before applying hint, scan against `profile.preferences.avoid` (substring/keyword). Skip hint if conflict. Or remove static hints and derive from profile.

---

### F8. Eval harness cannot reproduce the failure
**File:** evaluation/* (per `context_potential-issues.md`)

Three structural gaps:
1. **No playlist-B post-feedback.** Eval generates one playlist on fresh sandbox, applies fixed-index dislikes, refines profile, exits. Memory leakage never tested.
2. **`has_must_have_cite` is a text match on rationale, not a fit check.** Boston rationale `"uplifting"` → cite=true. Track is American → profile violation. Eval scores false-pass.
3. **Fresh sandbox profile per run.** Real production profile is large/stale/feedback-laden. Clean-room success != production success.

**Fix direction (matches `context_potential-issues.md` priority list):**
1. Add playlist-B-after-feedback step. Hard-fail on:
   - rejected/disliked artist appears.
   - exact disliked `(artist, track)` reappears.
   - artist with ≥3 prior track-dislikes reappears.
2. Replace text-cite with deterministic metadata check where possible:
   - `Japanese-only` → Spotify market check + Japanese-script artist name detection.
   - `not 80s` → Spotify album release year decade check.
   - `American artists avoid` → Spotify artist country if exposed (else punt to LLM judge).
3. Add stateful eval: copy anonymized real-user debug profile as input.

---

### F9. Observability gap blocks every diagnosis
Matches GPT-5.5 finding #7. Per-run trace bundle missing.

Currently logged: `stage1_summary` (count only), `stage2_summary` (count + status), `batch_summary` (counts + token totals). No way to answer:
- *Which* artists were in Stage 1 pool?
- *Which* tags drove their score?
- *Which* avoid tags were considered?
- *Why* did Stage 2 approve artist X?
- *What* did Stage 3 see in the prompt?

**Fix direction:** add `--debug-trace` mode writing per-run JSON bundle with: profile snapshot, query tags + weights, full candidate list with score components, avoid tag set, Stage 2 prompt+response, Stage 3 prompt+response, post-filter decisions per track, Spotify search query+result per track. Path: `%LOCALAPPDATA%/spotyvibe/debug/<run_id>/trace.json`.

---

## Disagreements with GPT-5.5 analysis

| Topic | GPT-5.5 | Claude |
|---|---|---|
| Pool quality root cause | "RAG/Stage 1 returns invalid pools" — generic | Specifically: tokenizer + no hard gate (F1+F2). Mechanism named. |
| `uplifting` collision | not noted | F2: "Songs that are not uplifting" puts `uplifting` in BOTH must and avoid. Negation blind. |
| `80s` stop word | not noted | F2: `80s` is in `_STOP_TOKENS`, so 80s avoid filter is silently dead. |
| `train_profile` "no effective change" | called it a bug | F5: it's a missing feature (feedback never plumbed). UX implies it works. |
| Recommended fallback | "Disable RAG/staged path by default" | Premature. F3+F2 fixes are <30 LOC and recover most quality without losing cost wins. |
| Action priority | broad list | F3 is single highest-leverage 5-LOC change. |

---

## Recommended P0 implementation order

Sized for a single PR each. Sequence chosen so each step is independently verifiable.

1. **F3 fix — Stage 2 skip safety.** [suggestions.py:993](../core/src/suggestions.py#L993). 5-10 LOC. Guard `skipped_no_overlap` behind "all avoid traits are tag-detectable". Add unit test pinning behavior on a profile with `American artists` avoid trait.

2. **F7 fix — strip 80s hint.** [suggestions.py:1233](../core/src/suggestions.py#L1233). 1-line removal or profile-aware filter. Trivial.

3. **F4 fix — auto-escalate dislikes.** [feedback.py:65](../core/src/feedback.py#L65). ~15 LOC + test. Threshold N=3.

4. **F2 fix — avoid tokenizer.** [retrieval.py:53,504](../core/src/rag/retrieval.py#L53). Remove era stops from avoid path; add aliases; add `not <token>` negation skip in `_extract_text_tokens` when called from avoid context.

5. **F1 fix — hard must-have gate.** [retrieval.py:556](../core/src/rag/retrieval.py#L556). Add `must_have_tags` profile field + pre-filter step in `retrieve_candidates`. Schema migration: derive `must_have_tags` from existing prose during one-shot upgrade. Train_profile system prompt updated to populate.

6. **F5 fix — feedback into train_profile.** [profile.py:595](../core/src/profile.py#L595). Add `## RECENT DISLIKES` section to user message. Cap at N=20 most-recent.

7. **F9 — trace bundle.** App-wide. New module `core/src/trace.py`. Wire all stages.

8. **F8 — eval harness post-feedback regression.** evaluation/*. Add playlist-B step + leakage gates. New deterministic metadata check for `Japanese-only`. Replace cite-rate as primary metric with leakage rate.

Steps 1-3 ship within hours. Steps 4-6 are larger but each independently testable. Step 7 unblocks all future debugging. Step 8 prevents regression of these fixes.

---

## What NOT to do

- **Do not disable the staged pipeline.** F1+F2+F3 are the actual bugs; reverting to legacy mega-prompt loses cost wins from `context_implementation-state.md` Phase 6.0 without solving root causes.
- **Do not re-enable Stage 3 `json_schema`** (per `context_implementation-state.md` lines 270-274 reverted-list).
- **Do not chase eval cost optimization** until F8 lands. Per `context_todo.md` line 243: "Cost work is blocked until functional validation works."
- **Do not trust `has_must_have_cite` for quality decisions** until F8.

---

## Open questions for the user

1. F4 escalation threshold: 3 tracks? 2? Should rejection be auto-confirmed or surface as a UI prompt ("You disliked 3 tracks by X — block this artist?")?
2. F5 deterministic vs LLM path: prefer code-side reason-token aggregation (free, predictable) or LLM merge into avoid (richer)?
3. F1 schema migration: silently derive `must_have_tags` from existing prose at first load, or require user to re-train profile?
