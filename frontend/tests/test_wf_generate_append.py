"""Integration test: Generate Playlist (Append) + Like/Dislike + Refine."""
import json
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import (
    create_integration_server, build_sse_stream,
    open_generate_section, open_review_section,
    GENERATED_TRACKS_APPEND, PLAYLISTS,
)


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestGenerateAppendPlaylist:
    """Generate in Append mode, give feedback, then verify via Refine Playlist."""

    def _setup_and_generate(self, page: Page, base_url: str, feedback_calls: list):
        sse_body = build_sse_stream(
            GENERATED_TRACKS_APPEND,
            "https://open.spotify.com/playlist/pl-append-1",
        )
        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_body,
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))
        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(status=200, headers={"Content-Type": "application/json"},
                          body=json.dumps({"status": "ok", "removal": {"removed": True}})),
        )[1])
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        append_radio = page.locator('input[name="playlist_mode"][value="append"]')
        if append_radio.count() > 0:
            append_radio.check(force=True)
            page.wait_for_timeout(100)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

    def test_generation_creates_4_tracks(self, page: Page, base_url):
        self._setup_and_generate(page, base_url, [])
        assert page.locator(".track-item").count() == 4

    def test_like_and_dislike_feedback(self, page: Page, base_url):
        feedback_calls = []
        self._setup_and_generate(page, base_url, feedback_calls)
        page.locator("#track-0 .btn-feedback").click()
        page.locator("#submitBtn-0-like").click()
        page.wait_for_timeout(150)
        page.locator("#track-1 .btn-feedback").click()
        page.locator("#submitBtn-1-like").click()
        page.wait_for_timeout(150)
        page.locator("#track-2 .btn-feedback").click()
        page.locator("#submitBtn-2-dislike").click()
        page.wait_for_timeout(150)
        likes = [c for c in feedback_calls if c["action"] == "like"]
        dislikes = [c for c in feedback_calls if c["action"] == "dislike"]
        assert len(likes) == 2
        assert len(dislikes) == 1
        assert likes[0]["artist"] == "Foo Fighters"
        assert likes[1]["artist"] == "Royal Blood"
        assert dislikes[0]["artist"] == "Biffy Clyro"

    def test_refine_shows_remaining_tracks(self, page: Page, base_url):
        feedback_calls = []
        self._setup_and_generate(page, base_url, feedback_calls)
        page.locator("#track-0 .btn-feedback").click()
        page.locator("#submitBtn-0-like").click()
        page.wait_for_timeout(150)
        page.locator("#track-1 .btn-feedback").click()
        page.locator("#submitBtn-1-like").click()
        page.wait_for_timeout(150)
        page.locator("#track-2 .btn-feedback").click()
        page.locator("#submitBtn-2-dislike").click()
        page.wait_for_timeout(150)
        remaining_tracks = [
            {"artist": "Foo Fighters", "track": "Everlong", "track_id": "t1",
             "cover_url": "https://example.com/c1.jpg"},
            {"artist": "Royal Blood", "track": "Figure It Out", "track_id": "t2",
             "cover_url": "https://example.com/c2.jpg"},
            {"artist": "Nothing But Thieves", "track": "Amsterdam", "track_id": "t4",
             "cover_url": "https://example.com/c4.jpg"},
        ]
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": PLAYLISTS}),
        ))
        page.route("**/api/playlist/*/tracks", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks": remaining_tracks}),
        ))
        open_review_section(page)
        page.wait_for_timeout(100)
        picker = page.locator("#reviewPlaylistPicker")
        picker.wait_for(state="visible")
        picker.select_option(index=1)
        page.locator("#reviewLoadBtn").click()
        page.locator("#reviewTrackArea").wait_for(state="visible", timeout=5000)
        review_items = page.locator("#reviewTrackList .track-item")
        assert review_items.count() == 3
        expect(review_items.nth(0)).to_contain_text("Foo Fighters")
        expect(review_items.nth(1)).to_contain_text("Royal Blood")
        expect(review_items.nth(2)).to_contain_text("Nothing But Thieves")

