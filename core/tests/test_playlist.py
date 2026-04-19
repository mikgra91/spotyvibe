"""Tests for core/playlist.py — Spotify OAuth, search, and playlist management."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from core.src.playlist import (
    find_existing_playlist,
    get_existing_track_uris,
    get_user_playlists,
    get_playlist_tracks,
    remove_from_playlist,
    search_tracks,
    add_to_playlist,
    get_spotify_auth_status,
    get_spotify_auth_url,
    disconnect_spotify,
    handle_spotify_callback,
    filter_emerging_artists,
    PLAYLIST_NAME,
    REDIRECT_URI,
)


class TestGetSpotifyAuthStatus:
    def setup_method(self):
        """Clear the auth status cache before each test."""
        from core.src.playlist import _auth_status_cache
        _auth_status_cache["status"] = None
        _auth_status_cache["expires"] = 0.0

    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "", "SPOTIPY_CLIENT_SECRET": ""})
    def test_not_configured_when_no_creds(self):
        assert get_spotify_auth_status() == "not_configured"

    @patch("core.src.playlist.get_spotify_oauth")
    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "id", "SPOTIPY_CLIENT_SECRET": "secret"})
    def test_not_authenticated_when_no_token(self, mock_oauth):
        mock_oauth.return_value.validate_token.return_value = None
        assert get_spotify_auth_status() == "not_authenticated"

    @patch("core.src.playlist.spotipy.Spotify")
    @patch("core.src.playlist.get_spotify_oauth")
    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "id", "SPOTIPY_CLIENT_SECRET": "secret"})
    def test_authenticated_when_valid_token(self, mock_oauth, mock_sp_cls):
        mock_oauth.return_value.validate_token.return_value = {"access_token": "tok"}
        mock_sp_cls.return_value.current_user.return_value = {"id": "user1"}
        assert get_spotify_auth_status() == "authenticated"
        # Verify auth_manager is used (enables auto-refresh) rather than bare auth=
        mock_sp_cls.assert_called_once_with(auth_manager=mock_oauth.return_value)

    @patch("core.src.playlist.spotipy.Spotify")
    @patch("core.src.playlist.get_spotify_oauth")
    @patch.dict(os.environ, {"SPOTIPY_CLIENT_ID": "id", "SPOTIPY_CLIENT_SECRET": "secret"})
    def test_not_authenticated_when_token_invalid(self, mock_oauth, mock_sp_cls):
        mock_oauth.return_value.validate_token.return_value = {"access_token": "expired"}
        mock_sp_cls.return_value.current_user.side_effect = Exception("token expired")
        assert get_spotify_auth_status() == "not_authenticated"


class TestDisconnectSpotify:
    def test_removes_cache_file(self, tmp_path):
        cache = tmp_path / ".spotify-cache"
        cache.write_text('{"token": "data"}')
        with patch("core.src.playlist.CACHE_FILE", cache):
            result = disconnect_spotify()
        assert result is True
        assert not cache.exists()

    def test_returns_true_when_no_cache(self, tmp_path):
        cache = tmp_path / ".spotify-cache"
        with patch("core.src.playlist.CACHE_FILE", cache):
            result = disconnect_spotify()
        assert result is True


class TestGetSpotifyAuthUrl:
    @patch("core.src.playlist.get_spotify_oauth")
    def test_returns_url(self, mock_oauth):
        mock_oauth.return_value.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?..."
        url = get_spotify_auth_url()
        assert url.startswith("https://")


class TestHandleSpotifyCallback:
    @patch("core.src.playlist.get_spotify_oauth")
    def test_success(self, mock_oauth):
        mock_oauth.return_value.get_access_token.return_value = "tok"
        assert handle_spotify_callback("auth_code") is True

    @patch("core.src.playlist.get_spotify_oauth")
    def test_failure(self, mock_oauth):
        mock_oauth.return_value.get_access_token.side_effect = Exception("fail")
        assert handle_spotify_callback("bad_code") is False


class TestFindExistingPlaylist:
    def test_finds_matching_playlist(self):
        sp = MagicMock()
        sp.current_user_playlists.return_value = {
            "items": [
                {"name": "Other Playlist"},
                {"name": PLAYLIST_NAME, "id": "pl123"},
            ],
            "next": None,
        }
        result = find_existing_playlist(sp)
        assert result is not None
        assert result["id"] == "pl123"

    def test_returns_none_when_not_found(self):
        sp = MagicMock()
        sp.current_user_playlists.return_value = {
            "items": [{"name": "Random"}],
            "next": None,
        }
        assert find_existing_playlist(sp) is None

    def test_paginates(self):
        sp = MagicMock()
        sp.current_user_playlists.side_effect = [
            {"items": [{"name": "A"}], "next": "url"},
            {"items": [{"name": PLAYLIST_NAME, "id": "found"}], "next": None},
        ]
        result = find_existing_playlist(sp)
        assert result is not None
        assert result["id"] == "found"


class TestGetExistingTrackUris:
    def test_collects_all_uris(self):
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [
                {"item": {"uri": "spotify:track:1"}},
                {"item": {"uri": "spotify:track:2"}},
            ],
            "next": None,
        }
        uris = get_existing_track_uris(sp, "pl123")
        assert uris == {"spotify:track:1", "spotify:track:2"}

    def test_paginates(self):
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [{"item": {"uri": "spotify:track:1"}}],
            "next": "more",
        }
        sp.next.return_value = {
            "items": [{"item": {"uri": "spotify:track:2"}}],
            "next": None,
        }
        uris = get_existing_track_uris(sp, "pl123")
        assert len(uris) == 2

    def test_skips_entries_without_uri(self):
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [
                {"item": {"uri": "spotify:track:1"}},
                {"item": None},
                {"item": {"uri": None}},
            ],
            "next": None,
        }
        uris = get_existing_track_uris(sp, "pl123")
        assert uris == {"spotify:track:1"}

    def test_fallback_to_legacy_track_key(self):
        """Older Spotify API responses used 'track' instead of 'item'."""
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [{"track": {"uri": "spotify:track:legacy"}}],
            "next": None,
        }
        uris = get_existing_track_uris(sp, "pl123")
        assert uris == {"spotify:track:legacy"}


class TestRemoveFromPlaylist:
    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_removes_track_successfully(self, mock_client_fn, mock_find, mock_uris):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = {"id": "pl123"}
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:abc"}]}
        }
        mock_uris.return_value = {"spotify:track:abc"}

        result = remove_from_playlist("artist", "song")
        assert result["removed"] is True
        sp.playlist_remove_all_occurrences_of_items.assert_called_once()

    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_returns_false_when_no_playlist(self, mock_client_fn, mock_find):
        mock_client_fn.return_value = MagicMock()
        mock_find.return_value = None
        result = remove_from_playlist("artist", "song")
        assert result["removed"] is False
        assert "not found" in str(result["reason"]).lower()

    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_returns_false_when_track_not_on_spotify(self, mock_client_fn, mock_find):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = {"id": "pl123"}
        sp.search.return_value = {"tracks": {"items": []}}
        result = remove_from_playlist("artist", "song")
        assert result["removed"] is False

    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_returns_false_when_track_not_in_playlist(self, mock_client_fn, mock_find, mock_uris):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = {"id": "pl123"}
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:xyz"}]}
        }
        mock_uris.return_value = {"spotify:track:other"}
        result = remove_from_playlist("artist", "song")
        assert result["removed"] is False
        assert "not in playlist" in str(result["reason"]).lower()

    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_uses_explicit_playlist_id_and_track_id(self, mock_client_fn, mock_find, mock_uris):
        """Explicit playlist_id + track_id skip the name lookup and search."""
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_uris.return_value = {"spotify:track:abc"}

        result = remove_from_playlist(
            "artist", "song", playlist_id="custom_pl", track_id="abc"
        )
        assert result["removed"] is True
        mock_find.assert_not_called()
        sp.search.assert_not_called()
        sp.playlist_remove_all_occurrences_of_items.assert_called_once_with(
            "custom_pl", ["spotify:track:abc"]
        )

    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_explicit_playlist_id_with_track_id_not_in_playlist(self, mock_client_fn, mock_find, mock_uris):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_uris.return_value = {"spotify:track:other"}

        result = remove_from_playlist(
            "artist", "song", playlist_id="custom_pl", track_id="abc"
        )
        assert result["removed"] is False
        assert "not in playlist" in str(result["reason"]).lower()
        mock_find.assert_not_called()


class TestSearchTracks:
    def _mock_oauth_and_spotify(self, sp_mock):
        """Set up mocks for the pre-fetched-token search_tracks flow."""
        oauth = MagicMock()
        oauth.cache_handler.get_cached_token.return_value = {"access_token": "tok"}
        oauth.validate_token.return_value = {"access_token": "tok"}
        return patch("core.src.playlist.get_spotify_oauth", return_value=oauth), \
               patch("core.src.playlist.spotipy.Spotify", return_value=sp_mock)

    def test_finds_tracks(self):
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {
                "items": [{
                    "uri": "spotify:track:1",
                    "album": {"images": [{"url": "big"}, {"url": "small"}]},
                }]
            }
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        with p_oauth, p_sp:
            tracks = [{"artist": "a", "track": "b"}]
            found, not_found = search_tracks(tracks)
        assert len(found) == 1
        assert found[0]["uri"] == "spotify:track:1"
        assert found[0]["cover_url"] == "small"
        assert not_found == []

    def test_reports_not_found(self):
        sp = MagicMock()
        sp.search.return_value = {"tracks": {"items": []}}
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        with p_oauth, p_sp:
            tracks = [{"artist": "unknown", "track": "song"}]
            found, not_found = search_tracks(tracks)
        assert found == []
        assert len(not_found) == 1

    def test_deduplicates_input(self):
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        with p_oauth, p_sp:
            tracks = [
                {"artist": "a", "track": "b"},
                {"artist": "a", "track": "b"},  # duplicate
            ]
            found, not_found = search_tracks(tracks)
        # Only one search should be performed
        assert sp.search.call_count == 1

    def test_calls_progress_callback(self):
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        with p_oauth, p_sp:
            progress_calls = []
            search_tracks(
                [{"artist": "a", "track": "b"}],
                on_progress=lambda done, total: progress_calls.append((done, total)),
            )
        assert len(progress_calls) == 1
        assert progress_calls[0] == (1, 1)


class TestAddToPlaylist:
    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_adds_to_existing_playlist(self, mock_client_fn, mock_find, mock_uris):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = {
            "id": "pl123",
            "name": PLAYLIST_NAME,
            "external_urls": {"spotify": "https://open.spotify.com/playlist/pl123"},
        }
        mock_uris.return_value = set()

        tracks = [{"artist": "a", "track": "b", "uri": "spotify:track:1"}]
        result = add_to_playlist(tracks)
        assert result["added"] == 1
        assert "url" in result
        sp.playlist_add_items.assert_called_once()

    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_creates_new_playlist(self, mock_client_fn, mock_find):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = None
        sp.current_user_playlist_create.return_value = {
            "id": "new_pl",
            "external_urls": {"spotify": "https://open.spotify.com/playlist/new_pl"},
        }
        tracks = [{"artist": "a", "track": "b", "uri": "spotify:track:1"}]
        result = add_to_playlist(tracks)
        assert result["added"] == 1
        sp.current_user_playlist_create.assert_called_once_with(PLAYLIST_NAME, public=False)

    @patch("core.src.playlist.get_existing_track_uris")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_skips_already_in_playlist(self, mock_client_fn, mock_find, mock_uris):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = {
            "id": "pl123",
            "name": PLAYLIST_NAME,
            "external_urls": {"spotify": "https://open.spotify.com/playlist/pl123"},
        }
        mock_uris.return_value = {"spotify:track:1"}

        tracks = [{"artist": "a", "track": "b", "uri": "spotify:track:1"}]
        result = add_to_playlist(tracks)
        assert result["added"] == 0
        sp.playlist_add_items.assert_not_called()

    @patch("core.src.playlist.disconnect_spotify")
    @patch("core.src.playlist.find_existing_playlist")
    @patch("core.src.playlist.get_spotify_client")
    def test_handles_403_forbidden(self, mock_client_fn, mock_find, mock_disconnect):
        from spotipy.exceptions import SpotifyException
        sp = MagicMock()
        mock_client_fn.return_value = sp
        mock_find.return_value = None
        sp.current_user_playlist_create.side_effect = SpotifyException(
            http_status=403, code=-1, msg="Forbidden"
        )
        with pytest.raises(RuntimeError, match="403"):
            add_to_playlist([{"artist": "a", "track": "b", "uri": "spotify:track:1"}])
        mock_disconnect.assert_called_once()


class TestRedirectUri:
    def test_redirect_uri(self):
        assert REDIRECT_URI == "http://127.0.0.1:5000/callback"


class TestGetUserPlaylists:
    """get_user_playlists must read track count from the 'items' or 'tracks' summary."""

    @patch("core.src.playlist.get_spotify_client")
    def test_reads_count_from_items_field(self, mock_client_fn):
        """Feb 2026: Spotify moved the summary from 'tracks' to 'items'."""
        sp = MagicMock()
        mock_client_fn.return_value = sp
        sp.current_user_playlists.return_value = {
            "items": [
                {"id": "pl1", "name": "My List", "tracks": None,
                 "items": {"href": "...", "total": 42}},
            ],
            "next": None,
        }
        result = get_user_playlists()
        assert result == [{"id": "pl1", "name": "My List", "track_count": 42}]

    @patch("core.src.playlist.get_spotify_client")
    def test_falls_back_to_tracks_field(self, mock_client_fn):
        """Pre-Feb 2026 responses use 'tracks' for the summary."""
        sp = MagicMock()
        mock_client_fn.return_value = sp
        sp.current_user_playlists.return_value = {
            "items": [
                {"id": "pl1", "name": "Old List",
                 "tracks": {"href": "...", "total": 10}},
            ],
            "next": None,
        }
        result = get_user_playlists()
        assert result == [{"id": "pl1", "name": "Old List", "track_count": 10}]

    @patch("core.src.playlist.get_spotify_client")
    def test_handles_both_null(self, mock_client_fn):
        """When both 'tracks' and 'items' are null, track_count defaults to 0."""
        sp = MagicMock()
        mock_client_fn.return_value = sp
        sp.current_user_playlists.return_value = {
            "items": [
                {"id": "pl1", "name": "Empty", "tracks": None},
            ],
            "next": None,
        }
        result = get_user_playlists()
        assert result == [{"id": "pl1", "name": "Empty", "track_count": 0}]

    def test_redirect_uri_used_in_oauth(self):
        """get_spotify_oauth() must use the module-level REDIRECT_URI."""
        with patch.dict(os.environ, {
            "SPOTIPY_CLIENT_ID": "test_id",
            "SPOTIPY_CLIENT_SECRET": "test_secret",
        }):
            from core.src.playlist import get_spotify_oauth
            oauth = get_spotify_oauth()
            assert oauth.redirect_uri == REDIRECT_URI


class TestGetPlaylistTracks:
    """Tests for get_playlist_tracks() — fetches tracks with enriched metadata."""

    @patch("core.src.playlist.get_spotify_client")
    def test_returns_enriched_tracks(self, mock_client_fn):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        sp.playlist_items.return_value = {
            "items": [{
                "item": {
                    "uri": "spotify:track:abc123",
                    "name": "Test Song",
                    "artists": [{"name": "Test Artist", "external_urls": {"spotify": "https://open.spotify.com/artist/1"}}],
                    "album": {
                        "images": [{"url": "https://img/lg.jpg"}, {"url": "https://img/sm.jpg"}],
                        "external_urls": {"spotify": "https://open.spotify.com/album/1"},
                    },
                    "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
                },
            }],
            "next": None,
        }
        result = get_playlist_tracks("pl1")
        assert len(result) == 1
        t = result[0]
        assert t["artist"] == "Test Artist"
        assert t["track"] == "Test Song"
        assert t["uri"] == "spotify:track:abc123"
        assert t["track_id"] == "abc123"
        assert t["cover_url"] == "https://img/sm.jpg"
        assert t["spotify_url"] == "https://open.spotify.com/track/abc123"
        assert t["artist_url"] == "https://open.spotify.com/artist/1"
        assert t["album_url"] == "https://open.spotify.com/album/1"

    @patch("core.src.playlist.get_spotify_client")
    def test_skips_entries_without_track(self, mock_client_fn):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        sp.playlist_items.return_value = {
            "items": [
                {"item": None},
                {"item": {"uri": "spotify:track:ok", "name": "Good", "artists": [{"name": "A"}], "album": {}, "external_urls": {}}},
            ],
            "next": None,
        }
        result = get_playlist_tracks("pl1")
        assert len(result) == 1
        assert result[0]["track"] == "Good"

    @patch("core.src.playlist.get_spotify_client")
    def test_paginates(self, mock_client_fn):
        sp = MagicMock()
        mock_client_fn.return_value = sp
        page1 = {
            "items": [{"item": {"uri": "spotify:track:1", "name": "T1", "artists": [{"name": "A1"}], "album": {}, "external_urls": {}}}],
            "next": "page2",
        }
        page2 = {
            "items": [{"item": {"uri": "spotify:track:2", "name": "T2", "artists": [{"name": "A2"}], "album": {}, "external_urls": {}}}],
            "next": None,
        }
        sp.playlist_items.return_value = page1
        sp.next.return_value = page2
        result = get_playlist_tracks("pl1")
        assert len(result) == 2
        assert result[0]["track"] == "T1"
        assert result[1]["track"] == "T2"


class TestFilterEmergingArtists:
    """Unit tests for filter_emerging_artists()."""

    def _track(self, release_date):
        return {"artist": "Test Artist", "track": "Test Track", "release_date": release_date}

    def test_recent_full_date_survives(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        recent = f"{now.year}-{now.month:02d}-01"
        survivors, rejected = filter_emerging_artists([self._track(recent)], cutoff_months=6)
        assert len(survivors) == 1
        assert len(rejected) == 0

    def test_old_full_date_rejected(self):
        survivors, rejected = filter_emerging_artists([self._track("2020-01-01")], cutoff_months=6)
        assert len(survivors) == 0
        assert len(rejected) == 1

    def test_year_only_recent_survives(self):
        from datetime import datetime, timezone
        year = datetime.now(timezone.utc).year
        # Dec 31 of current year is >= cutoff
        survivors, rejected = filter_emerging_artists([self._track(str(year))], cutoff_months=6)
        assert len(survivors) == 1

    def test_year_only_old_rejected(self):
        survivors, rejected = filter_emerging_artists([self._track("2015")], cutoff_months=6)
        assert len(survivors) == 0
        assert len(rejected) == 1

    def test_missing_release_date_kept(self):
        survivors, rejected = filter_emerging_artists([self._track("")], cutoff_months=6)
        assert len(survivors) == 1
        assert len(rejected) == 0

    def test_none_release_date_kept(self):
        track = {"artist": "A", "track": "T", "release_date": None}
        survivors, rejected = filter_emerging_artists([track], cutoff_months=6)
        assert len(survivors) == 1

    def test_month_only_recent_survives(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        recent = f"{now.year}-{now.month:02d}"
        survivors, rejected = filter_emerging_artists([self._track(recent)], cutoff_months=6)
        assert len(survivors) == 1
        assert len(rejected) == 0

    def test_month_only_old_rejected(self):
        survivors, rejected = filter_emerging_artists([self._track("2015-06")], cutoff_months=6)
        assert len(survivors) == 0
        assert len(rejected) == 1

    def test_mixed_batch(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        recent = f"{now.year}-{now.month:02d}-01"
        tracks = [self._track(recent), self._track("2010-05-20"), self._track("")]
        survivors, rejected = filter_emerging_artists(tracks, cutoff_months=6)
        assert len(survivors) == 2   # recent + missing date
        assert len(rejected) == 1   # 2010 track


class TestStreamingScope:
    """Web Playback SDK requires the ``streaming`` scope (§8a)."""

    def test_oauth_includes_streaming_scope(self):
        with patch("core.src.playlist.SpotifyOAuth") as mock_oauth:
            from core.src.playlist import get_spotify_oauth
            get_spotify_oauth()
            kwargs = mock_oauth.call_args.kwargs
            assert "streaming" in kwargs["scope"].split()
            # Existing scopes must still be present.
            assert "playlist-modify-private" in kwargs["scope"]
            assert "playlist-read-private" in kwargs["scope"]
            assert "user-read-private" in kwargs["scope"]


class TestGetSpotifySessionInfo:
    @patch("core.src.playlist.get_spotify_client")
    @patch("core.src.playlist.get_spotify_auth_status", return_value="authenticated")
    def test_premium_user(self, _mock_status, mock_client):
        sp = MagicMock()
        sp.current_user.return_value = {"product": "premium"}
        mock_client.return_value = sp
        from core.src.playlist import get_spotify_session_info
        info = get_spotify_session_info()
        assert info == {"is_premium": True, "product": "premium"}

    @patch("core.src.playlist.get_spotify_client")
    @patch("core.src.playlist.get_spotify_auth_status", return_value="authenticated")
    def test_free_user(self, _mock_status, mock_client):
        sp = MagicMock()
        sp.current_user.return_value = {"product": "free"}
        mock_client.return_value = sp
        from core.src.playlist import get_spotify_session_info
        info = get_spotify_session_info()
        assert info["is_premium"] is False
        assert info["product"] == "free"

    @patch("core.src.playlist.get_spotify_auth_status", return_value="not_authenticated")
    def test_unauthenticated_returns_defaults(self, _mock_status):
        from core.src.playlist import get_spotify_session_info
        info = get_spotify_session_info()
        assert info == {"is_premium": False, "product": None}


class TestGetSpotifyAccessToken:
    @patch("core.src.playlist.get_spotify_oauth")
    def test_returns_token_when_cached(self, mock_oauth):
        oauth = MagicMock()
        oauth.cache_handler.get_cached_token.return_value = {"access_token": "tok_xyz"}
        oauth.validate_token.return_value = {"access_token": "tok_xyz"}
        mock_oauth.return_value = oauth
        from core.src.playlist import get_spotify_access_token
        assert get_spotify_access_token() == "tok_xyz"

    @patch("core.src.playlist.get_spotify_oauth")
    def test_returns_none_when_no_token(self, mock_oauth):
        oauth = MagicMock()
        oauth.cache_handler.get_cached_token.return_value = None
        oauth.validate_token.return_value = None
        mock_oauth.return_value = oauth
        from core.src.playlist import get_spotify_access_token
        assert get_spotify_access_token() is None
