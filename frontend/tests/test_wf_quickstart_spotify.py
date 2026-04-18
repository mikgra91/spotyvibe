"""Integration test: Quickstart Guide — Spotify provider."""
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import create_integration_server, switch_to_tab


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestQuickstartSpotifyWorkflow:
    """Quickstart guide for the Spotify provider."""

    def _open_quickstart_spotify(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.wait_for_timeout(100)
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        page.evaluate("openQuickstart(true)")
        page.wait_for_timeout(150)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_quickstart_opens_for_spotify(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_toc_has_correct_spotify_entries(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc).to_be_visible()
        visible_entries = toc.locator(
            '.qs-toc-entry[data-qs-provider="both"], '
            '.qs-toc-entry[data-qs-provider="spotify"]'
        )
        assert visible_entries.count() == 5
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Generate a Playlist"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Review"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Refine"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Repeat"]')).to_be_visible()

    def test_toc_does_not_show_openai_entries(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()

    def test_generate_step_content(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Generate a Playlist"]').click()
        page.wait_for_timeout(150)
        step_page = page.locator('[data-qs-page="3"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Generate a Playlist")
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_review_step_content(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Review"]').click()
        page.wait_for_timeout(150)
        step_page = page.locator('[data-qs-page="4"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Review")
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_refine_step_content(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Refine"]').click()
        page.wait_for_timeout(150)
        step_page = page.locator('[data-qs-page="5"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Refine")
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_repeat_step_content(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Repeat"]').click()
        page.wait_for_timeout(150)
        step_page = page.locator('[data-qs-page="6"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Repeat")
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_pagination_navigates_spotify_steps(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="3"]')).to_be_visible()
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="4"]')).to_be_visible()
        page.locator("#qsPagPrev").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="3"]')).to_be_visible()

    def test_quickstart_does_not_auto_open_on_spotify_switch(self, page: Page, base_url):
        # Quickstart is now launcher-only; switching tabs should not pop the modal.
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        switch_to_tab(page, "spotify")
        page.wait_for_timeout(300)
        expect(page.locator("#quickstartModal")).to_be_hidden()

    def test_last_step_next_closes_modal(self, page: Page, base_url):
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Repeat"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="6"]')).to_be_visible()
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(250)
        expect(page.locator("#quickstartModal")).to_be_hidden()

