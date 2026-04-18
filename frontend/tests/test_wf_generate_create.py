"""Integration test: Generate Playlist (Create New) + Like/Dislike + History + Charts."""
import json
import re
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import (
    create_integration_server, build_sse_stream, switch_to_tab,
    open_generate_section, expand_dashboard,
    GENERATED_TRACKS_CREATE, HISTORY_CREATE, TASTE_DATA_CREATE,
)


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestGenerateCreateNewPlaylist:
    """Generate a new playlist, give feedback, verify history and taste charts."""

    def _setup_generation(self, page: Page, base_url: str):
        sse_body = build_sse_stream(
            GENERATED_TRACKS_CREATE,
            "https://open.spotify.com/playlist/pl-create-1",
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
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

    def _run_generation(self, page: Page):
        open_generate_section(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

    def test_generation_creates_5_tracks(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        self._run_generation(page)
        tracks = page.locator(".track-item")
        assert tracks.count() == 5
        expect(tracks.nth(0)).to_contain_text("Muse")
        expect(tracks.nth(1)).to_contain_text("Radiohead")
        expect(tracks.nth(2)).to_contain_text("Arctic Monkeys")
        expect(tracks.nth(3)).to_contain_text("Queens of the Stone Age")
        expect(tracks.nth(4)).to_contain_text("The Black Keys")

    def test_playlist_link_shown(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        self._run_generation(page)
        expect(page.locator("#playlistLinkBox")).to_be_visible()
        expect(page.locator("#playlistLinkBox")).to_contain_text("open.spotify.com")

    def test_like_tracks_sends_feedback(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        feedback_calls = []
        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(status=200, headers={"Content-Type": "application/json"},
                          body=json.dumps({"status": "ok"})),
        )[1])
        self._run_generation(page)
        page.locator("#track-0 .btn-feedback").click()
        page.locator("#submitBtn-0-like").click()
        page.wait_for_timeout(150)
        page.locator("#track-3 .btn-feedback").click()
        page.locator("#submitBtn-3-like").click()
        page.wait_for_timeout(150)
        likes = [c for c in feedback_calls if c["action"] == "like"]
        assert len(likes) == 2
        assert likes[0]["artist"] == "Muse"
        assert likes[1]["artist"] == "Queens of the Stone Age"

    def test_dislike_track_sends_feedback(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        feedback_calls = []
        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(status=200, headers={"Content-Type": "application/json"},
                          body=json.dumps({"status": "ok", "removal": {"removed": True}})),
        )[1])
        self._run_generation(page)
        page.locator("#track-2 .btn-feedback").click()
        page.locator("#submitBtn-2-dislike").click()
        page.wait_for_timeout(150)
        dislikes = [c for c in feedback_calls if c["action"] == "dislike"]
        assert len(dislikes) == 1
        assert dislikes[0]["artist"] == "Arctic Monkeys"

    def test_history_shows_generated_tracks(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        page.route("**/api/runs", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"runs": HISTORY_CREATE}),
        ))
        self._run_generation(page)
        switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(250)
        items = page.locator("#historyList .history-run-item")
        assert items.count() >= 1
        items.first.click()
        page.wait_for_timeout(150)
        expect(items.first).to_have_class(re.compile(r"expanded"))
        expanded = items.first
        for artist in ["Muse", "Radiohead", "Arctic Monkeys", "Queens of the Stone Age", "The Black Keys"]:
            expect(expanded).to_contain_text(artist)

    def test_history_has_playlist_link(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        page.route("**/api/runs", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"runs": HISTORY_CREATE}),
        ))
        self._run_generation(page)
        switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(250)
        link = page.locator("#historyList .history-run-item").first.locator("a", has_text="Open playlist")
        expect(link).to_have_count(1)

    def test_taste_dashboard_charts_reflect_generation(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps(TASTE_DATA_CREATE),
        ))
        self._run_generation(page)
        switch_to_tab(page, "openai")
        expand_dashboard(page)
        page.wait_for_timeout(100)
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(1)
        expect(page.locator("#dashboardNeutral .dashboard-card--scatter svg")).to_have_count(1)
        expect(page.locator("#dashboardNeutral .dashboard-card--decades svg")).to_have_count(1)

    def test_taste_dashboard_empty_state_disappears(self, page: Page, base_url):
        self._setup_generation(page, base_url)
        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps(TASTE_DATA_CREATE),
        ))
        self._run_generation(page)
        switch_to_tab(page, "openai")
        expand_dashboard(page)
        page.wait_for_timeout(100)
        expect(page.locator(".dashboard-empty")).to_be_hidden()

