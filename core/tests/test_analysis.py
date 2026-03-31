"""Tests for core/analysis.py — Band/Song Analysis."""
import json
from unittest.mock import patch, MagicMock, mock_open
import pytest
from core.src.analysis import analyze_band_song


def _make_http_response(content: dict) -> dict:
    """Build a minimal chat completions response dict."""
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


class TestAnalyzeBandSong:
    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_returns_structured_result(self, mock_lang, mock_model, mock_create, mock_debug):
        gpt_output = {
            "artist": "Radiohead",
            "track": "Creep",
            "genre": ["Alternative Rock"],
            "style_tags": ["melancholic"],
            "characteristics": {"energy": "medium"},
            "profile_suggestions": ["I like alternative rock"],
        }
        mock_create.return_value = _make_http_response(gpt_output)

        result = analyze_band_song("Radiohead", "Creep")
        assert result["artist"] == "Radiohead"
        assert "Alternative Rock" in result["genre"]
        assert len(result["profile_suggestions"]) > 0

    def test_raises_on_empty_artist(self):
        with pytest.raises(ValueError, match="Artist name is required"):
            analyze_band_song("")

    def test_raises_on_blank_artist(self):
        with pytest.raises(ValueError, match="Artist name is required"):
            analyze_band_song("   ")

    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_empty_gpt_response(self, mock_lang, mock_model, mock_create, mock_debug):
        mock_create.return_value = {"choices": [{"message": {"content": ""}}]}

        with pytest.raises(ValueError, match="empty response"):
            analyze_band_song("Test Artist")

    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_invalid_json(self, mock_lang, mock_model, mock_create, mock_debug):
        mock_create.return_value = {"choices": [{"message": {"content": "not json at all"}}]}

        with pytest.raises(ValueError, match="invalid JSON"):
            analyze_band_song("Test")

    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="Deutsch")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_passes_language_to_prompt(self, mock_lang, mock_model, mock_create, mock_debug):
        mock_create.return_value = _make_http_response({"artist": "Test"})

        analyze_band_song("Test")
        call_kwargs = mock_create.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "Deutsch" in system_msg

    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_defaults_missing_keys(self, mock_lang, mock_model, mock_create, mock_debug):
        # GPT returns minimal JSON without all expected keys
        mock_create.return_value = _make_http_response({"artist": "X"})

        result = analyze_band_song("X")
        assert result["genre"] == []
        assert result["style_tags"] == []
        assert result["characteristics"] == {}
        assert result["profile_suggestions"] == []

    @patch("core.src.analysis.debug_log")
    @patch("core.src.analysis.chat_completions_create")
    @patch("core.src.analysis.get_model", return_value="gpt-4o")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_artist_only_no_track(self, mock_lang, mock_model, mock_create, mock_debug):
        mock_create.return_value = _make_http_response({"artist": "Radiohead"})

        result = analyze_band_song("Radiohead")
        call_kwargs = mock_create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "Radiohead" in user_msg
        assert "\u2014" not in user_msg  # no track separator (em dash)
