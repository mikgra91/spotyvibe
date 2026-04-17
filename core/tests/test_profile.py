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
    """Return context managers that patch active profile paths to use tmp_path/profiles/<id>/."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    profile_dir = profiles_dir / profile_id
    profile_dir.mkdir(exist_ok=True)
    profile_path = profile_dir / "profile.json"
    history_path = profile_dir / "profile.history.json"
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
            profile_path = tmp_path / "profiles" / "test-id" / "profile.json"
            assert profile_path.exists()
            data = json.loads(profile_path.read_text())
            assert data["last_updated"] is None
            assert "preferences" in data

    def test_does_not_overwrite_existing(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_path = tmp_path / "profiles" / "test-id" / "profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text('{"custom": true}')
        with p1, p2, p3, p4:
            ensure_profile()
        data = json.loads(profile_path.read_text())
        assert data == {"custom": True}


class TestLoadProfile:
    def test_loads_existing_profile(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_path = tmp_path / "profiles" / "test-id" / "profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        expected = {"last_updated": "2025-01-01", "preferences": {}}
        profile_path.write_text(json.dumps(expected))
        with p1, p2, p3, p4:
            result = load_profile()
        assert result == expected

    def test_creates_profile_if_missing(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        with p1, p2, p3, p4:
            result = load_profile()
        profile_path = tmp_path / "profiles" / "test-id" / "profile.json"
        assert "preferences" in result
        assert profile_path.exists()


class TestSaveProfile:
    def test_writes_profile_and_backup(self, tmp_path):
        p1, p2, p3, p4 = _patch_active_profile(tmp_path)
        profile_dir = tmp_path / "profiles" / "test-id"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = profile_dir / "profile.json"
        history_path = profile_dir / "profile.history.json"
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
    @patch("core.src.profile.call_gpt_json")
    @patch("core.src.profile.load_profile")
    def test_calls_gpt_and_updates_profile(
        self, mock_load, mock_gpt, mock_save
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
        mock_gpt.return_value = gpt_output

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
    @patch("core.src.profile.call_gpt_json")
    @patch("core.src.profile.load_profile")
    def test_raises_on_invalid_json(
        self, mock_load, mock_gpt, mock_save
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
        mock_gpt.side_effect = ValueError("AI returned invalid JSON (Profile Training). Please try again.")

        with pytest.raises(ValueError, match="invalid JSON"):
            train_profile({
                "core_description": "rock",
                "must_have": "",
                "soft_preferences": "",
                "avoid": "",
            })
        mock_save.assert_not_called()

    @patch("core.src.profile.save_profile")
    @patch("core.src.profile.call_gpt_json")
    @patch("core.src.profile.load_profile")
    def test_preserves_schema_when_gpt_drops_keys(
        self, mock_load, mock_gpt, mock_save
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
        mock_gpt.return_value = gpt_output

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
    _UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _UUID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def test_returns_empty_when_no_profiles(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert result == []

    def test_lists_all_profiles(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / self._UUID_A).mkdir()
        (profiles_dir / self._UUID_A / "profile.json").write_text(
            json.dumps({"name": "Work", "last_updated": "2025-01-01"}))
        (profiles_dir / self._UUID_B).mkdir()
        (profiles_dir / self._UUID_B / "profile.json").write_text(
            json.dumps({"name": "Chill", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 2
        assert result[0] == {"id": self._UUID_A, "name": "Work", "trained": True, "last_updated": "2025-01-01"}
        assert result[1] == {"id": self._UUID_B, "name": "Chill", "trained": False, "last_updated": None}

    def test_ignores_non_uuid_directories(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / self._UUID_A).mkdir()
        (profiles_dir / self._UUID_A / "profile.json").write_text(
            json.dumps({"name": "A", "last_updated": None}))
        (profiles_dir / "not-a-uuid").mkdir()
        (profiles_dir / "not-a-uuid" / "profile.json").write_text(
            json.dumps({"name": "B", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1

    def test_skips_corrupt_files(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / self._UUID_A).mkdir()
        (profiles_dir / self._UUID_A / "profile.json").write_text(
            json.dumps({"name": "Good", "last_updated": None}))
        (profiles_dir / self._UUID_B).mkdir()
        (profiles_dir / self._UUID_B / "profile.json").write_text("NOT JSON {{{")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1
        assert result[0]["id"] == self._UUID_A

    def test_excludes_unnamed_profiles(self, tmp_path):
        """Profiles with empty or missing name should be filtered out."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / self._UUID_A).mkdir()
        (profiles_dir / self._UUID_A / "profile.json").write_text(
            json.dumps({"name": "My Profile", "last_updated": None}))
        (profiles_dir / self._UUID_B).mkdir()
        (profiles_dir / self._UUID_B / "profile.json").write_text(
            json.dumps({"name": "", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        assert len(result) == 1
        assert result[0]["name"] == "My Profile"

    def test_migrates_flat_files_to_subdirectories(self, tmp_path):
        """Flat-layout profile files should be migrated automatically."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        # Old flat layout
        (profiles_dir / f"{self._UUID_A}.json").write_text(
            json.dumps({"name": "Legacy", "last_updated": "2025-01-01"}))
        (profiles_dir / f"{self._UUID_A}.history.json").write_text(
            json.dumps({"name": "Legacy old", "last_updated": None}))
        (profiles_dir / f"{self._UUID_A}_run_history.json").write_text(
            json.dumps([{"run_id": "r1"}]))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4:
            result = list_profiles()
        # Profile should be found via the new layout
        assert len(result) == 1
        assert result[0]["id"] == self._UUID_A
        assert result[0]["name"] == "Legacy"
        # Flat files should be gone, subdirectory should exist
        assert not (profiles_dir / f"{self._UUID_A}.json").exists()
        assert not (profiles_dir / f"{self._UUID_A}.history.json").exists()
        assert not (profiles_dir / f"{self._UUID_A}_run_history.json").exists()
        assert (profiles_dir / self._UUID_A / "profile.json").exists()
        assert (profiles_dir / self._UUID_A / "profile.history.json").exists()
        assert (profiles_dir / self._UUID_A / "run_history.json").exists()


class TestCreateProfile:
    def test_creates_profile_with_name(self, tmp_path):
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.set_active_profile_id") as mock_set:
            result = create_profile("Workout")
        assert result["name"] == "Workout"
        assert result["id"]  # UUID string
        profile_path = tmp_path / "profiles" / result["id"] / "profile.json"
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
        existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        (profiles_dir / existing_id).mkdir()
        (profiles_dir / existing_id / "profile.json").write_text(
            json.dumps({"name": "Workout", "last_updated": None}))
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.set_active_profile_id"), pytest.raises(ValueError, match="already exists"):
            create_profile("workout")  # case-insensitive


class TestDeleteProfile:
    # Valid UUIDs for testing
    _UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _UUID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _UUID_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    def test_deletes_profile_directory(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profile_dir = profiles_dir / self._UUID_A
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("{}")
        (profile_dir / "profile.history.json").write_text("{}")
        (profile_dir / "run_history.json").write_text("[]")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.get_active_profile_id", return_value=self._UUID_A), \
             patch("core.src.profile.set_active_profile_id") as mock_set:
            delete_profile(self._UUID_A)
        assert not profile_dir.exists()
        mock_set.assert_called_once_with("")

    def test_clears_active_when_deleting_active_profile(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profile_dir = profiles_dir / self._UUID_B
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("{}")
        _, _, _, p4 = _patch_active_profile(tmp_path)
        with p4, patch("core.src.profile.get_active_profile_id", return_value=self._UUID_B), \
             patch("core.src.profile.set_active_profile_id") as mock_set:
            delete_profile(self._UUID_B)
        mock_set.assert_called_once_with("")

    def test_does_not_clear_active_when_deleting_other_profile(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profile_dir = profiles_dir / self._UUID_B
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("{}")
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
        profile_dir = profiles_dir / self._UUID_A
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("{}")
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

        with patch("core.src.profile.call_gpt_json") as mock_gpt, \
             patch("core.src.profile.SEED_PROMPT_FILE") as mock_file:
            mock_file.read_text.return_value = (
                "Playlist: {name}, {count} tracks. "
                "Artists: {top_artists_list}. Genres: {top_genres_list}. "
                "Energy: {energy}, Valence: {valence}, Tempo: {tempo}. "
                "Moods: {moods}"
            )
            mock_gpt.return_value = json.loads(mock_gpt_json)

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
        mock_gpt_result = {
            "core_description": "Test",
            "must_have": ["a", "b", "c", "d", "e"],
            "soft_preferences": [],
            "avoid": ["should be removed"],
            "vibe_description": ""
        }

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

        with patch("core.src.profile.call_gpt_json") as mock_gpt, \
             patch("core.src.profile.SEED_PROMPT_FILE") as mock_file:
            mock_file.read_text.return_value = (
                "{name}{count}{top_artists_list}{top_genres_list}"
                "{energy}{valence}{tempo}{moods}"
            )
            mock_gpt.return_value = mock_gpt_result

            result = draft_profile_from_playlist(summary)

        assert len(result["must_have"]) == 3
        assert result["avoid"] == []


# ── Integration tests ────────────────────────────────────────────────
#
# These tests use the `isolated_profiles_env` fixture which patches ONLY
# the directory constants, letting real path resolution run through
# config.py. They catch bugs that unit tests with mocked paths miss —
# like the list_profiles() crash on _run_history.json files.

class TestProfileIntegration:
    """Integration tests that exercise real disk I/O with real path resolution."""

    def test_create_and_list_round_trip(self, isolated_profiles_env):
        """Create a profile on disk, then list it — verifies the full chain."""
        result = create_profile("Rock")
        pid = result["id"]

        # Verify it's on disk in the correct subdirectory
        profile_file = isolated_profiles_env["profiles_dir"] / pid / "profile.json"
        assert profile_file.exists(), "Profile JSON not created on disk"

        data = json.loads(profile_file.read_text())
        assert data["name"] == "Rock"

        # Verify list_profiles finds it
        profiles = list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["id"] == pid
        assert profiles[0]["name"] == "Rock"
        assert profiles[0]["trained"] is False

    def test_create_activate_load_round_trip(self, isolated_profiles_env):
        """Create → auto-activate → load: verify profile data comes back intact."""
        from config import get_active_profile_id

        result = create_profile("Jazz")
        pid = result["id"]

        # create_profile auto-activates
        assert get_active_profile_id() == pid

        # load_profile should return the template with name set
        profile = load_profile()
        assert profile["name"] == "Jazz"
        assert "preferences" in profile
        assert "artists" in profile
        assert "history" in profile
        assert "feedback" in profile
        assert "meta" in profile
        assert "taste_rules" in profile
        assert profile["last_updated"] is None

    def test_create_two_profiles_list_both(self, isolated_profiles_env):
        """Two profiles created → both appear in list_profiles."""
        r1 = create_profile("Rock")
        r2 = create_profile("Jazz")

        profiles = list_profiles()
        assert len(profiles) == 2
        names = {p["name"] for p in profiles}
        assert names == {"Rock", "Jazz"}
        ids = {p["id"] for p in profiles}
        assert r1["id"] in ids
        assert r2["id"] in ids

    def test_delete_profile_removes_directory(self, isolated_profiles_env):
        """Delete removes the entire profile subdirectory."""
        result = create_profile("Temp")
        pid = result["id"]
        profile_dir = isolated_profiles_env["profiles_dir"] / pid
        assert profile_dir.exists()

        delete_profile(pid)
        assert not profile_dir.exists()
        assert list_profiles() == []

    def test_activate_profile_switches_context(self, isolated_profiles_env):
        """Activating a different profile changes which one load_profile returns."""
        r1 = create_profile("Rock")
        r2 = create_profile("Jazz")

        # create_profile auto-activates the last one
        assert load_profile()["name"] == "Jazz"

        activate_profile(r1["id"])
        assert load_profile()["name"] == "Rock"

        activate_profile(r2["id"])
        assert load_profile()["name"] == "Jazz"

    def test_save_profile_creates_history_backup(self, isolated_profiles_env):
        """Save creates a .history.json backup alongside profile.json."""
        result = create_profile("Rock")
        pid = result["id"]
        profile_dir = isolated_profiles_env["profiles_dir"] / pid

        profile = load_profile()
        profile["preferences"]["core_description"] = "Heavy rock"
        save_profile(profile)

        assert (profile_dir / "profile.json").exists()
        assert (profile_dir / "profile.history.json").exists()

        # Current file has the update
        current = json.loads((profile_dir / "profile.json").read_text())
        assert current["preferences"]["core_description"] == "Heavy rock"

        # Backup has the original (no core_description or empty)
        backup = json.loads((profile_dir / "profile.history.json").read_text())
        assert backup["preferences"]["core_description"] == ""

    def test_list_profiles_survives_stray_flat_files(self, isolated_profiles_env):
        """Stray flat files (old layout) in profiles dir don't crash list_profiles.

        This is the exact scenario that caused the original bug: _run_history.json
        in the profiles root is a JSON array, and list_profiles() called .get()
        on it, causing an AttributeError.
        """
        result = create_profile("Rock")
        pid = result["id"]
        profiles_dir = isolated_profiles_env["profiles_dir"]

        # Write a stray JSON array file (simulates old _run_history.json)
        stray = profiles_dir / "some_stray_file.json"
        stray.write_text(json.dumps([{"run_id": "x"}]))

        # Must not crash
        profiles = list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Rock"

    def test_list_profiles_survives_non_dict_profile_json(self, isolated_profiles_env):
        """A profile.json containing a JSON array instead of dict is skipped."""
        profiles_dir = isolated_profiles_env["profiles_dir"]
        bad_uuid = "deadbeef-dead-beef-dead-beefdeadbeef"
        bad_dir = profiles_dir / bad_uuid
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text(json.dumps([1, 2, 3]))

        profiles = list_profiles()
        assert len(profiles) == 0

    def test_list_profiles_ignores_non_uuid_directories(self, isolated_profiles_env):
        """Directories not matching UUID pattern are ignored."""
        profiles_dir = isolated_profiles_env["profiles_dir"]
        bogus = profiles_dir / "my-backup"
        bogus.mkdir()
        (bogus / "profile.json").write_text(json.dumps({"name": "Fake", "last_updated": None}))

        profiles = list_profiles()
        assert len(profiles) == 0

    def test_migration_moves_flat_files_to_subdirectory(self, isolated_profiles_env):
        """Flat-layout files are migrated to subdirectory on list_profiles call."""
        profiles_dir = isolated_profiles_env["profiles_dir"]
        fake_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

        # Write old flat-layout files
        (profiles_dir / f"{fake_uuid}.json").write_text(
            json.dumps({"name": "Legacy", "last_updated": "2025-01-01"}))
        (profiles_dir / f"{fake_uuid}.history.json").write_text(
            json.dumps({"name": "Legacy old"}))
        (profiles_dir / f"{fake_uuid}_run_history.json").write_text(
            json.dumps([{"run_id": "r1"}]))

        profiles = list_profiles()

        # Profile found in new layout
        assert len(profiles) == 1
        assert profiles[0]["id"] == fake_uuid
        assert profiles[0]["name"] == "Legacy"

        # Flat files gone
        assert not (profiles_dir / f"{fake_uuid}.json").exists()
        assert not (profiles_dir / f"{fake_uuid}.history.json").exists()
        assert not (profiles_dir / f"{fake_uuid}_run_history.json").exists()

        # Subdirectory has all files
        sub = profiles_dir / fake_uuid
        assert (sub / "profile.json").exists()
        assert (sub / "profile.history.json").exists()
        assert (sub / "run_history.json").exists()

    def test_save_profile_sections_round_trip(self, isolated_profiles_env):
        """Save sections → load → verify preferences match."""
        create_profile("Rock")

        updated = save_profile_sections({
            "core_description": "Heavy rock with theatrical vocals",
            "must_have": "guitar solos\nhigh energy",
            "soft_preferences": "prog influence",
            "avoid": "country\nelectronic",
        })

        # Re-load from disk and verify
        reloaded = load_profile()
        assert reloaded["preferences"]["core_description"] == "Heavy rock with theatrical vocals"
        assert reloaded["preferences"]["must_have"] == ["guitar solos", "high energy"]
        assert reloaded["preferences"]["soft_preferences"] == ["prog influence"]
        assert reloaded["preferences"]["avoid"] == ["country", "electronic"]
        assert reloaded["last_updated"] is not None

    def test_delete_active_profile_clears_active_id(self, isolated_profiles_env):
        """Deleting the active profile sets ACTIVE_PROFILE_ID to empty."""
        from config import get_active_profile_id

        result = create_profile("Temp")
        pid = result["id"]
        assert get_active_profile_id() == pid

        delete_profile(pid)
        assert get_active_profile_id() == ""

    def test_create_profile_populates_full_template(self, isolated_profiles_env):
        """Newly created profile has all template keys and correct structure."""
        result = create_profile("Test")
        profile = load_profile()

        # All top-level keys from the template
        for key in ("name", "last_updated", "meta", "preferences",
                     "artists", "history", "feedback", "taste_rules"):
            assert key in profile, f"Missing top-level key: {key}"

        # Preferences has the expected sub-keys
        prefs = profile["preferences"]
        for key in ("core_description", "must_have", "soft_preferences", "avoid"):
            assert key in prefs, f"Missing preferences key: {key}"

        # Lists are actually lists
        assert isinstance(prefs["must_have"], list)
        assert isinstance(prefs["soft_preferences"], list)
        assert isinstance(prefs["avoid"], list)

    def test_profile_data_persists_across_load_save_cycles(self, isolated_profiles_env):
        """Data written via save_profile survives a full load→save→load cycle."""
        create_profile("Cycle")
        profile = load_profile()

        profile["preferences"]["core_description"] = "Progressive rock"
        profile["preferences"]["must_have"] = ["complex time signatures", "guitar"]
        profile["artists"]["confirmed"] = ["Rush", "Yes"]
        save_profile(profile)

        # Load again and verify all fields survived
        reloaded = load_profile()
        assert reloaded["preferences"]["core_description"] == "Progressive rock"
        assert reloaded["preferences"]["must_have"] == ["complex time signatures", "guitar"]
        assert reloaded["artists"]["confirmed"] == ["Rush", "Yes"]
        assert reloaded["name"] == "Cycle"

