# Cloud Run × SpotyVibe — Synergy & Cost Analysis

**Date:** 2026-04-21
**Source domain:** `cloud.run` → redirects to `cloud.google.com/run/` (it *is* Google Cloud Run)
**Scope:** Evaluate whether Cloud Run could host (a) the Flask backend, (b) a self-hosted LLM, or (c) auxiliary backend services for SpotyVibe, and what that would cost.

---

## 1. TL;DR

- Cloud Run is an excellent technical fit for the Flask backend — Python/Flask is a first-class deployment target, scale-to-zero is native, WebSockets work, and the always-free tier likely covers the entire current user base at zero cost.
- **Hosting an LLM on Cloud Run is technically supported (NVIDIA L4 GPU) but has no free tier for GPUs.** At SpotyVibe's current volume it would cost a few dollars a month, BUT it would **downgrade recommendation quality** (Gemma/Llama 4-bit ≪ GPT-4 for creative/nuanced music reasoning) and introduce **15–30 s cold starts** on sporadic use. Not recommended as a drop-in replacement for OpenAI.
- The strongest synergy is **optional** cloud-hosted deployment (reduces user install friction) and **backend microservices** (RAG retrieval endpoint, Spotify artist cache) — both comfortably inside the free tier at current scale.
- **Android becomes viable again if (and only if) RAG moves server-side.** The original blocker was shipping CPython (via Chaquopy) + the 7 MB corpus + corpus update flow onto mobile — commit `a21c87b` (2026-04-19). A Cloud Run RAG endpoint eliminates all three and reduces the Android app to a thin native client. **But revisiting Android is still a significant rewrite**, not a free upgrade — Kotlin code was fully deleted, and the Flask app currently serves HTML, not JSON.
- **The free tier is "always free"**, not a trial that expires. It resets monthly.

---

## 2. What Cloud Run is

Fully-managed serverless container platform. You push a container (or point it at source) and it runs on demand, auto-scaling from 0 → N instances.

Relevant capabilities for SpotyVibe:

| Capability | Detail |
|---|---|
| Languages | Python/Flask via source-based deploy (auto-builds container) |
| Scale-to-zero | Native — no charge when idle (except min-instance config) |
| Cold start | ~Sub-second for CPU, 5 s + model load for GPU |
| Request timeout | Default 5 min, max **60 min** (sufficient for GPT calls, RAG lookups) |
| Streaming | HTTP chunked encoding supported; each chunk resets client timeout |
| WebSockets | Supported |
| GPU | **NVIDIA L4 (24 GB VRAM)** and NVIDIA RTX Pro 6000; 1 GPU per instance; 5 s startup |
| Regions | 23 Tier-1 regions (standard price), 23 Tier-2 regions (+20%) |
| OAuth / custom domains | Supported (helpful for Spotify redirect URI) |

---

## 3. Free tier (always free, monthly, per billing account)

### Services — request-based billing (typical Flask backend mode)

| Resource | Free per month | Interpretation |
|---|---|---|
| CPU | 180,000 vCPU-seconds | 50 hours of 1 vCPU running |
| Memory | 360,000 GiB-seconds | 100 hours of 1 GiB running |
| Requests | 2,000,000 | — |
| Egress | 1 GiB/month (North America) | — |

### Services — instance-based billing

| Resource | Free per month |
|---|---|
| CPU | 240,000 vCPU-seconds |
| Memory | 450,000 GiB-seconds |

### Jobs & Worker Pools

Jobs: 240k vCPU-sec, 450k GiB-sec.
Worker Pools: 384k vCPU-sec, 728k GiB-sec.

### ⚠ No free tier for GPUs

Every GPU-second is billed from the first second.

---

## 4. Paid pricing (Tier-1 regions, e.g. `us-central1`, `europe-west1`)

### CPU / memory / requests

| Mode | vCPU-sec | GiB-sec | Requests |
|---|---|---|---|
| Request-based (active) | $0.000024 | $0.0000025 | $0.40 / 1 M |
| Request-based (idle, min-instances) | $0.0000025 | $0.0000025 | — |
| Instance-based | $0.000018 | $0.000002 | — |

### GPU (per second)

| GPU | Without zonal redundancy | With zonal redundancy |
|---|---|---|
| NVIDIA L4 | **$0.0001867** (~$0.672/h, $484/mo if always on) | $0.0002909 (~$1.047/h) |
| NVIDIA RTX Pro 6000 | $0.00036522 (~$1.315/h) | $0.00056913 (~$2.049/h) |

### Official pricing examples from Google

| Workload | Config | $/month |
|---|---|---|
| Public API / website | 10 M req, 1 vCPU, 512 MiB | $13.69 |
| Serverless function | 10 M req, 0.167 vCPU, 256 MiB | $7.25 |
| Batch job | 1 hr/month, 1 vCPU, 512 MiB | **$0.00** (in free tier) |
| AI inference (GPU) | 4 vCPU, 16 GiB, L4, 2 peak instances | $822.40 |

---

## 5. Synergy scenarios for SpotyVibe

### Scenario A — Host the Flask backend as an optional hosted service

**What it looks like:** Package [app.py](app.py) + core/ into a container, deploy to Cloud Run. Users hit `https://spotyvibe.example.com` instead of installing the EXE/wheel. OAuth redirect URI points at the hosted URL.

**Pros**
- Removes install friction — no EXE download, no Python runtime, works on tablets/Chromebooks.
- Scale-to-zero: idle users cost literally $0.
- Rolling updates are instant for everyone.

**Cons / blockers**
- **Multi-tenancy rewrite required.** Today the app assumes one user per process: [config.py](config.py), `.credentials`, `.spotify-cache`, `personalized_music_profile.json` are all on the local filesystem. A hosted version must move per-user state to a DB (Firestore, Postgres via Cloud SQL) and scope it by Spotify user ID.
- **OpenAI key management.** Either (a) each user brings their own key (current model — works, but the whole point of hosting is to reduce user overhead) or (b) you pay for all users' OpenAI calls (cost goes up linearly with adoption — could be unbounded).
- **Spotify OAuth redirect URI** must be registered for the public domain; users still authenticate to their own Spotify account.
- **Premium-only constraint still applies** (see `SKILL.md` § "Development Mode restrictions").

**Cost estimate — 10 active users, ~50 requests each / month**
- ~500 requests/mo → **1500x under the free request limit**.
- Average request 3 s at 1 vCPU / 512 MiB → 1500 vCPU-sec, 750 GiB-sec → **inside free tier**.
- **Expected monthly bill: $0**, unless you add a min-instance (eliminates cold starts but costs ~$9/mo for `min_instances=1` on 0.167 vCPU/256 MiB).
- Database (Firestore free tier: 1 GiB storage, 50k reads/day) also free at this scale.

**Verdict:** Technically clean, financially trivial, but **requires non-trivial multi-tenancy refactor**. Worth doing only if you plan to distribute SpotyVibe beyond self-installers.

---

### Scenario B — Self-host an LLM on Cloud Run to replace OpenAI

**What it looks like:** Deploy Ollama + Gemma 9b / Llama 3 8b on a Cloud Run service with an L4 GPU. Point [core/src/openai_http.py](core/src/openai_http.py) at the new endpoint (OpenAI-compatible APIs exist for Ollama).

**Pros**
- Fixed per-second GPU cost instead of per-token OpenAI cost — potentially cheaper at high volume.
- Data stays in your GCP project.
- No dependency on OpenAI rate limits / outages.

**Cons**
- **Quality gap.** SpotyVibe's recommendation prompts ([prompts/*.txt](prompts/)) are creative/nuanced. 4-bit Gemma 9b / Llama 8b produce noticeably worse music suggestions than GPT-4-class models. This is the dominant concern — cost is secondary if the product gets worse.
- **Cold starts of 15–30 s** loading the model into VRAM on first request after idle ([source](https://cloud.google.com/blog/products/application-development/run-your-ai-inference-applications-on-cloud-run-with-nvidia-gpus/)). For sporadic single-user use, nearly every request hits a cold start.
- **No GPU free tier** — every second billed.
- **Only L4 and RTX Pro 6000 available** — no A100/H100, so large frontier models (Llama 70B full-precision, etc.) aren't an option on Cloud Run today.
- Region availability: L4 primarily in `us-central1`, `europe-west4`, `asia-southeast1`.

**Cost math — Scenario B at current scale (~500 LLM calls/month)**

Assume each request = 25 s GPU-active (including cold-start amortized):

| Component | Calculation | $/mo |
|---|---|---|
| L4 GPU (no redundancy) | 500 × 25 s × $0.0001867 | $2.33 |
| CPU (8 vCPU while GPU active) | 500 × 25 × 8 × $0.000024 | $2.40 |
| Memory (32 GiB while active) | 500 × 25 × 32 × $0.0000025 | $1.00 |
| **Total** | | **~$5.73** |

**Comparison — OpenAI GPT-4o-class usage at same volume**

500 requests × ~(2000 in + 500 out) tokens ≈ $5–10/month with GPT-4o, much less with GPT-4o-mini.

**Verdict:** Costs are comparable at this scale. **The quality gap is the disqualifier**, not the money. Consider this only if: (a) you hit OpenAI cost pain at 10–100× today's volume, (b) an open model at that future date matches GPT-4 quality for creative prompts, or (c) you need data residency / offline sovereignty that OpenAI can't provide.

---

### Scenario C — Cloud Run as a backend service layer (best synergy)

Even if Scenario A/B don't happen, Cloud Run is a natural fit for **optional auxiliary services** that reduce per-user overhead without requiring a full migration:

1. **Spotify artist metadata cache.** Many users look up the same popular artists. A shared Cloud Run + Firestore cache removes duplicate Spotify API calls and speeds up [core/src/analysis.py](core/src/analysis.py). **Free tier covers this easily.**
2. **RAG retrieval endpoint.** Recent commits (`77e17ea`, `5528818`, `61e02b0`) added RAG. Today the corpus ships as a ~7 MB gzipped asset pulled from GitHub Releases ([core/src/rag/distribution.py](core/src/rag/distribution.py)) and the TF-IDF scoring runs locally ([core/src/rag/retrieval.py](core/src/rag/retrieval.py)). Moving this to Cloud Run removes the local download, keeps the corpus centrally fresh, and scales to zero between queries.
3. **Batch/nightly jobs.** Cloud Run Jobs (up to 24-hour runs, 240k vCPU-sec free/mo) for periodic tasks like rebuilding the RAG corpus ([build-tools/build_rag_corpus.py](build-tools/build_rag_corpus.py)) and publishing the artifact.
4. **Telemetry/eval collection.** The eval logging work in `5528818` could ship to a lightweight Cloud Run endpoint + BigQuery rather than being local-only.

**Estimated cost for all four at current scale: $0/mo** (everything fits the free tier).

#### 5.C.1 — Concrete design: RAG retrieval as a Cloud Run service

**Surface:** one POST endpoint, e.g. `POST /api/rag/score_artists`, mirroring the existing [score_artists](core/src/rag/retrieval.py#L118) signature:

```json
// Request
{
  "profile": { ...profile JSON... },
  "primary_reference": { ...optional... },
  "deny_keys": ["artist-a-normalised", "artist-b-normalised"],
  "pool_size": 20,
  "popularity_penalty": 0.4,
  "corpus_version": "2026-04-19"   // optional pin; server chooses latest if absent
}
// Response
{
  "corpus_version": "2026-04-19",
  "artists": [ { "name": "...", "tags": [...], "listener_popularity": 0.3, ... } ]
}
```

**Container:** copy `core/src/rag/` as-is into the service, plus a tiny Flask/FastAPI wrapper. No ML deps, no GPU — pure TF-IDF over an in-memory corpus. The existing pure-Python retrieval is already embarrassingly well-suited to a stateless serverless endpoint.

**Corpus storage:** keep publishing `artists.jsonl.gz` via [publish_rag_corpus.py](build-tools/publish_rag_corpus.py), but read it from a Google Cloud Storage bucket on container start. Rebuilds become a one-click Cloud Run Job invocation.

**Memory / CPU:** 1 vCPU + 512 MiB is plenty for today's corpus. Budget 30–60 MiB for the parsed in-memory index.

**Caching:** set `min_instances=0` to stay scale-to-zero. First request after idle pays a cold start (~1–2 s to unzip + parse the corpus); warm requests are sub-100 ms. If cold start becomes user-visible, bump to `min_instances=1` (~$2/mo at 0.167 vCPU/256 MiB).

**Client-side change in [core/src/suggestions.py](core/src/suggestions.py):** inject a "RagBackend" abstraction with two implementations — `LocalRag` (today) and `RemoteRag` (HTTP). Keeps desktop EXE/wheel fully offline-capable while letting the hosted/mobile variant call the service. This is a small, contained refactor.

**Cost at 50 users × 200 RAG calls/month = 10,000 calls:**
- CPU: 10,000 × 0.2 s × 1 vCPU ≈ 2,000 vCPU-sec → free
- Memory: 10,000 × 0.2 × 0.5 GiB ≈ 1,000 GiB-sec → free
- Requests: 10,000 → free (2 M free)
- GCS egress (50 MB of JSON responses): free (<1 GiB/mo)
- **Total: $0/mo.** Stays free until ~100× this volume.

---

### Scenario D — Android APK, revisited (the motivating question)

Android was dropped in [`a21c87b` "Drop Android support"](https://github.com/mikgra91/spotyvibe/commit/a21c87b) (2026-04-19) because the mobile experience depended on Chaquopy to run the full Python stack on-device, and RAG pushed that model past breaking point: the corpus file had to be bundled or downloaded, kept in sync, and parsed in Python on a phone. A Cloud Run RAG endpoint changes the shape of the problem — RAG stops being a mobile problem at all. Does that make Android viable again?

**What the original blocker actually was** (reconstructed from the drop commit):
- Chaquopy bundled CPython + site-packages into the APK → large install, slow cold start, fragile upgrades.
- RAG added a 7 MB corpus + `.meta.json` sidecar + an update-check flow that had to run inside the Python layer on Android.
- Authentication used a custom `spotyvibe://callback` scheme just for Android.

**What the Cloud Run architecture makes possible**

| Former dependency | Replacement if RAG is remote |
|---|---|
| Chaquopy CPython runtime | None — APK is native Kotlin/Compose |
| 7 MB corpus on device | Server-side, no download |
| Corpus version check + update download flow | Server picks latest version; client is version-agnostic |
| Local TF-IDF scoring | `POST /api/rag/score_artists` |
| Local suggestion engine (OpenAI HTTP) | Either (a) native Kotlin OpenAI client with user's key, or (b) proxy via Cloud Run |
| Spotify OAuth via custom scheme | Standard Android App Links / PKCE flow against a public redirect URI |

**What Android-on-Cloud-Run would actually require**

1. **Re-extract a JSON API** from [app.py](app.py). Today [app.py](app.py) renders HTML templates; mobile needs structured JSON endpoints for: profile CRUD, suggestion pipeline (generate / refine / review), feedback (like/dislike/remove), playlist save, analysis. Most of the business logic in `core/src/` is already UI-agnostic — this is mostly route-level plumbing, but non-trivial.
2. **Rewrite the Android client.** The Kotlin/Compose UI deleted in `a21c87b` is gone. Rebuilding it is weeks of work — do not underestimate just because "the backend is easier now".
3. **Decide where Spotify and OpenAI clients live.** Three options:
   - *Direct-from-APK:* Android app holds the user's OpenAI key and Spotify tokens, calls both vendors directly. Cloud Run only serves RAG + corpus. **Simplest cost and privacy story.**
   - *Full proxy:* Cloud Run handles all vendor calls. Keys either stored server-side (you become a custodian) or passed per-request (awkward on mobile).
   - *Hybrid:* Spotify direct (mobile SDK exists), OpenAI via Cloud Run proxy for rate-limiting/eval-logging.
4. **Multi-tenant state.** If anything other than RAG moves server-side (profile, history, feedback), the single-user file-system assumption has to break. Same concern as Scenario A.
5. **Store distribution + review.** Google Play has its own overhead (closed testing track, privacy policy, data-safety form). If the user base is small, sideloaded APK releases via GitHub are still fine.

**Cost view at Android-plausible scale (50 users, ~500 sessions/mo each, ~3 RAG calls/session = 75,000 RAG calls/mo)**

- RAG endpoint: 75 k × 0.2 s × 1 vCPU = 15,000 vCPU-sec → free (free tier = 180k)
- Memory: 75 k × 0.2 × 0.5 GiB = 7,500 GiB-sec → free
- Requests: 75 k → free
- Outbound egress (~200 MB/mo): free
- **Still $0/mo.** Android at this scale does *not* push Cloud Run out of the free tier for a RAG-only backend.

**What genuinely improves for Android users vs. the prior Chaquopy approach**
- APK shrinks dramatically (no Python, no corpus, no site-packages) — tens of MB saved.
- App starts in sub-second instead of waiting for a Python interpreter to warm.
- Corpus updates are invisible and instant — user never sees a "new corpus available" modal.
- Crash surface shrinks (no Python-on-Android interop bugs).
- Play Store review is easier (native-only app, no unusual runtime).

**What does not improve**
- Battery / network cost per request goes up slightly (every suggestion now hits the network for retrieval).
- **Offline mode is lost** for RAG. Today's desktop path works fully offline after corpus install; an Android client calling Cloud Run does not.
- The user still needs a Premium Spotify account and an OpenAI key (unless you proxy).

**Verdict**

Cloud Run + remote RAG is **a necessary precondition, not a sufficient reason**, to reintroduce Android. The corpus/Python problem is genuinely solved. But the Android work itself (Kotlin UI, JSON API extraction, OAuth flow re-implementation, Play Store overhead) is the same scope it always was — and that's what got cut in `a21c87b`. Recommend only if the hosted backend is already being built for desktop/web reasons and Android can piggyback on the same JSON API surface.

---

## 6. Recommendations

In order of value vs. effort:

1. **Highest ROI — Scenario C.2 (RAG retrieval endpoint).** Small, contained refactor: wrap the existing [core/src/rag/retrieval.py](core/src/rag/retrieval.py) in a Flask/FastAPI route, deploy to Cloud Run, and introduce a `RagBackend` abstraction with local + remote implementations. Desktop stays offline-capable; the hosted/mobile variant uses the remote backend. $0/mo at current scale. **Do this first.**
2. **Also high ROI — Scenario C.1 (Spotify artist cache).** Shared cache cuts Spotify API calls and latency. Stays inside the free tier. Pairs naturally with the RAG service.
3. **Android (Scenario D) — revisit only after C.2 exists.** The RAG endpoint removes the *technical* blocker that killed Android in `a21c87b`, but the client rewrite is still weeks of work. Do it only if you also want a hosted web/mobile-friendly variant (Scenario A) — then Android piggybacks on the same JSON API. Don't rewrite the Android app just because RAG moved to the cloud.
4. **Medium ROI — Scenario A (hosted multi-tenant backend).** Makes sense if you want broad distribution (web + Android). Requires breaking the single-user-filesystem assumption in [config.py](config.py), `.credentials`, and `personalized_music_profile.json`.
5. **Low ROI today — Scenario B (self-hosted LLM).** Revisit only when an open model demonstrably matches GPT-4-class quality on music-recommendation prompts, or when OpenAI spend becomes material. For now, OpenAI via [core/src/openai_http.py](core/src/openai_http.py) is the right choice.

**Suggested order of execution (if all are pursued):**
`C.2 (RAG endpoint)` → `C.1 (Spotify cache)` → `A (multi-tenant backend)` → `D (Android client)`. Each step is independently useful and de-risks the next.

**Do not do:**
- Deploy a min-instance GPU service "just in case" — that's ~$484/mo burning while idle.
- Put the LLM behind a 5-minute default timeout without streaming; reasoning prompts can blow past it.
- Use a Tier-2 region (+20% cost) unless latency to a specific geography demands it.
- Rebuild the Android client before the JSON API and RAG endpoint exist. The 2026-04-19 removal wasn't wasted effort — it removed dead code the team wasn't going to maintain. Only reintroduce when the backend makes it cheap.

---

## 7. Quick-reference cost card

| Question | Answer |
|---|---|
| Is the free tier time-limited? | **No.** It's always-free and resets monthly. |
| What does the Flask backend cost at 10 users / ~500 req/mo? | **$0** (well within free tier) |
| What does Cloud Run cost if the app is idle all month? | **$0** (scale-to-zero, no min-instance) |
| What does the RAG endpoint cost at 75 k calls/mo (Android-scale)? | **$0** (inside free tier) |
| What does an L4 GPU cost 24/7? | ~**$484/mo** (no zonal redundancy) |
| What does an L4 GPU cost for 500 × 25 s inference/mo? | ~**$2.33** GPU + ~$3.40 CPU/RAM = **~$6/mo** |
| Max request timeout? | **60 min** (default 5 min) |
| Max instance size? | 8 vCPU, 32 GiB RAM, 1 GPU |
| Egress free? | First 1 GiB/mo North America only |
| Does remote RAG unblock Android? | **Technically yes, practically partially** — removes the Python-on-mobile and corpus-on-device blockers, but the Kotlin client rewrite is still weeks of work |

---

## 8. Sources

- [Google Cloud Run overview](https://cloud.google.com/run/)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Run your AI inference applications on Cloud Run with NVIDIA GPUs (Google Cloud blog)](https://cloud.google.com/blog/products/application-development/run-your-ai-inference-applications-on-cloud-run-with-nvidia-gpus/)
- [Run LLM inference on GPUs with Gemma and Ollama (Cloud Run tutorial)](https://docs.cloud.google.com/run/docs/tutorials/gpu-gemma-with-ollama)
- [Configure request timeout for services](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Cloud Run quotas and limits](https://docs.cloud.google.com/run/quotas)
- [Google Cloud Run Free Tier (freetiers.com)](https://www.freetiers.com/directory/google-cloud-run)
- [Ollama cloud pricing](https://ollama.com/pricing)
