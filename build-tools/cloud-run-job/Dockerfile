FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        xz-utils ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY build-tools/cloud-run-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build-tools/build_rag_corpus.py        build-tools/
COPY build-tools/refresh_rag_corpus.py      build-tools/
COPY build-tools/cloud_run_publish.py       build-tools/
COPY build-tools/enrich_with_spotify.py     build-tools/
COPY build-tools/spotify_enrichment/        build-tools/spotify_enrichment/
COPY build-tools/enrich_with_lastfm.py      build-tools/
COPY build-tools/lastfm_enrichment/         build-tools/lastfm_enrichment/
COPY data/rag_corpus/tag_aliases.json       data/rag_corpus/

ENTRYPOINT ["python", "build-tools/cloud_run_publish.py"]

