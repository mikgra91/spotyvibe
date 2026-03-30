"""Tests for core/analysis.py — Band/Song Analysis."""
import json
from unittest.mock import patch, MagicMock, mock_open
import pytest
from core.analysis import analyze_band_song


class TestAnalyzeBandSong:
    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_returns_structured_result(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        gpt_output = {
            "artist": "Radiohead",
            "track": "Creep",
            "genre": ["Alternative Rock"],
            "style_tags": ["melancholic"],
            "characteristics": {"energy": "medium"},
            "profile_suggestions": ["I like alternative rock"],
        }
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(gpt_output)
        mock_client.chat.completions.create.return_value = mock_response

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

    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_empty_gpt_response(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_client.chat.completions.create.return_value = mock_response

        with pytest.raises(ValueError, match="empty response"):
            analyze_band_song("Test Artist")

    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_invalid_json(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"
        mock_client.chat.completions.create.return_value = mock_response

        with pytest.raises(ValueError, match="invalid JSON"):
            analyze_band_song("Test")

    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="Deutsch")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_passes_language_to_prompt(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"artist": "Test"})
        mock_client.chat.completions.create.return_value = mock_response

        analyze_band_song("Test")
        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args[1]["messages"][0]["content"]
        assert "Deutsch" in system_msg

    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_defaults_missing_keys(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        # GPT returns minimal JSON without all expected keys
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"artist": "X"})
        mock_client.chat.completions.create.return_value = mock_response

        result = analyze_band_song("X")
        assert result["genre"] == []
        assert result["style_tags"] == []
        assert result["characteristics"] == {}
        assert result["profile_suggestions"] == []

    @patch("core.analysis.debug_log")
    @patch("core.analysis.get_openai_client")
    @patch("core.analysis.get_model", return_value="gpt-4o")
    @patch("core.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_artist_only_no_track(self, mock_lang, mock_model, mock_client_fn, mock_debug):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"artist": "Radiohead"})
        mock_client.chat.completions.create.return_value = mock_response

        result = analyze_band_song("Radiohead")
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "Radiohead" in user_msg
        assert "\u2014" not in user_msg  # no track separator (em dash)
