#!/usr/bin/env bash
# One-shot: clear halt flag, rebuild image, raise timeout, trigger job.
# Run when Spotify quota has reset (Retry-After window expired).
#
# Pre-flight check we DO NOT do here: confirming Spotify quota is back.
# If you're unsure, hit `curl -i -H "Authorization: Bearer <token>" \
# https://api.spotify.com/v1/search?q=test&type=artist` once first — a
# 429 with Retry-After tells you the bucket is still drained; a 200
# means we're good to go.

set -euo pipefail

PROJECT=spotivibe-rag
REGION=us-central1
JOB=spotivibe-rag-builder
BUCKET=spotivibe-rag-corpus
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "===== 1/5  Sanity: gcloud project + auth ====="
gcloud config set project "$PROJECT"
gcloud auth list --filter=status:ACTIVE --format="value(account)"

echo
echo "===== 2/5  Clear halt flag (if present) ====="
if gcloud storage ls "gs://$BUCKET/halt.flag" >/dev/null 2>&1; then
  echo "Halt flag exists — contents:"
  gcloud storage cat "gs://$BUCKET/halt.flag" || true
  echo
  read -rp "Delete halt.flag and continue? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Aborted by user."; exit 1; }
  gcloud storage rm "gs://$BUCKET/halt.flag"
  echo "Halt flag deleted."
else
  echo "No halt flag — clean state."
fi

echo
echo "===== 3/5  Rebuild Docker image via Cloud Build ====="
echo "Submitting build (cloudbuild.yaml in $SCRIPT_DIR)…"
(cd "$SCRIPT_DIR/../.." && gcloud builds submit \
  --config "build-tools/cloud-run-job/cloudbuild.yaml" \
  --region="$REGION" \
  .)
echo "Build complete."

echo
echo "===== 4/5  Raise job task-timeout to 2 h ====="
gcloud run jobs update "$JOB" \
  --region "$REGION" \
  --task-timeout=7200

echo
echo "===== 5/5  Trigger execution ====="
gcloud run jobs execute "$JOB" \
  --region "$REGION" \
  --async

echo
echo "===== Done ====="
echo "Watch with:"
echo "  gcloud run jobs executions list --job $JOB --region $REGION --limit 3"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB' --limit 30 --freshness=1h --format='value(timestamp,severity,textPayload)'"
echo
echo "Phase 4 (top-tracks) adds ~1 search call per matched artist (~0.17 s)."
echo "At ~30 K matched artists that's ~85 min; total wall ≈ 90-100 min."
