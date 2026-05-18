#!/usr/bin/env bash
# One-shot redeploy + trigger for the batched RAG-builder cycle.
#
#   1. Clear halt.flag (operator confirmation required)
#   2. Rebuild + push Docker image
#   3. Grant the compute service account permission to self-trigger
#   4. Apply runtime settings (env vars, task-timeout, retries)
#   5. Wipe stale build-state.json so the next execution starts a
#      fresh cycle from Phase 1
#   6. Trigger the first execution; subsequent batches self-chain

set -euo pipefail

PROJECT=spotivibe-rag
PROJECT_NUMBER=844237372250
REGION=us-central1
JOB=spotivibe-rag-builder
BUCKET=spotivibe-rag-corpus
COMPUTE_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "===== 1/6  Sanity: gcloud project + auth ====="
gcloud config set project "$PROJECT" >/dev/null
gcloud auth list --filter=status:ACTIVE --format="value(account)"

echo
echo "===== 2/6  Clear halt flag + stale build-state (if present) ====="
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

# Always wipe build-state on full redeploy: a code change to the
# state-machine could invalidate the old format.
if gcloud storage ls "gs://$BUCKET/build-state.json" >/dev/null 2>&1; then
  echo "Wiping prior build-state.json (full redeploy starts a new cycle)."
  gcloud storage rm "gs://$BUCKET/build-state.json"
fi

echo
echo "===== 3/6  Rebuild Docker image via Cloud Build ====="
echo "Submitting build (cloudbuild.yaml in $SCRIPT_DIR)…"
(cd "$SCRIPT_DIR/../.." && gcloud builds submit \
  --config "build-tools/cloud-run-job/cloudbuild.yaml" \
  --region="$REGION" \
  .)
echo "Build complete."

echo
echo "===== 4/6  Grant self-trigger IAM (idempotent) ====="
# The batched cloud_run_publish.py self-triggers the next batch via
# the Cloud Run Admin REST API. The container's default service
# account (Compute Engine SA on Cloud Run) therefore needs the
# run.jobs.run permission. roles/run.developer is the smallest
# pre-defined role that includes it.
gcloud run jobs add-iam-policy-binding "$JOB" \
  --region "$REGION" \
  --member="serviceAccount:$COMPUTE_SA" \
  --role="roles/run.developer" 2>&1 | tail -3 || true

echo
echo "===== 5/6  Apply runtime settings ====="
# task-timeout 4500 (75 min): each batch typically ~50 min but
# Last.fm API rate can drop to ~1.3 art/s, pushing 5000-artist
# batches to ~65 min. 75 min absorbs the slack without burning
# the free-tier vCPU budget.
# max-retries 0: never auto-retry. The self-trigger handles
# progression even on failure (we want each batch to try once,
# log, advance).
# env: BATCH_SIZE=5000 (5000 artists/batch), MIN_REBUILD_DAYS=6
# (cycle skip respects weekly cadence).
gcloud run jobs update "$JOB" \
  --region "$REGION" \
  --task-timeout=4500 \
  --max-retries=0 \
  --update-env-vars=BATCH_SIZE=5000,MIN_REBUILD_DAYS=6,CYCLE_TTL_DAYS=25,BATCH_RUN_REGION="$REGION",BATCH_RUN_JOB="$JOB" 2>&1 | tail -5

echo
echo "===== 6/6  Trigger first execution (FORCE_REBUILD=1) ====="
# The first execution always starts a new cycle: Phase 1 MB build +
# the first ~5000-artist Last.fm batch + self-trigger for batch 2.
gcloud run jobs execute "$JOB" \
  --region "$REGION" \
  --update-env-vars=FORCE_REBUILD=1 \
  --async

echo
echo "===== Done ====="
echo "Watch with:"
echo "  gcloud run jobs executions list --job $JOB --region $REGION --limit 5"
echo "  gcloud storage cat gs://$BUCKET/build-state.json"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB' --limit 30 --freshness=2h --format='value(timestamp,severity,textPayload)'"
echo
echo "Expected behaviour:"
echo "  - This first execution: Phase 1 (MB build, ~10 min) + first batch (~50 min)"
echo "  - Each subsequent execution self-triggers in build-state.json's next_offset"
echo "  - ~35 batches × ~50 min = ~30 h wall clock (with cooldowns between executions)"
echo "  - Final batch finalises corpus + manifest; clears build-state.json"
