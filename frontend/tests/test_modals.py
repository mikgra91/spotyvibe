"""Credentials, Settings, Help, and Quickstart modal tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import open_burger_menu, open_quickstart


class TestCredentialsModal:
    """Credentials modal — entering API keys."""

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))

    def test_shows_three_fields(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        expect(page.locator("#cred-OPENAI_API_KEY")).to_be_visible()
        expect(page.locator("#cred-SPOTIPY_CLIENT_ID")).to_be_visible()
        expect(page.locator("#cred-SPOTIPY_CLIENT_SECRET")).to_be_visible()

    def test_shows_credential_status(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        expect(page.locator("#status-OPENAI_API_KEY")).to_contain_text("Set")
        expect(page.locator("#status-SPOTIPY_CLIENT_ID")).to_contain_text("Set")
        expect(page.locator("#status-SPOTIPY_CLIENT_SECRET")).to_contain_text("Set")

    def test_closes_on_cancel(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.locator("#credentialsModal .btn-cancel").click()
        expect(page.locator("#credentialsModal")).not_to_have_class(re.compile(r"open"))

    def test_closes_on_overlay_click(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.locator("#credentialsModal").click(position={"x": 5, "y": 5})
        expect(page.locator("#credentialsModal")).not_to_have_class(re.compile(r"open"))

    def test_closes_on_escape(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.keyboard.press("Escape")
        expect(page.locator("#credentialsModal")).not_to_have_class(re.compile(r"open"))

    def test_save_sends_api_call(self, page: Page, base_url):
        page.goto(base_url)
        save_requests = []

        def handle_save(route):
            save_requests.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            )

        page.route("**/api/settings/credentials", lambda route: (
            handle_save(route) if route.request.method == "POST" else route.continue_()
        ))

        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.locator("#cred-OPENAI_API_KEY").fill("sk-test-new-key")
        page.locator("#credentialsModal .btn-save").click()
        page.wait_for_timeout(150)
        assert len(save_requests) == 1


class TestSettingsModal:
    """Settings modal — model selection, playlist size, new artist %, debug mode."""

    def _open_settings(self, page: Page):
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        expect(page.locator("#settingsModal")).to_have_class(re.compile(r"open"))

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)

    def test_shows_model_dropdown(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)
        page.wait_for_load_state("domcontentloaded")
        select = page.locator("#settings-model")
        expect(select).to_be_visible()

    def test_model_dropdown_has_options(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        options = page.locator("#settings-model option").all_text_contents()
        assert "gpt-4.1-mini" in options
        assert "gpt-4.1" in options

    def test_shows_playlist_size(self, page: Page, base_url):
        page.goto(base_url)
        from helpers import open_generate_section
        open_generate_section(page)
        expect(page.locator("#genSize")).to_be_visible()

    def test_shows_new_artist_percentage(self, page: Page, base_url):
        page.goto(base_url)
        from helpers import open_generate_section
        open_generate_section(page)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        expect(page.locator("#genNewArtistPct")).to_be_visible()

    def test_stage3_radios_present_with_fast_default(self, page: Page, base_url):
        # L5 (2026-05-08): Stage 3 strategy radios appear with the
        # "Fast" preset checked by default (Path 3 default = no behaviour
        # change for existing users).
        page.goto(base_url)
        self._open_settings(page)
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        for value in ("fast", "best", "auto", "custom"):
            expect(page.locator(f"input[name='stage3_mode'][value='{value}']")).to_be_visible()
        expect(page.locator("input[name='stage3_mode'][value='fast']")).to_be_checked()

    def test_stage3_preset_disables_model_dropdown(self, page: Page, base_url):
        # When a preset (fast / best / auto) is active the model dropdown
        # is greyed out — preset modes ignore the dropdown value at
        # request time, so leaving it active would be misleading.
        page.goto(base_url)
        self._open_settings(page)
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        page.locator("input[name='stage3_mode'][value='auto']").click()
        expect(page.locator("#settings-model")).to_be_disabled()

    def test_stage3_custom_reenables_model_dropdown(self, page: Page, base_url):
        # Switching back to Custom must re-enable the model controls so
        # the user can pick their own model (incl. local LLMs).
        page.goto(base_url)
        self._open_settings(page)
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        page.locator("input[name='stage3_mode'][value='best']").click()
        expect(page.locator("#settings-model")).to_be_disabled()
        page.locator("input[name='stage3_mode'][value='custom']").click()
        expect(page.locator("#settings-model")).to_be_enabled()

    def test_shows_debug_mode_checkbox(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#settings-debug")).to_be_visible()

    def test_closes_on_cancel(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)
        page.locator("#settingsModal .btn-cancel").click()
        expect(page.locator("#settingsModal")).not_to_have_class(re.compile(r"open"))

    def test_closes_on_escape(self, page: Page, base_url):
        page.goto(base_url)
        self._open_settings(page)
        page.keyboard.press("Escape")
        expect(page.locator("#settingsModal")).not_to_have_class(re.compile(r"open"))


class TestHelpModal:
    """Help modal — loads and displays the user manual."""

    def _open_help(self, page: Page):
        open_burger_menu(page)
        page.locator("#settingsDropdown [data-i18n='nav.help']").click()
        expect(page.locator("#helpModal")).to_have_class(re.compile(r"open"))

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        self._open_help(page)

    def test_loads_help_content(self, page: Page, base_url):
        page.goto(base_url)
        self._open_help(page)
        page.locator("#helpContent >> text=SpotyVibe User Guide").wait_for(timeout=2500)
        expect(page.locator("#helpContent >> text=SpotyVibe User Guide")).to_be_visible()

    def test_help_contains_key_sections(self, page: Page, base_url):
        page.goto(base_url)
        self._open_help(page)
        page.locator("#helpContent >> text=SpotyVibe User Guide").wait_for(timeout=2500)
        content = page.locator("#helpContent")
        expect(content.locator("h2:has-text('Getting Started')").first).to_be_visible()
        expect(content.locator("h2:has-text('Playlist Generation')").first).to_be_visible()

    def test_closes_on_close_button(self, page: Page, base_url):
        page.goto(base_url)
        self._open_help(page)
        page.locator("#helpModal .help-close-btn").click()
        expect(page.locator("#helpModal")).not_to_have_class(re.compile(r"open"))

    def test_closes_on_escape_key(self, page: Page, base_url):
        page.goto(base_url)
        self._open_help(page)
        page.keyboard.press("Escape")
        expect(page.locator("#helpModal")).not_to_have_class(re.compile(r"open"))


class TestQuickstartModal:
    """Quickstart guide modal — TOC, pagination, navigation, close, don't-show-again."""

    def test_quickstart_opens_via_js(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)

    def test_toc_entries_visible(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        toc = page.locator(".qs-toc")
        expect(toc).to_be_visible()
        expect(toc.locator(".qs-toc-entry").first).to_be_visible()

    def test_toc_navigation_to_step(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

    def test_close_button_closes_modal(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        page.locator(".qs-close-btn").click()
        expect(page.locator("#quickstartModal")).to_be_hidden()

    def test_overlay_click_closes_modal(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        page.locator("#quickstartModal").click(position={"x": 5, "y": 5})
        expect(page.locator("#quickstartModal")).to_be_hidden()

    def test_dont_show_again_sets_localstorage(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("localStorage.removeItem('spotyvibe-quickstart-openai-dismissed')")
        page.evaluate("localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed')")
        open_quickstart(page)
        checkbox = page.locator(".quickstartDontShowCb")
        checkbox.check()
        page.locator(".qs-close-btn").click()
        page.wait_for_timeout(150)
        value = page.evaluate("localStorage.getItem('spotyvibe-quickstart-openai-dismissed')")
        assert value == "true"

    def test_pagination_next_advances_page(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="2"]')).to_be_visible()

    def test_pagination_back_returns_to_previous(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_quickstart(page)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(150)
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="2"]')).to_be_visible()
        page.locator("#qsPagPrev").click()
        page.wait_for_timeout(150)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

    def test_quickstart_opens_with_force_flag(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("localStorage.setItem('spotyvibe-quickstart-dismissed', 'true')")
        dismissed = page.evaluate("localStorage.getItem('spotyvibe-quickstart-dismissed')")
        assert dismissed == "true"
        open_quickstart(page)

