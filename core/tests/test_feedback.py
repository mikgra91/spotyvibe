"""Tests for core/feedback.py — like/dislike track recording."""

from contextlib import contextmanager
from unittest.mock import patch
from core.src.feedback import like_track, dislike_track


def _mock_transaction(profile_data):
    """Create a mock profile_transaction that captures the saved profile."""
    saved = {}

    @contextmanager
    def _transaction():
        def _load():
            return profile_data

        def _save(profile):
            saved["data"] = profile

        yield _load, _save

    return _transaction, saved


class TestLikeTrack:
    def test_like_with_track_and_reason(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"confirmed": []},
            "feedback": {"liked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            like_track("Artist A", track="Song 1", reason="great melody")

        assert len(saved["data"]["feedback"]["liked_tracks"]) == 1
        assert saved["data"]["feedback"]["liked_tracks"][0] == {
            "artist": "Artist A",
            "track": "Song 1",
            "reason": "great melody",
        }
        assert "Artist A" in saved["data"]["artists"]["confirmed"]

    def test_like_artist_only(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"confirmed": ["Existing"]},
            "feedback": {"liked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            like_track("New Artist")

        # No track-level entry added
        assert len(saved["data"]["feedback"]["liked_tracks"]) == 0
        assert "New Artist" in saved["data"]["artists"]["confirmed"]
        # Existing artist still present
        assert "Existing" in saved["data"]["artists"]["confirmed"]

    def test_like_does_not_duplicate_confirmed_artist(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"confirmed": ["Artist A"]},
            "feedback": {"liked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            like_track("Artist A", track="Song 2")

        assert saved["data"]["artists"]["confirmed"].count("Artist A") == 1


class TestDislikeTrack:
    def test_dislike_specific_track(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            dislike_track("Artist B", track="Bad Song", reason="too slow")

        assert len(saved["data"]["feedback"]["disliked_tracks"]) == 1
        assert saved["data"]["feedback"]["disliked_tracks"][0] == {
            "artist": "Artist B",
            "track": "Bad Song",
            "reason": "too slow",
        }
        # Track-level dislike should NOT reject the whole artist
        assert len(saved["data"]["artists"]["rejected"]) == 0

    def test_dislike_artist_level(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            dislike_track("Bad Artist", reason="too electronic")

        assert len(saved["data"]["artists"]["rejected"]) == 1
        assert saved["data"]["artists"]["rejected"][0] == {
            "name": "Bad Artist",
            "reason": "too electronic",
        }

    def test_dislike_default_reason(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            dislike_track("X", track="Y")

        assert saved["data"]["feedback"]["disliked_tracks"][0]["reason"] == "user feedback"

    def test_dislike_does_not_duplicate_rejected_artist(self):
        mock_tx, saved = _mock_transaction({
            "artists": {"rejected": [{"name": "Bad", "reason": "old"}]},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", mock_tx):
            dislike_track("Bad", reason="still bad")

        # Should not add a second entry
        assert len(saved["data"]["artists"]["rejected"]) == 1


class TestDislikeAutoEscalation:
    """F4 (2026-05-01): three distinct track-dislikes for the same artist
    auto-promotes that artist to ``artists.rejected`` so the next playlist
    run treats them as a hard exclusion. Production profile had 9 disliked
    DREAMS COME TRUE tracks but the artist was still eligible for
    re-suggestion."""

    def _stateful_tx(self, profile_data):
        """Mock transaction whose load_fn returns the SAME dict each
        call so back-to-back dislike_track() calls can accumulate state."""
        from contextlib import contextmanager

        @contextmanager
        def _transaction():
            yield (lambda: profile_data), (lambda p: None)

        return _transaction, profile_data

    def test_two_dislikes_do_not_auto_reject(self):
        tx, profile = self._stateful_tx({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", tx):
            dislike_track("Spammy Band", track="One", reason="too loud")
            dislike_track("Spammy Band", track="Two", reason="80s")

        assert len(profile["feedback"]["disliked_tracks"]) == 2
        assert profile["artists"]["rejected"] == []

    def test_three_distinct_dislikes_auto_reject(self):
        tx, profile = self._stateful_tx({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", tx):
            dislike_track("Spammy Band", track="One", reason="too loud")
            dislike_track("Spammy Band", track="Two", reason="80s")
            dislike_track("Spammy Band", track="Three", reason="not Japanese")

        assert len(profile["artists"]["rejected"]) == 1
        entry = profile["artists"]["rejected"][0]
        assert entry["name"] == "Spammy Band"
        assert entry.get("auto") is True
        # Reason carries the dislike-reason context for downstream
        # train_profile (F5) consumption.
        assert "auto-rejected after 3 disliked tracks" in entry["reason"]
        assert "too loud" in entry["reason"]

    def test_repeat_track_does_not_double_count(self):
        tx, profile = self._stateful_tx({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", tx):
            dislike_track("Spammy Band", track="One", reason="too loud")
            dislike_track("Spammy Band", track="One", reason="too loud")
            dislike_track("Spammy Band", track="Two", reason="80s")

        # Only TWO distinct tracks — must not auto-reject yet.
        assert profile["artists"]["rejected"] == []

    def test_case_insensitive_artist_match(self):
        tx, profile = self._stateful_tx({
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", tx):
            dislike_track("DREAMS COME TRUE", track="One")
            dislike_track("Dreams Come True", track="Two")
            dislike_track("dreams come true", track="Three")

        assert len(profile["artists"]["rejected"]) == 1
        assert profile["artists"]["rejected"][0]["name"] in {
            "DREAMS COME TRUE", "Dreams Come True", "dreams come true",
        }

    def test_already_rejected_not_duplicated(self):
        tx, profile = self._stateful_tx({
            "artists": {"rejected": [{"name": "Spammy Band", "reason": "manual"}]},
            "feedback": {"disliked_tracks": []},
        })
        with patch("core.src.feedback.profile_transaction", tx):
            dislike_track("Spammy Band", track="One")
            dislike_track("Spammy Band", track="Two")
            dislike_track("Spammy Band", track="Three")

        # Should still have only ONE rejection entry (the manual one).
        assert len(profile["artists"]["rejected"]) == 1
        assert profile["artists"]["rejected"][0]["reason"] == "manual"
