#!/usr/bin/env bash
# Simple manual trigger — no image rebuild.
# Use for weekly refreshes when the deployed image is already correct.
# For a full image rebuild + trigger, use redeploy_and_run.sh instead.

set -euo pipefail

PROJECT=spotivibe-rag
REGION=us-central1
JOB=spotivibe-rag-builder
BUCKET=spotivibe-rag-corpus

gcloud config set project "$PROJECT" >/dev/null

# Refuse if halt.flag is set — that's the circuit breaker.
if gcloud storage ls "gs://$BUCKET/halt.flag" >/dev/null 2>&1; then
  echo "❌ halt.flag is set on gs://$BUCKET/. Investigate before triggering:"
  gcloud storage cat "gs://$BUCKET/halt.flag"
  echo
  echo "Resume with:  gcloud storage rm gs://$BUCKET/halt.flag"
  exit 1
fi

echo "Triggering $JOB in $REGION …"
gcloud run jobs execute "$JOB" --region "$REGION" --async

echo
echo "Watch with:"
echo "  gcloud run jobs executions list --job $JOB --region $REGION --limit 3"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB' --limit 30 --freshness=1h --format='value(timestamp,severity,textPayload)'"
