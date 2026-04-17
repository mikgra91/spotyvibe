"""Tests for core/analysis.py — Band/Song Analysis."""
import json
from unittest.mock import patch, MagicMock, mock_open
import pytest
from core.src.analysis import analyze_band_song


class TestAnalyzeBandSong:
    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_returns_structured_result(self, mock_lang, mock_gpt):
        gpt_output = {
            "artist": "Radiohead",
            "track": "Creep",
            "genre": ["Alternative Rock"],
            "style_tags": ["melancholic"],
            "characteristics": {"energy": "medium"},
            "profile_suggestions": ["I like alternative rock"],
        }
        mock_gpt.return_value = gpt_output

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

    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_empty_gpt_response(self, mock_lang, mock_gpt):
        mock_gpt.side_effect = ValueError("AI returned an empty response (Band/Song Analysis). Please try again.")

        with pytest.raises(ValueError, match="empty response"):
            analyze_band_song("Test Artist")

    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_invalid_json(self, mock_lang, mock_gpt):
        mock_gpt.side_effect = ValueError("AI returned invalid JSON (Band/Song Analysis). Please try again.")

        with pytest.raises(ValueError, match="invalid JSON"):
            analyze_band_song("Test")

    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="Deutsch")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_passes_language_to_prompt(self, mock_lang, mock_gpt):
        mock_gpt.return_value = {"artist": "Test"}

        analyze_band_song("Test")
        call_args = mock_gpt.call_args
        messages = call_args[0][0]  # first positional arg
        system_msg = messages[0]["content"]
        assert "Deutsch" in system_msg

    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_defaults_missing_keys(self, mock_lang, mock_gpt):
        # GPT returns minimal JSON without all expected keys
        mock_gpt.return_value = {"artist": "X"}

        result = analyze_band_song("X")
        assert result["genre"] == []
        assert result["style_tags"] == []
        assert result["characteristics"] == {}
        assert result["audio_features"] == {}
        assert result["profile_suggestions"] == []

    @patch("core.src.analysis.call_gpt_json")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_artist_only_no_track(self, mock_lang, mock_gpt):
        mock_gpt.return_value = {"artist": "Radiohead"}

        result = analyze_band_song("Radiohead")
        call_args = mock_gpt.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "Radiohead" in user_msg
        assert "\u2014" not in user_msg  # no track separator (em dash)
