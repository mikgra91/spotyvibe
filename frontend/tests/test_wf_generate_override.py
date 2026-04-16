"""Integration test: Generate Playlist (Override/Replace) + Refine."""
import json
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import (
    create_integration_server, build_sse_stream,
    open_generate_section, open_review_section,
    GENERATED_TRACKS_OVERRIDE_A, GENERATED_TRACKS_OVERRIDE_B, PLAYLISTS,
)


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestGenerateOverridePlaylist:
    """Generate with Replace mode, re-generate, verify playlist changed."""

    def _setup_generation_with_tracks(self, page: Page, base_url: str, tracks: list,
                                       playlist_url: str):
        sse_body = build_sse_stream(tracks, playlist_url)
        try:
            page.unroute("**/api/run")
        except Exception:
            pass
        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_body,
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))

    def _select_replace_mode(self, page: Page):
        adv_btn = page.locator(".gen-mode-btn[data-mode='advanced']")
        if adv_btn.count() > 0:
            adv_btn.click()
            page.wait_for_timeout(100)
        replace_radio = page.locator('input[name="playlist_mode"][value="replace"]')
        if replace_radio.count() > 0:
            replace_radio.check(force=True)
            page.wait_for_timeout(100)

    def test_first_generation_shows_set_a(self, page: Page, base_url):
        self._setup_generation_with_tracks(
            page, base_url, GENERATED_TRACKS_OVERRIDE_A,
            "https://open.spotify.com/playlist/pl-replace-1",
        )
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        self._select_replace_mode(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)
        assert page.locator(".track-item").count() == 3
        expect(page.locator(".track-item").nth(0)).to_contain_text("Tool")
        expect(page.locator(".track-item").nth(1)).to_contain_text("Deftones")
        expect(page.locator(".track-item").nth(2)).to_contain_text("System of a Down")

    def test_second_generation_replaces_with_set_b(self, page: Page, base_url):
        self._setup_generation_with_tracks(
            page, base_url, GENERATED_TRACKS_OVERRIDE_A,
            "https://open.spotify.com/playlist/pl-replace-1",
        )
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        self._select_replace_mode(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)
        assert page.locator(".track-item").count() == 3
        self._setup_generation_with_tracks(
            page, base_url, GENERATED_TRACKS_OVERRIDE_B,
            "https://open.spotify.com/playlist/pl-replace-1",
        )
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        self._select_replace_mode(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)
        assert page.locator(".track-item").count() == 3
        expect(page.locator(".track-item").nth(0)).to_contain_text("Porcupine Tree")
        expect(page.locator(".track-item").nth(1)).to_contain_text("Opeth")
        expect(page.locator(".track-item").nth(2)).to_contain_text("Steven Wilson")

    def test_refine_shows_replaced_tracks(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        replaced_tracks = [
            {"artist": "Porcupine Tree", "track": "Trains", "track_id": "rt1",
             "cover_url": "https://example.com/c1.jpg"},
            {"artist": "Opeth", "track": "Harvest", "track_id": "rt2",
             "cover_url": "https://example.com/c2.jpg"},
            {"artist": "Steven Wilson", "track": "Routine", "track_id": "rt3",
             "cover_url": "https://example.com/c3.jpg"},
        ]
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": PLAYLISTS}),
        ))
        page.route("**/api/playlist/*/tracks", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks": replaced_tracks}),
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
        expect(review_items.nth(0)).to_contain_text("Porcupine Tree")
        expect(review_items.nth(1)).to_contain_text("Opeth")
        expect(review_items.nth(2)).to_contain_text("Steven Wilson")

