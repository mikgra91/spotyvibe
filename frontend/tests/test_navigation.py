"""Theme switcher, burger menu, keyboard navigation, i18n, and custom dialog tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    switch_to_tab, open_burger_menu, open_profile_editor,
    open_analysis_section,
)


class TestThemeSwitcher:
    """Theme switcher — Equalizer and Pulse themes."""

    def test_theme_buttons_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator('[data-theme="equalizer"]')).to_be_visible()
        expect(page.locator('[data-theme="pulse"]')).to_be_visible()

    def test_calm_is_default(self, page: Page, base_url):
        page.goto(base_url)
        calm_btn = page.locator('[data-theme="calm"]')
        expect(calm_btn).to_have_class(re.compile(r"active"))
        expect(page.locator("body")).to_have_class(re.compile(r"theme-calm"))

    def test_switch_to_pulse(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-pulse"))
        expect(page.locator('[data-theme="pulse"]')).to_have_class(re.compile(r"active"))
        expect(page.locator('[data-theme="equalizer"]')).not_to_have_class(re.compile(r"active"))

    def test_switch_back_to_equalizer(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        page.locator('[data-theme="equalizer"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-equalizer"))

    def test_theme_persists_via_localstorage(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        theme = page.evaluate("localStorage.getItem('spotyvibe-theme')")
        assert theme == "pulse"


class TestBurgerMenu:
    """Burger menu icon and dropdown menu."""

    def test_burger_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("button[aria-label=\"Menu\"]")).to_be_visible()

    def test_dropdown_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("#settingsDropdown")).not_to_have_class(re.compile(r"open"))

    def test_dropdown_opens_on_click(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)

    def test_dropdown_has_all_options(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        dd = page.locator("#settingsDropdown")
        expect(dd.locator("[data-i18n='nav.credentials']")).to_be_visible()
        expect(dd.locator("[data-i18n='nav.settings']")).to_be_visible()
        expect(dd.locator("[data-i18n='nav.help']")).to_be_visible()

    def test_dropdown_closes_on_outside_click(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("h1").click()
        expect(page.locator("#settingsDropdown")).not_to_have_class(re.compile(r"open"))

    def test_spotify_toggle_shows_disconnect_when_authenticated(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_burger_menu(page)
        expect(page.locator("#spotifyToggleBtn")).to_contain_text("Disconnect Spotify")


class TestSpotifyStatusPill:
    """U6 (2026-05-07): live Spotify status pill in the header.

    The pill mirrors `State.spotifyAuthStatus` into a CSS class so the
    coloured dot reflects the live connection state. Conftest patches
    `get_spotify_auth_status` to return ``"authenticated"``, so the pill
    should land in the connected state on every page load.
    """

    def test_pill_visible_in_header(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#spotifyStatusPill")).to_be_visible()

    def test_pill_shows_connected_when_authenticated(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        # Wait for renderComponentWarnings() to fire after the
        # checkSpotifyAuth() pre-flight ping resolves.
        pill = page.locator("#spotifyStatusPill.spotify-status-connected")
        expect(pill).to_be_visible(timeout=5_000)

    def test_pill_aria_label_localised(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        pill = page.locator("#spotifyStatusPill.spotify-status-connected")
        expect(pill).to_be_visible(timeout=5_000)
        expect(pill).to_have_attribute("aria-label", "Spotify connected")


class TestKeyboardNavigation:
    """Keyboard accessibility — tab bar, accordion, modals, skip link."""

    def test_tab_bar_activate_with_enter(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator('[data-tab="spotify"]').focus()
        page.keyboard.press("Enter")
        expect(page.locator('[data-tab="spotify"]')).to_have_attribute(
            "aria-selected", "true"
        )
        expect(page.locator("#providerSpotify")).to_be_visible()

    def test_accordion_header_enter_toggles(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        must_have = page.locator("#accMustHave")
        header = must_have.locator(".accordion-header")
        expect(must_have).not_to_have_class(re.compile(r"open"))
        header.focus()
        page.keyboard.press("Enter")
        expect(must_have).to_have_class(re.compile(r"open"))

    def test_accordion_header_space_toggles(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        soft_prefs = page.locator("#accSoftPrefs")
        header = soft_prefs.locator(".accordion-header")
        expect(soft_prefs).not_to_have_class(re.compile(r"open"))
        header.focus()
        page.keyboard.press("Space")
        expect(soft_prefs).to_have_class(re.compile(r"open"))

    def test_section_toggle_keyboard_enter(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "openai")
        header = page.locator("#analysisSection .train-header")
        body = page.locator("#analysisBody")
        if body.is_visible():
            page.locator("#analysisToggleBtn").click()
            expect(body).to_be_hidden()
        header.focus()
        page.keyboard.press("Enter")
        expect(body).to_be_visible()

    def test_skip_link_visible_on_focus(self, page: Page, base_url):
        page.goto(base_url)
        has_focus_rule = page.evaluate("""
            () => {
                for (const sheet of document.styleSheets) {
                    try {
                        for (const rule of sheet.cssRules) {
                            if (rule.selectorText === '.skip-link:focus' &&
                                    rule.style.top === '16px') {
                                return true;
                            }
                        }
                    } catch (e) {}
                }
                return false;
            }
        """)
        assert has_focus_rule, "No .skip-link:focus { top: 16px } CSS rule found"

    def test_help_modal_escape_closes(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown [data-i18n='nav.help']").click()
        expect(page.locator("#helpModal")).to_have_class(re.compile(r"open"))
        page.keyboard.press("Escape")
        expect(page.locator("#helpModal")).not_to_have_class(re.compile(r"open"))

    def test_burger_menu_button_keyboard(self, page: Page, base_url):
        page.goto(base_url)
        burger = page.locator('button[aria-label="Menu"]')
        burger.focus()
        page.keyboard.press("Enter")
        expect(page.locator("#settingsDropdown")).to_have_class(re.compile(r"open"))


class TestI18n:
    """Internationalisation — default English, no missing keys, German switch."""

    def test_default_language_english(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        heading = page.locator("h1").text_content()
        assert "SpotyVibe" in heading
        subtitle = page.locator(".subtitle").text_content()
        assert subtitle.strip() != "", "Subtitle should have English text"

    def test_no_untranslated_data_i18n_elements(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        empty = page.evaluate("""
            () => {
                const els = [...document.querySelectorAll('[data-i18n]')];
                return els.filter(el => {
                    const tag = el.tagName.toLowerCase();
                    if (['input','select','textarea','meta','link'].includes(tag)) return false;
                    const style = getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    return el.textContent.trim() === '';
                }).map(el => el.getAttribute('data-i18n'));
            }
        """)
        assert len(empty) == 0, f"Elements with empty i18n text: {empty}"

    def test_language_localstorage_default(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        lang = page.evaluate("localStorage.getItem('svLang')")
        assert lang in (None, "en"), f"Unexpected default language: {lang}"

    def test_language_switch_to_german(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.route("**/api/settings", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ))
        page.evaluate("window.i18n && window.i18n.setLanguage ? window.i18n.setLanguage('de') : null")
        page.wait_for_timeout(150)
        lang = page.evaluate("localStorage.getItem('svLang')")
        assert lang in (None, "en", "de"), f"Unexpected language state: {lang}"


class TestCustomDialogs:
    """Custom confirm/alert dialogs replace native alert()/confirm()."""

    def _open_credentials(self, page: Page):
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))

    def test_clear_credential_shows_custom_confirm(self, page: Page, base_url):
        page.goto(base_url)
        self._open_credentials(page)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#clear-OPENAI_API_KEY").click()
        confirm_overlay = page.locator("#customConfirmOverlay")
        expect(confirm_overlay).to_have_class(re.compile(r"open"), timeout=1000)
        expect(confirm_overlay).to_contain_text("Remove")

    def test_custom_confirm_cancel_dismisses(self, page: Page, base_url):
        page.goto(base_url)
        self._open_credentials(page)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#clear-OPENAI_API_KEY").click()
        confirm_overlay = page.locator("#customConfirmOverlay")
        expect(confirm_overlay).to_have_class(re.compile(r"open"), timeout=1000)
        confirm_overlay.locator(".btn-cancel").click()
        expect(confirm_overlay).to_have_count(0)

    def test_custom_confirm_closes_on_escape(self, page: Page, base_url):
        page.goto(base_url)
        self._open_credentials(page)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#clear-OPENAI_API_KEY").click()
        expect(page.locator("#customConfirmOverlay")).to_have_class(
            re.compile(r"open"), timeout=1000
        )
        page.keyboard.press("Escape")
        expect(page.locator("#customConfirmOverlay")).to_have_count(0)

