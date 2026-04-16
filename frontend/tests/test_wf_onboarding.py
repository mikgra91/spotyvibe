"""Integration test: Onboarding / Setup workflow."""
import json
import re
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import create_integration_server


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestOnboardingSetupWorkflow:
    """Full onboarding wizard — 7 steps from Welcome to Ready."""

    def _navigate_to_onboarding(self, page: Page, base_url: str):
        page.route("**/api/onboarding/status", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"completed": False}),
        ))
        page.goto(base_url + "/onboarding?replay=1")
        page.wait_for_load_state("domcontentloaded")

    def _go_to_page(self, page: Page, target: int):
        for _ in range(target):
            cta = page.locator(
                ".ob-page.active .ob-cta-start, .ob-page.active .ob-cta-skip-inline"
            ).first
            cta.click()
            page.wait_for_timeout(250)

    def test_onboarding_loads_welcome_step(self, page: Page, base_url):
        self._navigate_to_onboarding(page, base_url)
        expect(page.locator(".ob-wrap")).to_be_visible()
        expect(page.locator(".ob-feature")).to_have_count(3)
        pills = page.locator(".ob-pill")
        expect(pills.first).to_have_class(re.compile(r"ob-pill--current"))

    def test_step_indicators_advance(self, page: Page, base_url):
        self._navigate_to_onboarding(page, base_url)
        first_page_pills = page.locator(".ob-page").first.locator(".ob-pill")
        expect(first_page_pills.nth(0)).to_have_class(re.compile(r"ob-pill--current"))
        self._go_to_page(page, 1)
        active_pills = page.locator(".ob-page.active .ob-pill")
        expect(active_pills.nth(0)).to_have_class(re.compile(r"ob-pill--complete"))
        expect(active_pills.nth(1)).to_have_class(re.compile(r"ob-pill--current"))

    def test_openai_credential_step(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 1)
        expect(page.locator("#ob-openai-key")).to_be_visible()

    def test_spotify_credential_step(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 2)
        expect(page.locator("#ob-spotify-id")).to_be_visible()
        expect(page.locator("#ob-spotify-secret")).to_be_visible()

    def test_credential_save_button_present(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 1)
        expect(page.locator("#ob-openai-key")).to_be_attached()
        next_btn = page.locator('.ob-cta-next[onclick="obSaveAndNext()"]')
        assert next_btn.count() >= 1

    def test_full_wizard_to_ready_step(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
                "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
                "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
            }),
        ))
        page.route("**/api/spotify/status", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "authenticated"}),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 6)
        ready_cta = page.locator(
            ".ob-page.active .ob-cta-start, .ob-page.active .ob-cta--finish, "
            ".ob-page.active .ob-cta-next"
        )
        expect(ready_cta.first).to_be_visible()

    def test_language_toggle_visible_throughout(self, page: Page, base_url):
        self._navigate_to_onboarding(page, base_url)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()
        self._go_to_page(page, 1)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()
        self._go_to_page(page, 3)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()

    def test_skip_button_present_on_welcome(self, page: Page, base_url):
        self._navigate_to_onboarding(page, base_url)
        skip = page.locator('.ob-page.active .ob-btn-skip[onclick="skipOnboarding()"]')
        expect(skip).to_be_visible()

