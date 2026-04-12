# Wave 4 — Power users: custom LLM endpoints, cost estimator, voice input

> **Reader.** This document is written for Claude Sonnet 4.6 to implement. It assumes no memory of prior conversations. It is self-contained.
>
> **Prerequisites.** Waves 1, 2, 3 must be merged first. Wave 4 fulfils two deferred promises from earlier waves:
> - The **"Use a different provider…" link** added to onboarding step 6 in Wave 1 (but left inert).
> - The **"Cost estimate coming in a future update" placeholder** also added to onboarding step 6 in Wave 1.
>
> It also re-enables the Chip/Preset/Dashboard systems from Waves 2–3 to work against non-OpenAI providers without knowing anything about them.
>
> **Source of truth for *why*.** [`../design.md`](../design.md) § E.1, § E.2, § C.2.
>
> **Working directory.** `c:\git\spotyvibe`. All paths below are relative to the repo root.
>
> **Conventions.** Vanilla ES modules, no bundler. Jinja2 templates. Modular CSS. i18n via `data-i18n` + `i18n(key, fallback)`. All user-facing text lives in `frontend/static/i18n/en.json` and `de.json`. See [`../CLAUDE.md`](../CLAUDE.md). Per CLAUDE.md rule 2: all Spotify calls in `core/src/playlist.py`. Per rule: all OpenAI-protocol calls in `core/src/openai_http.py`.
>
> **What this wave is.** Three power-user features. They share almost no UI but touch a lot of backend and settings UI — grouping them here is a cost optimisation, not a UX decision.
>
> **What this wave is NOT.** No native Anthropic / Gemini / Bedrock SDKs (OpenAI-compatible protocol only). No monthly usage tracking (per-generation estimate only). No voice input on APK (desktop-web only). No help-page i18n (Wave 5). If you're about to install an `@anthropic-ai/sdk`, a `@google/generative-ai` package, or a usage-log database table — stop.

---

## 1. Scope map

| Ref | Name | Summary |
|-----|------|---------|
| E.1 | Custom OpenAI-compatible endpoints | The app can talk to any OpenAI-compatible endpoint: Ollama, LM Studio, Groq, OpenRouter, Azure (as Custom), or any other. Provider preset dropdown sets a default base URL; API key and model are configured per-provider. "Fetch available models" hits `/v1/models` on the configured endpoint and populates the model dropdown; graceful fallback to free-text. Local endpoints skip the API key requirement. |
| E.2 | Token-and-cost estimator | Client-side, approximate (char-count/4), shipped with a versioned JSON price table. Appears as a live widget in (a) onboarding step 6, (b) Settings modal, (c) a one-line footnote under the Generate button. Models not in the price table show "Estimate unavailable". Always disclosed as "Estimate only". |
| C.2 | Voice input for profile description | A microphone button inside the "Describe Your Vibe" textarea. Uses `SpeechRecognition` / `webkitSpeechRecognition`. Transcript appends at cursor position. No server round-trip, no LLM parse. Hidden on unsupported browsers. |

---

## 2. Files to create, modify, delete

### Create

| Path | Purpose |
|------|---------|
| `frontend/static/js/modules/provider.js` | Provider preset catalogue, switching, `/v1/models` fetch, credential form binding. |
| `frontend/static/js/modules/cost_estimate.js` | Approximate token counter, pricing lookup, live widget. |
| `frontend/static/js/modules/voice.js` | Web Speech API wrapper, transcript append, permission flow. |
| `frontend/static/css/provider.css` | Provider dropdown + credential rows + status line. |
| `frontend/static/css/cost_estimate.css` | Cost-estimate card + footnote style. |
| `frontend/static/css/voice.css` | Microphone button states (idle / recording / processing). |
| `frontend/static/data/pricing.json` | Versioned price table shipped with the app. |
| `implementation/wave4_power_users.md` | **This file.** |

### Modify

| Path | What changes |
|------|--------------|
| `frontend/templates/modals/settings_modal.html` | Add a "Provider" section at the top (above Used Model). Add a cost-estimate card below Used Model. Relabel "OPENAI API KEY" label to dynamic "{Provider} API key". |
| `frontend/templates/modals/credentials_modal.html` | Relabel the same field dynamically. |
| `frontend/templates/onboarding.html` | Step 6: wire "Use a different provider…" link to expand an inline provider block (same DOM as Settings but simpler). Replace the cost-estimate placeholder with a live widget. |
| `frontend/templates/train_profile.html` | Add microphone button inside the Describe Your Vibe textarea accordion (`#accVibeDesc`). |
| `frontend/templates/generate_section.html` | Add a one-line cost-estimate footnote under the Generate button (collapsible / subtle). |
| `frontend/static/js/main.js` | Bootstrap `provider.js`, `cost_estimate.js`, `voice.js`. |
| `frontend/static/js/modules/onboarding.js` (Wave 1) | Wire provider expandable on step 6. Call `CostEstimate.renderInto(node)` at step 6 activation. |
| `frontend/static/i18n/en.json` | Add every key listed in § 9. |
| `frontend/static/i18n/de.json` | Same keys with German strings. |
| `config.py` | Add `get_llm_base_url()`, `set_llm_base_url()`, `get_llm_provider_preset()`, `set_llm_provider_preset()`. Default `base_url` = `https://api.openai.com/v1`, default preset = `openai`. |
| `core/src/openai_http.py` | Read base URL from config on every call. Pass the configured base URL as a parameter to any underlying HTTP helper. Handle missing API keys for local endpoints. |
| `app.py` | Modify `GET /api/settings` to include `provider_preset`, `llm_base_url`, `llm_api_key_required` in the response. Modify `POST /api/settings` to accept `provider_preset` + `llm_base_url`. Add `POST /api/llm/fetch_models` endpoint that proxies a `GET {base_url}/models` server-side (so the browser doesn't have to deal with CORS on local endpoints). |
| `frontend/tests/test_documentation_screenshots.py` | Screenshots 81–92. |
| `frontend/tests/test_frontend.py` | Smoke tests for provider switch, cost estimate rendering, voice button presence. |
| `core/tests/test_openai_http.py` (create if absent) | Unit tests for base-URL plumbing and local-provider key-skip. |

### Delete

Nothing.

---

## 3. Shared patterns (read first)

### 3.1 Config contract

All three features read settings from the same flat shape returned by `GET /api/settings`:

```json
{
  "model": "gpt-4o-mini",
  "provider_preset": "openai",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_api_key_required": true,
  "playlist_size": 25,
  "new_artist_pct": 50,
  "debug_mode": false,
  "debug_controls_available": true,
  "ui_language": "en",
  "available_models": [ ... ]
}
```

New fields this wave introduces: `provider_preset`, `llm_base_url`, `llm_api_key_required`. The `llm_api_key_required` is derived server-side from the preset (false for `ollama` / `lmstudio`) — clients don't compute it.

### 3.2 Versioned pricing asset

`frontend/static/data/pricing.json`:

```json
{
  "schema_version": 1,
  "last_updated": "2026-04-12",
  "currency": "USD",
  "models": {
    "gpt-4o":        { "input_per_1m": 2.50, "output_per_1m": 10.00 },
    "gpt-4o-mini":   { "input_per_1m": 0.15, "output_per_1m":  0.60 },
    "gpt-4.1":       { "input_per_1m": 2.00, "output_per_1m":  8.00 },
    "gpt-4.1-mini":  { "input_per_1m": 0.40, "output_per_1m":  1.60 },
    "gpt-4.1-nano":  { "input_per_1m": 0.10, "output_per_1m":  0.40 }
  }
}
```

Unknown models show "Estimate unavailable". The file is versioned by `schema_version` + `last_updated`; the implementer updates `last_updated` on each release where prices move. Do not promise it's always current — the always-visible disclaimer covers that.

### 3.3 Approximate token counting (rationale)

The project already has a no-build-step, no-bundler frontend stack. Shipping a tokenizer library (even `js-tiktoken` at ~300 KB) would mean adding a static vendor asset and a CSP allowance. Wave 4 avoids that by approximating:

```
tokens ≈ ceil(char_count / 4)
```

This underestimates for code-heavy text and overestimates for whitespace-dense text, but the real-world variance for English/German profile text is within ±20 %. Combined with the explicit "estimate only" disclaimer, this is acceptable. If a future wave wants accurate counting, swap the `cost_estimate.countTokens()` implementation without changing the UI.

### 3.4 Per-call token accounting (formula)

For a single generation of N suggestions:

```
prompt overhead       ≈ 600 tokens   (system prompt + few-shot examples + response schema)
per-suggestion input  ≈  40 tokens   (track fields read back for dedup, carried context)
per-suggestion output ≈  80 tokens   (title, artist, rationale chips)

input  = 600 + countTokens(profileText) + N * 40
output =           N * 80
```

For a 25-track run with a 450-token profile: input ≈ 600 + 450 + 1000 = 2050, output ≈ 2000. Cost at gpt-4o-mini: ~$0.0015 per run.

---

## 4. E.1 — Custom OpenAI-compatible endpoints

### 4.1 Provider preset catalogue

Defined in `provider.js`:

```js
export const PROVIDER_PRESETS = {
  openai: {
    id: 'openai',
    name_i18n: 'provider.openai',
    default_base_url: 'https://api.openai.com/v1',
    local: false,
    models_endpoint_supported: true,
    doc_url: 'https://platform.openai.com/api-keys',
  },
  ollama: {
    id: 'ollama',
    name_i18n: 'provider.ollama',
    default_base_url: 'http://localhost:11434/v1',
    local: true,
    models_endpoint_supported: true,
    doc_url: 'https://ollama.com/download',
  },
  lmstudio: {
    id: 'lmstudio',
    name_i18n: 'provider.lmstudio',
    default_base_url: 'http://localhost:1234/v1',
    local: true,
    models_endpoint_supported: true,
    doc_url: 'https://lmstudio.ai/',
  },
  groq: {
    id: 'groq',
    name_i18n: 'provider.groq',
    default_base_url: 'https://api.groq.com/openai/v1',
    local: false,
    models_endpoint_supported: true,
    doc_url: 'https://console.groq.com/keys',
  },
  openrouter: {
    id: 'openrouter',
    name_i18n: 'provider.openrouter',
    default_base_url: 'https://openrouter.ai/api/v1',
    local: false,
    models_endpoint_supported: true,
    doc_url: 'https://openrouter.ai/keys',
  },
  custom: {
    id: 'custom',
    name_i18n: 'provider.custom',
    default_base_url: '',
    local: false,
    models_endpoint_supported: true,    // optimistic — let the user try
    doc_url: null,
  },
};
```

Azure OpenAI is **not** a dedicated preset. Azure users pick "Custom" and paste their full `https://{resource}.openai.azure.com/openai/deployments/{deployment}` URL. This is documented in the provider section's help text but not auto-configured. Rationale: Azure requires an `api-version` query-string parameter on every call — best left as an expert path.

### 4.2 Provider section in the Settings modal

Insert a new form group **at the top** of `settings_modal.html`, above the existing Used Model row:

```
┌─────────────────────────────────────────────────┐
│ ⚙️ Settings                                      │
├─────────────────────────────────────────────────┤
│ PROVIDER                                        │
│ [ OpenAI                                    ▾ ] │  ← preset dropdown
│ Pick where SpotyVibe gets its AI from.          │  ← inline hint
│ ▸ Learn more                                    │  ← Wave-2 learn-more pattern
│                                                 │
│ BASE URL                                        │
│ [ https://api.openai.com/v1                   ] │
│ Shown when preset = Custom, or hidden otherwise.│
│                                                 │
│ OPENAI API KEY                                  │  ← label swaps per provider
│ [ ●●●●●●●●●●●●●●●●●●●●●● ]  [🔁 Fetch models]   │
│ ✓ Key set · masked sk-…abc123                   │
│                                                 │
│ USED MODEL                                      │
│ [ gpt-4o-mini                               ▾ ] │  ← existing, now populated from fetch if available
│ (existing hint + Learn more from Wave 2)        │
│                                                 │
│ ─────────────────────────────────────────────── │
│ Cost estimate (Wave-4 § 5.3)                    │
│ ...                                             │
├─────────────────────────────────────────────────┤
│ PLAYLIST SIZE                                   │
│ ...                                             │
└─────────────────────────────────────────────────┘
```

**DOM outline:**

```html
<div class="form-row">
  <label for="settings-provider" data-i18n="provider.label">Provider</label>
  <select id="settings-provider" onchange="onProviderChange()">
    <option value="openai"     data-i18n="provider.openai">OpenAI</option>
    <option value="ollama"     data-i18n="provider.ollama">Ollama (local)</option>
    <option value="lmstudio"   data-i18n="provider.lmstudio">LM Studio (local)</option>
    <option value="groq"       data-i18n="provider.groq">Groq</option>
    <option value="openrouter" data-i18n="provider.openrouter">OpenRouter</option>
    <option value="custom"     data-i18n="provider.custom">Custom…</option>
  </select>
  <p class="inline-hint" data-i18n="provider.hint">Pick where SpotyVibe gets its AI from.</p>
  <details class="learn-more">
    <summary data-i18n="common.learn_more">Learn more</summary>
    <div class="learn-more-body" data-i18n="provider.learn_more">
      SpotyVibe speaks the OpenAI API protocol. Any OpenAI-compatible provider works — cloud (Groq, OpenRouter) or local (Ollama, LM Studio). For Azure OpenAI, pick "Custom" and paste your full deployment URL.
    </div>
  </details>
</div>

<!-- Base URL row — hidden unless preset = custom -->
<div class="form-row provider-base-url-row hidden" id="providerBaseUrlRow">
  <label for="settings-base-url" data-i18n="provider.base_url_label">Base URL</label>
  <input id="settings-base-url" type="text" placeholder="https://api.example.com/v1" autocomplete="off">
  <p class="inline-hint" data-i18n="provider.base_url_hint">Full URL ending in /v1. For Azure, include /openai/deployments/{deployment}.</p>
</div>

<!-- API key row — existing, but with label binding to provider name -->
<div class="form-row">
  <label for="settings-api-key" id="settings-api-key-label" data-i18n="provider.api_key_label_openai">OpenAI API Key</label>
  <div class="cred-input-wrap">
    <input id="settings-api-key" type="password" placeholder="sk-…" autocomplete="off">
    <button class="btn-fetch-models" id="btnFetchModels" onclick="fetchProviderModels()" data-i18n-title="provider.fetch_models_title" title="Fetch available models">🔁</button>
  </div>
  <div class="cred-status" id="status-settings-api-key"></div>
  <p class="inline-hint" id="settings-api-key-hint" data-i18n="provider.api_key_hint_openai">Paste your OpenAI API key.</p>
  <p class="inline-hint provider-local-notice hidden" id="providerLocalNotice" data-i18n="provider.local_notice">Local providers don't need an API key — any value or leave empty.</p>
</div>

<!-- Used Model row (existing — modified to support free-text when preset requires it) -->
<div class="form-row">
  <label for="settings-model" data-i18n="settings.model_label">Used Model</label>
  <div class="provider-model-wrap">
    <select id="settings-model">
      <!-- existing options; populated dynamically after Fetch models -->
    </select>
    <input id="settings-model-freetext" type="text" class="hidden" placeholder="llama3.1:8b" autocomplete="off">
    <button class="btn-model-mode" id="btnModelMode" onclick="toggleModelFreeText()" data-i18n-title="provider.model_mode_toggle" title="Toggle free-text">✎</button>
  </div>
  <p class="inline-hint" data-i18n="settings.model_hint">Which model produces your suggestions.</p>
  <!-- (existing learn-more from Wave 2 stays) -->
</div>
```

### 4.3 Provider-switching behaviour

`provider.js` listens for `onchange` on the preset dropdown. On change:

1. Update the **base URL input** visibility — hidden unless `preset === 'custom'`.
2. Update the **base URL value** — set to `PROVIDER_PRESETS[preset].default_base_url` (user can then edit if they picked Custom).
3. Update the **API key label** — `provider.api_key_label_{preset}` i18n key.
4. Update the **API key hint** — `provider.api_key_hint_{preset}`.
5. Toggle the **local notice** — visible iff `PROVIDER_PRESETS[preset].local === true`.
6. Clear the **model dropdown** (unless the preset is `openai` and the existing list is valid). The Fetch models button repopulates.
7. Remove the existing API key from state *without* deleting it from storage — users who switch providers and back should find their keys retained. Implementation: keep separate localStorage entries per preset id, e.g. `sv.llm_key.openai`, `sv.llm_key.groq`, etc. The `/api/settings/credentials` backend still stores a single active key; the client restores the preset-specific key on switch.

Actually, simpler: **one active key at a time**. Switching providers clears the key from the UI and the backend. The user re-enters. This matches how every tool that supports multi-provider handles it. Document clearly in the `provider.learn_more` copy.

### 4.4 Fetch models flow

`POST /api/llm/fetch_models` — request body:

```json
{
  "base_url": "http://localhost:11434/v1",
  "api_key": "ollama"
}
```

Server-side:
- Make a `GET {base_url}/models` with `Authorization: Bearer {api_key}` (if key is non-empty).
- Parse the standard OpenAI-compatible response: `{ data: [{ id: "model-name", ... }, ... ] }`.
- Return `{ models: ["model-a", "model-b", ...] }` or `{ error: "..." }` with HTTP 502.
- Timeout: 5 seconds for remote, 2 seconds for `localhost`/`127.0.0.1`.

Client-side after success:
- Populate `<select id="settings-model">` with the returned ids.
- Select the first one if the current value is not in the list.

Client-side after failure:
- Show an inline error under the button: `provider.fetch_failed` → "Couldn't reach that endpoint. Check the base URL and try again."
- Offer free-text fallback via the `✎` toggle (see § 4.5).

### 4.5 Free-text model name (for providers without a reachable `/models`)

Some local setups don't expose `/models`. The `✎` button toggles `<select>` and `<input type="text">`. Both feed the same `settings.model` value when saved.

### 4.6 Backend changes

**`config.py`:**

```python
DEFAULT_LLM_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_PROVIDER_PRESET = 'openai'
LOCAL_PRESETS = {'ollama', 'lmstudio'}

def get_llm_base_url() -> str:
    return _config().get('llm_base_url', DEFAULT_LLM_BASE_URL)

def set_llm_base_url(url: str):
    _config().set('llm_base_url', url.strip())

def get_llm_provider_preset() -> str:
    return _config().get('provider_preset', DEFAULT_PROVIDER_PRESET)

def set_llm_provider_preset(preset: str):
    _config().set('provider_preset', preset)

def llm_api_key_required() -> bool:
    return get_llm_provider_preset() not in LOCAL_PRESETS
```

**`core/src/openai_http.py`:**

- Read `get_llm_base_url()` at the start of every call.
- Pass the configured base URL into every `requests.post(...)` / `requests.get(...)`.
- When `llm_api_key_required()` is `False` and no key is set, send `Authorization: Bearer ollama` (a dummy) or omit the header entirely — OpenAI SDK contract says omitting is fine, but some proxies reject. Use a dummy `ollama` value for maximum compatibility.
- No other structural change. The rest of the module (completions, streaming, JSON-mode parsing) stays.

**`app.py`:**

- `POST /api/settings` accepts `provider_preset` and `llm_base_url`. Validates:
  - `provider_preset` is one of the 6 known ids.
  - `llm_base_url` is a well-formed URL ending in `/v1` (or `/openai/deployments/*/chat/completions` for Azure-like custom URLs — keep the validator permissive: just reject empty strings and obvious garbage).
- `POST /api/llm/fetch_models` — see § 4.4.
- `GET /api/settings` adds the three new fields to the response.

### 4.7 Credentials modal changes

The existing `credentials_modal.html` still lists three credentials (OpenAI key + two Spotify). Replace the "OpenAI API Key" label with `{Provider} API key` via `data-i18n="provider.api_key_label_{preset}"` — bound at render time by a new hook in `provider.js` that watches for `#credentialsModal` open events.

---

## 5. E.2 — Token-and-cost estimator

### 5.1 Three mount points

All three read from the same state: current `playlist_size`, current `model`, current profile text.

| Location | Shape | When it refreshes |
|----------|-------|-------------------|
| **Onboarding step 6** — full card | Title + 6-row definition list + disclaimer | On step activation; on model change |
| **Settings modal** — full card | Same | On modal open; on model change; on playlist-size change |
| **Generate panel** — single-line footnote | "≈ $0.0015 · gpt-4o-mini · est." | Every time the panel body opens; when the size slider changes |

### 5.2 Cost-estimate card DOM

```html
<div class="cost-estimate-card" id="costEstimateCard">
  <div class="cost-estimate-header">
    <span class="cost-estimate-icon" aria-hidden="true">💰</span>
    <h3 class="cost-estimate-title" data-i18n="cost.title">Estimated cost per generation</h3>
  </div>
  <dl class="cost-estimate-list">
    <dt data-i18n="cost.model">Model</dt>             <dd id="costModelName">gpt-4o-mini</dd>
    <dt data-i18n="cost.profile_size">Profile size</dt><dd id="costProfileTokens">~450 tokens</dd>
    <dt data-i18n="cost.tracks">Suggestions</dt>       <dd id="costTracks">25 tracks</dd>
    <dt data-i18n="cost.tokens_in">Tokens in</dt>      <dd id="costTokensIn">~2,050</dd>
    <dt data-i18n="cost.tokens_out">Tokens out</dt>    <dd id="costTokensOut">~2,000</dd>
    <dt data-i18n="cost.total" class="cost-total-label">Estimated cost</dt>
    <dd id="costTotal" class="cost-total-value">≈ $0.0015</dd>
  </dl>
  <p class="cost-estimate-disclaimer" data-i18n="cost.disclaimer">Estimate only — actual cost depends on your profile size and provider rates.</p>
  <p class="cost-estimate-unavailable hidden" id="costUnavailable" data-i18n="cost.unavailable">Cost estimate unavailable for this model — prices aren't shipped in the app yet.</p>
</div>
```

### 5.3 Styling

- `.cost-estimate-card` — `background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; margin: 12px 0;`
- `.cost-estimate-header` — `display: flex; gap: 10px; align-items: center; margin-bottom: 10px;`
- `.cost-estimate-title` — `font-size: 0.92rem; font-weight: 700; color: var(--text-primary); margin: 0;`
- `.cost-estimate-list` — `display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 0.84rem; margin: 0;`
- `dl dt` — `color: var(--text-muted);`
- `dl dd` — `color: var(--text-secondary); text-align: right; font-variant-numeric: tabular-nums; margin: 0;`
- `.cost-total-label` — `color: var(--text-primary); font-weight: 600; padding-top: 6px; border-top: 1px solid var(--border); margin-top: 4px;`
- `.cost-total-value` — `color: var(--primary); font-weight: 700; padding-top: 6px; border-top: 1px solid var(--border); margin-top: 4px;`
- `.cost-estimate-disclaimer` — `font-size: 0.76rem; color: var(--text-muted); font-style: italic; margin: 10px 0 0; line-height: 1.4;`
- `.cost-estimate-unavailable` — `font-size: 0.82rem; color: var(--warning); margin: 10px 0 0;`

### 5.4 Generate-panel footnote

A compact one-liner, inserted immediately below the Generate button:

```html
<p class="cost-footnote" id="costFootnote">
  <span class="cost-footnote-icon" aria-hidden="true">💰</span>
  <span id="costFootnoteText">≈ $0.0015 · gpt-4o-mini · est.</span>
  <button class="cost-footnote-expand" onclick="openSettings('cost')" data-i18n="cost.details">details</button>
</p>
```

Style: `display: flex; gap: 8px; align-items: center; font-size: 0.78rem; color: var(--text-muted); margin: 8px 0 0; justify-content: center;`. Subtle, dismissable-looking. Not alarming.

Hidden when `cost.unavailable` state applies; shows as "≈ — · {model} · estimate unavailable" in that case.

### 5.5 `cost_estimate.js` API

```js
/** Count tokens approximately. */
export function countTokens(text) {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

/** Load the shipped pricing table once, cache it. */
export async function getPricing() { ... }

/** Compute estimate for a single generation.
 *  Returns null if model is unpriced.
 */
export async function estimate({ model, profileText, tracks }) {
  const prices = (await getPricing()).models[model];
  if (!prices) return null;
  const profileTokens = countTokens(profileText);
  const tokensIn  = 600 + profileTokens + tracks * 40;
  const tokensOut = tracks * 80;
  const cost = (tokensIn  / 1_000_000) * prices.input_per_1m
             + (tokensOut / 1_000_000) * prices.output_per_1m;
  return {
    model, profileTokens, tracks, tokensIn, tokensOut, cost,
  };
}

/** Render the full card into the given element.
 *  Returns a teardown function.
 */
export function renderInto(node, opts) { ... }

/** Render the Generate-panel footnote into the given element. */
export function renderFootnote(node) { ... }
```

Profile text is read client-side from:
- Main app: `#trainVibeDesc.value + '\n' + #trainCoreDesc.value + '\n' + #trainMustHave.value + '\n' + #trainSoftPrefs.value + '\n' + #trainAvoid.value` (concatenated for token count).
- Onboarding step 6: an approximation. If the user has not yet built a profile, fall back to a constant of 300 characters (≈ 75 tokens). Document this assumption in the widget's subtitle: "Based on a typical 75-token profile. Your actual runs will be higher or lower."

### 5.6 Unknown-model handling

If `prices[model]` is undefined (custom endpoint returned `llama3.1:8b`, or a brand-new OpenAI model not yet in the shipped table):

- Hide the cost row, show `#costUnavailable` message.
- Hide the Generate-panel footnote.
- Onboarding step 6: show "Cost estimate not shipped for this model — check your provider's pricing page." with a link to `PROVIDER_PRESETS[preset].doc_url` when present.

### 5.7 Live refresh

The widget refreshes:
- On `blur` of any profile textarea.
- On `change` of `#settings-model` or `#settings-model-freetext`.
- On `input` of `#settings-playlist-size` (debounced 200 ms).
- On `input` of the Quick/Advanced size slider from Wave 2.

Implementation: a small event bus in `cost_estimate.js` OR direct listeners added in `main.js` bootstrap.

---

## 6. C.2 — Voice input for profile description

### 6.1 Button placement

Inside the Describe Your Vibe accordion body, position the mic button **absolutely** at the bottom-right of `#trainVibeDesc` textarea:

```html
<div class="vibe-textarea-wrap">
  <textarea id="trainVibeDesc" data-i18n-placeholder="profile.vibe_description_placeholder" …></textarea>
  <button class="voice-btn" id="voiceBtnVibe" onclick="toggleVoice('trainVibeDesc')" aria-label="Dictate" data-i18n-title="voice.dictate" title="Dictate">
    <span class="voice-btn-icon" aria-hidden="true">🎤</span>
    <span class="voice-btn-label" data-i18n="voice.speak">Speak</span>
  </button>
</div>
```

### 6.2 Styling

- `.vibe-textarea-wrap` — `position: relative;`
- `#trainVibeDesc` — existing styling + `padding-right: 110px;` (reserve space for the button)
- `.voice-btn` — `position: absolute; bottom: 10px; right: 10px; display: flex; align-items: center; gap: 6px; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-pill); padding: 6px 14px; font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); cursor: pointer; transition: background 120ms, color 120ms, border-color 120ms;`
- `.voice-btn:hover` — `background: var(--bg-card); color: var(--text-primary); border-color: rgba(30,215,96,0.35);`
- **Recording state** (`.voice-btn--recording`) — `background: rgba(239,68,68,0.12); color: var(--error); border-color: rgba(239,68,68,0.35);` The icon becomes a pulsing red dot: `.voice-btn--recording .voice-btn-icon { animation: voice-pulse 1.2s ease-in-out infinite; }` with keyframes scaling 1 ↔ 1.15 and opacity 1 ↔ 0.6.
- **Processing state** (`.voice-btn--processing`) — `opacity: 0.7; cursor: wait;` Icon swaps to `⏳`.
- **Unsupported state** — whole button hidden (class `hidden`).

### 6.3 Voice module (`voice.js`)

```js
const SUPPORT = (typeof window !== 'undefined')
  && (window.SpeechRecognition || window.webkitSpeechRecognition);

export function isSupported() { return !!SUPPORT; }

const LANG_MAP = { en: 'en-US', de: 'de-DE' };

let _current = null; // active recognition instance

export function toggleVoice(targetInputId) {
  if (!SUPPORT) return;
  if (_current) { _current.stop(); _current = null; return; }

  const Recog = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new Recog();
  rec.lang = LANG_MAP[getUiLang()] || 'en-US';
  rec.continuous = true;
  rec.interimResults = false;

  const target = document.getElementById(targetInputId);
  const button = document.querySelector(`[onclick*="${targetInputId}"].voice-btn`);

  rec.onstart = () => button.classList.add('voice-btn--recording');
  rec.onresult = (e) => appendTranscriptAtCursor(target, e.results);
  rec.onerror  = (e) => showVoiceError(button, e.error);
  rec.onend    = () => {
    button.classList.remove('voice-btn--recording');
    _current = null;
  };
  rec.start();
  _current = rec;
}

function appendTranscriptAtCursor(textarea, results) {
  const transcript = Array.from(results)
    .filter(r => r.isFinal)
    .map(r => r[0].transcript)
    .join(' ');
  if (!transcript) return;
  const start = textarea.selectionStart || textarea.value.length;
  const end = textarea.selectionEnd || start;
  const before = textarea.value.slice(0, start);
  const after  = textarea.value.slice(end);
  const needsSpaceBefore = before && !/\s$/.test(before);
  const prefix = needsSpaceBefore ? ' ' : '';
  textarea.value = before + prefix + transcript + after;
  const newPos = (before + prefix + transcript).length;
  textarea.selectionStart = textarea.selectionEnd = newPos;
  textarea.dispatchEvent(new Event('input'));
}
```

### 6.4 Error handling

- Permission denied: show a one-time toast "Mic access denied. Grant permission in your browser, then try again." (`voice.permission_denied`).
- No-speech (user clicked but said nothing): silently stop, no toast.
- Network error (Chrome can require network for server-side recognition): toast "Voice input needs a connection." (`voice.network`).
- Browser mid-recording `onend` without `onresult`: silent.

### 6.5 Reduced motion

`@media (prefers-reduced-motion: reduce)` disables the pulsing icon — replace the animation with a static red icon.

### 6.6 Accessibility

- Button has `aria-pressed="true"` when recording.
- Screen-reader live region (visually-hidden `<p role="status" aria-live="polite">`) announces "Recording started" and "Recording stopped — transcript added".

### 6.7 Not in scope for Wave 4

- No voice input in Core Description, Must Have, Soft Preferences, Avoid. These are structured fields where dictation causes more editing than typing saves. The design explicitly scopes voice to the Vibe textarea.
- No APK / WebView support. The feature is hidden on WebView UAs via `if (/; wv\)/.test(navigator.userAgent)) button.classList.add('hidden');`.
- No "hold to talk" — click-to-start / click-to-stop only (accessibility).
- No transcript editing UI beyond the normal textarea.

---

## 7. Onboarding step 6 — Wave-4 upgrade

Wave 1 built step 6 with:
1. A model dropdown.
2. A placeholder "Per-generation cost estimate coming in a future update."

Wave 4 replaces item 2 with a live `cost_estimate.js` widget mounted via `CostEstimate.renderInto(el)`. It also adds an **inline expandable** for custom providers:

```html
<details class="provider-advanced-expandable">
  <summary data-i18n="provider.use_different">Use a different provider…</summary>
  <div class="provider-advanced-body">
    <!-- same DOM as Settings-modal provider section, scoped to ob-* classes -->
  </div>
</details>
```

When expanded, the user sees the preset dropdown + base URL + API key rows. Saving on "Next →" persists both the provider settings and the model choice.

The "Use a different provider…" link that Wave 1 placed as a bare `<a>` is replaced by this `<details>`. Keep the i18n key.

---

## 8. Wiring — `main.js` bootstrap additions

```js
import * as Provider      from './modules/provider.js';
import * as CostEstimate  from './modules/cost_estimate.js';
import * as Voice         from './modules/voice.js';

window.addEventListener('DOMContentLoaded', () => {
    Provider.init();          // bind dropdown, fetch-models, API-key-label swap
    CostEstimate.init();      // preload pricing.json, wire listeners
    Voice.init();             // probe support, hide button if unsupported or WebView
});
```

Order: Provider before CostEstimate (cost widget reads the current provider/model to avoid stale data on first render).

---

## 9. i18n keys

Append to `en.json` and `de.json`.

```
# Provider (E.1)
provider.label                 = "Provider"                              / "Anbieter"
provider.hint                  = "Pick where SpotyVibe gets its AI from." / "Lege fest, woher SpotyVibe seine KI bezieht."
provider.learn_more            = "SpotyVibe speaks the OpenAI API protocol. Any OpenAI-compatible provider works — cloud (Groq, OpenRouter) or local (Ollama, LM Studio). For Azure OpenAI, pick \"Custom\" and paste your full deployment URL." / "SpotyVibe spricht das OpenAI-API-Protokoll. Jeder OpenAI-kompatible Anbieter funktioniert — Cloud (Groq, OpenRouter) oder lokal (Ollama, LM Studio). Für Azure OpenAI „Custom" wählen und die komplette Deployment-URL einfügen."
provider.openai                = "OpenAI"                                / "OpenAI"
provider.ollama                = "Ollama (local)"                        / "Ollama (lokal)"
provider.lmstudio              = "LM Studio (local)"                     / "LM Studio (lokal)"
provider.groq                  = "Groq"                                  / "Groq"
provider.openrouter            = "OpenRouter"                            / "OpenRouter"
provider.custom                = "Custom…"                               / "Eigene…"
provider.base_url_label        = "Base URL"                              / "Basis-URL"
provider.base_url_hint         = "Full URL ending in /v1. For Azure, include /openai/deployments/{deployment}." / "Vollständige URL, endet auf /v1. Für Azure /openai/deployments/{deployment} mitgeben."
provider.api_key_label_openai      = "OpenAI API key"                    / "OpenAI API-Schlüssel"
provider.api_key_label_ollama      = "API key (optional for Ollama)"     / "API-Schlüssel (optional für Ollama)"
provider.api_key_label_lmstudio    = "API key (optional for LM Studio)"  / "API-Schlüssel (optional für LM Studio)"
provider.api_key_label_groq        = "Groq API key"                      / "Groq API-Schlüssel"
provider.api_key_label_openrouter  = "OpenRouter API key"                / "OpenRouter API-Schlüssel"
provider.api_key_label_custom      = "API key"                           / "API-Schlüssel"
provider.api_key_hint_openai       = "Paste your OpenAI API key."        / "OpenAI API-Schlüssel einfügen."
provider.api_key_hint_ollama       = "Ollama accepts any string. Leave empty or use a dummy." / "Ollama akzeptiert jeden Wert. Leer lassen oder Dummy verwenden."
provider.api_key_hint_lmstudio     = "LM Studio accepts any string. Leave empty or use a dummy." / "LM Studio akzeptiert jeden Wert. Leer lassen oder Dummy verwenden."
provider.api_key_hint_groq         = "Paste your Groq API key."          / "Groq API-Schlüssel einfügen."
provider.api_key_hint_openrouter   = "Paste your OpenRouter API key."    / "OpenRouter API-Schlüssel einfügen."
provider.api_key_hint_custom       = "Paste your API key (if your endpoint requires one)." / "API-Schlüssel einfügen (falls dein Endpoint einen benötigt)."
provider.local_notice          = "Local providers don't need an API key — any value or leave empty." / "Lokale Anbieter brauchen keinen Schlüssel — beliebiger Wert oder leer."
provider.fetch_models_title    = "Fetch available models"                / "Modelle abrufen"
provider.fetch_failed          = "Couldn't reach that endpoint. Check the base URL and try again." / "Endpoint nicht erreichbar. Bitte Basis-URL prüfen und erneut versuchen."
provider.fetch_success         = "Loaded {count} models."                / "{count} Modelle geladen."
provider.model_mode_toggle     = "Toggle free-text model name"           / "Freitext für Modellnamen"
provider.use_different         = "Use a different provider…"             / "Anderen Anbieter verwenden…"
provider.switch_clears_key     = "Switching providers clears your stored API key. You'll need to paste the new one." / "Beim Anbieterwechsel wird der gespeicherte API-Schlüssel gelöscht. Du musst den neuen einfügen."

# Cost estimate (E.2)
cost.title                     = "Estimated cost per generation"         / "Geschätzte Kosten pro Generierung"
cost.model                     = "Model"                                 / "Modell"
cost.profile_size              = "Profile size"                          / "Profilgröße"
cost.tracks                    = "Suggestions"                           / "Vorschläge"
cost.tokens_in                 = "Tokens in"                             / "Tokens Eingabe"
cost.tokens_out                = "Tokens out"                            / "Tokens Ausgabe"
cost.total                     = "Estimated cost"                        / "Geschätzte Kosten"
cost.disclaimer                = "Estimate only — actual cost depends on your profile size and provider rates." / "Nur Schätzung — tatsächliche Kosten hängen von Profilgröße und Tarifen des Anbieters ab."
cost.unavailable               = "Cost estimate unavailable for this model — prices aren't shipped in the app yet." / "Kostenabschätzung für dieses Modell nicht verfügbar — Preise sind in der App noch nicht hinterlegt."
cost.tokens_approx             = "~{n} tokens"                           / "~{n} Tokens"
cost.tracks_count              = "{n} tracks"                            / "{n} Tracks"
cost.cost_value                = "≈ {amount}"                            / "≈ {amount}"
cost.details                   = "details"                               / "Details"
cost.assumed_profile           = "Based on a typical 75-token profile. Your actual runs will be higher or lower." / "Basiert auf einem typischen Profil mit 75 Tokens. Deine tatsächlichen Werte können abweichen."
cost.footnote_unavailable      = "estimate unavailable"                  / "Schätzung nicht verfügbar"
cost.footnote_tpl              = "≈ {cost} · {model} · est."             / "≈ {cost} · {model} · Schätzung"

# Voice (C.2)
voice.speak                    = "Speak"                                 / "Sprechen"
voice.listening                = "Listening…"                            / "Hört zu…"
voice.stop                     = "Stop"                                  / "Stopp"
voice.dictate                  = "Dictate into this field"               / "In dieses Feld diktieren"
voice.permission_denied        = "Mic access denied. Grant permission in your browser, then try again." / "Mikrofonzugriff verweigert. Erlaube den Zugriff im Browser und versuche es erneut."
voice.network                  = "Voice input needs a connection."        / "Spracheingabe benötigt eine Verbindung."
voice.started                  = "Recording started"                     / "Aufnahme gestartet"
voice.stopped                  = "Recording stopped — transcript added"  / "Aufnahme beendet — Text eingefügt"
```

---

## 10. Screenshot tests — additions to `test_documentation_screenshots.py`

Numbers 81–92. Append after Wave 3.

```python
# -- Wave 4: Power users ----------------------------------------------

def test_81_provider_dropdown_expanded(self, page: Page, screenshot_url):
    """Screenshot: Settings modal with provider dropdown open."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    page.locator("#settings-provider").click()
    page.wait_for_timeout(200)
    _shot_element(page, "81_provider_dropdown_expanded", "#settingsModal .modal")

def test_82_provider_custom_selected(self, page: Page, screenshot_url):
    """Screenshot: Settings modal with Custom provider selected, base URL row visible."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    page.select_option("#settings-provider", "custom")
    page.wait_for_timeout(300)
    _shot_element(page, "82_provider_custom_selected", "#settingsModal .modal")

def test_83_provider_local_ollama(self, page: Page, screenshot_url):
    """Screenshot: Settings modal with Ollama selected, local notice visible."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    page.select_option("#settings-provider", "ollama")
    page.wait_for_timeout(300)
    _shot_element(page, "83_provider_local_ollama", "#settingsModal .modal")

def test_84_fetch_models_success(self, page: Page, screenshot_url):
    """Screenshot: Fetch-models successful (populated dropdown)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.route("**/api/llm/fetch_models", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]}),
    ))
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    page.locator("#btnFetchModels").click()
    page.wait_for_timeout(500)
    _shot_element(page, "84_fetch_models_success", "#settingsModal .modal")

def test_85_fetch_models_failure(self, page: Page, screenshot_url):
    """Screenshot: Fetch-models with error message inline."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.route("**/api/llm/fetch_models", lambda route: route.fulfill(
        status=502,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"error": "unreachable"}),
    ))
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    page.select_option("#settings-provider", "custom")
    page.locator("#settings-base-url").fill("http://unreachable.example/v1")
    page.locator("#btnFetchModels").click()
    page.wait_for_timeout(500)
    _shot_element(page, "85_fetch_models_failure", "#settingsModal .modal")

def test_86_cost_estimate_full_card(self, page: Page, screenshot_url):
    """Screenshot: Full cost-estimate card in Settings modal (gpt-4o-mini)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(400)
    _shot_element(page, "86_cost_estimate_full_card", "#costEstimateCard")

def test_87_cost_estimate_unavailable(self, page: Page, screenshot_url):
    """Screenshot: Cost estimate showing unavailable state for an unknown model."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)
    # Force an unpriced model
    page.evaluate("""() => {
        document.getElementById('btnModelMode').click();
        document.getElementById('settings-model-freetext').value = 'llama3.1:8b';
        document.getElementById('settings-model-freetext').dispatchEvent(new Event('input'));
    }""")
    page.wait_for_timeout(400)
    _shot_element(page, "87_cost_estimate_unavailable", "#costEstimateCard")

def test_88_cost_footnote_generate(self, page: Page, screenshot_url):
    """Screenshot: Generate panel with cost-estimate footnote below the button."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    _switch_tab(page, "spotify")
    page.locator("#generateToggleBtn").click()
    page.wait_for_timeout(400)
    _shot_element(page, "88_cost_footnote_generate", "#generateSection .run-section")

def test_89_onboarding_step6_cost(self, page: Page, screenshot_url):
    """Screenshot: Onboarding step 6 with the Wave-4 cost widget live."""
    self._goto_onboarding_page(page, screenshot_url, page_index=5)
    page.wait_for_timeout(400)
    _shot(page, "89_onboarding_step6_cost")

def test_90_onboarding_step6_provider_expanded(self, page: Page, screenshot_url):
    """Screenshot: Onboarding step 6 with 'Use a different provider' expanded."""
    self._goto_onboarding_page(page, screenshot_url, page_index=5)
    page.locator("summary:has-text('Use a different provider')").click()
    page.wait_for_timeout(300)
    _shot(page, "90_onboarding_step6_provider_expanded")

def test_91_voice_button_idle(self, page: Page, screenshot_url):
    """Screenshot: Voice button in idle state inside the Vibe accordion."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(300)
    # Force voice button visible even if SpeechRecognition is missing in headless
    page.evaluate("document.getElementById('voiceBtnVibe').classList.remove('hidden')")
    page.wait_for_timeout(200)
    _shot_element(page, "91_voice_button_idle", "#accVibeDesc .vibe-textarea-wrap")

def test_92_voice_button_recording(self, page: Page, screenshot_url):
    """Screenshot: Voice button in recording state."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        const btn = document.getElementById('voiceBtnVibe');
        btn.classList.remove('hidden');
        btn.classList.add('voice-btn--recording');
        btn.setAttribute('aria-pressed', 'true');
    }""")
    page.wait_for_timeout(200)
    _shot_element(page, "92_voice_button_recording", "#accVibeDesc .vibe-textarea-wrap")
```

---

## 11. Smoke tests — additions to `test_frontend.py`

```python
def test_provider_switch_shows_base_url_row(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Settings')").click()
    page.wait_for_selector("#settings-provider")
    # Default: OpenAI → base URL row hidden
    assert page.locator("#providerBaseUrlRow").is_hidden()
    page.select_option("#settings-provider", "custom")
    assert page.locator("#providerBaseUrlRow").is_visible()

def test_provider_local_notice_for_ollama(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Settings')").click()
    page.wait_for_selector("#settings-provider")
    page.select_option("#settings-provider", "ollama")
    assert page.locator("#providerLocalNotice").is_visible()
    label = page.locator("#settings-api-key-label").text_content()
    assert "optional" in label.lower() or "optional" in label

def test_fetch_models_populates_dropdown(page, base_url):
    page.route("**/api/llm/fetch_models", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"models": ["m1", "m2", "m3"]}),
    ))
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Settings')").click()
    page.wait_for_selector("#btnFetchModels")
    page.locator("#btnFetchModels").click()
    page.wait_for_timeout(600)
    options = page.evaluate("Array.from(document.querySelectorAll('#settings-model option')).map(o => o.value)")
    assert set(options) >= {"m1", "m2", "m3"}

def test_cost_estimate_renders_for_known_model(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Settings')").click()
    page.wait_for_selector("#costEstimateCard")
    cost_text = page.locator("#costTotal").text_content()
    assert cost_text.startswith("≈")
    assert page.locator("#costUnavailable").is_hidden()

def test_cost_estimate_unavailable_for_unknown_model(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Settings')").click()
    page.wait_for_selector("#costEstimateCard")
    page.evaluate("""() => {
        document.getElementById('btnModelMode').click();
        const el = document.getElementById('settings-model-freetext');
        el.value = 'not-a-real-model';
        el.dispatchEvent(new Event('input'));
    }""")
    page.wait_for_timeout(400)
    assert page.locator("#costUnavailable").is_visible()

def test_voice_button_hidden_when_unsupported(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    # Remove both API prefixes before any mic init
    page.evaluate("""() => {
        delete window.SpeechRecognition;
        delete window.webkitSpeechRecognition;
    }""")
    # Voice.init should have run already — simulate re-init
    page.evaluate("""() => {
        import('/static/js/modules/voice.js').then(V => {
            if (!V.isSupported()) {
                document.getElementById('voiceBtnVibe').classList.add('hidden');
            }
        });
    }""")
    page.locator("#trainToggleBtn").click()
    page.wait_for_timeout(200)
    assert page.locator("#voiceBtnVibe").is_hidden()
```

---

## 12. Backend unit tests — `core/tests/test_openai_http.py`

Create if absent. Mock the HTTP layer and verify base URL plumbing:

```python
from unittest.mock import patch, MagicMock

def test_uses_configured_base_url():
    from core.src import openai_http
    from config import set_llm_base_url
    set_llm_base_url('http://localhost:11434/v1')
    with patch('core.src.openai_http.requests.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {'choices': [{'message': {'content': '{}'}}]})
        openai_http.chat_completion(messages=[], model='llama3')
        called_url = mock_post.call_args[0][0]
        assert called_url.startswith('http://localhost:11434/v1/')

def test_local_provider_skips_key_check():
    from core.src import openai_http
    from config import set_llm_provider_preset, set_llm_base_url
    set_llm_provider_preset('ollama')
    set_llm_base_url('http://localhost:11434/v1')
    with patch('core.src.openai_http.get_credentials') as mock_creds, \
         patch('core.src.openai_http.requests.post') as mock_post:
        mock_creds.return_value = {'OPENAI_API_KEY': {'is_set': False}}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {'choices': [{'message': {'content': '{}'}}]})
        # Should not raise "missing key" error
        openai_http.chat_completion(messages=[], model='llama3')
        assert mock_post.called
```

Plus parser tests for `POST /api/llm/fetch_models` in `core/tests/test_app.py` (or wherever Flask-route tests live).

---

## 13. Acceptance checklist

- [ ] Settings modal shows the provider section at the top with the 6 preset options.
- [ ] Switching preset toggles base-URL row visibility, updates API-key label, and refreshes the hint text.
- [ ] Selecting Ollama or LM Studio shows the "local provider" notice and marks the key field as optional.
- [ ] "Fetch available models" against a reachable endpoint populates the model dropdown with the returned ids.
- [ ] Failed fetch shows a localised error under the button; the model dropdown is not cleared.
- [ ] `✎` button toggles between model dropdown and free-text input. Saving either persists `settings.model`.
- [ ] `GET /api/settings` response includes `provider_preset`, `llm_base_url`, `llm_api_key_required`.
- [ ] `POST /api/settings` persists all three fields and validates `provider_preset` against the whitelist.
- [ ] `POST /api/llm/fetch_models` proxies to `GET {base_url}/models` with a 5 s remote / 2 s localhost timeout.
- [ ] `core/src/openai_http.py` reads `get_llm_base_url()` on every call and forwards it to the HTTP request.
- [ ] Local providers accept a missing API key and do not raise.
- [ ] Cost-estimate card renders in Settings modal with tokens-in, tokens-out, and cost.
- [ ] Cost card shows "Estimate unavailable" for models not in `pricing.json`.
- [ ] Cost widget updates on model change, playlist-size change, and profile-text change (debounced).
- [ ] Generate-panel footnote shows a one-line estimate or "estimate unavailable" consistent with the card.
- [ ] Onboarding step 6 shows a live estimate (not the Wave-1 placeholder).
- [ ] Onboarding step 6 "Use a different provider…" expandable reveals the provider fields inline.
- [ ] Voice button is visible inside the Vibe accordion when `SpeechRecognition` is supported.
- [ ] Voice button is hidden on browsers without `SpeechRecognition`, and on WebView UAs.
- [ ] Clicking the button enters recording state (pulsing red icon, `aria-pressed=true`).
- [ ] Final speech transcripts append at the textarea's cursor position with appropriate spacing.
- [ ] Clicking again stops recording; no transcript additions after stop.
- [ ] Permission-denied errors show a one-shot toast.
- [ ] Voice language follows the current UI language (en-US vs de-DE).
- [ ] `prefers-reduced-motion` disables the recording icon pulse.
- [ ] All 12 new screenshot tests pass under `-m screenshots`.
- [ ] All 6 new smoke tests pass under regular pytest.
- [ ] All new backend unit tests pass under `python -m pytest core/tests/`.
- [ ] No existing test regresses — full suite passes.
- [ ] No hardcoded English in new templates, JS, or Python responses.
- [ ] `pricing.json` parses as strict JSON and contains at least the 5 OpenAI models listed in § 3.2.
- [ ] Responsive: at 390×844, provider + cost sections stack without overflow; voice button touch target ≥ 44 px.

---

## 14. Review checklist before merging

- [ ] `version.py` bumped.
- [ ] `documentation/UserManual.md` updated: provider switching, cost estimate, voice input.
- [ ] `documentation/TechnicalManual.md` updated: `llm_base_url` config key, `POST /api/llm/fetch_models`, voice-input privacy note (no audio leaves the device — Web Speech API's implementation varies by browser; note this).
- [ ] `documentation/help.md` updated: "Using a different AI provider" section with the 6 presets + Azure-as-custom guidance.
- [ ] Privacy modal (Wave 1) data-flow table gets a new footnote: "Custom providers may route differently — check your provider's privacy policy."
- [ ] Setup guides (Wave 1): no changes needed — G1 and G2 remain OpenAI + Spotify.
- [ ] No Wave-5 surfaces started — no help.de.md split, no DE setup-guide screenshots.
- [ ] All new strings exist in both `en.json` and `de.json`.
- [ ] Project-tree section of `CLAUDE.md` updated with new JS modules and `pricing.json` asset.
- [ ] `pricing.json` `last_updated` field is set to the current release date.

---

## 15. Reference — surfaces you will touch in Wave 4

| File | Action |
|------|--------|
| `app.py` | Modify — `/api/settings` fields; new `/api/llm/fetch_models` |
| `config.py` | Modify — 4 new accessors |
| `core/src/openai_http.py` | Modify — base URL + api-key-optional plumbing |
| `frontend/templates/modals/settings_modal.html` | Modify — provider section + cost card |
| `frontend/templates/modals/credentials_modal.html` | Modify — dynamic API-key label |
| `frontend/templates/onboarding.html` | Modify — step 6 cost widget + provider expandable |
| `frontend/templates/train_profile.html` | Modify — voice button inside Vibe |
| `frontend/templates/generate_section.html` | Modify — cost footnote |
| `frontend/static/js/modules/provider.js` | Create |
| `frontend/static/js/modules/cost_estimate.js` | Create |
| `frontend/static/js/modules/voice.js` | Create |
| `frontend/static/js/modules/onboarding.js` | Modify — step 6 integration |
| `frontend/static/js/main.js` | Modify — bootstrap new modules |
| `frontend/static/css/provider.css` | Create |
| `frontend/static/css/cost_estimate.css` | Create |
| `frontend/static/css/voice.css` | Create |
| `frontend/static/data/pricing.json` | Create |
| `frontend/static/i18n/en.json` | Modify — § 9 keys |
| `frontend/static/i18n/de.json` | Modify — § 9 keys |
| `frontend/tests/test_documentation_screenshots.py` | Modify — tests 81–92 |
| `frontend/tests/test_frontend.py` | Modify — 6 smoke tests |
| `core/tests/test_openai_http.py` | Create / modify — base-URL plumbing tests |
| `documentation/UserManual.md`, `TechnicalManual.md`, `help.md` | Modify |

---

## 16. Opening contract for the implementer

You have full autonomy within Wave 4 scope. Do **not** implement anything outside it. When you believe Wave 4 is done, stop and say "Wave 4 complete — please review". Do not commit, do not push, do not start on Wave 5 — the user opens the next implementation file when ready.
