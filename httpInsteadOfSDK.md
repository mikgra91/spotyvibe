# Plan: Replace OpenAI Python SDK with direct HTTP calls (no openai package)

## Goal
Stop depending on the official OpenAI Python SDK (openai), and instead call the OpenAI REST API directly over HTTPS.

## Primary motivation:
Android/Chaquopy builds fail when newer SDK versions pull in Rust/native deps:
- [] openai>=1.35 → depends on jiter (Rust)
- [] pydantic>=2 → depends on pydantic-core (Rust)

Using plain HTTP + stdlib JSON avoids these transitive native builds entirely.

## Secondary benefits:
- [] Fewer dependencies and simpler dependency pinning.
- [] More predictable behavior across desktop + Android.

## Non-goals (initial migration):
- [] Streaming responses.
- [] Function calling/tools.
- [] Realtime/audio endpoints.
- [] Migrating from Chat Completions to the Responses API.

## Current OpenAI SDK usage (what we must replace)

### Where the SDK is imported/used

#### core/utils.py
- [] from openai import OpenAI
- [] get_openai_client() creates OpenAI(api_key=...) and caches it.
- [] get_openai_models() calls client.models.list() and filters model IDs.

#### core/suggestions.py
- [] call_gpt(...) calls:
  client.chat.completions.create(...)
- [] Expects response.choices[0].message.content.

#### core/profile.py
- [] Imports SDK typing: from openai.types.chat import ChatCompletionMessageParam
- [] train_profile(...) calls the same API.

#### core/analysis.py
- [] analyze_band_song(...) calls client.chat.completions.create(...).

## Features relied upon
- [] Chat Completions endpoint semantics
- [] Models list for Settings dropdown
- [] Debug logging of raw JSON
- [] No streaming currently

## Model filtering & JSON-mode compatibility

### Decision: curated allowlist.

Maintain a small list of known-good model IDs.

### Allowed vs displayed models

[] allowed_set = union of:
- OPENAI_SUPPORTED_MODELS_JSON
- OPENAI_EXTRA_ALLOWED_MODELS

[] display_set = allowed_set + current configured model if missing

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
- [] Preserve allowlist order
- [] Append unsupported configured model at end

## Server-side validation rules
Validate:
- [] non-empty
- [] valid JSON
- [] JSON object

## Where the allowlist lives
- [] config.py → OPENAI_SUPPORTED_MODELS_JSON
- [] optional OPENAI_EXTRA_ALLOWED_MODELS

## Proposed design: HTTP client wrapper

### core/openai_http.py

Responsibilities:
- [] Base URL config
- [] Timeouts
- [] Optional headers
- [] urllib + json usage
- [] Centralized retries & errors

### Canonical exceptions
- [] OpenAIError
- [] OpenAIConfigError
- [] OpenAIRequestError
- [] OpenAIAuthError
- [] OpenAIRateLimitError
- [] OpenAITimeoutError
- [] OpenAIResponseError
- [] OpenAIUnsupportedModelError

### Core helper
_request_json(...)

### Retry behavior
- [] Retry on: 429, 500, 502, 503, 504
- [] models: 2 retries
- [] chat: 1 retry

### Headers
Required:
- [] Authorization: Bearer API key
- [] Content-Type: application/json

### Logging
- [] Never log API key
- [] Redact sensitive headers

### Public wrapper functions
- [] list_models()
- [] chat_completions_create(...)
- [] extract_chat_content(...)

## Migration plan

### Step 0 — Scope
Use only:
- [] POST /v1/chat/completions
- [] GET /v1/models

### Step 1 — Add HTTP module
Create core/openai_http.py

### Step 2 — Replace SDK usage
Update:
- [] core/utils.py
- [] core/suggestions.py
- [] core/profile.py
- [] core/analysis.py

### Step 3 — Remove SDK dependency
- [] requirements.txt
- [] android/app/build.gradle

### Step 4 — Update tests
- [] Mock HTTP wrapper
- [] Add test_openai_http.py

### Step 5 — Documentation updates
Update:
- [] README.md
- [] UserManual.md
- [] TechnicalManual.md
- [] AGENTS.md

### Step 6 — Validation
Desktop + Android tests and smoke checks

## Risks / considerations
- [] Rate limits
- [] Retry cost duplication
- [] Timeouts
- [] Proxy handling
- [] API evolution
- [] Stdlib HTTP limitations

## Rollout strategy
- [] Implement wrapper
- [] Migrate callsites
- [] Remove SDK
- [] Test

## Acceptance criteria
- [] No openai dependency
- [] Android build succeeds
- [] Functionality preserved
- [] Unsupported models handled clearly
- [] Tests passing
- [] No secrets in logs
