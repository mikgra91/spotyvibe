# Evaluation Workflow Issue — Compact State

## Core finding
Evaluation does **not** test the production failure path.

Production failure:
- User dislikes tracks/bands.
- Profile is updated.
- Next recommendation still includes disliked bands/tracks.
- Indicates possible failure in memory, filtering, retrieval, profile update, or prompt injection.

Current eval workflow:
1. Create fresh sandbox profile.
2. Train profile from canonical seed.
3. Generate one playlist.
4. Apply deterministic likes/dislikes.
5. Re-run `train_profile`.
6. Delete playlist/profile.
7. **No second playlist generation after feedback/profile update.**

Result:
- Eval can pass while memory/filtering is broken.
- Eval never proves disliked artists/tracks are suppressed after update.

## Major mismatch
Implementation state says:
- P3.1 changed `train_profile()` to send only mutable sections.
- History/feedback are never sent to GPT.
- Liked/disliked reasons accumulate but do **not yet update profile**.
- Feedback absorption is deferred/open work.

Eval scenario comment says:
- second `train_profile()` “absorbs feedback into profile.”

Likely reality:
- Eval exercises refine-train call.
- Eval does not verify feedback changed profile/retrieval/filtering behavior.
- Production bug is consistent with feedback not affecting future recommendations.

## Eval metric gap
Current eval mainly measures:
- Spotify-found rate.
- Must-have cite rate.
- Out-of-pool/HC2.
- Stage 1 on-genre.
- Cost/latency.
- Completion count.

These do **not** measure:
- Real taste match.
- Dislike leakage.
- Avoid leakage.
- Memory effectiveness.
- Post-feedback recommendation behavior.
- User-specific accumulated profile behavior.

Known context:
- Dislike rate still not re-measured.
- Manual real-user dislike-rate measurement is still blocking.
- Eval success does not predict production quality.

## Deterministic feedback issue
Current eval feedback:
- Likes fixed indices: `(0, 3, 6, 9, 12)`.
- Dislikes fixed indices: `(2, 7, 11)`.
- Reasons are fixed strings.
- Feedback does not depend on actual track quality.

Impact:
- A good track at disliked index is always disliked.
- A bad track at liked index is always liked.
- Useful for API exercise only.
- Not valid as quality/taste signal.

## Under-fill issue
Harness reclassifies some zero/short playlist failures as `under_filled`, treated as non-broken anti-hallucination behavior.

Risk:
- Production sees “only 5 songs returned” as failure.
- Eval may normalize short output unless completion gate is enforced.
- Completion must be a hard failure if below target threshold.

Required gate:
- Playlist completion ≥95% of requested size.
- For playlist size 15: require ≥15 or at least ≥14, depending policy.

## Fresh-profile issue
Each eval creates/deletes a fresh sandbox profile.

Misses production conditions:
- Large/old profile.
- Accumulated dislikes.
- Repeated profile updates.
- Real user profile drift.
- Stale memory.
- Persistent disliked artists/tracks.
- Long-term avoid learning.

Result:
- Clean-room eval can pass while real profile fails.

## Known eval blocker
Eval sandbox copies real `.spotify-cache`.

Current issue:
- Stale/invalid cache caused Spotify `invalid_client`.
- Produced zero-track evals.
- Eval is unreliable until reconnect/cache handling is fixed.

Needed:
- Clear stale cache before OAuth/reconnect.
- Ensure eval uses valid Spotify auth.
- Fail fast if Spotify auth invalid before running model eval.

## Required evaluation update
Add post-feedback memory regression pass:

1. Generate playlist A.
2. Apply dislikes to selected tracks/artists.
3. Run profile update/refine.
4. Generate playlist B using same profile/target.
5. Compare A/B and fail on leakage.

Hard fail conditions:
- Disliked `(artist, track)` reappears in playlist B.
- Disliked artist/band reappears if artist-level dislike exists.
- Avoid traits from dislike reason not represented in profile/filter state.
- Stage 1 retrieves disliked artists without explicit allowed reason.
- Stage 2 approves disliked/avoid-overlap artists.
- Stage 3 outputs disliked/avoid-overlap artists.
- Final playlist under-fills below completion gate.
- Playlist B taste/dislike score does not improve vs A.

## Required tracing/logging
For each eval run, snapshot:

- Profile before seed train.
- Profile after seed train.
- Playlist A:
  - Stage 1 candidates.
  - Stage 1 scores/tags/reject reasons.
  - Stage 2 input/output.
  - Stage 3 prompt/raw output/normalized output.
  - Spotify verification results.
  - Final accepted/dropped tracks.
- Feedback store after likes/dislikes.
- Profile after refine train.
- Playlist B same full trace.
- Diff:
  - Profile before/after feedback.
  - Disliked store before/after.
  - Candidate leakage.
  - Approval leakage.
  - Final playlist leakage.

## Main learned facts
- Current eval validates mechanical output, not user satisfaction.
- Spotify-found + cite rate can look good while taste match is bad.
- One-shot clean profile eval cannot detect memory/filtering failures.
- Fixed-index feedback is not a quality metric.
- Feedback/profile update path appears unverified and possibly not implemented end-to-end.
- Under-fill must be treated as product failure when completion target is missed.
- Production-like stateful eval is required before trusting model/cost decisions.

## Priority fixes
1. Add second playlist generation after feedback/refine.
2. Add leakage gates for disliked tracks/artists.
3. Add hard completion gate.
4. Add real/profile-state eval using copied anonymized production debug profile.
5. Add full stage tracing for retrieval → ranking → profile → prompt → filtering → Spotify verify.
6. Fix Spotify auth/cache invalidation before re-running eval.
7. Stop using eval results for model/cost decisions until post-feedback quality gates exist.