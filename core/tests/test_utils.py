import os
from unittest.mock import patch, MagicMock, mock_open

import json

import pytest

from core.src.utils import strip_code_fences, loads_lenient, debug_log, clear_debug_log, app_log, get_openai_models, sanitize_text, sanitize_profile


class TestLoadsLenient:
    def test_plain_json(self):
        assert loads_lenient('{"playlist": []}') == {"playlist": []}

    def test_trailing_prose(self):
        """Claude Haiku appends an explanatory sentence after the JSON —
        standard json.loads raises 'Extra data'. loads_lenient ignores it."""
        text = '{"playlist": [{"artist": "a"}]}\n\nZero is correct here.'
        assert loads_lenient(text) == {"playlist": [{"artist": "a"}]}

    def test_leading_prose(self):
        text = 'Here is the JSON:\n{"playlist": []}'
        assert loads_lenient(text) == {"playlist": []}

    def test_prose_both_sides(self):
        text = 'Result:\n{"ok": true}\nDone.'
        assert loads_lenient(text) == {"ok": True}

    def test_no_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            loads_lenient("no json at all")


class TestStripCodeFences:
    def test_plain_json_unchanged(self):
        text = '{"key": "value"}'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_multiline(self):
        text = '```json\n{\n  "list": [1, 2, 3]\n}\n```'
        assert strip_code_fences(text) == '{\n  "list": [1, 2, 3]\n}'

    def test_no_fence_passthrough(self):
        assert strip_code_fences("plain text") == "plain text"

    def test_surrounding_whitespace(self):
        text = '  \n```json\n{}\n```\n  '
        assert strip_code_fences(text) == '{}'

    def test_opening_fence_only(self):
        text = '```json\n{"key": "value"}'
        # Only opening fence, no closing — still strips the opening line
        assert strip_code_fences(text) == '{"key": "value"}'


class TestDebugLog:
    @patch("core.src.utils.get_debug_mode", return_value=False)
    def test_skips_when_debug_off(self, mock_mode, tmp_path):
        """debug_log should not write anything when debug mode is disabled."""
        log_file = tmp_path / "prompt.log"
        with patch("core.src.utils.PROMPT_LOG_FILE", log_file):
            debug_log("Test", [{"role": "user", "content": "hi"}], '{"ok": true}')
        assert not log_file.exists()

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_writes_when_debug_on(self, mock_mode, tmp_path):
        """debug_log should write label, messages, and response to prompt.log."""
        log_file = tmp_path / "prompt.log"
        with patch("core.src.utils.PROMPT_LOG_FILE", log_file):
            messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
            debug_log("TestLabel", messages, '{"result": "ok"}')
        content = log_file.read_text()
        assert "TestLabel" in content
        assert "[SYSTEM]" in content
        assert "[USER]" in content
        assert "hello" in content
        assert '"result": "ok"' in content

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_handles_non_json_response(self, mock_mode, tmp_path):
        log_file = tmp_path / "prompt.log"
        with patch("core.src.utils.PROMPT_LOG_FILE", log_file):
            debug_log("Test", [{"role": "user", "content": "hi"}], "not json")
        content = log_file.read_text()
        assert "not json" in content

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_appends_to_existing_log(self, mock_mode, tmp_path):
        log_file = tmp_path / "prompt.log"
        log_file.write_text("previous content\n")
        with patch("core.src.utils.PROMPT_LOG_FILE", log_file):
            debug_log("New", [{"role": "user", "content": "msg"}], "resp")
        content = log_file.read_text()
        assert "previous content" in content
        assert "New" in content


class TestAppLog:
    @patch("core.src.utils.get_debug_mode", return_value=False)
    def test_skips_when_debug_off(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            app_log("test event")
        assert not log_file.exists()

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_writes_when_debug_on(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            app_log("server started")
        content = log_file.read_text()
        assert "server started" in content

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_includes_timestamp(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            app_log("check timestamp")
        content = log_file.read_text()
        assert "UTC" in content

    @patch("core.src.utils.get_debug_mode", return_value=True)
    def test_appends_to_existing_log(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        log_file.write_text("previous line\n")
        with patch("core.src.utils.DEBUG_LOG_FILE", log_file):
            app_log("new event")
        content = log_file.read_text()
        assert "previous line" in content
        assert "new event" in content


class TestClearDebugLog:
    def test_deletes_debug_log(self, tmp_path):
        debug_file = tmp_path / "debug.log"
        debug_file.write_text("debug data")
        prompt_file = tmp_path / "prompt.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", debug_file), \
             patch("core.src.utils.PROMPT_LOG_FILE", prompt_file):
            clear_debug_log()
        assert not debug_file.exists()

    def test_deletes_prompt_log(self, tmp_path):
        debug_file = tmp_path / "debug.log"
        prompt_file = tmp_path / "prompt.log"
        prompt_file.write_text("prompt data")
        with patch("core.src.utils.DEBUG_LOG_FILE", debug_file), \
             patch("core.src.utils.PROMPT_LOG_FILE", prompt_file):
            clear_debug_log()
        assert not prompt_file.exists()

    def test_deletes_both_files(self, tmp_path):
        debug_file = tmp_path / "debug.log"
        debug_file.write_text("debug data")
        prompt_file = tmp_path / "prompt.log"
        prompt_file.write_text("prompt data")
        with patch("core.src.utils.DEBUG_LOG_FILE", debug_file), \
             patch("core.src.utils.PROMPT_LOG_FILE", prompt_file):
            clear_debug_log()
        assert not debug_file.exists()
        assert not prompt_file.exists()

    def test_no_error_when_files_missing(self, tmp_path):
        debug_file = tmp_path / "debug.log"
        prompt_file = tmp_path / "prompt.log"
        with patch("core.src.utils.DEBUG_LOG_FILE", debug_file), \
             patch("core.src.utils.PROMPT_LOG_FILE", prompt_file):
            clear_debug_log()  # should not raise


class TestSanitizeText:
    def test_removes_null_bytes(self):
        assert sanitize_text("hello\x00world") == "helloworld"

    def test_removes_control_characters(self):
        assert sanitize_text("hello\x01\x02world") == "helloworld"

    def test_preserves_newlines_and_tabs(self):
        result = sanitize_text("line1\nline2\ttab")
        assert "\n" in result
        # tabs are collapsed to single space by the regex
        assert "line2 tab" in result

    def test_collapses_spaces(self):
        assert sanitize_text("hello     world") == "hello world"

    def test_strips_whitespace(self):
        assert sanitize_text("  hello  ") == "hello"

    def test_non_string_passthrough(self):
        assert sanitize_text(42) == ""
        assert sanitize_text(None) == ""


class TestSanitizeProfile:
    def test_sanitizes_nested_dict(self):
        profile = {"a": "hello\x00", "b": {"c": "world\x01"}}
        result = sanitize_profile(profile)
        assert result["a"] == "hello"
        assert result["b"]["c"] == "world"

    def test_sanitizes_list_values(self):
        profile = {"items": ["a\x00b", "c\x01d"]}
        result = sanitize_profile(profile)
        assert result["items"] == ["ab", "cd"]

    def test_preserves_non_strings(self):
        profile = {"count": 5, "flag": True, "items": [1, 2]}
        assert sanitize_profile(profile) == profile


class TestGetOpenaiModels:
    def test_returns_list_of_dicts(self):
        """get_openai_models returns structured objects with id, label, supported."""
        models = get_openai_models()
        assert isinstance(models, list)
        assert len(models) > 0
        for m in models:
            assert "id" in m
            assert "label" in m
            assert "supported" in m

    def test_supported_models_are_marked_true(self):
        models = get_openai_models()
        supported = [m for m in models if m["supported"]]
        assert len(supported) > 0
        # All supported model labels should not contain "(unsupported)"
        for m in supported:
            assert "(unsupported)" not in m["label"]

    def test_includes_default_model(self):
        models = get_openai_models()
        ids = [m["id"] for m in models]
        assert "gpt-4.1-mini" in ids

    def test_appends_configured_model_if_not_in_allowlist(self):
        with patch("core.src.utils.get_model", return_value="custom-preview-model"):
            models = get_openai_models()
        ids = [m["id"] for m in models]
        assert "custom-preview-model" in ids
        custom = next(m for m in models if m["id"] == "custom-preview-model")
        assert custom["supported"] is False
        assert "(unsupported)" in custom["label"]
        # Unsupported model should be appended at the end
        assert models[-1]["id"] == "custom-preview-model"

    def test_does_not_duplicate_if_configured_model_in_allowlist(self):
        with patch("core.src.utils.get_model", return_value="gpt-4.1-mini"):
            models = get_openai_models()
        count = sum(1 for m in models if m["id"] == "gpt-4.1-mini")
        assert count == 1

    def test_preserves_allowlist_order(self):
        from config import OPENAI_SUPPORTED_MODELS_JSON
        with patch("core.src.utils.get_model", return_value="gpt-4.1-mini"):
            models = get_openai_models()
        allowlist_models = [m for m in models if m["supported"]]
        returned_ids = [m["id"] for m in allowlist_models]
        # Verify order matches OPENAI_SUPPORTED_MODELS_JSON
        allowlist_in_result = [mid for mid in OPENAI_SUPPORTED_MODELS_JSON if mid in returned_ids]
        assert allowlist_in_result == [mid for mid in returned_ids if mid in OPENAI_SUPPORTED_MODELS_JSON]
