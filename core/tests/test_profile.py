"""Tests for core/profile.py — profile I/O, status, and training."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.src.profile import (
    _load_template,
    ensure_profile,
    load_profile,
    save_profile,
    is_profile_trained,
    get_profile_status,
    train_profile,
    save_profile_sections,
    list_profiles,
    create_profile,
    delete_profile,
    activate_profile,
    draft_profile_from_playlist,
)


class TestLoadTemplate:
    def test_returns_dict_with_required_keys(self):
        template = _load_template()
        assert isinstance(template, dict)
        assert "name" in template
        assert "preferences" in template
        assert "history" in template
        assert "feedback" in template
        assert "artists" in template
        assert template["last_updated"] is None


def _patch_active_profile(tmp_path, profile_id="test-id"):
    """Return context managers that patch active profile paths to use tmp_path/profiles/."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    profile_path = profiles_dir / f"{profile_id}.json"
    history_path = profiles_dir / f"{profile_id}.history.json"
    return (
        patch("core.src.profile.get_active_profile_path", return_value=profile_path),
        patch("core.src.profile.get_active_history_path", return_value=history_path),
        patch("core.src.profile.get_active_profile_id", return_value=profile_id),
        patch("core.src.profile.PROFILES_DIR", profiles_dir),
    )


class TestEnsureProfile:
    def test_creates_profile_from_template(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        with p1, p2, p3, p4:
            ensure_profile()
            profile_path = tmp_path / "profiles" / "test-id.json"
            assert profile_path.exists()
            data = json.loads(profile_path.read_text())
            assert data["last_updated"] is None
            assert "preferences" in data

    def test_does_not_overwrite_existing(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_path = tmp_path / "profiles" / "test-id.json"
        (tmp_path / "profiles").mkdir(exist_ok=True)
        profile_path.write_text('{"custom": true}')
        with p1, p2, p3, p4:
            ensure_profile()
        data = json.loads(profile_path.read_text())
        assert data == {"custom": True}


class TestLoadProfile:
    def test_loads_existing_profile(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_path = tmp_path / "profiles" / "test-id.json"
        (tmp_path / "profiles").mkdir(exist_ok=True)
        expected = {"last_updated": "2025-01-01", "preferences": {}}
        profile_path.write_text(json.dumps(expected))
        with p1, p2, p3, p4:
            result = load_profile()
        assert result == expected

    def test_creates_profile_if_missing(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        with p1, p2, p3, p4:
            result = load_profile()
        profile_path = tmp_path / "profiles" / "test-id.json"
        assert "preferences" in result
        assert profile_path.exists()


class TestSaveProfile:
    def test_writes_profile_and_backup(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_path = tmp_path / "profiles" / "test-id.json"
        history_path = tmp_path / "profiles" / "test-id.history.json"
        (tmp_path / "profiles").mkdir(exist_ok=True)
        original = {"last_updated": None, "preferences": {}, "history": {}, "feedback": {}, "artists": {}, "meta": {"goal": ""}, "taste_rules": {"primary_driver": "", "dealbreaker_priority": []}}
        profile_path.write_text(json.dumps(original))

        updated = {**original, "last_updated": "2025-06-01"}
        with p1, p2, p3, p4:
            save_profile(updated)

        saved = json.loads(profile_path.read_text())
        assert saved["last_updated"] == "2025-06-01"
        backup = json.loads(history_path.read_text())
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


class TestListProfiles:
    def test_returns_empty_when_no_profiles(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert result == []

    def test_lists_all_profiles(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "aaa.json").write_text(json.dumps({"name": "Work", "last_updated": "2025-01-01"}))
        (profiles_dir / "bbb.json").write_text(json.dumps({"name": "Chill", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 2
        assert result[0] == {"id": "aaa", "name": "Work", "trained": True, "last_updated": "2025-01-01"}
        assert result[1] == {"id": "bbb", "name": "Chill", "trained": False, "last_updated": None}

    def test_excludes_history_files(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "aaa.json").write_text(json.dumps({"name": "A", "last_updated": None}))
        (profiles_dir / "aaa.history.json").write_text(json.dumps({"name": "A", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1

    def test_skips_corrupt_files(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "good.json").write_text(json.dumps({"name": "Good", "last_updated": None}))
        (profiles_dir / "bad.json").write_text("NOT JSON {{{")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1
        assert result[0]["id"] == "good"

    def test_excludes_unnamed_profiles(self, tmp_path):
        """Profiles with empty or missing name should be filtered out."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "named.json").write_text(json.dumps({"name": "My Profile", "last_updated": None}))
        (profiles_dir / "empty.json").write_text(json.dumps({"name": "", "last_updated": None}))
        (profiles_dir / "missing.json").write_text(json.dumps({"last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1
        assert result[0]["name"] == "My Profile"


class TestCreateProfile:
    def test_creates_profile_with_name(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.set_active_profile_id") as mock_set:
            result = create_profile("Workout")
        assert result["name"] == "Workout"
        assert result["id"]  # UUID string
        profile_path = tmp_path / "profiles" / f"{result['id']}.json"
        assert profile_path.exists()
        data = json.loads(profile_path.read_text())
        assert data["name"] == "Workout"
        mock_set.assert_called_once_with(result["id"])

    def test_rejects_empty_name(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, pytest.raises(ValueError, match="cannot be empty"):
            create_profile("")

    def test_rejects_too_long_name(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, pytest.raises(ValueError, match="too long"):
            create_profile("A" * 50)

    def test_rejects_duplicate_name(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "existing.json").write_text(json.dumps({"name": "Workout", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.set_active_profile_id"), pytest.raises(ValueError, match="already exists"):
            create_profile("workout")  # case-insensitive


class TestDeleteProfile:
    # Valid UUIDs for testing
    _UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _UUID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _UUID_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    def test_deletes_profile_and_history(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / f"{self._UUID_A}.json").write_text("{}")
        (profiles_dir / f"{self._UUID_A}.history.json").write_text("{}")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.get_active_profile_id", return_value=self._UUID_A), \
             patch("core.src.profile.set_active_profile_id") as mock_set:
            delete_profile(self._UUID_A)
        assert not (profiles_dir / f"{self._UUID_A}.json").exists()
        assert not (profiles_dir / f"{self._UUID_A}.history.json").exists()
        mock_set.assert_called_once_with("")

    def test_clears_active_when_deleting_active_profile(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / f"{self._UUID_B}.json").write_text("{}")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.get_active_profile_id", return_value=self._UUID_B), \
             patch("core.src.profile.set_active_profile_id") as mock_set:
            delete_profile(self._UUID_B)
        mock_set.assert_called_once_with("")

    def test_does_not_clear_active_when_deleting_other_profile(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / f"{self._UUID_B}.json").write_text("{}")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.get_active_profile_id", return_value=self._UUID_C), \
             patch("core.src.profile.set_active_profile_id") as mock_set:
            delete_profile(self._UUID_B)
        mock_set.assert_not_called()

    def test_raises_on_missing_profile(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, pytest.raises(ValueError, match="not found"):
            delete_profile(self._UUID_C)

    def test_raises_on_empty_id(self):
        with pytest.raises(ValueError, match="required"):
            delete_profile("")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            delete_profile("../../.credentials")


class TestActivateProfile:
    _UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _UUID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def test_activates_existing_profile(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / f"{self._UUID_A}.json").write_text("{}")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.set_active_profile_id") as mock_set:
            activate_profile(self._UUID_A)
        mock_set.assert_called_once_with(self._UUID_A)

    def test_raises_on_missing_profile(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, pytest.raises(ValueError, match="not found"):
            activate_profile(self._UUID_B)

    def test_raises_on_empty_id(self):
        with pytest.raises(ValueError, match="required"):
            activate_profile("")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            activate_profile("../../.credentials")


class TestDraftProfileFromPlaylist:
    """C8: Tests for draft_profile_from_playlist (Wave 3)."""

    def test_returns_valid_structure_with_all_keys(self):
        mock_gpt_json = json.dumps({
            "core_description": "Upbeat melodic rock with strong hooks.",
            "must_have": ["driving guitar", "strong melody", "high energy"],
            "soft_preferences": ["indie rock", "alt rock"],
            "avoid": [],
            "vibe_description": "Energetic and anthemic."
        })

        summary = {
            "name": "Test Playlist",
            "track_count": 20,
            "tracks": [],
            "top_artists": ["Foo Fighters", "Muse"],
            "top_genres": ["indie rock", "alt rock"],
            "energy": 0.8,
            "valence": 0.6,
            "tempo": 120.0,
            "moods": ["upbeat", "energetic"],
        }

        with patch("core.src.profile.chat_completions_create") as mock_create, \
             patch("core.src.profile.extract_chat_content", return_value=mock_gpt_json), \
             patch("core.src.profile.get_model", return_value="gpt-4o-mini"), \
             patch("core.src.profile.SEED_PROMPT_FILE") as mock_file:
            mock_file.read_text.return_value = (
                "Playlist: {name}, {count} tracks. "
                "Artists: {top_artists_list}. Genres: {top_genres_list}. "
                "Energy: {energy}, Valence: {valence}, Tempo: {tempo}. "
                "Moods: {moods}"
            )
            mock_create.return_value = {"choices": [{"message": {"content": mock_gpt_json}}]}

            result = draft_profile_from_playlist(summary)

        assert isinstance(result, dict)
        assert "core_description" in result
        assert "must_have" in result
        assert "soft_preferences" in result
        assert "avoid" in result
        assert "vibe_description" in result
        assert result["avoid"] == []
        assert len(result["must_have"]) <= 3

    def test_caps_must_have_at_3(self):
        mock_gpt_json = json.dumps({
            "core_description": "Test",
            "must_have": ["a", "b", "c", "d", "e"],
            "soft_preferences": [],
            "avoid": ["should be removed"],
            "vibe_description": ""
        })

        summary = {
            "name": "Big List",
            "track_count": 50,
            "tracks": [],
            "top_artists": [],
            "top_genres": [],
            "energy": 0.5,
            "valence": 0.5,
            "tempo": 100.0,
            "moods": [],
        }

        with patch("core.src.profile.chat_completions_create") as mock_create, \
             patch("core.src.profile.extract_chat_content", return_value=mock_gpt_json), \
             patch("core.src.profile.get_model", return_value="gpt-4o-mini"), \
             patch("core.src.profile.SEED_PROMPT_FILE") as mock_file:
            mock_file.read_text.return_value = (
                "{name}{count}{top_artists_list}{top_genres_list}"
                "{energy}{valence}{tempo}{moods}"
            )
            mock_create.return_value = {}

            result = draft_profile_from_playlist(summary)

        assert len(result["must_have"]) == 3
        assert result["avoid"] == []

