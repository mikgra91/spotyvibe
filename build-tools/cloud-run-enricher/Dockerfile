FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY build-tools/cloud-run-enricher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build-tools/enrich_top_tracks.py        build-tools/
COPY build-tools/cloud_run_top_tracks.py     build-tools/
COPY build-tools/spotify_enrichment/         build-tools/spotify_enrichment/

ENTRYPOINT ["python", "build-tools/cloud_run_top_tracks.py"]
