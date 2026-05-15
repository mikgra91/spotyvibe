#!/usr/bin/env bash
# One-shot deploy of the spotivibe-rag-enricher job.
# Builds the Docker image and (re)creates the Cloud Run Job with the
# secrets-bound env config. Idempotent — safe to re-run after code changes.

set -euo pipefail

PROJECT=spotivibe-rag
REGION=us-central1
JOB=spotivibe-rag-enricher
BUCKET=spotivibe-rag-corpus
IMAGE="us-central1-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/$JOB:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

gcloud config set project "$PROJECT" >/dev/null

echo "===== 1/3  Build + push image ====="
(cd "$REPO_ROOT" && gcloud builds submit \
  --config build-tools/cloud-run-enricher/cloudbuild.yaml \
  --region "$REGION" \
  .)

echo
echo "===== 2/3  Create or update Cloud Run Job ====="
# `gcloud run jobs deploy` is idempotent: creates if missing, updates if present.
gcloud run jobs deploy "$JOB" \
  --region "$REGION" \
  --image "$IMAGE" \
  --task-timeout=7200 \
  --memory=2Gi \
  --cpu=1 \
  --max-retries=0 \
  --set-env-vars="GCS_BUCKET=$BUCKET,TOP_TRACKS_PER_ARTIST=5" \
  --set-secrets="SPOTIFY_CLIENT_ID=spotify-client-id:latest,SPOTIFY_CLIENT_SECRET=spotify-client-secret:latest"

echo
echo "===== 3/3  Disable Spotify enrichment on the legacy builder job ====="
# The legacy spotivibe-rag-builder job used to do Phase 2 (Spotify) inline.
# That's now this enricher's responsibility. Flip the env switch so the
# builder skips Phase 2 cleanly. The code path is retained (DISABLE_*
# env var) so we can re-enable in an emergency.
gcloud run jobs update spotivibe-rag-builder \
  --region "$REGION" \
  --update-env-vars="DISABLE_SPOTIFY_ENRICHMENT=1"

echo
echo "===== Done ====="
echo "Trigger with: bash $SCRIPT_DIR/trigger.sh"
