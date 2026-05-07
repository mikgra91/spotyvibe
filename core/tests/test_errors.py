"""Tests for core.src.errors — translatable error helpers."""
import pytest

from core.src.errors import TranslatableError, as_response_payload
from core.src.openai_http import OpenAIConfigError, OpenAIUnsupportedModelError


class TestTranslatableError:
    def test_carries_key_message_and_default_status(self):
        exc = TranslatableError("error.foo", "Foo failed.")
        assert exc.key == "error.foo"
        assert exc.message == "Foo failed."
        assert str(exc) == "Foo failed."
        assert exc.status_code == 400
        assert exc.params is None

    def test_custom_status_and_params(self):
        exc = TranslatableError(
            "error.bar",
            "Bar failed: {detail}",
            params={"detail": "x"},
            status_code=503,
        )
        assert exc.status_code == 503
        assert exc.params == {"detail": "x"}


class TestAsResponsePayload:
    def test_translatable_error_includes_key(self):
        exc = TranslatableError("error.foo", "Foo.")
        payload = as_response_payload(exc)
        assert payload == {
            "error": "Foo.",
            "error_key": "error.foo",
            "error_class": "permanent",
        }

    def test_translatable_error_includes_params(self):
        exc = TranslatableError(
            "error.foo", "Foo {n}", params={"n": "42"},
        )
        payload = as_response_payload(exc)
        assert payload["error_params"] == {"n": "42"}

    def test_plain_exception_omits_key(self):
        exc = RuntimeError("boom")
        payload = as_response_payload(exc)
        assert payload == {"error": "boom"}
        assert "error_key" not in payload

    def test_openai_config_error_carries_key(self):
        exc = OpenAIConfigError("API key missing")
        payload = as_response_payload(exc)
        assert payload["error_key"] == "error.openai.config_missing"

    def test_openai_unsupported_model_error_carries_key(self):
        exc = OpenAIUnsupportedModelError("Model 'x' not supported")
        payload = as_response_payload(exc)
        assert payload["error_key"] == "error.openai.unsupported_model"

    def test_blank_key_attribute_omitted(self):
        class BlankKeyError(Exception):
            key = ""

        payload = as_response_payload(BlankKeyError("oops"))
        assert "error_key" not in payload


class TestErrorClass:
    """U2: transient vs permanent classification surfaces in payload."""

    def test_default_error_class_is_permanent(self):
        exc = TranslatableError("error.foo", "Foo.")
        assert exc.error_class == "permanent"
        payload = as_response_payload(exc)
        assert payload["error_class"] == "permanent"

    def test_transient_error_class_propagates(self):
        exc = TranslatableError(
            "error.transient.x", "Slow.", error_class="transient",
        )
        payload = as_response_payload(exc)
        assert payload["error_class"] == "transient"

    def test_unknown_error_class_value_is_dropped(self):
        exc = TranslatableError(
            "error.foo", "Foo.", error_class="bogus",
        )
        payload = as_response_payload(exc)
        assert "error_class" not in payload

    def test_error_class_attribute_on_plain_exception(self):
        class RateLimit(Exception):
            error_class = "transient"
            key = "error.transient.foo"

        payload = as_response_payload(RateLimit("slow"))
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.foo"

    def test_openai_rate_limit_is_transient(self):
        from core.src.openai_http import OpenAIRateLimitError

        exc = OpenAIRateLimitError("429", status_code=429)
        payload = as_response_payload(exc)
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.openai_rate_limited"

    def test_openai_timeout_is_transient(self):
        from core.src.openai_http import OpenAITimeoutError

        exc = OpenAITimeoutError("timed out")
        payload = as_response_payload(exc)
        assert payload["error_class"] == "transient"
        assert payload["error_key"] == "error.transient.openai_slow"
