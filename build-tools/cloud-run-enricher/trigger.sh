#!/usr/bin/env bash
# Trigger one execution of the spotivibe-rag-enricher job.
# Refuses if halt.flag is set (Spotify circuit breaker).

set -euo pipefail

PROJECT=spotivibe-rag
REGION=us-central1
JOB=spotivibe-rag-enricher
BUCKET=spotivibe-rag-corpus

gcloud config set project "$PROJECT" >/dev/null

if gcloud storage ls "gs://$BUCKET/halt.flag" >/dev/null 2>&1; then
  echo "❌ halt.flag is set — refusing to trigger. Contents:"
  gcloud storage cat "gs://$BUCKET/halt.flag"
  echo
  echo "Investigate, then resume with:"
  echo "  gcloud storage rm gs://$BUCKET/halt.flag"
  exit 1
fi

echo "Triggering $JOB in $REGION …"
gcloud run jobs execute "$JOB" --region "$REGION" --wait=false

echo
echo "Watch with:"
echo "  gcloud run jobs executions list --job $JOB --region $REGION --limit 3"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB' --limit 30 --freshness=2h --format='value(timestamp,severity,textPayload)'"
