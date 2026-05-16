# RAG corpus

This directory holds the retrieval corpus used by `core/src/rag/`.

- `tag_aliases.json` — hand-curated synonym map (user text → canonical tag).
- `artists.jsonl.gz` — the artist corpus. **Not committed.** Build with
  `build-tools/rag/build_rag_corpus.py` or download the release asset.

See `documentation/TechnicalManual.md` §"RAG candidate-pool feature" and
§"RAG design reference" for the full design.
