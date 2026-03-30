# Plan: Replace OpenAI Python SDK with direct HTTP calls (no openai package)

## Goal
Stop depending on the official OpenAI Python SDK (openai), and instead call the OpenAI REST API directly over HTTPS.

## Primary motivation:
Android/Chaquopy builds fail when newer SDK versions pull in Rust/native deps:
- [X] openai>=1.35 → depends on jiter (Rust)
- [X] pydantic>=2 → depends on pydantic-core (Rust)

Using plain HTTP + stdlib JSON avoids these transitive native builds entirely.

## Secondary benefits:
- [X] Fewer dependencies and simpler dependency pinning.
- [X] More predictable behavior across desktop + Android.

## Non-goals (initial migration):
- [X] Streaming responses.
- [X] Function calling/tools.
- [X] Realtime/audio endpoints.
- [X] Migrating from Chat Completions to the Responses API.

## Current OpenAI SDK usage (what we must replace)

### Where the SDK is imported/used

#### core/utils.py
- [X] from openai import OpenAI
- [X] get_openai_client() creates OpenAI(api_key=...) and caches it.
- [X] get_openai_models() calls client.models.list() and filters model IDs.

#### core/suggestions.py
- [X] call_gpt(...) calls:
  client.chat.completions.create(...)
- [X] Expects response.choices[0].message.content.

#### core/profile.py
- [X] Imports SDK typing: from openai.types.chat import ChatCompletionMessageParam
- [X] train_profile(...) calls the same API.

#### core/analysis.py
- [X] analyze_band_song(...) calls client.chat.completions.create(...).

## Features relied upon
- [X] Chat Completions endpoint semantics
- [X] Models list for Settings dropdown
- [X] Debug logging of raw JSON
- [X] No streaming currently

## Model filtering & JSON-mode compatibility

### Decision: curated allowlist.

Maintain a small list of known-good model IDs.

### Allowed vs displayed models

[X] allowed_set = union of:
- OPENAI_SUPPORTED_MODELS_JSON
- OPENAI_EXTRA_ALLOWED_MODELS

[X] display_set = allowed_set + current configured model if missing

## Unsupported-model handling

### Locally unsupported:
Raise OpenAIUnsupportedModelError before API call.

### API-rejected:
Normalize 400 responses to OpenAIUnsupportedModelError.

## UI contract for model list

Structured model objects:
[
  {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini", "supported": true},
  {"id": "custom-model", "label": "custom-model (unsupported)", "supported": false}
]

## Model ordering
- [X] Preserve allowlist order
- [X] Append unsupported configured model at end

## Server-side validation rules
Validate:
- [X] non-empty
- [X] valid JSON
- [X] JSON object

## Where the allowlist lives
- [X] config.py → OPENAI_SUPPORTED_MODELS_JSON
- [X] optional OPENAI_EXTRA_ALLOWED_MODELS

## Proposed design: HTTP client wrapper

### core/openai_http.py

Responsibilities:
- [X] Base URL config
- [X] Timeouts
- [X] Optional headers
- [X] urllib + json usage
- [X] Centralized retries & errors

### Canonical exceptions
- [X] OpenAIError
- [X] OpenAIConfigError
- [X] OpenAIRequestError
- [X] OpenAIAuthError
- [X] OpenAIRateLimitError
- [X] OpenAITimeoutError
- [X] OpenAIResponseError
- [X] OpenAIUnsupportedModelError

### Core helper
_request_json(...)

### Retry behavior
- [X] Retry on: 429, 500, 502, 503, 504
- [X] models: 2 retries
- [X] chat: 1 retry

### Headers
Required:
- [X] Authorization: Bearer API key
- [X] Content-Type: application/json

### Logging
- [X] Never log API key
- [X] Redact sensitive headers

### Public wrapper functions
- [X] list_models()
- [X] chat_completions_create(...)
- [X] extract_chat_content(...)

## Migration plan

### Step 0 — Scope
Use only:
- [X] POST /v1/chat/completions
- [X] GET /v1/models

### Step 1 — Add HTTP module
Create core/openai_http.py

### Step 2 — Replace SDK usage
Update:
- [X] core/utils.py
- [X] core/suggestions.py
- [X] core/profile.py
- [X] core/analysis.py

### Step 3 — Remove SDK dependency
- [X] requirements.txt
- [X] android/app/build.gradle

### Step 4 — Update tests
- [X] Mock HTTP wrapper
- [X] Add test_openai_http.py

### Step 5 — Documentation updates
Update:
- [X] README.md
- [X] UserManual.md
- [X] TechnicalManual.md
- [X] AGENTS.md

### Step 6 — Validation
Desktop + Android tests and smoke checks

## Risks / considerations
- [X] Rate limits
- [X] Retry cost duplication
- [X] Timeouts
- [X] Proxy handling
- [X] API evolution
- [X] Stdlib HTTP limitations

## Rollout strategy
- [X] Implement wrapper
- [X] Migrate callsites
- [X] Remove SDK
- [X] Test

## Acceptance criteria
- [X] No openai dependency
- [X] Android build succeeds
- [X] Functionality preserved
- [X] Unsupported models handled clearly
- [X] Tests passing
- [X] No secrets in logs
