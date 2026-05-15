# Cloud Run — operator's guide

Single reference for the GCP-side build/enrich pipeline that produces the public RAG corpus consumed by every SpotyVibe install.

> **Read this first when anything in cloud breaks.** The two Cloud Run Jobs share a bucket and a circuit-breaker; getting the mental model right saves time.

---

## 1. Architecture at a glance

```
                  ┌────────────────────────────┐
                  │  spotivibe-rag-builder     │  scheduled (cron)
                  │  (job: legacy, MB-only)    │
                  │                            │
                  │  Phase 1: MusicBrainz dump │
                  │     → 175k-artist corpus   │
                  │  Phase 2: SKIPPED          │  ← DISABLE_SPOTIFY_ENRICHMENT=1
                  │  Phase B: Last.fm enrich   │
                  │  Phase 3: Upload to GCS    │
                  └──────────┬─────────────────┘
                             │
                             ▼
                  gs://spotivibe-rag-corpus/
                    ├─ artists.jsonl.gz       ← public corpus
                    ├─ manifest.json          ← version + sha256
                    ├─ halt.flag              ← circuit breaker (when present)
                    ├─ top-tracks-checkpoint  ← resumable enrichment state
                    └─ lastfm-checkpoint.*    ← resumable Last.fm state
                             ▲
                             │ download → enrich → re-upload
                             │
                  ┌──────────┴─────────────────┐
                  │  spotivibe-rag-enricher    │  manual trigger
                  │  (job: top-tracks split)   │
                  │                            │
                  │  1. Download corpus        │
                  │  2. Add `top_tracks` field │
                  │     via Spotify search     │
                  │  3. Re-upload corpus       │
                  └────────────────────────────┘
```

**Why two jobs?** The MB build takes ~30 min and has no rate-limit risk. The Spotify enrichment takes ~85 min and CAN hit the daily quota. Splitting them means a rate-limit kills only the enricher — the MB-only corpus stays usable and the enricher resumes from its GCS checkpoint on the next run. Before this split, a rate-limit at minute 90 wasted minute 0-30 of MB work too.

---

## 2. The two jobs in detail

### 2a. `spotivibe-rag-builder` — MusicBrainz + Last.fm pass

- **Region:** `us-central1`
- **Image:** built from `build-tools/cloud-run-job/Dockerfile`
- **Entrypoint:** `python build-tools/cloud_run_publish.py`
- **Schedule:** cron-driven (legacy — review with `gcloud scheduler jobs list`).
- **What it does:** Downloads the latest MusicBrainz dump, builds a top-N artist corpus, attaches Last.fm tags, uploads `artists.jsonl.gz` + `manifest.json` to GCS.

#### Env vars (legacy job)

| Var | Default | Effect |
|---|---|---|
| `GCS_BUCKET` | `spotivibe-rag-corpus` | Destination bucket. |
| `CORPUS_TOP_N` | `350000` | Max artists retained from MB dump (sorted by proxy popularity). |
| `KEEP_INTERMEDIATES` | unset | `1` retains the `.rag-cache/mb/<date>/` MB extract between runs. |
| `MIN_REBUILD_DAYS` | `25` | Skip the run if `manifest.built_at` is younger than this. **Set 0 to force.** |
| `FORCE_REBUILD` | unset | `1` ignores both halt.flag and `MIN_REBUILD_DAYS`. |
| `DISABLE_SPOTIFY_ENRICHMENT` | **`1`** (after split) | `1` skips Phase 2 entirely. Code path retained for emergency re-enable. |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | from Secret Manager | Required only if Phase 2 is re-enabled. |
| `SPOTIFY_MAX_ENRICH` | `50000` | Cap on Phase 2 lookups when re-enabled. Lower if hitting limits. |
| `LASTFM_API_KEY` | from Secret Manager | Required for Phase B. |
| `DISABLE_LASTFM_ENRICHMENT` | unset | `1` skips Phase B. Use during a Last.fm outage. |
| `LASTFM_MAX_ENRICH` | unset (≈170k) | Cap on Last.fm lookups. |

### 2b. `spotivibe-rag-enricher` — top-tracks-only Spotify enrichment

- **Region:** `us-central1`
- **Image:** built from `build-tools/cloud-run-enricher/Dockerfile`
- **Entrypoint:** `python build-tools/cloud_run_top_tracks.py`
- **Schedule:** none — manual trigger.
- **What it does:** Downloads the published corpus, adds `top_tracks: list[str]` per artist via Spotify search-by-name, re-uploads. Resumable via `top-tracks-checkpoint.json` in GCS.

**Why it's separate:**
1. The legacy job's Spotify enrichment also tried to refresh `genres` / `popularity` — both gutted by Spotify in Feb 2026 — so it ran two API calls per artist for one useful field. This job skips the artist-ID resolve pass; one call per artist, half the rate-limit pressure.
2. A rate-limit in the enricher only halts the enricher, not the MB build.

#### Env vars (enricher job)

| Var | Default | Effect |
|---|---|---|
| `GCS_BUCKET` | `spotivibe-rag-corpus` | Source + destination. |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | from Secret Manager | Required. Exits 2 if missing. |
| `TOP_TRACKS_PER_ARTIST` | `5` | Tracks per artist. More = better Stage-3 grounding, more API calls. |
| `TOP_TRACKS_LIMIT` | unset | Optional cap on artists to enrich. Empty = all. |
| `TOP_TRACKS_MIN_POPULARITY` | unset | Skip artists with `listener_popularity` below this (0..100). Use to focus budget on long-tail-safe range. |
| `FORCE_REBUILD` | unset | `1` ignores halt.flag. |
| `DISABLE_TOP_TRACKS` | unset | `1` exits 0 immediately. Kill-switch when something is wrong. |

---

## 3. The circuit breaker — `halt.flag`

A single GCS object guards **both** jobs: `gs://spotivibe-rag-corpus/halt.flag`.

### When it gets written

- `enrich_with_spotify.py` returns exit 42 (rate-limit) → legacy job writes a hard halt.
- `enrich_top_tracks.py` returns exit 42 → enricher job writes a hard halt.
- `enrich_with_lastfm.py` returns exit 43 (rate-limit) → legacy job writes a hard halt.

### How to inspect it

```bash
gcloud storage cat gs://spotivibe-rag-corpus/halt.flag
```

Contents look like:
```json
{
  "halted_at": "2026-05-15T11:16:06Z",
  "reason": "spotify_rate_limited",
  "detail": "...",
  "resume_with": "gcloud storage rm gs://spotivibe-rag-corpus/halt.flag"
}
```

### How to clear it

```bash
gcloud storage rm gs://spotivibe-rag-corpus/halt.flag
```

Then re-trigger the job. If you want to retry without waiting for the next cron, also set `FORCE_REBUILD=1` for one execution (env-var override on `gcloud run jobs execute --update-env-vars`).

### Hard vs soft halt

- **Hard halt** (no `expires_at` field) — written by rate-limit catchers. **Manual reset required.** This is intentional: a rate-limit means something is structurally wrong; silently retrying risks a multi-hour temp-ban.
- **Soft halt** (with `expires_at` ISO-8601 timestamp) — seeded externally to wait out a known window. Auto-clears once the timestamp is in the past.

---

## 4. The helper scripts — what each one does

All scripts live under `build-tools/`.

### `build-tools/cloud-run-job/redeploy_and_run.sh`

**Use when:** code changed in `cloud_run_publish.py` / `enrich_with_spotify.py` / `build_rag_corpus.py` / Last.fm enrichment.

Steps:
1. Confirms project + auth.
2. Shows halt.flag (if any), asks for `y`, deletes it.
3. `gcloud builds submit` against `cloud-run-job/cloudbuild.yaml`.
4. `gcloud run jobs update spotivibe-rag-builder --task-timeout=7200`.
5. `gcloud run jobs execute spotivibe-rag-builder --wait=false`.

Interactive — won't no-op silently.

### `build-tools/cloud-run-job/trigger_only.sh`

**Use when:** existing legacy image is fine, just want to fire a scheduled-style run manually.

Refuses if halt.flag is set. No build, no env changes. One execute.

### `build-tools/cloud-run-enricher/deploy.sh`

**Use when:** first-time enricher deploy, or after editing `enrich_top_tracks.py` / `cloud_run_top_tracks.py`.

Steps:
1. `gcloud builds submit` against `cloud-run-enricher/cloudbuild.yaml`.
2. `gcloud run jobs deploy spotivibe-rag-enricher …` — idempotent (creates or updates).
   - Sets `GCS_BUCKET`, `TOP_TRACKS_PER_ARTIST=5`.
   - Binds Spotify secrets from Secret Manager (`spotify-client-id`, `spotify-client-secret`).
   - `--task-timeout=7200`, `--memory=2Gi`, `--cpu=1`, `--max-retries=0`.
3. Flips `DISABLE_SPOTIFY_ENRICHMENT=1` on the legacy builder job (one-line state change, no rebuild).

### `build-tools/cloud-run-enricher/trigger.sh`

**Use when:** ready to refresh top_tracks on the published corpus.

Refuses if halt.flag is set. One execute. Print watch commands.

---

## 5. Common operations — copy-paste recipes

### Inspect current state

```bash
# Both jobs exist?
gcloud run jobs list --region us-central1

# Latest execution of each
gcloud run jobs executions list --job spotivibe-rag-builder  --region us-central1 --limit 3
gcloud run jobs executions list --job spotivibe-rag-enricher --region us-central1 --limit 3

# Published corpus metadata
gcloud storage cat gs://spotivibe-rag-corpus/manifest.json

# Halt flag set?
gcloud storage ls gs://spotivibe-rag-corpus/halt.flag
```

### Watch a run live

```bash
EXEC=$(gcloud run jobs executions list --job spotivibe-rag-enricher \
  --region us-central1 --limit 1 --format='value(name)')
gcloud logging read \
  "resource.type=cloud_run_job AND labels.\"run.googleapis.com/execution_name\"=$EXEC" \
  --format='value(timestamp,severity,textPayload)' --freshness=2h --order=asc
```

### Disable a job temporarily without deleting it

```bash
# Builder
gcloud run jobs update spotivibe-rag-builder --region us-central1 \
  --update-env-vars=FORCE_REBUILD=0,MIN_REBUILD_DAYS=9999

# Enricher
gcloud run jobs update spotivibe-rag-enricher --region us-central1 \
  --update-env-vars=DISABLE_TOP_TRACKS=1
```

Undo with the opposite value, or `--remove-env-vars=DISABLE_TOP_TRACKS`.

### Re-enable Phase 2 on the legacy builder (emergency only)

```bash
gcloud run jobs update spotivibe-rag-builder --region us-central1 \
  --update-env-vars=DISABLE_SPOTIFY_ENRICHMENT=0
```

This brings back the *old* dual-pass enrichment. Use only if the new enricher job is broken and you need a one-shot fix.

### Force a rebuild without waiting for cron

```bash
gcloud run jobs execute spotivibe-rag-builder --region us-central1 \
  --update-env-vars=FORCE_REBUILD=1 --wait=false
```

The override applies to that single execution.

### Inspect the resumable checkpoint

```bash
# Top-tracks enricher checkpoint (per-artist name → list of tracks)
gcloud storage cat gs://spotivibe-rag-corpus/top-tracks-checkpoint.json | head -c 500

# Last.fm enricher checkpoint (per-mbid → tags+listeners)
gcloud storage ls -l gs://spotivibe-rag-corpus/lastfm-checkpoint.jsonl.gz
```

---

## 6. Decision matrix — which script do I run?

| Situation | Run |
|---|---|
| You changed `enrich_with_spotify.py`, `cloud_run_publish.py`, `build_rag_corpus.py`, or Last.fm code | `build-tools/cloud-run-job/redeploy_and_run.sh` |
| You changed `enrich_top_tracks.py` or `cloud_run_top_tracks.py` | `build-tools/cloud-run-enricher/deploy.sh` |
| Legacy job image is fine, you just want to refresh the MB corpus now | `build-tools/cloud-run-job/trigger_only.sh` |
| Enricher image is fine, you want fresh top_tracks now | `build-tools/cloud-run-enricher/trigger.sh` |
| Spotify rate-limited and halt.flag is set | Wait for the published Retry-After window, then `gcloud storage rm gs://spotivibe-rag-corpus/halt.flag` and re-trigger |

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Job exits 0 immediately, log says `⏸ halt.flag is set` | Circuit breaker open. | Inspect halt.flag, fix underlying issue, delete the flag. |
| Job exits 0 immediately, log says `⏭ A successful build is < N days old` | `MIN_REBUILD_DAYS` guard tripped. | Use `--update-env-vars=FORCE_REBUILD=1` on the execute, or lower `MIN_REBUILD_DAYS`. |
| `ABORT: Spotify rate-limit detected` | Daily quota exhausted. | halt.flag is now set with `Retry-After` detail. Wait the published window, clear flag, re-trigger. The next run resumes from the checkpoint. |
| `ERROR: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET unset` | Secret binding broken. | Confirm secrets exist (`gcloud secrets list`) and match the kebab-case names in `deploy.sh`. |
| Build step succeeds in <60 s | Layer cache hit — normal after the first push. | No action. |
| `Permission denied on metadata server` | Cloud Run job lacks IAM. | Ensure the job's service account has `roles/storage.objectAdmin` on the bucket and `roles/secretmanager.secretAccessor` on the secrets. |
| Enricher runs but `top_tracks` field never appears in corpus | Either no Spotify hits (suspicious — check log for `0 with tracks`) or the upload step failed (check log for `Uploading enriched corpus`). | Re-run; checkpoint preserves prior work. |
| Job timed out after exactly 60 min | Old default. | Already raised to 2 h on both jobs via the deploy scripts. Re-deploy if a job was created before the change. |

---

## 8. Recovery flow after a rate-limit halt

1. Read the halt detail: `gcloud storage cat gs://spotivibe-rag-corpus/halt.flag`.
2. Note the `Retry-After` in the log of the failed execution. Wait at least that long — 24 h is the safe default if you're unsure.
3. Delete the halt flag: `gcloud storage rm gs://spotivibe-rag-corpus/halt.flag`.
4. Trigger the relevant job: `bash build-tools/cloud-run-enricher/trigger.sh` (or `cloud-run-job/trigger_only.sh`).
5. The enricher reads the prior checkpoint from GCS and skips already-fetched artists — no double-billing.

---

## 9. What lives where

```
build-tools/
├── build_rag_corpus.py                # Phase 1 MB builder
├── refresh_rag_corpus.py              # Phase 1 wrapper (download MB dump → build_rag_corpus)
├── enrich_with_spotify.py             # legacy dual-pass enricher (artist ID + top tracks)
├── enrich_with_lastfm.py              # Phase B Last.fm enricher
├── enrich_top_tracks.py               # NEW lean enricher (top tracks by artist name)
├── cloud_run_publish.py               # legacy job entrypoint
├── cloud_run_top_tracks.py            # enricher job entrypoint
├── build_top_tracks_overlay.py        # LOCAL-only diagnostic overlay builder
├── cloud-run-job/                     # legacy job deploy assets
│   ├── Dockerfile
│   ├── cloudbuild.yaml
│   ├── requirements.txt
│   ├── redeploy_and_run.sh
│   └── trigger_only.sh
└── cloud-run-enricher/                # NEW enricher job deploy assets
    ├── Dockerfile
    ├── cloudbuild.yaml
    ├── requirements.txt
    ├── deploy.sh
    └── trigger.sh
```
