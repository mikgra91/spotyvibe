"""Tests for core/profile.py — profile I/O, status, and training."""

import json
from unittest.mock import patch, MagicMock

from core.src.profile import (
    _load_template,
    ensure_profile,
    load_profile,
    save_profile,
    is_profile_trained,
    get_profile_status,
    train_profile,
    save_profile_sections,
)


class TestLoadTemplate:
    def test_returns_dict_with_required_keys(self):
        template = _load_template()
        assert isinstance(template, dict)
        assert "preferences" in template
        assert "history" in template
        assert "feedback" in template
        assert "artists" in template
        assert template["last_updated"] is None


class TestEnsureProfile:
    def test_creates_profile_from_template(self, tmp_path):
        profile_file = tmp_path / "profile.json"
        with patch("core.src.profile.PROFILE_FILE", profile_file):
            ensure_profile()
        assert profile_file.exists()
        data = json.loads(profile_file.read_text())
        assert data["last_updated"] is None
        assert "preferences" in data

    def test_does_not_overwrite_existing(self, tmp_path):
        profile_file = tmp_path / "profile.json"
        profile_file.write_text('{"custom": true}')
        with patch("core.src.profile.PROFILE_FILE", profile_file):
            ensure_profile()
        data = json.loads(profile_file.read_text())
        assert data == {"custom": True}


class TestLoadProfile:
    def test_loads_existing_profile(self, tmp_path):
        profile_file = tmp_path / "profile.json"
        expected = {"last_updated": "2025-01-01", "preferences": {}}
        profile_file.write_text(json.dumps(expected))
        with patch("core.src.profile.PROFILE_FILE", profile_file):
            result = load_profile()
        assert result == expected

    def test_creates_profile_if_missing(self, tmp_path):
        profile_file = tmp_path / "profile.json"
        with patch("core.src.profile.PROFILE_FILE", profile_file):
            result = load_profile()
        assert "preferences" in result
        assert profile_file.exists()


class TestSaveProfile:
    def test_writes_profile_and_backup(self, tmp_path):
        profile_file = tmp_path / "profile.json"
        history_file = tmp_path / "profile.history.json"
        # Create initial profile
        original = {"last_updated": None, "preferences": {}, "history": {}, "feedback": {}, "artists": {}, "meta": {"goal": ""}, "taste_rules": {"primary_driver": "", "dealbreaker_priority": []}}
        profile_file.write_text(json.dumps(original))

        updated = {**original, "last_updated": "2025-06-01"}
        with patch("core.src.profile.PROFILE_FILE", profile_file), \
             patch("core.src.profile.PROFILE_HISTORY_FILE", history_file):
            save_profile(updated)

        saved = json.loads(profile_file.read_text())
        assert saved["last_updated"] == "2025-06-01"
        # Backup should contain the original
        backup = json.loads(history_file.read_text())
        assert backup["last_updated"] is None


class TestIsProfileTrained:
    @patch("core.src.profile.load_profile")
    def test_true_when_timestamp_set(self, mock_load):
        mock_load.return_value = {"last_updated": "2025-01-01T00:00:00"}
        assert is_profile_trained() is True

    @patch("core.src.profile.load_profile")
    def test_false_when_no_timestamp(self, mock_load):
        mock_load.return_value = {"last_updated": None}
        assert is_profile_trained() is False

    @patch("core.src.profile.load_profile")
    def test_false_when_empty_string(self, mock_load):
        mock_load.return_value = {"last_updated": ""}
        assert is_profile_trained() is False


class TestGetProfileStatus:
    @patch("core.src.profile.load_profile")
    def test_returns_status_dict(self, mock_load):
        mock_load.return_value = {"last_updated": "2025-01-01T12:00:00"}
        status = get_profile_status()
        assert status["trained"] is True
        assert status["last_updated"] == "2025-01-01T12:00:00"

    @patch("core.src.profile.load_profile")
    def test_untrained_status(self, mock_load):
        mock_load.return_value = {"last_updated": None}
        status = get_profile_status()
        assert status["trained"] is False
        assert status["last_updated"] is None


class TestTrainProfile:
    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.debug_log")
    @patch("core.src.profile.get_model", return_value="gpt-4o")
    @patch("core.src.profile.chat_completions_create")
    @patch("core.src.profile.load_profile")
    def test_calls_gpt_and_updates_profile(
        self, mock_load, mock_create, mock_model, mock_debug, mock_save
    ):
        original_profile = {
            "last_updated": None,
            "meta": {"goal": ""},
            "preferences": {"core_description": "", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": [], "moderate": [], "rejected": []},
            "history": {"suggested_artists": ["old artist"], "suggested_tracks": ["old track"]},
            "feedback": {"liked_tracks": [{"artist": "a", "track": "b"}], "disliked_tracks": []},
            "taste_rules": {"primary_driver": "", "dealbreaker_priority": []},
        }
        mock_load.return_value = original_profile

        gpt_output = {
            "last_updated": None,
            "meta": {"goal": "energetic music"},
            "preferences": {"core_description": "rock", "must_have": ["guitar"], "soft_preferences": [], "avoid": ["country"]},
            "artists": {"confirmed": ["metallica"], "moderate": [], "rejected": []},
            "history": {"suggested_artists": ["REPLACED"], "suggested_tracks": ["REPLACED"]},
            "feedback": {"liked_tracks": ["REPLACED"], "disliked_tracks": []},
            "taste_rules": {"primary_driver": "energy", "dealbreaker_priority": ["country"]},
        }
        mock_create.return_value = {"choices": [{"message": {"content": json.dumps(gpt_output)}}]}

        sections = {
            "core_description": "I love rock music",
            "must_have": "guitar solos",
            "soft_preferences": "",
            "avoid": "country",
        }

        result = train_profile(sections)

        # history and feedback should be PRESERVED from original, not from GPT
        assert result["history"] == original_profile["history"]
        assert result["feedback"] == original_profile["feedback"]

        # GPT output for other sections should be used
        assert result["meta"]["goal"] == "energetic music"
        assert result["preferences"]["core_description"] == "rock"

        # Timestamp should be set
        assert result["last_updated"] is not None

        # save_profile should have been called
        mock_save.assert_called_once()

    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.debug_log")
    @patch("core.src.profile.get_model", return_value="gpt-4o")
    @patch("core.src.profile.chat_completions_create")
    @patch("core.src.profile.load_profile")
    def test_raises_on_invalid_json(
        self, mock_load, mock_create, mock_model, mock_debug, mock_save
    ):
        mock_load.return_value = {
            "last_updated": None,
            "meta": {"goal": ""},
            "preferences": {"core_description": "", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": [], "moderate": [], "rejected": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
            "taste_rules": {"primary_driver": "", "dealbreaker_priority": []},
        }
        mock_create.return_value = {"choices": [{"message": {"content": "NOT VALID JSON {{{{"}}]}

        import pytest
        with pytest.raises(ValueError, match="invalid response"):
            train_profile({
                "core_description": "rock",
                "must_have": "",
                "soft_preferences": "",
                "avoid": "",
            })
        mock_save.assert_not_called()

    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.debug_log")
    @patch("core.src.profile.get_model", return_value="gpt-4o")
    @patch("core.src.profile.chat_completions_create")
    @patch("core.src.profile.load_profile")
    def test_preserves_schema_when_gpt_drops_keys(
        self, mock_load, mock_create, mock_model, mock_debug, mock_save
    ):
        original_profile = {
            "last_updated": None,
            "meta": {"goal": "discover new music"},
            "preferences": {"core_description": "rock", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": ["metallica"], "moderate": [], "rejected": []},
            "history": {"suggested_artists": ["old"], "suggested_tracks": ["old track"]},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
            "taste_rules": {"primary_driver": "energy", "dealbreaker_priority": []},
        }
        mock_load.return_value = original_profile

        # GPT output that drops "artists", "meta", and "taste_rules" keys
        gpt_output = {
            "preferences": {"core_description": "heavy rock", "must_have": ["guitar"], "soft_preferences": [], "avoid": []},
        }
        mock_create.return_value = {"choices": [{"message": {"content": json.dumps(gpt_output)}}]}

        result = train_profile({
            "core_description": "heavy rock",
            "must_have": "guitar",
            "soft_preferences": "",
            "avoid": "",
        })

        # All template keys must be present even though GPT dropped them
        assert "artists" in result
        assert "meta" in result
        assert "taste_rules" in result
        assert "preferences" in result
        # GPT's preference updates should still apply
        assert result["preferences"]["core_description"] == "heavy rock"
        # history and feedback preserved from original
        assert result["history"] == original_profile["history"]
        assert result["feedback"] == original_profile["feedback"]


class TestSaveProfileSections:
    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.load_profile")
    def test_updates_preferences_directly(self, mock_load, mock_save):
        original = {
            "last_updated": None,
            "meta": {"goal": ""},
            "preferences": {"core_description": "", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": [], "moderate": [], "rejected": []},
            "history": {"suggested_artists": ["old"], "suggested_tracks": ["old track"]},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
        }
        mock_load.return_value = original

        sections = {
            "core_description": "I love rock",
            "must_have": "guitar solos\nhigh energy",
            "soft_preferences": "prog influence",
            "avoid": "country\nelectronic",
        }
        result = save_profile_sections(sections)

        assert result["preferences"]["core_description"] == "I love rock"
        assert result["preferences"]["must_have"] == ["guitar solos", "high energy"]
        assert result["preferences"]["soft_preferences"] == ["prog influence"]
        assert result["preferences"]["avoid"] == ["country", "electronic"]
        assert result["last_updated"] is not None
        # History and feedback untouched
        assert result["history"] == original["history"]
        assert result["feedback"] == original["feedback"]
        mock_save.assert_called_once()

    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.load_profile")
    def test_handles_empty_optional_sections(self, mock_load, mock_save):
        original = {
            "last_updated": None,
            "meta": {"goal": ""},
            "preferences": {"core_description": "", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": [], "moderate": [], "rejected": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
        }
        mock_load.return_value = original

        sections = {
            "core_description": "Just rock",
            "must_have": "",
            "soft_preferences": "",
            "avoid": "",
        }
        result = save_profile_sections(sections)

        assert result["preferences"]["core_description"] == "Just rock"
        assert result["preferences"]["must_have"] == []
        assert result["preferences"]["soft_preferences"] == []
        assert result["preferences"]["avoid"] == []

    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.load_profile")
    def test_strips_blank_lines(self, mock_load, mock_save):
        original = {
            "last_updated": None,
            "meta": {"goal": ""},
            "preferences": {"core_description": "", "must_have": [], "soft_preferences": [], "avoid": []},
            "artists": {"confirmed": [], "moderate": [], "rejected": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
        }
        mock_load.return_value = original

        sections = {
            "core_description": "rock",
            "must_have": "energy\n\n  \nhigh tempo",
            "soft_preferences": "",
            "avoid": "",
        }
        result = save_profile_sections(sections)
        assert result["preferences"]["must_have"] == ["energy", "high tempo"]
