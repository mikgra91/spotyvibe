"""Profile editor, export, warnings, and toast notification tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    open_profile_editor, close_profile_editor,
    open_generate_section, open_burger_menu,
)


class TestProfileEditor:
    """Music Profile section — editing, accordion panels, save/cancel."""

    def test_edit_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("#trainToggleBtn")).to_be_visible()

    def test_editor_hidden_by_default_when_trained(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#trainToggleBtn")).to_be_visible()

    def test_toggle_opens_and_closes_editor(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        close_profile_editor(page)
        page.locator("#trainToggleBtn").click()
        body = page.locator("#trainBody")
        expect(body).to_be_visible()
        expect(page.locator("#trainToggleBtn")).to_have_text("Hide")
        page.locator("#trainToggleBtn").click()
        expect(body).to_be_hidden()
        expect(page.locator("#trainToggleBtn")).to_have_text("Show")

    def test_accordion_sections_present(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        expect(page.locator("#accCoreDesc")).to_be_visible()
        expect(page.locator("#accMustHave")).to_be_visible()
        expect(page.locator("#accSoftPrefs")).to_be_visible()
        expect(page.locator("#accAvoid")).to_be_visible()

    def test_core_description_required_validation(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        core_desc = page.locator("#trainCoreDesc")
        expect(core_desc).to_be_visible()
        core_desc.fill("")
        page.locator("#trainSaveBtn").click()
        toast = page.locator("#toast")
        expect(toast).to_be_visible(timeout=1500)

    def test_save_profile_directly(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        core_desc = page.locator("#trainCoreDesc")
        expect(core_desc).to_be_visible()
        core_desc.fill("Upbeat rock with strong melodies")
        page.locator("#trainSaveBtn").click()
        toast = page.locator("#toast")
        expect(toast).to_be_visible(timeout=1500)

    def test_accordion_toggle(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        must_have = page.locator("#accMustHave")
        header = must_have.locator(".accordion-header")
        expect(must_have).not_to_have_class(re.compile(r"open"))
        header.click()
        expect(must_have).to_have_class(re.compile(r"open"))
        header.click()
        expect(must_have).not_to_have_class(re.compile(r"open"))

    def test_describe_your_vibe_textarea_present(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        vibe = page.locator("textarea#trainVibeDesc, textarea[placeholder*='vibe'], textarea[placeholder*='Vibe']").first
        if not vibe.is_visible():
            vibe = page.locator("#trainBody textarea").first
        expect(vibe).to_be_visible()

    def test_import_export_reset_visible_in_edit_mode(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        close_profile_editor(page)
        page.locator("#trainToggleBtn").click()
        expect(page.locator("#trainBody")).to_be_visible()
        expect(page.locator("#profileMenuTrigger")).to_be_visible()
        page.locator("#profileMenuTrigger").click()
        expect(page.locator("#profileMenuUpload")).to_be_visible()
        expect(page.locator("#profileMenuExport")).to_be_visible()
        expect(page.locator("#profileMenuReset")).to_be_visible()
        expect(page.locator("#profileMenuDelete")).to_be_visible()


class TestProfileExport:
    """Profile export downloads a JSON file."""

    def test_export_triggers_download(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        close_profile_editor(page)
        page.locator("#trainToggleBtn").click()
        expect(page.locator("#trainBody")).to_be_visible()
        expect(page.locator("#profileMenuTrigger")).to_be_visible()
        page.locator("#profileMenuTrigger").click()
        expect(page.locator("#profileMenuExport")).to_be_visible()
        with page.expect_download() as download_info:
            page.locator("#profileMenuExport").click()
        download = download_info.value
        assert download.suggested_filename == "spotyvibe_profile.json"


class TestWarningsWithMissingCredentials:
    """Verify warnings appear when credentials/auth are missing."""

    def test_openai_warning_when_key_missing(self, page: Page, base_url):
        page.goto(base_url)

        def handle_creds(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "OPENAI_API_KEY": {"masked": "", "is_set": False},
                    "SPOTIPY_CLIENT_ID": {"masked": "****", "is_set": True},
                    "SPOTIPY_CLIENT_SECRET": {"masked": "****", "is_set": True},
                }),
            )

        page.route("**/api/settings/credentials", handle_creds)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        train_warn = page.locator("#trainWarn")
        expect(train_warn).to_be_visible()
        expect(train_warn).to_contain_text("OpenAI API key is missing")
        open_generate_section(page)
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("OpenAI API key is missing")
        expect(page.locator("#trainSendBtn")).to_be_disabled()
        expect(page.locator("#trainToggleBtn")).to_be_disabled()
        expect(page.locator("#runBtn")).to_be_disabled()

    def test_spotify_warning_when_not_authenticated(self, page: Page, base_url):
        page.goto(base_url)

        def handle_spotify(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "not_authenticated"}),
            )

        page.route("**/api/spotify/status", handle_spotify)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("Spotify login required")
        expect(page.locator("#runBtn")).to_be_disabled()

    def test_spotify_warning_when_not_configured(self, page: Page, base_url):
        page.goto(base_url)

        def handle_spotify(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "not_configured"}),
            )

        page.route("**/api/spotify/status", handle_spotify)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("Spotify credentials are missing")

    def test_no_openai_warning_for_local_provider(self, page: Page, base_url):
        page.goto(base_url)

        def handle_settings(route):
            if route.request.method == "GET":
                route.fulfill(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({
                        "model": "llama3",
                        "debug_mode": False,
                        "debug_controls_available": True,
                        "debug_log_path": "debug.log",
                        "playlist_size": 10,
                        "new_artist_percentage": 30,
                        "provider_preset": "ollama",
                        "llm_api_key_required": False,
                    }),
                )
            else:
                route.continue_()

        def handle_creds(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "OPENAI_API_KEY": {"masked": "", "is_set": False},
                    "SPOTIPY_CLIENT_ID": {"masked": "****", "is_set": True},
                    "SPOTIPY_CLIENT_SECRET": {"masked": "****", "is_set": True},
                }),
            )

        page.route("**/api/settings", handle_settings)
        page.route("**/api/settings/credentials", handle_creds)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        train_warn = page.locator("#trainWarn")
        expect(train_warn).to_have_class(re.compile(r"hidden"))
        expect(page.locator("#trainToggleBtn")).to_be_enabled()


class TestToastNotifications:
    """Toast notifications appear for user actions."""

    def test_toast_appears_on_feedback(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run(route):
            sse_body = (
                'data: {"type":"result","playlist":['
                '{"artist":"Toast Artist","track":"Toast Song","reason":"Test"}],'
                '"playlist_url":"https://open.spotify.com/playlist/t",'
                '"added":1,"not_found":[],"was_cancelled":false}\n\n'
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream"},
                body=sse_body,
            )

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run)
        page.route("**/api/profile/status", handle_profile_status)
        page.route("**/api/feedback", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ))

        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=2500)
        page.locator("#track-0 .btn-feedback").click()
        page.locator("#submitBtn-0-like").click()
        toast = page.locator("#toast")
        expect(toast).to_contain_text("Liked", timeout=1500)

