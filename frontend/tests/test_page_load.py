"""Page load, meta tags, visual styling, and responsive layout tests."""

import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    switch_to_tab, open_generate_section, open_profile_editor,
    open_burger_menu,
)


@pytest.fixture(scope="class")
def loaded_page(browser, base_url):
    """A page that has already navigated to base_url — shared across a class."""
    ctx = browser.new_context(locale="en-US")
    pg = ctx.new_page()
    pg.set_default_timeout(10_000)
    pg.set_default_navigation_timeout(10_000)
    pg.add_init_script(
        "localStorage.setItem('spotyvibe-quickstart-dismissed', 'true');"
    )
    pg.goto(base_url)
    pg.wait_for_load_state("domcontentloaded")
    yield pg
    pg.close()
    ctx.close()


class TestPageLoad:
    """The main page loads and shows the essential structure (single page load)."""

    def test_title_is_spotyvibe(self, loaded_page):
        expect(loaded_page).to_have_title("SpotyVibe")

    def test_heading_visible(self, loaded_page):
        expect(loaded_page.locator("h1")).to_have_text("SpotyVibe")

    def test_subtitle_visible(self, loaded_page):
        expect(loaded_page.locator(".subtitle")).to_be_visible()

    def test_openai_tab_panel_visible_by_default(self, loaded_page):
        expect(loaded_page.locator("#providerOpenai")).to_be_visible()
        expect(loaded_page.locator("#providerSpotify")).to_be_hidden()

    def test_history_panel_hidden_by_default(self, loaded_page):
        expect(loaded_page.locator("#historyPanel")).to_be_hidden()


class TestPageLoadInteractive:
    """Tests that need their own page load because they mutate state."""

    def test_provider_sections_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator(".provider-badge-openai")).to_be_visible()
        switch_to_tab(page, "spotify")
        expect(page.locator(".provider-badge-spotify")).to_be_visible()

    def test_generate_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        expect(page.locator("#runBtn")).to_have_text("▶ Generate Suggestions")


class TestMetaTags:
    """Verify essential meta tags are present (shared page load)."""

    def test_theme_color_meta_tag(self, loaded_page):
        meta = loaded_page.locator('meta[name="theme-color"]')
        expect(meta).to_have_count(1)
        content = meta.get_attribute("content")
        assert content and content.strip(), "theme-color meta tag has no content"

    def test_body_background_gradient_applied(self, loaded_page):
        bg_image = loaded_page.evaluate("getComputedStyle(document.body).backgroundImage")
        assert "gradient" in bg_image, f"Expected gradient on body, got: {bg_image}"

    def test_heading_color(self, loaded_page):
        # Read the parsed RGB triple via a 1x1 canvas so the check is robust
        # against modern color forms (`oklch(...)`, `color-mix(...)`) that
        # getComputedStyle may surface in newer browsers. The h1 carries a
        # colored brand accent, so we only assert the text is not invisible
        # — not transparent, and reasonably bright on the dark background.
        rgb = loaded_page.evaluate(
            """() => {
                const c = document.createElement('canvas');
                c.width = c.height = 1;
                const ctx = c.getContext('2d');
                ctx.fillStyle = getComputedStyle(document.querySelector('h1')).color;
                ctx.fillRect(0, 0, 1, 1);
                return Array.from(ctx.getImageData(0, 0, 1, 1).data);
            }"""
        )
        r, g, b, a = rgb
        assert a > 0, f"h1 is fully transparent: {rgb}"
        assert (r, g, b) != (0, 0, 0), f"h1 has wrong color (should be light): {rgb}"
        # Perceived brightness (rec. 601). Brand green ~ 162; pure white ~ 255;
        # near-black ~ 0–50. Anything >= 100 is visible on the dark background.
        brightness = 0.299 * r + 0.587 * g + 0.114 * b
        assert brightness >= 100, (
            f"h1 is too dark to be readable on dark background, "
            f"rgb={rgb}, brightness={brightness:.0f}"
        )

    def test_font_family_inter(self, loaded_page):
        font = loaded_page.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily")
        assert "Inter" in font, f"Expected Inter font, got: {font}"

    def test_primary_color_on_active_tab(self, loaded_page):
        color = loaded_page.evaluate(
            "getComputedStyle(document.querySelector('[data-tab=\"openai\"]')).color"
        )
        assert color != "rgb(101, 103, 107)", f"Active tab appears muted: {color}"

    def test_glass_panel_has_background(self, loaded_page):
        bg = loaded_page.evaluate(
            "getComputedStyle(document.querySelector('.provider-section')).background"
        )
        assert bg and bg != "none", f"Provider section has no background: {bg}"

    def test_input_dark_background(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        bg = page.evaluate(
            "getComputedStyle(document.querySelector('#trainCoreDesc')).backgroundColor"
        )
        assert bg == "rgb(15, 19, 24)", f"Expected --bg-input, got: {bg}"

    def test_theme_switch_changes_body_class(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-pulse"))
        page.locator('[data-theme="equalizer"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-equalizer"))

    def test_css_stylesheets_loaded(self, page: Page, base_url):
        css_errors = []
        page.on("response", lambda resp: css_errors.append(resp.url)
                if resp.url.endswith(".css") and resp.status != 200 else None)
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        sheet_count = page.evaluate("document.styleSheets.length")
        assert sheet_count >= 11, f"Expected ≥11 CSS sheets loaded, got {sheet_count}"
        assert len(css_errors) == 0, f"CSS load errors: {css_errors}"

    def test_generate_button_has_gradient(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        bg_image = page.evaluate(
            "getComputedStyle(document.querySelector('#runBtn')).backgroundImage"
        )
        assert "gradient" in bg_image, f"Expected gradient on #runBtn, got: {bg_image}"

    def test_mobile_no_horizontal_overflow(self, page: Page, base_url):
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(base_url)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert not overflow, "Horizontal overflow detected at 375px viewport"


class TestResponsiveLayout:
    """Basic responsive layout checks."""

    def test_mobile_viewport(self, page: Page, base_url):
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(base_url)
        expect(page.locator("h1")).to_be_visible()
        expect(page.locator('[data-tab="spotify"]')).to_be_visible()
        expect(page.locator("button[aria-label=\"Menu\"]")).to_be_visible()

    def test_tablet_viewport(self, page: Page, base_url):
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(base_url)
        expect(page.locator("h1")).to_be_visible()
        expect(page.locator('[data-tab="spotify"]')).to_be_visible()

    def test_open_data_dir_hidden_on_mobile(self, page: Page, base_url):
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        expect(page.locator("#settingsModal")).to_have_class(re.compile(r"open"))
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        expect(page.locator("#openDataDirBtn")).to_be_hidden()

    def test_open_data_dir_visible_on_desktop(self, page: Page, base_url):
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        expect(page.locator("#settingsModal")).to_have_class(re.compile(r"open"))
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=2500)
        expect(page.locator("#openDataDirBtn")).to_be_visible()
