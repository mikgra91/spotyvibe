"""Tests for core/openai_http.py — direct HTTP OpenAI client."""

import json
import os
import urllib.error
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from core.src.openai_http import (
    OpenAIError,
    OpenAIConfigError,
    OpenAIRequestError,
    OpenAIAuthError,
    OpenAIRateLimitError,
    OpenAITimeoutError,
    OpenAIResponseError,
    OpenAIUnsupportedModelError,
    _get_api_key,
    _request_json,
    chat_completions_create,
    extract_chat_content,
)


# ── _get_api_key ─────────────────────────────────────────────────────

class TestGetApiKey:
    def test_raises_when_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OpenAIConfigError, match="not configured"):
                _get_api_key()

    def test_returns_key_when_set(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            assert _get_api_key() == "sk-test"


# ── _request_json ────────────────────────────────────────────────────

def _make_http_error(status, body=""):
    """Helper: build a urllib.error.HTTPError with a readable body."""
    err = urllib.error.HTTPError(
        url="https://api.openai.com/v1/test",
        code=status,
        msg="Error",
        hdrs={},
        fp=BytesIO(body.encode("utf-8")),
    )
    return err


class TestRequestJson:
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("urllib.request.urlopen")
    def test_success_get(self, mock_urlopen):
        response_body = json.dumps({"data": [{"id": "gpt-4o"}]}).encode("utf-8")
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = response_body
        mock_urlopen.return_value = mock_ctx

        result = _request_json("GET", "/models", retries=0)
        assert result == {"data": [{"id": "gpt-4o"}]}

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("urllib.request.urlopen")
    def test_raises_auth_error_on_401(self, mock_urlopen):
        mock_urlopen.side_effect = _make_http_error(401, '{"error": {"message": "Invalid key"}}')
        with pytest.raises(OpenAIAuthError):
            _request_json("GET", "/models", retries=0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("urllib.request.urlopen")
    def test_raises_unsupported_model_on_400_with_model_msg(self, mock_urlopen):
        body = json.dumps({"error": {"message": "The model does not exist"}})
        mock_urlopen.side_effect = _make_http_error(400, body)
        with pytest.raises(OpenAIUnsupportedModelError, match="Model rejected"):
            _request_json("POST", "/chat/completions", body={}, retries=0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("urllib.request.urlopen")
    def test_raises_request_error_on_400_non_model(self, mock_urlopen):
        body = json.dumps({"error": {"message": "Bad parameter foo"}})
        mock_urlopen.side_effect = _make_http_error(400, body)
        with pytest.raises(OpenAIRequestError) as exc_info:
            _request_json("POST", "/chat/completions", body={}, retries=0)
        assert exc_info.value.status_code == 400

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_retries_on_429_then_succeeds(self, mock_urlopen, mock_sleep):
        success_body = json.dumps({"ok": True}).encode("utf-8")
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = success_body

        mock_urlopen.side_effect = [
            _make_http_error(429, "rate limited"),
            mock_ctx,
        ]

        result = _request_json("GET", "/models", retries=1)
        assert result == {"ok": True}
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_raises_rate_limit_after_all_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _make_http_error(429, "rate limited")
        with pytest.raises(OpenAIRateLimitError):
            _request_json("GET", "/models", retries=1)
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("urllib.request.urlopen")
    def test_raises_response_error_on_non_json_body(self, mock_urlopen):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.read.return_value = b"not json at all"
        mock_urlopen.return_value = mock_ctx

        with pytest.raises(OpenAIResponseError, match="non-JSON"):
            _request_json("GET", "/models", retries=0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_raises_timeout_error_on_socket_timeout(self, mock_urlopen, mock_sleep):
        import socket
        mock_urlopen.side_effect = urllib.error.URLError(socket.timeout("timed out"))
        with pytest.raises(OpenAITimeoutError):
            _request_json("GET", "/models", retries=0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http.time.sleep")
    @patch("urllib.request.urlopen")
    def test_raises_timeout_error_on_bare_socket_timeout(self, mock_urlopen, mock_sleep):
        import socket
        mock_urlopen.side_effect = socket.timeout("timed out")
        with pytest.raises(OpenAITimeoutError):
            _request_json("GET", "/models", retries=0)

    def test_raises_config_error_when_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OpenAIConfigError):
                _request_json("GET", "/models", retries=0)



# ── chat_completions_create ──────────────────────────────────────────

class TestChatCompletionsCreate:
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_calls_endpoint_with_correct_body(self, mock_req):
        mock_req.return_value = {
            "choices": [{"message": {"content": '{"playlist": []}'}}]
        }
        messages = [{"role": "user", "content": "hello"}]
        chat_completions_create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        mock_req.assert_called_once_with(
            "POST",
            "/chat/completions",
            body={
                "model": "gpt-4.1-mini",
                "messages": messages,
                "temperature": 0.5,
                "response_format": {"type": "json_object"},
            },
            retries=1,
        )

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_omits_response_format_when_none(self, mock_req):
        mock_req.return_value = {"choices": [{"message": {"content": "hi"}}]}
        chat_completions_create(model="gpt-4.1-mini", messages=[])
        body = mock_req.call_args[1]["body"]
        assert "response_format" not in body

    @patch.dict(os.environ, {"LLM_BASE_URL": "https://api.openai.com/v1"})
    def test_raises_unsupported_model_error_for_unknown_model(self):
        # Model allowlist only fires on the OpenAI provider; defaults
        # were flipped to OpenRouter on 2026-05-14 so the test now pins
        # the base URL explicitly.
        with pytest.raises(OpenAIUnsupportedModelError, match="not in the supported model list"):
            chat_completions_create(model="totally-fake-model", messages=[])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "LLM_BASE_URL": "https://api.openai.com/v1"})
    @patch("core.src.openai_http._request_json")
    def test_passes_prompt_cache_key_to_payload(self, mock_req):
        # C4 (2026-05-10): the routing hint must reach OpenAI verbatim
        # so the cache router can pin the request to a host with the
        # matching prefix already loaded. prompt_cache_key is OpenAI-only
        # — must pin LLM_BASE_URL since the default is now OR.
        mock_req.return_value = {"choices": [{"message": {"content": "hi"}}]}
        chat_completions_create(
            model="gpt-4.1-mini",
            messages=[],
            prompt_cache_key="sv-stage3:gpt-4.1-mini:English:0",
        )
        body = mock_req.call_args[1]["body"]
        assert body["prompt_cache_key"] == "sv-stage3:gpt-4.1-mini:English:0"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_omits_prompt_cache_key_when_unset(self, mock_req):
        # Default callers (analysis, profile-update) don't pass the hint;
        # we must NOT inject a stray field that some compatibility-mode
        # endpoints may reject.
        mock_req.return_value = {"choices": [{"message": {"content": "hi"}}]}
        chat_completions_create(model="gpt-4.1-mini", messages=[])
        body = mock_req.call_args[1]["body"]
        assert "prompt_cache_key" not in body

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._is_openai_provider", return_value=False)
    @patch("core.src.openai_http._request_json")
    def test_omits_prompt_cache_key_on_local_provider(self, mock_req, _mock_is_openai):
        # Local / OpenAI-compatibility-mode endpoints (Ollama, LM Studio)
        # may 400 on unknown payload fields. The hint is OpenAI-only.
        mock_req.return_value = {"choices": [{"message": {"content": "hi"}}]}
        chat_completions_create(
            model="llama3.1:8b",
            messages=[],
            prompt_cache_key="sv-stage3:llama3.1:8b:English:0",
        )
        body = mock_req.call_args[1]["body"]
        assert "prompt_cache_key" not in body


# ── extract_chat_content ─────────────────────────────────────────────

class TestExtractChatContent:
    def test_extracts_content_string(self):
        response = {"choices": [{"message": {"content": "Hello!"}}]}
        assert extract_chat_content(response) == "Hello!"

    def test_strips_whitespace(self):
        response = {"choices": [{"message": {"content": "  hello  "}}]}
        assert extract_chat_content(response) == "hello"

    def test_handles_none_content(self):
        response = {"choices": [{"message": {"content": None}}]}
        assert extract_chat_content(response) == ""

    def test_raises_on_missing_choices(self):
        with pytest.raises(OpenAIResponseError):
            extract_chat_content({})

    def test_raises_on_empty_choices(self):
        with pytest.raises(OpenAIResponseError):
            extract_chat_content({"choices": []})

    def test_raises_on_wrong_structure(self):
        with pytest.raises(OpenAIResponseError):
            extract_chat_content({"choices": [{"no_message": True}]})


# ── Exception hierarchy ──────────────────────────────────────────────

class TestExceptionHierarchy:
    def test_auth_error_is_request_error(self):
        assert issubclass(OpenAIAuthError, OpenAIRequestError)

    def test_rate_limit_error_is_request_error(self):
        assert issubclass(OpenAIRateLimitError, OpenAIRequestError)

    def test_request_error_is_openai_error(self):
        assert issubclass(OpenAIRequestError, OpenAIError)

    def test_config_error_is_openai_error(self):
        assert issubclass(OpenAIConfigError, OpenAIError)

    def test_timeout_error_is_openai_error(self):
        assert issubclass(OpenAITimeoutError, OpenAIError)

    def test_response_error_is_openai_error(self):
        assert issubclass(OpenAIResponseError, OpenAIError)

    def test_unsupported_model_error_is_openai_error(self):
        assert issubclass(OpenAIUnsupportedModelError, OpenAIError)

    def test_request_error_stores_status_code(self):
        err = OpenAIRequestError("msg", status_code=429, response_body="body")
        assert err.status_code == 429
        assert err.response_body == "body"


# ── C10: Base URL and local provider tests ───────────────────────────

class TestBaseUrlAndLocalProvider:
    """C10: Tests for custom base URL and local providers (Wave 4)."""

    def test_uses_configured_base_url(self):
        """_request_json should use the base URL from config."""
        custom_url = "http://localhost:11434/v1"
        response_body = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("core.src.openai_http._get_base_url", return_value=custom_url), \
             patch("core.src.openai_http._get_api_key", return_value="test-key"), \
             patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = _request_json("POST", "/chat/completions", body={"model": "llama3"})

        # Verify the URL used starts with the custom base URL
        actual_request = mock_urlopen.call_args[0][0]
        assert actual_request.full_url.startswith(custom_url)
        assert result["choices"][0]["message"]["content"] == "hi"

    def test_local_provider_skips_key_requirement(self):
        """When llm_api_key_required returns False, _get_api_key should return 'not-needed'."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("config.llm_api_key_required", return_value=False):
            key = _get_api_key()
        assert key == "not-needed"

    def test_raises_when_no_key_and_required(self):
        """When llm_api_key_required returns True (or not available), should raise."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("config.llm_api_key_required", return_value=True):
            with pytest.raises(OpenAIConfigError, match="not configured"):
                _get_api_key()

# ── OPEN-3 (2026-04-28): json_schema auto-downgrade ──
class TestJsonSchemaAutoDowngrade:
    """When the model rejects strict json_schema with a 400, the client
    should auto-downgrade to json_object once and cache the rejection."""
    def setup_method(self):
        # Reset the per-process cache between tests.
        from core.src import openai_http as _oh
        _oh._JSON_SCHEMA_UNSUPPORTED.clear()
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_passes_json_schema_through_when_supported(self, mock_req):
        from core.src.openai_http import chat_completions_create
        mock_req.return_value = {"choices": [{"message": {"content": "{}"}}]}
        rf = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {}}}
        chat_completions_create(model="gpt-4.1-mini", messages=[], response_format=rf)
        # Single call, payload carries the strict schema.
        assert mock_req.call_count == 1
        body = mock_req.call_args.kwargs["body"]
        assert body["response_format"] == rf
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_downgrades_to_json_object_on_400_schema_reject(self, mock_req):
        from core.src.openai_http import (chat_completions_create,
                                          OpenAIRequestError,
                                          _JSON_SCHEMA_UNSUPPORTED)
        def _side(method, path, body=None, retries=1):
            if body and body.get("response_format", {}).get("type") == "json_schema":
                raise OpenAIRequestError(
                    "bad request",
                    status_code=400,
                    response_body=(
                        '{"error":{"message":"response_format json_schema '
                        'is not supported for this model"}}'
                    ),
                )
            return {"choices": [{"message": {"content": "{}"}}]}
        mock_req.side_effect = _side
        rf = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {}}}
        chat_completions_create(model="gpt-4.1-mini", messages=[], response_format=rf)
        # Two calls — the first failed, the second succeeded with json_object.
        assert mock_req.call_count == 2
        retry_body = mock_req.call_args_list[1].kwargs["body"]
        assert retry_body["response_format"] == {"type": "json_object"}
        # Cache is now populated.
        assert "gpt-4.1-mini" in _JSON_SCHEMA_UNSUPPORTED
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_uses_json_object_directly_when_cached(self, mock_req):
        from core.src.openai_http import (chat_completions_create,
                                          _JSON_SCHEMA_UNSUPPORTED)
        _JSON_SCHEMA_UNSUPPORTED.add("gpt-4.1-mini")
        mock_req.return_value = {"choices": [{"message": {"content": "{}"}}]}
        rf = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {}}}
        chat_completions_create(model="gpt-4.1-mini", messages=[], response_format=rf)
        # Single call, direct json_object — no probing for the schema.
        assert mock_req.call_count == 1
        body = mock_req.call_args.kwargs["body"]
        assert body["response_format"] == {"type": "json_object"}
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("core.src.openai_http._request_json")
    def test_does_not_downgrade_unrelated_400(self, mock_req):
        from core.src.openai_http import (chat_completions_create,
                                          OpenAIRequestError,
                                          _JSON_SCHEMA_UNSUPPORTED)
        mock_req.side_effect = OpenAIRequestError(
            "bad messages format",
            status_code=400,
            response_body='{"error":{"message":"messages array is empty"}}',
        )
        rf = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {}}}
        with pytest.raises(OpenAIRequestError):
            chat_completions_create(model="gpt-4.1-mini", messages=[], response_format=rf)
        # No downgrade, no cache pollution.
        assert "gpt-4.1-mini" not in _JSON_SCHEMA_UNSUPPORTED


# ── S8: direct unit tests for the rejection heuristic ──
class TestLooksLikeSchemaRejection:
    """Direct coverage of the heuristic itself, independent of the
    chat_completions_create wrapper. Local-LLM compatibility regressions
    here would silently break every Ollama / LM Studio / Groq user, so
    the rule deserves its own pinned test surface."""

    def test_empty_body_returns_false(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection("") is False
        assert _looks_like_schema_rejection(None) is False  # type: ignore[arg-type]

    def test_openai_style_unsupported_message_matches(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection(
            '{"error":{"message":"response_format json_schema is not supported '
            'for this model"}}'
        ) is True

    def test_lm_studio_style_unsupported_matches(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection(
            "model does not support json_schema response_format"
        ) is True

    def test_invalid_response_format_matches(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection(
            "invalid response_format: must be one of text|json_object"
        ) is True

    def test_case_insensitive(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection(
            "RESPONSE_FORMAT JSON_SCHEMA NOT SUPPORTED"
        ) is True

    def test_unrelated_400_returns_false(self):
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection(
            '{"error":{"message":"messages array is empty"}}'
        ) is False
        assert _looks_like_schema_rejection(
            '{"error":{"message":"context length exceeded"}}'
        ) is False
        assert _looks_like_schema_rejection(
            '{"error":{"message":"rate limit reached"}}'
        ) is False

    def test_signal_word_alone_does_not_match(self):
        """Bare 'invalid' or 'unsupported' without any schema/format keyword
        must not flip the heuristic — that's how genuine 400s leak into
        the auto-downgrade path."""
        from core.src.openai_http import _looks_like_schema_rejection
        assert _looks_like_schema_rejection("invalid model id") is False
        assert _looks_like_schema_rejection("model unsupported") is False
