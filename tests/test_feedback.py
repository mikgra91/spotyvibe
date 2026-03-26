from unittest.mock import patch
from core.feedback import like_track, dislike_track


class TestLikeTrack:
    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_like_with_track_and_reason(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"confirmed": []},
            "feedback": {"liked_tracks": []},
        }
        like_track("Artist A", track="Song 1", reason="great melody")

        saved = mock_save.call_args[0][0]
        assert len(saved["feedback"]["liked_tracks"]) == 1
        assert saved["feedback"]["liked_tracks"][0] == {
            "artist": "Artist A",
            "track": "Song 1",
            "reason": "great melody",
        }
        assert "Artist A" in saved["artists"]["confirmed"]

    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_like_artist_only(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"confirmed": ["Existing"]},
            "feedback": {"liked_tracks": []},
        }
        like_track("New Artist")

        saved = mock_save.call_args[0][0]
        # No track-level entry added
        assert len(saved["feedback"]["liked_tracks"]) == 0
        assert "New Artist" in saved["artists"]["confirmed"]
        # Existing artist still present
        assert "Existing" in saved["artists"]["confirmed"]

    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_like_does_not_duplicate_confirmed_artist(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"confirmed": ["Artist A"]},
            "feedback": {"liked_tracks": []},
        }
        like_track("Artist A", track="Song 2")

        saved = mock_save.call_args[0][0]
        assert saved["artists"]["confirmed"].count("Artist A") == 1


class TestDislikeTrack:
    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_dislike_specific_track(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        }
        dislike_track("Artist B", track="Bad Song", reason="too slow")

        saved = mock_save.call_args[0][0]
        assert len(saved["feedback"]["disliked_tracks"]) == 1
        assert saved["feedback"]["disliked_tracks"][0] == {
            "artist": "Artist B",
            "track": "Bad Song",
            "reason": "too slow",
        }
        # Track-level dislike should NOT reject the whole artist
        assert len(saved["artists"]["rejected"]) == 0

    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_dislike_artist_level(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        }
        dislike_track("Bad Artist", reason="too electronic")

        saved = mock_save.call_args[0][0]
        assert len(saved["artists"]["rejected"]) == 1
        assert saved["artists"]["rejected"][0] == {
            "name": "Bad Artist",
            "reason": "too electronic",
        }

    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_dislike_default_reason(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"rejected": []},
            "feedback": {"disliked_tracks": []},
        }
        dislike_track("X", track="Y")

        saved = mock_save.call_args[0][0]
        assert saved["feedback"]["disliked_tracks"][0]["reason"] == "user feedback"

    @patch("core.feedback.save_profile")
    @patch("core.feedback.load_profile")
    def test_dislike_does_not_duplicate_rejected_artist(self, mock_load, mock_save):
        mock_load.return_value = {
            "artists": {"rejected": [{"name": "Bad", "reason": "old"}]},
            "feedback": {"disliked_tracks": []},
        }
        dislike_track("Bad", reason="still bad")

        saved = mock_save.call_args[0][0]
        # Should not add a second entry
        assert len(saved["artists"]["rejected"]) == 1

