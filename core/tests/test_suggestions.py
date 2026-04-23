import json
from unittest.mock import MagicMock, patch

from core.src.suggestions import (
    _build_deny_set_json,
    _migrate_suggested_tracks,
    _normalize_key,
    _strip_gpt_annotation,
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

    def test_does_not_mutate_original_profile(self):
        """normalize_history must not modify the caller's profile dict."""
        original_artists = ["Artist A", "artist a"]
        original_tracks = [{"artist": "Radiohead", "track": "Creep"}]
        profile = {
            "history": {
                "suggested_artists": list(original_artists),
                "suggested_tracks": [dict(t) for t in original_tracks],
            },
            "preferences": {"core_description": "rock"},
        }
        result = normalize_history(profile)
        # Original must be unchanged
        assert profile["history"]["suggested_artists"] == original_artists
        assert profile["history"]["suggested_tracks"] == original_tracks
        # preferences must be the exact same object (shallow copy, not deep)
        assert result["preferences"] is profile["preferences"]


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
                    {"artist": "artist x", "track": "t1"},
                    {"artist": "artist x", "track": "t2"},
                    {"artist": "artist x", "track": "t3"},
                    {"artist": "artist x", "track": "t4"},
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
    @patch("core.src.suggestions.load_text_file")
    def test_returns_two_messages(self, mock_load):
        mock_load.side_effect = [
            "You are a music bot. Generate {batch_size} tracks in {gpt_language}.",
            "DENY:\n{deny_set_json}\nPROFILE:{profile_json}\nPROFILE:\n{profile_json}\nFEEDBACK:\n{recent_feedback}\n{audio_filters_block}\nNeed {batch_size} songs.",
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

    @patch("core.src.suggestions.load_text_file")
    def test_recently_filtered_tracks_end_up_in_deny_set(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
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

    @patch("core.src.suggestions.load_text_file")
    def test_accepted_tracks_appended(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        accepted = [{"artist": "A", "track": "B"}]
        messages = build_messages(profile, accepted_tracks=accepted)
        assert "already accepted" in messages[1]["content"].lower()
        assert "A - B" in messages[1]["content"]

    @patch("core.src.suggestions.load_text_file")
    def test_audio_filters_injected_into_prompt(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        filters = {"energy": {"min": 0.6, "max": 1.0}, "tempo": {"min": 120}}
        messages = build_messages(profile, audio_filters=filters)
        content = messages[1]["content"]
        assert "AUDIO FILTER CONSTRAINTS" in content
        assert "energy" in content
        assert "between 0.6 and 1.0" in content
        assert "tempo" in content
        assert "at least 120" in content

    @patch("core.src.suggestions.load_text_file")
    def test_no_audio_filters_no_block(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        messages = build_messages(profile, audio_filters=None)
        assert "AUDIO FILTER CONSTRAINTS" not in messages[1]["content"]

    @patch("core.src.suggestions.load_text_file")
    def test_emerging_only_injects_constraint_into_system_prompt(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size} {new_artist_percentage} {min_new_artists} {gpt_language}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        messages = build_messages(profile, batch_size=10, emerging_only=True)
        assert "debut release is within the last 6 months" in messages[0]["content"]

    @patch("core.src.suggestions.load_text_file")
    def test_emerging_only_false_no_constraint(self, mock_load):
        mock_load.side_effect = [
            "System prompt {batch_size} {new_artist_percentage} {min_new_artists} {gpt_language}.",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        messages = build_messages(profile, batch_size=10, emerging_only=False)
        assert "debut release" not in messages[0]["content"]

    @patch("core.src.suggestions.load_text_file")
    def test_emerging_only_uses_larger_buffer(self, mock_load):
        """emerging_only=True should request batch_size + 20 instead of batch_size + 5."""
        mock_load.side_effect = [
            "{batch_size}",
            "DENY:\n{deny_set_json}\nPROFILE:\n{profile_json}\n{audio_filters_block}\nNeed {batch_size} songs.",
        ]
        profile = {
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {},
        }
        messages = build_messages(profile, batch_size=10, emerging_only=True)
        # System prompt should contain "30" (10 + 20)
        assert "30" in messages[0]["content"]


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

    def test_drops_self_excluded_entries(self):
        """GPT sometimes includes forbidden tracks as 'excluded' placeholders."""
        result = {
            "playlist": [
                {"artist": "Good Artist", "track": "Good Song", "reason": "Fits the vibe."},
                {
                    "artist": "Boards of Canada (excluded due to forbidden tracks and history)",
                    "track": "Dayvan Cowboy",
                    "reason": "Forbidden track, excluded.",
                },
                {
                    "artist": "Emancipator",
                    "track": "Safe in the Steep Cliffs",
                    "reason": "Not suggested due to deny list.",
                },
            ],
        }
        normalized = normalize_response(result)
        assert len(normalized["playlist"]) == 1
        assert normalized["playlist"][0]["artist"] == "good artist"

    def test_strips_gpt_annotation_from_artist_names(self):
        """Parenthetical annotations like '(different track)' are stripped."""
        result = {
            "playlist": [
                {"artist": "Tycho (different track)", "track": "Hours", "reason": "Chill."},
                {"artist": "Helios (different track)", "track": "Reprise", "reason": "Ambient."},
                {"artist": "Nightmares on Wax (different from forbidden)", "track": "Les Nuits", "reason": "Classic."},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["artist"] == "tycho"
        assert normalized["playlist"][1]["artist"] == "helios"
        assert normalized["playlist"][2]["artist"] == "nightmares on wax"

    def test_preserves_legitimate_parentheticals(self):
        """Artist names with non-annotation parentheticals are left intact."""
        result = {
            "playlist": [
                {"artist": "Iron & Wine", "track": "Flightless Bird", "reason": "Calm."},
                {"artist": "fun.", "track": "We Are Young", "reason": "Pop."},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["artist"] == "iron & wine"
        assert normalized["playlist"][1]["artist"] == "fun."

    def test_normalizes_energy_valence(self):
        """Energy and valence floats from GPT are clamped to [0, 1]."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "energy": 0.85, "valence": 0.3},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["energy"] == 0.85
        assert normalized["playlist"][0]["valence"] == 0.3

    def test_clamps_energy_valence_out_of_range(self):
        """Values outside [0, 1] are clamped."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "energy": 1.5, "valence": -0.2},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["energy"] == 1.0
        assert normalized["playlist"][0]["valence"] == 0.0

    def test_strips_invalid_energy_valence(self):
        """Non-numeric energy/valence values are removed."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "energy": "high", "valence": None},
            ],
        }
        normalized = normalize_response(result)
        assert "energy" not in normalized["playlist"][0]

    def test_missing_energy_valence_ok(self):
        """Tracks without energy/valence are accepted (backward compat)."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "reason": "fits"},
            ],
        }
        normalized = normalize_response(result)
        assert "energy" not in normalized["playlist"][0]
        assert "valence" not in normalized["playlist"][0]

    def test_normalizes_genres(self):
        """GPT genres are lowercased, trimmed, and capped at 3."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T",
                 "genres": ["Indie Rock", " Alternative ", "Post-Punk", "Extra"]},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["genres"] == ["indie rock", "alternative", "post-punk"]

    def test_genres_defaults_to_empty_list(self):
        """Tracks without genres get an empty list."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "reason": "fits"},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["genres"] == []

    def test_genres_non_list_replaced(self):
        """Non-list genres value is replaced with empty list."""
        result = {
            "playlist": [
                {"artist": "A", "track": "T", "genres": "rock"},
            ],
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["genres"] == []


class TestStripGptAnnotation:
    _WORDS = {"different", "excluded", "forbidden", "not in",
              "due to", "see above", "alternate version",
              "from history", "other track", "previously"}

    def test_strips_different_track(self):
        assert _strip_gpt_annotation("Tycho (different track)", self._WORDS) == "Tycho"

    def test_strips_excluded_annotation(self):
        result = _strip_gpt_annotation(
            "Boards of Canada (excluded due to forbidden tracks and history)", self._WORDS
        )
        assert result == "Boards of Canada"

    def test_preserves_plain_artist(self):
        assert _strip_gpt_annotation("Massive Attack", self._WORDS) == "Massive Attack"

    def test_preserves_non_annotation_parens(self):
        assert _strip_gpt_annotation("The Orb (feat. David Gilmour)", self._WORDS) == "The Orb (feat. David Gilmour)"

    def test_preserves_empty_string(self):
        assert _strip_gpt_annotation("", self._WORDS) == ""


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
    @patch("core.src.suggestions.debug_log")
    @patch("core.src.suggestions.get_model", return_value="gpt-4o")
    @patch("core.src.suggestions.extract_chat_content")
    @patch("core.src.suggestions.chat_completions_create")
    def test_returns_parsed_json(self, mock_create, mock_extract, mock_model, mock_log):
        gpt_response = {
            "playlist": [{"artist": "test", "track": "song"}],
            "new_artists": ["test"],
            "profile_updates": {
                "suggested_artists": ["test"],
                "suggested_tracks": ["test song"],
            },
        }
        mock_create.return_value = MagicMock()
        mock_extract.return_value = json.dumps(gpt_response)

        messages = [{"role": "user", "content": "test"}]
        result = call_gpt(messages)
        assert result["playlist"][0]["artist"] == "test"
        assert result["playlist"][0]["track"] == "song"

    @patch("core.src.suggestions.debug_log")
    @patch("core.src.suggestions.get_model", return_value="gpt-4o")
    @patch("core.src.suggestions.extract_chat_content")
    @patch("core.src.suggestions.chat_completions_create")
    def test_handles_empty_response(self, mock_create, mock_extract, mock_model, mock_log):
        mock_create.return_value = MagicMock()
        mock_extract.return_value = "   "

        result = call_gpt([{"role": "user", "content": "test"}])
        assert result["playlist"] == []

    @patch("core.src.suggestions.debug_log")
    @patch("core.src.suggestions.get_model", return_value="gpt-4o")
    @patch("core.src.suggestions.extract_chat_content")
    @patch("core.src.suggestions.chat_completions_create")
    def test_handles_invalid_json(self, mock_create, mock_extract, mock_model, mock_log):
        mock_create.return_value = MagicMock()
        mock_extract.return_value = "not valid json at all"

        result = call_gpt([{"role": "user", "content": "test"}])
        assert result["playlist"] == []

    @patch("core.src.suggestions.debug_log")
    @patch("core.src.suggestions.get_model", return_value="gpt-4o")
    @patch("core.src.suggestions.extract_chat_content")
    @patch("core.src.suggestions.chat_completions_create")
    def test_strips_code_fences_before_parse(self, mock_create, mock_extract, mock_model, mock_log):
        gpt_response = {
            "playlist": [{"artist": "a", "track": "b"}],
            "new_artists": ["a"],
            "profile_updates": {"suggested_artists": ["a"], "suggested_tracks": ["a b"]},
        }
        fenced = f"```json\n{json.dumps(gpt_response)}\n```"
        mock_create.return_value = MagicMock()
        mock_extract.return_value = fenced

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


class TestNormalizeRationale:
    """Wave 3: rationale parsing tests."""

    def test_well_formed_rationale_passes_through(self):
        from core.src.suggestions import _normalize_rationale
        entry = {
            "rationale": [
                {"type": "profile_match", "arg": "indie rock"},
                {"type": "artist_match", "arg": "Foo Fighters"},
            ]
        }
        result = _normalize_rationale(entry)
        assert len(result) == 2
        assert result[0]["type"] == "profile_match"
        assert result[1]["arg"] == "Foo Fighters"

    def test_unknown_type_dropped(self):
        from core.src.suggestions import _normalize_rationale
        entry = {
            "rationale": [
                {"type": "unknown_type", "arg": "test"},
                {"type": "profile_match", "arg": "rock"},
            ]
        }
        result = _normalize_rationale(entry)
        assert len(result) == 1
        assert result[0]["type"] == "profile_match"

    def test_capped_to_2_entries(self):
        from core.src.suggestions import _normalize_rationale
        entry = {
            "rationale": [
                {"type": "profile_match", "arg": "a"},
                {"type": "artist_match", "arg": "b"},
                {"type": "recency", "arg": "c"},
            ]
        }
        result = _normalize_rationale(entry)
        assert len(result) == 2

    def test_arg_truncated_to_40_chars(self):
        from core.src.suggestions import _normalize_rationale
        long_arg = "a" * 60
        entry = {"rationale": [{"type": "profile_match", "arg": long_arg}]}
        result = _normalize_rationale(entry)
        assert len(result[0]["arg"]) == 40

    def test_legacy_fallback_from_reason(self):
        from core.src.suggestions import _normalize_rationale
        entry = {"reason": "Matches your profile"}
        result = _normalize_rationale(entry)
        assert len(result) == 1
        assert result[0]["type"] == "legacy"
        assert result[0]["arg"] == "Matches your profile"

    def test_fallback_when_both_missing(self):
        from core.src.suggestions import _normalize_rationale
        entry = {}
        result = _normalize_rationale(entry)
        assert len(result) == 1
        assert result[0]["type"] == "fallback"

    def test_empty_rationale_array_falls_back(self):
        from core.src.suggestions import _normalize_rationale
        entry = {"rationale": []}
        result = _normalize_rationale(entry)
        assert result[0]["type"] == "fallback"

    def test_missing_arg_dropped(self):
        from core.src.suggestions import _normalize_rationale
        entry = {"rationale": [{"type": "novelty"}, {"type": "profile_match", "arg": "rock"}]}
        result = _normalize_rationale(entry)
        assert len(result) == 1
        assert result[0]["type"] == "profile_match"

    def test_empty_arg_dropped(self):
        from core.src.suggestions import _normalize_rationale
        entry = {"rationale": [{"type": "recency", "arg": ""}, {"type": "novelty", "arg": "  "}]}
        result = _normalize_rationale(entry)
        assert result[0]["type"] == "fallback"

    def test_normalize_response_adds_rationale(self):
        result = {
            "playlist": [
                {"artist": "Muse", "track": "Hysteria", "rationale": [{"type": "profile_match", "arg": "rock"}]},
                {"artist": "Queen", "track": "Bohemian Rhapsody", "reason": "classic"},
            ]
        }
        normalized = normalize_response(result)
        assert normalized["playlist"][0]["rationale"][0]["type"] == "profile_match"
        assert normalized["playlist"][1]["rationale"][0]["type"] == "legacy"


