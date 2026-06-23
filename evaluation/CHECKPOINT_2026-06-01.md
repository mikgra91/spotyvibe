# Checkpoint — 2026-06-01 (cite-rate disambiguation, paused)

Resume point for the AI-tag-overlay **release gate**. We were disambiguating
whether the AI-tag wiring regresses must-have-cite rate. The original alarm
(2-iter sweep: gpt-5.4-mini 90.8%→80.0%, gpt-4.1-mini 96.7%→92.5%) looks like
**small-n noise** — preliminary 6-iter data shows no real regression.

## Where we are

- **Overlay wiring is DONE & tested** (uncommitted): `ai_vocab.py`, `corpus.py`,
  `retrieval.py` (`_artist_tag_weight` ai_tags branch → weight 2), `harness.py`
  (sandbox copies `ai_tags_overlay.json`), `test_rag_ai_tags.py` (6 tests pass).
- **Local corpus state:** `ai_tags_overlay.json` is RESTORED in
  `C:/Users/micha/AppData/Local/spotyvibe/rag_corpus/` → **treatment is active**.
- **eval/settings.ini** is set to the disambiguation config (NOT the original):
  - `models = openai/gpt-5.4-mini, openai/gpt-4.1-mini`
  - `iterations = 6`
  - `scenarios = default,lastfm_tag_weighting`
  - ⚠ Restore to original after the gate clears: `models = anthropic/claude-haiku-4.5`, `iterations = 3`.

## Results so far (cite-rate = has_must_have_cite over track rows, null verify)

| Model | TREATMENT (overlay present), 6 iters | BASELINE (overlay absent) |
|---|---|---|
| gpt-5.4-mini | **0.895** (282/315) | 0.883 (159/180) *partial* |
| gpt-4.1-mini | **0.936** (337/360) | 0.967 (58/60) *partial, thin* |

- Treatment dir (COMPLETE): `evaluation/results/20260601-193651/`
- Baseline dir (PARTIAL — killed mid-run): `evaluation/results/20260601-202413/`
  - gpt-5.4-mini ~complete; gpt-4.1-mini only ~2 iters (n=60). **Re-run baseline fresh tomorrow** rather than trust the thin 4.1-mini number.

By-scenario treatment detail: 4.1-mini default 1.000 / lastfm 0.872; 5.4-mini default 0.889 / lastfm 0.900.

## Tomorrow — resume steps

1. **Finish the baseline** (clean, full 6 iters):
   ```bash
   # overlay aside → baseline
   mv "/c/Users/micha/AppData/Local/spotyvibe/rag_corpus/ai_tags_overlay.json" \
      "/c/Users/micha/AppData/Local/spotyvibe/rag_corpus/ai_tags_overlay.json.HELD"
   python evaluation/run_evaluation.py --no-confirm --verify-mode null
   # restore overlay
   mv "/c/Users/micha/AppData/Local/spotyvibe/rag_corpus/ai_tags_overlay.json.HELD" \
      "/c/Users/micha/AppData/Local/spotyvibe/rag_corpus/ai_tags_overlay.json"
   ```
2. **Compute deltas** with the aggregator snippet (reads `*/eval.jsonl`,
   counts `has_must_have_cite` per model). Same snippet used today.
3. **Decide the gate:**
   - Δ within ~±3pp → **noise → gate clears.** Proceed to release the corpus.
   - Δ still meaningfully negative on a model → apply **Lever A** and re-eval
     (treatment+enforcement as a 3rd condition).

## Cite-enforcement levers (designed, NOT applied — would confound runs)

- **Lever A (recommended):** in `prompts/system_prompt.txt` (~L40) and
  `prompts/track_select_system.txt` (~L52), make `rationale[0]` a *positional*
  reserved slot = `{type: profile_match, arg: <the specific must_have trait this
  track satisfies>}`. Legitimate: HC4 already forces every track to satisfy
  must_have; this just surfaces that anchor. **Do NOT edit prompts while an
  eval is running** (prompts are read live).
- **Lever B:** inject `CITE ONE OF: [<verbatim must_have strings>]` next to the
  rationale schema so the detector's substring check matches.
- **Lever C:** broaden `core/src/eval_log.py::_arg_satisfies_must_have` to also
  accept `must_have_tags` (fixes a real false-negative). Do NOT extend to
  AI-tag scenes — that masks drift.

## After the gate clears — release the corpus

Build slim prod overlay (drop `_usage`/`_oov`/`source_hash` QA metadata, keep
`mbid→ai_tags`), upload to GCS next to `artists.jsonl.gz`, wire client download
in `core/src/rag/distribution.py`.

## Other uncommitted work (needs a `CP ALLOWED` to commit)

- API robustness fix: `app.py` `_request_json_object()` + 9 endpoints,
  `core/tests/test_api_robustness.py` (54 cases pass).
- Taste dashboard fix: `core/src/taste.py`, `taste_dashboard.html/.js`, i18n
  `dashboard.card_artists` (en/de/jp).
- See `git status` for the full list.
</content>
