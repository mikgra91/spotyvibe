import json
from unittest.mock import MagicMock, patch

import pytest

from core.src.suggestions import (
    _build_deny_set_json,
    _hash_messages_for_audit,
    _migrate_suggested_tracks,
    _normalize_key,
    _resolve_stage3_model,
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

    def test_artist_track_counts_block_present(self):
        # C3 (2026-05-10): every render carries the new aggregate, even
        # when history is small enough to fit in the verbatim window.
        profile = {
            "history": {
                "suggested_artists": ["artist x"],
                "suggested_tracks": [
                    {"artist": "artist x", "track": "t1"},
                    {"artist": "artist x", "track": "t2"},
                ],
            },
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        assert deny["artist_track_counts"] == {"artist x": 2}
        # Verbatim block also still present for the recent slice.
        assert deny["forbidden_tracks"] == {"artist x": ["t1", "t2"]}

    def test_artist_track_counts_sorted_descending_by_count(self):
        # Highest-signal artists first so smaller models hit them earliest.
        profile = {
            "history": {
                "suggested_artists": ["a", "b", "c"],
                "suggested_tracks": (
                    [{"artist": "low", "track": f"t{i}"} for i in range(1)]
                    + [{"artist": "high", "track": f"t{i}"} for i in range(5)]
                    + [{"artist": "mid", "track": f"t{i}"} for i in range(3)]
                ),
            },
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        assert list(deny["artist_track_counts"].keys()) == ["high", "mid", "low"]

    def test_forbidden_tracks_trimmed_to_recent_window(self, monkeypatch):
        # Use a non-default boundary (10) so the trim is unambiguously
        # the code under test, not the default constant. With 30 historical
        # tracks and RECENT_VERBATIM_TRACKS=10, only the latest 10 should
        # appear verbatim — but the aggregate still reflects all 30.
        monkeypatch.setattr("core.src.suggestions.RECENT_VERBATIM_TRACKS", 10)
        history = (
            [{"artist": "old", "track": f"o{i}"} for i in range(20)]
            + [{"artist": "new", "track": f"n{i}"} for i in range(10)]
        )
        profile = {
            "history": {"suggested_tracks": history, "suggested_artists": []},
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        # Verbatim: only 'new' (the last 10); 'old' is past the window.
        assert "old" not in deny["forbidden_tracks"]
        assert "new" in deny["forbidden_tracks"]
        assert len(deny["forbidden_tracks"]["new"]) == 10
        # Aggregate covers everything still in GPT_HISTORY_LIMIT scope.
        assert deny["artist_track_counts"]["old"] == 20
        assert deny["artist_track_counts"]["new"] == 10
        # Both old and new exhaust the threshold (4) — long-tail artists
        # the verbatim block forgot are still surfaced as exhausted.
        assert "old" in deny["exhausted_artists"]
        assert "new" in deny["exhausted_artists"]

    def test_exhausted_artists_drives_off_aggregate_not_recent_window(self):
        # An artist with 5 tracks all in the older slice (beyond the
        # verbatim window) must still be marked exhausted via the aggregate.
        history = (
            [{"artist": "buried", "track": f"b{i}"} for i in range(5)]
            + [{"artist": "fresh", "track": f"f{i}"} for i in range(100)]
        )
        profile = {
            "history": {"suggested_tracks": history, "suggested_artists": []},
            "artists": {"rejected": []},
            "feedback": {"disliked_artists": [], "disliked_tracks": []},
        }
        deny = json.loads(_build_deny_set_json(profile))
        assert "buried" in deny["exhausted_artists"]
        # And buried doesn't appear verbatim anymore.
        assert "buried" not in deny["forbidden_tracks"]


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


class TestNormalizeResponseSchemaCollapse:
    """Phase 1 schema-collapse fix (2026-04-27).

    Pin the four invariants of the anti-confabulation guard so a future
    refactor of normalize_response cannot silently re-open the regression
    that drove gpt-5.4-mini's Spotify-found rate from 96.8% to 7.7%.
    """

    def test_drops_track_equals_artist_case_insensitive(self):
        result = {"playlist": [
            {"artist": "The Newfangled Four", "track": "the newfangled four"},
            {"artist": "Bear Ghost", "track": "Necromancin' Dancin'"},
        ]}
        normalized = normalize_response(result)
        assert len(normalized["playlist"]) == 1
        assert normalized["playlist"][0]["artist"] == "bear ghost"
        assert normalized["_schema_collapse"]["eq_artist"] == 1
        assert normalized["_schema_collapse"]["total"] == 1

    def test_drops_placeholder_track_tokens(self):
        result = {"playlist": [
            {"artist": "Foo", "track": "untitled"},
            {"artist": "Bar", "track": "intro"},
            {"artist": "Baz", "track": "-"},
            {"artist": "Qux", "track": "Real Title"},
        ]}
        normalized = normalize_response(result)
        assert len(normalized["playlist"]) == 1
        assert normalized["playlist"][0]["artist"] == "qux"
        assert normalized["_schema_collapse"]["placeholder_token"] == 3

    def test_drops_duplicate_within_batch(self):
        result = {"playlist": [
            {"artist": "Tally Hall", "track": "Good Day"},
            {"artist": "tally hall", "track": "good day"},  # dup post-norm
            {"artist": "Tally Hall", "track": "Banana Man"},
        ]}
        normalized = normalize_response(result)
        assert len(normalized["playlist"]) == 2
        tracks = {e["track"] for e in normalized["playlist"]}
        assert tracks == {"good day", "banana man"}
        assert normalized["_schema_collapse"]["dup_in_batch"] == 1

    def test_schema_collapse_meta_zeroed_when_clean(self):
        result = {"playlist": [
            {"artist": "Tally Hall", "track": "Good Day"},
            {"artist": "Bear Ghost", "track": "Necromancin' Dancin'"},
        ]}
        normalized = normalize_response(result)
        assert len(normalized["playlist"]) == 2
        sc = normalized["_schema_collapse"]
        assert sc == {"eq_artist": 0, "placeholder_token": 0,
                      "dup_in_batch": 0, "total": 0}


class TestHashMessagesForAudit:
    """Tier 1 (2026-05-10) — prompt-prefix hashes catch drift between
    runs and let the eval log group calls by cache-eligible prefix.
    """

    def test_hashes_system_and_user_separately(self):
        msgs = [
            {"role": "system", "content": "you are a helpful assistant"},
            {"role": "user", "content": "hello"},
        ]
        h = _hash_messages_for_audit(msgs)
        assert "system_md5" in h and len(h["system_md5"]) == 16
        assert "user_md5" in h and len(h["user_md5"]) == 16
        assert h["system_md5"] != h["user_md5"]

    def test_identical_input_yields_identical_hash(self):
        msgs1 = [{"role": "system", "content": "X"}, {"role": "user", "content": "Y"}]
        msgs2 = [{"role": "system", "content": "X"}, {"role": "user", "content": "Y"}]
        assert _hash_messages_for_audit(msgs1) == _hash_messages_for_audit(msgs2)

    def test_different_content_yields_different_hash(self):
        msgs1 = [{"role": "system", "content": "X"}, {"role": "user", "content": "Y1"}]
        msgs2 = [{"role": "system", "content": "X"}, {"role": "user", "content": "Y2"}]
        h1 = _hash_messages_for_audit(msgs1)
        h2 = _hash_messages_for_audit(msgs2)
        # System unchanged, user changed.
        assert h1["system_md5"] == h2["system_md5"]
        assert h1["user_md5"] != h2["user_md5"]

    def test_only_first_system_and_first_user_hashed(self):
        # Defensive: a multi-turn message list shouldn't blow up the
        # field map; we only care about the first occurrence of each role.
        msgs = [
            {"role": "system", "content": "first system"},
            {"role": "user", "content": "first user"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second user"},
        ]
        h = _hash_messages_for_audit(msgs)
        assert set(h.keys()) == {"system_md5", "user_md5"}

    def test_empty_or_malformed_returns_empty(self):
        assert _hash_messages_for_audit([]) == {}
        assert _hash_messages_for_audit(None) == {}
        # Malformed entries are skipped silently (telemetry must not crash).
        assert _hash_messages_for_audit([{"no": "role"}, "string"]) == {}


class TestResolveStage3Model:
    """2026-05-14 — STAGE3_MODE switch removed. The resolver now always
    returns get_model(); profile + mode args are ignored.
    """

    def test_always_returns_get_model(self):
        with patch("core.src.suggestions.get_model", return_value="deepseek/deepseek-v4-flash"):
            assert _resolve_stage3_model() == "deepseek/deepseek-v4-flash"
            assert _resolve_stage3_model({}) == "deepseek/deepseek-v4-flash"
            assert _resolve_stage3_model(None, mode="ignored") == "deepseek/deepseek-v4-flash"

    def test_passthrough_for_arbitrary_model(self):
        with patch("core.src.suggestions.get_model", return_value="local-llama-3.1"):
            assert _resolve_stage3_model({"feedback": {"disliked_tracks": [{"a": "b"}]}}) == "local-llama-3.1"


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
    def test_meta_carries_tier1_diagnostics(self, mock_create, mock_extract, mock_model, mock_log):
        # Tier 1 (2026-05-10): system_fingerprint + prompt_hashes must
        # propagate via the meta dict so eval_log.batch_summary can
        # detect silent OpenAI model rolls and prompt drift.
        mock_create.return_value = {
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "system_fingerprint": "fp_abc123",
        }
        mock_extract.return_value = '{"playlist": [], "new_artists": [], "profile_updates": {"suggested_artists": [], "suggested_tracks": []}}'
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user message"},
        ]
        result, meta = call_gpt(msgs, return_meta=True)
        assert meta["system_fingerprint"] == "fp_abc123"
        assert "system_md5" in meta["prompt_hashes"]
        assert "user_md5" in meta["prompt_hashes"]
        assert meta["usage"]["prompt_tokens"] == 100
        assert meta["latency_s"] >= 0

    @patch("core.src.suggestions.debug_log")
    @patch("core.src.suggestions.get_model", return_value="gpt-4o")
    @patch("core.src.suggestions.extract_chat_content")
    @patch("core.src.suggestions.chat_completions_create")
    def test_meta_handles_missing_system_fingerprint(self, mock_create, mock_extract, mock_model, mock_log):
        # Local LLMs (Ollama, LM Studio) don't return system_fingerprint.
        # The meta must surface None rather than KeyError-ing telemetry.
        mock_create.return_value = {
            "usage": {"prompt_tokens": 50, "completion_tokens": 25},
            # no system_fingerprint key
        }
        mock_extract.return_value = '{"playlist": []}'
        result, meta = call_gpt([{"role": "user", "content": "x"}], return_meta=True)
        assert meta["system_fingerprint"] is None

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
        with pytest.raises(FileNotFoundError):
            load_text_file(str(tmp_path / "nonexistent.txt"))

    def test_caches_repeated_reads(self, tmp_path):
        """L4 (2026-05-07): identical paths must hit the LRU cache so
        Stage 3's per-batch prompt loads don't re-read four files
        ten times each per playlist run."""
        f = tmp_path / "cached.txt"
        f.write_text("v1", encoding="utf-8")
        # Clear any state from prior tests in the same session.
        load_text_file.cache_clear()
        first = load_text_file(str(f))
        # Mutate the file on disk — the cache must NOT pick this up
        # within the same session (that's the whole point of the cache).
        f.write_text("v2", encoding="utf-8")
        second = load_text_file(str(f))
        assert first == second == "v1"
        info = load_text_file.cache_info()
        assert info.hits >= 1
        # cache_clear lets a long-lived process reload after a manual
        # prompt-file edit.
        load_text_file.cache_clear()
        third = load_text_file(str(f))
        assert third == "v2"


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

    def test_arg_truncated_to_80_chars(self):
        # 2026-04-28: cap bumped 40 → 80 to keep paraphrased args produced
        # under strict json_schema (OPEN-3) within match range of the
        # has_must_have_cite metric. UI chip styling wraps long labels.
        from core.src.suggestions import _normalize_rationale
        long_arg = "a" * 100
        entry = {"rationale": [{"type": "profile_match", "arg": long_arg}]}
        result = _normalize_rationale(entry)
        assert len(result[0]["arg"]) == 80

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


# ── Phase 1: build_taste_summary ─────────────────────────────────────

class TestBuildTasteSummary:
    def _call(self, profile):
        from core.src.suggestions import build_taste_summary
        return build_taste_summary(profile)

    def test_basic_fields_included(self):
        profile = {
            "preferences": {
                "must_have": ["punchy guitars", "hooks"],
                "soft_preferences": ["theatrical", "quirky"],
                "avoid": ["classic rock"],
                "eras": ["modern"],
            },
            "artists": {"confirmed": [{"name": "Bear Ghost"}, {"name": "Tally Hall"}]},
            "meta": {"primary_reference": "Bear Ghost"},
        }
        summary = self._call(profile)
        assert "Must:" in summary
        assert "punchy guitars" in summary
        assert "Avoid:" in summary
        assert "classic rock" in summary
        assert "Style anchors:" in summary
        assert "Bear Ghost" in summary

    def test_empty_profile_returns_empty_string(self):
        assert self._call({}) == ""
        assert self._call(None) == ""  # type: ignore[arg-type]

    def test_length_cap(self):
        # P-compact (2026-05-19): per-section caps + aggregate cap (default
        # 1200 chars). A 2000-char core_description hits the per-section
        # 200-char cap first, so the rendered summary stays well under the
        # aggregate cap.
        long_desc = "x" * 2000
        profile = {"preferences": {"core_description": long_desc}}
        summary = self._call(profile)
        assert len(summary) <= 1200
        # Per-section cap also enforced: core_description itself does not
        # exceed its 200-char per-section cap (+1 for the truncation marker).
        assert "x" * 220 not in summary

    def test_section_truncation_telemetry(self):
        # When must_have overflows its per-section cap, telemetry must
        # mark that specific section truncated — production code can then
        # alert / log without re-tokenising.
        from core.src.suggestions import get_last_taste_summary_telemetry
        long_must = ", ".join([f"trait-{i}" for i in range(60)])
        profile = {"preferences": {"must_have": [long_must]}}
        self._call(profile)
        tel = get_last_taste_summary_telemetry()
        assert tel is not None
        assert tel["must_have"]["truncated"] is True
        assert tel["any_section_truncated"] is True

    def test_no_truncation_on_small_profile(self):
        from core.src.suggestions import get_last_taste_summary_telemetry
        profile = {
            "preferences": {"must_have": ["hooks"], "avoid": ["screamo"]},
            "artists": {"confirmed": [{"name": "Tally Hall"}]},
        }
        self._call(profile)
        tel = get_last_taste_summary_telemetry()
        assert tel is not None
        assert tel["any_section_truncated"] is False
        assert tel["summary_truncated"] is False
        assert tel["facet_count"] == 3  # 1 must + 1 avoid + 1 anchor

    def test_must_have_preserved_when_core_description_huge(self):
        # Regression for the bug this work is preventing: the previous
        # 800-char aggregate cap meant a 2000-char core_description could
        # crowd the must_have / avoid sections out of the summary
        # entirely. With per-section caps, must_have and avoid always fit.
        profile = {
            "preferences": {
                "must_have": ["punchy guitars", "modern production"],
                "avoid": ["80s production", "classic rock"],
                "core_description": "y" * 5000,
            },
        }
        summary = self._call(profile)
        assert "punchy guitars" in summary
        assert "80s production" in summary

    def test_env_override_aggregate_cap(self):
        import os
        from core.src.suggestions import build_taste_summary
        os.environ["SPOTYVIBE_TASTE_SUMMARY_MAX_CHARS"] = "300"
        try:
            profile = {
                "preferences": {
                    "must_have": ["hooks"] * 10,
                    "avoid": ["nu-metal"] * 10,
                    "core_description": "z" * 500,
                },
            }
            summary = build_taste_summary(profile)
            assert len(summary) <= 300
        finally:
            del os.environ["SPOTYVIBE_TASTE_SUMMARY_MAX_CHARS"]

    def test_confirmed_anchors_capped_at_five(self):
        confirmed = [{"name": f"Artist {i}"} for i in range(10)]
        profile = {"artists": {"confirmed": confirmed}}
        summary = self._call(profile)
        # Only first 5 appear in anchors block
        assert "Artist 0" in summary
        assert "Artist 5" not in summary

    def test_no_avoid_no_avoid_line(self):
        profile = {"preferences": {"must_have": ["hooks"]}}
        summary = self._call(profile)
        assert "Avoid:" not in summary


# ── P-compact (2026-05-19): build_focused_taste_summary ──────────────

class TestBuildFocusedTasteSummary:
    def test_empty_pool_tags_falls_back_to_default(self):
        from core.src.suggestions import (
            build_focused_taste_summary, build_taste_summary,
        )
        profile = {
            "preferences": {
                "must_have": ["hooks"], "avoid": ["screamo"],
            },
        }
        focused = build_focused_taste_summary(profile, pool_tags=None)
        plain = build_taste_summary(profile)
        assert focused == plain

    def test_focus_picks_overlapping_items(self):
        from core.src.suggestions import build_focused_taste_summary
        # Pool is heavy on "indie pop" + "art pop" → must_have items
        # mentioning "pop" should rank higher than the off-topic
        # "thrash metal" one when we keep only 2 per section.
        profile = {
            "preferences": {
                "must_have": [
                    "thrash metal energy",
                    "indie pop hooks",
                    "art pop quirk",
                    "trap drums",
                    "punchy guitars",
                    "anime vocals",
                    "modern production",
                    "shoegaze drone",
                    "math rock rhythms",
                    "k-pop polish",
                    "synth pop lead",
                    "garage rock vibe",
                ],
                "avoid": [],
            },
        }
        pool_tags = ["indie pop"] * 30 + ["art pop"] * 20 + ["math rock"] * 5
        summary = build_focused_taste_summary(
            profile, pool_tags=pool_tags, top_k_per_section=2,
        )
        # The two highest-overlap must_have items are pop-flavoured; an
        # off-topic "trap drums" should not survive top-2.
        assert "indie pop" in summary
        assert "art pop" in summary
        assert "trap drums" not in summary

    def test_short_lists_kept_intact(self):
        from core.src.suggestions import build_focused_taste_summary
        profile = {
            "preferences": {
                "must_have": ["hooks", "energy"],
                "avoid": ["screamo"],
            },
        }
        pool_tags = ["indie pop"] * 10
        summary = build_focused_taste_summary(
            profile, pool_tags=pool_tags, top_k_per_section=5,
        )
        # Lists under top_k_per_section stay intact regardless of score.
        assert "hooks" in summary
        assert "energy" in summary
        assert "screamo" in summary

    def test_telemetry_records_focused_block(self):
        from core.src.suggestions import (
            build_focused_taste_summary, get_last_taste_summary_telemetry,
        )
        profile = {
            "preferences": {
                "must_have": [f"facet-{i}" for i in range(15)],
            },
        }
        build_focused_taste_summary(
            profile, pool_tags=["indie pop"] * 5, top_k_per_section=3,
        )
        tel = get_last_taste_summary_telemetry()
        assert tel is not None
        assert "focused" in tel
        assert tel["focused"]["enabled"] is True
        assert tel["focused"]["must_have_in"] == 15
        assert tel["focused"]["must_have_kept"] == 3

# ── Phase 1: check_avoid_compliance ──────────────────────────────────

class TestCheckAvoidCompliance:
    def _call(self, artist_names, avoid_traits, mock_response=None):
        from core.src.suggestions import check_avoid_compliance
        import json
        from unittest.mock import patch
        if mock_response is None:
            mock_response = json.dumps({"approved": list(artist_names)})

        def _fake_create(**kwargs):
            return {"choices": [{"message": {"content": mock_response}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                return check_avoid_compliance(artist_names, avoid_traits)

    def test_empty_artists_returns_empty(self):
        from core.src.suggestions import check_avoid_compliance
        approved, meta = check_avoid_compliance([], ["classic rock"])
        assert approved == []
        assert meta["status"] == "skipped_empty_input"

    def test_no_avoid_traits_returns_all(self):
        from core.src.suggestions import check_avoid_compliance
        names = ["Artist A", "Artist B"]
        approved, meta = check_avoid_compliance(names, [])
        assert approved == names
        assert meta["status"] == "skipped_no_avoid"
        approved2, meta2 = check_avoid_compliance(names, None)
        assert approved2 == names
        assert meta2["status"] == "skipped_no_avoid"

    def test_skipped_no_overlap_when_stage1_already_filtered(self):
        """L1 (2026-04-29): when Stage 1 reports pool_avoid_overlap=0 AND
        every avoid trait was tag-covered (F3, 2026-05-01) the LLM call
        must be skipped — Stage 1's tag filter already removed every
        candidate matching an avoid trait. Ship-blocker for the
        cost-saving path; keep this assertion strict."""
        from core.src.suggestions import check_avoid_compliance
        names = ["Artist A", "Artist B"]
        approved, meta = check_avoid_compliance(
            names, ["classic rock"],
            pool_avoid_overlap=0,
            avoid_traits_fully_covered=True,
        )
        assert approved == names
        assert meta["status"] == "skipped_no_overlap"
        assert meta["latency_s"] is None  # no LLM call → no latency
        assert meta["prompt_chars"] == 0  # no LLM call → no prompt built

    def test_skip_suppressed_when_traits_not_fully_covered(self):
        """F3 (2026-05-01): pool_avoid_overlap=0 alone is not enough to
        skip — when at least one avoid prose entry produced zero
        corpus-resolved tags (e.g. "American artists", "80s production
        style") the zero-overlap signal is meaningless and the LLM
        semantic check MUST run. Regression guard for the F3
        production failure."""
        names = ["American Rock Band"]
        response = '{"approved": []}'  # LLM rejects the American artist
        from core.src.suggestions import check_avoid_compliance
        from unittest.mock import patch
        with patch(
            "core.src.suggestions.chat_completions_create",
            side_effect=lambda **kw: {
                "choices": [{"message": {"content": response}}],
                "usage": None,
            },
        ):
            with patch(
                "core.src.suggestions.extract_chat_content",
                side_effect=lambda r: r["choices"][0]["message"]["content"],
            ):
                approved, meta = check_avoid_compliance(
                    names,
                    ["American artists", "80s production style"],
                    pool_avoid_overlap=0,
                    avoid_traits_fully_covered=False,
                )
        assert approved == []  # LLM filtered the unsafe artist
        assert meta["status"] == "ok"  # LLM was called, not skipped
        assert meta["latency_s"] is not None
        assert meta["prompt_chars"] > 0

    def test_overlap_nonzero_still_calls_llm(self):
        """When Stage 1 reports residual avoid-tag overlap (e.g. filter was
        bypassed for being too aggressive), the LLM check must still run."""
        names = ["Artist A", "Classic Rock Band"]
        response = '{"approved": ["Artist A"]}'
        from core.src.suggestions import check_avoid_compliance
        import json as _json
        from unittest.mock import patch
        with patch("core.src.suggestions.chat_completions_create",
                   side_effect=lambda **kw: {"choices": [{"message": {"content": response}}], "usage": None}):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                approved, meta = check_avoid_compliance(
                    names, ["classic rock"], pool_avoid_overlap=1,
                )
        assert approved == ["Artist A"]
        assert meta["status"] == "ok"

    def test_approved_subset_returned(self):
        names = ["Good Band", "Classic Rock Band", "Indie Artist"]
        response = '{"approved": ["Good Band", "Indie Artist"]}'
        approved, meta = self._call(names, ["classic rock"], mock_response=response)
        assert set(approved) == {"Good Band", "Indie Artist"}
        assert "Classic Rock Band" not in approved
        assert meta["status"] == "ok"
        assert meta["latency_s"] is not None
        assert meta["prompt_chars"] > 0

    def test_only_original_names_returned(self):
        """LLM cannot inject new names not in the input list."""
        names = ["Artist A"]
        response = '{"approved": ["Artist A", "Injected Artist"]}'
        approved, _meta = self._call(names, ["avoid trait"], mock_response=response)
        assert approved == ["Artist A"]
        assert "Injected Artist" not in approved

    def test_fallback_on_llm_error(self):
        from core.src.suggestions import check_avoid_compliance
        from unittest.mock import patch
        names = ["Artist A", "Artist B"]
        with patch("core.src.suggestions.chat_completions_create", side_effect=RuntimeError("api down")):
            approved, meta = check_avoid_compliance(names, ["rock"])
        assert approved == names
        assert meta["status"] == "error"

    def test_invalid_json_response_marks_status(self):
        names = ["Artist A"]
        response = "not even close to json"
        approved, meta = self._call(names, ["rock"], mock_response=response)
        # Falls through except branch — JSONDecodeError is an Exception
        assert approved == names
        assert meta["status"] == "error"


# ── F7 (2026-05-01): _filter_diversity_hints ─────────────────────────

class TestFilterDiversityHints:
    """Diversity hints that contradict the user's avoid prose are dropped
    so the model never sees "Focus on 1970s-1980s artists" alongside an
    avoid entry of "80s production style" (F7 production failure)."""

    _HINTS = [
        "Focus on artists from the 1970s-1980s that match the profile.",
        "Explore Japanese, Korean, or Scandinavian artists matching the profile.",
        "Look for artists who released their first album after 2020.",
        "Consider solo projects or side projects of artists similar to the anchors.",
        "Explore soundtrack and compilation albums for hidden gems.",
    ]

    def test_no_avoid_passthrough(self):
        from core.src.suggestions import _filter_diversity_hints
        assert _filter_diversity_hints(self._HINTS, None) == self._HINTS
        assert _filter_diversity_hints(self._HINTS, []) == self._HINTS

    def test_drops_decade_conflict_short_form(self):
        from core.src.suggestions import _filter_diversity_hints
        out = _filter_diversity_hints(self._HINTS, ["80s production style"])
        assert "Focus on artists from the 1970s-1980s that match the profile." not in out
        assert len(out) == len(self._HINTS) - 1

    def test_drops_decade_conflict_long_form(self):
        from core.src.suggestions import _filter_diversity_hints
        out = _filter_diversity_hints(self._HINTS, ["Avoid 1980s synth-pop"])
        assert all("1970s-1980s" not in h for h in out)

    def test_keeps_unrelated_hints(self):
        from core.src.suggestions import _filter_diversity_hints
        out = _filter_diversity_hints(self._HINTS, ["Excessive synthesizers"])
        # No decade conflict; "synthesizers" doesn't appear in any hint
        assert out == self._HINTS

    def test_drops_keyword_conflict(self):
        from core.src.suggestions import _filter_diversity_hints
        out = _filter_diversity_hints(
            self._HINTS, ["No soundtrack-style instrumentals please"],
        )
        assert all("soundtrack" not in h.lower() for h in out)


# ── Phase 1: select_tracks ───────────────────────────────────────────

class TestSelectTracks:
    _GOOD_RESULT = {
        "playlist": [
            {
                "artist": "good band", "track": "great song",
                "reason": "fits taste", "energy": 0.8, "valence": 0.7,
                "genres": ["indie rock"],
                "rationale": [{"type": "profile_match", "arg": "punchy guitars"}],
            }
        ]
    }

    def _make_profile(self):
        return {
            "preferences": {"must_have": ["hooks"], "soft_preferences": ["quirky"], "avoid": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
            "artists": {"confirmed": [], "rejected": []},
            "meta": {},
        }

    def _call(self, approved_names, taste_summary, batch_size, profile, **kwargs):
        from core.src.suggestions import select_tracks
        import json
        from unittest.mock import patch

        raw_json = json.dumps(self._GOOD_RESULT)

        def _fake_create(**kw):
            return {"choices": [{"message": {"content": raw_json}}], "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                return select_tracks(approved_names, taste_summary, batch_size, profile, **kwargs)

    def test_returns_tuple_result_meta(self):
        profile = self._make_profile()
        result, meta = self._call(["Good Band", "Other Band"], "Must: hooks.", 10, profile)
        assert isinstance(result, dict)
        assert "playlist" in result
        assert "latency_s" in meta

    def test_result_normalized(self):
        profile = self._make_profile()
        result, _ = self._call(["Good Band", "Other Band"], "Must: hooks.", 10, profile)
        # normalize_response lowercases artist/track
        assert result["playlist"][0]["artist"] == "good band"

    def test_empty_response_returns_empty_playlist(self):
        from core.src.suggestions import select_tracks
        from unittest.mock import patch

        def _fake_create(**kw):
            return {"choices": [{"message": {"content": ""}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content", return_value=""):
                result, meta = select_tracks(
                    ["Artist A", "Artist B"], "summary", 5, self._make_profile()
                )
        assert result["playlist"] == []
        assert meta["latency_s"] >= 0

    def test_prompt_components_captured(self):
        from core.src.suggestions import get_last_prompt_components
        profile = self._make_profile()
        self._call(["Good Band", "Other Band"], "Must: hooks.", 10, profile)
        components = get_last_prompt_components()
        assert components is not None
        assert components["pool"] > 0   # approved artists block
        assert components["deny_set"] == 0  # no deny list in Stage 3
        assert components["profile"] == 0   # no full profile JSON

    def test_l11_effective_batch_size_uses_stage3_over_request_constant(self):
        """L11 (2026-04-29): the buffer that turns batch_size=10 into the
        effective request was reduced from a hardcoded +5 to the configurable
        STAGE3_OVER_REQUEST constant (default 2). Sweep evidence: Spotify-found
        was 100% on 58/60 rows so the +5 buffer was wasted output tokens."""
        from core.src.suggestions import select_tracks
        from config import STAGE3_OVER_REQUEST
        from unittest.mock import patch
        import json as _json

        # The system prompt receives `{batch_size}` substituted with the
        # effective_batch_size. We capture the rendered prompt and assert
        # the substitution used batch_size + STAGE3_OVER_REQUEST.
        captured = {}
        def _fake_create(**kw):
            captured["messages"] = kw.get("messages")
            return {"choices": [{"message": {"content": _json.dumps(self._GOOD_RESULT)}}],
                    "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                select_tracks(["Good Band", "Other Band"], "Must: hooks.", 10, self._make_profile())

        system_msg = captured["messages"][0]["content"]
        expected = 10 + STAGE3_OVER_REQUEST
        # The system prompt rendered the effective batch size — assert it
        # matches the new formula. Search for the integer in context to
        # avoid false positives on unrelated numbers.
        assert f"UP TO {expected}" in captured["messages"][1]["content"] or \
               str(expected) in system_msg, \
            f"effective_batch_size={expected} not visible in rendered prompt"
        # Hard guard against accidental revert to the old +5.
        assert STAGE3_OVER_REQUEST <= 3, \
            "STAGE3_OVER_REQUEST regressed above 3 — see lever L11"

    def test_l8_recent_feedback_line_dropped_when_empty(self):
        """L8 (2026-04-29): when the profile has no liked/disliked feedback,
        build_feedback_summary returns "" and the {recent_feedback}
        placeholder leaves an empty line in the rendered prompt. select_tracks
        must strip the placeholder line entirely so we don't pay a token
        for whitespace nor distract the model with a blank line."""
        from core.src.suggestions import select_tracks
        from unittest.mock import patch
        import json as _json

        captured = {}
        def _fake_create(**kw):
            captured["messages"] = kw.get("messages")
            return {"choices": [{"message": {"content": _json.dumps(self._GOOD_RESULT)}}],
                    "usage": None}

        # Profile has empty feedback lists → build_feedback_summary returns "".
        profile = self._make_profile()
        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                select_tracks(["Good Band", "Other Band"], "Must: hooks.", 10, profile)

        user_msg = captured["messages"][1]["content"]
        # The "Recent user feedback" header is build_feedback_summary's
        # contribution; should not appear when feedback is empty.
        assert "Recent user feedback" not in user_msg
        # No double-blank-line collapse from the dropped placeholder
        # (heuristic: TASTE SUMMARY block flows into the next non-empty
        # section without an orphaned blank line carrying tokens).
        assert "\n\n\n" not in user_msg, \
            "double-blank-line found — {recent_feedback} placeholder not stripped cleanly"

    def test_approved_top_tracks_reach_llm_user_message(self):
        """End-to-end plumbing: when approved_top_tracks is supplied,
        the rendered known: lines must appear in the user message that
        is actually sent to the LLM. Guards against future refactors
        that silently drop the overlay parameter on the floor.
        """
        from core.src.suggestions import select_tracks
        import json
        from unittest.mock import patch

        captured = {}

        def _fake_create(**kw):
            captured["messages"] = kw.get("messages")
            return {"choices": [{"message": {"content": json.dumps(self._GOOD_RESULT)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

        overlay = {
            "good band": ["great song", "another hit"],
            "obscure act": ["only known release"],
        }
        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                select_tracks(
                    ["Good Band", "Obscure Act"], "Must: hooks.", 10,
                    self._make_profile(),
                    approved_top_tracks=overlay,
                )

        assert captured.get("messages"), "LLM was never called"
        user_msg = next(m["content"] for m in captured["messages"] if m["role"] == "user")
        # Both overlay entries must be rendered as known: lines.
        assert 'known: "great song", "another hit"' in user_msg
        assert 'known: "only known release"' in user_msg

    def test_missing_overlay_renders_no_examples_marker(self):
        """When approved_top_tracks is supplied but doesn't cover an
        artist, that artist must get the explicit
        ``(no track examples available — …)`` marker so the prompt's
        anti-confab clause can fire on it. Pre-fix, the artist would
        appear as a bare name and the model would freely invent titles.
        """
        from core.src.suggestions import select_tracks
        import json
        from unittest.mock import patch

        captured = {}

        def _fake_create(**kw):
            captured["messages"] = kw.get("messages")
            return {"choices": [{"message": {"content": json.dumps(self._GOOD_RESULT)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                select_tracks(
                    ["Covered Artist", "Uncovered Artist"], "Must: hooks.", 10,
                    self._make_profile(),
                    approved_top_tracks={"covered artist": ["one", "two"]},
                )

        user_msg = next(m["content"] for m in captured["messages"] if m["role"] == "user")
        assert 'known: "one", "two"' in user_msg
        assert "no track examples available" in user_msg


class TestSelectTracksQ1PoolShuffle:
    """Q1 (2026-05-23) — per-batch deterministic shuffle of the approved
    artist pool.

    Production post-mortem against the user's `japanese_theatrical`
    profile (run f334693d, 2026-05-22) showed Stage 3 picking the same
    ~6 anchor artists across all 6 batches when given a pool of 50.
    Classic positional-attention bias. Shuffling by `batch_num` breaks
    the bias while keeping runs reproducible.
    """

    _GOOD_RESULT = {
        "playlist": [
            {"artist": "x", "track": "y", "reason": "r",
             "energy": 0.5, "valence": 0.5, "genres": ["g"],
             "rationale": [{"type": "profile_match", "arg": "z"}]}
        ]
    }

    def _make_profile(self):
        return {
            "preferences": {"must_have": ["hooks"], "soft_preferences": [], "avoid": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
            "artists": {"confirmed": [], "rejected": []},
            "meta": {},
        }

    def _capture_user_message(self, approved_names, batch_num, env=None):
        """Invoke select_tracks and return the rendered user-role message."""
        import os
        import json as _json
        from unittest.mock import patch
        from core.src.suggestions import select_tracks

        captured = {}

        def _fake_create(**kw):
            captured["messages"] = kw.get("messages")
            return {"choices": [{"message": {"content": _json.dumps(self._GOOD_RESULT)}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                              "total_tokens": 15}}

        with patch.dict(os.environ, env or {}, clear=False):
            with patch("core.src.suggestions.chat_completions_create",
                       side_effect=_fake_create):
                with patch("core.src.suggestions.extract_chat_content",
                           side_effect=lambda r: r["choices"][0]["message"]["content"]):
                    select_tracks(approved_names, "summary", 5, self._make_profile(),
                                  batch_num=batch_num)

        return next(m["content"] for m in captured["messages"]
                    if m["role"] == "user")

    @staticmethod
    def _artist_order_in_block(user_msg, candidates):
        """Return the order in which `candidates` appear in user_msg."""
        positions = []
        for name in candidates:
            idx = user_msg.find(f"- {name}")
            positions.append((idx, name))
        # Keep only ones actually present, sort by position.
        return [n for idx, n in sorted(p for p in positions if p[0] >= 0)]

    def test_shuffle_changes_artist_order_across_batches(self):
        names = [f"Artist{i:02d}" for i in range(20)]
        msg_b1 = self._capture_user_message(names, batch_num=1)
        msg_b2 = self._capture_user_message(names, batch_num=2)
        order_b1 = self._artist_order_in_block(msg_b1, names)
        order_b2 = self._artist_order_in_block(msg_b2, names)
        assert order_b1 != names, "batch 1 should NOT match input order"
        assert order_b2 != names, "batch 2 should NOT match input order"
        assert order_b1 != order_b2, "different batches must yield different orders"

    def test_shuffle_is_deterministic_per_batch(self):
        names = [f"Artist{i:02d}" for i in range(20)]
        msg_a = self._capture_user_message(names, batch_num=3)
        msg_b = self._capture_user_message(names, batch_num=3)
        order_a = self._artist_order_in_block(msg_a, names)
        order_b = self._artist_order_in_block(msg_b, names)
        assert order_a == order_b, "same batch_num must yield identical order"

    def test_env_override_disables_shuffle(self):
        names = [f"Artist{i:02d}" for i in range(20)]
        msg = self._capture_user_message(
            names, batch_num=5,
            env={"SPOTYVIBE_DISABLE_POOL_SHUFFLE": "1"},
        )
        order = self._artist_order_in_block(msg, names)
        assert order == names, "shuffle disabled must preserve input order"

    def test_shuffle_does_not_drop_or_duplicate_artists(self):
        names = [f"Artist{i:02d}" for i in range(50)]
        msg = self._capture_user_message(names, batch_num=7)
        order = self._artist_order_in_block(msg, names)
        assert sorted(order) == sorted(names)
        assert len(order) == len(set(order))


class TestSelectTracksA6PoolStarvationRefusal:
    """A6 (2026-05-13) — pool-starvation refusal gate.

    Motivated by B-11 fingerprints: every model (gpt-4.1, gpt-5.4,
    gpt-5.4-mini) confabulated tracks when the approved pool was a
    single artist with no `known:` examples. The widened gate refuses
    early — without burning an LLM call — for both `len == 0` and
    `len == 1 AND no known: tracks`.
    """

    def _make_profile(self):
        return {
            "preferences": {"must_have": ["hooks"], "soft_preferences": [], "avoid": []},
            "history": {"suggested_artists": [], "suggested_tracks": []},
            "feedback": {"liked_tracks": [], "disliked_tracks": []},
            "artists": {"confirmed": [], "rejected": []},
            "meta": {},
        }

    def test_empty_pool_refuses_without_llm_call(self):
        from core.src.suggestions import select_tracks
        from unittest.mock import patch

        called = {"n": 0}

        def _fake_create(**_kw):
            called["n"] += 1
            return {"choices": [{"message": {"content": "{}"}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            result, meta = select_tracks([], "summary", 5, self._make_profile())

        assert called["n"] == 0, "A6 must refuse before any LLM call when pool is empty"
        assert result["playlist"] == []
        assert result["new_artists"] == []
        assert result["profile_updates"] == {"suggested_artists": [], "suggested_tracks": []}
        assert meta["refusal_reason"] == "empty_pool"
        assert meta["latency_s"] == 0.0
        assert meta["usage"] is None

    def test_single_artist_no_known_refuses_without_llm_call(self):
        from core.src.suggestions import select_tracks
        from unittest.mock import patch

        called = {"n": 0}

        def _fake_create(**_kw):
            called["n"] += 1
            return {"choices": [{"message": {"content": "{}"}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            # No overlay supplied → no known tracks → refusal.
            result, meta = select_tracks(["Brian Eno"], "summary", 5, self._make_profile())

        assert called["n"] == 0, "A6 must refuse before any LLM call (single, no known)"
        assert result["playlist"] == []
        assert meta["refusal_reason"] == "single_artist_no_known"

    def test_single_artist_with_overlay_empty_list_refuses(self):
        """Overlay supplied but artist's entry is empty list — still no known
        grounding, so the gate must fire."""
        from core.src.suggestions import select_tracks
        from unittest.mock import patch

        called = {"n": 0}

        def _fake_create(**_kw):
            called["n"] += 1
            return {"choices": [{"message": {"content": "{}"}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            result, meta = select_tracks(
                ["Brian Eno"], "summary", 5, self._make_profile(),
                approved_top_tracks={"brian eno": []},
            )

        assert called["n"] == 0
        assert meta["refusal_reason"] == "single_artist_no_known"
        assert result["playlist"] == []

    def test_single_artist_with_known_tracks_does_not_refuse(self):
        """Single artist BUT with `known:` examples → grounded enough; the
        gate must NOT fire and the LLM call must proceed."""
        from core.src.suggestions import select_tracks
        from unittest.mock import patch
        import json as _json

        called = {"n": 0}
        good_payload = _json.dumps({
            "playlist": [{"artist": "Brian Eno", "track": "An Ending (Ascent)"}],
            "new_artists": [],
            "profile_updates": {"suggested_artists": [], "suggested_tracks": []},
        })

        def _fake_create(**_kw):
            called["n"] += 1
            return {"choices": [{"message": {"content": good_payload}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                result, meta = select_tracks(
                    ["Brian Eno"], "summary", 5, self._make_profile(),
                    approved_top_tracks={"brian eno": ["An Ending (Ascent)"]},
                )

        assert called["n"] == 1, "single artist with known tracks must reach the LLM"
        assert "refusal_reason" not in meta
        assert result["playlist"], "expected non-empty playlist on grounded single-artist call"

    def test_two_artists_no_overlay_does_not_refuse(self):
        """Two artists with no overlay → still has cross-pool diversity to
        ground reasoning on; the gate must NOT fire."""
        from core.src.suggestions import select_tracks
        from unittest.mock import patch
        import json as _json

        called = {"n": 0}
        good_payload = _json.dumps({
            "playlist": [{"artist": "Foo", "track": "Bar"}],
            "new_artists": [],
            "profile_updates": {"suggested_artists": [], "suggested_tracks": []},
        })

        def _fake_create(**_kw):
            called["n"] += 1
            return {"choices": [{"message": {"content": good_payload}}], "usage": None}

        with patch("core.src.suggestions.chat_completions_create", side_effect=_fake_create):
            with patch("core.src.suggestions.extract_chat_content",
                       side_effect=lambda r: r["choices"][0]["message"]["content"]):
                _, meta = select_tracks(
                    ["Foo", "Baz"], "summary", 5, self._make_profile(),
                )

        assert called["n"] == 1
        assert "refusal_reason" not in meta


class TestFormatApprovedArtistsBlock:
    """Track-level grounding (2026-04-27 follow-up).

    The APPROVED_ARTISTS block is the load-bearing change that gives
    Stage 3 real `(artist, track)` literals to anchor against. Pin the
    rendering shape so a future prompt refactor cannot silently strip
    the `known:` lines and reintroduce hallucination.
    """

    def test_bare_names_when_no_overlay(self):
        from core.src.suggestions import _format_approved_artists_block
        out = _format_approved_artists_block(["Foo", "Bar"], None)
        assert out == "- Foo\n- Bar"

    def test_bare_names_when_overlay_empty(self):
        from core.src.suggestions import _format_approved_artists_block
        out = _format_approved_artists_block(["Foo", "Bar"], {})
        assert out == "- Foo\n- Bar"

    def test_known_block_rendered_when_overlay_has_tracks(self):
        from core.src.suggestions import _format_approved_artists_block
        overlay = {
            "tally hall": ["good day", "banana man"],
            "bear ghost": ["necromancin' dancin'"],
        }
        out = _format_approved_artists_block(
            ["Tally Hall", "Bear Ghost"], overlay
        )
        assert "- Tally Hall" in out
        assert '    known: "good day", "banana man"' in out
        assert "- Bear Ghost" in out
        assert "    known: \"necromancin' dancin'\"" in out

    def test_max_5_tracks_per_artist(self):
        from core.src.suggestions import _format_approved_artists_block
        overlay = {"foo": [f"track {i}" for i in range(10)]}
        out = _format_approved_artists_block(["Foo"], overlay)
        # Count quoted titles
        import re
        quoted = re.findall(r'"[^"]+"', out)
        assert len(quoted) == 5

    def test_artist_with_no_overlay_entry_marked_when_overlay_active(self):
        """When the overlay is in use but a specific artist has no entry,
        the prompt explicitly says no examples are available so the
        anti-confab clause kicks in for that artist."""
        from core.src.suggestions import _format_approved_artists_block
        overlay = {"tally hall": ["good day"]}
        out = _format_approved_artists_block(
            ["Tally Hall", "Niflhel"], overlay
        )
        assert "- Niflhel" in out
        assert "no track examples available" in out

    def test_lookup_is_case_insensitive(self):
        """Overlay keys are lowercase; APPROVED_ARTISTS comes through
        with whatever casing Stage 1 produced. Lookup must match either way."""
        from core.src.suggestions import _format_approved_artists_block
        overlay = {"foo": ["A", "B"]}
        out = _format_approved_artists_block(["Foo"], overlay)
        assert "- Foo" in out
        assert '    known: "A", "B"' in out

    def test_empty_track_strings_filtered(self):
        from core.src.suggestions import _format_approved_artists_block
        overlay = {"foo": ["", "  ", "real"]}
        out = _format_approved_artists_block(["Foo"], overlay)
        assert '    known: "real"' in out
