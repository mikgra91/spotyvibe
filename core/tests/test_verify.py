"""Tests for the verifier abstraction (Track A Step 1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.src.verify import (
    ChainVerifier, LastfmVerifier, MusicBrainzVerifier,
    NullVerifier, OverlayVerifier, SpotifyVerifier, Verifier,
    _SqliteVerifyCache, normalise_title,
)


# ── Protocol contract ────────────────────────────────────────────────

class TestProtocol:
    def test_null_verifier_satisfies_protocol(self):
        assert isinstance(NullVerifier(), Verifier)

    def test_spotify_verifier_satisfies_protocol(self):
        v = SpotifyVerifier(shared_sp=MagicMock())
        assert isinstance(v, Verifier)

    def test_protocol_names(self):
        assert SpotifyVerifier(shared_sp=MagicMock()).name == "spotify"
        assert NullVerifier().name == "null"


# ── NullVerifier ─────────────────────────────────────────────────────

class TestNullVerifier:
    def test_every_input_marked_found(self):
        v = NullVerifier()
        kind, payload = v.verify({"artist": "x", "track": "y"})
        assert kind == "found"
        assert payload["artist"] == "x"
        assert payload["track"] == "y"

    def test_synthetic_spotify_keys_populated(self):
        """Downstream code (release_year parser, SSE event builder)
        expects every Spotify-shaped key to be present. NullVerifier
        sets each to None so no KeyError surfaces in the consumer."""
        v = NullVerifier()
        _, payload = v.verify({"artist": "x", "track": "y"})
        for key in ("uri", "track_id", "cover_url", "preview_url",
                    "spotify_url", "album_url", "release_date",
                    "artist_url", "artist_id"):
            assert key in payload
            assert payload[key] is None

    def test_does_not_mutate_input_dict(self):
        v = NullVerifier()
        original = {"artist": "x", "track": "y"}
        v.verify(original)
        assert original == {"artist": "x", "track": "y"}

    def test_preserves_caller_supplied_extras(self):
        # When the caller has already filled e.g. ``release_date``
        # (deferred-mode late-verify pass), NullVerifier must NOT
        # overwrite it with None.
        v = NullVerifier()
        _, payload = v.verify({
            "artist": "x", "track": "y", "release_date": "2024-01-01",
        })
        assert payload["release_date"] == "2024-01-01"


# ── SpotifyVerifier ──────────────────────────────────────────────────

class TestSpotifyVerifier:
    @patch("core.src.playlist._do_spotify_search")
    def test_delegates_to_do_spotify_search(self, mock_search):
        mock_search.return_value = ("found", {"artist": "x", "track": "y",
                                               "uri": "spotify:track:abc"})
        sp = MagicMock()
        v = SpotifyVerifier(shared_sp=sp)
        result = v.verify({"artist": "x", "track": "y"})
        # Wrapper is genuinely thin — forwards the exact tuple.
        assert result == ("found", {"artist": "x", "track": "y",
                                      "uri": "spotify:track:abc"})
        # And it must pass the spotipy client through unchanged.
        mock_search.assert_called_once_with({"artist": "x", "track": "y"}, sp)


# ── Playlist module slot ─────────────────────────────────────────────

class TestPlaylistModuleSlot:
    def test_default_verifier_is_none(self):
        from core.src import playlist
        playlist.clear_verifier()
        assert playlist.get_verifier() is None

    def test_set_and_get_round_trip(self):
        from core.src import playlist
        v = NullVerifier()
        playlist.set_verifier(v)
        try:
            assert playlist.get_verifier() is v
        finally:
            playlist.clear_verifier()

    def test_clear_verifier_alias(self):
        from core.src import playlist
        playlist.set_verifier(NullVerifier())
        playlist.clear_verifier()
        assert playlist.get_verifier() is None


# ── End-to-end: iter_search_tracks with a verifier installed ─────────

class TestIterSearchWithVerifier:
    """Pin the load-bearing behaviour: when ``_VERIFIER`` is set,
    ``iter_search_tracks`` MUST consult it instead of hitting Spotify.
    A regression here would silently burn the user's Spotify quota in
    fast-eval mode — the failure mode this whole refactor exists to
    prevent."""

    def test_null_verifier_skips_spotify_and_yields_found(self):
        from core.src import playlist
        # Patch the production Spotify path to BLOW UP if called — that
        # is exactly the contract we want to enforce.
        sentinel = {"called": False}

        def _explode(*_args, **_kwargs):
            sentinel["called"] = True
            raise AssertionError("Spotify path called despite NullVerifier")

        playlist.set_verifier(NullVerifier())
        try:
            with patch.object(playlist, "_do_spotify_search", _explode), \
                 patch.object(playlist, "get_spotify_oauth") as mock_oauth:
                # iter_search_tracks gates on token presence; give it a fake.
                mock_oauth.return_value.cache_handler.get_cached_token \
                    .return_value = {"access_token": "fake"}
                mock_oauth.return_value.validate_token.return_value = \
                    {"access_token": "fake"}
                results = list(playlist.iter_search_tracks([
                    {"artist": "x", "track": "y"},
                ]))
        finally:
            playlist.clear_verifier()

        assert sentinel["called"] is False, "Spotify path must NOT fire"
        assert len(results) == 1
        kind, payload = results[0]
        assert kind == "found"
        assert payload["artist"] == "x"
        assert payload["uri"] is None     # NullVerifier synthesised None
        # release_year is post-parsed in iter_search_tracks from release_date.
        assert "release_year" in payload


# ── normalise_title ─────────────────────────────────────────────────

class TestNormaliseTitle:
    def test_lowercases(self):
        assert normalise_title("Good Day") == "good day"

    def test_drops_trailing_parens(self):
        assert normalise_title("Good Day (Remastered 2020)") == "good day"
        assert normalise_title("Track [Live]") == "track"

    def test_strips_punctuation_and_diacritics(self):
        assert normalise_title("Don't Stop") == "dont stop"
        assert normalise_title("Café Söngs") == "cafe songs"

    def test_collapses_whitespace(self):
        assert normalise_title("  multi   space  ") == "multi space"

    def test_empty_input(self):
        assert normalise_title("") == ""
        assert normalise_title(None) == ""


# ── OverlayVerifier ─────────────────────────────────────────────────

class _FakeArtistRow:
    def __init__(self, name, top_tracks):
        self.name = name
        self.top_tracks = list(top_tracks)


class _FakeCorpus:
    """Minimal RagCorpus stand-in: ``artists`` list +
    ``by_name_normalised`` map. Enough for OverlayVerifier."""

    def __init__(self, rows):
        from core.src.rag.corpus import normalise_name
        self.artists = list(rows)
        self.by_name_normalised = {
            normalise_name(r.name): i for i, r in enumerate(self.artists)
        }


class TestOverlayVerifier:
    def test_constructor_rejects_none_corpus(self):
        with pytest.raises(ValueError, match="OverlayVerifier requires"):
            OverlayVerifier(None)

    def test_exact_title_match_returns_found(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Good Day", "Banana Man"])])
        v = OverlayVerifier(c)
        kind, payload = v.verify({"artist": "Tally Hall", "track": "Good Day"})
        assert kind == "found"
        assert payload["verified_by"] == "overlay"
        assert payload["overlay_match"] == "Good Day"
        # Spotify-shaped enrichment keys must all be present.
        assert payload["uri"] is None

    def test_remaster_suffix_still_matches(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Good Day"])])
        v = OverlayVerifier(c)
        kind, payload = v.verify({
            "artist": "Tally Hall", "track": "Good Day (Remastered 2024)",
        })
        assert kind == "found"
        assert payload["overlay_match"] == "Good Day"

    def test_case_and_punctuation_insensitive(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Don't Stop"])])
        v = OverlayVerifier(c)
        kind, _ = v.verify({"artist": "tally hall", "track": "dont stop"})
        assert kind == "found"

    def test_artist_missing_returns_not_found(self):
        c = _FakeCorpus([_FakeArtistRow("Other Band", ["Song"])])
        v = OverlayVerifier(c)
        kind, label = v.verify({"artist": "Tally Hall", "track": "Good Day"})
        assert kind == "not_found"
        assert label == "Tally Hall - Good Day"

    def test_artist_present_but_no_top_tracks(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", [])])
        v = OverlayVerifier(c)
        kind, _ = v.verify({"artist": "Tally Hall", "track": "Good Day"})
        assert kind == "not_found"

    def test_artist_present_but_title_missing(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Banana Man"])])
        v = OverlayVerifier(c)
        kind, _ = v.verify({"artist": "Tally Hall", "track": "Good Day"})
        assert kind == "not_found"

    def test_empty_input_fields(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Good Day"])])
        v = OverlayVerifier(c)
        assert v.verify({"artist": "", "track": "Good Day"})[0] == "not_found"
        assert v.verify({"artist": "Tally Hall", "track": ""})[0] == "not_found"

    def test_satisfies_verifier_protocol(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Good Day"])])
        assert isinstance(OverlayVerifier(c), Verifier)
        assert OverlayVerifier(c).name == "overlay"

    def test_does_not_mutate_input_dict(self):
        c = _FakeCorpus([_FakeArtistRow("Tally Hall", ["Good Day"])])
        v = OverlayVerifier(c)
        original = {"artist": "Tally Hall", "track": "Good Day"}
        v.verify(original)
        assert original == {"artist": "Tally Hall", "track": "Good Day"}


# ── _SqliteVerifyCache ─────────────────────────────────────────────

class TestSqliteCache:
    def test_round_trip(self, tmp_path):
        c = _SqliteVerifyCache(tmp_path / "v.sqlite")
        assert c.get("musicbrainz", "x", "y") is None
        c.put("musicbrainz", "x", "y", "found", '{"a":1}')
        assert c.get("musicbrainz", "x", "y") == ("found", '{"a":1}')

    def test_namespace_by_verifier(self, tmp_path):
        c = _SqliteVerifyCache(tmp_path / "v.sqlite")
        c.put("musicbrainz", "x", "y", "found", '{"a":1}')
        c.put("lastfm",      "x", "y", "not_found", None)
        assert c.get("musicbrainz", "x", "y")[0] == "found"
        assert c.get("lastfm", "x", "y")[0] == "not_found"

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "v.sqlite"
        c1 = _SqliteVerifyCache(path)
        c1.put("musicbrainz", "x", "y", "found", '{}')
        c2 = _SqliteVerifyCache(path)
        assert c2.get("musicbrainz", "x", "y")[0] == "found"


# ── MusicBrainzVerifier ─────────────────────────────────────────────

class _FakeMBResponse:
    def __init__(self, status_code: int, body: dict | None = None,
                 headers: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


class _FakeSession:
    """Captures requests + replays canned responses."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self._responses.pop(0)


class TestMusicBrainzVerifier:
    def test_hit_returns_found_with_release_date(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        session = _FakeSession([_FakeMBResponse(200, {
            "recordings": [{
                "id": "rec-id-1",
                "first-release-date": "1985-04-01",
            }],
        })])
        v = MusicBrainzVerifier(cache=cache, session=session,
                                 min_inter_request=0.0)
        kind, payload = v.verify({"artist": "A-ha", "track": "Take On Me"})
        assert kind == "found"
        assert payload["release_date"] == "1985-04-01"
        assert payload["verified_by"] == "musicbrainz"
        assert payload["mb_recording_id"] == "rec-id-1"

    def test_miss_returns_not_found_and_caches(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        session = _FakeSession([_FakeMBResponse(200, {"recordings": []})])
        v = MusicBrainzVerifier(cache=cache, session=session,
                                 min_inter_request=0.0)
        kind, _ = v.verify({"artist": "Unknown", "track": "Whatever"})
        assert kind == "not_found"
        # Second call must NOT hit the network.
        v2 = MusicBrainzVerifier(cache=cache, session=_FakeSession([]),
                                  min_inter_request=0.0)
        assert v2.verify({"artist": "Unknown", "track": "Whatever"})[0] == "not_found"

    def test_cache_hit_skips_network(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        cache.put("musicbrainz", "x", "y", "found", '{"release_date":"2001-01-01"}')
        v = MusicBrainzVerifier(cache=cache, session=_FakeSession([]),
                                 min_inter_request=0.0)
        kind, payload = v.verify({"artist": "X", "track": "Y"})
        assert kind == "found"
        assert payload["release_date"] == "2001-01-01"
        assert payload["verified_by"] == "musicbrainz"

    def test_retry_after_above_cap_raises(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        session = _FakeSession([_FakeMBResponse(503, headers={"Retry-After": "7200"})])
        v = MusicBrainzVerifier(cache=cache, session=session,
                                 min_inter_request=0.0)
        with pytest.raises(RuntimeError, match="exceeds cap"):
            v.verify({"artist": "X", "track": "Y"})

    def test_protocol_satisfied(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        v = MusicBrainzVerifier(cache=cache, session=_FakeSession([]),
                                 min_inter_request=0.0)
        assert isinstance(v, Verifier)
        assert v.name == "musicbrainz"


# ── LastfmVerifier ─────────────────────────────────────────────────

class TestLastfmVerifier:
    def test_no_api_key_returns_not_found(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        v = LastfmVerifier(api_key="", cache=cache,
                            session=_FakeSession([]))
        kind, _ = v.verify({"artist": "X", "track": "Y"})
        assert kind == "not_found"

    def test_hit_returns_found(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        session = _FakeSession([_FakeMBResponse(200, {
            "track": {"name": "Take On Me",
                       "url": "https://www.last.fm/music/A-ha/Take+On+Me"},
        })])
        v = LastfmVerifier(api_key="fake", cache=cache, session=session)
        kind, payload = v.verify({"artist": "A-ha", "track": "Take On Me"})
        assert kind == "found"
        assert payload["verified_by"] == "lastfm"
        assert payload["lastfm_url"].startswith("https://")

    def test_error_response_caches_not_found(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        session = _FakeSession([_FakeMBResponse(200, {"error": 6,
                                                       "message": "Track not found"})])
        v = LastfmVerifier(api_key="fake", cache=cache, session=session)
        assert v.verify({"artist": "X", "track": "Y"})[0] == "not_found"
        # Second call must NOT hit network.
        v2 = LastfmVerifier(api_key="fake", cache=cache,
                             session=_FakeSession([]))
        assert v2.verify({"artist": "X", "track": "Y"})[0] == "not_found"

    def test_protocol_satisfied(self, tmp_path):
        cache = _SqliteVerifyCache(tmp_path / "v.sqlite")
        v = LastfmVerifier(api_key="x", cache=cache,
                            session=_FakeSession([]))
        assert isinstance(v, Verifier)
        assert v.name == "lastfm"


# ── ChainVerifier ──────────────────────────────────────────────────

class _StubVerifier:
    def __init__(self, name, result):
        self.name = name
        self._result = result
        self.calls = 0

    def verify(self, track):
        self.calls += 1
        return self._result


class TestChainVerifier:
    def test_first_hit_wins(self):
        a = _StubVerifier("a", ("found", {"x": 1}))
        b = _StubVerifier("b", ("found", {"x": 2}))
        c = ChainVerifier([a, b])
        kind, payload = c.verify({"artist": "x", "track": "y"})
        assert kind == "found"
        assert payload == {"x": 1}
        assert a.calls == 1 and b.calls == 0

    def test_falls_through_to_next_on_miss(self):
        a = _StubVerifier("a", ("not_found", "x - y"))
        b = _StubVerifier("b", ("found", {"x": 2}))
        c = ChainVerifier([a, b])
        kind, payload = c.verify({"artist": "x", "track": "y"})
        assert kind == "found"
        assert payload == {"x": 2}
        assert a.calls == 1 and b.calls == 1

    def test_all_miss_returns_last_not_found(self):
        a = _StubVerifier("a", ("not_found", "label-a"))
        b = _StubVerifier("b", ("not_found", "label-b"))
        c = ChainVerifier([a, b])
        kind, label = c.verify({"artist": "x", "track": "y"})
        assert kind == "not_found"
        assert label == "label-b"

    def test_exception_in_verifier_does_not_abort_chain(self):
        class _Boom:
            name = "boom"
            def verify(self, _): raise RuntimeError("explode")
        b = _StubVerifier("b", ("found", {"x": 2}))
        c = ChainVerifier([_Boom(), b])
        kind, payload = c.verify({"artist": "x", "track": "y"})
        assert kind == "found"
        assert b.calls == 1

    def test_empty_chain_rejected(self):
        with pytest.raises(ValueError, match="at least one"):
            ChainVerifier([])

    def test_protocol_satisfied(self):
        c = ChainVerifier([NullVerifier()])
        assert isinstance(c, Verifier)
        assert c.name == "chain"
