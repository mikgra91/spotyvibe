"""Spotify enrichment helpers for the RAG corpus build pipeline.

Pure build-time module — never imported at runtime by the SpotyVibe app.
Lives under build-tools/ so the runtime corpus consumer (core/src/rag/)
stays free of any HTTP / Spotify dependencies.
"""

