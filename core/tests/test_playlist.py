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

    @patch("core.src.playlist.get_spotify_oauth")
    def test_clears_stale_cache_before_authorize(self, mock_oauth, tmp_path):
        # A stale cache from a previous OAuth round must be removed before
        # generating the authorize URL — otherwise spotipy reuses the old
        # client_id at callback exchange and Spotify returns invalid_client.
        cache = tmp_path / ".spotify-cache"
        cache.write_text('{"access_token": "stale"}')
        mock_oauth.return_value.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?..."
        with patch("core.src.playlist.CACHE_FILE", cache):
            get_spotify_auth_url()
        assert not cache.exists()

    @patch("core.src.playlist.get_spotify_oauth")
    def test_no_cache_does_not_raise(self, mock_oauth, tmp_path):
        cache = tmp_path / ".spotify-cache"  # never created
        mock_oauth.return_value.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?..."
        with patch("core.src.playlist.CACHE_FILE", cache):
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


class TestSearchTracksRunCache:
    """L2 (2026-05-06): per-run search-result cache.

    The cache is bracketed by ``start_run_search_cache()`` /
    ``end_run_search_cache()`` around a generation run, so a track the
    LLM proposes in batch 1 AND batch 5 only hits Spotify once. The
    first call populates; the second skips the network entirely.
    """

    def _mock_oauth_and_spotify(self, sp_mock):
        oauth = MagicMock()
        oauth.cache_handler.get_cached_token.return_value = {"access_token": "tok"}
        oauth.validate_token.return_value = {"access_token": "tok"}
        return patch("core.src.playlist.get_spotify_oauth", return_value=oauth), \
               patch("core.src.playlist.spotipy.Spotify", return_value=sp_mock)

    def test_cache_off_by_default(self):
        """Without start_run_search_cache, every call hits Spotify."""
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        # Defensive: ensure cache is closed.
        pl.end_run_search_cache()
        with p_oauth, p_sp:
            pl.search_tracks([{"artist": "a", "track": "b"}])
            pl.search_tracks([{"artist": "a", "track": "b"}])
        assert sp.search.call_count == 2

    def test_cache_hits_skip_spotify_for_repeat_pair(self):
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {
                "items": [{
                    "uri": "spotify:track:1",
                    "album": {"images": [{"url": "img"}], "release_date": "2020"},
                }]
            }
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                first, _ = pl.search_tracks([{"artist": "a", "track": "b"}])
                second, _ = pl.search_tracks([{"artist": "a", "track": "b"}])
            assert sp.search.call_count == 1  # 2nd call short-circuited
            assert first[0]["uri"] == "spotify:track:1"
            assert second[0]["uri"] == "spotify:track:1"
        finally:
            pl.end_run_search_cache()

    def test_cache_normalises_case_and_whitespace(self):
        """Cache key is lower/strip — `'  Bear Ghost '` and
        `'bear ghost'` collide."""
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                pl.search_tracks([{"artist": "  Bear Ghost  ", "track": "Mr Bubbles"}])
                pl.search_tracks([{"artist": "bear ghost", "track": "MR BUBBLES"}])
            assert sp.search.call_count == 1
        finally:
            pl.end_run_search_cache()

    def test_cache_caches_not_found_too(self):
        """A miss is also worth caching — re-searching a hallucination
        wastes a roundtrip every time."""
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {"tracks": {"items": []}}
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                _, miss_a = pl.search_tracks([{"artist": "halluc", "track": "fake"}])
                _, miss_b = pl.search_tracks([{"artist": "halluc", "track": "fake"}])
            assert sp.search.call_count == 1
            assert miss_a == miss_b == ["halluc - fake"]
        finally:
            pl.end_run_search_cache()

    def test_end_run_clears_cache(self):
        """After end_run, a re-opened cache must not see prior entries."""
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                pl.search_tracks([{"artist": "a", "track": "b"}])
        finally:
            pl.end_run_search_cache()
        # Re-open. Same call must hit Spotify again (different "run").
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                pl.search_tracks([{"artist": "a", "track": "b"}])
            assert sp.search.call_count == 2
        finally:
            pl.end_run_search_cache()

    def test_cache_does_not_bleed_caller_supplied_keys(self):
        """Caller-supplied fields (like GPT genres) on the input track
        must be applied to the cached enrichment — never replaced by
        stale values from the first batch."""
        from core.src import playlist as pl
        sp = MagicMock()
        sp.search.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:1", "album": {"images": []}}]}
        }
        p_oauth, p_sp = self._mock_oauth_and_spotify(sp)
        pl.start_run_search_cache()
        try:
            with p_oauth, p_sp:
                first, _ = pl.search_tracks([
                    {"artist": "a", "track": "b", "genres": ["rock"]},
                ])
                second, _ = pl.search_tracks([
                    {"artist": "a", "track": "b", "genres": ["pop"]},
                ])
            # Cache stored only Spotify-derived fields; caller's
            # GPT-supplied `genres` survives the round-trip.
            assert first[0]["genres"] == ["rock"]
            assert second[0]["genres"] == ["pop"]
        finally:
            pl.end_run_search_cache()


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
        from core.src.errors import TranslatableError
        with pytest.raises(TranslatableError, match="403") as exc:
            add_to_playlist([{"artist": "a", "track": "b", "uri": "spotify:track:1"}])
        assert exc.value.key == "error.spotify.reconnect_required"
        assert exc.value.status_code == 403
        # A 403 on a playlist write must NOT nuke the whole Spotify session —
        # it usually means the target playlist isn't the user's to modify.
        mock_disconnect.assert_not_called()


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
            # Required to append to / replace existing *public* playlists.
            assert "playlist-modify-public" in kwargs["scope"]
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


class TestSerialSearchModeResolvers:
    """2026-05-07: env-var resolvers that throttle Spotify search calls
    during the eval harness without changing the user-facing app path."""

    def test_serial_off_by_default(self, monkeypatch):
        from core.src.playlist import _is_serial_search_mode
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", raising=False)
        assert _is_serial_search_mode() is False

    def test_serial_on_for_truthy_values(self, monkeypatch):
        from core.src.playlist import _is_serial_search_mode
        for val in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", val)
            assert _is_serial_search_mode() is True, f"failed for {val!r}"

    def test_serial_off_for_falsy_or_empty(self, monkeypatch):
        from core.src.playlist import _is_serial_search_mode
        for val in ("", "0", "no", "false", "off", "garbage"):
            monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", val)
            assert _is_serial_search_mode() is False, f"failed for {val!r}"

    def test_pool_size_default_uses_min(self, monkeypatch):
        # P2 (2026-05-24): default cap clamped to DEFAULT_MAX_SEARCH_WORKERS
        # (2) so callers can no longer accidentally fire 5+ concurrent
        # searches. The previous behaviour (raw min) is preserved when
        # n_unique < cap.
        from core.src.playlist import (
            _resolve_search_pool_size, DEFAULT_MAX_SEARCH_WORKERS,
        )
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", raising=False)
        monkeypatch.delenv("SPOTIVIBE_MAX_SEARCH_WORKERS", raising=False)
        assert DEFAULT_MAX_SEARCH_WORKERS == 2
        assert _resolve_search_pool_size(5, 10) == 2
        assert _resolve_search_pool_size(5, 3) == 2
        assert _resolve_search_pool_size(5, 2) == 2
        assert _resolve_search_pool_size(5, 1) == 1
        assert _resolve_search_pool_size(5, 0) == 1

    def test_pool_size_serial_forces_one(self, monkeypatch):
        from core.src.playlist import _resolve_search_pool_size
        monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", "1")
        assert _resolve_search_pool_size(5, 10) == 1
        assert _resolve_search_pool_size(5, 0) == 1

    def test_pool_size_env_var_override_in_range(self, monkeypatch):
        # P2 (2026-05-24): SPOTIVIBE_MAX_SEARCH_WORKERS lets a power
        # user tune concurrency without code change. Values in [1, 5]
        # are honoured.
        from core.src.playlist import _resolve_search_pool_size
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", raising=False)
        monkeypatch.setenv("SPOTIVIBE_MAX_SEARCH_WORKERS", "4")
        assert _resolve_search_pool_size(5, 10) == 4
        monkeypatch.setenv("SPOTIVIBE_MAX_SEARCH_WORKERS", "1")
        assert _resolve_search_pool_size(5, 10) == 1

    def test_pool_size_env_var_out_of_range_falls_back(self, monkeypatch):
        # Misconfigured values silently use the safe default so a typo
        # can't reproduce the 2026-05-24 ban incident.
        from core.src.playlist import (
            _resolve_search_pool_size, DEFAULT_MAX_SEARCH_WORKERS,
        )
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", raising=False)
        for bad in ("0", "99", "-3", "notanumber", ""):
            monkeypatch.setenv("SPOTIVIBE_MAX_SEARCH_WORKERS", bad)
            assert _resolve_search_pool_size(5, 10) == DEFAULT_MAX_SEARCH_WORKERS, (
                f"bad value {bad!r} should fall back to default"
            )

    def test_post_search_throttle_no_op_when_unset(self, monkeypatch):
        import core.src.playlist as pl
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S", raising=False)
        called = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: called.append(s))
        pl._post_search_throttle()
        assert called == []

    def test_post_search_throttle_no_op_for_invalid(self, monkeypatch):
        import core.src.playlist as pl
        monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S", "notanumber")
        called = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: called.append(s))
        pl._post_search_throttle()
        assert called == []

    def test_post_search_throttle_no_op_for_zero_or_negative(self, monkeypatch):
        import core.src.playlist as pl
        called = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: called.append(s))
        for val in ("0", "-1", "-0.5"):
            monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S", val)
            pl._post_search_throttle()
        assert called == []

    def test_post_search_throttle_sleeps_for_positive(self, monkeypatch):
        import core.src.playlist as pl
        monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_DELAY_S", "0.5")
        called = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: called.append(s))
        pl._post_search_throttle()
        assert called == [0.5]


# ── N3 (2026-05-13): iter_search_tracks verifier-precedence bug-fix ──

class TestIterSearchTracksVerifierPrecedence:
    """Regression test for the bug discovered 2026-05-13.

    Before the fix, ``iter_search_tracks`` validated the Spotify token
    BEFORE checking ``_VERIFIER``. When the harness installed a
    ``NullVerifier`` (via ``--verify-mode null``) AND the spotify cache
    was missing (OP2), every track came back as ``"not_found"`` — the
    null path was effectively dead. The fix: resolve the verifier
    first; only validate the Spotify token when no alternative
    verifier is installed.
    """

    def setup_method(self):
        # Make sure no stale verifier from a previous test bleeds in.
        from core.src import playlist as pl
        pl.clear_verifier()

    def teardown_method(self):
        from core.src import playlist as pl
        pl.clear_verifier()

    def test_null_verifier_yields_found_without_spotify_token(self, monkeypatch):
        """With a NullVerifier installed, no Spotify token lookup must
        happen and every track must come back as ``found`` (NullVerifier
        treats every track as existing)."""
        from core.src import playlist as pl
        from core.src.verify import NullVerifier

        # Sentinel: if the production token-fetch path is touched, blow up.
        def _explode(*a, **kw):
            raise AssertionError(
                "iter_search_tracks must not call get_spotify_oauth() "
                "when a verifier is installed"
            )

        monkeypatch.setattr(pl, "get_spotify_oauth", _explode)

        pl.set_verifier(NullVerifier())
        tracks = [
            {"artist": "X", "track": "Y"},
            {"artist": "A", "track": "B"},
        ]
        results = list(pl.iter_search_tracks(tracks))
        assert len(results) == 2
        for kind, _payload in results:
            assert kind == "found", \
                f"NullVerifier should yield 'found', got {kind}"

    def test_no_verifier_still_requires_spotify_token(self, monkeypatch):
        """Backwards-compat: production (no verifier installed) must
        keep the existing token-required behaviour — missing token
        yields 'not_found' for every track."""
        from core.src import playlist as pl

        # No verifier installed; mock the oauth path to return no token.
        class _FakeCache:
            def get_cached_token(self):
                return None

        class _FakeOAuth:
            cache_handler = _FakeCache()
            def validate_token(self, _t):
                return None

        monkeypatch.setattr(pl, "get_spotify_oauth", lambda: _FakeOAuth())

        results = list(pl.iter_search_tracks([{"artist": "X", "track": "Y"}]))
        assert results == [("not_found", "X - Y")]


# ── P0 (2026-05-24): Spotify long-cooldown gate ─────────────────────


class TestSpotifyCooldown:
    """Round-trip + behavioural tests for the Retry-After gate.

    The cooldown is a one-line file; tests use a per-test temp path so
    state never leaks between runs.
    """

    def _redirect_cooldown(self, monkeypatch, tmp_path):
        import core.src.playlist as pl
        cf = tmp_path / ".spotify-cooldown"
        monkeypatch.setattr(pl, "COOLDOWN_FILE", cf)
        return pl, cf

    def test_no_cooldown_when_file_missing(self, monkeypatch, tmp_path):
        pl, _ = self._redirect_cooldown(monkeypatch, tmp_path)
        assert pl.spotify_cooldown_remaining_s() == 0
        assert pl.is_spotify_in_cooldown() is False

    def test_set_and_read_roundtrip(self, monkeypatch, tmp_path):
        pl, cf = self._redirect_cooldown(monkeypatch, tmp_path)
        pl._set_spotify_cooldown(300)
        remaining = pl.spotify_cooldown_remaining_s()
        # Allow a small window for test execution time.
        assert 295 <= remaining <= 300
        assert pl.is_spotify_in_cooldown() is True
        assert cf.exists()

    def test_expired_cooldown_reads_zero(self, monkeypatch, tmp_path):
        pl, cf = self._redirect_cooldown(monkeypatch, tmp_path)
        import time as _t
        cf.write_text(str(int(_t.time()) - 10), encoding="utf-8")
        assert pl.spotify_cooldown_remaining_s() == 0

    def test_malformed_file_treated_as_no_cooldown(self, monkeypatch, tmp_path):
        pl, cf = self._redirect_cooldown(monkeypatch, tmp_path)
        cf.write_text("not-a-number", encoding="utf-8")
        assert pl.spotify_cooldown_remaining_s() == 0

    def test_clear_removes_file(self, monkeypatch, tmp_path):
        pl, cf = self._redirect_cooldown(monkeypatch, tmp_path)
        pl._set_spotify_cooldown(60)
        assert cf.exists()
        pl.clear_spotify_cooldown()
        assert not cf.exists()
        assert pl.spotify_cooldown_remaining_s() == 0

    def test_set_zero_or_negative_is_noop(self, monkeypatch, tmp_path):
        pl, cf = self._redirect_cooldown(monkeypatch, tmp_path)
        pl._set_spotify_cooldown(0)
        pl._set_spotify_cooldown(-5)
        assert not cf.exists()


class TestSpotifySearch429LongRetryAfter:
    """P0 (2026-05-24): when Retry-After exceeds the threshold the
    handler must persist a cooldown and raise SpotifyCooldownError
    instead of looping retries that extend the ban."""

    def _setup(self, monkeypatch, tmp_path):
        import core.src.playlist as pl
        cf = tmp_path / ".spotify-cooldown"
        monkeypatch.setattr(pl, "COOLDOWN_FILE", cf)
        # Skip the jitter sleep in tests for speed/determinism.
        monkeypatch.setattr(pl, "_apply_search_jitter", lambda: None)
        # Skip post-search throttle (no-op for safety).
        monkeypatch.setattr(pl, "_post_search_throttle", lambda: None)
        return pl, cf

    def test_long_retry_after_persists_cooldown_and_raises(
            self, monkeypatch, tmp_path):
        pl, cf = self._setup(monkeypatch, tmp_path)
        from spotipy.exceptions import SpotifyException

        sp = MagicMock()
        sp.search.side_effect = SpotifyException(
            http_status=429,
            code=-1,
            msg="rate limited",
            headers={"Retry-After": "38401"},
        )

        with pytest.raises(pl.SpotifyCooldownError) as excinfo:
            pl._do_spotify_search({"artist": "a", "track": "b"}, sp)

        assert excinfo.value.seconds_remaining >= 38000
        # Spotify is called exactly once — no retries against a banned token.
        assert sp.search.call_count == 1
        # Cooldown persisted for future runs.
        assert cf.exists()
        assert pl.spotify_cooldown_remaining_s() > 0

    def test_short_retry_after_still_uses_retry_loop(
            self, monkeypatch, tmp_path):
        pl, cf = self._setup(monkeypatch, tmp_path)
        from spotipy.exceptions import SpotifyException

        # Skip the actual sleep
        monkeypatch.setattr(pl.time, "sleep", lambda s: None)

        sp = MagicMock()
        # First call 429 (short Retry-After), second call succeeds.
        sp.search.side_effect = [
            SpotifyException(
                http_status=429, code=-1, msg="throttle",
                headers={"Retry-After": "5"},
            ),
            {"tracks": {"items": [{
                "uri": "spotify:track:1",
                "album": {"images": [], "release_date": "2024-01-01"},
                "external_urls": {"spotify": "u"},
                "artists": [{"external_urls": {"spotify": "au"}, "id": "aid"}],
                "preview_url": None,
            }]}},
        ]

        result_type, _ = pl._do_spotify_search(
            {"artist": "a", "track": "b"}, sp)
        assert result_type == "found"
        # No cooldown should have been persisted for a transient 429.
        assert not cf.exists() or pl.spotify_cooldown_remaining_s() == 0
        assert sp.search.call_count == 2

    def test_existing_cooldown_short_circuits_before_call(
            self, monkeypatch, tmp_path):
        pl, _ = self._setup(monkeypatch, tmp_path)
        pl._set_spotify_cooldown(600)
        sp = MagicMock()
        with pytest.raises(pl.SpotifyCooldownError):
            pl._do_spotify_search({"artist": "a", "track": "b"}, sp)
        # Pre-emptive raise — Spotify never touched.
        assert sp.search.call_count == 0


class TestIterSearchTracksCooldown:
    """The streaming wrapper must short-circuit when cool-down is set
    AND must cancel pending workers if one mid-stream raises."""

    def test_pre_existing_cooldown_short_circuits_all(
            self, monkeypatch, tmp_path):
        import core.src.playlist as pl
        cf = tmp_path / ".spotify-cooldown"
        monkeypatch.setattr(pl, "COOLDOWN_FILE", cf)
        pl._set_spotify_cooldown(900)

        # No verifier installed, no Spotify call should happen.
        tracks = [{"artist": "x", "track": str(i)} for i in range(3)]
        results = list(pl.iter_search_tracks(tracks))
        assert len(results) == 3
        assert all(k == "not_found" for k, _ in results)


class TestApplySearchJitter:
    def test_jitter_sleeps_in_default_mode(self, monkeypatch):
        import core.src.playlist as pl
        monkeypatch.delenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", raising=False)
        slept = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: slept.append(s))
        pl._apply_search_jitter()
        assert len(slept) == 1
        assert pl._JITTER_MIN_S <= slept[0] <= pl._JITTER_MAX_S

    def test_jitter_skipped_in_serial_mode(self, monkeypatch):
        import core.src.playlist as pl
        monkeypatch.setenv("SPOTIVIBE_SPOTIFY_SEARCH_SERIAL", "1")
        slept = []
        monkeypatch.setattr(pl.time, "sleep", lambda s: slept.append(s))
        pl._apply_search_jitter()
        assert slept == []
