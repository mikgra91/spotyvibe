"""Tests for core/src/spotify_metadata.py — all external HTTP calls are mocked."""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from core.src.spotify_metadata import (
    SpotifyMetadataError,
    analyze_metadata,
    get_client_credentials_token,
    normalize_compare_text,
    score_artist_candidate,
    score_track_candidate,
    strip_version_suffixes,
    _token_cache,
)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Save and restore _token_cache around every test to prevent leaks."""
    saved = dict(_token_cache)
    yield
    _token_cache.update(saved)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(name="Bohemian Rhapsody", artist_name="Queen", artist_id="a1", track_id="t1", popularity=80):
    return {
        "id": track_id,
        "name": name,
        "artists": [{"id": artist_id, "name": artist_name}],
        "album": {"name": "A Night at the Opera", "release_date": "1975-10-31"},
        "duration_ms": 354000,
        "popularity": popularity,
        "preview_url": None,
        "external_urls": {"spotify": "https://open.spotify.com/track/t1"},
    }


def _make_artist(name="Queen", artist_id="a1", popularity=90):
    return {
        "id": artist_id,
        "name": name,
        "genres": ["rock", "classic rock"],
        "popularity": popularity,
        "followers": {"total": 1000000},
        "external_urls": {"spotify": "https://open.spotify.com/artist/a1"},
    }




# ---------------------------------------------------------------------------
# normalize_compare_text
# ---------------------------------------------------------------------------

class TestNormalizeCompareText:
    def test_lowercases(self):
        assert normalize_compare_text("HELLO") == "hello"

    def test_trims_whitespace(self):
        assert normalize_compare_text("  hello  ") == "hello"

    def test_collapses_internal_spaces(self):
        assert normalize_compare_text("hello   world") == "hello world"

    def test_combined(self):
        assert normalize_compare_text("  The   Beatles  ") == "the beatles"

    def test_empty_string(self):
        assert normalize_compare_text("") == ""


# ---------------------------------------------------------------------------
# strip_version_suffixes
# ---------------------------------------------------------------------------

class TestStripVersionSuffixes:
    def test_strips_remastered(self):
        assert strip_version_suffixes("Song Title (Remastered)") == "Song Title"

    def test_strips_remastered_with_year(self):
        assert strip_version_suffixes("Come Together (2009 Remaster)") == "Come Together"

    def test_strips_live(self):
        assert strip_version_suffixes("Let It Be (Live)") == "Let It Be"

    def test_strips_deluxe_edition(self):
        assert strip_version_suffixes("Abbey Road (Deluxe Edition)") == "Abbey Road"

    def test_strips_square_brackets(self):
        result = strip_version_suffixes("Something [2024 Mix]")
        assert "2024" not in result.lower()

    def test_case_insensitive(self):
        result = strip_version_suffixes("Hey Jude (REMASTERED)")
        assert "remastered" not in result.lower()

    def test_no_suffix_unchanged(self):
        assert strip_version_suffixes("Bohemian Rhapsody") == "Bohemian Rhapsody"


# ---------------------------------------------------------------------------
# score_track_candidate
# ---------------------------------------------------------------------------

class TestScoreTrackCandidate:
    def test_exact_match_both_gives_high_score(self):
        candidate = _make_track(name="Bohemian Rhapsody", artist_name="Queen", popularity=80)
        score = score_track_candidate(candidate, "Queen", "Bohemian Rhapsody")
        # +0.6 track, +0.3 artist (popularity no longer a factor)
        assert score == pytest.approx(0.9, abs=1e-9)

    def test_exact_track_no_artist_gives_0_6(self):
        candidate = _make_track(name="Bohemian Rhapsody", artist_name="Queen", popularity=0)
        score = score_track_candidate(candidate, "", "Bohemian Rhapsody")
        assert abs(score - 0.6) < 0.01

    def test_partial_match_gives_lower_score(self):
        candidate = _make_track(name="Bohemian Rhapsody (Remastered)", artist_name="Queen", popularity=0)
        score = score_track_candidate(candidate, "Queen", "Bohemian Rhapsody")
        # Strip suffixes should still find exact match
        assert score == pytest.approx(0.9, abs=1e-9)

    def test_wrong_track_name_no_track_score(self):
        candidate = _make_track(name="We Will Rock You", artist_name="Queen", popularity=0)
        score = score_track_candidate(candidate, "Queen", "Bohemian Rhapsody")
        # Only artist match (+0.3)
        assert score == pytest.approx(0.3, abs=1e-9)

    def test_no_match_gives_zero(self):
        candidate = _make_track(name="Other Song", artist_name="Other Artist", popularity=500)
        score = score_track_candidate(candidate, "Queen", "Bohemian Rhapsody")
        assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# score_artist_candidate
# ---------------------------------------------------------------------------

class TestScoreArtistCandidate:
    def test_exact_match_gives_1(self):
        candidate = _make_artist(name="Queen", popularity=90)
        score = score_artist_candidate(candidate, "Queen")
        assert score == pytest.approx(1.0)

    def test_case_insensitive_exact_match(self):
        candidate = _make_artist(name="queen", popularity=0)
        score = score_artist_candidate(candidate, "Queen")
        assert score == pytest.approx(1.0)

    def test_no_match_gives_zero(self):
        candidate = _make_artist(name="The Beatles", popularity=100)
        score = score_artist_candidate(candidate, "Queen")
        assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# analyze_metadata — track + artist (full success path)
# ---------------------------------------------------------------------------

class TestAnalyzeMetadataTrackAndArtist:
    @patch("core.src.spotify_metadata.get_artist_metadata")
    @patch("core.src.spotify_metadata.get_track_metadata")
    @patch("core.src.spotify_metadata.search_track_candidates")
    @patch("core.src.spotify_metadata.get_client_credentials_token")
    def test_returns_full_result(
        self,
        mock_token,
        mock_search_tracks,
        mock_track_meta,
        mock_artist_meta,
    ):
        mock_token.return_value = "fake-token"
        mock_search_tracks.return_value = [_make_track()]
        mock_track_meta.return_value = {
            "id": "t1", "name": "Bohemian Rhapsody", "artists": ["Queen"],
            "album": "A Night at the Opera", "release_date": "1975-10-31",
            "duration_ms": 354000,
            "preview_url": None, "external_urls": {},
        }
        mock_artist_meta.return_value = {
            "id": "a1", "name": "Queen", "genres": ["rock"],
            "external_urls": {},
        }

        result = analyze_metadata(artist="Queen", track="Bohemian Rhapsody", market="US")

        assert result["query"] == {"artist": "Queen", "track": "Bohemian Rhapsody", "market": "US"}
        assert result["match"]["type"] == "track"
        assert result["match"]["provider"] == "spotify"
        assert result["match"]["spotify_track_id"] == "t1"
        assert result["match"]["spotify_artist_id"] == "a1"
        assert result["track"] is not None
        assert result["artist"] is not None
        assert result["match"]["processed_at"].endswith("Z")
        assert "low_confidence_match" not in result["warnings"]

    @patch("core.src.spotify_metadata.get_artist_metadata")
    @patch("core.src.spotify_metadata.get_track_metadata")
    @patch("core.src.spotify_metadata.search_track_candidates")
    @patch("core.src.spotify_metadata.get_client_credentials_token")
    def test_no_candidates_raises(
        self,
        mock_token,
        mock_search_tracks,
        mock_track_meta,
        mock_artist_meta,
    ):
        mock_token.return_value = "fake-token"
        mock_search_tracks.return_value = []

        with pytest.raises(SpotifyMetadataError, match="No match found"):
            analyze_metadata(artist="Queen", track="Nonexistent Track")


# ---------------------------------------------------------------------------
# analyze_metadata — artist-only
# ---------------------------------------------------------------------------

class TestAnalyzeMetadataArtistOnly:
    @patch("core.src.spotify_metadata.get_artist_metadata")
    @patch("core.src.spotify_metadata.search_artist_candidates")
    @patch("core.src.spotify_metadata.get_client_credentials_token")
    def test_returns_artist_result(self, mock_token, mock_search, mock_artist_meta):
        mock_token.return_value = "fake-token"
        mock_search.return_value = [_make_artist(name="Queen", popularity=90)]
        mock_artist_meta.return_value = {
            "id": "a1", "name": "Queen", "genres": ["rock"],
            "external_urls": {},
        }

        result = analyze_metadata(artist="Queen", track=None)

        assert result["match"]["type"] == "artist"
        assert result["match"]["spotify_track_id"] is None
        assert result["track"] is None
        assert result["artist"]["name"] == "Queen"

    @patch("core.src.spotify_metadata.search_artist_candidates")
    @patch("core.src.spotify_metadata.get_client_credentials_token")
    def test_no_artist_candidates_raises(self, mock_token, mock_search):
        mock_token.return_value = "fake-token"
        mock_search.return_value = []

        with pytest.raises(SpotifyMetadataError, match="No match found"):
            analyze_metadata(artist="Unknown Artist XYZ", track=None)

    def test_no_artist_and_no_track_raises(self):
        with pytest.raises(SpotifyMetadataError):
            analyze_metadata(artist=None, track=None)


# ---------------------------------------------------------------------------
# Low confidence warning
# ---------------------------------------------------------------------------

class TestLowConfidenceWarning:
    @patch("core.src.spotify_metadata.get_artist_metadata")
    @patch("core.src.spotify_metadata.get_track_metadata")
    @patch("core.src.spotify_metadata.search_track_candidates")
    @patch("core.src.spotify_metadata.get_client_credentials_token")
    def test_low_score_adds_warning(
        self,
        mock_token,
        mock_search_tracks,
        mock_track_meta,
        mock_artist_meta,
    ):
        mock_token.return_value = "fake-token"
        # Return a candidate whose name doesn't match the query at all
        low_match = _make_track(name="Completely Different Song", artist_name="Other Artist", popularity=0)
        mock_search_tracks.return_value = [low_match]
        mock_track_meta.return_value = {
            "id": "t1", "name": "Completely Different Song", "artists": ["Other Artist"],
            "album": "Album", "release_date": "2000-01-01",
            "duration_ms": 200000,
            "preview_url": None, "external_urls": {},
        }
        mock_artist_meta.return_value = {
            "id": "a2", "name": "Other Artist", "genres": [],
            "external_urls": {},
        }

        result = analyze_metadata(artist="Queen", track="Bohemian Rhapsody")

        assert "low_confidence_match" in result["warnings"]



# ---------------------------------------------------------------------------
# Missing credentials raises SpotifyMetadataError
# ---------------------------------------------------------------------------

class TestMissingCredentials:
    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "", "SPOTIPY_CLIENT_SECRET": ""})
    def test_missing_credentials_raises(self):
        # Reset the token cache to force a refresh attempt
        _token_cache["token"] = None
        _token_cache["expires_at"] = 0.0

        with pytest.raises(SpotifyMetadataError, match="credentials not configured"):
            get_client_credentials_token()

    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "id", "SPOTIPY_CLIENT_SECRET": ""})
    def test_missing_secret_raises(self):
        _token_cache["token"] = None
        _token_cache["expires_at"] = 0.0

        with pytest.raises(SpotifyMetadataError, match="credentials not configured"):
            get_client_credentials_token()


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

class TestTokenCaching:
    def test_cached_token_is_reused(self):
        _token_cache["token"] = "cached-token"
        _token_cache["expires_at"] = time.time() + 3600

        with patch("core.src.spotify_metadata.urllib.request.urlopen") as mock_urlopen:
            token = get_client_credentials_token()
            assert token == "cached-token"
            mock_urlopen.assert_not_called()

