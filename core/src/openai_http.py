"""Direct HTTP client for the OpenAI REST API — no openai SDK required.

Uses only Python stdlib: urllib.request, urllib.error, json, time.

Endpoints used:
  POST /v1/chat/completions
"""

import json
import os
import socket
import time
import urllib.request
import urllib.error


# ── Exceptions ───────────────────────────────────────────────────────

class OpenAIError(Exception):
    """Base class for all OpenAI-related errors."""


class OpenAIConfigError(OpenAIError):
    """API key or configuration is missing or invalid."""

    key = "error.openai.config_missing"


class OpenAIRequestError(OpenAIError):
    """HTTP error returned by the OpenAI API."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OpenAIAuthError(OpenAIRequestError):
    """401 — API key rejected by OpenAI."""


class OpenAIRateLimitError(OpenAIRequestError):
    """429 — rate limit exceeded."""

    error_class = "transient"
    key = "error.transient.openai_rate_limited"


class OpenAITimeoutError(OpenAIError):
    """Request timed out before a response was received."""

    error_class = "transient"
    key = "error.transient.openai_slow"


class OpenAIResponseError(OpenAIError):
    """API response is present but has an unexpected structure."""


class OpenAIUnsupportedModelError(OpenAIError):
    """Model is locally blocked or was rejected by the API (400)."""

    key = "error.openai.unsupported_model"


# ── Configuration ────────────────────────────────────────────────────

_BASE_URL = "https://api.openai.com/v1"

# Combined connect + read timeout in seconds.
# Chat completions can be slow for large prompts, so this is generous.
_TIMEOUT = 130

# HTTP status codes that warrant a retry with exponential back-off.
_RETRY_STATUS = {429, 500, 502, 503, 504}


# ── Internal helpers ─────────────────────────────────────────────────

def _get_base_url() -> str:
    """Return the currently configured LLM base URL."""
    try:
        from config import get_llm_base_url
        return get_llm_base_url()
    except (ImportError, Exception):
        return _BASE_URL


def _is_openai_provider() -> bool:
    """Return True when the configured base URL points to OpenAI's API."""
    return _get_base_url().rstrip("/") == _BASE_URL


def _get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        # Wave 4: Local providers don't need a key
        try:
            from config import llm_api_key_required
            if not llm_api_key_required():
                return "not-needed"  # placeholder for Authorization header
        except ImportError:
            # Stand-alone test harness with no ``config`` module on the path.
            pass
        raise OpenAIConfigError(
            "OpenAI API key is not configured. "
            "Go to ⚙️ → Credentials to set it."
        )
    return key


def _make_headers(api_key: str) -> dict:
    # Never log the Authorization header — it contains the secret key.
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _request_json(method: str, path: str, body=None, retries: int = 1) -> dict:
    """Send a JSON request to the OpenAI REST API.

    Retries on transient server errors (429 / 5xx) with exponential
    back-off (2s, 4s, …).  Non-retriable errors (400, 401, other 4xx)
    are raised immediately without retrying.

    Args:
        method:  HTTP verb — "GET" or "POST".
        path:    API path relative to the base URL, e.g. "/chat/completions".
        body:    Python dict serialised as the JSON request body (POST only).
        retries: Number of additional attempts after the first failure.

    Returns:
        Parsed JSON response as a Python dict.

    Raises:
        OpenAIConfigError: No API key is configured.
        OpenAIAuthError: 401 response — key is invalid or revoked.
        OpenAIUnsupportedModelError: 400 with a model-related error message.
        OpenAIRateLimitError: 429 after all retries are exhausted.
        OpenAIRequestError: Any other HTTP error.
        OpenAITimeoutError: Request timed out on all attempts.
        OpenAIResponseError: Response body is present but not valid JSON.
    """
    api_key = _get_api_key()
    headers = _make_headers(api_key)
    base_url = _get_base_url()
    url = f"{base_url}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None

    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(2 ** attempt)  # 2 s, 4 s, …

        try:
            req = urllib.request.Request(
                url, data=data, headers=headers, method=method
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise OpenAIResponseError(
                        f"API returned non-JSON body: {raw[:200]}"
                    ) from exc

        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                body_bytes = exc.read()
                body_str = body_bytes.decode("utf-8", errors="replace")
            except (IOError, ValueError, OSError):
                body_str = ""

            # 401 — bad API key, raise immediately (no retry)
            if status == 401:
                raise OpenAIAuthError(
                    "Authentication failed — check your OpenAI API key.",
                    status_code=status,
                    response_body=body_str,
                )

            # 400 — bad request; if message mentions the model, surface that
            if status == 400:
                try:
                    err_json = json.loads(body_str)
                    msg = err_json.get("error", {}).get("message", "")
                except (json.JSONDecodeError, AttributeError):
                    msg = ""
                if "model" in msg.lower():
                    raise OpenAIUnsupportedModelError(
                        f"Model rejected by API: {msg}"
                    )
                raise OpenAIRequestError(
                    f"Bad request (400): {body_str[:300]}",
                    status_code=status,
                    response_body=body_str,
                )

            # Retriable server-side errors
            if status in _RETRY_STATUS:
                cls = OpenAIRateLimitError if status == 429 else OpenAIRequestError
                last_exc = cls(
                    f"OpenAI error ({status}): {body_str[:200]}",
                    status_code=status,
                    response_body=body_str,
                )
                continue  # retry

            # All other HTTP errors — raise immediately
            raise OpenAIRequestError(
                f"OpenAI API error ({status}): {body_str[:300]}",
                status_code=status,
                response_body=body_str,
            )

        except urllib.error.URLError as exc:
            inner = getattr(exc, "reason", exc)
            if isinstance(inner, (socket.timeout, TimeoutError)):
                last_exc = OpenAITimeoutError(f"Request timed out: {exc}")
            else:
                last_exc = OpenAIRequestError(f"Network error: {exc}")
            continue  # retry on network errors
        except socket.timeout as exc:
            last_exc = OpenAITimeoutError(f"Request timed out: {exc}")
            continue

    # All attempts failed — raise the last recorded exception
    if last_exc is not None:
        raise last_exc
    raise OpenAIRequestError("All retry attempts failed with no recorded error.")


# ── Public API ───────────────────────────────────────────────────────


def chat_completions_create(
    model: str,
    messages: list,
    temperature: float = 0.7,
    response_format: dict | None = None,
    prompt_cache_key: str | None = None,
) -> dict:
    """POST /v1/chat/completions — call the chat completions endpoint.

    Validates the model against the local allowlist before sending —
    raises OpenAIUnsupportedModelError immediately if the model is not
    in the list, avoiding a wasted API round-trip.

    OPEN-3 (2026-04-28): when ``response_format`` is a strict json_schema
    request and the model rejects it (HTTP 400 with "response_format" /
    "json_schema" / "schema" in the error message), we auto-downgrade
    once to ``{"type": "json_object"}`` and cache the result so future
    calls with the same model skip straight to json_object. This lets
    Stage 3 (the schema-collapse-prone path) opt into strict schemas
    on supported models without breaking models that don't.

    Args:
        model:           OpenAI model ID string.
        messages:        List of {"role", "content"} message dicts.
        temperature:     Sampling temperature (0–2).
        response_format: Optional format constraint, e.g.
                         {"type": "json_object"} or
                         {"type": "json_schema", "json_schema": {...}}.

    Returns:
        Parsed API response dict.

    Raises:
        OpenAIUnsupportedModelError: Model not in local allowlist.
        OpenAIConfigError: No API key configured.
        OpenAIAuthError: API key rejected.
        OpenAIRateLimitError: Rate limited after all retries.
        OpenAIRequestError: Other HTTP or network error.
        OpenAITimeoutError: Request timed out.
    """
    # Model allowlist only applies when targeting OpenAI's API.
    # Non-OpenAI providers (Ollama, LM Studio, Groq, etc.) use their own
    # model IDs which are not in the curated OpenAI list.
    if _is_openai_provider():
        from config import OPENAI_SUPPORTED_MODELS_JSON, OPENAI_EXTRA_ALLOWED_MODELS
        allowed = set(OPENAI_SUPPORTED_MODELS_JSON) | set(OPENAI_EXTRA_ALLOWED_MODELS)
        if model not in allowed:
            raise OpenAIUnsupportedModelError(
                f"Model '{model}' is not in the supported model list. "
                "Select a supported model in ⚙️ Settings."
            )

    # Some reasoning-tier models only accept the default temperature and
    # reject any explicit value. Configured in config.OPENAI_NO_TEMPERATURE_MODELS
    # so the next reasoning-tier model can be onboarded without code changes here.
    from config import OPENAI_NO_TEMPERATURE_MODELS
    payload: dict = {
        "model": model,
        "messages": messages,
    }
    if model not in OPENAI_NO_TEMPERATURE_MODELS:
        payload["temperature"] = temperature

    # OPEN-3: auto-downgrade strict json_schema for models that reject it.
    effective_response_format = response_format
    if (
        response_format is not None
        and isinstance(response_format, dict)
        and response_format.get("type") == "json_schema"
        and model in _JSON_SCHEMA_UNSUPPORTED
    ):
        effective_response_format = {"type": "json_object"}

    if effective_response_format is not None:
        payload["response_format"] = effective_response_format

    # C4 (2026-05-10) — `prompt_cache_key` is a routing hint that pins
    # the request to a host whose KV cache already holds the same prefix.
    # OpenAI auto-caches eligible prompts (>= 1024 tokens) but the cache
    # is per-host; without this hint the router load-balances across
    # hosts and most calls miss. With a stable key the hit rate stabilises.
    # Only sent on OpenAI provider — non-OpenAI compatibility-mode
    # endpoints may 400 on unknown fields.
    if prompt_cache_key and _is_openai_provider():
        payload["prompt_cache_key"] = prompt_cache_key

    try:
        return _request_json("POST", "/chat/completions", body=payload, retries=1)
    except OpenAIRequestError as exc:
        # Auto-downgrade if the model rejected json_schema and we haven't
        # already cached this fact. Single retry; never recurse.
        if (
            effective_response_format is not None
            and isinstance(effective_response_format, dict)
            and effective_response_format.get("type") == "json_schema"
            and exc.status_code == 400
            and _looks_like_schema_rejection(exc.response_body or str(exc))
        ):
            _JSON_SCHEMA_UNSUPPORTED.add(model)
            payload["response_format"] = {"type": "json_object"}
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "Model %s rejected json_schema response_format — "
                "auto-downgraded to json_object for this and future calls. "
                "Reject body: %s", model, (exc.response_body or "")[:200],
            )
            return _request_json("POST", "/chat/completions", body=payload, retries=1)
        raise


# OPEN-3 (2026-04-28): per-process cache of models known to reject strict
# json_schema response_format. Populated lazily on first 400 from the API
# so subsequent calls for the same model skip the failed handshake.
_JSON_SCHEMA_UNSUPPORTED: set[str] = set()


def _looks_like_schema_rejection(body: str) -> bool:
    """Heuristic — does this 400 body indicate the model can't do strict
    json_schema? Conservative: only downgrade on clear signals so that
    real bad-request errors (bad messages, bad model, etc.) keep raising.
    """
    if not body:
        return False
    b = body.lower()
    return (
        ("response_format" in b or "json_schema" in b or "json schema" in b)
        and ("not supported" in b or "unsupported" in b
             or "invalid" in b or "must be" in b
             or "does not support" in b or "schema" in b)
    )


def extract_chat_content(response: dict) -> str:
    """Extract the assistant's content string from a chat completions response.

    Args:
        response: Parsed API response dict from chat_completions_create().

    Returns:
        Stripped content string (may be empty if the model returned nothing).

    Raises:
        OpenAIResponseError: Response does not have the expected structure.
    """
    try:
        return (response["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIResponseError(
            f"Unexpected chat completion response structure: {exc}"
        ) from exc


def call_gpt_json(messages, temperature=0.7, label="GPT Call"):
    """Call GPT with JSON mode, parse the response, and return a dict.

    Combines the repeated pattern of:
        response = chat_completions_create(...)
        raw = extract_chat_content(response)
        debug_log(label, messages, raw)
        content = strip_code_fences(raw)
        result = json.loads(content)

    Args:
        messages:    List of {"role", "content"} message dicts.
        temperature: Sampling temperature (0–2).
        label:       Debug log label for this call.

    Returns:
        Parsed JSON dict from the GPT response.

    Raises:
        ValueError: If GPT returns empty or unparseable JSON.
    """
    result, _meta = call_gpt_json_with_meta(messages, temperature=temperature, label=label)
    return result


def call_gpt_json_with_meta(messages, temperature=0.7, label="GPT Call"):
    """Same as ``call_gpt_json`` but also returns telemetry meta.

    Returns ``(result, meta)`` where ``meta = {"usage": …, "latency_s": …,
    "model": "…", "raw_response_chars": int}``. Used by features that
    write per-call rows to the eval log (Band/Song Analysis, AI Profile
    Update, Stage 2 avoid-checker, etc.) so cost / latency / quality can be
    compared across model A/B variants.
    """
    from .utils import strip_code_fences, debug_log
    from config import get_model

    model = get_model()
    t0 = time.monotonic()
    response = chat_completions_create(
        model=model,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    latency_s = time.monotonic() - t0

    raw = extract_chat_content(response)
    debug_log(label, messages, raw)
    content = strip_code_fences(raw)

    usage = response.get("usage") if isinstance(response, dict) else None
    meta = {
        "usage": usage,
        "latency_s": latency_s,
        "model": model,
        "raw_response_chars": len(raw or ""),
    }

    if not content:
        raise ValueError(f"AI returned an empty response ({label}). Please try again.")

    try:
        return json.loads(content), meta
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI returned invalid JSON ({label}). Please try again.") from exc

