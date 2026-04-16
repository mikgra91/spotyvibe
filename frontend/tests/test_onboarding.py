"""Onboarding flow, wizard, credential prefill, and Wave 2 quick wins tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    switch_to_tab, open_profile_editor, open_generate_section,
    navigate_onboarding_to_page,
)


class TestOnboardingCredentialPrefill:
    """Onboarding page prefills credential status when keys are already set."""

    def test_shows_green_status_when_openai_key_set(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
                "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
                "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
            }),
        ))
        navigate_onboarding_to_page(page, base_url, 1)
        page.locator("#ob-set-openai:not(.hidden)").wait_for(timeout=5000)
        expect(page.locator("#ob-set-openai")).to_be_visible()
        expect(page.locator("#ob-set-openai")).to_contain_text("OK")
        expect(page.locator("#ob-input-wrap-openai")).to_be_hidden()

    def test_shows_green_status_when_spotify_creds_set(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 2)
        page.locator("#ob-set-spotify-id:not(.hidden)").wait_for(timeout=5000)
        expect(page.locator("#ob-set-spotify-id")).to_be_visible()
        expect(page.locator("#ob-set-spotify-id")).to_contain_text("OK")
        expect(page.locator("#ob-set-spotify-secret")).to_be_visible()
        expect(page.locator("#ob-set-spotify-secret")).to_contain_text("OK")
        expect(page.locator("#ob-input-wrap-spotify-id")).to_be_hidden()
        expect(page.locator("#ob-input-wrap-spotify-secret")).to_be_hidden()

    def test_no_duplicate_skip_button_in_cred_section(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 1)
        cred_section = page.locator(".ob-cred-section")
        skip_buttons_in_section = cred_section.locator(".ob-btn-skip")
        expect(skip_buttons_in_section).to_have_count(0)


class TestOnboardingFlow:
    """Onboarding wizard — 7-step flow."""

    def test_onboarding_page_loads(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 0)
        expect(page).to_have_title(re.compile(r"SpotyVibe"))
        expect(page.locator(".ob-wrap")).to_be_visible()
        expect(page.locator(".ob-icon").first).to_be_attached()

    def test_step_indicators_update_on_navigation(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 0)
        pills = page.locator(".ob-pill")
        expect(pills.first).to_have_class(re.compile(r"ob-pill--current"))
        page.locator(".ob-cta-start").click()
        page.wait_for_timeout(250)
        pages = page.locator(".ob-page")
        expect(pages.nth(1)).to_have_class(re.compile(r"active"))

    def test_language_toggle_always_visible(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 0)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()
        en_btn = page.locator(".ob-lang-toggle .lang-toggle-btn[data-lang='en']")
        expect(en_btn).to_have_class(re.compile(r"active"))

    def test_language_switch_to_german(self, page: Page, base_url):
        page.route("**/api/settings", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ) if route.request.method == "POST" else route.continue_())
        navigate_onboarding_to_page(page, base_url, 0)
        page.locator(".ob-lang-toggle .lang-toggle-btn[data-lang='de']").click()
        page.wait_for_timeout(250)
        expect(page.locator(".ob-lang-toggle .lang-toggle-btn[data-lang='de']")).to_have_class(re.compile(r"active"))
        expect(page.locator(".ob-lang-toggle .lang-toggle-btn[data-lang='en']")).not_to_have_class(re.compile(r"active"))
        lang = page.evaluate("localStorage.getItem('svLang')")
        assert lang == "de"

    def test_openai_step_shows_input_when_not_set(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        navigate_onboarding_to_page(page, base_url, 1)
        page.locator("#ob-input-wrap-openai:not(.hidden)").wait_for(timeout=5000)
        expect(page.locator(".ob-page.active .ob-cred-section")).to_be_visible()
        expect(page.locator("#ob-openai-key")).to_be_visible()

    def test_spotify_cred_step_shows_inputs_when_not_set(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        navigate_onboarding_to_page(page, base_url, 2)
        page.locator("#ob-input-wrap-spotify-id:not(.hidden)").wait_for(timeout=5000)
        expect(page.locator(".ob-page.active .ob-cred-section")).to_be_visible()
        expect(page.locator("#ob-spotify-id")).to_be_visible()
        expect(page.locator("#ob-spotify-secret")).to_be_visible()

    def test_openai_step_next_saves_credential(self, page: Page, base_url):
        save_requests = []
        def handle_creds(route):
            if route.request.method == "POST":
                save_requests.append(route.request.post_data_json)
                route.fulfill(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({"status": "ok"}),
                )
            else:
                route.fulfill(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({
                        "OPENAI_API_KEY": {"masked": "", "is_set": False},
                        "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                        "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
                    }),
                )
        page.route("**/api/settings/credentials", handle_creds)
        navigate_onboarding_to_page(page, base_url, 1)
        page.locator("#ob-input-wrap-openai:not(.hidden)").wait_for(timeout=5000)
        page.locator("#ob-openai-key").fill("sk-test-key")
        page.wait_for_timeout(100)
        page.locator(".ob-page.active .ob-cta-next").click()
        page.wait_for_timeout(250)
        assert len(save_requests) >= 1

    def test_spotify_connect_step_shows_button(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 3)
        expect(page.locator("#ob-spotify-btn")).to_be_visible()

    def test_skip_completes_onboarding_and_redirects(self, page: Page, base_url):
        complete_calls = []
        page.route("**/api/onboarding/complete", lambda route: (
            complete_calls.append(True),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            ),
        )[1])
        navigate_onboarding_to_page(page, base_url, 0)
        page.locator(".ob-btn-skip").first.click()
        page.wait_for_url(re.compile(r"127\.0\.0\.1:\d+/$"), timeout=10000)
        assert len(complete_calls) >= 1

    def test_back_button_navigates_backward(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 1)
        page.locator(".ob-page.active .ob-btn-skip").first.click()
        page.wait_for_timeout(250)
        transform = page.evaluate("document.getElementById('obPages').style.transform")
        assert transform == "translateX(0%)" or transform == "" or "0" in transform

    def test_onboarding_input_styling(self, page: Page, base_url):
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        navigate_onboarding_to_page(page, base_url, 1)
        bg = page.evaluate(
            "getComputedStyle(document.querySelector('.ob-cred-input')).backgroundColor"
        )
        assert bg == "rgb(15, 19, 24)", f"Expected dark input bg, got: {bg}"

    def test_onboarding_responsive_mobile(self, page: Page, base_url):
        page.set_viewport_size({"width": 375, "height": 812})
        navigate_onboarding_to_page(page, base_url, 0)
        expect(page.locator(".ob-wrap")).to_be_visible()
        expect(page.locator(".ob-icon").first).to_be_attached()
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert not overflow, "Horizontal overflow detected at mobile viewport"

    def test_finish_button_completes_onboarding(self, page: Page, base_url):
        complete_calls = []
        page.route("**/api/onboarding/complete", lambda route: (
            complete_calls.append(True),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            ),
        )[1])
        navigate_onboarding_to_page(page, base_url, 6)
        page.locator("#ob-finish-btn").click()
        page.wait_for_url(re.compile(r"127\.0\.0\.1:\d+/$"), timeout=10000)
        assert len(complete_calls) >= 1


class TestOnboardingWizardWave1:
    """Smoke tests for the 7-step onboarding wizard (Wave 1)."""

    def test_wizard_walks_7_steps(self, page: Page, base_url):
        page.route("**/api/onboarding/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"completed": False}),
        ))
        page.route("**/api/onboarding/complete", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ))
        page.goto(base_url + "/onboarding?replay=1")
        page.wait_for_load_state("domcontentloaded")
        page.locator(".ob-cta-start").click()
        page.wait_for_timeout(150)
        for _ in range(5):
            skip = page.locator(".ob-page.active .ob-cta-skip-inline, .ob-page.active .ob-cta-start").first
            skip.click()
            page.wait_for_timeout(150)
        expect(page.locator("#ob-finish-btn")).to_be_visible(timeout=5000)

    def test_wizard_howto_accordion_toggles(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 1)
        toggle = page.locator("#ob-guide-openai .ob-cred-guide-toggle")
        body = page.locator("#ob-openai-guide-body")
        expect(body).not_to_have_class(re.compile(r"open"))
        toggle.click()
        page.wait_for_timeout(100)
        expect(body).to_have_class(re.compile(r"open"))
        toggle.click()
        page.wait_for_timeout(100)
        expect(body).not_to_have_class(re.compile(r"open"))

    def test_privacy_modal_opens_and_closes(self, page: Page, base_url):
        navigate_onboarding_to_page(page, base_url, 0)
        page.locator(".ob-privacy-link").click()
        page.wait_for_timeout(150)
        expect(page.locator("#privacyModal")).to_have_class(re.compile(r"open"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        expect(page.locator("#privacyModal")).not_to_have_class(re.compile(r"open"))

    def test_language_toggle_persists_across_steps(self, page: Page, base_url):
        page.route("**/api/settings", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ) if route.request.method == "POST" else route.continue_())
        navigate_onboarding_to_page(page, base_url, 0)
        page.locator(".ob-lang-toggle button[data-lang='de']").click()
        page.wait_for_timeout(250)
        page.locator(".ob-cta-start").click()
        page.wait_for_timeout(150)
        expect(page.locator(".ob-lang-toggle button[data-lang='de']")).to_have_class(re.compile(r"active"))


class TestWave2QuickWins:
    """Smoke tests for Wave 2 features: Quick/Advanced, exploration slider,
    presets, and completeness meter."""

    def test_quick_advanced_mode_persists(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        assert page.evaluate("localStorage.getItem('sv.gen_mode')") == "advanced"
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        adv_btn = page.locator(".gen-mode-btn[data-mode='advanced']")
        expect(adv_btn).to_have_class(re.compile(r"active"))

    def test_exploration_slider_updates_underlying_fields(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        page.evaluate("""() => {
            const s = document.getElementById('explorationSlider');
            s.value = 1;
            s.dispatchEvent(new Event('input'));
        }""")
        page.wait_for_timeout(100)
        pct = page.evaluate("document.getElementById('genNewArtistPct').value")
        assert int(pct) == 10
        emerging = page.evaluate("document.getElementById('emergingArtistsCheckbox').checked")
        assert emerging is False

    def test_exploration_slider_custom_on_hand_edit(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        page.evaluate("""() => {
            const el = document.getElementById('genNewArtistPct');
            el.value = 33;
            el.dispatchEvent(new Event('input'));
            el.dispatchEvent(new Event('change'));
        }""")
        page.wait_for_timeout(150)
        label = page.locator(".exploration-value").text_content()
        assert "Custom" in label or "Eigene" in label

    def test_preset_save_and_reload(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("localStorage.removeItem('sv.presets.user')")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        page.locator(".preset-save-btn").click()
        page.wait_for_timeout(100)
        page.locator("#savePresetInput").fill("Test preset")
        page.locator("#savePresetModal .btn-save").click()
        page.wait_for_timeout(150)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        stored = page.evaluate("JSON.parse(localStorage.getItem('sv.presets.user') || '[]')")
        assert any(p["name"] == "Test preset" for p in stored)

    def test_completeness_hides_at_high_score(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        page.locator("#trainCoreDesc").fill("Upbeat melodic rock with strong hooks, theatrical vocals, and constant momentum — think Queen meets Bear Ghost.")
        page.evaluate("""() => {
            document.getElementById('trainMustHave').value = 'high energy\\nstrong memorable melodies\\nvocals';
            document.getElementById('trainSoftPrefs').value = 'prog influence';
            document.getElementById('trainAvoid').value = 'electronic/synth-heavy';
        }""")
        for sel in ["#trainCoreDesc", "#trainMustHave", "#trainSoftPrefs", "#trainAvoid"]:
            page.evaluate(f"document.querySelector('{sel}').dispatchEvent(new Event('input'))")
        page.wait_for_timeout(100)
        expect(page.locator("#profileCompletenessCard")).to_have_class(re.compile(r"is-complete"))

    def test_tooltip_removed_from_audio_filters(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(150)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        page.locator(".audio-filter-toggle").click()
        page.wait_for_timeout(100)
        energy_label = page.locator(".audio-filter-row:has-text('Energy') label")
        assert energy_label.get_attribute("data-tooltip") is None
        assert page.locator(".audio-filter-row:has-text('Energy') .inline-hint").is_visible()

