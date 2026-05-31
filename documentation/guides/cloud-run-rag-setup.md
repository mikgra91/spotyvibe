# Cloud Run setup — public read-only RAG corpus mirror

> **Purpose**: stand up a Google Cloud Run service that hosts the MusicBrainz-derived
> RAG corpus, refreshes it automatically once a week, and exposes it as a
> public *read-only* download endpoint that the SpotyVibe desktop client can
> point at instead of the GitHub Releases mirror.
>
> **Audience**: the maintainer who currently runs `refresh_rag_corpus.py` +
> `publish_rag_corpus.py` by hand on a personal machine.
>
> **Out of scope**: hosting the LLM (rejected — quality gap vs hosted GPT-4-class
> models; see `documentation/TechnicalManual.md` § RAG limitations) and multi-tenant
> Flask hosting (deferred — see `result-improvement.md` § CF-Rat-6).

> **Deployed status (2026-04-22):** Infrastructure is live.
> - Project: `spotivibe-rag` | Region: `us-central1`
> - GCS bucket: `spotivibe-rag-corpus` (public read, us-central1)
> - Cloud Run Job: `spotivibe-rag-builder` (2 vCPU, 4 GiB, 60 min timeout)
> - Cloud Scheduler: `spotivibe-rag-weekly` (Mon 03:00 Europe/Vienna)
> - Service account: `spotivibe-rag-builder@spotivibe-rag.iam.gserviceaccount.com`
> - **Next step:** trigger first manual execution to seed the bucket (§ 12 step 2).

---

## 1. What this gives you

| Today (manual) | After this setup (automated) |
|---|---|
| You run `python build-tools/rag/refresh_rag_corpus.py` on your laptop quarterly. | A weekly Cloud Run **Job** rebuilds the corpus on Google's hardware. |
| You run `python build-tools/rag/publish_rag_corpus.py` to push to GitHub Releases. | The Job uploads the new `artists.jsonl.gz` + `manifest.json` to a public **GCS bucket**. |
| Clients fetch from `https://github.com/.../releases/.../artists.jsonl.gz`. | Clients fetch from `https://storage.googleapis.com/<bucket>/artists.jsonl.gz` (or a custom domain). |
| You eat ~3 GB of MusicBrainz dumps + ~33 GB extracted on your laptop every refresh. | Cloud Run Job ephemeral storage handles it; nothing stays on your machine. |
| Refresh cadence depends on your memory. | Cloud Scheduler triggers it weekly at a fixed time. |

**Cost**: $0/mo on the always-free tier (see § 9 below). Worst case at 10× volume: a few cents.

**Security model**: the bucket is **public read** (anyone can `GET` the corpus), **private write** (only the Cloud Run Job's service account can upload, **using its own Google-managed credentials — no token, no PAT, no secret to rotate**). Users do *not* need a Google Cloud account to consume the corpus.

### 1.1 What you do once vs what runs forever

| One-time, manual (you, ~30 min) | Forever, automatic (Cloud Run + Scheduler) |
|---|---|
| Create the GCP project, link billing, enable APIs (§ 3.1 – § 3.3) | Weekly cron triggers the Job (§ 6) |
| Create the GCS bucket and the two service accounts (§ 3.4 – § 3.5) | Job downloads the latest MusicBrainz dump (~3 GB) into ephemeral disk |
| Build + push the Docker image once (§ 4.4) | Extracts (~33 GB ephemeral) and runs `build_rag_corpus.py` |
| Create the Cloud Run Job + Cloud Scheduler trigger (§ 5 – § 6) | Uploads the resulting 7 MB `artists.jsonl.gz` + `manifest.json` to the bucket |
| **Trigger the first Job run manually** to seed the bucket and watch logs (§ 12 step 2) | Container exits → ephemeral disk wiped automatically |
| Flip the `RAG_MANIFEST_URL` default in `config.py` and ship a release (§ 12 step 5) | Clients fetch the fresh file via plain HTTPS GET, no auth |

> **The bucket starts empty.** No manual upload of an existing corpus
> is required — the very first Job execution generates the file from
> scratch from the MusicBrainz dump. You trigger that first run
> manually only so you can observe the pipeline working before handing
> control over to the cron.

---

## 2. Architecture

```
┌──────────────────────────┐    weekly cron (Cloud Scheduler)
│  Cloud Scheduler         │─────────────────────┐
│  cron: 0 3 * * 1 (Mon)   │                     ▼
└──────────────────────────┘    ┌────────────────────────────────────┐
                                │ Cloud Run Job                      │
│ - container: build_rag_corpus.py   │
│ - 4 GiB RAM, 2 vCPU, 1 task       │
                                │ - timeout: 60 min                  │
                                │ - ephemeral disk for MB dumps      │
                                └─────────────┬──────────────────────┘
                                              │ uploads
                                              ▼
                                ┌────────────────────────────────────┐
                                │ GCS bucket: spotyvibe-rag-corpus   │
                                │ - artists.jsonl.gz (~7 MB)         │
                                │ - manifest.json                    │
                                │ - PUBLIC READ via IAM allUsers     │
                                └─────────────┬──────────────────────┘
                                              │ HTTPS GET
                                              ▼
                                ┌────────────────────────────────────┐
                                │ SpotyVibe desktop client           │
                                │ core/src/rag/distribution.py       │
                                │ - reads RAG_MANIFEST_URL env var   │
                                └────────────────────────────────────┘
```

We use a **Cloud Run Job** (not a Service) because the rebuild is a long-running batch task with no inbound HTTP. Jobs are billed only while running — the idle weekly cadence costs nothing.

---

## 3. One-time user / project setup

### 3.1 Create / pick a Google Cloud project

1. Go to <https://console.cloud.google.com/>. Sign in (or create) a Google account. **No credit card needed** for the free tier, but linking a billing account is required to enable the APIs — Google will not charge unless you exceed free quotas.
2. Create a new project. Suggested name: `spotyvibe-rag`. Note the **Project ID** (e.g. `spotyvibe-rag-471829`) — you'll need it below.
3. **Link a billing account.** Console → Billing → Link a billing account. (Required to enable Cloud Run + GCS, but free-tier usage stays at $0.)

### 3.2 Install + initialise `gcloud`

Locally, install the Google Cloud CLI: <https://cloud.google.com/sdk/docs/install>

```bash
gcloud auth login
gcloud config set project spotivibe-rag          # your actual project ID
gcloud config set run/region us-central1          # free-tier region
```

### 3.3 Enable the APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

This is a one-time action per project. Takes ~1 minute.

### 3.4 Create the public corpus bucket

```bash
# Pick a globally-unique bucket name. Lowercase, no underscores.
BUCKET=spotyvibe-rag-corpus

gcloud storage buckets create gs://$BUCKET \
  --location=us-central1 \
  --uniform-bucket-level-access

# Remove public access prevention so we can grant allUsers read access.
gcloud storage buckets update gs://$BUCKET --clear-pap

# Make objects readable by anyone on the internet (read-only, no list).
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

> **Why `us-central1`?** GCS's "always-free" 5 GB-months storage tier
> only covers the three US single-region locations
> (`us-central1`, `us-east1`, `us-west1`). Buckets in any other region
> (including `europe-west1`) are billed from the first byte. At our
> 7 MB scale that's still a fraction of a cent per month — but
> `us-central1` keeps the strict-zero-cost story intact. The bucket
> being in the US has no client-side impact: GCS serves objects from
> Google's global edge cache, so European users still get sub-100 ms
> downloads.

> **Why uniform access + objectViewer at the bucket level?** This grants
> *read* on every object that lives in the bucket but does **not** grant
> *list*, *write* or *delete*. Casual visitors cannot browse the bucket
> contents — they must know the exact object name.

> **The bucket starts empty — that's fine.** No manual bootstrap is
> needed. The first Cloud Run Job execution (§ 5) builds the corpus
> from the MusicBrainz dump from scratch and uploads it. Until that
> first run completes the bucket simply has no objects; clients
> requesting `manifest.json` get HTTP 404 and fall back to the legacy
> path (or, on a fresh install, simply prompt the user to wait for the
> first publish). You will trigger that first run manually below to
> seed the bucket *and* prove the pipeline works end-to-end before the
> weekly cron takes over.

### 3.4.1 Why GCS, not GitHub Releases?

Both are valid 7 MB hosts. We pick GCS specifically for the *automation*
side, not the delivery side:

| | GCS bucket (chosen) | GitHub Releases |
|---|---|---|
| Auth from Cloud Run Job | **Service account, automatic** — Google's metadata service injects credentials. **No token to manage.** | GitHub PAT with `repo:write`. Must be stored as a Cloud Run secret. **Rotates / can be revoked / counts against your account.** |
| Cost at our scale | $0/mo (see § 9) | $0/mo |
| Public download URL | `https://storage.googleapis.com/<bucket>/artists.jsonl.gz` | `https://github.com/.../releases/download/rag-corpus-latest/artists.jsonl.gz` |
| CDN / edge caching | Native via GCS frontend | Native via GitHub's CDN |
| Operational footprint | One bucket | One PAT to keep alive forever |

The deciding factor is **no PAT lifecycle management**. The Cloud Run
service account auths to its own project's GCS without any human in
the loop — that's the whole point of "set it up once and forget it".

### 3.5 Create a dedicated service account for the Job

```bash
SA=spotyvibe-rag-builder
gcloud iam service-accounts create $SA \
  --display-name="SpotyVibe RAG corpus builder"

# Allow the SA to write to the corpus bucket only (least privilege).
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:${SA}@$(gcloud config get-value project).iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

---

## 4. Container image — what runs in the Job

The Job container does exactly what `build-tools/rag/refresh_rag_corpus.py` +
`build-tools/rag/publish_rag_corpus.py` do today, plus an upload to GCS instead
of GitHub Releases.

### 4.1 New file: `build-tools/cloud-run-job/Dockerfile`

```dockerfile
# Slim Python base. Cloud Run Jobs add no overhead — the image is the unit.
FROM python:3.13-slim

# OS deps for tarfile XZ extraction + curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xz-utils ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only install what build_rag_corpus.py needs — keep image small.
COPY build-tools/cloud-run-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the corpus-builder code (NOT the whole repo — we don't need
# Flask, Spotipy, etc. in this container).
COPY build-tools/rag/build_rag_corpus.py        build-tools/
COPY build-tools/rag/refresh_rag_corpus.py      build-tools/
COPY build-tools/cloud_run_publish.py       build-tools/
COPY data/rag_corpus/tag_aliases.json       data/rag_corpus/

ENTRYPOINT ["python", "build-tools/cloud_run_publish.py"]
```

### 4.2 New file: `build-tools/cloud-run-job/requirements.txt`

```
google-cloud-storage>=2.18.0
```

(That's it. The corpus builder uses only stdlib.)

### 4.3 New file: `build-tools/cloud_run_publish.py`

The orchestrator that runs *inside* the Job:

```python
"""Cloud Run Job entry point: refresh the RAG corpus and upload to GCS.

Reads its configuration from env vars set in the Job spec:
    GCS_BUCKET           — destination bucket (e.g. "spotyvibe-rag-corpus")
    CORPUS_TOP_N         — top-N artists to include (default 350000)
    KEEP_INTERMEDIATES   — "1" to retain MB dumps between runs (default off)

Pipeline:
    1. Run refresh_rag_corpus.py (downloads MB dump + invokes build_rag_corpus.py).
    2. Compute sha256 of the resulting artists.jsonl.gz.
    3. Upload artists.jsonl.gz to gs://$GCS_BUCKET/artists.jsonl.gz.
    4. Write + upload manifest.json with corpus_url, sha256, size, build timestamp.
    5. Wipe the working directory (corpus build leaves ~33 GB extracted).

Exit non-zero on any failure so Cloud Run logs the run as failed.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from google.cloud import storage  # type: ignore

ROOT = Path(__file__).resolve().parent.parent  # repo root inside the container
CORPUS_PATH = ROOT / "data" / "rag_corpus" / "artists.jsonl.gz"
MANIFEST_PATH = ROOT / "data" / "rag_corpus" / "manifest.json"
WORK_DIR = ROOT / "build-tools" / ".rag-cache"


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    bucket_name = os.environ["GCS_BUCKET"]
    top_n = os.environ.get("CORPUS_TOP_N", "350000")

    # 1. Build the corpus.
    cleanup_flag = [] if os.environ.get("KEEP_INTERMEDIATES") == "1" else ["--cleanup"]
    _run([
        "python", "build-tools/rag/refresh_rag_corpus.py",
        "--top-n", top_n,
        *cleanup_flag,
    ])

    if not CORPUS_PATH.exists():
        print(f"ERROR: corpus not produced at {CORPUS_PATH}", file=sys.stderr)
        return 1

    # 2. Compute hash + assemble manifest.
    sha = _sha256(CORPUS_PATH)
    size = CORPUS_PATH.stat().st_size
    version = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    corpus_url = f"https://storage.googleapis.com/{bucket_name}/artists.jsonl.gz"
    manifest = {
        "corpus_version": version,
        "built_at": datetime.datetime.utcnow().isoformat() + "Z",
        "sha256": sha,
        "size_bytes": size,
        "corpus_url": corpus_url,
        "source": "cloud-run-job",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    # 3. + 4. Upload both, corpus first so manifest never points at a missing asset.
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    print(f"Uploading {CORPUS_PATH} ({size:,} bytes) → gs://{bucket_name}/artists.jsonl.gz",
          flush=True)
    blob = bucket.blob("artists.jsonl.gz")
    blob.cache_control = "public, max-age=86400"  # 1-day CDN cache
    blob.upload_from_filename(str(CORPUS_PATH))

    print(f"Uploading manifest → gs://{bucket_name}/manifest.json", flush=True)
    mblob = bucket.blob("manifest.json")
    mblob.cache_control = "public, max-age=300"   # 5-min cache so updates are seen quickly
    mblob.upload_from_filename(str(MANIFEST_PATH))

    # 5. Wipe the work dir even if KEEP_INTERMEDIATES wasn't set — Cloud Run
    # ephemeral disk is gone after the Job exits anyway, but this keeps logs
    # tidy if the Job is re-used as a long-running scratch container.
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print(f"OK: published version {version} ({sha[:12]}…)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> **Why we keep `--cleanup` on by default**: Cloud Run Jobs run in a sandbox
> with ephemeral disk. The 33 GB of extracted MusicBrainz tarballs disappears
> when the Job container exits regardless. The `--cleanup` flag just frees
> disk inside the same run so the build doesn't fight itself for space.

### 4.4 Deploy the image

From the repo root, with your project + region set:

```bash
PROJECT=$(gcloud config get-value project)
REGION=us-central1

# Cloud Build uses cloudbuild.yaml which specifies the Dockerfile path.
gcloud builds submit \
  --config=build-tools/cloud-run-job/cloudbuild.yaml \
  .
```

First push takes ~3–5 minutes (Cloud Build is creating the Artifact Registry repo on the fly). Subsequent pushes are layer-cached and faster.

---

## 5. Create the Cloud Run Job

```bash
PROJECT=$(gcloud config get-value project)
REGION=us-central1
SA=spotivibe-rag-builder@${PROJECT}.iam.gserviceaccount.com
BUCKET=spotivibe-rag-corpus
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/spotyvibe-rag-builder:latest

gcloud run jobs create spotivibe-rag-builder \
  --image=$IMAGE \
  --region=$REGION \
  --service-account=$SA \
  --set-env-vars=GCS_BUCKET=${BUCKET},CORPUS_TOP_N=350000 \
  --max-retries=1 \
  --task-timeout=60m \
  --cpu=2 \
  --memory=4Gi
```

Sizing rationale:

| Knob | Value | Why |
|---|---|---|
| `--cpu` | 2 | Sufficient for XZ extraction + JSON parsing; keeps cost low while staying within free tier. |
| `--memory` | 4 GiB | Adequate for artist+release-group table parsing. Upgrade to 8 GiB if the job OOMs. |
| `--task-timeout` | 60 m | Default 10 min is too tight; the build typically takes 8–15 min including the ~3 GB download. |
| `--max-retries` | 1 | One retry on transient MetaBrainz / network blips. More than that masks real failures. |

Verify the Job exists and run it once manually:

```bash
gcloud run jobs execute spotivibe-rag-builder --region=$REGION --wait
gcloud storage ls gs://$BUCKET   # should list artists.jsonl.gz + manifest.json
```

You should see the corpus and manifest in the bucket. Test a public download:

```bash
curl -sI https://storage.googleapis.com/$BUCKET/manifest.json
# HTTP/2 200 — no auth header needed. Cache-Control: public, max-age=300.
```

---

## 6. Schedule the weekly refresh

Cloud Scheduler triggers the Job via its REST API. Pick a low-traffic time
(03:00 UTC Monday is a good default — well after MusicBrainz publishes its
weekly dump on Sunday).

```bash
PROJECT=$(gcloud config get-value project)
REGION=us-central1
SA=spotivibe-rag-builder@${PROJECT}.iam.gserviceaccount.com

# Grant the builder SA permission to invoke the Job (needed by Scheduler).
gcloud run jobs add-iam-policy-binding spotivibe-rag-builder \
  --region=$REGION \
  --member=serviceAccount:$SA \
  --role=roles/run.invoker

# Create the cron (Monday 03:00 Vienna time — after MusicBrainz Sunday dump).
gcloud scheduler jobs create http spotivibe-rag-weekly \
  --location=$REGION \
  --schedule="0 3 * * 1" \
  --time-zone="Europe/Vienna" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/spotivibe-rag-builder:run" \
  --http-method=POST \
  --oauth-service-account-email=$SA
```

Verify the next run time:

```bash
gcloud scheduler jobs describe spotyvibe-rag-weekly --location=$REGION | grep -E '(schedule|state|nextRunTime)'
```

To trigger ad-hoc (e.g. after an emergency fix to `tag_aliases.json`):

```bash
gcloud scheduler jobs run spotyvibe-rag-weekly --location=$REGION
# OR call the Job directly without going through Scheduler:
gcloud run jobs execute spotivibe-rag-builder --region=$REGION
```

---

## 7. Point SpotyVibe at the new endpoint

Two changes needed in the desktop client — both are environment-variable
overrides; no code change required for the cutover.

### 7.1 Configure clients via env var

The existing constant in `config.py`:

```python
RAG_MANIFEST_URL = os.environ.get(
    "RAG_MANIFEST_URL",
    "https://github.com/mikgra91/spotyvibe/releases/download/"
    "rag-corpus-latest/manifest.json",
)
```

…already supports a `RAG_MANIFEST_URL` override. Set it to the GCS URL:

```bash
export RAG_MANIFEST_URL=https://storage.googleapis.com/spotyvibe-rag-corpus/manifest.json
```

(For Windows desktop installs, this can be set in the user's environment or
baked into a future release by changing the default literal.)

### 7.2 Recommended: dual-publish during cutover

For the first 4 weeks after standing this up, keep `publish_rag_corpus.py` running on the GitHub Releases path **as well** — that gives you a fallback if the Cloud Run Job hits an outage and lets you A/B compare client telemetry. After 4 weeks of green Cloud Run runs, drop the GitHub publish step.

### 7.3 No multi-tenant / no auth required

Bucket is `roles/storage.objectViewer` to `allUsers` — clients fetch with a
plain `GET`. There is **no API key, no quota per client, no signed URL flow**
required. The CDN cache (`Cache-Control: public, max-age=86400` on the
corpus, 5 min on the manifest) absorbs almost all the traffic so even thousands
of users land near zero on Google's bandwidth meter.

---

## 8. Operational runbook

### Where to look first

| Symptom | Where |
|---|---|
| "My client says no update available" | Console → Cloud Run → Jobs → `spotivibe-rag-builder` → Executions → check the latest run's stdout |
| "Manifest looks stale" | `gcloud storage ls --long gs://spotyvibe-rag-corpus` — check `Updated:` timestamp |
| "Weekly run didn't fire" | Console → Cloud Scheduler → `spotyvibe-rag-weekly` → check `Last execution status` |
| "Build failed mid-run" | Console → Cloud Run → Jobs → Executions → click the failed task → Logs |

### Useful commands

```bash
# Recent Job executions (last 10).
gcloud run jobs executions list --job=spotivibe-rag-builder --region=$REGION --limit=10

# Tail logs of the most recent execution.
gcloud run jobs executions describe <execution-id> --region=$REGION --format=json | jq

# Force-trigger a refresh now.
gcloud run jobs execute spotivibe-rag-builder --region=$REGION

# Roll back a corpus (manual: re-upload an old version from a backup).
# We don't keep historical versions in the bucket by default — see § 11
# for an optional Object Versioning enhancement.
```

### What can break

1. **MusicBrainz dump URL drift.** If MetaBrainz reorganises `data.metabrainz.org`, `_fetch_latest_folder()` in `refresh_rag_corpus.py` breaks. The Job will exit non-zero; alert via § 10.
2. **Bucket write quota.** Free tier is 5 GiB stored / 1 GiB egress / month. The corpus is 7 MB, manifest is 1 KB — quota is unreachable at any sane refresh cadence.
3. **Cloud Build push fails.** Usually a transient Artifact Registry hiccup. Re-run `gcloud builds submit ...`.

---

## 9. Cost expectation

### 9.1 Cloud Run + Scheduler + Artifact Registry

| Component | Free tier (always free, monthly) | Our actual usage / month |
|---|---|---|
| Cloud Run Jobs vCPU | 240,000 vCPU-sec | 2 vCPU × 15 min × 4 runs = **1,800 vCPU-sec** (0.75 % of free) |
| Cloud Run Jobs memory | 450,000 GiB-sec | 4 GiB × 15 min × 4 runs = **14,400 GiB-sec** (3.2 % of free) |
| Cloud Scheduler | 3 jobs free | 1 job |
| Artifact Registry | 0.5 GiB free | ~150 MB image |

### 9.2 Cloud Storage (where the corpus lives)

GCS has its own always-free tier, **separate from Cloud Run's**:

| GCS resource | Always-free quota | Our usage | Cost outside free tier |
|---|---|---|---|
| Standard storage | 5 GB-months | **0.007 GB** (7 MB corpus + 1 KB manifest) — 0.14 % of free | $0.020/GB-month → ~$0.00014 / mo |
| Class A operations (writes / lists) | 5,000 / month | **4** (weekly Job × 2 objects) — 0.08 % of free | $0.005 / 1k ops → fractions of a cent |
| Class B operations (reads / gets) | 50,000 / month | ~16,000 / mo at **1,000 active users, 1 manifest fetch + 0.25 corpus refresh per week** — 32 % of free | $0.0004 / 1k ops |
| Egress to internet | 100 GB / month (most destinations) | ~1.75 GB / mo at the same scale — 1.75 % of free | $0.12 / GB beyond free |

> **Why us-central1 matters here.** GCS's 5 GB-months free tier only
> applies to the three US single-region buckets (`us-central1`,
> `us-east1`, `us-west1`). Multi-region and non-US buckets are billed
> from byte one — at our scale that would still be cents-per-month, but
> sticking to `us-central1` keeps the entire setup at literally $0.

### 9.3 What it would take to get a non-trivial bill

| Limit | Our distance from it |
|---|---|
| Free Cloud Run vCPU exhausted | The Job would need to run >24 h/mo, which it physically cannot (60-min task timeout × 4 runs = 4 h max). |
| Free GCS storage exhausted | We'd need to keep ~700 historical corpus versions (5 GB / 7 MB). |
| Free GCS reads exhausted | ~3,100 active users *all* refreshing the manifest *daily*. |
| Free GCS egress exhausted | ~57,000 corpus refresh downloads/mo (e.g. ~14,000 active users refreshing weekly). |

**At 1,000 active users worldwide refreshing weekly the bill rounds to $0.** **Structurally bounded** — there is no realistic SpotyVibe usage pattern that escapes the free tier from this Cloud Run setup.

---

## 10. Optional: alerting on failed runs

Cloud Run does not email you on Job failure by default. Add a simple
Cloud Logging alert:

```bash
gcloud alpha monitoring policies create \
  --policy-from-file=- <<'YAML'
displayName: "spotivibe-rag-builder failed"
combiner: OR
conditions:
  - displayName: "Job execution failed"
    conditionMatchedLog:
      filter: |
        resource.type="cloud_run_job"
        resource.labels.job_name="spotivibe-rag-builder"
        severity>=ERROR
notificationChannels:
  # Replace with your notification channel ID (set up first under
  # Console → Monitoring → Alerting → Notification channels).
  - projects/PROJECT_ID/notificationChannels/CHANNEL_ID
YAML
```

Or skip this entirely and just check the Cloud Run console once a week — the
weekly cadence makes silent failures uninteresting (next week's run will
re-publish a fresh corpus).

---

## 11. Optional enhancements

Not required for v1, but worth knowing they exist:

| Enhancement | Why |
|---|---|
| **Object Versioning** on the bucket | Keeps the previous N corpus versions automatically — instant rollback. Costs storage for retained versions (~7 MB each). |
| **Custom domain** (e.g. `corpus.spotyvibe.app`) | Cleaner client-side URL than `storage.googleapis.com/...`. Requires DNS + a load balancer (no longer free — adds ~$18/mo). Skip unless you actually need branded URLs. |
| **Cloud CDN in front of the bucket** | Bucket already serves with global edge caching via the GCS frontend; explicit CDN only matters at very high traffic. Skip until needed. |
| **Multi-region bucket** | Doubles storage cost. Single-region with GCS edge caching is plenty for a 7 MB asset. Skip. |
| **Cloud Tasks** instead of Scheduler | Useful if you ever need to chain multiple post-build tasks (e.g. invalidate a CDN, ping a webhook). Overkill for a single-step pipeline. |

---

## 12. Migration / rollback plan

> **No manual seed needed.** The bucket starts empty; the first Job run
> populates it from the MusicBrainz dump from scratch. Steps 1–2 below
> *are* that first run — you trigger it manually purely so you can
> watch logs the first time, then the cron takes over.

Going live:

1. **Stand up infrastructure** (§ 3 – § 6) — bucket, Job, Scheduler.
2. **Trigger the Job once manually** to seed the bucket and verify the pipeline end-to-end:
   ```bash
   gcloud run jobs execute spotivibe-rag-builder --region=$REGION --wait
   gcloud storage ls gs://$BUCKET   # → artists.jsonl.gz + manifest.json
   ```
3. **Smoke-test from a client** by pointing your local SpotyVibe at the new URL:
   ```bash
   export RAG_MANIFEST_URL=https://storage.googleapis.com/spotyvibe-rag-corpus/manifest.json
   python app.py
   ```
   Open the app, confirm Settings → Candidate pool shows "current" and a generation run uses the new corpus.
4. **Optional — dual-publish for 1–2 weeks** (only if you want a safety net): keep running `publish_rag_corpus.py` on the GitHub Releases path in parallel. The existing default `RAG_MANIFEST_URL` still points at GitHub so users see no change. Skip this step if the smoke test in (3) was clean — Cloud Run is producing the same file the manual script would.
5. **Flip the default** in `config.py` and cut a SpotyVibe release:
   ```python
   RAG_MANIFEST_URL = os.environ.get(
       "RAG_MANIFEST_URL",
       "https://storage.googleapis.com/spotyvibe-rag-corpus/manifest.json",
   )
   ```
6. **Stop running `publish_rag_corpus.py` manually.** The Cloud Run cron now owns the build.

Rolling back:

- **One client**: unset / override `RAG_MANIFEST_URL`. Done.
- **All clients**: revert the `config.py` default and ship a patch release. The GitHub Releases path is left alive as a permanent fallback for any clients still pinning the old URL — keep one manual `publish_rag_corpus.py` run from the most recent dump as the "frozen fallback" before fully decommissioning the GitHub path.

---

## 13. What this setup does NOT do

To keep the scope honest:

- **No LLM hosting.** Suggestions still go to OpenAI (or whatever the user's `LLM_BASE_URL` points at). Self-hosting a smaller open-weight model on Cloud Run GPU was rejected: cost-comparable but quality gap vs GPT-4-class is the disqualifier (see `documentation/TechnicalManual.md` § RAG limitations).
- **No remote retrieval / no RAG-as-a-service.** This setup just makes the corpus *file* easier to publish. The TF-IDF scoring still runs locally on the user's machine via `core/src/rag/retrieval.py`. A future Scenario C.2 (remote `POST /api/rag/score_artists`) would need a Cloud Run **Service** alongside this Job — see `result-improvement.md` § CF-Rat-6.
- **No user accounts / no auth.** Bucket is public read. If you need per-user quota, switch to signed URLs and a Cloud Run Service that mints them — out of scope here.
- **No write-back from clients.** Eval-log shipping (`spotyvibe_with_rag/eval.jsonl` etc.) is not implemented in this setup. The bucket explicitly does not grant write to anyone except the builder SA.
















---
## 9. Phase B — Last.fm enrichment (tags + listeners + top_tracks)
**Status (2026-05-16):** active. The previous Phase 2 (Spotify-based artist enrichment) was **retired** because Spotify's Development-Mode quota caps an app at ~1000 calls/day — structurally incompatible with bulk enrichment of ~174K artists. Top-tracks are now sourced from Last.fm instead.

### 9.1 What enrichment does
For each artist with an MBID, the job invokes `run_lastfm_enrichment.py` which makes three Last.fm API calls:
1. `artist.getInfo` → listener + playcount counts.
2. `artist.getTopTags` → up to 100 weighted tags (0-100), filtered to weight ≥ 30.
3. `artist.getTopTracks` → playcount-ranked track titles (top 5 by default).

Result fields added to each enriched row:
- `lastfm_listeners` (int)
- `lastfm_playcount` (int)
- `lastfm_tags` (list of `[name, weight]`)
- `top_tracks` (list of track titles, ranked by Last.fm playcount)

Last.fm coverage is excellent for mainstream Western artists and acceptable for non-Western/niche. Unmatched rows are emitted unchanged.

### 9.2 Credentials
You need a Last.fm API key from <https://www.last.fm/api/account/create>. Store in Secret Manager:
```bash
printf '%s' '<your-lastfm-key>' | gcloud secrets create lastfm-api-key --data-file=- --replication-policy=automatic
SA="spotivibe-rag-builder@$(gcloud config get-value project).iam.gserviceaccount.com"
gcloud secrets add-iam-policy-binding lastfm-api-key \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
```
Bind to the Job:
```bash
gcloud run jobs update spotivibe-rag-builder --region=us-central1 \
  --update-secrets=LASTFM_API_KEY=lastfm-api-key:latest
```
Disable temporarily: `DISABLE_LASTFM_ENRICHMENT=1` env var (passthrough — MB-only corpus).

### 9.3 Throughput
~3 API calls per artist at ~5.5 req/s. A full pass over ~176K artists is ~17 h, run as a self-chaining batched workflow (`BATCH_SIZE` artists/execution; progress in `build-state.json`; results accumulated in `gs://<bucket>/lastfm-checkpoint.jsonl`). Checkpoint+resume is built in, so a mid-run timeout / crash resumes cleanly.

### 9.4 Incremental seeding (2026-05-30)
A new cycle no longer re-fetches every artist. After the Phase-1 MB build, `cloud_run_publish.py` calls `merge_corpus.py` to **carry the previously-published corpus's Last.fm layer forward** onto the fresh MB build (matched by `mbid`) and writes the result as the seed `lastfm-checkpoint.jsonl`. Phase B's existing skip-set then skips every carried-forward artist and fetches **only the delta** — new mbids plus any still lacking Last.fm data. First production run (2026-05-30): of 176,560 artists, **146,493 were carried forward** and only **30,067** needed fetching (~17 %), turning a ~17 h pass into ~4–5 h. The Last.fm, MusicBrainz, and (local, manual) AI layers each own their own fields, so an update to one never clobbers the others. On a first-ever build (no previous corpus on GCS) the job falls back to a full enrichment pass. See `core/tests/test_merge_corpus.py` for the merge contract.
---
## 10. Circuit breaker & auto-retry (2026-04)
### 10.1 Why this exists
### 10.2 How it works

| Component | Behaviour |
|---|---|
| **Cloud Scheduler** | Triggers the Job **every 2 hours** (cron `0 */2 * * *`, Europe/Vienna). |
| **Job startup** | Reads `gs://spotivibe-rag-corpus/halt.flag`. If absent or expired → proceed. If present and active → exit 0 immediately. |
| **Soft halt (auto-expiring)** | Halt-flag JSON includes `"expires_at": "<ISO-8601 UTC>"`. Once the timestamp is in the past, the job **auto-deletes the flag and proceeds**. Used to wait out known temp-ban windows without manual intervention. |
| **Hard halt (manual reset)** | Halt-flag JSON has no `expires_at`. **Always active** until the user manually deletes the flag. Set automatically by the rate-limit catcher because an unexpected rate-limit means something is structurally wrong (creds, throttle config, Spotify policy change) — silently retrying could trigger another multi-hour temp-ban. |
| **Recent-build skip** | If `manifest.json` shows a successful build < `MIN_REBUILD_DAYS` days old, exits 0. Preserves weekly cadence on the cron path. **⚠ Trap:** the execution shows as "succeeded" in `gcloud run jobs executions list` even though nothing ran. Always pass `FORCE_REBUILD=1` on manual triggers (the helper scripts under `build-tools/cloud-run-job/` do this automatically — only catch the trap if you `gcloud run jobs execute` by hand). The skip line in the log is now `⏭ ⏭ ⏭ SKIPPING: published build is < N days old. This execution did NO work.` |
| **Enrichment step** | Last.fm uses 180 ms throttle (~5.5 req/s); has separate retry-budget + smoke pre-flight. Cumulative-backoff abort > 300 s. |
| **On rate-limit** | Last.fm enricher exits 43 (Spotify exit code 42 retained for the user-facing app's verify path); publisher writes a **hard** `halt.flag` to GCS and exits non-zero. **No partial corpus is uploaded** — the existing GCS corpus stays intact. |
### 10.3 Manual operations

| Action | Command |
|---|---|
| **Inspect halt flag** | `gcloud storage cat gs://spotivibe-rag-corpus/halt.flag` |
| **Resume after a halt (hard or soft)** | `gcloud storage rm gs://spotivibe-rag-corpus/halt.flag` |
| **Seed a soft halt** (auto-clears after `expires_at`) | See snippet in §10.3.1 below |
| **Force a rebuild** (bypasses both checks) | `gcloud run jobs execute spotivibe-rag-builder --region=us-central1 --update-env-vars=FORCE_REBUILD=1 --wait` |
| **Disable Last.fm enrichment temporarily** | `gcloud run jobs update spotivibe-rag-builder --region=us-central1 --update-env-vars=DISABLE_LASTFM_ENRICHMENT=1` |
| **Re-enable Last.fm enrichment** | `gcloud run jobs update spotivibe-rag-builder --region=us-central1 --remove-env-vars=DISABLE_LASTFM_ENRICHMENT` |
| **Pause scheduler entirely** | `gcloud scheduler jobs pause spotivibe-rag-weekly --location=us-central1` |
| **Resume scheduler** | `gcloud scheduler jobs resume spotivibe-rag-weekly --location=us-central1` |

#### 10.3.1 Seeding a soft (auto-expiring) halt

When you want the job to wait out a known temp-ban window without
remembering to manually re-enable it, write a halt flag with an
``expires_at`` timestamp. Adjust the date to a few hours past the
expected ban lift:

```bash
cat > /tmp/halt.json << 'EOF'
{
  "halted_at": "2026-04-23T10:00:00Z",
  "expires_at": "2026-04-24T11:30:00Z",
  "reason": "spotify_temp_ban_active",
  "detail": "Auto-expires; job will resume on the next scheduler tick after expires_at."
}
EOF
gcloud storage cp /tmp/halt.json gs://spotivibe-rag-corpus/halt.flag \
  --cache-control='no-cache, max-age=0' --content-type='application/json'
```

The next 2-h scheduler tick **after** `expires_at` will see that the
timestamp is in the past, auto-delete the flag, and proceed with a real
build. No manual action required.
### 10.4 What happens during a temp-ban
1. **Now (during ban):** halt.flag is set → the every-2h scheduler triggers the job, the job sees the flag and exits cleanly. No Spotify API calls. Cloud Run cost: <1 second per attempt.
2. **After ban lifts (≥24h later):** you delete the halt flag manually. The next 2h scheduler tick triggers a real run.
3. **If rate-limited again:** halt flag is auto-set, run fails (visible in Cloud Run logs as a failed execution), all subsequent scheduler ticks skip until you resume.
### 10.5 Tuning knobs
All are env vars on the Cloud Run job (set via `gcloud run jobs update ... --update-env-vars=KEY=value`):
| Var | Default | Effect |
|---|---|---|
| `MIN_REBUILD_DAYS` | `6` | Skip if last build is younger than this. |
| `FORCE_REBUILD` | unset | If `1`, ignore both halt flag and recent-build skip. |
| `DISABLE_LASTFM_ENRICHMENT` | unset | If `1`, build MB-only corpus (no `top_tracks` / `lastfm_*` fields). |
| `CORPUS_TOP_N` | `500000` | MB filter cap. Actual yield ~170-180K. |
| `LASTFM_MAX_ENRICH` | unset | Cap on Last.fm lookups. Empty = enrich all matched rows. |
The Last.fm throttle (`_MIN_INTER_REQUEST_SEC = 0.18`) is in `build-tools/rag/lastfm_enrichment/client.py`; per-artist call count + top-tracks limit are tuned via the `--top-tracks-per-artist N` flag (default 5) in `build-tools/rag/run_lastfm_enrichment.py`.
