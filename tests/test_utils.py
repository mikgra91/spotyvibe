import os
from unittest.mock import patch, MagicMock, mock_open

from core.utils import strip_code_fences, debug_log, clear_debug_log, get_openai_client, get_openai_models, sanitize_text, sanitize_profile


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
    @patch("core.utils.get_debug_mode", return_value=False)
    def test_skips_when_debug_off(self, mock_mode, tmp_path):
        """debug_log should not write anything when debug mode is disabled."""
        log_file = tmp_path / "debug.log"
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            debug_log("Test", [{"role": "user", "content": "hi"}], '{"ok": true}')
        assert not log_file.exists()

    @patch("core.utils.get_debug_mode", return_value=True)
    def test_writes_when_debug_on(self, mock_mode, tmp_path):
        """debug_log should write label, messages, and response to file."""
        log_file = tmp_path / "debug.log"
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
            debug_log("TestLabel", messages, '{"result": "ok"}')
        content = log_file.read_text()
        assert "TestLabel" in content
        assert "[SYSTEM]" in content
        assert "[USER]" in content
        assert "hello" in content
        assert '"result": "ok"' in content

    @patch("core.utils.get_debug_mode", return_value=True)
    def test_handles_non_json_response(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            debug_log("Test", [{"role": "user", "content": "hi"}], "not json")
        content = log_file.read_text()
        assert "not json" in content

    @patch("core.utils.get_debug_mode", return_value=True)
    def test_appends_to_existing_log(self, mock_mode, tmp_path):
        log_file = tmp_path / "debug.log"
        log_file.write_text("previous content\n")
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            debug_log("New", [{"role": "user", "content": "msg"}], "resp")
        content = log_file.read_text()
        assert "previous content" in content
        assert "New" in content


class TestClearDebugLog:
    def test_deletes_existing_file(self, tmp_path):
        log_file = tmp_path / "debug.log"
        log_file.write_text("some log data")
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            clear_debug_log()
        assert not log_file.exists()

    def test_no_error_when_file_missing(self, tmp_path):
        log_file = tmp_path / "debug.log"
        with patch("core.utils.DEBUG_LOG_FILE", log_file):
            clear_debug_log()  # should not raise


class TestGetOpenaiClient:
    def setup_method(self):
        """Reset the module-level client cache before each test."""
        import core.utils
        core.utils._openai_client = None
        core.utils._openai_key = None

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    def test_raises_when_no_key(self):
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            import core.utils
            core.utils._openai_client = None
            core.utils._openai_key = None
            try:
                get_openai_client()
                assert False, "Expected ValueError"
            except ValueError as e:
                assert "not configured" in str(e)

    @patch("core.utils.OpenAI")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"})
    def test_creates_client(self, mock_openai_cls):
        import core.utils
        core.utils._openai_client = None
        core.utils._openai_key = None
        client = get_openai_client()
        mock_openai_cls.assert_called_once_with(api_key="sk-test123")
        assert client is mock_openai_cls.return_value

    @patch("core.utils.OpenAI")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"})
    def test_reuses_client_same_key(self, mock_openai_cls):
        import core.utils
        core.utils._openai_client = None
        core.utils._openai_key = None
        c1 = get_openai_client()
        c2 = get_openai_client()
        # Should only create one client
        mock_openai_cls.assert_called_once()
        assert c1 is c2

    @patch("core.utils.OpenAI")
    def test_recreates_client_on_key_change(self, mock_openai_cls):
        import core.utils
        core.utils._openai_client = None
        core.utils._openai_key = None
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-key1"}):
            get_openai_client()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-key2"}):
            get_openai_client()
        assert mock_openai_cls.call_count == 2


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
        assert sanitize_text(42) == 42
        assert sanitize_text(None) is None


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
    @patch("core.utils.get_openai_client")
    def test_returns_sorted_chat_models(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        model_data = [
            MagicMock(id="gpt-4o"),
            MagicMock(id="gpt-3.5-turbo"),
            MagicMock(id="o1-preview"),
            MagicMock(id="gpt-4o-realtime"),  # should be excluded
            MagicMock(id="gpt-4o-audio"),      # should be excluded
            MagicMock(id="text-embedding-3"),   # should be excluded
            MagicMock(id="tts-1"),              # should be excluded
        ]
        mock_client.models.list.return_value = MagicMock(data=model_data)

        models = get_openai_models()
        assert "gpt-4o" in models
        assert "gpt-3.5-turbo" in models
        assert "o1-preview" in models
        assert "gpt-4o-realtime" not in models
        assert "gpt-4o-audio" not in models
        assert "text-embedding-3" not in models
        assert "tts-1" not in models
        # Should be sorted
        assert models == sorted(models)

