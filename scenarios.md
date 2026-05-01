# Evaluation scenario brainstorm

## Current test behavior

- Unit tests do not call the real evaluation harness.
- `core/tests/test_evaluation_scenario.py` pins scenario structure:
  - required seed sections exist
  - feedback indices are deterministic and non-overlapping
  - indices fit a 30-track playlist
  - analysis target exists
  - scenario registry contains `default` and `regression_japanese_theatrical`
  - unknown scenario names fail loud
- `core/tests/test_evaluation_leakage.py` pins playlist-B leakage rules:
  - rejected artist reappears
  - exact disliked track reappears
  - artist with 3 distinct disliked tracks reappears
- Real evaluation flow:
  - create sandbox profile
  - train profile from scenario seed
  - run fixed Band/Song Analysis target
  - generate playlist A
  - push playlist A to Spotify
  - apply deterministic likes/dislikes by index
  - re-train profile from refine sections
  - generate playlist B on the same profile
  - audit playlist B for feedback leakage
  - cleanup playlists and profile
- Reported signals:
  - playlist-B leakage pass/fail
  - Spotify-found rate
  - must-have cite rate
  - Stage 2 approved/candidates
  - cost, latency, token usage
  - telemetry row counts
- Current scenario coverage:
  - `default`: broad modern theatrical pop-rock; mostly tag-detectable filters
  - `regression_japanese_theatrical`: Japanese-only + semantic avoid filters; known leakage failure

## Current blind spots

- Only two profiles.
- Mostly one musical neighborhood: theatrical pop-rock / J-pop / J-rock.
- Feedback is positional, not semantic.
- Avoid checks mostly rely on profile-leakage, not independent oracle checks.
- Hard constraints are not measured separately from soft preferences.
- No coverage for mood-only profiles.
- No coverage for era-only profiles.
- No coverage for low-resource / obscure genres.
- No coverage for conflicting constraints.
- No coverage for multilingual constraints beyond Japanese.
- No coverage for track-form filters: live, acoustic, remix, instrumental, cover, radio edit.
- No coverage for diversity constraints: repeated artists, same-scene clustering, over-mainstream picks.

## Scenario shape

Each scenario should define:

- `name`
- `purpose`
- `seed_sections`
- `analysis_artist`
- `analysis_track`
- `like_indices`
- `dislike_indices`
- `like_reason`
- `dislike_reason`
- `refine_sections`
- expected degradation signals
- optional oracle checks beyond leakage

Keep scenarios deterministic. Do not branch by model.

## Scenario matrix

| ID | Profile focus | Hard filter | Main degradation caught |
|---|---|---|---|
| S01 | Japanese theatrical uplift | Japanese-only, no 80s, no American artists | known semantic avoid leakage |
| S02 | German darkwave minimal | German-language vocals, no metal, no EDM drops | language drift, genre drift |
| S03 | Brazilian samba-funk party | Brazilian artists, Portuguese vocals, no reggaeton | country/language confusion |
| S04 | 90s boom bap hip-hop | 1990-1999 sound, no trap, no pop rap | era drift, modern-production leakage |
| S05 | Ambient instrumental focus | instrumental only, no vocals, no beats | vocal leakage, beat leakage |
| S06 | Acoustic folk intimacy | acoustic, no drums-heavy rock, no polished pop | production-style drift |
| S07 | Female-fronted punk energy | female vocals, punk/riot grrrl, no pop-punk gloss | vocal/scene constraint miss |
| S08 | Non-English metal boundary | non-English vocals, melodic metal, no screaming | nuanced filter handling |
| S09 | Jazz fusion technical | instrumental fusion, no smooth jazz, no vocal standards | subgenre precision |
| S10 | K-pop bright dance | Korean pop, upbeat, no Japanese/English western pop | market/language leakage |
| S11 | Nordic melancholic indie | Nordic artists, cold mood, no sunny pop | geography + mood drift |
| S12 | Club techno strict | techno, no house, no vocals, no EDM festival drops | adjacent-electronic confusion |
| S13 | Soul oldies but not rock | 60s/70s soul, no classic rock, no disco | era allowed but genre boundary |
| S14 | Modern hyperpop chaos | hyperpop, abrasive, no mainstream dance-pop | mainstream smoothing |
| S15 | Obscure local scene | low-mainstream artists, no global hits | popularity bias |
| S16 | Covers/remixes excluded | original studio recordings only | remix/live/cover leakage |
| S17 | Sad quiet study | low-energy, sparse, no anthemic choruses | mood/energy overcorrection |
| S18 | Workout aggression | high-energy, aggressive, no slow intros | energy mismatch |
| S19 | Contradictory profile | calm + aggressive conflict | graceful under-fill vs hallucination |
| S20 | Artist rejection stress | repeated dislikes from one artist | feedback escalation failure |

## High-priority scenarios

### S02 — German darkwave minimal

- Core: cold German darkwave / Neue Deutsche Todeskunst adjacent.
- Must-have: German-language vocals, minor-key, sparse synth/guitar atmosphere.
- Soft: gothic, post-punk, minimal wave.
- Avoid: metal growls, EDM drops, English-language alt-rock, upbeat synthpop.
- Analysis target: `Lebanon Hanover` — `Gallowdance`.
- Like reason: German darkwave atmosphere, restrained and cold.
- Dislike reason: too upbeat, too EDM, not German-language, or too metal.
- Catches:
  - English darkwave leakage
  - generic gothic rock leakage
  - industrial/metal overreach
  - synthpop optimism creep

### S03 — Brazilian samba-funk party

- Core: Brazilian party music with live percussion and groove.
- Must-have: Brazilian artist, Portuguese vocals, samba/funk/carnival energy.
- Soft: brass, call-and-response, danceable rhythm.
- Avoid: reggaeton, Latin trap, Spanish vocals, generic EDM remixes.
- Analysis target: `Jorge Ben Jor` — `Mas Que Nada`.
- Like reason: Brazilian Portuguese groove with organic percussion.
- Dislike reason: Spanish/reggaeton/EDM drift.
- Catches:
  - Latin-region overgeneralization
  - Spanish-vs-Portuguese miss
  - Spotify-search false positives

### S04 — 90s boom bap hip-hop

- Core: 1990s East Coast / golden-age boom bap.
- Must-have: boom-bap drums, rap vocals, 90s feel.
- Soft: samples, DJ scratches, gritty production.
- Avoid: trap hi-hats, autotune, pop rap, drill, glossy 2010s production.
- Analysis target: `Gang Starr` — `Mass Appeal`.
- Like reason: grounded 90s boom-bap sound.
- Dislike reason: modern trap/pop-rap drift.
- Catches:
  - era leakage
  - modern production leakage
  - genre adjacency collapse

### S05 — Ambient instrumental focus

- Core: beatless or near-beatless ambient for concentration.
- Must-have: instrumental, atmospheric, slow development.
- Soft: drone, texture, field recordings, gentle synth pads.
- Avoid: vocals, drums, dance beats, cinematic trailer crescendos.
- Analysis target: `Brian Eno` — `An Ending (Ascent)`.
- Like reason: instrumental ambient texture with no vocal focus.
- Dislike reason: vocals, beat-driven structure, or dramatic crescendo.
- Catches:
  - vocal leakage
  - ambient-vs-downtempo confusion
  - over-dramatic soundtrack picks

### S06 — Acoustic folk intimacy

- Core: intimate acoustic folk singer-songwriter.
- Must-have: acoustic instruments, warm vocal, low-to-mid energy.
- Soft: fingerpicked guitar, small-room production, lyrical focus.
- Avoid: full-band rock, electronic production, arena choruses, polished radio pop.
- Analysis target: `Nick Drake` — `Pink Moon`.
- Like reason: intimate acoustic folk fit.
- Dislike reason: too polished, too rock, too electronic, too big.
- Catches:
  - production-scale drift
  - acoustic token ignored
  - popular-radio bias

### S07 — Female-fronted punk energy

- Core: sharp female-fronted punk / riot grrrl energy.
- Must-have: female lead vocals, punk attitude, guitar-forward urgency.
- Soft: raw production, feminist/defiant lyrics.
- Avoid: male-fronted punk, pop-punk gloss, indie pop softness, metalcore.
- Analysis target: `Bikini Kill` — `Rebel Girl`.
- Like reason: female-fronted punk urgency.
- Dislike reason: male-fronted, too glossy, too soft, or too metal.
- Catches:
  - vocalist constraint miss
  - punk/pop-punk boundary failure
  - scene token over-broadening

### S08 — Non-English melodic metal without screaming

- Core: melodic metal or heavy rock with clean non-English vocals.
- Must-have: non-English vocals, melodic hooks, heavy guitars, no screaming.
- Soft: symphonic or folk-metal touches.
- Avoid: English vocals, growls/screams, death metal, metalcore breakdowns.
- Analysis target: `Myrath` — `Believer`.
- Like reason: clean melodic heavy track with non-English/global flavor.
- Dislike reason: screaming, English-only, or extreme-metal drift.
- Catches:
  - clean-vocal constraint miss
  - English fallback
  - over-heavy retrieval

### S09 — Jazz fusion technical

- Core: instrumental jazz fusion with technical playing.
- Must-have: instrumental, jazz harmony, fusion rhythm section.
- Soft: odd meters, electric piano, virtuosic solos.
- Avoid: smooth jazz, vocal jazz standards, lo-fi beats, lounge music.
- Analysis target: `Return to Forever` — `Spain`.
- Like reason: technical instrumental jazz-fusion fit.
- Dislike reason: smooth/lounge/vocal/lo-fi drift.
- Catches:
  - jazz umbrella too broad
  - instrumental ignored
  - low-effort smooth jazz picks

### S10 — K-pop bright dance

- Core: bright Korean pop with polished group vocals.
- Must-have: Korean artist, K-pop production, upbeat dance energy.
- Soft: hooks, choreography-ready rhythm, glossy mixing.
- Avoid: J-pop, western English pop, ballads, hip-hop-only tracks.
- Analysis target: `TWICE` — `Fancy`.
- Like reason: bright Korean pop dance fit.
- Dislike reason: not Korean/K-pop, too slow, or too hip-hop-only.
- Catches:
  - K-pop vs J-pop confusion
  - western pop fallback
  - ballad leakage

### S11 — Nordic melancholic indie

- Core: melancholic Nordic indie / art-pop.
- Must-have: Nordic artist, cold/melancholic mood, restrained production.
- Soft: airy vocals, wintery synths, minimal arrangements.
- Avoid: sunny indie pop, US/UK guitar pop, EDM drops, maximalist choruses.
- Analysis target: `AURORA` — `Runaway`.
- Like reason: Nordic melancholic restraint.
- Dislike reason: sunny, non-Nordic, too EDM, or too maximalist.
- Catches:
  - geography constraint miss
  - mood inversion
  - UK/US indie defaulting

### S12 — Club techno strict

- Core: functional club techno.
- Must-have: techno pulse, minimal vocals, hypnotic repetition.
- Soft: Berlin/Detroit influence, dark warehouse feel.
- Avoid: house piano, EDM festival drops, trance leads, pop vocals.
- Analysis target: `Jeff Mills` — `The Bells`.
- Like reason: strict techno energy.
- Dislike reason: house/trance/EDM/pop-vocal drift.
- Catches:
  - electronic subgenre collapse
  - vocal hooks ignored
  - festival EDM contamination

## Secondary scenarios

### S13 — Soul oldies but not rock

- Must-have: 60s/70s soul/R&B vocals, warm rhythm section, vintage recording.
- Avoid: classic rock, disco, yacht rock, modern retro-soul.
- Analysis target: `Otis Redding` — `Try a Little Tenderness`.
- Catches: era filter too broad, rock leakage, modern substitutions.

### S14 — Modern hyperpop chaos

- Must-have: distorted digital production, exaggerated hooks, chaotic texture.
- Avoid: clean mainstream dance-pop, normal synthpop, acoustic versions, mellow indie.
- Analysis target: `100 gecs` — `money machine`.
- Catches: model smoothing, genre sanitization, abrasion ignored.

### S15 — Obscure local scene

- Must-have: low-mainstream profile, scene fit, not global chart staples.
- Avoid: globally famous artists, obvious hits, editorial-playlist staples.
- Analysis target: choose a mid-obscurity anchor with reliable Spotify presence.
- Catches: popularity bias, safe recommendation collapse.

### S16 — Original studio recordings only

- Must-have: original studio recording.
- Avoid: live, acoustic, remix, cover, karaoke, sped-up, slowed/reverb, radio edit if avoidable.
- Analysis target: genre-specific anchor.
- Catches: track-title variant leakage, Spotify search accepts wrong version.

### S17 — Sad quiet study

- Must-have: low energy, melancholic, non-intrusive.
- Avoid: anthemic choruses, upbeat drums, dramatic builds, party energy.
- Analysis target: `Sufjan Stevens` — `Fourth of July`.
- Catches: mood/energy mismatch, chorus intensity ignored.

### S18 — Workout aggression

- Must-have: high energy, driving rhythm, aggressive momentum.
- Avoid: slow intros, mid-tempo mood pieces, ballads, long ambient sections.
- Analysis target: `The Prodigy` — `Breathe`.
- Catches: energy mismatch, slow-intro leakage, playlist pacing failure.

### S19 — Contradictory profile

- Must-have: calm, minimal, aggressive, high-energy.
- Avoid: both too soft and too intense.
- Expected behavior: under-fill is acceptable; hallucination or random picks are not.
- Catches: refusal/under-fill quality, instruction conflict handling.

### S20 — Artist rejection stress

- Seed: normal genre profile.
- Feedback: dislike 3+ distinct tracks by the same artist.
- Refine: explicitly reject that artist and adjacent soundalikes.
- Expected: playlist B contains zero tracks by that artist.
- Catches: feedback escalation failure, rejected-artist leakage.

## Additional oracle checks to consider

- `language_match_rate`
  - Japanese, Korean, German, Portuguese, non-English.
- `geo_match_rate`
  - artist country or scene where available.
- `era_match_rate`
  - release year or era proxy.
- `instrumental_match_rate`
  - no vocal tracks for instrumental profiles.
- `track_form_leak_count`
  - title contains live, remix, acoustic, cover, karaoke, sped up, slowed, radio edit.
- `artist_repeat_rate`
  - too many tracks by same artist.
- `mainstream_leak_count`
  - obvious global stars in discovery scenarios.
- `avoid_term_cite_rate`
  - tracks cite avoid traits or adjacent forbidden terms.
- `hard_constraint_fail_count`
  - separate hard-filter failures from soft-preference misses.
- `underfill_quality`
  - under-fill can pass if constraints are genuinely narrow.

## Recommended implementation order

1. Keep `default` for cost/speed/model comparison.
2. Keep `regression_japanese_theatrical` as known production-failure gate.
3. Add S05 ambient instrumental.
4. Add S04 90s boom bap.
5. Add S03 Brazilian Portuguese.
6. Add S12 strict techno.
7. Add S16 original studio recordings only.
8. Add S19 contradictory profile.

## Pass/fail ideas

- Hard filters should be zero-tolerance in small playlists.
- Soft preferences should be percentage-based.
- Playlist-B leakage should stay zero.
- Spotify-found should stay high unless scenario intentionally narrow.
- Under-fill should not fail automatically for narrow or contradictory scenarios.
- Hallucinated or off-pool tracks should always fail.
- Repeated known disliked artists should always fail.
