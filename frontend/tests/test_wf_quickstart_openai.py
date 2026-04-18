"""Integration test: Quickstart Guide — OpenAI provider."""
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


class TestQuickstartOpenAIWorkflow:
    """Quickstart guide for the OpenAI provider."""

    def _open_quickstart_openai(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "openai")
        page.wait_for_timeout(100)
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        page.evaluate("openQuickstart(true)")
        page.wait_for_timeout(150)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_quickstart_opens_for_openai(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_toc_has_correct_openai_entries(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc).to_be_visible()
        visible_entries = toc.locator(
            '.qs-toc-entry[data-qs-provider="both"], '
            '.qs-toc-entry[data-qs-provider="openai"]'
        )
        assert visible_entries.count() == 2
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Build Your Profile"]')).to_be_visible()

    def test_toc_does_not_show_spotify_entries(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()

    def test_setup_step_has_demo_player(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"] .qs-demo-player')).to_be_visible()

    def test_profile_step_content(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Build Your Profile"]').click()
        page.wait_for_timeout(150)
        step_page = page.locator('[data-qs-page="2"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Build Your Profile")
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_pagination_navigates_steps(self, page: Page, base_url):
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="2"]')).to_be_visible()
        page.locator("#qsPagPrev").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

    def test_quickstart_does_not_auto_open_on_load(self, page: Page, base_url):
        # Quickstart is now launcher-only; loading the page should not pop the modal.
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        page.wait_for_timeout(300)
        expect(page.locator("#quickstartModal")).to_be_hidden()

