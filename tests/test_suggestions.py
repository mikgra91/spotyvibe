import json
from unittest.mock import MagicMock, patch

from core.suggestions import (
    _build_deny_set_json,
    _migrate_suggested_tracks,
    _normalize_key,
    build_messages,
    call_gpt,
    filter_duplicate_suggestions,
    load_text_file,
    normalize_history,
    normalize_response,
    update_profile,
)


class TestNormalizeKey:
    def test_basic(self):
        assert _normalize_key("Hello World") == "hello world"

    def test_strips_punctuation(self):
        assert _normalize_key("AC/DC - Highway to Hell") == "acdc highway to hell"

    def test_collapses_whitespace(self):
        assert _normalize_key("  lots   of   spaces  ") == "lots of spaces"

    def test_empty_string(self):
        assert _normalize_key("") == ""


class TestNormalizeHistory:
    def test_deduplicates_case_insensitive(self):
        profile = {
            "history": {
                "suggested_artists": ["Artist A", "artist a", "ARTIST A"],
                "suggested_tracks": ["Track 1", "track 1", "TRACK 1"],
            }
        }
        result = normalize_history(profile)
        assert len(result["history"]["suggested_artists"]) == 1
        assert result["history"]["suggested_artists"][0] == "artist a"
        assert len(result["history"]["suggested_tracks"]) == 1
        # After migration, string entries become {"artist": "", "track": "..."} dicts
        assert result["history"]["suggested_tracks"][0] == {"artist": "", "track": "track 1"}

    def test_empty_history(self):
        profile = {"history": {"suggested_artists": [], "suggested_tracks": []}}
        result = normalize_history(profile)
        assert result["history"]["suggested_artists"] == []
        assert result["history"]["suggested_tracks"] == []

    def test_preserves_order(self):
        profile = {
            "history": {
                "suggested_artists": ["Zebra", "Alpha", "Muse"],
                "suggested_tracks": [],
            }
        }
        result = normalize_history(profile)
        assert result["history"]["suggested_artists"] == ["zebra", "alpha", "muse"]

    def test_migrates_legacy_strings_to_dicts(self):
        profile = {
            "history": {
                "suggested_artists": ["pink floyd"],
                "suggested_tracks": ["pink floyd wish you were here"],
            }
        }
        result = normalize_history(profile)
        tracks = result["history"]["suggested_tracks"]
        assert len(tracks) == 1
        assert tracks[0] == {"artist": "pink floyd", "track": "wish you were here"}

    def test_dict_entries_pass_through_unchanged(self):
        profile = {
            "history": {
                "suggested_artists": ["radiohead"],
                "suggested_tracks": [{"artist": "radiohead", "track": "creep"}],
            }
        }
        result = normalize_history(profile)
        tracks = result["history"]["suggested_tracks"]
        assert tracks[0] == {"artist": "radiohead", "track": "creep"}


class TestFilterDuplicateSuggestions:
    def _make_result(self, playlist):
        artists = list({item["artist"] for item in playlist})
        tracks = [f"{item['artist']} {item['track']}" for item in playlist]
        return {
            "playlist": playlist,
            "new_artists": artists,
            "profile_updates": {
                "suggested_artists": artists,
                "suggested_tracks": tracks,
            },
        }

    def test_removes_history_duplicates(self):
        profile = {
            "history": {"suggested_tracks": ["artist1 track1"]},
            "feedback": {"disliked_tracks": []},
        }
        result = self._make_result(
            [
                {"artist": "artist1", "track": "track1", "reason": "r"},
                {"artist": "artist2", "track": "track2", "reason": "r"},
            ]
        )
        filtered = filter_duplicate_suggestions(profile, result)
        assert len(filtered["playlist"]) == 1
        assert filtered["playlist"][0]["artist"] == "artist2"

    def test_removes_disliked(self):
        profile = {
            "history": {"suggested_tracks": []},
            "feedback": {
                "disliked_tracks": [{"artist": "bad", "track": "song"}],
            },
        }
        result = self._make_result(
            [
                {"artist": "bad", "track": "song", "reason": "r"},
                {"artist": "good", "track": "hit", "reason": "r"},
            ]
        )
        filtered = filter_duplicate_suggestions(profile, result)
        assert len(filtered["playlist"]) == 1
        assert filtered["playlist"][0]["artist"] == "good"

    def test_removes_batch_duplicates(self):
        profile = {
            "history": {"suggested_tracks": []},
            "feedback": {"disliked_tracks": []},
        }
        result = self._make_result(
            [
                {"artist": "x", "track": "y", "reason": "r"},
                {"artist": "x", "track": "y", "reason": "r"},
            ]
        )
        filtered = filter_duplicate_suggestions(profile, result)
        assert len(filtered["playlist"]) == 1

    def test_empty_playlist_passthrough(self):
        profile = {
            "history": {"suggested_tracks": []},
            "feedback": {"disliked_tracks": []},
        }
        result = self._make_result([])
        filtered = filter_duplicate_suggestions(profile, result)
        assert filtered["playlist"] == []


def _extract_deny_json(user_message: str) -> dict:
    """Helper for tests: parse the deny-set JSON embedded in our test templates."""
    start = user_message.index("DENY:\n") + len("DENY:\n")
    end = user_message.index("\nPROFILE:")
    raw = user_message[start:end]
    return json.loads(raw)


class TestBuildDenySetJson:
    def test_empty_when_no_history(self):
        profile = {
            "history": {"suggested_tracks": [], "suggested_artists": []},
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        assert deny["forbidden_artists"] == []
        assert deny["exhausted_artists"] == []
        assert deny["forbidden_tracks"] == {}
        assert deny["disliked_tracks"] == {}

    def test_marks_exhausted_artist(self):
        profile = {
            "history": {
                "suggested_artists": ["artist x"],
                "suggested_tracks": [
                    "artist x t1",
                    "artist x t2",
                    "artist x t3",
                    "artist x t4",
                ],
            },
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        assert "artist x" in deny["exhausted_artists"]

    def test_includes_retry_forbidden_tracks(self):
        profile = {
            "history": {"suggested_tracks": [], "suggested_artists": []},
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile, ephemeral_deny_tracks={"a b"}))
        assert deny["retry_forbidden_tracks"] == ["a b"]


class TestBuildMessages:
    @patch("core.suggestions.load_text_file")
    def test_returns_two_messages(self, mock_load):
        mock_load.side_effect = [
            "You are a music bot. Generate {batch_size} tracks in {gpt_language}.",
            "DENY:\n{deny_set_json}\nPROFILE:{profile_json}\nPROFILE:\n{profile_json}\nFEEDBACK:\n{recent_feedback}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
            "preferences": {},
        }
        messages = build_messages(profile, batch_size=10)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "{batch_size}" not in messages[0]["content"]
        assert "{batch_size}" not in messages[1]["content"]
        assert "{gpt_language}" not in messages[0]["content"]

    @patch("core.suggestions.load_text_file")
    def test_recently_filtered_tracks_end_up_in_deny_set(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        filtered = [{"artist": "dup", "track": "song"}]
        messages = build_messages(profile, recently_filtered_tracks=filtered)
        deny = _extract_deny_json(messages[1]["content"])
        assert "retry_forbidden_tracks" in deny
        assert "dup song" in deny["retry_forbidden_tracks"]

    @patch("core.suggestions.load_text_file")
    def test_accepted_tracks_appended(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        accepted = [{"artist": "A", "track": "B"}]
        messages = build_messages(profile, accepted_tracks=accepted)
        assert "already accepted" in messages[1]["content"].lower()
        assert "A - B" in messages[1]["content"]


class TestNormalizeResponse:
    def test_lowercases_playlist_entries_and_strips_metadata(self):
        result = {
            "playlist": [{"artist": "AC/DC", "track": "Thunderstruck"}],
            "new_artists": ["AC/DC"],
            "profile_updates": {
                "suggested_artists": ["AC/DC"],
                "suggested_tracks": ["AC/DC Thunderstruck"],
            },
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["artist"] == "ac/dc"
        assert normalized["playlist"][0]["track"] == "thunderstruck"
        assert normalized["new_artists"] == []
        assert normalized["profile_updates"]["suggested_artists"] == []
        assert normalized["profile_updates"]["suggested_tracks"] == []

    def test_strips_validation_key(self):
        result = {
            "playlist": [],
            "validation": {"some": "data"},
        }
        normalized = normalize_response(result)
        assert "validation" not in normalized


class TestUpdateProfile:
    def test_adds_new_artists_and_tracks(self):
        profile = {
            "history": {
                "suggested_artists": ["existing artist"],
                "suggested_tracks": ["existing artist song1"],
            }
        }
        result = {
            "profile_updates": {
                "suggested_artists": ["new artist"],
                "suggested_tracks": [{"artist": "new artist", "track": "newsong"}],
            }
        }
        updated = update_profile(profile, result)
        assert "new artist" in updated["history"]["suggested_artists"]
        assert {"artist": "new artist", "track": "newsong"} in updated["history"]["suggested_tracks"]
        assert "existing artist" in updated["history"]["suggested_artists"]

    def test_no_duplicate_artists(self):
        profile = {
            "history": {
                "suggested_artists": ["artist a"],
                "suggested_tracks": [],
            }
        }
        result = {
            "profile_updates": {
                "suggested_artists": ["Artist A", "artist a"],
                "suggested_tracks": [],
            }
        }
        updated = update_profile(profile, result)
        count = sum(
            1 for a in updated["history"]["suggested_artists"] if a.lower() == "artist a"
        )
        assert count == 1

    def test_no_duplicate_tracks(self):
        profile = {
            "history": {
                "suggested_artists": [],
                "suggested_tracks": [{"artist": "", "track": "artist track1"}],
            }
        }
        result = {
            "profile_updates": {
                "suggested_artists": [],
                "suggested_tracks": [{"artist": "", "track": "Artist Track1"}],
            }
        }
        updated = update_profile(profile, result)
        # Dedup: normalized keys match — only one entry remains
        count = sum(
            1 for t in updated["history"]["suggested_tracks"]
            if isinstance(t, dict) and t.get("track", "").lower() == "artist track1"
        )
        assert count == 1


class TestCallGpt:
    @patch("core.suggestions.debug_log")
    @patch("core.suggestions.get_model", return_value="gpt-4o")
    @patch("core.suggestions.get_openai_client")
    def test_returns_parsed_json(self, mock_client_fn, mock_model, mock_log):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        gpt_response = {
            "playlist": [{"artist": "test", "track": "song"}],
            "new_artists": ["test"],
            "profile_updates": {
                "suggested_artists": ["test"],
                "suggested_tracks": ["test song"],
            },
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(gpt_response)
        mock_client.chat.completions.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = call_gpt(messages)
        assert result["playlist"][0]["artist"] == "test"
        assert result["playlist"][0]["track"] == "song"

    @patch("core.suggestions.debug_log")
    @patch("core.suggestions.get_model", return_value="gpt-4o")
    @patch("core.suggestions.get_openai_client")
    def test_handles_empty_response(self, mock_client_fn, mock_model, mock_log):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "   "
        mock_client.chat.completions.create.return_value = mock_response

        result = call_gpt([{"role": "user", "content": "test"}])
        assert result["playlist"] == []

    @patch("core.suggestions.debug_log")
    @patch("core.suggestions.get_model", return_value="gpt-4o")
    @patch("core.suggestions.get_openai_client")
    def test_handles_invalid_json(self, mock_client_fn, mock_model, mock_log):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"
        mock_client.chat.completions.create.return_value = mock_response

        result = call_gpt([{"role": "user", "content": "test"}])
        assert result["playlist"] == []

    @patch("core.suggestions.debug_log")
    @patch("core.suggestions.get_model", return_value="gpt-4o")
    @patch("core.suggestions.get_openai_client")
    def test_strips_code_fences_before_parse(self, mock_client_fn, mock_model, mock_log):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        gpt_response = {
            "playlist": [{"artist": "a", "track": "b"}],
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        fenced = f"```json\n{json.dumps(gpt_response)}\n```"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fenced
        mock_client.chat.completions.create.return_value = mock_response

        result = call_gpt([{"role": "user", "content": "test"}])
        assert len(result["playlist"]) == 1


class TestLoadTextFile:
    def test_loads_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        content = load_text_file(str(f))
        assert content == "hello world"

    def test_raises_for_missing_file(self, tmp_path):
        try:
            load_text_file(str(tmp_path / "nonexistent.txt"))
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass

