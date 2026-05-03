"""Tests for core/analysis.py — Band/Song Analysis."""
from unittest.mock import patch, mock_open
import pytest
from core.src.analysis import analyze_band_song
from core.src.errors import TranslatableError


def _meta(latency_s=0.5, prompt_tokens=200, completion_tokens=100):
    return {
        "usage": {"prompt_tokens": prompt_tokens,
                  "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
        "latency_s": latency_s,
        "model": "gpt-test",
        "raw_response_chars": 800,
    }


class TestAnalyzeBandSong:
    @patch("core.src.analysis.call_gpt_json_with_meta")
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
        mock_gpt.return_value = (gpt_output, _meta())

        result = analyze_band_song("Radiohead", "Creep")
        assert result["artist"] == "Radiohead"
        assert "Alternative Rock" in result["genre"]
        assert len(result["profile_suggestions"]) > 0

    def test_raises_on_empty_artist(self):
        with pytest.raises(TranslatableError, match="Artist name is required") as exc:
            analyze_band_song("")
        assert exc.value.key == "error.analysis.artist_required"

    def test_raises_on_blank_artist(self):
        with pytest.raises(TranslatableError, match="Artist name is required") as exc:
            analyze_band_song("   ")
        assert exc.value.key == "error.analysis.artist_required"

    @patch("core.src.analysis.call_gpt_json_with_meta")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_empty_gpt_response(self, mock_lang, mock_gpt):
        mock_gpt.side_effect = ValueError("AI returned an empty response (Band/Song Analysis). Please try again.")

        with pytest.raises(ValueError, match="empty response"):
            analyze_band_song("Test Artist")

    @patch("core.src.analysis.call_gpt_json_with_meta")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_handles_invalid_json(self, mock_lang, mock_gpt):
        mock_gpt.side_effect = ValueError("AI returned invalid JSON (Band/Song Analysis). Please try again.")

        with pytest.raises(ValueError, match="invalid JSON"):
            analyze_band_song("Test")

    @patch("core.src.analysis.call_gpt_json_with_meta")
    @patch("core.src.analysis.get_gpt_language", return_value="Deutsch")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_passes_language_to_prompt(self, mock_lang, mock_gpt):
        mock_gpt.return_value = ({"artist": "Test"}, _meta())

        analyze_band_song("Test")
        call_args = mock_gpt.call_args
        messages = call_args[0][0]  # first positional arg
        system_msg = messages[0]["content"]
        assert "Deutsch" in system_msg

    @patch("core.src.analysis.call_gpt_json_with_meta")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_defaults_missing_keys(self, mock_lang, mock_gpt):
        # GPT returns minimal JSON without all expected keys
        mock_gpt.return_value = ({"artist": "X"}, _meta())

        result = analyze_band_song("X")
        assert result["genre"] == []
        assert result["style_tags"] == []
        assert result["characteristics"] == {}
        assert result["audio_features"] == {}
        assert result["profile_suggestions"] == []

    @patch("core.src.analysis.call_gpt_json_with_meta")
    @patch("core.src.analysis.get_gpt_language", return_value="English")
    @patch("builtins.open", mock_open(read_data="You are a music expert. Respond in {gpt_language}."))
    def test_artist_only_no_track(self, mock_lang, mock_gpt):
        mock_gpt.return_value = ({"artist": "Radiohead"}, _meta())

        result = analyze_band_song("Radiohead")
        call_args = mock_gpt.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "Radiohead" in user_msg
        assert "—" not in user_msg  # no track separator (em dash)
