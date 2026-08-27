FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        xz-utils ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY build-tools/cloud-run-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build-tools/cloud_run_publish.py       build-tools/
# Second entrypoint, selected by the spotivibe-ai-blocklist job via --command
# /--args. Shares the image; publishes on its own schedule.
COPY build-tools/publish_ai_blocklist.py    build-tools/
COPY build-tools/rag/                       build-tools/rag/
COPY data/rag_corpus/tag_aliases.json       data/rag_corpus/

ENTRYPOINT ["python", "build-tools/cloud_run_publish.py"]
