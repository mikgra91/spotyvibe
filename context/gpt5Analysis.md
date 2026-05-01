# GPT-5 Analysis — Production Quality Failure

Inputs: `TODO.md`, `context/context_todo.md`, `C:\Users\micha\AppData\Local\spotyvibe\debug`.

## State

- Recommendation quality is P0 broken.
- Pause cost/speed work until quality, memory, filtering, and tracing are fixed.
- Failures are structural: retrieval, avoid filtering, profile learning, post-generation filtering.

## Findings

### 1. RAG / Stage 1 returns invalid candidate pools

Profile constraints:

- Japanese artists only.
- Energetic/theatrical/uplifting Japanese rock/pop.
- Harmonized layered vocals.
- No screaming.
- Avoid: electronic, excessive synths, 80s production, American artists, non-uplifting songs.

Production candidates/recommendations included:

- Boston, Ships Have Sailed, Prof, Danny Elfman.
- ZARD, Orange Range, B’z, Morning Musume, Crystal Kay, DREAMS COME TRUE.
- Dreamcatcher, D, DIR EN GREY, Yoko Kanno / Tank!.

Implication: profile mismatch starts at retrieval/candidate-pool stage, before Stage 3.

### 2. Stage 2 avoid filter skip is unsafe

Observed in `eval.jsonl`:

```text
status = skipped_no_overlap
approved_out = candidates_in
```

Examples:

- `50 -> 50`
- `45 -> 45`

Cause: L1 skip uses `pool_avoid_overlap == 0` from corpus tag overlap. This does not prove semantic avoid compliance.

Avoid traits not safely tag-verifiable:

- American artists.
- 80s production style.
- Songs that are not uplifting.
- Excessive synthesizers.

Effect: Stage 2 passes whole pool without semantic check. Treat as P0 regression suspect. Disable skip when `avoid_traits` is non-empty unless all avoid traits are machine-verifiable.

### 3. Profile training often produces no effective change

Observed `profile_update_summary`:

```text
profile_hash_before == profile_hash_after
status = ok
```

Effect: training reports success but does not change profile.

Persisted rejected artists remain small despite many dislikes:

- B’z / b’z variant.
- Orange Range.
- Prof.
- Crystal Kay.

Many disliked artists stay only as exact track dislikes. They are not promoted to artist-level rejection or rule-level memory.

### 4. Exact-track dislikes are insufficient

Current filter blocks:

- rejected/disliked artists.
- exact disliked `(artist, track)` pairs.

Failure mode: if one track is disliked because the artist/category violates the profile, another track by same artist can still be recommended.

Dislike reasons requiring stronger memory:

- Not Japanese.
- 80s.
- R&B, not rock.
- No singing.
- Electronic.
- Does not comply with profile.

Needed: escalation from dislike reason to artist ban and/or avoid-rule update.

### 5. Stage 3 diversity hint can violate profile

Hardcoded hint can add:

> Focus on artists from the 1970s-1980s that match the profile.

This conflicts with active avoid rule:

> 80s production style.

Remove or make profile-aware.

### 6. Eval metrics miss real quality failures

`has_must_have_cite = true` only means the rationale text cites a must-have term. It does not verify actual track fit.

False-pass examples possible:

- Rationale says “uplifting” but track is not uplifting.
- Rationale says “Japanese market” but artist is K-pop/non-Japanese.
- Rationale says “no screaming” but track has no singing or wrong genre.
- Disliked/rejected artist passes if exact filter misses it.

Current eval can pass while production quality fails.

### 7. Observability gaps

Missing or insufficient trace data:

- Stage 1 query tags/weights.
- Stage 1 per-candidate scores and score components.
- Candidate tags, genres, popularity, top tracks.
- Avoid tags extracted from profile.
- Candidate avoid-overlap details.
- Stage 2 prompt/response and reject reasons.
- Stage 3 prompt/response/reasoning linked to final tracks.
- Post-filter reason codes.
- Feedback entries included in generation/training.
- Profile training diff.
- Spotify search query, returned candidates, selected result.

Also observed: mojibake/encoding corruption for Japanese text in logs.

## Actions

### P0

1. Disable `skipped_no_overlap` when `avoid_traits` is non-empty.
2. Add per-run trace bundle:
   - profile snapshot/hash/id
   - active feedback/dislikes
   - Stage 1 query tags/weights
   - Stage 1 candidates with score components, tags, genres, popularity, top tracks
   - avoid tags and candidate overlaps
   - Stage 2 prompt/response/reject reasons
   - Stage 3 prompt/response/reasoning
   - post-filter decisions with reason codes
   - Spotify search queries/results/selected match
   - final playlist and rejected candidates
3. Fix memory semantics:
   - multiple disliked tracks by same artist => artist rejection candidate
   - reason contains `not Japanese`, `not rock`, `80s`, `electronic`, `no singing`, `does not comply` => artist/rule escalation candidate
   - profile training must emit diff or explicit `no_change`
4. Remove or gate 1970s/1980s diversity hint.
5. Add production-like eval checks:
   - Japanese-only
   - no rejected artists
   - no disliked artists
   - no disliked exact tracks
   - no obvious genre/region violations
   - playlist completion
   - semantic fit verifier or deterministic metadata checks

### Candidate product fallback

- Disable RAG/staged path by default until it passes production-like traces.
- If kept, require semantic gates and full traceability.

## Other bugs observed

- Playback stuck after removing currently playing track; removed track keeps playing and blocks other playback.
- Settings Save lacks busy/progress state; slow save encourages repeated clicks.
- Spotify reconnect/cache fragility remains relevant.
- Japanese log text encoding corruption reduces debuggability.
